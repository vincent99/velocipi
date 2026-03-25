package music

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"sync"
	"time"
)

const mpvSocket = "/tmp/velocipi-mpv.sock"

// PlaybackStatus represents the current playback state.
type PlaybackStatus string

const (
	StatusStopped PlaybackStatus = "stopped"
	StatusPlaying PlaybackStatus = "playing"
	StatusPaused  PlaybackStatus = "paused"
)

// Player manages mpv and the playback queue.
type Player struct {
	mu          sync.Mutex
	db          *DB
	cfg         MusicConfig
	queue       *Queue
	broadcaster Broadcaster

	status        PlaybackStatus
	elapsedSec    float64
	currentSongID int64   // ID of the song currently loaded into mpv (0 = none)
	currentLength float64 // duration in seconds of the current song

	controlCh chan ControlMsg
}

// NewPlayer creates a Player. Call Run(ctx) in a goroutine to start it.
func NewPlayer(db *DB, cfg MusicConfig, bc Broadcaster) *Player {
	p := &Player{
		db:          db,
		cfg:         cfg,
		queue:       NewQueue(),
		broadcaster: bc,
		status:      StatusStopped,
		controlCh:   make(chan ControlMsg, 16),
	}
	p.restore()
	return p
}

// Control sends a control message to the player (non-blocking).
func (p *Player) Control(msg ControlMsg) {
	select {
	case p.controlCh <- msg:
	default:
	}
}

// StateMsg returns a snapshot suitable for WebSocket broadcast.
func (p *Player) StateMsg() MusicStateMsg {
	p.mu.Lock()
	status := string(p.status)
	elapsed := p.elapsedSec
	p.mu.Unlock()

	qs := p.queue.State()
	msg := MusicStateMsg{
		Type:        "musicState",
		QueueIndex:  qs.CurrentIndex,
		Status:      status,
		Shuffle:     qs.Shuffle,
		Repeat:      string(qs.Repeat),
		ElapsedSec:  elapsed,
		QueueLength: len(qs.Entries),
	}
	if len(qs.Entries) > 0 && qs.CurrentIndex >= 0 && qs.CurrentIndex < len(qs.Entries) {
		id := qs.Entries[qs.CurrentIndex].SongID
		msg.CurrentSongID = &id
	}
	return msg
}

// QueueSnapshot returns the current queue state for API responses.
func (p *Player) QueueSnapshot() QueueState {
	return p.queue.State()
}

