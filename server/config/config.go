package config

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"reflect"
	"time"

	"gopkg.in/yaml.v3"
	"periph.io/x/conn/v3/physic"
)

// CameraConfig holds connection parameters for a single IP camera.
type CameraConfig struct {
	Name       string `yaml:"name"       json:"name"`
	Driver     string `yaml:"driver"     json:"driver"` // "rtsp" (default/empty) or "siyi"
	Host       string `yaml:"host"       json:"host"`
	Port       int    `yaml:"port"       json:"port"`
	Username   string `yaml:"username"   json:"username"`
	Password   string `yaml:"password"   json:"password"`
	Audio      bool   `yaml:"audio"      json:"audio"`                  // record and stream audio (default false)
	Record     *bool  `yaml:"record,omitempty" json:"record,omitempty"` // nil or true = record; false = skip
	Sort       *int   `yaml:"sort,omitempty"   json:"sort,omitempty"`
	SiyiAIHost string `yaml:"siyiAIHost" json:"siyiAIHost"` // IP of AI tracking module; empty = disabled
}

// MusicConfig holds settings for the music player subsystem.
type MusicConfig struct {
	Volume                int     `yaml:"volume"               json:"volume"`
	AudioDevice           string  `yaml:"audioDevice"          json:"audioDevice"` // mpv --audio-device value; "auto" = let mpv choose
	AlbumRequiredPercent  int     `yaml:"albumRequiredPercent" json:"albumRequiredPercent"`
	MinDbVersion          int     `yaml:"minDbVersion"         json:"minDbVersion"`
	MaxBitrate            int     `yaml:"maxBitrate"            json:"maxBitrate"`            // kbps; 0 = no limit
	TranscodeFormat       string  `yaml:"transcodeFormat"       json:"transcodeFormat"`       // e.g. "aac", "mp3"
	PlayedRequiredPercent int     `yaml:"playedRequiredPercent" json:"playedRequiredPercent"` // % elapsed before a skip counts as a play
	AcoustIDKey           string  `yaml:"acoustidKey"           json:"acoustidKey"`           // AcoustID API key (register free at acoustid.org)
	AcoustIDMinScore      float64 `yaml:"acoustidMinScore"      json:"acoustidMinScore"`      // minimum AcoustID match score (0.0–1.0) to accept a result
}

// StorageConfig holds filesystem directory paths for all subsystems.
type StorageConfig struct {
	DVR    string `yaml:"dvr"    json:"dvr"`    // recordings directory; default "recordings"
	Music  string `yaml:"music"  json:"music"`  // music library root; default "music"
	Backup string `yaml:"backup" json:"backup"` // database backup directory; default "backup"
	Snaps  string `yaml:"snaps"  json:"snaps"`  // downloaded camera snaps/photos; default "snaps"
}

// DVRConfig holds settings for the DVR recording subsystem.
type DVRConfig struct {
	SegmentDuration int            `yaml:"segmentDuration" json:"segmentDuration"` // seconds
	ThumbnailHeight int            `yaml:"thumbnailHeight" json:"thumbnailHeight"` // px height for snapshot + segment thumbnails
	FFmpegLog       bool           `yaml:"ffmpegLog"       json:"ffmpegLog"`       // pipe ffmpeg stderr to server log
	Record          bool           `yaml:"record"          json:"record"`          // enable recording on startup (default true)
	MinFreeDisk     float64        `yaml:"minFreeDisk"     json:"minFreeDisk"`     // minimum free disk space in GB; 0 = disabled
	DiskSpacePoll   string         `yaml:"diskSpacePoll"   json:"diskSpacePoll"`   // how often to poll disk space, e.g. "1m"
	Cameras         []CameraConfig `yaml:"cameras"         json:"cameras"`
}

