package session

import (
	"os"
	"path/filepath"
	"strings"
)

// Delete removes every file belonging to a session: the given audio segments
// (relative paths from the records), the transcript JSONL + text log, and the
// session manifest. Any date directories left empty afterward are removed too.
// Missing files are ignored; the first real error (if any) is returned.
//
// The current layout groups audio and transcripts by date rather than by a
// single per-session folder, so "delete the folder" means pruning the now-empty
// audio/<date> and transcripts/<date> directories.
func Delete(root, id string, audioFiles []string) error {
	rootAbs, _ := filepath.Abs(root)
	var firstErr error
	dirs := map[string]struct{}{}

	rm := func(p string) {
		if err := os.Remove(p); err != nil && !os.IsNotExist(err) && firstErr == nil {
			firstErr = err
		}
	}
	// under confines p to the storage root (defense against a doctored path).
	under := func(p string) bool {
		pa, _ := filepath.Abs(p)
		return pa == rootAbs || strings.HasPrefix(pa, rootAbs+string(os.PathSeparator))
	}

	for _, rel := range audioFiles {
		if rel == "" {
			continue
		}
		p := filepath.Join(root, filepath.Clean("/"+rel))
		if !under(p) {
			continue
		}
		rm(p)
		dirs[filepath.Dir(p)] = struct{}{}
	}

	if jsonl, _ := FindTranscriptJSONL(root, id); jsonl != "" {
		rm(jsonl)
		rm(strings.TrimSuffix(jsonl, ".jsonl") + ".txt")
		dirs[filepath.Dir(jsonl)] = struct{}{}
	}

	rm(filepath.Join(root, "sessions", id+".json"))

	// Best-effort: remove any now-empty date directories (os.Remove fails, and is
	// ignored, if the dir still holds another session's files).
	for d := range dirs {
		_ = os.Remove(d)
	}
	return firstErr
}
