// Package g3x provides a G3X avionics state module.
// Currently uses mock data; in the future this will be populated from live
// avionics data (e.g. serial, UDP, or Bluetooth from a Garmin G3X Touch).
package g3x

import (
	"context"
	"math"
	"sync"
	"time"
)

// State holds the current GPS/attitude state of the aircraft.
type State struct {
	Lat      float64 // degrees, positive = north
	Lon      float64 // degrees, positive = east
	AltFt    float64 // feet MSL
	Heading  float64 // degrees true (0–360)
	Roll     float64 // degrees, positive = right bank
	Pitch    float64 // degrees, positive = nose up
	Yaw      float64 // degrees true, same as Heading for fixed-wing
	SpeedKts float64 // knots ground speed
}

// G3X tracks avionics state and broadcasts updates.
type G3X struct {
	mu       sync.RWMutex
	state    State
	onChange func(State)
}

// Mock starting state: straight and level over Chandler AZ at 10,000 ft,
// headed northeast (045°) at 200 kts.
var initialState = State{
	Lat:      33.3062,
	Lon:      -111.8413,
	AltFt:    10000,
	Heading:  45,
	Roll:     0,
	Pitch:    0,
	Yaw:      45,
	SpeedKts: 200,
}

// New creates a G3X module initialised with the mock starting state.
func New() *G3X {
	return &G3X{state: initialState}
}

// State returns the current avionics state (safe for concurrent use).
func (g *G3X) State() State {
	g.mu.RLock()
	defer g.mu.RUnlock()
	return g.state
}

// OnChange registers a callback invoked each time the state is updated.
// Only one callback may be registered; a second call replaces the first.
func (g *G3X) OnChange(fn func(State)) {
	g.mu.Lock()
	g.onChange = fn
	g.mu.Unlock()
}

// Run starts the mock update loop: updates position once per second using
// simple dead-reckoning from heading and speed, then fires onChange.
// Blocks until ctx is cancelled.
func (g *G3X) Run(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			g.tick()
		}
	}
}

// tick advances the mock position by one second of dead-reckoning travel.
func (g *G3X) tick() {
	g.mu.Lock()
	s := g.state

	// Degrees per second at given speed and heading.
	// 1 knot ≈ 1 nautical mile/hr; 1 NM = 1/60 degree of latitude.
	knotsPerSec := s.SpeedKts / 3600.0
	nmPerSec := knotsPerSec
	headingRad := s.Heading * math.Pi / 180.0

	dLat := nmPerSec * math.Cos(headingRad) / 60.0
	latRad := s.Lat * math.Pi / 180.0
	dLon := nmPerSec * math.Sin(headingRad) / (60.0 * math.Cos(latRad))

	s.Lat += dLat
	s.Lon += dLon
	g.state = s
	cb := g.onChange
	g.mu.Unlock()

	if cb != nil {
		cb(s)
	}
}
