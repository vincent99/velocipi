package dvr

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// RecordingFile describes one archived MP4 segment.
type RecordingFile struct {
	Camera    string `json:"camera"`    // original camera name (from filename)
	Session   string `json:"session"`   // session directory name, e.g. "2026-02-23" or "2026-02-23-01"
	Date      string `json:"date"`      // "2026-02-22" (from filename, always present)
	StartTime string `json:"startTime"` // "15-04-05"
	Filename  string `json:"filename"`  // basename without extension, e.g. "2026-02-22_15-04-05_Left"
	HasThumb  bool   `json:"hasThumb"`  // _thumb.jpg exists
	HasFull   bool   `json:"hasFull"`   // _full.jpg exists
}

// parseRecordingName parses a filename of the form
// "{yyyy-mm-dd_hh-mm-ss}_{cam}.mp4" into its components.
// Returns ("", "", "", false) if the name doesn't match.
func parseRecordingName(name string) (date, startTime, cam string, ok bool) {
	if !strings.HasSuffix(name, ".mp4") {
		return
	}
	base := strings.TrimSuffix(name, ".mp4")
	// Expected: "2006-01-02_15-04-05_CamName"
	// The date+time portion is always 19 chars: "2006-01-02_15-04-05"
	if len(base) < 21 || base[10] != '_' || base[19] != '_' {
		return
	}
	date = base[:10]
	startTime = base[11:19]
	cam = base[20:]
	ok = true
	return
}

// ListRecordings returns all MP4 segments found under recordingsDir,
// sorted by session descending then start time ascending.
func (m *Manager) ListRecordings() ([]RecordingFile, error) {
	root := m.recordingsDir
	entries, err := os.ReadDir(root)
	if os.IsNotExist(err) {
		return []RecordingFile{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("list recordings: %w", err)
	}

	var out []RecordingFile
	for _, sessionEntry := range entries {
		if !sessionEntry.IsDir() {
			continue
		}
		session := sessionEntry.Name()
		sessionDir := filepath.Join(root, session)
		files, err := os.ReadDir(sessionDir)
		if err != nil {
			continue
		}
		for _, f := range files {
			if f.IsDir() || !strings.HasSuffix(f.Name(), ".mp4") {
				continue
			}
			date, startTime, cam, ok := parseRecordingName(f.Name())
			if !ok {
				continue
			}
			base := filepath.Join(sessionDir, strings.TrimSuffix(f.Name(), ".mp4"))
			_, thumbErr := os.Stat(base + "_thumb.jpg")
			_, fullErr := os.Stat(base + "_full.jpg")
			out = append(out, RecordingFile{
				Camera:    unsanitizeName(cam),
				Session:   session,
				Date:      date,
				StartTime: startTime,
				Filename:  strings.TrimSuffix(f.Name(), ".mp4"),
				HasThumb:  thumbErr == nil,
				HasFull:   fullErr == nil,
			})
		}
	}

	sort.Slice(out, func(i, j int) bool {
		if out[i].Session != out[j].Session {
			return out[i].Session > out[j].Session // session descending
		}
		return out[i].StartTime < out[j].StartTime // time ascending
	})
	return out, nil
}

// DeleteRecording deletes a single MP4 segment and its associated JPEGs.
// session is the session directory name; filename is the basename without extension.
func (m *Manager) DeleteRecording(session, filename string) error {
	if strings.ContainsAny(session, "/\\") || strings.ContainsAny(filename, "/\\") {
		return fmt.Errorf("invalid session or filename")
	}
	dir := filepath.Join(m.recordingsDir, session)
	base := filepath.Join(dir, filename)
	for _, ext := range []string{".mp4", "_thumb.jpg", "_full.jpg"} {
		path := base + ext
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("delete %s: %w", path, err)
		}
	}
	return nil
}

// DeleteHour deletes all recordings (and associated JPEGs) in a given session
// directory whose time component starts with the given hour (e.g. "15").
func (m *Manager) DeleteHour(session, hour string) error {
	dir := filepath.Join(m.recordingsDir, session)
	entries, err := os.ReadDir(dir)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("delete hour: %w", err)
	}
	// Files match: {date}_{hour}-??-??_{cam}.* (mp4, _thumb.jpg, _full.jpg)
	// The date portion of the filename is the first 10 chars; hour starts at char 11.
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		// Filename format: yyyy-mm-dd_hh-mm-ss_cam.*
		// Hour is at position 11..12.
		name := e.Name()
		if len(name) > 13 && name[11:13] == hour {
			path := filepath.Join(dir, name)
			if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
				return fmt.Errorf("delete %s: %w", path, err)
			}
		}
	}
	return nil
}

// DeleteSession removes the entire session directory.
func (m *Manager) DeleteSession(session string) error {
	if strings.ContainsAny(session, "/\\") {
		return fmt.Errorf("invalid session name")
	}
	dir := filepath.Join(m.recordingsDir, session)
	if err := os.RemoveAll(dir); err != nil {
		return fmt.Errorf("delete session %s: %w", session, err)
	}
	return nil
}

// unsanitizeName reverses the underscore-for-space substitution done by
// sanitizeName so that camera names are restored for display. Other
// substitutions (/ → -, etc.) are lossy and cannot be reversed; this is
// best-effort for the common case of spaces in names.
func unsanitizeName(s string) string {
	return strings.ReplaceAll(s, "_", " ")
}
