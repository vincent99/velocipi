package hardware

import (
	"log"
	"sync"

	"github.com/vincent99/velocipi-go/config"
	"github.com/vincent99/velocipi-go/hardware/airsensor"
	"github.com/vincent99/velocipi-go/hardware/expander"
	"github.com/vincent99/velocipi-go/hardware/lightsensor"
	"github.com/vincent99/velocipi-go/hardware/tpms"
)

var (
	airOnce   sync.Once
	airSensor *airsensor.AirSensor

	lightOnce   sync.Once
	lightSensor *lightsensor.LightSensor

	tpmsOnce sync.Once
	tpmsUnit *tpms.TPMS

	expanderOnce sync.Once
	expanderUnit *expander.Expander
)

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
		cfg := config.Load()
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
		cfg := config.Load()
		e, err := expander.New()
		if err != nil {
			log.Println("hardware: expander init error:", err)
			return
		}
		// All pins are inputs except the LED pin.
		inputs := uint16(0xFFFF) &^ (1 << cfg.BitLED)
		if err := e.Init(inputs); err != nil {
			log.Println("hardware: expander init error:", err)
			return
		}
		expanderUnit = e
	})
	return expanderUnit
}
