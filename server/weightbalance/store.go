package weightbalance

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

// store is the JSON-file-backed persistence layer, rooted at cfg.Storage.WeightBalance.
// A single mutex guards all reads/writes -- this data is edited rarely
// (config screen, or one save per flight) so simplicity wins over fine-grained locking.
type store struct {
	mu  sync.Mutex
	dir string
}

func newStore(dir string) *store {
	return &store{dir: dir}
}

func (s *store) peopleFile() string  { return filepath.Join(s.dir, "people.json") }
func (s *store) layoutsFile() string { return filepath.Join(s.dir, "layouts.json") }
func (s *store) savedDir() string    { return filepath.Join(s.dir, "saved") }

func (s *store) loadPeople() ([]Person, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	people := []Person{}
	if err := readJSON(s.peopleFile(), &people); err != nil {
		return nil, err
	}
	return people, nil
}

func (s *store) savePeople(people []Person) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return writeJSON(s.dir, s.peopleFile(), people)
}

func (s *store) loadLayouts() ([]Layout, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	layouts := []Layout{}
	if err := readJSON(s.layoutsFile(), &layouts); err != nil {
		return nil, err
	}
	return layouts, nil
}

func (s *store) saveLayouts(layouts []Layout) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	// Never persist the computed Hash field -- it's derived, not stored.
	for i := range layouts {
		layouts[i].Hash = ""
	}
	return writeJSON(s.dir, s.layoutsFile(), layouts)
}

// saveSnapshot writes data (with SavedAt stamped to now) and svg to a
// timestamped pair of files under saved/, returning the stamp used.
func (s *store) saveSnapshot(data SavedWB, svg string) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	stamp := time.Now().UTC().Format("20060102-150405.000")
	data.SavedAt = time.Now().UTC().Format(time.RFC3339)

	dir := s.savedDir()
	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", err
	}
	if err := writeJSON(s.dir, filepath.Join(dir, stamp+".json"), data); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(dir, stamp+".svg"), []byte(svg), 0644); err != nil {
		return "", err
	}
	return stamp, nil
}

// loadLatestSnapshot returns the most recently saved SavedWB, or ok=false if
// none exist yet. Filenames sort chronologically (fixed-width timestamp), so
// "latest" is just the last name in a sorted directory listing.
func (s *store) loadLatestSnapshot() (SavedWB, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entries, err := os.ReadDir(s.savedDir())
	if os.IsNotExist(err) {
		return SavedWB{}, false, nil
	}
	if err != nil {
		return SavedWB{}, false, err
	}

	var names []string
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".json" {
			names = append(names, e.Name())
		}
	}
	if len(names) == 0 {
		return SavedWB{}, false, nil
	}
	sort.Strings(names)
	latest := names[len(names)-1]

	var data SavedWB
	if err := readJSON(filepath.Join(s.savedDir(), latest), &data); err != nil {
		return SavedWB{}, false, err
	}
	return data, true, nil
}

// readJSON decodes path into v. A missing file leaves v at its zero value
// (the caller pre-seeds v with an empty slice/map so "not configured yet"
// reads back as [] / {} rather than null).
func readJSON(path string, v any) error {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	return json.Unmarshal(data, v)
}

// writeJSON marshals v and writes it to path, creating dir if needed.
func writeJSON(dir, path string, v any) error {
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// hashLayout returns a SHA-256 hex digest of layout's canonical JSON
// representation (with Hash itself excluded), used so the client can tell
// whether a layout has changed since a given saved snapshot was made.
// json.Marshal of a struct with fixed field order is stable, so the same
// layout content always hashes the same.
func hashLayout(l Layout) string {
	l.Hash = ""
	data, _ := json.Marshal(l)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
