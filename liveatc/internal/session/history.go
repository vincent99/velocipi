package session

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

// ListManifests reads every session manifest under root/sessions and returns
// them most-recent first. A missing sessions dir yields an empty slice.
func ListManifests(root string) ([]Session, error) {
	dir := filepath.Join(root, "sessions")
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var out []Session
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		var s Session
		if err := json.Unmarshal(data, &s); err != nil {
			continue
		}
		out = append(out, s)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].StartTime.After(out[j].StartTime) })
	return out, nil
}

// FindTranscriptJSONL locates the transcript JSONL for a session id by globbing
// under root/transcripts (the date subdir isn't known from the id alone).
// Returns "" (no error) if none is found.
func FindTranscriptJSONL(root, id string) (string, error) {
	pattern := filepath.Join(root, "transcripts", "*", "transcript_"+id+".jsonl")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return "", err
	}
	if len(matches) == 0 {
		return "", nil
	}
	return matches[0], nil
}
