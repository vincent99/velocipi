// Package lcd controls the Raspberry Pi's own built-in LCD backlight via
// sysfs (the standard Linux backlight-class driver interface). Split out of
// hardware/brightness, which used to own this device directly -- brightness
// is now a generic percentage engine any number of subscribers (this one,
// hardware/knob, ...) can drive their own hardware from.
package lcd

import (
	"math"
	"os"
	"path"
	"strconv"
	"strings"
)

// DefaultDevice is used when Config.Device is empty.
const DefaultDevice = "/sys/class/backlight/10-0045"

const (
	brightnessFile    = "brightness"
	maxBrightnessFile = "max_brightness"
)

type Config struct {
	Device string
	// MinBrightness/MaxBrightness are in this device's own raw sysfs
	// brightness units (not a percentage) -- MaxBrightness of 0 means
	// "read it from the device tree via sysfs's own max_brightness file"
	// rather than requiring it be hardcoded here, since it varies by panel.
	MinBrightness int
	MaxBrightness int
}

type LCD struct {
	device        string
	minBrightness int
	maxBrightness int
	current       int
}

// New opens/validates the backlight device, reading MaxBrightness from
// sysfs if not given explicitly.
func New(cfg Config) (*LCD, error) {
	dev := cfg.Device
	if dev == "" {
		dev = DefaultDevice
	}

	minBrightness := cfg.MinBrightness
	if minBrightness == 0 {
		minBrightness = 1
	}

	maxBrightness := cfg.MaxBrightness
	if maxBrightness == 0 {
		raw, err := os.ReadFile(path.Join(dev, maxBrightnessFile))
		if err != nil {
			return nil, err
		}
		val, err := strconv.Atoi(strings.TrimSpace(string(raw)))
		if err != nil {
			return nil, err
		}
		maxBrightness = val
	}

	return &LCD{
		device:        dev,
		minBrightness: minBrightness,
		maxBrightness: maxBrightness,
	}, nil
}

// Set maps a 0-100 percentage onto this device's own raw brightness range
// (floored at MinBrightness, capped at MaxBrightness) and writes it to sysfs.
func (l *LCD) Set(pct float64) error {
	if pct < 0 {
		pct = 0
	} else if pct > 100 {
		pct = 100
	}
	raw := l.minBrightness + int(math.Round(float64(l.maxBrightness-l.minBrightness)*pct/100.0))
	err := os.WriteFile(path.Join(l.device, brightnessFile), []byte(strconv.Itoa(raw)), 0600)
	if err == nil {
		l.current = raw
	}
	return err
}

// Current returns the last raw brightness value successfully written.
func (l *LCD) Current() int {
	return l.current
}
