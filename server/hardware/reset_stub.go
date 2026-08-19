//go:build !linux

package hardware

import (
	"log"
	"time"
)

// Reset is a stub on non-Linux platforms -- the shared hardware reset pin
// requires a real Linux GPIO character device (see reset_linux.go).
func Reset(_ time.Duration) {
	log.Println("hardware: reset pin unavailable, using stub")
}
