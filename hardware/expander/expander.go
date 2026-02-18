// Sparkfun ??
// https://www.sparkfun.com/??
// https://cdn.sparkfun.com/??

package expander

import (
	"errors"
	"time"

	"github.com/vincent99/velocipi-go/hardware/i2c"
)

const (
	DEFAULT_ADDRESS = 0x20

	// Configuration 8-bit register
	CONFIG = 0x0A // General config, only 0x00 supported here.  [bank, mirror, sequential, slew, hw address, int pin open drain, int pin polarity, unused]

	// Pin configuration, 16-bits, [A7 ... A0 B7 ... B0]
	DIRECTION_CONF    = 0x00 // 0 = output, 1 = input
	POLARITY_CONF     = 0x02 // 0 = normal, 1 = reverse
	PULL_UP_CONF      = 0x0C // 0 = disabled, 1 = pull-up resistor enabled
	INTERRUPT_ENABLE  = 0x04 // 0 = disabled, 1 = enabled interrupt on change
	INTERRUPT_MODE    = 0x08 // 0 = compare previous value, 1 = compare against INTERRUPT_COMPARE
	INTERRUPT_COMPARE = 0x06 // Comparison value used when INTERRUPT_MODE on pin=1

	// Read-Only Interrupt status, 16-bits
	INTERRUPT       = 0x0E // 0 = no change, 1 = pin changed
	INTERRUPT_VALUE = 0x10 // Value of all pins at time of interrupt, value will not change until interrupt cleared via read of this or INPUT_VALUE

	// Read-Write Pin status, 16-bits
	INPUT_VALUE  = 0x12 // Read: Current value of all pins, Write: Sets OUTPUT_VALUE register
	OUTPUT_VALUE = 0x14 // Read: Current status of outputs, Write: Sets value for configured DIRECTION_CONF=output pins
)

type Expander struct {
	iface *i2c.I2C
}

type Config struct {
	Address uint8
	Device  string
}

func NewExpander() (*Expander, error) {
	return NewExpanderWithOptions(&Config{})
}

func NewExpanderWithOptions(opt *Config) (*Expander, error) {
	address := opt.Address
	if address == 0 {
		address = DEFAULT_ADDRESS
	}

	iface, err := i2c.New(opt.Device, address)

	if err != nil {
		return nil, err
	}

	v := &Expander{
		iface,
	}

	return v, v.Init()
}

func (v *Expander) Init() error {
	if !v.IsConnected() {
		return errors.New("expander not found")
	}

	if err := v.SetDirection(0xffbf); err != nil {
		return errors.New("expander could not set input direction: " + err.Error())
	}

	if err := v.SetPolarity(0xffbf); err != nil {
		return errors.New("expander could not be set polarity: " + err.Error())
	}

	if err := v.SetPullUp(0xffbf); err != nil {
		return errors.New("expander could not be set pull-up resistors: " + err.Error())
	}

	if err := v.SetInterrupts(0xffbf, 0x0000, 0x0000); err != nil {
		return errors.New("expander could set interrupt: " + err.Error())
	}

	return nil
}

func (v *Expander) IsConnected() bool {
	var buf []byte
	_, err := v.iface.WriteBytes(buf)
	return err == nil
}

// --------

func (v *Expander) SetDirection(pins uint16) error {
	return v.iface.WriteRegisterU16LE(DIRECTION_CONF, pins)
}

func (v *Expander) GetDirection() (uint16, error) {
	return v.iface.ReadRegisterU16LE(DIRECTION_CONF)
}

func (v *Expander) SetPolarity(pins uint16) error {
	return v.iface.WriteRegisterU16LE(POLARITY_CONF, pins)
}

func (v *Expander) GetPolarity() (uint16, error) {
	return v.iface.ReadRegisterU16LE(POLARITY_CONF)
}

func (v *Expander) SetPullUp(pins uint16) error {
	return v.iface.WriteRegisterU16LE(PULL_UP_CONF, pins)
}

func (v *Expander) GetPullUp() (uint16, error) {
	return v.iface.ReadRegisterU16LE(PULL_UP_CONF)
}

func (v *Expander) SetInterrupts(enabled uint16, mode uint16, value uint16) error {
	err := v.iface.WriteRegisterU16LE(INTERRUPT_ENABLE, enabled)
	if err != nil {
		return err
	}

	err = v.iface.WriteRegisterU16LE(INTERRUPT_MODE, mode)
	if err != nil {
		return err
	}

	return v.iface.WriteRegisterU16LE(INTERRUPT_COMPARE, value)
}

func (v *Expander) GetInterruptConfig() (enabled uint16, mode uint16, value uint16, err error) {
	enabled, err = v.iface.ReadRegisterU16LE(INTERRUPT_ENABLE)
	if err != nil {
		return enabled, mode, value, err
	}

	mode, err = v.iface.ReadRegisterU16LE(INTERRUPT_MODE)
	if err != nil {
		return enabled, mode, value, err
	}

	value, err = v.iface.ReadRegisterU16LE(INTERRUPT_COMPARE)
	return enabled, mode, value, err
}

func (v *Expander) Read() (uint16, error) {
	return v.iface.ReadRegisterU16LE(INPUT_VALUE)
}

func (v *Expander) Write(value uint16) error {
	return v.iface.WriteRegisterU16LE(OUTPUT_VALUE, value)
}

func (v *Expander) readInterrupt() (bool, uint16, error) {
	intr, err := v.iface.ReadRegisterU16LE(INTERRUPT)
	if err != nil {
		return false, 0, err
	}

	if intr == 0 {
		return false, 0, nil
	}

	val, err := v.iface.ReadRegisterU16LE(INTERRUPT_VALUE)
	if err != nil {
		return false, 0, err
	}

	return true, val, nil
}

func (v *Expander) Watch() (chan uint16, chan bool) {
	quit := make(chan bool)
	event := make(chan uint16)

	go func(event chan uint16) {
		ticker := time.NewTicker(10 * time.Millisecond)
		for {
			select {
			case <-ticker.C:
				changed, data, err := v.readInterrupt()
				if err != nil {
					close(event)
					close(quit)
				}

				if changed {
					event <- data
				}

			case <-quit:
				ticker.Stop()
				close(event)
				close(quit)
				return
			}
		}

	}(event)

	return event, quit
}
