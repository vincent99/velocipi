package music

import (
	"math/rand"
	"sort"
	"sync"
)

// RepeatMode controls what happens at the end of the queue.
type RepeatMode string

const (
	RepeatOff   RepeatMode = "off"
	RepeatSong  RepeatMode = "song"
	RepeatQueue RepeatMode = "queue"
)

// QueueEntry is one item in the playback queue.
type QueueEntry struct {
	SongID        int64 `json:"songId"`
	OriginalIndex int   `json:"originalIndex"` // position before shuffle; -1 means not set
}

// QueueState is a serialisable snapshot of the queue.
type QueueState struct {
	Entries      []QueueEntry `json:"entries"`
	CurrentIndex int          `json:"currentIndex"`
	Shuffle      bool         `json:"shuffle"`
	Repeat       RepeatMode   `json:"repeat"`
}

// Queue manages the ordered list of songs to be played.
type Queue struct {
	mu           sync.RWMutex
	entries      []QueueEntry
	currentIndex int
	shuffle      bool
	repeat       RepeatMode
}

// NewQueue creates an empty queue.
func NewQueue() *Queue {
	return &Queue{repeat: RepeatOff}
}

// Replace wipes the queue and fills it with the given song IDs.
func (q *Queue) Replace(songIDs []int64) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.entries = make([]QueueEntry, len(songIDs))
	for i, id := range songIDs {
		q.entries[i] = QueueEntry{SongID: id, OriginalIndex: -1}
	}
	q.currentIndex = 0
	if q.shuffle {
		q.shuffleRemaining()
	}
}

// EnqueueAfterCurrent inserts songIDs immediately after the current position.
func (q *Queue) EnqueueAfterCurrent(songIDs []int64) {
	q.mu.Lock()
	defer q.mu.Unlock()
	insert := make([]QueueEntry, len(songIDs))
	for i, id := range songIDs {
		insert[i] = QueueEntry{SongID: id, OriginalIndex: -1}
	}
	pos := q.currentIndex + 1
	if pos > len(q.entries) {
		pos = len(q.entries)
	}
	q.entries = append(q.entries[:pos], append(insert, q.entries[pos:]...)...)
}

// Append adds songIDs to the end of the queue.
func (q *Queue) Append(songIDs []int64) {
	q.mu.Lock()
	defer q.mu.Unlock()
	for _, id := range songIDs {
		q.entries = append(q.entries, QueueEntry{SongID: id, OriginalIndex: -1})
	}
}

// Current returns the song ID at the current position and whether it exists.
func (q *Queue) Current() (songID int64, index int, ok bool) {
	q.mu.RLock()
	defer q.mu.RUnlock()
	if len(q.entries) == 0 || q.currentIndex < 0 || q.currentIndex >= len(q.entries) {
		return 0, 0, false
	}
	return q.entries[q.currentIndex].SongID, q.currentIndex, true
}

// Advance moves to the next song according to repeat mode.
// Returns (songID, true) if there is a next song, or (0, false) if playback should stop.
func (q *Queue) Advance() (songID int64, ok bool) {
	q.mu.Lock()
	defer q.mu.Unlock()

	switch q.repeat {
	case RepeatSong:
		if len(q.entries) == 0 {
			return 0, false
		}
		return q.entries[q.currentIndex].SongID, true

	case RepeatQueue:
		q.currentIndex++
		if q.currentIndex >= len(q.entries) {
			q.currentIndex = 0
			if q.shuffle {
				// Re-randomize entire queue, saving original indices.
				q.shuffleAll()
			}
		}
		if len(q.entries) == 0 {
			return 0, false
		}
		return q.entries[q.currentIndex].SongID, true

	default: // RepeatOff
		q.currentIndex++
		if q.currentIndex >= len(q.entries) {
			return 0, false
		}
		return q.entries[q.currentIndex].SongID, true
	}
}

// Prev moves to the previous song. Returns (songID, true) if available.
func (q *Queue) Prev() (songID int64, ok bool) {
	q.mu.Lock()
	defer q.mu.Unlock()
	if q.currentIndex <= 0 {
		if len(q.entries) > 0 {
			return q.entries[0].SongID, true
		}
		return 0, false
	}
	q.currentIndex--
	return q.entries[q.currentIndex].SongID, true
}

// SetShuffle enables or disables shuffle mode.
func (q *Queue) SetShuffle(on bool) {
	q.mu.Lock()
	defer q.mu.Unlock()
	if on == q.shuffle {
		return
	}
	q.shuffle = on
	if on {
		q.shuffleRemaining()
	} else {
		q.unshuffleRemaining()
	}
}

