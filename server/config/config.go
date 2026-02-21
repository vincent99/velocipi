package config

import (
	"encoding/json"
	"log"
	"os"
	"reflect"
	"time"

	"gopkg.in/yaml.v3"
	"periph.io/x/conn/v3/physic"
)

// CameraConfig holds connection parameters for a single IP camera.
type CameraConfig struct {
	Name     string `yaml:"name"     json:"name"`
	Host     string `yaml:"host"     json:"host"`
	Port     int    `yaml:"port"     json:"port"`
	Username string `yaml:"username" json:"username"`
	Password string `yaml:"password" json:"password"`
}

// DVRConfig holds settings for the DVR recording subsystem.
type DVRConfig struct {
	RecordingsDir string         `yaml:"recordingsDir" json:"recordingsDir"`
	Cameras       []CameraConfig `yaml:"cameras"       json:"cameras"`
}

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
	Nose  []string `yaml:"nose"  json:"nose"`
	Left  []string `yaml:"left"  json:"left"`
	Right []string `yaml:"right" json:"right"`
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
	Addr         string `yaml:"addr"         json:"addr"`
	AppURL       string `yaml:"appUrl"       json:"appUrl"`
	I2CDevice    string `yaml:"i2cDevice"    json:"i2cDevice"`
	PingInterval string `yaml:"pingInterval" json:"pingInterval"`

	AirSensor   SensorConfig   `yaml:"airSensor"   json:"airSensor"`
	DVR         DVRConfig      `yaml:"dvr"         json:"dvr"`
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

// LoadResult holds both the effective merged config and the raw defaults.
type LoadResult struct {
	Config   *Config // effective merged config (defaults + overrides)
	Defaults *Config // values from config.default.yaml only
}

// Load reads config.default.yaml as the baseline, then applies any overrides
// from config.yaml (if it exists and is valid).
func Load() *LoadResult {
	var defaults Config

	data, err := os.ReadFile("config.default.yaml")
	if err != nil {
		log.Fatal("config: read error: ", err)
	}
	if err := yaml.Unmarshal(data, &defaults); err != nil {
		log.Fatal("config: parse error: ", err)
	}

	// Start with a copy of defaults, then layer overrides on top.
	cfg := defaults
	if ovData, err := os.ReadFile("config.yaml"); err == nil {
		if err := yaml.Unmarshal(ovData, &cfg); err != nil {
			log.Println("config: ignoring malformed config.yaml:", err)
		}
	}

	parseDurations(&cfg)
	parseDurations(&defaults)

	return &LoadResult{Config: &cfg, Defaults: &defaults}
}

func parseDurations(cfg *Config) {
	cfg.ExpanderIntervalDur = parseDuration(cfg.Expander.Interval, "expander.interval")
	cfg.AirSensorIntervalDur = parseDuration(cfg.AirSensor.Interval, "airSensor.interval")
	cfg.LightSensorIntervalDur = parseDuration(cfg.LightSensor.Interval, "lightSensor.interval")
	cfg.PingIntervalDur = parseDuration(cfg.PingInterval, "pingInterval")
	cfg.SplashDurationDur = parseDuration(cfg.Screen.SplashDuration, "screen.splashDuration")

	if err := cfg.OLEDSPIFreq.Set(cfg.OLED.SPISpeed); err != nil {
		log.Fatalf("config: invalid oled.spiSpeed %q: %v", cfg.OLED.SPISpeed, err)
	}
}

// SaveOverrides writes only the fields that differ from defaults to config.yaml.
func SaveOverrides(updated, defaults Config) error {
	uMap := toMap(updated)
	dMap := toMap(defaults)
	diff := diffMaps(uMap, dMap)
	data, err := yaml.Marshal(diff)
	if err != nil {
		return err
	}
	return os.WriteFile("config.yaml", data, 0644)
}

func toMap(v any) map[string]any {
	b, _ := json.Marshal(v)
	var m map[string]any
	_ = json.Unmarshal(b, &m)
	return m
}

func diffMaps(override, defaults map[string]any) map[string]any {
	result := map[string]any{}
	for k, ov := range override {
		dv, ok := defaults[k]
		if !ok {
			result[k] = ov
			continue
		}
		if om, ok2 := ov.(map[string]any); ok2 {
			if dm, ok3 := dv.(map[string]any); ok3 {
				sub := diffMaps(om, dm)
				if len(sub) > 0 {
					result[k] = sub
				}
				continue
			}
		}
		if !reflect.DeepEqual(ov, dv) {
			result[k] = ov
		}
	}
	return result
}

func parseDuration(s, field string) time.Duration {
	d, err := time.ParseDuration(s)
	if err != nil {
		log.Fatalf("config: invalid %s %q: %v", field, s, err)
	}
	return d
}
