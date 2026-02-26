// Package music implements the music player subsystem: SQLite database,
// filesystem sync, audio playback via mpv, and HTTP API handlers.
package music

import "github.com/vincent99/velocipi/server/config"

// MusicConfig is an alias so sub-files in this package can reference it
// without importing config directly everywhere.
type MusicConfig = config.MusicConfig

// Broadcaster is satisfied by *hub.Hub in the main package, allowing the
// music player to broadcast WebSocket messages without an import cycle.
type Broadcaster interface {
	BroadcastAll(msg any)
}

// PlayerController is the interface exposed to the main package so that
// hub.go can dispatch inbound musicControl WebSocket messages without
// importing concrete player types.
type PlayerController interface {
	Control(msg ControlMsg)
	// StateMsg returns the current player state as a MusicStateMsg ready for broadcast.
	StateMsg() MusicStateMsg
	// QueueMsg returns the full queue snapshot as a MusicQueueMsg ready for broadcast.
	QueueMsg() MusicQueueMsg
}

// ControlMsg carries a player control action from a WebSocket client.
type ControlMsg struct {
	Action string  // play|pause|stop|next|prev|seek|skipForward|skipBack|setVolume|setShuffle|setRepeat
	Value  float64 // seek: absolute sec; skipForward/skipBack: delta sec; setVolume: 0-100
	Str    string  // setRepeat: "off"|"song"|"queue"
}
