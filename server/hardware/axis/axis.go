// Package axis provides avionics state for the panel-mounted Garmin Axis
// displays (formerly referred to as "G3X" in this codebase, before the
// switch to Axis screens).
// Currently uses mock data; in the future this will be populated from live
// avionics data (e.g. serial, UDP, or Bluetooth from the real unit).
package axis

import (
	"context"
	"math"
	"math/rand"
	"sync"
	"time"
)

func randFloat() float64 { return rand.Float64() }

// State holds the current GPS/attitude state of the aircraft.
type State struct {
	Lat      float64 `json:"lat"`        // degrees, positive = north
	Lon      float64 `json:"lon"`        // degrees, positive = east
	AltFt    float64 `json:"altFt"`      // feet MSL
	Heading  float64 `json:"heading"`    // degrees true (0–360)
	Roll     float64 `json:"roll"`       // degrees, positive = right bank
	Pitch    float64 `json:"pitch"`      // degrees, positive = nose up
	Yaw      float64 `json:"yaw"`        // degrees true, same as Heading for fixed-wing
	SpeedKts float64 `json:"speedKts"`   // knots ground speed
	OAT      float64 `json:"oatCelsius"` // outside air temperature, °C
	Origin   string  `json:"origin"`     // ICAO airport code of the origin airport
	Dest     string  `json:"dest"`       // ICAO airport code of the destination airport
	Com1     float64 `json:"com1"`       // COM1 frequency, Hz
	Com2     float64 `json:"com2"`       // COM2 frequency, Hz
	Nav1     float64 `json:"nav1"`       // NAV1 frequency, Hz
	Nav2     float64 `json:"nav2"`       // NAV2 frequency, Hz
}

// Axis tracks avionics state and broadcasts updates.
type Axis struct {
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
	Heading:  93,
	Roll:     0,
	Pitch:    0,
	Yaw:      93,
	SpeedKts: 200,
	OAT:      40,
	Origin:   "KCHD",
	Dest:     "X26",
	Com1:     126.1,
	Com2:     124.4,
	Nav1:     114.8,
	Nav2:     110.6,
}

// CelsiusToFahrenheit converts a temperature from °C to °F.
func CelsiusToFahrenheit(c float64) float64 { return c*9/5 + 32 }

// New creates an Axis module initialised with the mock starting state.
func New() *Axis {
	return &Axis{state: initialState}
}

// State returns the current avionics state (safe for concurrent use).
func (a *Axis) State() State {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.state
}

// OnChange registers a callback invoked each time the state is updated.
// Only one callback may be registered; a second call replaces the first.
func (a *Axis) OnChange(fn func(State)) {
	a.mu.Lock()
	a.onChange = fn
	a.mu.Unlock()
}

// Run starts the mock update loop: updates position once per second using
// simple dead-reckoning from heading and speed, then fires onChange.
// Blocks until ctx is cancelled.
func (a *Axis) Run(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			a.tick()
		}
	}
}

// tick advances the mock position by one second of dead-reckoning travel.
func (a *Axis) tick() {
	a.mu.Lock()
	s := a.state

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

	// Random walk: OAT ±0.1°C/s, altitude ±10 ft/s.
	s.OAT += (math.Round(randFloat()*2-1) * 0.1)
	s.AltFt += (math.Round(randFloat()*2-1) * 10)

	a.state = s
	cb := a.onChange
	a.mu.Unlock()

	if cb != nil {
		cb(s)
	}
}