// SetRepeat changes the repeat mode.
func (q *Queue) SetRepeat(mode RepeatMode) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.repeat = mode
}

// Len returns the total number of entries in the queue.
func (q *Queue) Len() int {
	q.mu.RLock()
	defer q.mu.RUnlock()
	return len(q.entries)
}

// Shuffle returns the current shuffle state.
func (q *Queue) Shuffle() bool {
	q.mu.RLock()
	defer q.mu.RUnlock()
	return q.shuffle
}

// Repeat returns the current repeat mode.
func (q *Queue) Repeat() RepeatMode {
	q.mu.RLock()
	defer q.mu.RUnlock()
	return q.repeat
}

// State returns a serialisable snapshot.
func (q *Queue) State() QueueState {
	q.mu.RLock()
	defer q.mu.RUnlock()
	entries := make([]QueueEntry, len(q.entries))
	copy(entries, q.entries)
	return QueueState{
		Entries:      entries,
		CurrentIndex: q.currentIndex,
		Shuffle:      q.shuffle,
		Repeat:       q.repeat,
	}
}

// JumpTo sets the current queue index without advancing playback.
// Returns false if the index is out of range.
func (q *Queue) JumpTo(index int) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	if index < 0 || index >= len(q.entries) {
		return false
	}
	q.currentIndex = index
	return true
}

// RemoveAt removes the entry at the given queue index.
// If index is the current song and playback is active, the caller must handle
// stopping/advancing. Adjusts currentIndex if needed.
func (q *Queue) RemoveAt(index int) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	if index < 0 || index >= len(q.entries) {
		return false
	}
	q.entries = append(q.entries[:index], q.entries[index+1:]...)
	// Keep currentIndex valid.
	if q.currentIndex > index {
		q.currentIndex--
	}
	if q.currentIndex >= len(q.entries) && q.currentIndex > 0 {
		q.currentIndex = len(q.entries) - 1
	}
	return true
}

// MoveAt moves the entry at fromIndex to toIndex, shifting other entries.
// Returns false if either index is out of range.
func (q *Queue) MoveAt(fromIndex, toIndex int) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	n := len(q.entries)
	if fromIndex < 0 || fromIndex >= n || toIndex < 0 || toIndex >= n || fromIndex == toIndex {
		return false
	}
	entry := q.entries[fromIndex]
	// Remove from old position.
	q.entries = append(q.entries[:fromIndex], q.entries[fromIndex+1:]...)
	// Insert at new position.
	q.entries = append(q.entries[:toIndex], append([]QueueEntry{entry}, q.entries[toIndex:]...)...)
	// Keep currentIndex pointing at the same song.
	if q.currentIndex == fromIndex {
		q.currentIndex = toIndex
	} else if fromIndex < q.currentIndex && toIndex >= q.currentIndex {
		q.currentIndex--
	} else if fromIndex > q.currentIndex && toIndex <= q.currentIndex {
		q.currentIndex++
	}
	return true
}

// Restore loads state from a snapshot.
func (q *Queue) Restore(s QueueState) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.entries = s.Entries
	q.currentIndex = s.CurrentIndex
	q.shuffle = s.Shuffle
	q.repeat = s.Repeat
}

// shuffleRemaining randomizes all entries after currentIndex.
// Must be called with lock held.
func (q *Queue) shuffleRemaining() {
	start := q.currentIndex + 1
	if start >= len(q.entries) {
		return
	}
	tail := q.entries[start:]
	// Save original indices.
	for i := range tail {
		if tail[i].OriginalIndex < 0 {
			tail[i].OriginalIndex = start + i
		}
	}
	rand.Shuffle(len(tail), func(i, j int) {
		tail[i], tail[j] = tail[j], tail[i]
	})
}

// unshuffleRemaining sorts entries after currentIndex by OriginalIndex and clears that field.
// Must be called with lock held.
func (q *Queue) unshuffleRemaining() {
	start := q.currentIndex + 1
	if start >= len(q.entries) {
		return
	}
	tail := q.entries[start:]
	sort.Slice(tail, func(i, j int) bool {
		return tail[i].OriginalIndex < tail[j].OriginalIndex
	})
	for i := range tail {
		tail[i].OriginalIndex = -1
	}
}

// shuffleAll randomizes the entire queue and resets currentIndex to 0.
// Must be called with lock held.
func (q *Queue) shuffleAll() {
	for i := range q.entries {
		q.entries[i].OriginalIndex = i
	}
	rand.Shuffle(len(q.entries), func(i, j int) {
		q.entries[i], q.entries[j] = q.entries[j], q.entries[i]
	})
}
