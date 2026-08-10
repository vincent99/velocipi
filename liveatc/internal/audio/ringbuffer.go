package audio

import "sync"

// RingBuffer is a fixed-capacity, overwrite-oldest ring of int16 PCM samples.
// It exists so the pipeline always has a short window of recent audio in memory
// (e.g. for pre-roll / debugging) without ever writing the continuous stream to
// disk. Only per-transmission segments are persisted.
type RingBuffer struct {
	mu   sync.Mutex
	buf  []int16
	head int // index of next write
	size int // number of valid samples (<= cap)
	cap  int
}

// NewRingBuffer holds up to capacity samples.
func NewRingBuffer(capacity int) *RingBuffer {
	if capacity < 1 {
		capacity = 1
	}
	return &RingBuffer{buf: make([]int16, capacity), cap: capacity}
}

// Write appends samples, overwriting the oldest when full.
func (r *RingBuffer) Write(samples []int16) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, s := range samples {
		r.buf[r.head] = s
		r.head = (r.head + 1) % r.cap
		if r.size < r.cap {
			r.size++
		}
	}
}

// Last returns up to n most-recent samples in chronological order.
func (r *RingBuffer) Last(n int) []int16 {
	r.mu.Lock()
	defer r.mu.Unlock()
	if n > r.size {
		n = r.size
	}
	out := make([]int16, n)
	// Oldest of the n starts n positions behind head.
	start := (r.head - n + r.cap) % r.cap
	for i := 0; i < n; i++ {
		out[i] = r.buf[(start+i)%r.cap]
	}
	return out
}
