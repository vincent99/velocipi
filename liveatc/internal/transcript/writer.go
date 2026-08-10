package transcript

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/vincent99/liveatc/internal/gps"
)

// Writer persists records to two parallel outputs for a single session:
//   - an append-only JSONL log (one record per line; the durable source of truth)
//   - a human-readable text log for quick review
type Writer struct {
	mu    sync.Mutex
	jsonl *os.File
	text  *os.File
}

// NewWriter opens (creating parent dirs) the JSONL and text logs at the given
// paths in append mode.
func NewWriter(jsonlPath, textPath string) (*Writer, error) {
	if err := os.MkdirAll(filepath.Dir(jsonlPath), 0o755); err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(textPath), 0o755); err != nil {
		return nil, err
	}
	jf, err := os.OpenFile(jsonlPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return nil, err
	}
	tf, err := os.OpenFile(textPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		_ = jf.Close()
		return nil, err
	}
	return &Writer{jsonl: jf, text: tf}, nil
}

// Append writes the record to both logs and flushes them.
func (w *Writer) Append(r TransmissionRecord) error {
	line, err := json.Marshal(r)
	if err != nil {
		return err
	}

	w.mu.Lock()
	defer w.mu.Unlock()

	if _, err := w.jsonl.Write(append(line, '\n')); err != nil {
		return err
	}
	if _, err := w.text.WriteString(formatText(r) + "\n"); err != nil {
		return err
	}
	// Flush to disk so a hard power cut loses at most the in-flight record.
	if err := w.jsonl.Sync(); err != nil {
		return err
	}
	return w.text.Sync()
}

// Close closes both files.
func (w *Writer) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	e1 := w.jsonl.Close()
	e2 := w.text.Close()
	if e1 != nil {
		return e1
	}
	return e2
}

// formatText renders one line like:
//
//	[14:30:22Z] [RX] [N43.21 W76.54 | 8500ft | 135kt] "Cessna 12345, cleared ..."
func formatText(r TransmissionRecord) string {
	ts := r.StartTime.UTC().Format("15:04:05") + "Z"
	dir := strings.ToUpper(r.Direction)
	if dir == "" {
		dir = "UNKNOWN"
	}
	return fmt.Sprintf("[%s] [%s] [%s] %q", ts, dir, formatGPS(r.GPSStart), r.Transcript)
}

func formatGPS(f gps.GPSFix) string {
	if !f.Valid {
		return "no gps"
	}
	return fmt.Sprintf("%s %s | %dft | %dkt",
		latStr(f.Lat), lonStr(f.Lon),
		int(math.Round(f.AltFt)), int(math.Round(f.GroundspeedKt)))
}

func latStr(lat float64) string {
	h := "N"
	if lat < 0 {
		h, lat = "S", -lat
	}
	return fmt.Sprintf("%s%.2f", h, lat)
}

func lonStr(lon float64) string {
	h := "E"
	if lon < 0 {
		h, lon = "W", -lon
	}
	return fmt.Sprintf("%s%.2f", h, lon)
}
