// Package ptt monitors a push-to-talk (PTT) GPIO line to classify a
// transmission as outgoing (tx). See the pipeline for the fallback audio-level
// heuristic used when no PTT line is wired.
//
// TX vs RX detection, two options (both documented in the code):
//  1. GPIO PTT (this package): if the pilot's PTT line is wired to a Pi GPIO,
//     a high level during a transmission means the pilot was keying the radio,
//     so the transmission is definitively "tx" (otherwise "rx"). Definitive.
//  2. Audio-level heuristic (pipeline): the TX sidetone on a cockpit intercom
//     is typically louder than received audio, so mean segment RMS above a
//     configurable threshold suggests "tx". Ambiguous -> "unknown".
package ptt

import "time"

// Monitor reports whether the PTT line was asserted during a time window.
type Monitor interface {
	// Enabled reports whether a real GPIO line is being watched.
	Enabled() bool
	// ActiveSince reports whether PTT was asserted at or after t (i.e. during a
	// transmission that started at t).
	ActiveSince(t time.Time) bool
	// Close releases the GPIO line.
	Close() error
}

type disabled struct{}

func (disabled) Enabled() bool              { return false }
func (disabled) ActiveSince(time.Time) bool { return false }
func (disabled) Close() error               { return nil }

// Disabled returns a no-op monitor (used when no PTT pin is configured or on
// platforms without GPIO support).
func Disabled() Monitor { return disabled{} }
