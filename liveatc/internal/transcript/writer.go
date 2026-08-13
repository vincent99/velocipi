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
	mu        sync.Mutex
	jsonl     *os.File
	text      *os.File
	jsonlPath string
	textPath  string
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
	return &Writer{jsonl: jf, text: tf, jsonlPath: jsonlPath, textPath: textPath}, nil
}

// DeleteRecord removes the record with id from this session's JSONL and
// regenerates the text log, holding the appender's lock and reopening both
// append handles onto the rewritten files so it can't race concurrent Appends.
// Returns the removed record and whether it was found.
func (w *Writer) DeleteRecord(id string) (TransmissionRecord, bool, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	recs, err := ReadJSONL(w.jsonlPath)
	if err != nil {
		return TransmissionRecord{}, false, err
	}
	remaining, removed, ok := removeByID(recs, id)
	if !ok {
		return TransmissionRecord{}, false, nil
	}

	// Rewrite the JSONL and reopen the append handle onto the new file.
	if err := w.jsonl.Close(); err != nil {
		return removed, false, err
	}
	jErr := writeJSONLAtomic(w.jsonlPath, remaining)
	jf, err := os.OpenFile(w.jsonlPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return removed, false, err
	}
	w.jsonl = jf
	if jErr != nil {
		return removed, false, jErr
	}

	// Regenerate the text log and reopen its append handle.
	if err := w.text.Close(); err != nil {
		return removed, false, err
	}
	tErr := writeTextAtomic(w.textPath, remaining)
	tf, err := os.OpenFile(w.textPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return removed, false, err
	}
	w.text = tf
	if tErr != nil {
		return removed, false, tErr
	}
	return removed, true, nil
}

// Rewrite applies fn to this session's full record list and rewrites both the
// JSONL and the text log atomically (reopening the append handles), under the
// appender's lock. Used by multi-record edits like merge.
func (w *Writer) Rewrite(fn func([]TransmissionRecord) []TransmissionRecord) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	recs, err := ReadJSONL(w.jsonlPath)
	if err != nil {
		return err
	}
	recs = fn(recs)

	if err := w.jsonl.Close(); err != nil {
		return err
	}
	jErr := writeJSONLAtomic(w.jsonlPath, recs)
	jf, err := os.OpenFile(w.jsonlPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	w.jsonl = jf
	if jErr != nil {
		return jErr
	}

	if err := w.text.Close(); err != nil {
		return err
	}
	tErr := writeTextAtomic(w.textPath, recs)
	tf, err := os.OpenFile(w.textPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	w.text = tf
	return tErr
}

// UpdateRecord applies mut to the record with id in this session's JSONL and
// returns the updated record. It rewrites the file atomically while holding the
// same lock the appender uses, then reopens the append handle onto the new file
// -- so it can't interleave with, or lose, concurrent Appends.
func (w *Writer) UpdateRecord(id string, mut func(*TransmissionRecord)) (TransmissionRecord, bool, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	recs, err := ReadJSONL(w.jsonlPath)
	if err != nil {
		return TransmissionRecord{}, false, err
	}
	rec, ok := applyTo(recs, id, mut)
	if !ok {
		return TransmissionRecord{}, false, nil
	}

	// Close our append handle before the rename so subsequent Appends don't keep
	// writing to the now-unlinked old inode; reopen it onto the rewritten file.
	if err := w.jsonl.Close(); err != nil {
		return TransmissionRecord{}, false, err
	}
	writeErr := writeJSONLAtomic(w.jsonlPath, recs)
	jf, openErr := os.OpenFile(w.jsonlPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if openErr != nil {
		return TransmissionRecord{}, false, openErr
	}
	w.jsonl = jf
	if writeErr != nil {
		return TransmissionRecord{}, false, writeErr
	}
	return rec, true, nil
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
	ch := ""
	if r.Channel != "" {
		ch = " [" + r.Channel + "]"
	}
	return fmt.Sprintf("[%s]%s [%s] [%s] %q", ts, ch, dir, formatGPS(r.GPSStart), r.Transcript)
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
