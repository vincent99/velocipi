package oled

import (
	"image"

	"periph.io/x/conn/v3/physic"
)

// Display is the common interface implemented by all OLED drivers.
type Display interface {
	// Blit converts img and writes it to the physical display.
	Blit(img image.Image)
	// SetBrightness sets display brightness. Range and semantics are
	// driver-specific (see each driver's SetBrightness doc).
	SetBrightness(b byte)
	// Width returns the display width in pixels.
	Width() int
	// Height returns the display height in pixels.
	Height() int
	// Close releases all hardware resources.
	Close()
}

// Config holds the hardware configuration for an OLED display.
type Config struct {
	// SPIPort is the spidev path, e.g. "/dev/spidev0.0".
	SPIPort string
	// SPISpeed is the SPI clock frequency.
	SPISpeed physic.Frequency
	// GPIOChip is the gpiochip device, e.g. "gpiochip0".
	GPIOChip string
	// StatusPin is the BCM GPIO line number for the status/auxiliary pin.
	// SSD1327: data/command select output (low=command, high=data).
	// Noritake GE256X64B: SBUSY input (high=busy, low=ready).
	StatusPin int
	// ResetPin is the BCM GPIO line number for the reset pin.
	ResetPin int
	// Flip reverses the frame buffer before writing (180° rotation).
	Flip bool
}
