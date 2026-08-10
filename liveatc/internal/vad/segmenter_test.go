package vad

import (
	"testing"
	"time"
)

// makeFrame returns a frame of the given amplitude (0 = silence).
func makeFrame(n int, amp int16) []int16 {
	f := make([]int16, n)
	for i := range f {
		f[i] = amp
	}
	return f
}

// feedFrames pushes count frames of the given score into the segmenter.
func feedFrames(s *Segmenter, count int, score float64) {
	for i := 0; i < count; i++ {
		s.Feed(makeFrame(s.p.FrameSamples, 1000), score)
	}
}

func newTestSegmenter(clock func() time.Time) (*Segmenter, *[]Segment) {
	// 16k, 512-sample frames = 32ms/frame.
	p := Params{
		SampleRate:   16000,
		FrameSamples: 512,
		Threshold:    0.5,
		MinSpeech:    300 * time.Millisecond, // ~10 frames
		MinSilence:   800 * time.Millisecond, // ~25 frames
		MaxSegment:   60000 * time.Millisecond,
		PreRoll:      200 * time.Millisecond, // ~6 frames
	}
	s := NewSegmenter(p, clock)
	var got []Segment
	s.OnSegment = func(seg Segment) { got = append(got, seg) }
	return s, &got
}

func TestSegmenterEmitsOnSilence(t *testing.T) {
	s, got := newTestSegmenter(nil)

	feedFrames(s, 5, 0.0)  // idle (builds pre-roll)
	feedFrames(s, 20, 0.9) // ~640ms speech (> min speech)
	feedFrames(s, 30, 0.0) // ~960ms silence (> min silence) -> emit

	if len(*got) != 1 {
		t.Fatalf("expected 1 segment, got %d", len(*got))
	}
	// Pre-roll (6) + 20 speech + trailing silence up to the emit point (25).
	seg := (*got)[0]
	minLen := (6 + 20) * 512
	if len(seg.Samples) < minLen {
		t.Errorf("segment too short: got %d samples, want >= %d", len(seg.Samples), minLen)
	}
}

func TestSegmenterDropsShortBlip(t *testing.T) {
	s, got := newTestSegmenter(nil)

	feedFrames(s, 5, 0.0)  // idle
	feedFrames(s, 3, 0.9)  // ~96ms speech (< 300ms min) -> a PTT blip
	feedFrames(s, 30, 0.0) // silence ends the candidate

	if len(*got) != 0 {
		t.Fatalf("expected blip to be dropped, got %d segments", len(*got))
	}
}

func TestSegmenterSpeechStartFires(t *testing.T) {
	s, _ := newTestSegmenter(nil)
	fired := 0
	s.OnSpeechStart = func(time.Time) { fired++ }

	feedFrames(s, 20, 0.9)
	feedFrames(s, 30, 0.0)

	if fired != 1 {
		t.Fatalf("expected OnSpeechStart once, got %d", fired)
	}
}

func TestSegmenterFlushEmitsHeld(t *testing.T) {
	s, got := newTestSegmenter(nil)

	feedFrames(s, 20, 0.9) // confirmed speech, no trailing silence
	s.Flush()

	if len(*got) != 1 {
		t.Fatalf("expected Flush to emit held segment, got %d", len(*got))
	}
}
