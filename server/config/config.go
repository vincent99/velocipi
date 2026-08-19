package config

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	"periph.io/x/conn/v3/physic"
)

// configDir is the directory holding config.default.yaml / config.yaml. It
// defaults to "." (the process working directory) to preserve prior behavior;
// override it once at startup via SetDir (wired to the -config flag in main).
var configDir = "."

// SetDir sets the directory Load and SaveOverrides read/write config files in.
// Call it before the first Load().
func SetDir(dir string) {
	if dir != "" {
		configDir = dir
	}
}

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
	DVR           string `yaml:"dvr"           json:"dvr"`           // recordings directory; default "recordings"
	Music         string `yaml:"music"         json:"music"`         // music library root; default "music"
	Backup        string `yaml:"backup"        json:"backup"`        // database backup directory; default "backup"
	Snaps         string `yaml:"snaps"         json:"snaps"`         // downloaded camera snaps/photos; default "snaps"
	LiveATC       string `yaml:"liveatc"       json:"liveatc"`       // liveatc audio/transcripts root (used by the intercom-stt process)
	WeightBalance string `yaml:"weightBalance" json:"weightBalance"` // weight & balance people/layouts/saved records root
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
	HeaderColor      string        `yaml:"headerColor"      json:"headerColor"`
	AdminHeaderColor string        `yaml:"adminHeaderColor" json:"adminHeaderColor"`
	Antialiasing     bool          `yaml:"antialiasing"     json:"antialiasing"`
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
	KnobInnerA uint `yaml:"knobInnerA" json:"knobInnerA"` // quadrature A
	KnobInnerB uint `yaml:"knobInnerB" json:"knobInnerB"` // quadrature B
	KnobOuterA uint `yaml:"knobOuterA" json:"knobOuterA"` // quadrature A
	KnobOuterB uint `yaml:"knobOuterB" json:"knobOuterB"` // quadrature B
	LEDR       uint `yaml:"ledR"       json:"ledR"`
	LEDW       uint `yaml:"ledW"       json:"ledW"`
	LEDB       uint `yaml:"ledB"       json:"ledB"`
	LEDY       uint `yaml:"ledY"       json:"ledY"`
	JoyCenter  uint `yaml:"joyCenter"  json:"joyCenter"`
	JoyDown    uint `yaml:"joyDown"    json:"joyDown"`
	JoyUp      uint `yaml:"joyUp"      json:"joyUp"`
	JoyRight   uint `yaml:"joyRight"   json:"joyRight"`
	JoyLeft    uint `yaml:"joyLeft"    json:"joyLeft"`
	JoyKnobA   uint `yaml:"joyKnobA"   json:"joyKnobA"` // quadrature A
	JoyKnobB   uint `yaml:"joyKnobB"   json:"joyKnobB"` // quadrature B
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

// ThermalConfig holds settings for the thermal camera serial interface.
type ThermalConfig struct {
	// Device is the path to the serial device (e.g. "/dev/ttyUSB0").
	// If empty, the thermal camera subsystem is disabled.
	Device string `yaml:"device" json:"device"`
}

// AirConConfig holds settings for the aircon state/command relay
// (hardware/aircon) -- transport is the knob's serial link (see
// KnobConfig); the aircon subsystem is enabled/disabled by whether the
// knob itself is configured, not by anything here.
type AirConConfig struct {
	// HistoryMinutes is how many minutes of temperature data to keep in memory.
	HistoryMinutes int `yaml:"historyMinutes" json:"historyMinutes"`
	// SampleIntervalSecs is how often a temperature sample is recorded. Defaults to 10.
	SampleIntervalSecs int `yaml:"sampleIntervalSecs" json:"sampleIntervalSecs"`
}

// AxisConfig holds settings for the Axis (formerly G3X) avionics module.
// Currently unused by hardware/axis, which only generates mock data --
// present here so the config key isn't silently swallowed once a real
// serial/UDP/BT feed replaces the mock.
type AxisConfig struct {
	Device string `yaml:"device" json:"device"`
}

// BrightnessConfig holds settings for the ambient-light-driven brightness
// engine (hardware/brightness), shared by every subscriber (LCD, knob, ...).
type BrightnessConfig struct {
	Delay  string  `yaml:"delay"  json:"delay"`  // debounce/average window, e.g. "2s"
	Speed  string  `yaml:"speed"  json:"speed"`  // ramp duration when the target percentage changes, e.g. "2s"
	MinLux float64 `yaml:"minLux" json:"minLux"` // lux at/below which brightness is 0%
	MaxLux float64 `yaml:"maxLux" json:"maxLux"` // lux at/above which brightness is 100%
}

