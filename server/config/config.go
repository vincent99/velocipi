package config

import (
	"log"
	"os"
	"time"

	"gopkg.in/yaml.v3"
	"periph.io/x/conn/v3/physic"
)

// NavMenuConfig holds display settings for the panel navigation menu.
type NavMenuConfig struct {
	HideDelay int `yaml:"hideDelay" json:"hideDelay"` // ms
	CellWidth int `yaml:"cellWidth" json:"cellWidth"` // px
}

// KeyMapConfig maps logical key names to the JS key values used in DOM events.
type KeyMapConfig struct {
	Up         string `yaml:"up"         json:"up"`
	Down       string `yaml:"down"       json:"down"`
	Left       string `yaml:"left"       json:"left"`
	Right      string `yaml:"right"      json:"right"`
	Enter      string `yaml:"enter"      json:"enter"`
	JoyLeft    string `yaml:"joyLeft"    json:"joyLeft"`
	JoyRight   string `yaml:"joyRight"   json:"joyRight"`
	InnerLeft  string `yaml:"innerLeft"  json:"innerLeft"`
	InnerRight string `yaml:"innerRight" json:"innerRight"`
	OuterLeft  string `yaml:"outerLeft"  json:"outerLeft"`
	OuterRight string `yaml:"outerRight" json:"outerRight"`
}

// PanelConfig holds the physical dimensions of the OLED panel display.
type PanelConfig struct {
	Width  int `yaml:"width"  json:"width"`
	Height int `yaml:"height" json:"height"`
}

// UIConfig holds the subset of config sent to the browser UI via /config.
type UIConfig struct {
	Tail        string        `yaml:"tail"        json:"tail"`
	HeaderColor string        `yaml:"headerColor" json:"headerColor"`
	Panel       PanelConfig   `yaml:"panel"       json:"panel"`
	NavMenu     NavMenuConfig `yaml:"navMenu"     json:"navMenu"`
	KeyMap      KeyMapConfig  `yaml:"keyMap"      json:"keyMap"`
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
	KnobInner  uint `yaml:"knobInner"  json:"knobInner"` // and bit+1
	KnobOuter  uint `yaml:"knobOuter"  json:"knobOuter"` // and bit+1
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
	Flip     bool   `yaml:"flip"     json:"flip"`
}

// Config holds all runtime configuration.
type Config struct {
	Addr         string `yaml:"addr"        json:"addr"`
	AppURL       string `yaml:"appUrl"      json:"appUrl"`
	I2CDevice    string `yaml:"i2cDevice"   json:"i2cDevice"`
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

// Load reads config.yaml and parses it.
// String duration/frequency fields are parsed into their typed counterparts.
func Load() *Config {
	var cfg Config

	data, err := os.ReadFile("config.yaml")
	if err != nil {
		log.Fatal("config: read error: ", err)
	}
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		log.Fatal("config: parse error: ", err)
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
