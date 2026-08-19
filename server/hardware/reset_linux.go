//go:build linux

package hardware

import (
	"log"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/config"
	"github.com/warthog618/go-gpiocdev"
)

var (
	resetOnce sync.Once
	resetLine *gpiocdev.Line // nil when ResetPin == 0
)

// resetLineInit opens the shared hardware reset GPIO line on first call.
// Returns nil (and logs) if ResetPin is 0 or the line cannot be opened.
func resetLineInit() *gpiocdev.Line {
	resetOnce.Do(func() {
		cfg := config.Load().Config
		if cfg.Hardware.ResetPin == 0 {
			return
		}
		chip := cfg.Hardware.OLED.GPIOChip
		if chip == "" {
			chip = "gpiochip0"
		}
		l, err := gpiocdev.RequestLine(chip, cfg.Hardware.ResetPin,
			gpiocdev.AsOutput(1),
			gpiocdev.WithPullUp,
		)
		if err != nil {
			log.Printf("hardware: reset pin %d open error: %v", cfg.Hardware.ResetPin, err)
			return
		}
		log.Printf("hardware: reset pin %d ready", cfg.Hardware.ResetPin)
		resetLine = l
	})
	return resetLine
}

// Reset pulses the shared hardware reset pin low for dur, then high.
// Does nothing if no ResetPin is configured.
func Reset(dur time.Duration) {
	l := resetLineInit()
	if l == nil {
		return
	}
	if err := l.SetValue(0); err != nil {
		log.Println("hardware: reset low error:", err)
		return
	}
	time.Sleep(dur)
	if err := l.SetValue(1); err != nil {
		log.Println("hardware: reset high error:", err)
	}
}
