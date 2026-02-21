// Sparkfun SX1509 16-bit I2C GPIO expander
// https://www.sparkfun.com/sparkfun-16-output-i-o-expander-breakout-sx1509.html

package expander

import (
	"time"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware/i2c"
)

const (
	DEFAULT_ADDRESS = 0x3E

	DIRECTION_CONF    = 0x00 // 0 = output, 1 = input
	POLARITY_CONF     = 0x02
	PULL_UP_CONF      = 0x0C
	INTERRUPT_ENABLE  = 0x04
	INTERRUPT_MODE    = 0x08
	INTERRUPT_COMPARE = 0x06
	INTERRUPT         = 0x0E
	INTERRUPT_VALUE   = 0x10
	INPUT_VALUE       = 0x12
	OUTPUT_VALUE      = 0x14
)

type Expander struct {
	iface    *i2c.I2C
	interval time.Duration
	previous uint16
	updates  chan Change
	stop     chan struct{}
}

type Change struct {
	Value    uint16
	Previous uint16
}

func New() (*Expander, error) {
	cfg := config.Load().Config
	address := cfg.Expander.Address
	if address == 0 {
		address = DEFAULT_ADDRESS
	}

	iface, err := i2c.New(cfg.I2CDevice, address)
	if err != nil {
		return nil, err
	}

	return &Expander{
		iface:    iface,
		interval: cfg.ExpanderIntervalDur,
		updates:  make(chan Change, 16),
		stop:     make(chan struct{}),
	}, nil
}

// Init configures the expander. inputs is a bitmask where 1 = input pin, 0 = output pin.
func (e *Expander) Init(inputs uint16) error {
	if err := e.SetDirection(inputs); err != nil {
		return err
	}

	if err := e.SetPolarity(0xFFFF); err != nil {
		return err
	}

	if err := e.SetPullUp(inputs); err != nil {
		return err
	}

	val, err := e.Read()
	if err != nil {
		return err
	}
	e.previous = val

	go e.poll()
	return nil
}

// Updates returns the channel that receives a Change whenever the input state changes.
func (e *Expander) Updates() <-chan Change {
	return e.updates
}

// Close stops the polling goroutine.
func (e *Expander) Close() {
	close(e.stop)
}

// poll reads the input register on each tick and sends to the updates channel on change.
func (e *Expander) poll() {
	ticker := time.NewTicker(e.interval)
	defer ticker.Stop()

	for {
		select {
		case <-e.stop:
			return
		case <-ticker.C:
			value, err := e.iface.ReadRegisterU16LE(INPUT_VALUE)
			if err != nil {
				continue
			}

			previous := e.previous
			if value == previous {
				continue
			}
			e.previous = value

			select {
			case e.updates <- Change{Value: value, Previous: previous}:
			default:
			}
		}
	}
}

// --- Configuration ---

func (e *Expander) SetDirection(pins uint16) error {
	return e.iface.WriteRegisterU16LE(DIRECTION_CONF, pins)
}

func (e *Expander) GetDirection() (uint16, error) {
	return e.iface.ReadRegisterU16LE(DIRECTION_CONF)
}

func (e *Expander) SetPolarity(pins uint16) error {
	return e.iface.WriteRegisterU16LE(POLARITY_CONF, pins)
}

func (e *Expander) GetPolarity() (uint16, error) {
	return e.iface.ReadRegisterU16LE(POLARITY_CONF)
}

func (e *Expander) SetPullUp(pins uint16) error {
	return e.iface.WriteRegisterU16LE(PULL_UP_CONF, pins)
}

func (e *Expander) GetPullUp() (uint16, error) {
	return e.iface.ReadRegisterU16LE(PULL_UP_CONF)
}

func (e *Expander) SetInterrupts(enabled, mode, value uint16) error {
	if err := e.iface.WriteRegisterU16LE(INTERRUPT_ENABLE, enabled); err != nil {
		return err
	}
	if err := e.iface.WriteRegisterU16LE(INTERRUPT_MODE, mode); err != nil {
		return err
	}
	return e.iface.WriteRegisterU16LE(INTERRUPT_COMPARE, value)
}

func (e *Expander) GetInterruptConfig() (enabled, mode, value uint16, err error) {
	if enabled, err = e.iface.ReadRegisterU16LE(INTERRUPT_ENABLE); err != nil {
		return
	}
	if mode, err = e.iface.ReadRegisterU16LE(INTERRUPT_MODE); err != nil {
		return
	}
	value, err = e.iface.ReadRegisterU16LE(INTERRUPT_COMPARE)
	return
}

// --- I/O ---

func (e *Expander) Read() (uint16, error) {
	return e.iface.ReadRegisterU16LE(INPUT_VALUE)
}

// Write sets output pins. If mask is 0xFFFF all pins are written directly.
// Otherwise only the masked bits are changed.
func (e *Expander) Write(value, mask uint16) error {
	if mask != 0xFFFF {
		cur, err := e.Read()
		if err != nil {
			return err
		}
		value = (cur &^ mask) | (value & mask)
	}
	return e.iface.WriteRegisterU16LE(OUTPUT_VALUE, value)
}
