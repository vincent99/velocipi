package led

import (
	"time"

	"github.com/vincent99/velocipi-go/hardware/expander"
)

// State holds the current LED state.
type State struct {
	Mode string        // "off", "on", or "blink"
	Rate time.Duration // only meaningful when Mode == "blink"
}

// Controller manages a single LED wired to one bit of an expander.
type Controller struct {
	mask     uint16
	blinkCh  chan struct{}
	state    State
	onChange func(State)
}

// New creates a Controller for the LED at the given bit position.
func New(bit uint) *Controller {
	return &Controller{
		mask:  1 << bit,
		state: State{Mode: "off"},
	}
}

// OnChange registers a callback that is called whenever the LED state changes.
// Only one callback is supported; calling again replaces the previous one.
func (l *Controller) OnChange(fn func(State)) {
	l.onChange = fn
}

// CurrentState returns the current LED state.
func (l *Controller) CurrentState() State {
	return l.state
}

func (l *Controller) stopBlink() {
	if l.blinkCh != nil {
		close(l.blinkCh)
		l.blinkCh = nil
	}
}

func (l *Controller) notify() {
	if l.onChange != nil {
		l.onChange(l.state)
	}
}

// On turns the LED on and stops any active blink.
func (l *Controller) On(e *expander.Expander) {
	l.stopBlink()
	_ = e.Write(l.mask, l.mask)
	l.state = State{Mode: "on"}
	l.notify()
}

// Off turns the LED off and stops any active blink.
func (l *Controller) Off(e *expander.Expander) {
	l.stopBlink()
	_ = e.Write(0, l.mask)
	l.state = State{Mode: "off"}
	l.notify()
}

// Blink toggles the LED at the given rate, stopping any previous blink.
func (l *Controller) Blink(e *expander.Expander, rate time.Duration) {
	l.stopBlink()
	stop := make(chan struct{})
	l.blinkCh = stop
	l.state = State{Mode: "blink", Rate: rate}
	l.notify()
	go func() {
		on := true
		ticker := time.NewTicker(rate)
		defer ticker.Stop()
		for {
			select {
			case <-stop:
				return
			case <-ticker.C:
				val := uint16(0)
				if on {
					val = l.mask
				}
				_ = e.Write(val, l.mask)
				on = !on
			}
		}
	}()
}