// Run is the main player loop. It blocks until ctx is cancelled.
func (p *Player) Run(ctx context.Context) {
	if _, err := exec.LookPath("mpv"); err != nil {
		log.Println("music: mpv not found in PATH — audio playback disabled")
		<-ctx.Done()
		return
	}

	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	// cancelMpv cancels the context passed to the currently running mpv goroutine.
	var cancelMpv context.CancelFunc
	// mpvDone receives the error (or nil) when mpv exits.
	var mpvDone chan error

	// startCurrent launches mpv for the song at the current queue position.
	// If no song is available, stops playback.
	startCurrent := func() {
		songID, currentIdx, ok := p.queue.Current()
		if !ok {
			if cancelMpv != nil {
				cancelMpv()
				cancelMpv = nil
				mpvDone = nil
			}
			p.mu.Lock()
			p.status = StatusStopped
			p.elapsedSec = 0
			p.currentSongID = 0
			p.currentLength = 0
			p.mu.Unlock()
			p.saveState()
			p.broadcast()
			return
		}

		var path string
		var length float64
		err := p.db.db.QueryRow(`SELECT path, length FROM song WHERE id=? AND deleted IS NULL`, songID).Scan(&path, &length)
		if err != nil || func() bool { _, e := os.Stat(path); return e != nil }() {
			log.Printf("music: song %d unavailable — removing from queue: %v", songID, err)
			p.queue.RemoveAt(currentIdx)
			p.saveState()
			p.broadcast()
			p.broadcastQueue()
			if p.queue.Len() > 0 {
				// Recurse via controlCh to avoid stack overflow on long runs of bad files.
				p.controlCh <- ControlMsg{Action: "_startCurrent"}
			} else {
				p.mu.Lock()
				p.status = StatusStopped
				p.elapsedSec = 0
				p.currentSongID = 0
				p.currentLength = 0
				p.mu.Unlock()
				p.saveState()
				p.broadcast()
			}
			return
		}

		if cancelMpv != nil {
			cancelMpv()
		}
		mpvCtx, cancel := context.WithCancel(ctx)
		cancelMpv = cancel
		done := make(chan error, 1)
		mpvDone = done

		p.mu.Lock()
		p.status = StatusPlaying
		p.elapsedSec = 0
		p.currentSongID = songID
		p.currentLength = length
		p.mu.Unlock()
		p.saveState()
		p.broadcast()

		go func() {
			done <- runMpv(mpvCtx, path, p.cfg.Volume, p.cfg.AudioDevice)
		}()
	}

	// killMpv stops the running mpv process and clears state.
	killMpv := func() {
		if cancelMpv != nil {
			cancelMpv()
			cancelMpv = nil
			mpvDone = nil
		}
	}

	for {
		select {
		case <-ctx.Done():
			killMpv()
			p.saveState()
			return

		case err := <-mpvDone:
			mpvDone = nil
			cancelMpv = nil
			if err != nil && ctx.Err() == nil {
				log.Println("music: mpv exited:", err)
			}
			// Song played to natural end — count as a full play.
			p.mu.Lock()
			finishedID := p.currentSongID
			p.mu.Unlock()
			p.incrementPlays(finishedID)
			if _, ok := p.queue.Advance(); ok {
				p.broadcastQueue()
				startCurrent()
			} else {
				p.mu.Lock()
				p.status = StatusStopped
				p.elapsedSec = 0
				p.currentSongID = 0
				p.currentLength = 0
				p.mu.Unlock()
				p.saveState()
				p.broadcast()
			}

		case msg := <-p.controlCh:
			switch msg.Action {
			case "_startCurrent":
				startCurrent()

			case "play":
				p.mu.Lock()
				isPlaying := p.status == StatusPlaying
				isPaused := p.status == StatusPaused
				p.mu.Unlock()
				if isPlaying {
					break
				}
				if isPaused && cancelMpv != nil {
					// Resume paused mpv.
					if err := mpvCommand(`{ "command": ["set_property", "pause", false] }`); err != nil {
						log.Println("music: mpv resume:", err)
					}
					p.mu.Lock()
					p.status = StatusPlaying
					p.mu.Unlock()
					p.saveState()
					p.broadcast()
				} else {
					startCurrent()
				}

			case "pause":
				p.mu.Lock()
				if p.status == StatusPlaying {
					p.status = StatusPaused
				}
				p.mu.Unlock()
				if err := mpvCommand(`{ "command": ["set_property", "pause", true] }`); err != nil {
					log.Println("music: mpv pause:", err)
				}
				p.saveState()
				p.broadcast()

			case "stop":
				killMpv()
				p.mu.Lock()
				p.status = StatusStopped
				p.elapsedSec = 0
				p.mu.Unlock()
				p.saveState()
				p.broadcast()

			case "next":
				p.countPlayIfHalfway()
				killMpv()
				if _, ok := p.queue.Advance(); ok {
					p.broadcastQueue()
					startCurrent()
				} else {
					p.mu.Lock()
					p.status = StatusStopped
					p.elapsedSec = 0
					p.currentSongID = 0
					p.currentLength = 0
					p.mu.Unlock()
					p.saveState()
					p.broadcast()
				}

			case "prev":
				p.countPlayIfHalfway()
				killMpv()
				if _, ok := p.queue.Prev(); ok {
					p.broadcastQueue()
					startCurrent()
				}

			case "jumpToIndex":
				p.countPlayIfHalfway()
				if p.queue.JumpTo(int(msg.Value)) {
					killMpv()
					p.mu.Lock()
					p.elapsedSec = 0
					p.mu.Unlock()
					p.broadcastQueue()
					startCurrent()
					p.saveState()
					p.broadcast()
				}

			case "seek":
				p.mu.Lock()
				p.elapsedSec = msg.Value
				p.mu.Unlock()
				cmd := fmt.Sprintf(`{ "command": ["seek", %.3f, "absolute"] }`, msg.Value)
				if err := mpvCommand(cmd); err != nil {
					log.Println("music: mpv seek:", err)
				}
				p.saveState()
				p.broadcast()

			case "skipForward":
				p.mu.Lock()
				p.elapsedSec += msg.Value
				p.mu.Unlock()
				cmd := fmt.Sprintf(`{ "command": ["seek", %.3f, "relative"] }`, msg.Value)
				if err := mpvCommand(cmd); err != nil {
					log.Println("music: mpv skipForward:", err)
				}
				p.saveState()
				p.broadcast()

			case "skipBack":
				p.mu.Lock()
				p.elapsedSec -= msg.Value
				if p.elapsedSec < 0 {
					p.elapsedSec = 0
				}
				p.mu.Unlock()
				cmd := fmt.Sprintf(`{ "command": ["seek", %.3f, "relative"] }`, -msg.Value)
				if err := mpvCommand(cmd); err != nil {
					log.Println("music: mpv skipBack:", err)
				}
				p.saveState()
				p.broadcast()

			case "setVolume":
				p.cfg.Volume = int(msg.Value)
				cmd := fmt.Sprintf(`{ "command": ["set_property", "volume", %.0f] }`, msg.Value)
				if err := mpvCommand(cmd); err != nil {
					log.Println("music: mpv setVolume:", err)
				}

			case "setShuffle":
				on := msg.Str == "true"
				p.queue.SetShuffle(on)
				p.saveState()
				p.broadcast()
				p.broadcastQueue()

			case "setRepeat":
				p.queue.SetRepeat(RepeatMode(msg.Str))
				p.saveState()
				p.broadcast()

			case "undoQueueChange":
				if p.queue.UndoChange() {
					p.broadcastQueue()
					p.saveState()
					p.broadcast()
				}

			case "replace":
				var ids []int64
				if err := json.Unmarshal([]byte(msg.Str), &ids); err == nil {
					p.queue.Replace(ids)
				}
				p.broadcastQueue()
				killMpv()
				startCurrent()

			case "enqueue":
				var ids []int64
				if err := json.Unmarshal([]byte(msg.Str), &ids); err == nil {
					p.queue.EnqueueAfterCurrent(ids)
				}
				p.saveState()
				p.broadcast()
				p.broadcastQueue()

			case "append":
				var ids []int64
				if err := json.Unmarshal([]byte(msg.Str), &ids); err == nil {
					p.queue.Append(ids)
				}
				p.saveState()
				p.broadcast()
				p.broadcastQueue()
			}

		case <-ticker.C:
			p.mu.Lock()
			if p.status == StatusPlaying {
				p.elapsedSec++
			}
			elapsed := p.elapsedSec
			p.mu.Unlock()
			p.broadcast()
			if int(elapsed)%5 == 0 {
				p.db.SetState("player.elapsedSec", elapsed)
			}
		}
	}
}

