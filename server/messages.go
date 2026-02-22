package main

import (
	"github.com/vincent99/velocipi/server/hardware/airsensor"
	"github.com/vincent99/velocipi/server/hardware/led"
	"github.com/vincent99/velocipi/server/hardware/tpms"
)

// Outbound message types. Each has a fixed Type field so the JSON consumer
// always knows exactly which fields will be present.

type PingMsg struct {
	Type string `json:"type"` // always "ping"
	Time string `json:"time"`
}

type AirReadingMsg struct {
	Type    string            `json:"type"` // always "airReading"
	Reading airsensor.Reading `json:"reading"`
}

type LuxReadingMsg struct {
	Type string  `json:"type"` // always "luxReading"
	Lux  float64 `json:"lux"`
}

type TpmsMsg struct {
	Type string     `json:"type"` // always "tpms"
	Tire *tpms.Tire `json:"tire"`
}

type LEDStateMsg struct {
	Type string `json:"type"`           // always "ledState"
	Mode string `json:"mode"`           // "off", "on", "blink"
	Rate int    `json:"rate,omitempty"` // blink rate in ms, only set when mode == "blink"
}

type KeyEchoMsg struct {
	Type      string `json:"type"`      // always "keyEcho"
	EventType string `json:"eventType"` // "keydown" or "keyup"
	Key       string `json:"key"`       // logical key name
}

// Inbound message types from websocket clients.

type inboundMsg struct {
	Type string `json:"type"`
}

type inboundKeyMsg struct {
	EventType string `json:"eventType"` // "keydown", "keyup", or "keypress"
	Key       string `json:"key"`
}

type inboundLEDMsg struct {
	State string `json:"state"`          // "off", "on", "blink"
	Rate  int    `json:"rate,omitempty"` // blink rate in ms, default 500
}

type inboundNavigateMsg struct {
	Path string `json:"path"` // URL path to navigate to, e.g. "/panel/test"
}

// ledStateMsg builds a LEDStateMsg from a led.State.
func ledStateMsg(s led.State) LEDStateMsg {
	msg := LEDStateMsg{Type: "ledState", Mode: s.Mode}
	if s.Mode == "blink" {
		msg.Rate = int(s.Rate.Milliseconds())
	}
	return msg
}
