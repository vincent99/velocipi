package config

import (
	"log"
	"os"
	"time"

	"gopkg.in/yaml.v3"
	"periph.io/x/conn/v3/physic"
)

// UIConfig holds the subset of config sent to the browser UI via /config.
type UIConfig struct {
	Tail string `yaml:"tail" json:"tail"`
}

// TireAddresses maps one or more BT addresses to a wheel position label.
type TireAddresses struct {
	FL []string `yaml:"fl" json:"fl"`
	FR []string `yaml:"fr" json:"fr"`
	RL []string `yaml:"rl" json:"rl"`
	RR []string `yaml:"rr" json:"rr"`
}

type ExpanderBits struct {
	KnobCenter uint `yaml:"knobCenter" json:"knobCenter"`
	KnobInner  uint `yaml:"knobInner"  json:"knobInner"`  // and bit+1
	KnobOuter  uint `yaml:"knobOuter"  json:"knobOuter"`  // and bit+1
	LED        uint `yaml:"led"        json:"led"`
	JoyCenter  uint `yaml:"joyCenter"  json:"joyCenter"`
	JoyDown    uint `yaml:"joyDown"    json:"joyDown"`
	JoyUp      uint `yaml:"joyUp"      json:"joyUp"`
	JoyRight   uint `yaml:"joyRight"   json:"joyRight"`
	JoyLeft    uint `yaml:"joyLeft"    json:"joyLeft"`
	JoyKnob    uint `yaml:"joyKnob"    json:"joyKnob"` // and bit+1
}

type ExpanderConfig struct {
	Address  uint8        `yaml:"address"  json:"address"`
	Interval string       `yaml:"interval" json:"interval"`
	Bits     ExpanderBits `yaml:"bits"     json:"bits"`
}

type SensorConfig struct {
	Address  uint8  `yaml:"address"  json:"address"`
	Interval string `yaml:"interval" json:"interval"`
}

type ScreenConfig struct {
	SplashImage    string `yaml:"splashImage"    json:"splashImage"`
	SplashDuration string `yaml:"splashDuration" json:"splashDuration"`
	FPS            int    `yaml:"fps"            json:"fps"`
}

type OLEDConfig struct {
	SPIPort  string `yaml:"spiPort"  json:"spiPort"`
	SPISpeed string `yaml:"spiSpeed" json:"spiSpeed"`
	GPIOChip string `yaml:"gpioChip" json:"gpioChip"`
	DCPin    int    `yaml:"dcPin"    json:"dcPin"`
	ResetPin int    `yaml:"resetPin" json:"resetPin"`
	Width    int    `yaml:"width"    json:"width"`
	Height   int    `yaml:"height"   json:"height"`
	Flip     bool   `yaml:"flip"     json:"flip"`
}

// Config holds all runtime configuration.
type Config struct {
	Addr        string `yaml:"addr"        json:"addr"`
	AppURL      string `yaml:"appUrl"      json:"appUrl"`
	I2CDevice   string `yaml:"i2cDevice"   json:"i2cDevice"`
	PingInterval string `yaml:"pingInterval" json:"pingInterval"`

	AirSensor   SensorConfig   `yaml:"airSensor"   json:"airSensor"`
	Expander    ExpanderConfig `yaml:"expander"    json:"expander"`
	LightSensor SensorConfig   `yaml:"lightSensor" json:"lightSensor"`
	OLED        OLEDConfig     `yaml:"oled"        json:"oled"`
	Screen      ScreenConfig   `yaml:"screen"      json:"screen"`
	Tires       TireAddresses  `yaml:"tires"       json:"tires"`
	UI          UIConfig       `yaml:"ui"          json:"ui"`

	// Parsed values — not serialized, populated by Load()
	ExpanderIntervalDur    time.Duration    `yaml:"-" json:"-"`
	AirSensorIntervalDur   time.Duration    `yaml:"-" json:"-"`
	LightSensorIntervalDur time.Duration    `yaml:"-" json:"-"`
	PingIntervalDur        time.Duration    `yaml:"-" json:"-"`
	SplashDurationDur      time.Duration    `yaml:"-" json:"-"`
	OLEDSPIFreq            physic.Frequency `yaml:"-" json:"-"`
}

var defaults = Config{
	Addr:         "0.0.0.0:8080",
	AppURL:       "http://localhost:8080/app/",
	I2CDevice:    "/dev/i2c-1",
	PingInterval: "1s",

	Expander: ExpanderConfig{
		Address:  0x20,
		Interval: "2ms",
		Bits: ExpanderBits{
			KnobCenter: 0,
			KnobInner:  1,
			KnobOuter:  3,
			LED:        6,
			JoyCenter:  8,
			JoyDown:    9,
			JoyUp:      10,
			JoyRight:   11,
			JoyLeft:    12,
			JoyKnob:    13,
		},
	},

	AirSensor: SensorConfig{
		Address:  0x77,
		Interval: "1s",
	},

	LightSensor: SensorConfig{
		Address:  0x48,
		Interval: "1s",
	},

	Screen: ScreenConfig{
		SplashImage:    "ui/public/img/logo.png",
		SplashDuration: "2s",
		FPS:            30,
	},

	OLED: OLEDConfig{
		SPIPort:  "/dev/spidev0.0",
		SPISpeed: "2.40MHz",
		GPIOChip: "gpiochip0",
		DCPin:    5,
		ResetPin: 6,
		Width:    256,
		Height:   64,
		Flip:     true,
	},

	Tires: TireAddresses{
		FL: []string{"4a:a0:00:00:eb:02", "ae3806cb-ea50-2187-4d1d-10010147721a"},
		FR: []string{"4a:85:00:00:3a:50", "bc7ac313-2870-3c1f-c2bc-6047a80b58c2"},
		RL: []string{"4a:88:00:00:72:70", "24237bb2-4496-36b6-a755-64e9de75ac6c"},
		RR: []string{"4a:85:00:00:d7:38", "99633f0c-d627-5f15-7d5d-f171b5a745e7"},
	},
}

// Load reads config.yaml, falling back to defaults for any missing fields.
// String duration/frequency fields are parsed into their typed counterparts.
func Load() *Config {
	cfg := defaults

	data, err := os.ReadFile("config.yaml")
	if err != nil {
		if !os.IsNotExist(err) {
			log.Fatal("config: read error: ", err)
		}
		log.Println("config: no config.yaml found, using defaults")
	} else {
		if err := yaml.Unmarshal(data, &cfg); err != nil {
			log.Fatal("config: parse error: ", err)
		}
	}

	cfg.ExpanderIntervalDur = parseDuration(cfg.Expander.Interval, "expander.interval")
	cfg.AirSensorIntervalDur = parseDuration(cfg.AirSensor.Interval, "airSensor.interval")
	cfg.LightSensorIntervalDur = parseDuration(cfg.LightSensor.Interval, "lightSensor.interval")
	cfg.PingIntervalDur = parseDuration(cfg.PingInterval, "pingInterval")
	cfg.SplashDurationDur = parseDuration(cfg.Screen.SplashDuration, "screen.splashDuration")

	if err := cfg.OLEDSPIFreq.Set(cfg.OLED.SPISpeed); err != nil {
		log.Fatalf("config: invalid oled.spiSpeed %q: %v", cfg.OLED.SPISpeed, err)
	}

	return &cfg
}


func parseDuration(s, field string) time.Duration {
	d, err := time.ParseDuration(s)
	if err != nil {
		log.Fatalf("config: invalid %s %q: %v", field, s, err)
	}
	return d
}
