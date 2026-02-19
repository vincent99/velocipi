// Sparkfun VEML6030 ambient light sensor
// https://www.sparkfun.com/sparkfun-ambient-light-sensor-veml6030-qwiic.html
// https://cdn.sparkfun.com/assets/d/7/4/2/9/veml6030_datasheet.pdf

package lightsensor

import (
	"errors"
	"math"

	"github.com/vincent99/velocipi-go/config"
	"github.com/vincent99/velocipi-go/hardware/i2c"
)

const (
	DEFAULT_ADDRESS = 0x48

	// 16-bit registers
	SETTING_REG            = 0x00
	H_THRESH_REG           = 0x01
	L_THRESH_REG           = 0x02
	POWER_SAVE_REG         = 0x03
	AMBIENT_LIGHT_DATA_REG = 0x04
	WHITE_LIGHT_DATA_REG   = 0x05
	INTERRUPT_REG          = 0x06

	// 16-bit register masks
	THRESH_MASK    = 0x0
	GAIN_MASK      = 0x1800
	INTEG_MASK     = 0x03C0
	PERS_PROT_MASK = 0x0030
	INT_EN_MASK    = 0x0002
	INT_MASK       = 0xC000

	// Register bit positions
	NO_SHIFT      = 0x00
	INT_EN_POS    = 0x01
	PSM_POS       = 0x01
	PERS_PROT_POS = 0x04
	INTEG_POS     = 0x06
	GAIN_POS      = 0xB
	INT_POS       = 0xE

	// Integration times
	INTEG_TIME_800 = 800
	INTEG_TIME_400 = 400
	INTEG_TIME_200 = 200
	INTEG_TIME_100 = 100
	INTEG_TIME_50  = 50
	INTEG_TIME_25  = 25
)

// Table of lux conversion values depending on the integration time and gain.
// The arrays represent the all possible integration times and the index of the
// arrays represent the register's gain settings, which is directly analogous to
// their bit representations.
var EIGHT_HIT = [4]float64{0.0036, 0.0072, 0.0288, 0.0576}
var FOUR_HIT = [4]float64{0.0072, 0.0144, 0.0576, 0.1152}
var TWO_HIT = [4]float64{0.0144, 0.0288, 0.1152, 0.2304}
var ONE_HIT = [4]float64{0.0288, 0.0576, 0.2304, 0.4608}
var FIFTY_HIT = [4]float64{0.0576, 0.1152, 0.4608, 0.9216}
var TWENTY_FIVE_IT = [4]float64{0.1152, 0.2304, 0.9216, 1.8432}

type LightSensor struct {
	iface *i2c.I2C
}

type Config struct {
	Address uint8
	Device  string
}

func NewLightSensor() (*LightSensor, error) {
	cfg := config.Load()
	return NewLightSensorWithOptions(&Config{
		Address: cfg.LightSensorAddress,
		Device:  cfg.I2CDevice,
	})
}

func NewLightSensorWithOptions(opt *Config) (*LightSensor, error) {
	address := opt.Address
	if address == 0 {
		address = DEFAULT_ADDRESS
	}

	iface, err := i2c.New(opt.Device, address)

	v := &LightSensor{
		iface,
	}

	if err != nil {
		return v, err
	}

	return v, v.Init()
}

func (v *LightSensor) Init() error {
	if !v.IsConnected() {
		return errors.New("light sensor not found")
	}

	if err := v.SetPower(true); err != nil {
		return errors.New("light sensor could not be powered on: " + err.Error())
	}

	if err := v.SetGain(4); err != nil {
		return errors.New("light sensor could not be set gain: " + err.Error())
	}

	if err := v.SetIntegrationTime(800); err != nil {
		return errors.New("light sensor could not be set integration: " + err.Error())
	}

	if err := v.SetPersistenceProtect(8); err != nil {
		return errors.New("light sensor could not be set persistence: " + err.Error())
	}

	if err := v.SetInterruptEnabled(false); err != nil {
		return errors.New("light sensor could disable interrupt: " + err.Error())
	}

	if err := v.SetInterruptThresholds(100, 1000); err != nil {
		return errors.New("light sensor could set interrupt thresholds: " + err.Error())
	}

	return nil
}

func (v *LightSensor) IsConnected() bool {
	var buf []byte
	_, err := v.iface.WriteBytes(buf)
	return err == nil
}

// --------

func (v *LightSensor) SetPower(on bool) error {
	if on {
		return v.writeRegister(SETTING_REG, 0x0001, 0, 0)
	} else {
		return v.writeRegister(SETTING_REG, 0x0001, 1, 0)
	}
}

func (v *LightSensor) GetPower() (on bool, err error) {
	raw, err := v.readRegister(SETTING_REG)
	if err != nil {
		return false, err
	}

	on = (raw & 0x0001) == 0
	return on, nil
}

