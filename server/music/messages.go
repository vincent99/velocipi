package music

// MusicStateMsg is broadcast over WebSocket to all clients whenever the player
// state changes. It is also returned to newly-connected clients on join.
type MusicStateMsg struct {
	Type          string  `json:"type"`          // always "musicState"
	CurrentSongID *int64  `json:"currentSongId"` // nil when stopped
	QueueIndex    int     `json:"queueIndex"`
	Status        string  `json:"status"` // "playing" | "paused" | "stopped"
	Shuffle       bool    `json:"shuffle"`
	Repeat        string  `json:"repeat"` // "off" | "song" | "queue"
	ElapsedSec    float64 `json:"elapsedSec"`
	QueueLength   int     `json:"queueLength"`
}

// MusicQueueEntry is one entry in the pushed queue snapshot.
type MusicQueueEntry struct {
	SongID        int64 `json:"songId"`
	Song          *Song `json:"song"`
	OriginalIndex int   `json:"originalIndex"`
}

// MusicQueueMsg is broadcast whenever the queue contents or order change.
// Clients use this to replace their local queue state without polling.
type MusicQueueMsg struct {
	Type         string            `json:"type"` // always "musicQueue"
	CurrentIndex int               `json:"currentIndex"`
	Entries      []MusicQueueEntry `json:"entries"`
}
