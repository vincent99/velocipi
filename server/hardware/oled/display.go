package oled

import "image"

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
