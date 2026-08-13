package audio

import "math"

// SplitDetector decides, frame by frame, whether a stereo feed is "mono" (both
// channels carry the same audio -- the cockpit comms are joined) or "split" (the
// two channels are independent radios, one per ear).
//
// It compares per-frame difference energy to signal energy: identical channels
// give a difference-energy ratio ~0 (mono), while independent channels (or one
// silent, one active) give a ratio near 1 (split). During silence the metric is
// meaningless, so the last decision is held. A short debounce prevents flapping
// so the join/split state can change at will without chattering.
//
// The debounce also keeps onset transients harmless: at a join<->split change
// the first ~hold frames are attributed to the old mode, but as long as
// hold*frameDur (default ~256ms) stays below the VAD min-speech (default 300ms),
// that fragment is too short to be emitted and is dropped.
type SplitDetector struct {
	thresh    float64 // diff/signal ratio above which the frame looks "split"
	floorRMS  float64 // combined RMS below which the frame is silence (state held)
	hold      int     // consecutive contrary frames required to flip state
	split     bool
	candidate bool
	count     int
}

// NewSplitDetector uses sensible defaults when thresh<=0.
func NewSplitDetector(thresh float64) *SplitDetector {
	if thresh <= 0 {
		thresh = 0.15
	}
	return &SplitDetector{
		thresh:   thresh,
		floorRMS: 200, // ~ quiet floor for a post-squelch feed
		hold:     8,   // ~256ms at 512-sample frames @ 16k
	}
}

// Split reports the current state without processing a frame.
func (d *SplitDetector) Split() bool { return d.split }

// Update processes one aligned L/R frame and returns the current split state.
func (d *SplitDetector) Update(l, r []int16) bool {
	n := len(l)
	if len(r) < n {
		n = len(r)
	}
	if n == 0 {
		return d.split
	}
	var diff, sig float64
	for i := 0; i < n; i++ {
		a, b := float64(l[i]), float64(r[i])
		delta := a - b
		diff += delta * delta
		sig += a*a + b*b
	}
	// Silence -> hold the current decision (the ratio is noise when quiet).
	if math.Sqrt(sig/float64(2*n)) < d.floorRMS {
		d.count = 0
		return d.split
	}

	want := diff/(sig+1e-9) > d.thresh
	if want == d.split {
		d.count = 0
		return d.split
	}
	// Debounce: require `hold` consecutive frames of the contrary reading.
	if want == d.candidate {
		d.count++
	} else {
		d.candidate, d.count = want, 1
	}
	if d.count >= d.hold {
		d.split, d.count = want, 0
	}
	return d.split
}