// NavMenuConfig holds display settings for the panel navigation menu.
type NavMenuConfig struct {
	HideDelay   int `yaml:"hideDelay"   json:"hideDelay"`   // ms
	CellWidth   int `yaml:"cellWidth"   json:"cellWidth"`   // px
	LongPressMs int `yaml:"longPressMs" json:"longPressMs"` // ms hold for long-press cancel
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

// PanelConfig holds the physical dimensions and color scheme of the OLED panel display.
type PanelConfig struct {
	Width              int    `yaml:"width"               json:"width"`
	Height             int    `yaml:"height"              json:"height"`
	ControlBackground  string `yaml:"controlBackground"   json:"controlBackground"`  // default control background
	ControlBorder      string `yaml:"controlBorder"       json:"controlBorder"`      // default control border
	ControlText        string `yaml:"controlText"         json:"controlText"`        // default control text
	SelectedBackground string `yaml:"selectedBackground"  json:"selectedBackground"` // focused (selected) control background
	SelectedBorder     string `yaml:"selectedBorder"      json:"selectedBorder"`     // focused control border
	SelectedText       string `yaml:"selectedText"        json:"selectedText"`       // focused control text
	ActiveBackground   string `yaml:"activeBackground"    json:"activeBackground"`   // active (editing) control background
	ActiveBorder       string `yaml:"activeBorder"        json:"activeBorder"`       // active control border
	ActiveText         string `yaml:"activeText"          json:"activeText"`         // active control text
	HomeTimezone       string `yaml:"homeTimezone"        json:"homeTimezone"`       // IANA tz for "Home" clock
	TimeFormat         string `yaml:"timeFormat"          json:"timeFormat"`         // dayjs format string e.g. "hh:mm:ssa", "HH:mm:ss"
}

// UIConfig holds the subset of config sent to the browser UI via /config.
type UIConfig struct {
	Tail             string        `yaml:"tail"             json:"tail"`
	HeaderColor      string        `yaml:"headerColor"      json:"headerColor"`
	AdminHeaderColor string        `yaml:"adminHeaderColor" json:"adminHeaderColor"`
	Panel            PanelConfig   `yaml:"panel"            json:"panel"`
	NavMenu          NavMenuConfig `yaml:"navMenu"          json:"navMenu"`
	KeyMap           KeyMapConfig  `yaml:"keyMap"           json:"keyMap"`
}

// StringSlice is a []string that unmarshals from either a YAML scalar ("abc")
// or a YAML sequence (["abc", "def"]).
type StringSlice []string

func (s *StringSlice) UnmarshalYAML(value *yaml.Node) error {
	switch value.Kind {
	case yaml.ScalarNode:
		*s = StringSlice{value.Value}
	case yaml.SequenceNode:
		var ss []string
		if err := value.Decode(&ss); err != nil {
			return err
		}
		*s = ss
	default:
		return fmt.Errorf("config: cannot unmarshal %v into StringSlice", value.Tag)
	}
	return nil
}

// TireAddresses maps one or more BT addresses to a wheel position label.
type TireAddresses struct {
	Nose  StringSlice `yaml:"nose"  json:"nose"`
	Left  StringSlice `yaml:"left"  json:"left"`
	Right StringSlice `yaml:"right" json:"right"`
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
	Driver    string `yaml:"driver"    json:"driver"` // "ssd1327" or "ge256x64b"
	SPISpeed  string `yaml:"spiSpeed"  json:"spiSpeed"`
	GPIOChip  string `yaml:"gpioChip"  json:"gpioChip"`
	StatusPin int    `yaml:"statusPin" json:"statusPin"`
	ResetPin  int    `yaml:"resetPin"  json:"resetPin"`
	Flip      bool   `yaml:"flip"      json:"flip"`
}

// AirConConfig holds BLE client settings for the aircon controller.
type AirConConfig struct {
	// DeviceName is the BLE local name advertised by the AirCon controller
	// (e.g. "AirCon"). If empty, the aircon subsystem is disabled.
	DeviceName string `yaml:"deviceName" json:"deviceName"`
	// ServiceUUID is the 128-bit custom GATT service UUID advertised by the controller.
	ServiceUUID string `yaml:"serviceUUID" json:"serviceUUID"`
	// HistoryMinutes is how many minutes of temperature data to keep in memory.
	HistoryMinutes int `yaml:"historyMinutes" json:"historyMinutes"`
}

// Config holds all runtime configuration.
type Config struct {
	Addr         string `yaml:"addr"         json:"addr"`
	I2CDevice    string `yaml:"i2cDevice"    json:"i2cDevice"`
	SPIDevice    string `yaml:"spiDevice"    json:"spiDevice"`
	PingInterval string `yaml:"pingInterval" json:"pingInterval"`

	Storage     StorageConfig  `yaml:"storage"     json:"storage"`
	AirSensor   SensorConfig   `yaml:"airSensor"   json:"airSensor"`
	DVR         DVRConfig      `yaml:"dvr"         json:"dvr"`
	Music       MusicConfig    `yaml:"music"       json:"music"`
	Expander    ExpanderConfig `yaml:"expander"    json:"expander"`
	LightSensor SensorConfig   `yaml:"lightSensor" json:"lightSensor"`
	OLED        OLEDConfig     `yaml:"oled"        json:"oled"`
	Screen      ScreenConfig   `yaml:"screen"      json:"screen"`
	Tires       TireAddresses  `yaml:"tires"       json:"tires"`
	UI          UIConfig       `yaml:"ui"          json:"ui"`
	AirCon      AirConConfig   `yaml:"airCon"      json:"airCon"`

	// Parsed values — not serialized, populated by Load()
	AppURL                 string           `yaml:"-" json:"-"` // http://localhost:<VELOCIPI_PORT>/panel/
	ExpanderIntervalDur    time.Duration    `yaml:"-" json:"-"`
	AirSensorIntervalDur   time.Duration    `yaml:"-" json:"-"`
	LightSensorIntervalDur time.Duration    `yaml:"-" json:"-"`
	PingIntervalDur        time.Duration    `yaml:"-" json:"-"`
	SplashDurationDur      time.Duration    `yaml:"-" json:"-"`
	DVRDiskSpacePollDur    time.Duration    `yaml:"-" json:"-"`
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

	// Build AppURL from VELOCIPI_PORT (default 8080).
	port := os.Getenv("VELOCIPI_PORT")
	if port == "" {
		port = "8080"
	}
	cfg.AppURL = "http://localhost:" + port + "/panel/"
	defaults.AppURL = cfg.AppURL

	return &LoadResult{Config: &cfg, Defaults: &defaults}
}

func parseDurations(cfg *Config) {
	cfg.ExpanderIntervalDur = parseDuration(cfg.Expander.Interval, "expander.interval")
	cfg.AirSensorIntervalDur = parseDuration(cfg.AirSensor.Interval, "airSensor.interval")
	cfg.LightSensorIntervalDur = parseDuration(cfg.LightSensor.Interval, "lightSensor.interval")
	cfg.PingIntervalDur = parseDuration(cfg.PingInterval, "pingInterval")
	cfg.SplashDurationDur = parseDuration(cfg.Screen.SplashDuration, "screen.splashDuration")
	cfg.DVRDiskSpacePollDur = parseDuration(cfg.DVR.DiskSpacePoll, "dvr.diskSpacePoll")

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