// LCDConfig holds settings for the Pi's own built-in LCD backlight.
type LCDConfig struct {
	Device        string `yaml:"device"        json:"device"`        // sysfs backlight device path; empty = hardware/lcd's own default
	MinBrightness int    `yaml:"minBrightness" json:"minBrightness"` // raw device units, floor
	MaxBrightness int    `yaml:"maxBrightness" json:"maxBrightness"` // raw device units; 0 = read from sysfs max_brightness
}

// KnobConfig holds settings for the AC control knob's serial connection.
type KnobConfig struct {
	Device        string `yaml:"device"        json:"device"`        // serial device path
	MinBrightness int    `yaml:"minBrightness" json:"minBrightness"` // 0-100, floor
	MaxBrightness int    `yaml:"maxBrightness" json:"maxBrightness"` // 0-100, ceiling
}

// HardwareConfig groups all the physical-hardware wiring config: bus devices,
// the shared reset pin, and each attached peripheral.
type HardwareConfig struct {
	I2CDevice   string         `yaml:"i2cDevice"   json:"i2cDevice"`
	SPIDevice   string         `yaml:"spiDevice"   json:"spiDevice"`
	ResetPin    int            `yaml:"resetPin"    json:"resetPin"` // shared hardware reset GPIO pin; 0 = disabled
	AirSensor   SensorConfig   `yaml:"airSensor"   json:"airSensor"`
	Expander    ExpanderConfig `yaml:"expander"    json:"expander"`
	LightSensor SensorConfig   `yaml:"lightSensor" json:"lightSensor"`
	OLED        OLEDConfig     `yaml:"oled"        json:"oled"`
	Screen      ScreenConfig   `yaml:"screen"      json:"screen"`
	Axis        AxisConfig     `yaml:"axis"        json:"axis"`
	LCD         LCDConfig      `yaml:"lcd"         json:"lcd"`
	Knob        KnobConfig     `yaml:"knob"        json:"knob"`
	Thermal     ThermalConfig  `yaml:"thermal"     json:"thermal"`
}

// Config holds all runtime configuration.
type Config struct {
	Addr         string `yaml:"addr"         json:"addr"`
	TailNumber   string `yaml:"tailNumber"   json:"tailNumber"`
	PingInterval string `yaml:"pingInterval" json:"pingInterval"`

	Hardware   HardwareConfig   `yaml:"hardware"    json:"hardware"`
	Storage    StorageConfig    `yaml:"storage"     json:"storage"`
	DVR        DVRConfig        `yaml:"dvr"         json:"dvr"`
	Music      MusicConfig      `yaml:"music"       json:"music"`
	Tires      TireAddresses    `yaml:"tires"       json:"tires"`
	UI         UIConfig         `yaml:"ui"          json:"ui"`
	AirCon     AirConConfig     `yaml:"airCon"      json:"airCon"`
	Brightness BrightnessConfig `yaml:"brightness"  json:"brightness"`

	// Parsed values — not serialized, populated by Load()
	AppURL                 string           `yaml:"-" json:"-"` // http://localhost:<VELOCIPI_PORT>/panel/
	ExpanderIntervalDur    time.Duration    `yaml:"-" json:"-"`
	AirSensorIntervalDur   time.Duration    `yaml:"-" json:"-"`
	LightSensorIntervalDur time.Duration    `yaml:"-" json:"-"`
	PingIntervalDur        time.Duration    `yaml:"-" json:"-"`
	SplashDurationDur      time.Duration    `yaml:"-" json:"-"`
	DVRDiskSpacePollDur    time.Duration    `yaml:"-" json:"-"`
	BrightnessDelayDur     time.Duration    `yaml:"-" json:"-"`
	BrightnessSpeedDur     time.Duration    `yaml:"-" json:"-"`
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

	data, err := os.ReadFile(filepath.Join(configDir, "config.default.yaml"))
	if err != nil {
		log.Fatal("config: read error: ", err)
	}
	if err := yaml.Unmarshal(data, &defaults); err != nil {
		log.Fatal("config: parse error: ", err)
	}

	// Start with a copy of defaults, then layer overrides on top.
	cfg := defaults
	if ovData, err := os.ReadFile(filepath.Join(configDir, "config.yaml")); err == nil {
		if err := yaml.Unmarshal(ovData, &cfg); err != nil {
			log.Println("config: ignoring malformed config.yaml:", err)
		}
	}

	parseDurations(&cfg)
	parseDurations(&defaults)

	// Storage roots are interpreted relative to the config file's directory (made
	// absolute) so the data tree travels with the config regardless of the
	// process working directory. Resolve both cfg and defaults identically so
	// SaveOverrides doesn't see storage as a difference and persist it.
	absDir := storageDirAbs()
	resolveStoragePaths(&cfg, absDir)
	resolveStoragePaths(&defaults, absDir)

	// Build AppURL from VELOCIPI_PORT (default 8080).
	port := os.Getenv("VELOCIPI_PORT")
	if port == "" {
		port = "8080"
	}
	cfg.AppURL = "http://localhost:" + port + "/panel/"
	defaults.AppURL = cfg.AppURL

	return &LoadResult{Config: &cfg, Defaults: &defaults}
}

