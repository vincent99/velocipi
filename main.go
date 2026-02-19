package main

import (
	"context"
	"encoding/json"
	"log"
	"net"
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/vincent99/velocipi-go/config"
	"github.com/vincent99/velocipi-go/hardware/oled"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

var hub *Hub

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("websocket upgrade error:", err)
		return
	}

	c := &client{conn: conn, send: make(chan []byte, 2)}
	hub.register(c)
	log.Println("websocket client connected:", r.RemoteAddr)
	go hub.sendReading(c)
	go hub.sendLux(c)
	go hub.sendTpms(c)

	// Write pump: drains c.send and writes to the WebSocket connection.
	go func() {
		defer hub.unregister(c)
		defer conn.Close()
		for msg := range c.send {
			if err := conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				log.Println("websocket write error:", err)
				return
			}
		}
	}()

	// Read pump: handles incoming messages and detects disconnect.
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			log.Println("websocket client disconnected:", r.RemoteAddr)
			hub.unregister(c)
			return
		}
		var msg inboundMsg
		if err := json.Unmarshal(data, &msg); err != nil {
			continue
		}
		switch msg.Type {
		case "reload":
			go hub.reload()
		case "key":
			var km inboundKeyMsg
			if err := json.Unmarshal(data, &km); err == nil {
				go hub.handleKeyMsg(km.EventType, km.Key)
			}
		}
	}
}

func screenHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("screen websocket upgrade error:", err)
		return
	}

	c := &client{conn: conn, send: make(chan []byte, 2)}
	hub.registerScreen(c)
	log.Println("screen client connected:", r.RemoteAddr)

	// Write pump: drains c.send and writes frames to the client.
	go func() {
		defer hub.unregisterScreen(c)
		defer conn.Close()
		for msg := range c.send {
			if err := conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				log.Println("screen write error:", err)
				return
			}
		}
	}()

	// Read pump: only used to detect disconnect; screen socket is send-only.
	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			log.Println("screen client disconnected:", r.RemoteAddr)
			hub.unregisterScreen(c)
			return
		}
	}
}

func main() {
	cfg := config.Load()
	ctx := context.Background()

	// Initialise the OLED display. Non-fatal if the hardware isn't present.
	var display *oled.OLED
	if o, err := oled.New(oled.Config{
		SPIPort:  cfg.OLEDSPIPort,
		SPISpeed: cfg.OLEDSPISpeed,
		GPIOChip: cfg.OLEDGPIOChip,
		DCPin:    cfg.OLEDDCPin,
		ResetPin: cfg.OLEDResetPin,
		Flip:     cfg.OLEDFlip,
	}, cfg.OLEDWidth, cfg.OLEDHeight); err != nil {
		log.Println("oled: init error (continuing without display):", err)
	} else {
		display = o
		defer display.Close()
	}

	// Initialize hub immediately so wsHandler is never called with a nil hub.
	// browserCtx is set after the browser starts up below.
	hub = newHub(nil, cfg, display)

	// Start HTTP server first so the browser can reach /app when it navigates.
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", wsHandler)
	mux.HandleFunc("/screen", screenHandler)
	mux.Handle("/", http.FileServer(http.Dir("frontend")))
	handler := corsMiddleware(mux)

	addr := cfg.Addr
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatal(err)
	}
	log.Println("listening on", addr)

	go func() {
		if err := http.Serve(ln, handler); err != nil {
			log.Fatal(err)
		}
	}()

	// Init the global browser instance (navigates to /app fire-and-forget).
	browserCtx, cancelBrowser := initBrowser(ctx)
	defer cancelBrowser()

	hub.mu.Lock()
	hub.browserCtx = browserCtx
	hub.mu.Unlock()

	// Start the air sensor, light sensor, TPMS, and input loops.
	go hub.runAirSensorLoop(ctx)
	go hub.runLightSensorLoop(ctx)
	go hub.runTpmsLoop(ctx)
	go hub.runInputLoop(ctx)

	// Run the screenshot+ping loop on the main goroutine.
	hub.runScreenshotLoop(ctx)
}
