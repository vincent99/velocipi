// Sparkfun BME280 temperature/pressure/humidity sensor
// https://www.sparkfun.com/sparkfun-atmospheric-sensor-breakout-bme280-qwiic.html
// https://cdn.sparkfun.com/assets/e/7/3/b/1/BME280_Datasheet.pdf

package airsensor

import (
	"errors"
	"fmt"
	"math"
	"velocity/hardware/i2c"
)

const (
	DEFAULT_ADDRESS    = 0x77
	CALIBRATION_A_REG  = 0x88
	CALIBRATION_B_REG  = 0xE1
	CALIBRATION_H1_REG = 0xA1
	DATA_REG           = 0xF7
	CHIP_ID_REG        = 0xD0 // Chip ID
	RESET_REG          = 0xE0
	HUM_RES            = 0xF2 // Humidity config
	CONFIG_RES         = 0xF4 // Temp/Pressure/Mode config

	BME280_CTRL_HUMIDITY_REG = 0xF2 // Ctrl Humidity Reg
	BME280_STAT_REG          = 0xF3 // Status Reg
	BME280_CTRL_MEAS_REG     = 0xF4 // Ctrl Measure Reg
)

type Calibration struct {
	T1 uint16
	T2 int16
	T3 int16
	P1 uint16
	P2 int16
	P3 int16
	P4 int16
	P5 int16
	P6 int16
	P7 int16
	P8 int16
	P9 int16
	H1 uint8
	H2 int16
	H3 uint8
	H4 int16
	H5 int16
	H6 int8
}

type AirSensor struct {
	iface             *i2c.I2C
	calibration       *Calibration
	tFine             int32
	referencePressure float32
}

type Config struct {
	Address uint8
	Device  string
}

type Reading struct {
	TempC          float32
	TempF          float32
	PressureMeters float32
	PressureFeet   float32
	Humidity       float32
	DewpointC      float32
	DewpointF      float32
}

func NewAirSensor() (*AirSensor, error) {
	return NewAirSensorWithOptions(&Config{})
}

func NewAirSensorWithOptions(opt *Config) (*AirSensor, error) {
	address := opt.Address
	if address == 0 {
		address = DEFAULT_ADDRESS
	}

	iface, err := i2c.New(opt.Device, address)

	v := &AirSensor{
		iface:             iface,
		calibration:       &Calibration{},
		referencePressure: 101325.0,
	}

	if err != nil {
		return v, err
	}

	return v, v.Init()
}

func (v *AirSensor) Init() error {
	if !v.IsConnected() {
		return errors.New("air sensor not found")
	}

	chipId, err := v.iface.ReadRegisterU8(CHIP_ID_REG)
	if err != nil {
		return err
	}

	if chipId != 0x58 && chipId != 0x60 {
		return errors.New("air sensor has unrecognized chip id")
	}

	a, err := v.iface.ReadRegister(CALIBRATION_A_REG, 26)
	if err != nil {
		return err
	}

	b, err := v.iface.ReadRegister(CALIBRATION_B_REG, 8)
	if err != nil {
		return err
	}

	h1, err := v.iface.ReadRegisterU8(CALIBRATION_H1_REG)
	if err != nil {
		return err
	}

	v.calibration = &Calibration{
		T1: uint16(uint16(a[0])<<8 | uint16(a[1])),
		T2: int16(int16(a[2])<<8 | int16(a[3])),
		T3: int16(int16(a[4])<<8 | int16(a[5])),

		P1: uint16(uint16(a[6])<<8 | uint16(a[7])),
		P2: int16(int16(a[8])<<8 | int16(a[9])),
		P3: int16(int16(a[10])<<8 | int16(a[11])),
		P4: int16(int16(a[12])<<8 | int16(a[13])),
		P5: int16(int16(a[14])<<8 | int16(a[15])),
		P6: int16(int16(a[16])<<8 | int16(a[17])),
		P7: int16(int16(a[18])<<8 | int16(a[19])),
		P8: int16(int16(a[20])<<8 | int16(a[21])),
		P9: int16(int16(a[22])<<8 | int16(a[23])),

		H1: h1,
		H2: int16(int16(b[0])<<8 | int16(b[1])),
		H3: uint8(b[2]),
		H4: int16(int16(b[3])<<8 | int16(b[4])),
		H5: int16(int16(b[5])<<8 | int16(b[6])),
		H6: int8(a[7]),
	}

	fmt.Printf("Calibration A: %x\n", a)
	fmt.Printf("Calibration B: %x\n", b)
	fmt.Println(v.calibration)

	hum, err := v.iface.ReadRegisterU8(HUM_RES)
	if err != nil {
		return err
	}
	v.iface.WriteRegisterU8(HUM_RES, (hum&0b11111000)|0b001)
	v.iface.WriteRegisterU8(CONFIG_RES, 0b00100111)

	return nil
}

