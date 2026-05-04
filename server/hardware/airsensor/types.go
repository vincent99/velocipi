package airsensor

import "math"

func round2(v float32) float32 {
	return float32(math.Round(float64(v)*100) / 100)
}

type Reading struct {
	TempC          float32 `json:"tempC"`
	TempF          float32 `json:"tempF"`
	PressureInches float32 `json:"pressureInches"`
	PressureMeters float32 `json:"pressureMeters"`
	PressureFeet   float32 `json:"pressureFeet"`
	Humidity       float32 `json:"humidity"`
	DewpointC      float32 `json:"dewpointC"`
	DewpointF      float32 `json:"dewpointF"`
}
