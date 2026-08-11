// Package vad turns a stream of scored audio frames into discrete transmission
// segments. A Scorer assigns each fixed-size frame a speech probability; the
// Segmenter applies hysteresis (min speech / min silence / max duration /
// pre-roll) to decide where one radio transmission starts and ends.
package vad

import (
	"math"
	"time"
)

// Segment is one detected transmission: contiguous PCM samples plus the
// wall-clock window they cover.
type Segment struct {
	Samples   []int16
	StartTime time.Time
	EndTime   time.Time
}

// Params configure the Segmenter. Durations come from config (ms) and the
// frame geometry from the capture layer.
type Params struct {
	SampleRate   int
	FrameSamples int
	Threshold    float64 // speech-probability cutoff [0..1]
	MinSpeech    time.Duration
	MinSilence   time.Duration
	MaxSegment   time.Duration
	PreRoll      time.Duration

	// CarrierFloor, when > 0, enables carrier-gated segmentation: a transmission
	// is bounded by the radio carrier (frame RMS) crossing this floor -- i.e. the
	// mic un-key / squelch close -- rather than by pauses in speech. This keeps a
	// whole transmission together through mid-sentence pauses and splits
	// back-to-back transmissions (tower vs read-back). Silero is then used only
	// to confirm a run holds real speech. 0 disables it (pure speech-silence
	// segmentation on MinSilence).
	CarrierFloor    float64
	CarrierHangover time.Duration // how long the carrier must stay below the floor to end a transmission
}

// Segmenter is fed one (frame, score) pair at a time via Feed. It is not
// safe for concurrent use; drive it from a single goroutine.
type Segmenter struct {
	p        Params
	frameDur time.Duration
	preRollN int // pre-roll length in samples
	now      func() time.Time

	// pre-roll history kept while idle so clipped starts are captured.
	preRoll []int16

	// current segment state
	collecting bool
	confirmed  bool // reached MinSpeech -> a real transmission
	seg        []int16
	startTime  time.Time
	speechAcc  time.Duration
	silenceAcc time.Duration
	segDur     time.Duration

	// OnSpeechStart fires once per confirmed transmission, at the moment it is
	// confirmed (used to snapshot GPS at transmission start).
	OnSpeechStart func(start time.Time)
	// OnSegment fires when a confirmed transmission ends (or is force-split).
	OnSegment func(Segment)
}

// NewSegmenter builds a Segmenter. clock may be nil (defaults to time.Now).
func NewSegmenter(p Params, clock func() time.Time) *Segmenter {
	if clock == nil {
		clock = time.Now
	}
	frameDur := time.Duration(p.FrameSamples) * time.Second / time.Duration(p.SampleRate)
	preRollN := int(p.PreRoll / time.Second * time.Duration(p.SampleRate))
	return &Segmenter{
		p:        p,
		frameDur: frameDur,
		preRollN: preRollN,
		now:      clock,
		preRoll:  make([]int16, 0, preRollN+p.FrameSamples),
	}
}

// Feed processes one frame and its speech score. It dispatches to carrier-gated
// segmentation when CarrierFloor is configured, else to speech-silence
// segmentation.
func (s *Segmenter) Feed(frame []int16, score float64) {
	if s.p.CarrierFloor > 0 {
		s.feedCarrier(frame, score)
		return
	}
	s.feedSilence(frame, score)
}

// feedSilence bounds a transmission by pauses in speech (silero below threshold
// for >= MinSilence). Simpler, but merges nothing/over-splits on feeds where
// distinct transmissions are separated only by a brief carrier drop.
func (s *Segmenter) feedSilence(frame []int16, score float64) {
	speech := score >= s.p.Threshold

	if !s.collecting {
		if speech {
			s.begin(frame, true)
		} else {
			s.pushPreRoll(frame)
		}
		return
	}

	// Collecting: every frame (including trailing silence) is appended so the
	// segment carries natural lead-out silence.
	s.seg = append(s.seg, frame...)
	s.segDur += s.frameDur

	if speech {
		s.silenceAcc = 0
		s.speechAcc += s.frameDur
		if !s.confirmed && s.speechAcc >= s.p.MinSpeech {
			s.confirmed = true
			if s.OnSpeechStart != nil {
				s.OnSpeechStart(s.startTime)
			}
		}
	} else {
		s.silenceAcc += s.frameDur
		if s.silenceAcc >= s.p.MinSilence {
			s.end()
			return
		}
	}

	// Hard cap: split long-winded transmissions so STT stays bounded.
	if s.segDur >= s.p.MaxSegment {
		s.end()
	}
}

