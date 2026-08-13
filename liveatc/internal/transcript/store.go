package transcript

import "sync"

// Store keeps transmission records in memory for the API to serve and fans each
// new record out to live websocket subscribers. It is safe for concurrent use.
//
// This is deliberately bounded/simple: the durable record of truth is the JSONL
// on disk; the store is a hot cache for the current process's lifetime.
type Store struct {
	mu      sync.RWMutex
	records []TransmissionRecord
	max     int
	subs    map[int]chan TransmissionRecord
	nextID  int
}

// NewStore keeps up to maxRecords in memory (older ones are dropped from the
// cache but remain on disk).
func NewStore(maxRecords int) *Store {
	if maxRecords <= 0 {
		maxRecords = 1000
	}
	return &Store{
		max:  maxRecords,
		subs: make(map[int]chan TransmissionRecord),
	}
}

// Add records a new transmission and notifies subscribers.
func (s *Store) Add(r TransmissionRecord) {
	s.mu.Lock()
	s.records = append(s.records, r)
	if len(s.records) > s.max {
		s.records = s.records[len(s.records)-s.max:]
	}
	s.mu.Unlock()
	s.notify(r)
}

// Update replaces the cached copy of a record (matched by ID) if present and
// notifies subscribers either way, so live viewers see edits (e.g. corrections)
// immediately. Records from past sessions not in the cache are only broadcast.
func (s *Store) Update(r TransmissionRecord) {
	s.mu.Lock()
	for i := range s.records {
		if s.records[i].ID == r.ID {
			s.records[i] = r
			break
		}
	}
	s.mu.Unlock()
	s.notify(r)
}

// notify fans a record out to all current subscribers without blocking.
func (s *Store) notify(r TransmissionRecord) {
	s.mu.RLock()
	subs := make([]chan TransmissionRecord, 0, len(s.subs))
	for _, ch := range s.subs {
		subs = append(subs, ch)
	}
	s.mu.RUnlock()

	for _, ch := range subs {
		// Non-blocking: a slow websocket client never stalls the pipeline.
		select {
		case ch <- r:
		default:
		}
	}
}

// Remove drops the cached record with the given id (if present).
func (s *Store) Remove(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := s.records[:0]
	for _, r := range s.records {
		if r.ID != id {
			out = append(out, r)
		}
	}
	s.records = out
}

// RemoveSession drops all cached records for a session.
func (s *Store) RemoveSession(sessionID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := s.records[:0]
	for _, r := range s.records {
		if r.SessionID != sessionID {
			out = append(out, r)
		}
	}
	s.records = out
}

// Recent returns up to n most-recent records (chronological order).
func (s *Store) Recent(n int) []TransmissionRecord {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if n <= 0 || n > len(s.records) {
		n = len(s.records)
	}
	out := make([]TransmissionRecord, n)
	copy(out, s.records[len(s.records)-n:])
	return out
}

// BySession returns all cached records for a session (chronological order).
func (s *Store) BySession(sessionID string) []TransmissionRecord {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var out []TransmissionRecord
	for _, r := range s.records {
		if r.SessionID == sessionID {
			out = append(out, r)
		}
	}
	return out
}

// Subscribe returns a channel of future records plus an unsubscribe func.
func (s *Store) Subscribe() (<-chan TransmissionRecord, func()) {
	ch := make(chan TransmissionRecord, 32)
	s.mu.Lock()
	id := s.nextID
	s.nextID++
	s.subs[id] = ch
	s.mu.Unlock()

	return ch, func() {
		s.mu.Lock()
		if c, ok := s.subs[id]; ok {
			delete(s.subs, id)
			close(c)
		}
		s.mu.Unlock()
	}
}
