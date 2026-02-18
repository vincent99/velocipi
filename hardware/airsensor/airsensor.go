// Sparkfun BME280 temperature/pressure/humidity sensor
// https://www.sparkfun.com/sparkfun-atmospheric-sensor-breakout-bme280-qwiic.html
// https://cdn.sparkfun.com/assets/e/7/3/b/1/BME280_Datasheet.pdf

package airsensor

import (
	"errors"
	"math"

	"github.com/vincent99/velocipi-go/hardware/i2c"
)

const (
	DEFAULT_ADDRESS    = 0x77
	CALIBRATION_A_REG  = 0x88
	CALIBRATION_B_REG  = 0xE1
	CALIBRATION_H1_REG = 0xA1
	DATA_REG           = 0xF7
	CHIP_ID_REG        = 0xD0 // Chip ID
	RESET_REG          = 0xE0
	CONFIG_HUM_RES     = 0xF2 // Humidity config
	CONFIG_MEAS_RES    = 0xF4 // Temp/Pressure config
	CONFIG_RES         = 0xF5 // Other config
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
	config            *Config
	calibration       *Calibration
	tFine             int32
	referencePressure float32
}

type RunMode byte

const (
	SLEEP  RunMode = 0b00
	FORCED RunMode = 0b01
	NORMAL RunMode = 0b11
)

type StandbyConfig byte

const (
	SB_1    StandbyConfig = 0b000
	SB_10   StandbyConfig = 0b110 // Yes, they're out of order.
	SB_20   StandbyConfig = 0b111
	SB_62   StandbyConfig = 0b001
	SB_125  StandbyConfig = 0b010
	SB_250  StandbyConfig = 0b011
	SB_500  StandbyConfig = 0b100
	SB_1000 StandbyConfig = 0b101
)

type FilterConfig byte

const (
	FILTER_OFF FilterConfig = 0b000
	FILTER_2   FilterConfig = 0b001
	FILTER_4   FilterConfig = 0b010
	FILTER_8   FilterConfig = 0b011
	FILTER_16  FilterConfig = 0b100
)

type OversampleConfig byte

const (
	SKIPPED OversampleConfig = 0b000
	OS_1    OversampleConfig = 0b001
	OS_2    OversampleConfig = 0b010
	OS_4    OversampleConfig = 0b011
	OS_8    OversampleConfig = 0b100
	OS_16   OversampleConfig = 0b101
)

type Config struct {
	Address uint8
	Device  string

	Mode               RunMode
	Standby            StandbyConfig
	Filter             FilterConfig
	TempOversample     OversampleConfig
	TempCorrectionC    float32
	PressureOversample OversampleConfig
	HumidityOversample OversampleConfig
}

type Reading struct {
	TempC          float32 `json:"tempC"`
	TempF          float32 `json:"tempF"`
	PressureInches float32 `json:"pressureInches"`
	PressureMeters float32 `json:"pressureMeters"`
	PressureFeet   float32 `json:"pressureFeet"`
	Humidity       float32 `json:"humidity"`
	DewpointC      float32 `json:"dewpointC"`
	DewpointF      float32 `json:"dewpointF"`
}

func NewAirSensor() (*AirSensor, error) {
	return NewAirSensorWithOptions(&Config{
		Mode:               NORMAL,
		Standby:            SB_1,
		Filter:             FILTER_2,
		TempOversample:     OS_16,
		PressureOversample: OS_16,
		HumidityOversample: OS_16,
		TempCorrectionC:    0,
	})
}

