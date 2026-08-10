// Package gps holds the current aircraft position, updated externally (today
// via the websocket/HTTP API, eventually from the Garmin Axis integration) and
// snapshotted at transmission boundaries.
package gps

import (
	"sync"
	"time"
)

// GPSFix is a single position sample. Field shape matches the eventual Garmin
// Axis feed so the producer can be swapped without touching consumers.
type GPSFix struct {
	Time          time.Time `json:"time"`
	Lat           float64   `json:"lat"`
	Lon           float64   `json:"lon"`
	AltFt         float64   `json:"alt_ft"`
	HeadingDeg    float64   `json:"heading_deg"`
	GroundspeedKt float64   `json:"groundspeed_kt"`
	FixQuality    int       `json:"fix_quality"`
	Valid         bool      `json:"valid"`
}

// Store is a concurrency-safe holder for the latest GPSFix.
type Store struct {
	mu   sync.RWMutex
	last GPSFix
}

// NewStore returns an empty store whose current fix is invalid.
func NewStore() *Store { return &Store{} }

// Update replaces the current fix. If the caller left Time zero, we stamp it now
// so downstream consumers always have something monotonic-ish to work with.
func (s *Store) Update(fix GPSFix) {
	if fix.Time.IsZero() {
		fix.Time = time.Now().UTC()
	}
	s.mu.Lock()
	s.last = fix
	s.mu.Unlock()
}

// Snapshot returns a copy of the current fix. If no valid fix has ever been set,
// the returned value has Valid=false (callers store null-ish values + the flag
// and must not block on GPS).
func (s *Store) Snapshot() GPSFix {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.last
}
