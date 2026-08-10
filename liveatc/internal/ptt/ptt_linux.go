//go:build linux

package ptt

import (
	"log/slog"
	"sync"
	"time"

	gpiocdev "github.com/warthog618/go-gpiocdev"
)

// lineMonitor watches a single GPIO line for edges. gpiocdev's rising edge is
// "inactive -> active", already normalized for active-low via WithActiveLow, so
// we track logical assertion state without re-deriving polarity here.
type lineMonitor struct {
	line *gpiocdev.Line
	log  *slog.Logger

	mu       sync.Mutex
	active   bool      // currently asserted
	lastFall time.Time // wall-clock time of the most recent deassert
}

// New requests the PTT line with both-edge event reporting.
func New(chip string, offset int, activeLow bool, log *slog.Logger) (Monitor, error) {
	m := &lineMonitor{log: log}

	opts := []gpiocdev.LineReqOption{
		gpiocdev.WithBothEdges,
		gpiocdev.WithEventHandler(m.handle),
	}
	if activeLow {
		opts = append(opts, gpiocdev.AsActiveLow)
	}

	line, err := gpiocdev.RequestLine(chip, offset, opts...)
	if err != nil {
		return nil, err
	}
	m.line = line

	// Seed initial state (the line may already be asserted at startup).
	if v, err := line.Value(); err == nil {
		m.active = v == 1
	}
	log.Info("PTT GPIO monitor active", "chip", chip, "offset", offset, "activeLow", activeLow)
	return m, nil
}

func (m *lineMonitor) handle(evt gpiocdev.LineEvent) {
	m.mu.Lock()
	switch evt.Type {
	case gpiocdev.LineEventRisingEdge:
		m.active = true
	case gpiocdev.LineEventFallingEdge:
		m.active = false
		m.lastFall = time.Now()
	}
	m.mu.Unlock()
}

func (m *lineMonitor) Enabled() bool { return true }

func (m *lineMonitor) ActiveSince(t time.Time) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	// Asserted now, or was released after the transmission began.
	return m.active || m.lastFall.After(t)
}

func (m *lineMonitor) Close() error {
	if m.line != nil {
		return m.line.Close()
	}
	return nil
}
