package main

import (
	"context"
	"encoding/json"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/oled"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

var hub *Hub

// spaHandler serves static files from dir, falling back to index.html for any
// path that doesn't match a real file (required for Vue Router history mode).
func spaHandler(dir string) http.Handler {
	fs := http.FileServer(http.Dir(dir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := filepath.Join(dir, filepath.Clean("/"+r.URL.Path))
		if _, err := os.Stat(path); os.IsNotExist(err) {
			http.ServeFile(w, r, filepath.Join(dir, "index.html"))
			return
		}
		fs.ServeHTTP(w, r)
	})
}

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
	go hub.sendLEDState(c)

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
		case "led":
			var lm inboundLEDMsg
			if err := json.Unmarshal(data, &lm); err == nil {
				go hub.handleLEDMsg(lm.State, lm.Rate)
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

	// Write pump: drains c.send and writes binary PNG frames to the client.
	go func() {
		defer hub.unregisterScreen(c)
		defer conn.Close()
		for msg := range c.send {
			if err := conn.WriteMessage(websocket.BinaryMessage, msg); err != nil {
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
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	// Start LED blinking immediately as a startup indicator.
	// It will be turned off once the first frame blits to the OLED.
	if e := hardware.Expander(); e != nil {
		hardware.LED().Blink(e, 250*time.Millisecond)
	}

	// Initialise the OLED display. Non-fatal if the hardware isn't present.
	var display *oled.OLED
	if o, err := oled.New(oled.Config{
		SPIPort:  cfg.OLED.SPIPort,
		SPISpeed: cfg.OLEDSPIFreq,
		GPIOChip: cfg.OLED.GPIOChip,
		DCPin:    cfg.OLED.DCPin,
		ResetPin: cfg.OLED.ResetPin,
		Flip:     cfg.OLED.Flip,
	}, cfg.OLED.Width, cfg.OLED.Height); err != nil {
		log.Println("oled: init error (continuing without display):", err)
	} else {
		display = o
	}

	// Initialize hub immediately so wsHandler is never called with a nil hub.
	// browserCtx is set after the browser starts up below.
	hub = newHub(nil, cfg, display)

	// Start HTTP server first so the browser can reach /app when it navigates.
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", wsHandler)
	mux.HandleFunc("/screen", screenHandler)
	mux.HandleFunc("/config", func(w http.ResponseWriter, r *http.Request) {
		data, err := json.Marshal(cfg.UI)
		if err != nil {
			http.Error(w, "config marshal error", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(data)
	})
	mux.Handle("/", spaHandler("ui/dist"))
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

	// Init the headless browser (process starts but no page loaded yet).
	browserCtx, cancelBrowser := initBrowser(ctx)
	defer cancelBrowser()

	hub.mu.Lock()
	hub.browserCtx = browserCtx
	hub.mu.Unlock()

	// Navigate to the app now that the HTTP server is listening.
	if err := navigateTo(browserCtx, cfg.AppURL); err != nil {
		log.Println("browser: initial navigate error:", err)
	} else {
		log.Println("browser: app loaded")
	}

	// Start background loops.
	go hub.runAirSensorLoop(ctx)
	go hub.runLightSensorLoop(ctx)
	go hub.runTpmsLoop(ctx)
	go hub.runInputLoop(ctx)
	go hub.runScreencastLoop(ctx)

	// Block until signal.
	<-ctx.Done()
	log.Println("shutting down...")

	// Turn off LED and clear OLED on exit.
	if e := hardware.Expander(); e != nil {
		hardware.LED().Off(e)
	}
	if display != nil {
		display.Close()
	}
}