// broadcast sends the current state to all WebSocket clients.
func (p *Player) broadcast() {
	if p.broadcaster != nil {
		p.broadcaster.BroadcastAll(p.StateMsg())
	}
}

// QueueMsg builds a full MusicQueueMsg with song details for each entry.
func (p *Player) QueueMsg() MusicQueueMsg {
	qs := p.queue.State()
	msg := MusicQueueMsg{
		Type:         "musicQueue",
		CurrentIndex: qs.CurrentIndex,
		Entries:      make([]MusicQueueEntry, 0, len(qs.Entries)),
	}
	for _, e := range qs.Entries {
		entry := MusicQueueEntry{SongID: e.SongID, OriginalIndex: e.OriginalIndex}
		rows, err := p.db.db.Query(
			`SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate FROM song WHERE id=?`,
			e.SongID,
		)
		if err == nil {
			if rows.Next() {
				if s, err := scanSong(rows); err == nil {
					entry.Song = s
				}
			}
			rows.Close()
		}
		msg.Entries = append(msg.Entries, entry)
	}
	return msg
}

// broadcastQueue sends the full queue snapshot to all WebSocket clients.
func (p *Player) broadcastQueue() {
	if p.broadcaster != nil {
		p.broadcaster.BroadcastAll(p.QueueMsg())
	}
}

