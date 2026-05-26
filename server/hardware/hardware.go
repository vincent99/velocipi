package hardware

import (
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware/aircon"
	"github.com/vincent99/velocipi/server/hardware/airsensor"
	"github.com/vincent99/velocipi/server/hardware/expander"
	"github.com/vincent99/velocipi/server/hardware/g3x"
	"github.com/vincent99/velocipi/server/hardware/led"
	"github.com/vincent99/velocipi/server/hardware/lightsensor"
	"github.com/vincent99/velocipi/server/hardware/thermalcam"
	"github.com/vincent99/velocipi/server/hardware/tpms"
	"github.com/warthog618/go-gpiocdev"
)

var (
	resetOnce sync.Once
	resetLine *gpiocdev.Line // nil when ResetPin == 0

	airConOnce sync.Once
	airConUnit *aircon.Client

	airOnce   sync.Once
	airSensor *airsensor.AirSensor

	lightOnce   sync.Once
	lightSensor *lightsensor.LightSensor

	tpmsOnce sync.Once
	tpmsUnit *tpms.TPMS

	expanderOnce sync.Once
	expanderUnit *expander.Expander

	ledRedOnce    sync.Once
	ledRedUnit    *led.Controller
	ledWhiteOnce  sync.Once
	ledWhiteUnit  *led.Controller
	ledBlueOnce   sync.Once
	ledBlueUnit   *led.Controller
	ledYellowOnce sync.Once
	ledYellowUnit *led.Controller

	g3xOnce sync.Once
	g3xUnit *g3x.G3X

	thermalOnce sync.Once
	thermalUnit *thermalcam.ThermalCam
)

// resetLineInit opens the shared hardware reset GPIO line on first call.
// Returns nil (and logs) if ResetPin is 0 or the line cannot be opened.
func resetLineInit() *gpiocdev.Line {
	resetOnce.Do(func() {
		cfg := config.Load().Config
		if cfg.ResetPin == 0 {
			return
		}
		chip := cfg.OLED.GPIOChip
		if chip == "" {
			chip = "gpiochip0"
		}
		l, err := gpiocdev.RequestLine(chip, cfg.ResetPin,
			gpiocdev.AsOutput(1),
			gpiocdev.WithPullUp,
		)
		if err != nil {
			log.Printf("hardware: reset pin %d open error: %v", cfg.ResetPin, err)
			return
		}
		log.Printf("hardware: reset pin %d ready", cfg.ResetPin)
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

// AirCon returns the singleton AirCon BLE client, or nil if not configured.
func AirCon() *aircon.Client {
	airConOnce.Do(func() {
		cfg := config.Load().Config
		if cfg.AirCon.DeviceName == "" {
			return
		}
		c, err := aircon.New(aircon.Config{
			DeviceName:         cfg.AirCon.DeviceName,
			ServiceUUID:        cfg.AirCon.ServiceUUID,
			HistoryMinutes:     cfg.AirCon.HistoryMinutes,
			SampleIntervalSecs: cfg.AirCon.SampleIntervalSecs,
		})
		if err != nil {
			log.Println("hardware: aircon init error:", err)
			return
		}
		airConUnit = c
	})
	return airConUnit
}

func AirSensor() *airsensor.AirSensor {
	airOnce.Do(func() {
		s, err := airsensor.NewAirSensor()
		if err != nil {
			log.Println("hardware: airsensor init error:", err)
		}
		airSensor = s
	})
	return airSensor
}

func LightSensor() *lightsensor.LightSensor {
	lightOnce.Do(func() {
		s, err := lightsensor.NewLightSensor()
		if err != nil {
			log.Println("hardware: lightsensor init error:", err)
		}
		lightSensor = s
	})
	return lightSensor
}

func TPMS() *tpms.TPMS {
	tpmsOnce.Do(func() {
		cfg := config.Load().Config
		t, err := tpms.Listen(&cfg.Tires)
		if err != nil {
			log.Println("hardware: tpms init error:", err)
		}
		tpmsUnit = t
	})
	return tpmsUnit
}

func Expander() *expander.Expander {
	expanderOnce.Do(func() {
		cfg := config.Load().Config
		e, err := expander.New()
		if err != nil {
			log.Println("hardware: expander init error:", err)
			return
		}
		// All pins are inputs except the LED pin.
		outputs := uint16((1 << cfg.Expander.Bits.LEDR) | (1 << cfg.Expander.Bits.LEDW) | (1 << cfg.Expander.Bits.LEDB) | (1 << cfg.Expander.Bits.LEDY))
		inputs := uint16(0xFFFF) &^ outputs

		if err := e.Init(inputs); err != nil {
			log.Println("hardware: expander init error:", err)
			return
		}
		expanderUnit = e
	})
	return expanderUnit
}

// G3X returns the singleton G3X avionics state module.
func G3X() *g3x.G3X {
	g3xOnce.Do(func() {
		g3xUnit = g3x.New()
	})
	return g3xUnit
}

// ThermalCam returns the singleton thermal camera serial interface, or nil if not configured.
func ThermalCam() *thermalcam.ThermalCam {
	thermalOnce.Do(func() {
		cfg := config.Load().Config
		if cfg.Thermal.Device == "" {
			return
		}
		c, err := thermalcam.New(cfg.Thermal.Device)
		if err != nil {
			log.Println("hardware: thermalcam init error:", err)
			return
		}
		thermalUnit = c
		go func() {
			state, errs := c.ReadState(30 * time.Second)
			for _, err := range errs {
				log.Println("thermalcam:", err)
			}
			if state != nil {
				b, _ := json.Marshal(state)
				log.Printf("thermalcam: %s", b)
			}
		}()
	})
	return thermalUnit
}

func LEDRed() *led.Controller {
	ledRedOnce.Do(func() {
		ledRedUnit = led.New(config.Load().Config.Expander.Bits.LEDR)
	})
	return ledRedUnit
}

func LEDWhite() *led.Controller {
	ledWhiteOnce.Do(func() {
		ledWhiteUnit = led.New(config.Load().Config.Expander.Bits.LEDW)
	})
	return ledWhiteUnit
}

func LEDBlue() *led.Controller {
	ledBlueOnce.Do(func() {
		ledBlueUnit = led.New(config.Load().Config.Expander.Bits.LEDB)
	})
	return ledBlueUnit
}

func LEDYellow() *led.Controller {
	ledYellowOnce.Do(func() {
		ledYellowUnit = led.New(config.Load().Config.Expander.Bits.LEDY)
	})
	return ledYellowUnit
}
