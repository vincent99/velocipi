// Package api exposes the transcript data over HTTP + websockets for later
// frontend integration, and accepts GPS updates from an external producer.
package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/gorilla/websocket"

	"github.com/vincent99/liveatc/internal/gps"
	"github.com/vincent99/liveatc/internal/session"
	"github.com/vincent99/liveatc/internal/transcript"
)

// Server wires the transcript store + GPS store to HTTP handlers.
type Server struct {
	store *transcript.Store
	gps   *gps.Store
	sess  *session.Session
	log   *slog.Logger
	http  *http.Server
	up    websocket.Upgrader
}

// New builds the API server bound to addr.
func New(addr string, store *transcript.Store, gpsStore *gps.Store, sess *session.Session, log *slog.Logger) *Server {
	s := &Server{
		store: store,
		gps:   gpsStore,
		sess:  sess,
		log:   log,
		// Internal service on a trusted network; allow any origin.
		up: websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("GET /api/session", s.handleSession)
	mux.HandleFunc("GET /api/transcripts/session/{id}", s.handleBySession)
	mux.HandleFunc("GET /api/transcripts/recent", s.handleRecent)
	mux.HandleFunc("POST /api/gps", s.handlePostGPS)
	mux.HandleFunc("/ws/transcripts", s.handleWSTranscripts)
	mux.HandleFunc("/ws/gps", s.handleWSGPS)

	s.http = &http.Server{Addr: addr, Handler: mux}
	return s
}

// Start begins serving; it returns when the listener stops.
func (s *Server) Start() error {
	s.log.Info("API listening", "addr", s.http.Addr)
	if err := s.http.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

// Shutdown gracefully stops the HTTP server.
func (s *Server) Shutdown(ctx context.Context) error { return s.http.Shutdown(ctx) }

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "session": s.sess.ID})
}

func (s *Server) handleSession(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, s.sess)
}

func (s *Server) handleBySession(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	writeJSON(w, http.StatusOK, s.store.BySession(id))
}

func (s *Server) handleRecent(w http.ResponseWriter, r *http.Request) {
	n := 20
	if v := r.URL.Query().Get("n"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			n = parsed
		}
	}
	writeJSON(w, http.StatusOK, s.store.Recent(n))
}

// handlePostGPS accepts a GPSFix as JSON and updates the current position.
func (s *Server) handlePostGPS(w http.ResponseWriter, r *http.Request) {
	var fix gps.GPSFix
	if err := json.NewDecoder(r.Body).Decode(&fix); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.gps.Update(fix)
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

// handleWSTranscripts streams each new TransmissionRecord as JSON. On connect it
// first backfills the recent cache so a fresh client isn't blank.
func (s *Server) handleWSTranscripts(w http.ResponseWriter, r *http.Request) {
	conn, err := s.up.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer conn.Close()

	ch, unsub := s.store.Subscribe()
	defer unsub()

	for _, rec := range s.store.Recent(20) {
		if err := conn.WriteJSON(rec); err != nil {
			return
		}
	}

	// Drain client-side control frames so close/ping are handled.
	go drain(conn)

	for rec := range ch {
		_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
		if err := conn.WriteJSON(rec); err != nil {
			return
		}
	}
}

// handleWSGPS accepts a stream of GPSFix JSON messages and updates position.
func (s *Server) handleWSGPS(w http.ResponseWriter, r *http.Request) {
	conn, err := s.up.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer conn.Close()

	for {
		var fix gps.GPSFix
		if err := conn.ReadJSON(&fix); err != nil {
			return
		}
		s.gps.Update(fix)
	}
}

func drain(conn *websocket.Conn) {
	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			return
		}
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
