package main

import (
	"context"
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/dvr"
	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/led"
	"github.com/vincent99/velocipi/server/hardware/oled"
)

type client struct {
	conn *websocket.Conn
	send chan []byte
}

type Hub struct {
	mu            sync.RWMutex
	clients       map[*client]struct{}
	screenClients map[*client]struct{}
	browserCtx    context.Context
	cfg           *config.Config
	oled          *oled.OLED
	dvrManager    *dvr.Manager

	lastFrameMu sync.RWMutex
	lastFrame   []byte // most recent decoded PNG from the screencast
}

func newHub(browserCtx context.Context, cfg *config.Config, o *oled.OLED) *Hub {
	h := &Hub{
		clients:       make(map[*client]struct{}),
		screenClients: make(map[*client]struct{}),
		browserCtx:    browserCtx,
		cfg:           cfg,
		oled:          o,
	}
	// Broadcast LED state to all clients whenever it changes.
	hardware.LED().OnChange(func(s led.State) {
		h.broadcastAll(ledStateMsg(s))
	})
	return h
}

func (h *Hub) register(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.clients[c] = struct{}{}
	log.Println("hub: client registered, total:", len(h.clients))
}

func (h *Hub) unregister(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if _, ok := h.clients[c]; ok {
		delete(h.clients, c)
		close(c.send)
		log.Println("hub: client unregistered, total:", len(h.clients))
	}
}

func (h *Hub) registerScreen(c *client) {
	h.mu.Lock()
	h.screenClients[c] = struct{}{}
	log.Println("hub: screen client registered, total:", len(h.screenClients))
	h.mu.Unlock()

	// Send the most recent frame immediately so the client doesn't see a blank screen.
	h.lastFrameMu.RLock()
	buf := h.lastFrame
	h.lastFrameMu.RUnlock()
	if buf != nil {
		select {
		case c.send <- buf:
		default:
		}
	}
}

func (h *Hub) unregisterScreen(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if _, ok := h.screenClients[c]; ok {
		delete(h.screenClients, c)
		close(c.send)
		log.Println("hub: screen client unregistered, total:", len(h.screenClients))
	}
}

func (h *Hub) screenshotClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.screenClients)
}

func (h *Hub) sendToClients(data []byte, clients map[*client]struct{}) {
	h.mu.RLock()
	snapshot := make([]*client, 0, len(clients))
	for c := range clients {
		snapshot = append(snapshot, c)
	}
	h.mu.RUnlock()

	for _, c := range snapshot {
		select {
		case c.send <- data:
		default:
		}
	}
}

// broadcastScreen sends raw PNG bytes as a binary frame to all /screen clients.
func (h *Hub) broadcastScreen(buf []byte) {
	h.sendToClients(buf, h.screenClients)
}

// broadcastAll sends to every /ws client.
func (h *Hub) broadcastAll(msg any) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Println("hub marshal error:", err)
		return
	}
	h.sendToClients(data, h.clients)
}

// broadcastKeyEcho notifies all clients that a logical key event was dispatched.
func (h *Hub) broadcastKeyEcho(logical, eventType string) {
	h.broadcastAll(KeyEchoMsg{Type: "keyEcho", EventType: eventType, Key: logical})
}

// sendCameraStatuses sends the current recording status of all cameras to a single client.
func (h *Hub) sendCameraStatuses(c *client) {
	if h.dvrManager == nil {
		return
	}
	for _, msg := range h.dvrManager.CameraStatuses() {
		data, err := json.Marshal(msg)
		if err != nil {
			continue
		}
		select {
		case c.send <- data:
		default:
		}
	}
}

// sendLEDState sends the current LED state to a single client.
func (h *Hub) sendLEDState(c *client) {
	l := hardware.LED()
	data, err := json.Marshal(ledStateMsg(l.CurrentState()))
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// handleLEDMsg controls the expander LED from a websocket message.
func (h *Hub) handleLEDMsg(state string, rateMs int) {
	e := hardware.Expander()
	if e == nil {
		return
	}
	l := hardware.LED()
	switch state {
	case "on":
		l.On(e)
	case "off":
		l.Off(e)
	case "blink":
		if rateMs <= 0 {
			rateMs = 500
		}
		l.Blink(e, time.Duration(rateMs)*time.Millisecond)
	}
}
