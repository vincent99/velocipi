package main

import (
	"context"
	"encoding/json"
	"log"
	"math"
	"time"

	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/airsensor"
)

// sendReading sends the current air sensor reading to a single client.
func (h *Hub) sendReading(c *client) {
	s := hardware.AirSensor()
	if s == nil {
		return
	}
	r, err := s.Read()
	if err != nil {
		log.Println("hub: airsensor read error:", err)
		return
	}
	data, err := json.Marshal(AirReadingMsg{Type: "airReading", Reading: *r})
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// runAirSensorLoop polls the air sensor and broadcasts any changed reading
// to all connected clients.
func (h *Hub) runAirSensorLoop(ctx context.Context) {
	s := hardware.AirSensor()
	if s == nil {
		log.Println("hub: airsensor unavailable, skipping poll loop")
		return
	}

	ticker := time.NewTicker(h.cfg.AirSensorIntervalDur)
	defer ticker.Stop()

	var last *airsensor.Reading

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r, err := s.Read()
			if err != nil {
				log.Println("hub: airsensor read error:", err)
				continue
			}
			if last != nil && *r == *last {
				continue
			}
			last = r
			data, err := json.Marshal(AirReadingMsg{Type: "airReading", Reading: *r})
			if err != nil {
				continue
			}
			h.sendToClients(data, h.clients)
		}
	}
}

// sendLux sends the current ambient lux reading to a single client.
func (h *Hub) sendLux(c *client) {
	s := hardware.LightSensor()
	if s == nil {
		return
	}
	lux, err := s.GetAmbientLux()
	if err != nil {
		log.Println("hub: lightsensor read error:", err)
		return
	}
	data, err := json.Marshal(LuxReadingMsg{Type: "luxReading", Lux: lux})
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// runLightSensorLoop polls the light sensor and broadcasts any changed lux
// value to all connected clients.
func (h *Hub) runLightSensorLoop(ctx context.Context) {
	s := hardware.LightSensor()
	if s == nil {
		log.Println("hub: lightsensor unavailable, skipping poll loop")
		return
	}

	ticker := time.NewTicker(h.cfg.LightSensorIntervalDur)
	defer ticker.Stop()

	const threshold = 1.0 // lux change required to trigger a broadcast
	last := -1.0

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			lux, err := s.GetAmbientLux()
			if err != nil {
				log.Println("hub: lightsensor read error:", err)
				continue
			}
			if last >= 0 && math.Abs(lux-last) < threshold {
				continue
			}
			last = lux
			data, err := json.Marshal(LuxReadingMsg{Type: "luxReading", Lux: lux})
			if err != nil {
				continue
			}
			h.sendToClients(data, h.clients)
		}
	}
}

// sendTpms sends the current state of all known tires to a single client.
func (h *Hub) sendTpms(c *client) {
	t := hardware.TPMS()
	if t == nil {
		return
	}
	for _, tire := range t.Tires() {
		data, err := json.Marshal(TpmsMsg{Type: "tpms", Tire: tire})
		if err != nil {
			continue
		}
		select {
		case c.send <- data:
		default:
		}
	}
}

// runTpmsLoop listens for tire updates and broadcasts each change to all clients.
func (h *Hub) runTpmsLoop(ctx context.Context) {
	t := hardware.TPMS()
	if t == nil {
		log.Println("hub: tpms unavailable, skipping loop")
		return
	}

	for {
		select {
		case <-ctx.Done():
			return
		case tire := <-t.Updates():
			data, err := json.Marshal(TpmsMsg{Type: "tpms", Tire: tire})
			if err != nil {
				continue
			}
			h.sendToClients(data, h.clients)
		}
	}
}
