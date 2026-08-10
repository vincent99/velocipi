package vad

// Scorer assigns a speech probability [0..1] to a single fixed-size PCM frame.
// Implementations must be safe to call from one goroutine only (the capture
// loop) unless documented otherwise.
type Scorer interface {
	// Score returns the speech probability for the frame.
	Score(frame []int16) (float64, error)
	// Close releases any resources (e.g. the sidecar process).
	Close() error
}