func (v *LightSensor) SetPowerSave(enabled bool, mode int) error {
	var val uint16

	if enabled {
		val = 0
	} else {
		val = 1
	}

	if mode < 1 || mode > 4 {
		return errors.New("invalid power save mode")
	}

	val += uint16((mode - 1) << 1)

	return v.writeRegister(POWER_SAVE_REG, 0x0007, val, 0)
}

func (v *LightSensor) GetPowerSave() (enabled bool, mode int, err error) {
	val, err := v.readRegister(POWER_SAVE_REG)

	if err != nil {
		return false, 0, err
	}

	enabled = (val & 0x1) == 1
	mode = int((val&0x6)>>1) + 1
	return
}

// --------

func (v *LightSensor) SetGain(gain int) (err error) {
	if gain < 1 || gain > 4 {
		return errors.New("invalid gain")
	}

	var val uint16 = 0

	switch gain {
	case 1:
		val = 0x02 // Gain 1/8
	case 2:
		val = 0x03 // Gain 1/4
	case 3:
		val = 0x00 // Gain 1
	case 4:
		val = 0x01 // Gain 2
	}

	return v.writeRegister(SETTING_REG, GAIN_MASK, val, GAIN_POS)
}

func (v *LightSensor) GetGain() (gain int, err error) {
	raw, err := v.readRegister(SETTING_REG)

	if err != nil {
		return 0, err
	}

	val := (raw & GAIN_MASK) >> GAIN_POS

	switch val {
	case 0x00:
		return 3, nil
	case 0x01:
		return 4, nil
	case 0x02:
		return 1, nil
	case 0x03:
		return 2, nil
	}

	return 0, errors.New("invalid gain received")
}

// --------

func (v *LightSensor) SetIntegrationTime(time int) (err error) {
	var val uint16 = 0

	switch time {
	case 25:
		val = 0x0C
	case 50:
		val = 0x08
	case 100:
		val = 0x00
	case 200:
		val = 0x01
	case 400:
		val = 0x02
	case 800:
		val = 0x03
	default:
		return errors.New("invalid integration time")
	}

	return v.writeRegister(SETTING_REG, INTEG_MASK, val, INTEG_POS)
}

func (v *LightSensor) GetIntegrationTime() (time int, err error) {
	raw, err := v.readRegister(SETTING_REG)

	if err != nil {
		return 0, err
	}

	val := (raw & INTEG_MASK) >> INTEG_POS

	switch val {
	case 0x0C:
		return 25, nil
	case 0x08:
		return 50, nil
	case 0x00:
		return 100, nil
	case 0x01:
		return 200, nil
	case 0x02:
		return 400, nil
	case 0x03:
		return 800, nil
	default:
		return 0, errors.New("invalid integration time")
	}
}

// --------

func (v *LightSensor) SetPersistenceProtect(num int) (err error) {
	var val uint16 = 0

	switch num {
	case 1:
		val = 0x00
	case 2:
		val = 0x01
	case 4:
		val = 0x02
	case 8:
		val = 0x03
	default:
		return errors.New("invalid persistence protect")
	}

	return v.writeRegister(SETTING_REG, PERS_PROT_MASK, val, PERS_PROT_POS)
}

func (v *LightSensor) GetPersistenceProtect() (num int, err error) {
	raw, err := v.readRegister(SETTING_REG)

	if err != nil {
		return 0, err
	}

	val := (raw & PERS_PROT_MASK) >> PERS_PROT_POS

	switch val {
	case 0x00:
		return 1, nil
	case 0x01:
		return 2, nil
	case 0x02:
		return 4, nil
	case 0x04:
		return 8, nil
	default:
		return 0, errors.New("invalid persistence protect")
	}
}

// --------

func (v *LightSensor) SetInterruptEnabled(enabled bool) (err error) {
	if enabled {
		return v.writeRegister(SETTING_REG, INT_EN_MASK, 1, INT_EN_POS)
	} else {
		return v.writeRegister(SETTING_REG, INT_EN_MASK, 0, INT_EN_POS)
	}
}

func (v *LightSensor) GetInterruptEnabled() (enabled bool, err error) {
	raw, err := v.readRegister(SETTING_REG)

	if err != nil {
		return false, err
	}

	val := (raw & INT_EN_MASK) >> INT_EN_POS

	return val > 0, nil
}

