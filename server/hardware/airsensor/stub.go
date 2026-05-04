//go:build !linux

package airsensor

import (
	"log"
	"math/rand"
	"sync"
	"time"
)

// AirSensor is a stub that returns slowly drifting random readings.
type AirSensor struct {
	mu      sync.Mutex
	current Reading
}

func NewAirSensor() (*AirSensor, error) {
	log.Println("airsensor: Hardware unavailable, using stub")
	s := &AirSensor{}
	s.current = s.randomReading()
	go s.drift()
	return s, nil
}

func (s *AirSensor) Read() (*Reading, error) {
	s.mu.Lock()
	r := s.current
	s.mu.Unlock()
	return &Reading{
		TempC:          round2(r.TempC),
		TempF:          round2(r.TempF),
		PressureInches: round2(r.PressureInches),
		PressureMeters: round2(r.PressureMeters),
		PressureFeet:   round2(r.PressureFeet),
		Humidity:       round2(r.Humidity),
		DewpointC:      round2(r.DewpointC),
		DewpointF:      round2(r.DewpointF),
	}, nil
}

func (s *AirSensor) randomReading() Reading {
	tempC := float32(20 + rand.Float32()*6) // 20–26 °C
	tempF := tempC*9/5 + 32
	humidity := float32(35 + rand.Float32()*30) // 35–65 %
	dewC := tempC - (100-humidity)/5            // rough approximation
	dewF := dewC*9/5 + 32
	pressurePa := float32(101000 + rand.Float32()*1000)
	return Reading{
		TempC:          tempC,
		TempF:          tempF,
		PressureInches: pressurePa / 3386.39,
		PressureMeters: (pressurePa - 101325) / -11.88,
		PressureFeet:   (pressurePa - 101325) / -11.88 * 3.28084,
		Humidity:       humidity,
		DewpointC:      dewC,
		DewpointF:      dewF,
	}
}

func (s *AirSensor) drift() {
	for {
		// Update every 1–10 seconds.
		time.Sleep(time.Duration(1+rand.Intn(10)) * time.Second)
		next := s.randomReading()
		s.mu.Lock()
		cur := s.current
		// Blend: move 10% toward the new random target so values drift, not jump.
		s.current = Reading{
			TempC:          cur.TempC + (next.TempC-cur.TempC)*0.1,
			TempF:          cur.TempF + (next.TempF-cur.TempF)*0.1,
			PressureInches: cur.PressureInches + (next.PressureInches-cur.PressureInches)*0.1,
			PressureMeters: cur.PressureMeters + (next.PressureMeters-cur.PressureMeters)*0.1,
			PressureFeet:   cur.PressureFeet + (next.PressureFeet-cur.PressureFeet)*0.1,
			Humidity:       cur.Humidity + (next.Humidity-cur.Humidity)*0.1,
			DewpointC:      cur.DewpointC + (next.DewpointC-cur.DewpointC)*0.1,
			DewpointF:      cur.DewpointF + (next.DewpointF-cur.DewpointF)*0.1,
		}
		s.mu.Unlock()
	}
}