func NewAirSensorWithOptions(opt *Config) (*AirSensor, error) {
	address := opt.Address
	if address == 0 {
		address = DEFAULT_ADDRESS
	}

	iface, err := i2c.New(opt.Device, address)

	v := &AirSensor{
		iface:             iface,
		config:            opt,
		calibration:       &Calibration{},
		referencePressure: 101325.0,
		tFine:             0,
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
		T1: uint16(uint16(a[1])<<8 | uint16(a[0])),
		T2: int16(int16(a[3])<<8 | int16(a[2])),
		T3: int16(int16(a[5])<<8 | int16(a[4])),

		P1: uint16(uint16(a[7])<<8 | uint16(a[6])),
		P2: int16(int16(a[9])<<8 | int16(a[8])),
		P3: int16(int16(a[11])<<8 | int16(a[10])),
		P4: int16(int16(a[13])<<8 | int16(a[12])),
		P5: int16(int16(a[15])<<8 | int16(a[14])),
		P6: int16(int16(a[17])<<8 | int16(a[16])),
		P7: int16(int16(a[19])<<8 | int16(a[18])),
		P8: int16(int16(a[21])<<8 | int16(a[20])),
		P9: int16(int16(a[23])<<8 | int16(a[22])),

		H1: h1,
		H2: int16(int16(b[1])<<8 | int16(b[0])),
		H3: uint8(b[2]),
		H4: int16(int16(b[3])<<4 | (int16(b[4]) & 0x0F)),
		H5: int16(int16(b[5])<<4 | (int16(b[4]) >> 4 & 0x0F)),
		H6: int8(b[6]),
	}

	//fmt.Printf("Calibration A: %x\n", a)
	//fmt.Printf("Calibration B: %x\n", b)
	//fmt.Println(v.calibration)

	return v.WriteConfig()
}

func (v *AirSensor) IsConnected() bool {
	var buf []byte
	_, err := v.iface.WriteBytes(buf)
	return err == nil
}

func (v *AirSensor) Reset() error {
	return v.iface.WriteRegisterU8(RESET_REG, 0xB6)
}

// --------

func (v *AirSensor) WriteConfig() error {
	err := v.SetMode(SLEEP)
	if err != nil {
		return err
	}

	hum, err := v.iface.ReadRegisterU8(CONFIG_HUM_RES)
	if err != nil {
		return err
	}

	hum = (hum & 0b11111000) | byte(v.config.HumidityOversample)
	cfg := byte(v.config.Standby)<<5 | byte(v.config.Filter)<<2
	meas := byte(v.config.TempOversample)<<5 | byte(v.config.PressureOversample)<<2 | byte(v.config.Mode)

	//fmt.Printf("Write %x: %08b\n", CONFIG_HUM_RES, hum)
	err = v.iface.WriteRegisterU8(CONFIG_HUM_RES, hum)
	if err != nil {
		return err
	}

	//fmt.Printf("Write %x: %08b\n", CONFIG_RES, cfg)
	err = v.iface.WriteRegisterU8(CONFIG_RES, cfg)
	if err != nil {
		return err
	}

	//fmt.Printf("Write %x: %08b\n", CONFIG_MEAS_RES, meas)
	return v.iface.WriteRegisterU8(CONFIG_MEAS_RES, meas)
}

func (v *AirSensor) GetMode() (RunMode, error) {
	cfg, err := v.iface.ReadRegisterU8(CONFIG_MEAS_RES)
	if err != nil {
		return SLEEP, err
	}

	return RunMode(cfg & 0b11), nil
}

func (v *AirSensor) SetMode(val RunMode) error {
	cfg, err := v.iface.ReadRegisterU8(CONFIG_MEAS_RES)
	if err != nil {
		return err
	}

	cfg = (cfg & 0b11111100) | (byte(val) << 2)
	return v.iface.WriteRegisterU8(CONFIG_MEAS_RES, cfg)
}

// --------