// saveState persists individual state keys to SQLite.
func (p *Player) saveState() {
	p.mu.Lock()
	status := p.status
	elapsed := p.elapsedSec
	p.mu.Unlock()

	qs := p.queue.State()
	p.db.SetState("player.status", string(status))
	p.db.SetState("player.elapsedSec", elapsed)
	p.db.SetState("player.shuffle", qs.Shuffle)
	p.db.SetState("player.repeat", string(qs.Repeat))
	p.db.SetState("player.queueEntries", qs.Entries)
	p.db.SetState("player.queueIndex", qs.CurrentIndex)
}

// incrementPlays increments the plays counter for the given song.
func (p *Player) incrementPlays(songID int64) {
	if songID <= 0 {
		return
	}
	if _, err := p.db.db.Exec(`UPDATE song SET plays=plays+1 WHERE id=?`, songID); err != nil {
		log.Printf("music: increment plays for song %d: %v", songID, err)
	}
}

// countPlayIfHalfway increments the play count for the song that is currently
// loaded if the required percentage of its duration has elapsed.
func (p *Player) countPlayIfHalfway() {
	p.mu.Lock()
	songID := p.currentSongID
	elapsed := p.elapsedSec
	length := p.currentLength
	p.mu.Unlock()
	pct := p.cfg.PlayedRequiredPercent
	if pct <= 0 {
		pct = 50
	}
	threshold := length * float64(pct) / 100.0
	if songID > 0 && length > 0 && elapsed >= threshold {
		p.incrementPlays(songID)
	}
}

// restore loads player state from SQLite on startup.
func (p *Player) restore() {
	var status string
	var elapsed float64
	var shuffle bool
	var repeat string
	var entries []QueueEntry
	var queueIndex int

	p.db.GetState("player.status", &status)
	p.db.GetState("player.elapsedSec", &elapsed)
	p.db.GetState("player.shuffle", &shuffle)
	p.db.GetState("player.repeat", &repeat)
	p.db.GetState("player.queueEntries", &entries)
	p.db.GetState("player.queueIndex", &queueIndex)

	if entries == nil {
		entries = []QueueEntry{}
	}

	p.queue.Restore(QueueState{
		Entries:      entries,
		CurrentIndex: queueIndex,
		Shuffle:      shuffle,
		Repeat:       RepeatMode(repeat),
	})

	p.mu.Lock()
	// Start paused (not playing) on restore.
	if PlaybackStatus(status) == StatusPlaying {
		p.status = StatusPaused
	} else if status != "" {
		p.status = PlaybackStatus(status)
	}
	p.elapsedSec = elapsed
	p.mu.Unlock()
}

// runMpv launches mpv for the given file and waits for it to finish.
func runMpv(ctx context.Context, path string, volume int, audioDevice string) error {
	args := []string{
		"--no-video",
		"--gapless-audio=yes",
		fmt.Sprintf("--volume=%d", volume),
		"--input-ipc-server=" + mpvSocket,
		"--input-terminal=no",
		"--really-quiet",
	}
	if audioDevice != "" && audioDevice != "auto" {
		args = append(args, "--audio-device="+audioDevice)
	}
	args = append(args, path)
	cmd := exec.CommandContext(ctx, "mpv", args...)
	return cmd.Run()
}

// mpvCommand sends a JSON IPC command to the running mpv instance.
func mpvCommand(jsonCmd string) error {
	conn, err := net.Dial("unix", mpvSocket)
	if err != nil {
		return err
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(500 * time.Millisecond))
	_, err = fmt.Fprintf(conn, "%s\n", jsonCmd)
	return err
}
