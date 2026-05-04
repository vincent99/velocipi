//go:build !linux

package lightsensor

import (
	"log"
	"math"
	"math/rand"
	"sync"
	"time"
)

// LightSensor is a stub that returns slowly drifting random lux readings.
type LightSensor struct {
	mu  sync.Mutex
	lux float64
}

func NewLightSensor() (*LightSensor, error) {
	log.Println("lightsensor: Hardware unavailable, using stub")
	s := &LightSensor{lux: 200 + rand.Float64()*600} // 200–800 lux
	go s.drift()
	return s, nil
}

func (s *LightSensor) GetAmbientLux() (float64, error) {
	s.mu.Lock()
	v := s.lux
	s.mu.Unlock()
	return math.Round(v*100) / 100, nil
}

func (s *LightSensor) GetWhiteLux() (float64, error) {
	return s.GetAmbientLux()
}

func (s *LightSensor) drift() {
	for {
		time.Sleep(time.Duration(1+rand.Intn(10)) * time.Second)
		target := 200 + rand.Float64()*600
		s.mu.Lock()
		s.lux = s.lux + (target-s.lux)*0.1
		s.mu.Unlock()
	}
}
