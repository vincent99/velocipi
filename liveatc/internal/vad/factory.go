package vad

import (
	"context"
	"log/slog"
)

// EngineParams selects and configures a Scorer.
type EngineParams struct {
	Engine       string // "silero" or "energy"
	SileroPython string
	SileroScript string
	SampleRate   int
	FrameSamples int
	Threshold    float64
}

// NewScorer builds the configured Scorer. When "silero" is requested but the
// sidecar fails to start, it logs a warning and transparently falls back to the
// energy scorer so the pipeline still runs.
func NewScorer(ctx context.Context, p EngineParams, log *slog.Logger) Scorer {
	if p.Engine == "silero" {
		s, err := NewSileroScorer(ctx, p.SileroPython, p.SileroScript, p.SampleRate, p.FrameSamples, p.Threshold, log)
		if err == nil {
			log.Info("VAD engine: silero sidecar", "python", p.SileroPython, "script", p.SileroScript)
			return s
		}
		log.Warn("silero sidecar unavailable, falling back to energy VAD", "err", err)
	}
	log.Info("VAD engine: energy (RMS gate)")
	return NewEnergyScorer(0, 0)
}
