package vad

import "math"

// EnergyScorer is a dependency-free fallback that scores frames by RMS energy.
// It is far cruder than Silero (it can't tell speech from any loud sound) but
// lets the pipeline run in dev/CI or when the sidecar can't start.
//
// The score maps RMS in [floor, ceil] linearly to [0, 1], so a Threshold of
// 0.5 corresponds to the midpoint between the configured floor and ceiling.
type EnergyScorer struct {
	floor float64 // RMS at/below which score is 0
	ceil  float64 // RMS at/above which score is 1
}

// NewEnergyScorer uses sensible defaults for 16-bit PCM if floor/ceil are 0.
func NewEnergyScorer(floor, ceil float64) *EnergyScorer {
	if floor <= 0 {
		floor = 300 // ~ ambient hiss for a post-squelch feed
	}
	if ceil <= floor {
		ceil = 3000 // typical speech level
	}
	return &EnergyScorer{floor: floor, ceil: ceil}
}

// Score returns the normalized RMS energy of the frame.
func (e *EnergyScorer) Score(frame []int16) (float64, error) {
	if len(frame) == 0 {
		return 0, nil
	}
	var sum float64
	for _, s := range frame {
		f := float64(s)
		sum += f * f
	}
	rms := math.Sqrt(sum / float64(len(frame)))
	score := (rms - e.floor) / (e.ceil - e.floor)
	if score < 0 {
		return 0, nil
	}
	if score > 1 {
		return 1, nil
	}
	return score, nil
}

// Close is a no-op; there is nothing to release.
func (e *EnergyScorer) Close() error { return nil }