func (v *AirSensor) IsConnected() bool {
	var buf []byte
	_, err := v.iface.WriteBytes(buf)
	return err == nil
}

// --------

// --------

func (v *AirSensor) Read() (r *Reading, err error) {
	r = &Reading{}

	raw, err := v.iface.ReadRegister(DATA_REG, 8)
	if err != nil {
		return r, err
	}

	fmt.Printf("Read: %x\n", raw)

	p := int32(raw[0])<<12 | int32(raw[1])<<4 | (int32(raw[2]) >> 4 & 0x0F)
	t := int32(raw[3])<<12 | int32(raw[4])<<4 | (int32(raw[5]) >> 4 & 0x0F)
	h := uint16(raw[6])<<8 | uint16(raw[7])

	t1 := (((t >> 3) - int32(v.calibration.T1<<1)) * int32(v.calibration.T2)) >> 11
	t2 := (((((t >> 4) - int32(v.calibration.T1)) * ((t >> 4) - int32(v.calibration.T1))) >> 12) * int32(v.calibration.T3)) >> 14
	v.tFine = t1 + t2

	celsius := float32((v.tFine*5+128)>>8) / 100
	fahrenheit := (celsius*9)/5 + 32

	fmt.Printf("Temp: %f / %f\n", celsius, fahrenheit)

	press := int32(0)

	var p1 int64 = int64(v.tFine) - 128000
	var p2 int64 = p1 * p1 * int64(v.calibration.P6)
	p2 = p2 + (int64(p1*int64(v.calibration.P5)) << 17)
	p2 = p2 + (int64(v.calibration.P4) << 35)
	p1 = ((p1 * p1 * int64(v.calibration.P3)) >> 8) + ((p1 * int64(v.calibration.P2)) << 12)
	p1 = ((1 << 47) + p1) * (int64(v.calibration.P1)) >> 33

	if p1 != 0 {
		var pA int64 = 1048576 - int64(p)
		pA = (((pA << 31) - p2) * 3125)

		p1 = (int64(v.calibration.P9) * (pA >> 13) * (pA >> 13)) >> 25
		p2 = (int64(v.calibration.P8) * pA) >> 19
		pA = ((pA + p1 + p2) >> 8) + (int64(v.calibration.P7) << 4)

		press = int32(pA / 256.0)
	}

	meters := (-44330.77) * float32(math.Pow(float64(press/int32(v.referencePressure)), 0.190263)-1.0)
	feet := meters * 3.28084

	fmt.Printf("Pressure: %f / %f\n", meters, feet)

	var h1 int32 = (v.tFine - 76800)
	h1 = ((((int32(h) << 14) - (int32(v.calibration.H4) << 20) - (int32(v.calibration.H5) * h1)) + (16384)) >> 15) * (((((((h1*int32(v.calibration.H6))>>10)*(((h1*int32(v.calibration.H3))>>11)+(32768)))>>10)+(2097152))*int32(v.calibration.H2) + 8192) >> 14)
	h1 = (h1 - (((((h1 >> 15) * (h1 >> 15)) >> 7) * int32(v.calibration.H1)) >> 4))
	h1 = min(max(h1, 0), 419430400)

	humidity := (h1 >> 12) / 1024.0
	fmt.Printf("Humidity: %d\n", humidity)

	ratio := 373.15 / (273.15 + float64(celsius))
	rhs := -7.90298 * (ratio - 1)
	rhs += 5.02808 * math.Log10(ratio)
	rhs += -1.3816e-7 * (math.Pow(10, (11.344*(1-1/ratio))) - 1)
	rhs += 8.1328e-3 * (math.Pow(10, (-3.49149*(ratio-1))) - 1)
	rhs += float64(math.Log(1013.246))
	vp := math.Pow(10, rhs-3) * float64(humidity)
	th := math.Log(vp / 0.61078)

	dewpointCelsius := float32((241.88 * th) / (17.558 - th))
	dewpointFahrenheit := dewpointCelsius*9/5 + 32

	fmt.Printf("Dewpoint: %f / %f\n", dewpointCelsius, dewpointFahrenheit)

	return &Reading{
		TempC:          celsius,
		TempF:          fahrenheit,
		PressureMeters: meters,
		PressureFeet:   feet,
		Humidity:       float32(humidity),
		DewpointC:      dewpointCelsius,
		DewpointF:      dewpointFahrenheit,
	}, nil
}