// feedCarrier bounds a transmission by the radio carrier: a run starts when the
// frame energy rises above CarrierFloor (mic keyed) and ends once it stays below
// it for CarrierHangover (mic un-keyed / squelch closed). Speech pauses within a
// keyed transmission keep the carrier up, so they don't split it; the brief
// carrier drop between two back-to-back transmissions does. Silero (score) only
// confirms the run holds real speech, so pure squelch-tail noise bursts are
// dropped.
func (s *Segmenter) feedCarrier(frame []int16, score float64) {
	carrier := frameRMS(frame) >= s.p.CarrierFloor
	speech := score >= s.p.Threshold

	if !s.collecting {
		if carrier {
			s.begin(frame, speech)
		} else {
			s.pushPreRoll(frame)
		}
		return
	}

	s.seg = append(s.seg, frame...)
	s.segDur += s.frameDur

	// Silero confirms the keyed run actually contains speech.
	if speech {
		s.speechAcc += s.frameDur
		if !s.confirmed && s.speechAcc >= s.p.MinSpeech {
			s.confirmed = true
			if s.OnSpeechStart != nil {
				s.OnSpeechStart(s.startTime)
			}
		}
	}

	// Carrier presence (not speech) drives the boundary. Hangover rides the
	// squelch tail and momentary energy dips within a single transmission.
	if carrier {
		s.silenceAcc = 0
	} else {
		s.silenceAcc += s.frameDur
		if s.silenceAcc >= s.p.CarrierHangover {
			s.end()
			return
		}
	}

	if s.segDur >= s.p.MaxSegment {
		s.end()
	}
}

// begin seeds a new (unconfirmed) segment with the pre-roll history + this
// frame. speech reports whether the seeding frame already counts as speech (the
// silence path always begins on speech; the carrier path may begin on a keyed
// but not-yet-speech frame).
func (s *Segmenter) begin(frame []int16, speech bool) {
	s.collecting = true
	s.confirmed = false
	s.seg = make([]int16, 0, len(s.preRoll)+len(frame))
	s.seg = append(s.seg, s.preRoll...)
	s.seg = append(s.seg, frame...)
	// StartTime accounts for the pre-roll audio that precedes "now".
	preRollDur := time.Duration(len(s.preRoll)) * time.Second / time.Duration(s.p.SampleRate)
	s.startTime = s.now().Add(-preRollDur)
	if speech {
		s.speechAcc = s.frameDur
	} else {
		s.speechAcc = 0
	}
	s.silenceAcc = 0
	s.segDur = time.Duration(len(s.seg)) * time.Second / time.Duration(s.p.SampleRate)
}

// frameRMS is the root-mean-square amplitude of a frame, used as the carrier
// (received-signal) energy estimate for carrier-gated segmentation.
func frameRMS(frame []int16) float64 {
	if len(frame) == 0 {
		return 0
	}
	var sum float64
	for _, v := range frame {
		f := float64(v)
		sum += f * f
	}
	return math.Sqrt(sum / float64(len(frame)))
}

// end finalizes the current segment. Confirmed transmissions are emitted;
// unconfirmed ones (PTT blips shorter than MinSpeech) are discarded.
func (s *Segmenter) end() {
	if s.confirmed && s.OnSegment != nil {
		// Derive EndTime from the captured audio length rather than the wall
		// clock, so the duration equals the real audio span regardless of
		// capture pacing (under --fast file replay, wall-clock time is
		// compressed and would report absurdly short durations).
		audioDur := time.Duration(len(s.seg)) * time.Second / time.Duration(s.p.SampleRate)
		s.OnSegment(Segment{
			Samples:   s.seg,
			StartTime: s.startTime,
			EndTime:   s.startTime.Add(audioDur),
		})
	}
	s.collecting = false
	s.confirmed = false
	s.seg = nil
	s.speechAcc = 0
	s.silenceAcc = 0
	s.segDur = 0
	s.preRoll = s.preRoll[:0]
}

// Flush ends any in-progress transmission immediately (used on shutdown so a
// held transmission isn't lost).
func (s *Segmenter) Flush() {
	if s.collecting {
		s.end()
	}
}

// pushPreRoll keeps the trailing preRollN samples of idle audio.
func (s *Segmenter) pushPreRoll(frame []int16) {
	if s.preRollN == 0 {
		return
	}
	s.preRoll = append(s.preRoll, frame...)
	if len(s.preRoll) > s.preRollN {
		s.preRoll = s.preRoll[len(s.preRoll)-s.preRollN:]
	}
}
