//go:build !linux

package ptt

import (
	"errors"
	"log/slog"
)

// New is unsupported off Linux (GPIO character device is Linux-only). The
// pipeline treats the returned error as "no PTT" and falls back to the
// audio-level heuristic.
func New(chip string, offset int, activeLow bool, log *slog.Logger) (Monitor, error) {
	return nil, errors.New("PTT GPIO monitor is only supported on linux")
}