func (v *AirSensor) Read() (r *Reading, err error) {
	r = &Reading{}

	raw, err := v.iface.ReadRegister(DATA_REG, 8)
	if err != nil {
		return r, err
	}

	//fmt.Printf("Read: %x\n", raw)

	p := int32(raw[0])<<12 | int32(raw[1])<<4 | (int32(raw[2]) >> 4 & 0x0F)
	t := int32(raw[3])<<12 | int32(raw[4])<<4 | (int32(raw[5]) >> 4 & 0x0F)
	h := uint16(raw[6])<<8 | uint16(raw[7])

	t1 := (((t >> 3) - int32(v.calibration.T1<<1)) * int32(v.calibration.T2)) >> 11
	t2 := (((((t >> 4) - int32(v.calibration.T1)) * ((t >> 4) - int32(v.calibration.T1))) >> 12) * int32(v.calibration.T3)) >> 14
	v.tFine = t1 + t2

	celsius := float32((v.tFine*5+128)>>8)/100 + v.config.TempCorrectionC
	fahrenheit := (celsius*9)/5 + 32

	//fmt.Printf("Temp: %f / %f\n", celsius, fahrenheit)

	press := float32(0)

	var p1 int64 = int64(v.tFine) - 128000
	var p2 int64 = p1 * p1 * int64(v.calibration.P6)
	p2 = p2 + (int64(p1*int64(v.calibration.P5)) << 17)
	p2 = p2 + (int64(v.calibration.P4) << 35)
	p1 = ((p1 * p1 * int64(v.calibration.P3)) >> 8) + ((p1 * int64(v.calibration.P2)) << 12)
	p1 = ((1 << 47) + p1) * (int64(v.calibration.P1)) >> 33

	if p1 != 0 {
		var pA int64 = 1048576 - int64(p)
		pA = (((pA << 31) - p2) * 3125) / p1
		p1 = (int64(v.calibration.P9) * (pA >> 13) * (pA >> 13)) >> 25
		p2 = (int64(v.calibration.P8) * pA) >> 19
		pA = ((pA + p1 + p2) >> 8) + (int64(v.calibration.P7) << 4)
		press = float32(pA / 256.0)
	}

	inches := press / 3386.39
	meters := (-44330.77) * float32(math.Pow(float64(press/v.referencePressure), 0.190263)-1.0)
	feet := meters * 3.28084

	//fmt.Printf("Pressure: %f\" %fm / %fft\n", inches, meters, feet)

	var h1 int32 = (v.tFine - 76800)
	h1 = ((((int32(h) << 14) - (int32(v.calibration.H4) << 20) - (int32(v.calibration.H5) * h1)) + (16384)) >> 15) * (((((((h1*int32(v.calibration.H6))>>10)*(((h1*int32(v.calibration.H3))>>11)+(32768)))>>10)+(2097152))*int32(v.calibration.H2) + 8192) >> 14)
	h1 = (h1 - (((((h1 >> 15) * (h1 >> 15)) >> 7) * int32(v.calibration.H1)) >> 4))
	h1 = min(max(h1, 0), 419430400)

	humidity := float32(h1>>12) / 1024.0
	//fmt.Printf("Humidity: %f%%\n", humidity)

	ratio := 373.15 / (273.15 + float64(celsius))
	rhs := -7.90298 * (ratio - 1)
	rhs += 5.02808 * math.Log10(ratio)
	rhs += -1.3816e-7 * (math.Pow(10, (11.344*(1-1/ratio))) - 1)
	rhs += 8.1328e-3 * (math.Pow(10, (-3.49149*(ratio-1))) - 1)
	rhs += float64(math.Log10(1013.246))
	vp := math.Pow(10, rhs-3) * float64(humidity)
	th := math.Log(vp / 0.61078)

	dewpointCelsius := float32((241.88 * th) / (17.558 - th))
	dewpointFahrenheit := dewpointCelsius*9/5 + 32

	// fmt.Printf("Dewpoint: %f C / %f F\n", dewpointCelsius, dewpointFahrenheit)

	return &Reading{
		TempC:          celsius,
		TempF:          fahrenheit,
		PressureInches: inches,
		PressureMeters: meters,
		PressureFeet:   feet,
		Humidity:       float32(humidity),
		DewpointC:      dewpointCelsius,
		DewpointF:      dewpointFahrenheit,
	}, nil
}