func (v *LightSensor) SetInterruptThresholds(lowLux int, highLux int) (err error) {
	if lowLux < 0 || lowLux > 120000 {
		return errors.New("invalid low lux value")
	}

	if highLux < 0 || highLux > 120000 {
		return errors.New("invalid high lux value")
	}

	lowBits, err := v.luxToBits(lowLux)
	if err != nil {
		return err
	}

	highBits, err := v.luxToBits(highLux)
	if err != nil {
		return err
	}

	err = v.writeRegister(L_THRESH_REG, THRESH_MASK, lowBits, NO_SHIFT)
	if err != nil {
		return err
	}

	err = v.writeRegister(H_THRESH_REG, THRESH_MASK, highBits, NO_SHIFT)
	if err != nil {
		return err
	}

	return nil
}

func (v *LightSensor) GetInterruptThresholds() (low int, high int, err error) {

	lowBits, err := v.readRegister(L_THRESH_REG)
	if err != nil {
		return 0, 0, err
	}

	highBits, err := v.readRegister(H_THRESH_REG)
	if err != nil {
		return 0, 0, err
	}

	low, err = v.bitsToLux(lowBits)
	if err != nil {
		return 0, 0, err
	}

	high, err = v.bitsToLux(highBits)
	if err != nil {
		return 0, 0, err
	}

	return low, high, nil
}

type Interrupt int

const (
	None Interrupt = iota
	Low
	High
)

func (v *LightSensor) ReadInterrupt() (status Interrupt, err error) {
	raw, err := v.readRegister(INTERRUPT_REG)
	if err != nil {
		return None, err
	}

	val := (raw & INT_MASK) >> INT_POS

	switch val {
	case 0:
		return None, nil
	case 1:
		return High, nil
	case 2:
		return Low, nil
	default:
		return None, errors.New("invalid interrupt state")
	}
}

func (v *LightSensor) GetAmbientLux() (lux float64, err error) {
	bits, err := v.readRegister(AMBIENT_LIGHT_DATA_REG)
	if err != nil {
		return 1000, err
	}

	return v.bitsToLuxCompensated(bits)
}

func (v *LightSensor) GetWhiteLux() (lux float64, err error) {
	bits, err := v.readRegister(WHITE_LIGHT_DATA_REG)
	if err != nil {
		return 1000, err
	}

	return v.bitsToLuxCompensated(bits)
}

// ----------------

func (v *LightSensor) readRegister(reg byte) (data uint16, err error) {
	return v.iface.ReadRegisterU16LE(reg)
}

func (v *LightSensor) writeRegister(reg byte, mask uint16, data uint16, shift uint16) (err error) {
	if shift > 0 {
		data = data << shift
	}

	var val uint16

	if mask > 0 {
		// fmt.Printf("Write  %d: %0.16b %X %d\n", reg, mask, data, shift)
		val, err = v.readRegister(reg)
		if err != nil {
			return err
		}

		// fmt.Printf("Mask    : %0.16b\n", mask)
		// fmt.Printf("Current : %0.16b\n", val)
		// fmt.Printf("Old Bits: %0.16b\n", (val & ^mask))
		// fmt.Printf("Data    : %0.16b\n", data)
		// fmt.Printf("New Bits: %0.16b\n", (data & mask))

		val = (val & ^mask) | (data & mask)
	} else {
		val = data
	}

	// fmt.Printf("Result  : %0.16b\n--------\n", val)
	err = v.iface.WriteRegisterU16LE(reg, val)
	return err
}

func (v *LightSensor) luxToBitFactor() (factor float64, err error) {
	gain, err := v.GetGain()
	if err != nil {
		return 0, err
	}

	integration, err := v.GetIntegrationTime()
	if err != nil {
		return 0, err
	}

	var index = gain - 1

	switch integration {
	case 800:
		factor = EIGHT_HIT[index]
	case 400:
		factor = FOUR_HIT[index]
	case 200:
		factor = TWO_HIT[index]
	case 100:
		factor = ONE_HIT[index]
	case 50:
		factor = FIFTY_HIT[index]
	case 25:
		factor = TWENTY_FIVE_IT[index]
	}

	return factor, nil
}

func (v *LightSensor) luxToBits(lux int) (bits uint16, err error) {
	factor, err := v.luxToBitFactor()
	if err != nil {
		return 0, err
	}

	bits = uint16(math.Round(float64(lux) / factor))

	return bits, nil
}

func (v *LightSensor) bitsToLux(bits uint16) (lux int, err error) {
	factor, err := v.luxToBitFactor()
	if err != nil {
		return 0, err
	}

	lux = int(math.Round(float64(bits) * factor))

	return lux, nil
}

func (v *LightSensor) bitsToLuxCompensated(bits uint16) (lux float64, err error) {
	val, err := v.bitsToLux(bits)
	flux := float64(val)

	if err != nil {
		return 0, err
	}

	if val <= 1000 {
		return flux, nil
	}

	compensated := (0.00000000000060135*math.Pow(flux, 4) - 0.0000000093924*math.Pow(flux, 3) + 0.000081488*math.Pow(flux, 2) + 1.0023*flux)

	return compensated, nil
}
