// Package session models one recording session (a flight): its ID, on-disk
// layout under the storage root, and the manifest written at startup.
package session

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// idLayout is the session-id / filesystem-safe timestamp form: 2006-01-02T15-04-05Z.
const idLayout = "2006-01-02T15-04-05Z"

// Session holds identity + paths for the current run.
type Session struct {
	ID        string    `json:"session_id"`
	StartTime time.Time `json:"start_time"`
	Aircraft  string    `json:"aircraft"`
	Device    string    `json:"audio_device"`
	Model     string    `json:"model"`
	Root      string    `json:"storage_root"`
}

// New builds a session whose ID encodes its UTC start time.
func New(root, aircraft, device, model string) *Session {
	now := time.Now().UTC()
	return &Session{
		ID:        now.Format(idLayout),
		StartTime: now,
		Aircraft:  aircraft,
		Device:    device,
		Model:     model,
		Root:      root,
	}
}

// startDate is the session's start date (yyyy-mm-dd), used for stable
// transcript paths across the whole session.
func (s *Session) startDate() string { return s.StartTime.UTC().Format("2006-01-02") }

// AudioPath returns the WAV path for a transmission at time t. id disambiguates
// segments so sub-second (and --fast replay, where wall-clock time barely
// advances) transmissions never collide. callsignHint may be empty (filled in
// post-STT); it is sanitized for the filesystem.
func (s *Session) AudioPath(t time.Time, id, callsignHint string) string {
	date := t.UTC().Format("2006-01-02")
	// Millisecond precision keeps names readable and ordered; the id suffix
	// guarantees uniqueness even when timestamps coincide.
	stamp := t.UTC().Format("2006-01-02_15-04-05.000")
	name := stamp
	if h := sanitize(callsignHint); h != "" {
		name += "_" + h
	}
	if short := shortID(id); short != "" {
		name += "_" + short
	}
	return filepath.Join(s.Root, "audio", date, name+".wav")
}

// shortID returns the first hyphen-delimited group of a UUID (8 hex chars),
// enough to disambiguate segments within a session.
func shortID(id string) string {
	if i := strings.IndexByte(id, '-'); i > 0 {
		return id[:i]
	}
	if len(id) > 8 {
		return id[:8]
	}
	return id
}

// JSONLPath returns the rolling transcript JSONL path for this session.
func (s *Session) JSONLPath() string {
	return filepath.Join(s.Root, "transcripts", s.startDate(), "transcript_"+s.ID+".jsonl")
}

// TextPath returns the human-readable transcript path for this session.
func (s *Session) TextPath() string {
	return filepath.Join(s.Root, "transcripts", s.startDate(), "transcript_"+s.ID+".txt")
}

// ManifestPath returns the session manifest JSON path.
func (s *Session) ManifestPath() string {
	return filepath.Join(s.Root, "sessions", s.ID+".json")
}

// Rel makes an absolute path relative to the storage root (records store
// relative audio paths so the tree is portable).
func (s *Session) Rel(path string) string {
	if rel, err := filepath.Rel(s.Root, path); err == nil {
		return rel
	}
	return path
}

// WriteManifest persists the session manifest.
func (s *Session) WriteManifest() error {
	if err := os.MkdirAll(filepath.Dir(s.ManifestPath()), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.ManifestPath(), data, 0o644)
}

// sanitize keeps only characters safe in a filename.
func sanitize(s string) string {
	out := make([]rune, 0, len(s))
	for _, r := range s {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-', r == '_':
			out = append(out, r)
		}
	}
	return string(out)
}
