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
	"github.com/vincent99/velocipi/server/hardware/g3x"
	"github.com/vincent99/velocipi/server/hardware/led"
	"github.com/vincent99/velocipi/server/hardware/oled"
	"github.com/vincent99/velocipi/server/hardware/siyi"
	"github.com/vincent99/velocipi/server/music"
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
	oled          oled.Display
	dvrManager    *dvr.Manager
	localCamera   string                   // name of the camera shown on the local display
	musicPlayer   music.PlayerController   // nil if music subsystem is disabled
	siyiManagers  map[string]*siyi.Manager // camera name → Siyi manager (nil if no Siyi cameras)

	lastFrameMu sync.RWMutex
	lastFrame   []byte // most recent decoded PNG from the screencast
}

func newHub(browserCtx context.Context, cfg *config.Config, o oled.Display) *Hub {
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
	// Send current DVR state.
	stateMsg := dvr.DVRStateMsg{Type: "dvrState", State: h.dvrManager.State()}
	if data, err := json.Marshal(stateMsg); err == nil {
		select {
		case c.send <- data:
		default:
		}
	}
	// Send most recent disk space reading if available.
	if ds := h.dvrManager.LastDiskSpace(); ds != nil {
		if data, err := json.Marshal(ds); err == nil {
			select {
			case c.send <- data:
			default:
			}
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

// sendLocalCamera sends the current panel camera name to a single client.
func (h *Hub) sendLocalCamera(c *client) {
	h.mu.RLock()
	name := h.localCamera
	h.mu.RUnlock()
	data, err := json.Marshal(LocalCameraMsg{Type: "localCamera", Camera: name})
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// SetMusicPlayer stores the music player controller so hub can delegate
// musicControl WebSocket messages and send initial state to new clients.
func (h *Hub) SetMusicPlayer(p music.PlayerController) {
	h.mu.Lock()
	h.musicPlayer = p
	h.mu.Unlock()
}

// BroadcastAll is the exported wrapper for broadcastAll, satisfying the
// music.Broadcaster interface without an import cycle.
func (h *Hub) BroadcastAll(msg any) {
	h.broadcastAll(msg)
}

// sendMusicState sends the current player state to a single newly-connected client.
func (h *Hub) sendMusicState(c *client) {
	h.mu.RLock()
	p := h.musicPlayer
	h.mu.RUnlock()
	if p == nil {
		return
	}
	data, err := json.Marshal(p.StateMsg())
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// sendMusicQueue sends the full queue snapshot to a single newly-connected client.
func (h *Hub) sendMusicQueue(c *client) {
	h.mu.RLock()
	p := h.musicPlayer
	h.mu.RUnlock()
	if p == nil {
		return
	}
	data, err := json.Marshal(p.QueueMsg())
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// setLocalCamera updates the panel camera and broadcasts the change to all clients.
func (h *Hub) setLocalCamera(name string) {
	h.mu.Lock()
	h.localCamera = name
	h.mu.Unlock()
	h.broadcastAll(LocalCameraMsg{Type: "localCamera", Camera: name})
}

// sendG3XState sends the current G3X state to a single newly-connected client.
func (h *Hub) sendG3XState(c *client) {
	s := hardware.G3X().State()
	msg := G3XStateMsg{
		Type: "g3xState", Lat: s.Lat, Lon: s.Lon, AltFt: s.AltFt,
		Heading: s.Heading, Roll: s.Roll, Pitch: s.Pitch, Yaw: s.Yaw, SpeedKts: s.SpeedKts,
	}
	data, err := json.Marshal(msg)
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// runG3XLoop runs the G3X mock avionics loop. It broadcasts state changes as
// g3xState WS messages and feeds attitude/GPS to any Siyi gimbal managers at
// 10 Hz (attitude) and 1 Hz (GPS).
func (h *Hub) runG3XLoop(ctx context.Context) {
	g := hardware.G3X()
	g.OnChange(func(s g3x.State) {
		msg := G3XStateMsg{
			Type: "g3xState", Lat: s.Lat, Lon: s.Lon, AltFt: s.AltFt,
			Heading: s.Heading, Roll: s.Roll, Pitch: s.Pitch, Yaw: s.Yaw, SpeedKts: s.SpeedKts, OATCelsius: s.OAT,
		}
		h.broadcastAll(msg)
	})
	go g.Run(ctx)

	// Attitude injection at 10 Hz; GPS injection at 1 Hz.
	attTicker := time.NewTicker(100 * time.Millisecond)
	gpsTicker := time.NewTicker(time.Second)
	defer attTicker.Stop()
	defer gpsTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-attTicker.C:
			s := g.State()
			h.mu.RLock()
			mgrs := h.siyiManagers
			h.mu.RUnlock()
			for _, mgr := range mgrs {
				go func(m *siyi.Manager) { _ = m.SendAttitude(s) }(mgr)
			}
		case <-gpsTicker.C:
			s := g.State()
			h.mu.RLock()
			mgrs := h.siyiManagers
			h.mu.RUnlock()
			for _, mgr := range mgrs {
				go func(m *siyi.Manager) { _ = m.SendGPS(s) }(mgr)
			}
		}
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
