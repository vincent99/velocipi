// Package api exposes the transcript data over HTTP + websockets for later
// frontend integration, and accepts GPS updates from an external producer.
package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/websocket"

	"github.com/vincent99/liveatc/internal/gps"
	"github.com/vincent99/liveatc/internal/session"
	"github.com/vincent99/liveatc/internal/transcript"
)

// Server wires the transcript store + GPS store to HTTP handlers.
type Server struct {
	store  *transcript.Store
	writer *transcript.Writer // live session's log; used to apply corrections safely
	gps    *gps.Store
	sess   *session.Session
	root   string // storage root (for reading past sessions + serving audio)
	uiDir  string // built SPA directory ("" disables UI serving)
	log    *slog.Logger
	http   *http.Server
	up     websocket.Upgrader
}

// New builds the API server bound to addr. root is the storage root; writer is
// the live session's transcript writer (for corrections); uiDir is the built
// SPA directory (empty to disable UI serving).
func New(addr, root, uiDir string, store *transcript.Store, writer *transcript.Writer, gpsStore *gps.Store, sess *session.Session, log *slog.Logger) *Server {
	s := &Server{
		store:  store,
		writer: writer,
		gps:    gpsStore,
		sess:   sess,
		root:   root,
		uiDir:  uiDir,
		log:    log,
		// Internal service on a trusted network; allow any origin.
		up: websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("GET /api/session", s.handleSession)
	mux.HandleFunc("GET /api/sessions", s.handleSessions)
	mux.HandleFunc("GET /api/transcripts/session/{id}", s.handleBySession)
	mux.HandleFunc("GET /api/transcripts/recent", s.handleRecent)
	mux.HandleFunc("PUT /api/transcripts/session/{sid}/{id}/correction", s.handleCorrection)
	mux.HandleFunc("PUT /api/transcripts/session/{sid}/{id}/reviewed", s.handleReviewed)
	mux.HandleFunc("GET /api/media/{path...}", s.handleMedia)
	mux.HandleFunc("POST /api/gps", s.handlePostGPS)
	mux.HandleFunc("/ws/transcripts", s.handleWSTranscripts)
	mux.HandleFunc("/ws/gps", s.handleWSGPS)
	if uiDir != "" {
		mux.Handle("/", s.spaHandler())
	}

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

// handleSessions lists every recorded session (from disk manifests), most
// recent first, flagging the currently-running one as live.
func (s *Server) handleSessions(w http.ResponseWriter, _ *http.Request) {
	manifests, err := session.ListManifests(s.root)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	type item struct {
		session.Session
		Live bool `json:"live"`
	}
	out := make([]item, 0, len(manifests))
	seen := false
	for _, m := range manifests {
		live := m.ID == s.sess.ID
		seen = seen || live
		out = append(out, item{Session: m, Live: live})
	}
	// The current session's manifest is written at startup, so it will normally
	// be present; guard anyway in case the manifest write failed.
	if !seen {
		out = append([]item{{Session: *s.sess, Live: true}}, out...)
	}
	writeJSON(w, http.StatusOK, out)
}

// handleBySession returns all records for a session, read from the durable JSONL
// on disk so both the live session and past sessions work uniformly (and any
// corrections are included).
func (s *Server) handleBySession(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	path, err := session.FindTranscriptJSONL(s.root, id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if path == "" {
		writeJSON(w, http.StatusOK, []transcript.TransmissionRecord{})
		return
	}
	recs, err := transcript.ReadJSONL(path)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if recs == nil {
		recs = []transcript.TransmissionRecord{}
	}
	writeJSON(w, http.StatusOK, recs)
}

// handleCorrection saves a human correction onto a record. The machine
// Transcript is left intact.
func (s *Server) handleCorrection(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Correction string `json:"correction"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.updateRecord(w, r, func(rec *transcript.TransmissionRecord) {
		now := time.Now().UTC()
		rec.Correction = body.Correction
		rec.CorrectedAt = now
		// Providing a correction implies the transmission was reviewed.
		rec.Reviewed = true
		rec.ReviewedAt = now
	})
}

// handleReviewed marks (or unmarks) a record as human-reviewed and error-free.
func (s *Server) handleReviewed(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Reviewed bool `json:"reviewed"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.updateRecord(w, r, func(rec *transcript.TransmissionRecord) {
		rec.Reviewed = body.Reviewed
		if body.Reviewed {
			rec.ReviewedAt = time.Now().UTC()
		} else {
			rec.ReviewedAt = time.Time{}
		}
	})
}

// updateRecord applies mut to the record identified by the {sid}/{id} path
// values and persists it. The live session is routed through the Writer (so it
// can't race the appender); past sessions are rewritten directly. The updated
// record is broadcast to live viewers.
func (s *Server) updateRecord(w http.ResponseWriter, r *http.Request, mut func(*transcript.TransmissionRecord)) {
	sid := r.PathValue("sid")
	id := r.PathValue("id")

	var (
		rec transcript.TransmissionRecord
		ok  bool
		err error
	)
	if sid == s.sess.ID && s.writer != nil {
		rec, ok, err = s.writer.UpdateRecord(id, mut)
	} else {
		path, ferr := session.FindTranscriptJSONL(s.root, sid)
		if ferr != nil {
			http.Error(w, ferr.Error(), http.StatusInternalServerError)
			return
		}
		if path == "" {
			http.Error(w, "session not found", http.StatusNotFound)
			return
		}
		rec, ok, err = transcript.UpdateRecordFile(path, id, mut)
	}
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if !ok {
		http.Error(w, "record not found", http.StatusNotFound)
		return
	}
	s.store.Update(rec) // reflect in the cache + push to live viewers
	writeJSON(w, http.StatusOK, rec)
}

// handleMedia serves a file (e.g. a segment WAV) from under the storage root.
// The path is cleaned and confined to the root to prevent traversal.
// http.ServeFile handles Range requests, so <audio> seeking works.
func (s *Server) handleMedia(w http.ResponseWriter, r *http.Request) {
	rel := r.PathValue("path")
	clean := filepath.Clean("/" + rel) // leading slash neutralises ".." escapes
	full := filepath.Join(s.root, clean)
	rootAbs, _ := filepath.Abs(s.root)
	fullAbs, _ := filepath.Abs(full)
	if fullAbs != rootAbs && !strings.HasPrefix(fullAbs, rootAbs+string(os.PathSeparator)) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	http.ServeFile(w, r, full)
}

// spaHandler serves the built Vue SPA from uiDir, falling back to index.html for
// client-side routes (paths that don't map to a real file). API and websocket
// routes are registered with more specific patterns, so they take precedence.
func (s *Server) spaHandler() http.Handler {
	fileSrv := http.FileServer(http.Dir(s.uiDir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := filepath.Join(s.uiDir, filepath.Clean(r.URL.Path))
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			fileSrv.ServeHTTP(w, r)
			return
		}
		http.ServeFile(w, r, filepath.Join(s.uiDir, "index.html"))
	})
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
