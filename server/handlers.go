package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/gorilla/websocket"
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

// corsMiddleware adds CORS headers to all responses.
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
	go hub.sendCameraStatuses(c)

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
		case "navigate":
			var nm inboundNavigateMsg
			if err := json.Unmarshal(data, &nm); err == nil {
				go hub.navigate(nm.Path)
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
