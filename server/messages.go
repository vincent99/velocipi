package main

import (
	"github.com/vincent99/velocipi/server/hardware/aircon"
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

type RecordingReadyMsg struct {
	Type     string `json:"type"`     // always "recordingReady"
	Camera   string `json:"camera"`   // original camera name
	Session  string `json:"session"`  // session directory name
	Filename string `json:"filename"` // base filename without extension
}

type LocalCameraMsg struct {
	Type   string `json:"type"`   // always "localCamera"
	Camera string `json:"camera"` // current panel camera name
}

type G3XStateMsg struct {
	Type       string  `json:"type"` // always "g3xState"
	Lat        float64 `json:"lat"`
	Lon        float64 `json:"lon"`
	AltFt      float64 `json:"altFt"`
	Heading    float64 `json:"heading"`
	Roll       float64 `json:"roll"`
	Pitch      float64 `json:"pitch"`
	Yaw        float64 `json:"yaw"`
	SpeedKts   float64 `json:"speedKts"`
	OATCelsius float64 `json:"oatCelsius"`
}

type SiyiAttitudeMsg struct {
	Type      string  `json:"type"`   // always "siyiAttitude"
	Camera    string  `json:"camera"` // camera name
	Yaw       float32 `json:"yaw"`
	Pitch     float32 `json:"pitch"`
	Roll      float32 `json:"roll"`
	YawRate   float32 `json:"yawRate"`
	PitchRate float32 `json:"pitchRate"`
	RollRate  float32 `json:"rollRate"`
}

// AirConStateMsg broadcasts the current aircon state to all WS clients.
type AirConStateMsg struct {
	Type  string        `json:"type"` // always "airConState"
	State aircon.State  `json:"state"`
}

// AirConHistoryMsg sends the temperature history to a newly-connected client.
type AirConHistoryMsg struct {
	Type    string               `json:"type"` // always "airConHistory"
	History []aircon.TempSample  `json:"history"`
}

// Inbound message types from websocket clients.

type inboundMsg struct {
	Type string `json:"type"`
}

type inboundMusicControlMsg struct {
	Action string  `json:"action"`          // play|pause|stop|next|prev|seek|skipForward|skipBack|setVolume|setShuffle|setRepeat
	Value  float64 `json:"value,omitempty"` // seek: absolute sec; skipForward/skipBack: delta sec; setVolume: 0-100
	Str    string  `json:"str,omitempty"`   // setRepeat: "off"|"song"|"queue"
}

type inboundSetLocalCameraMsg struct {
	Camera string `json:"camera"`
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
