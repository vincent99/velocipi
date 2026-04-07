package hardware

import (
	"log"
	"sync"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware/aircon"
	"github.com/vincent99/velocipi/server/hardware/airsensor"
	"github.com/vincent99/velocipi/server/hardware/expander"
	"github.com/vincent99/velocipi/server/hardware/g3x"
	"github.com/vincent99/velocipi/server/hardware/led"
	"github.com/vincent99/velocipi/server/hardware/lightsensor"
	"github.com/vincent99/velocipi/server/hardware/tpms"
)

var (
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

	ledOnce sync.Once
	ledUnit *led.Controller

	g3xOnce sync.Once
	g3xUnit *g3x.G3X
)

// AirCon returns the singleton AirCon BLE client, or nil if not configured.
func AirCon() *aircon.Client {
	airConOnce.Do(func() {
		cfg := config.Load().Config
		if cfg.AirCon.DeviceName == "" {
			return
		}
		c, err := aircon.New(aircon.Config{
			DeviceName:     cfg.AirCon.DeviceName,
			ServiceUUID:    cfg.AirCon.ServiceUUID,
			HistoryMinutes: cfg.AirCon.HistoryMinutes,
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
		inputs := uint16(0xFFFF) &^ (1 << cfg.Expander.Bits.LED)
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

// LED returns the singleton LED controller for the expander's LED pin.
func LED() *led.Controller {
	ledOnce.Do(func() {
		cfg := config.Load().Config
		ledUnit = led.New(cfg.Expander.Bits.LED)
	})
	return ledUnit
}