// storageDirAbs returns the absolute config directory (falling back to the raw
// configDir if it can't be resolved).
func storageDirAbs() string {
	if abs, err := filepath.Abs(configDir); err == nil {
		return abs
	}
	return configDir
}

// ResolveStorage rewrites cfg's storage paths to absolute under the config
// directory. Use it on a Config received from an external source (e.g. the admin
// UI, which is shown storage relative to the config -- see RelativizeStorage)
// before storing or using it, so internal paths stay absolute.
func ResolveStorage(cfg *Config) {
	resolveStoragePaths(cfg, storageDirAbs())
}

// RelativizeStorage returns a copy of cfg whose storage paths are expressed
// relative to the config directory when they live under it (left absolute
// otherwise). Used to present config to the admin UI. The input is unchanged.
func RelativizeStorage(cfg Config) Config {
	dir := storageDirAbs()
	v := reflect.ValueOf(&cfg.Storage).Elem()
	for i := 0; i < v.NumField(); i++ {
		f := v.Field(i)
		if f.Kind() != reflect.String || !f.CanSet() {
			continue
		}
		s := f.String()
		if s == "" || !filepath.IsAbs(s) {
			continue
		}
		// Only relativize paths under the config dir; anything outside (e.g. an
		// external SSD mount) stays absolute so it reads unambiguously.
		if rel, err := filepath.Rel(dir, s); err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			f.SetString(rel)
		}
	}
	return cfg
}

// resolveStoragePaths makes every path in the storage section absolute relative
// to cfgDir (the config file's directory) when it is given as a relative path.
// Reflection is used so all storage keys -- current and any added later -- are
// covered uniformly. Absolute and empty values are left untouched.
func resolveStoragePaths(cfg *Config, cfgDir string) {
	v := reflect.ValueOf(&cfg.Storage).Elem()
	for i := 0; i < v.NumField(); i++ {
		f := v.Field(i)
		if f.Kind() != reflect.String || !f.CanSet() {
			continue
		}
		if s := f.String(); s != "" && !filepath.IsAbs(s) {
			f.SetString(filepath.Join(cfgDir, s))
		}
	}
}

func parseDurations(cfg *Config) {
	cfg.ExpanderIntervalDur = parseDuration(cfg.Hardware.Expander.Interval, "hardware.expander.interval")
	cfg.AirSensorIntervalDur = parseDuration(cfg.Hardware.AirSensor.Interval, "hardware.airSensor.interval")
	cfg.LightSensorIntervalDur = parseDuration(cfg.Hardware.LightSensor.Interval, "hardware.lightSensor.interval")
	cfg.PingIntervalDur = parseDuration(cfg.PingInterval, "pingInterval")
	cfg.SplashDurationDur = parseDuration(cfg.Hardware.Screen.SplashDuration, "hardware.screen.splashDuration")
	cfg.DVRDiskSpacePollDur = parseDuration(cfg.DVR.DiskSpacePoll, "dvr.diskSpacePoll")
	cfg.BrightnessDelayDur = parseDuration(cfg.Brightness.Delay, "brightness.delay")
	cfg.BrightnessSpeedDur = parseDuration(cfg.Brightness.Speed, "brightness.speed")

	if err := cfg.OLEDSPIFreq.Set(cfg.Hardware.OLED.SPISpeed); err != nil {
		log.Fatalf("config: invalid hardware.oled.spiSpeed %q: %v", cfg.Hardware.OLED.SPISpeed, err)
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
	return os.WriteFile(filepath.Join(configDir, "config.yaml"), data, 0644)
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
