package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strconv"

	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/aircon"
)

// sendAirConState sends the current aircon state and history to a newly-connected client.
func (h *Hub) sendAirConState(c *client) {
	ac := hardware.AirCon()
	if ac == nil {
		return
	}
	data, err := json.Marshal(AirConStateMsg{Type: "airConState", State: ac.GetState()})
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}

	hist := ac.History()
	hdata, err := json.Marshal(AirConHistoryMsg{Type: "airConHistory", History: hist})
	if err != nil {
		return
	}
	select {
	case c.send <- hdata:
	default:
	}
}

// runAirConLoop starts the BLE client and broadcasts state changes to all WS clients.
func (h *Hub) runAirConLoop(ctx context.Context) {
	ac := hardware.AirCon()
	if ac == nil {
		log.Println("hub: aircon not configured, skipping")
		return
	}

	ac.OnChange(func(s aircon.State) {
		h.broadcastAll(AirConStateMsg{Type: "airConState", State: s})
	})

	ac.Run(ctx)
}

// registerAirConRoutes registers HTTP endpoints for writing aircon characteristics.
func registerAirConRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/aircon/set", airconSetHandler)
	mux.HandleFunc("/aircon/state", airconStateHandler)
}

// airconStateHandler returns the current aircon state and history as JSON.
func airconStateHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	ac := hardware.AirCon()
	if ac == nil {
		http.Error(w, "aircon not configured", http.StatusServiceUnavailable)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"state":   ac.GetState(),
		"history": ac.History(),
	})
}

// airconSetHandler writes a single characteristic. Body: {"field":"mode","value":"auto"}
func airconSetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	ac := hardware.AirCon()
	if ac == nil {
		http.Error(w, "aircon not configured", http.StatusServiceUnavailable)
		return
	}

	var body struct {
		Field string `json:"field"`
		Value string `json:"value"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "bad request: "+err.Error(), http.StatusBadRequest)
		return
	}

	var err error
	switch body.Field {
	case "mode":
		err = ac.SetMode(body.Value)
	case "fan":
		err = ac.SetFan(body.Value)
	case "setpoint":
		f, parseErr := strconv.ParseFloat(body.Value, 64)
		if parseErr != nil {
			http.Error(w, "invalid float value", http.StatusBadRequest)
			return
		}
		err = ac.SetSetpoint(f)
	case "circ":
		err = ac.SetCirculation(body.Value)
	case "panelTemp":
		f, parseErr := strconv.ParseFloat(body.Value, 64)
		if parseErr != nil {
			http.Error(w, "invalid float value", http.StatusBadRequest)
			return
		}
		err = ac.SetPanelTemp(f)
	case "delta":
		f, parseErr := strconv.ParseFloat(body.Value, 64)
		if parseErr != nil {
			http.Error(w, "invalid float value", http.StatusBadRequest)
			return
		}
		err = ac.SetDelta(f)
	default:
		http.Error(w, "unknown field: "+body.Field, http.StatusBadRequest)
		return
	}

	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
