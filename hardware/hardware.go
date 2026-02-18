package hardware

import (
	"log"
	"sync"

	"github.com/vincent99/velocipi-go/config"
	"github.com/vincent99/velocipi-go/hardware/airsensor"
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
)

func AirSensor(cfg *config.Config) *airsensor.AirSensor {
	airOnce.Do(func() {
		s, err := airsensor.NewAirSensorWithOptions(&airsensor.Config{
			Address: cfg.AirSensorAddress,
			Device:  cfg.I2CDevice,
		})
		if err != nil {
			log.Println("hardware: airsensor init error:", err)
		}
		airSensor = s
	})
	return airSensor
}

func LightSensor(cfg *config.Config) *lightsensor.LightSensor {
	lightOnce.Do(func() {
		s, err := lightsensor.NewLightSensorWithOptions(&lightsensor.Config{
			Address: cfg.LightSensorAddress,
			Device:  cfg.I2CDevice,
		})
		if err != nil {
			log.Println("hardware: lightsensor init error:", err)
		}
		lightSensor = s
	})
	return lightSensor
}

func TPMS(cfg *config.Config) *tpms.TPMS {
	tpmsOnce.Do(func() {
		t, err := tpms.Listen(&cfg.Tires)
		if err != nil {
			log.Println("hardware: tpms init error:", err)
		}
		tpmsUnit = t
	})
	return tpmsUnit
}
