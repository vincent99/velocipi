// Package brightness computes a desired 0-100% brightness level from an
// ambient light sensor, debounced/averaged over a configurable window (so a
// shadow briefly crossing the sensor doesn't cause a radical jump) and
// ramped smoothly toward that target over a configurable duration -- then
// fans the resulting percentage out to any number of subscribers. Each
// subscriber owns scaling that abstract percentage onto its own device's
// actual range (see hardware/lcd's and hardware/knob's own Set/
// SetBrightness methods) -- this package knows nothing about LCDs, knobs,
// or any other specific piece of hardware.
//
// Never crashes and never blocks on missing/broken hardware: with no
// sensor configured, or a sensor that only ever errors on read, it just
// holds at 100% forever (see New/sample's own comments).
package brightness

import (
	"context"
	"log"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/hardware/lightsensor"
)

// sampleInterval is this package's own internal sensor-polling cadence,
// independent of anything else in the process that might also be reading
// the same sensor (e.g. sensors.go's runLightSensorLoop, which exists
// purely to broadcast luxReading WS messages) -- deliberately not tied to
// that setting, since running the same shared *lightsensor.LightSensor
// singleton is inherently safe here in the low-frequency, low-stakes way
// both callers use it, and coupling this package's sampling rate to an
// unrelated one buys nothing.
const sampleInterval = time.Second

// rampSteps is how many discrete steps a ramp is divided into -- a ramp
// always takes exactly Config.Speed to complete, regardless of how big the
// jump is (a 1% correction takes just as long as a 0->100% swing), matching
// this package's brief: ramp *up/down in steps over a speed duration*.
const rampSteps = 40

// Handler is called with the new current percentage (0-100) every time it
// changes -- once per ramp step while ramping, not just once at the end.
type Handler func(pct float64)

type Config struct {
	// Sensor may be nil (or non-nil but permanently erroring on read,
	// e.g. hardware.LightSensor()'s own "always returns non-nil, error is
	// only visible via GetAmbientLux()'s return value" behavior) -- either
	// way this package just holds at 100% and keeps running.
	Sensor *lightsensor.LightSensor
	Delay  time.Duration // debounce/average window; <=0 defaults to 2s
	Speed  time.Duration // ramp duration when the target changes; <=0 defaults to 2s
	MinLux float64       // lux at/below which the target is 0%
	MaxLux float64       // lux at/above which the target is 100%; 0 defaults to 100
}

type sample struct {
	at  time.Time
	pct float64
}

type Brightness struct {
	sensor *lightsensor.LightSensor
	delay  time.Duration
	speed  time.Duration
	minLux float64
	maxLux float64

	mu        sync.Mutex
	listeners []Handler
	samples   []sample
	haveGood  bool
	target    float64
	current   float64
}

// New never fails -- there's no configuration or missing hardware that
// should prevent this package from running (see the package doc).
func New(cfg Config) *Brightness {
	maxLux := cfg.MaxLux
	if maxLux == 0 {
		maxLux = 100
	}
	delay := cfg.Delay
	if delay <= 0 {
		delay = 2 * time.Second
	}
	speed := cfg.Speed
	if speed <= 0 {
		speed = 2 * time.Second
	}
	return &Brightness{
		sensor: cfg.Sensor,
		delay:  delay,
		speed:  speed,
		minLux: cfg.MinLux,
		maxLux: maxLux,
		// Starting point before the first real sample (or forever, with no
		// working sensor) is full brightness -- never start dark.
		target:  100,
		current: 100,
	}
}

// Subscribe registers fn to be called with every new current percentage --
// immediately once with the current value, then again on every subsequent
// change (including every intermediate step of a ramp).
func (b *Brightness) Subscribe(fn Handler) {
	b.mu.Lock()
	b.listeners = append(b.listeners, fn)
	cur := b.current
	b.mu.Unlock()
	fn(cur)
}

// Current returns the last percentage sent to subscribers.
func (b *Brightness) Current() float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.current
}

// Run samples the sensor on a fixed internal cadence, recomputes the
// debounced target from the trailing Delay window, and drives the ramp
// toward it. Blocks until ctx is cancelled.
func (b *Brightness) Run(ctx context.Context) {
	if b.sensor == nil {
		log.Println("brightness: no light sensor configured, holding at 100%")
	}

	sampleTicker := time.NewTicker(sampleInterval)
	defer sampleTicker.Stop()

	rampInterval := b.speed / rampSteps
	if rampInterval <= 0 {
		rampInterval = 50 * time.Millisecond
	}
	rampTicker := time.NewTicker(rampInterval)
	defer rampTicker.Stop()

	var rampStep float64

	for {
		select {
		case <-ctx.Done():
			return

		case <-sampleTicker.C:
			b.sample()
			newTarget := b.recomputeTarget()
			b.mu.Lock()
			changed := newTarget != b.target
			b.target = newTarget
			cur := b.current
			b.mu.Unlock()
			if changed {
				rampStep = (newTarget - cur) / rampSteps
			}

		case <-rampTicker.C:
			b.mu.Lock()
			if b.current == b.target {
				b.mu.Unlock()
				continue
			}
			next := b.current + rampStep
			if rampStep == 0 || (rampStep > 0 && next >= b.target) || (rampStep < 0 && next <= b.target) {
				next = b.target
			}
			b.current = next
			listeners := append([]Handler(nil), b.listeners...)
			b.mu.Unlock()
			for _, fn := range listeners {
				fn(next)
			}
		}
	}
}

// sample reads one lux value (if a sensor is configured and it doesn't
// error) and appends it to the trailing Delay window used by
// recomputeTarget.
func (b *Brightness) sample() {
	if b.sensor == nil {
		return
	}
	lux, err := b.sensor.GetAmbientLux()
	if err != nil {
		log.Println("brightness: light sensor read error:", err)
		return
	}

	pct := luxToPct(lux, b.minLux, b.maxLux)
	now := time.Now()

	b.mu.Lock()
	b.haveGood = true
	b.samples = append(b.samples, sample{at: now, pct: pct})
	cutoff := now.Add(-b.delay)
	i := 0
	for i < len(b.samples) && b.samples[i].at.Before(cutoff) {
		i++
	}
	b.samples = b.samples[i:]
	b.mu.Unlock()
}

// recomputeTarget averages whatever samples currently fall within the
// trailing Delay window. With no sensor, or one that's never produced a
// single good reading, this keeps returning 100 forever -- the "fail
// gracefully" default.
func (b *Brightness) recomputeTarget() float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	if !b.haveGood || len(b.samples) == 0 {
		return 100
	}
	sum := 0.0
	for _, s := range b.samples {
		sum += s.pct
	}
	return sum / float64(len(b.samples))
}

func luxToPct(lux, minLux, maxLux float64) float64 {
	if maxLux <= minLux {
		return 100
	}
	if lux <= minLux {
		return 0
	}
	if lux >= maxLux {
		return 100
	}
	return 100 * (lux - minLux) / (maxLux - minLux)
}
