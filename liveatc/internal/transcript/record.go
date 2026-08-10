// Package transcript defines the transmission record model and its persistence
// (rolling JSONL + human-readable text log) plus an in-memory store the API
// serves from.
package transcript

import (
	"time"

	"github.com/vincent99/liveatc/internal/gps"
)

// WordToken is a single word with whisper's timing + confidence.
type WordToken struct {
	Word       string  `json:"word"`
	StartMs    int     `json:"start_ms"`
	EndMs      int     `json:"end_ms"`
	Confidence float32 `json:"confidence"`
}

// TransmissionRecord is the fully-transcribed result for one transmission.
type TransmissionRecord struct {
	ID         string      `json:"id"`         // UUID
	SessionID  string      `json:"session_id"` // groups records per flight/session
	StartTime  time.Time   `json:"start_time"` // UTC
	EndTime    time.Time   `json:"end_time"`   // UTC
	DurationMs int         `json:"duration_ms"`
	AudioFile  string      `json:"audio_file"` // path relative to storage root
	Transcript string      `json:"transcript"`
	Words      []WordToken `json:"words"`
	GPSStart   gps.GPSFix  `json:"gps_start"`
	GPSEnd     gps.GPSFix  `json:"gps_end"`
	Confidence float32     `json:"confidence"` // mean whisper token confidence
	Direction  string      `json:"direction"`  // "rx" | "tx" | "unknown"
	ModelUsed  string      `json:"model_used"`
}
