// Package dvr manages continuous recording of IP cameras to disk using ffmpeg.
// A single ffmpeg process per camera simultaneously writes archival MP4 segments,
// fans live MPEG-TS to browser viewers, and captures periodic JPEG thumbnails.
// All timestamps are UTC. Archival files are organised under per-day
// subdirectories: <recordingsDir>/<yyyy-mm-dd>/<yyyy-mm-dd_hh-mm-ss>_<cam>.mp4
package dvr

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/vincent99/velocipi/server/config"
)

// RecordingState is the DVR manager's recording mode.
type RecordingState string

const (
	RecordingOn     RecordingState = "on"
	RecordingPaused RecordingState = "paused"
	RecordingOff    RecordingState = "off"
)

const (
	// snapshotFPS is the thumbnail capture rate fed to ffmpeg's select filter.
	snapshotFPS = "1/5"
	// subscriberBuf is the channel depth for each MPEG-TS subscriber.
	// Slow browsers get dropped after the buffer fills rather than blocking
	// the broadcaster.
	subscriberBuf = 64
)

// broadcaster fans out []byte chunks to all current subscribers.
// Writes never block — subscribers whose channels are full are dropped.
type broadcaster struct {
	mu   sync.Mutex
	subs map[chan []byte]struct{}
}

func newBroadcaster() *broadcaster {
	return &broadcaster{subs: make(map[chan []byte]struct{})}
}

func (b *broadcaster) subscribe() chan []byte {
	ch := make(chan []byte, subscriberBuf)
	b.mu.Lock()
	b.subs[ch] = struct{}{}
	b.mu.Unlock()
	return ch
}

func (b *broadcaster) unsubscribe(ch chan []byte) {
	b.mu.Lock()
	delete(b.subs, ch)
	b.mu.Unlock()
}

func (b *broadcaster) send(data []byte) {
	b.mu.Lock()
	defer b.mu.Unlock()
	for ch := range b.subs {
		select {
		case ch <- data:
		default:
			// Subscriber too slow — drop it.
			delete(b.subs, ch)
			close(ch)
		}
	}
}

// frameEntry holds the latest snapshot for a camera and the subscribers waiting for the next one.
type frameEntry struct {
	mu   sync.Mutex
	data []byte // latest JPEG, nil until first capture
	// broadcast: close this channel to wake all waiters, then replace it.
	ready chan struct{}
}

func newFrameEntry() *frameEntry {
	return &frameEntry{ready: make(chan struct{})}
}

// latest returns the current frame data and a channel that closes when a newer
// frame is available.
func (f *frameEntry) latest() ([]byte, chan struct{}) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.data, f.ready
}

// publish stores a new frame and wakes all waiting goroutines.
func (f *frameEntry) publish(data []byte) {
	f.mu.Lock()
	f.data = data
	old := f.ready
	f.ready = make(chan struct{})
	f.mu.Unlock()
	close(old)
}

// liveCamera holds the live streaming state for one camera.
type liveCamera struct {
	ts    *broadcaster // MPEG-TS chunk fan-out
	frame *frameEntry  // latest JPEG thumbnail
}

// CameraStatusMsg is broadcast over WebSocket when a camera's recording state changes.
type CameraStatusMsg struct {
	Type      string `json:"type"`      // always "cameraStatus"
	Name      string `json:"name"`      // camera name (original, not sanitized)
	Recording bool   `json:"recording"` // true = actively recording
}

// DiskSpaceMsg is broadcast over WebSocket when disk space is polled.
type DiskSpaceMsg struct {
	Type    string  `json:"type"`    // always "diskSpace"
	TotalGB float64 `json:"totalGB"` // total disk space in GB
	UsedGB  float64 `json:"usedGB"`  // used disk space in GB
	FreeGB  float64 `json:"freeGB"`  // free disk space in GB
	UsedPct float64 `json:"usedPct"` // used percentage (0–100)
}

// DVRStateMsg is broadcast over WebSocket when the DVR recording state changes.
type DVRStateMsg struct {
	Type  string         `json:"type"`  // always "dvrState"
	State RecordingState `json:"state"` // "on", "paused", or "off"
}

// streamSession tracks the active camera and switch channel for one StreamActive connection.
type streamSession struct {
	activeCam    string
	switchNotify chan struct{}
}

// RecordingReadyMsg is broadcast over WebSocket when a segment's thumbnails
// have been written and the recording entry is ready to display.
type RecordingReadyMsg struct {
	Type     string `json:"type"`     // always "recordingReady"
	Camera   string `json:"camera"`   // original camera name
	Session  string `json:"session"`  // session directory name, e.g. "2026-02-23" or "2026-02-23-01"
	Filename string `json:"filename"` // base filename without extension
}

// Manager starts and supervises DVR recording for all configured cameras.
type Manager struct {
	mu               sync.RWMutex
	cfg              config.DVRConfig
	pollDur          time.Duration
	sessionDir       string                    // chosen at Start: {recordingsDir}/{yyyy-mm-dd[-NN]}
	live             map[string]*liveCamera    // sanitized name → live state
	recording        map[string]bool           // sanitized name → recording state
	sessions         map[string]*streamSession // clientID → per-connection state
	state            RecordingState            // overall recording state: on, paused, off
	lastDiskSpace    *DiskSpaceMsg             // most recent disk space reading
	onStatusChange   func(CameraStatusMsg)
	onRecordingReady func(RecordingReadyMsg)
	onDiskSpace      func(DiskSpaceMsg)
	onDVRState       func(DVRStateMsg)
}

// New creates a Manager. Call Start to begin recording.
func New(cfg config.DVRConfig, pollDur time.Duration) *Manager {
	live := make(map[string]*liveCamera, len(cfg.Cameras))
	for _, cam := range cfg.Cameras {
		live[sanitizeName(cam.Name)] = &liveCamera{
			ts:    newBroadcaster(),
			frame: newFrameEntry(),
		}
	}
	state := RecordingOff
	if len(cfg.Cameras) > 0 {
		if cfg.Record {
			state = RecordingOn
		} else {
			state = RecordingOff
		}
	}
	return &Manager{
		cfg:       cfg,
		pollDur:   pollDur,
		live:      live,
		recording: make(map[string]bool),
		sessions:  make(map[string]*streamSession),
		state:     state,
	}
}

// OnStatusChange registers a callback invoked whenever a camera's recording
// state changes. Must be called before Start.
func (m *Manager) OnStatusChange(fn func(CameraStatusMsg)) {
	m.onStatusChange = fn
}

// OnRecordingReady registers a callback invoked after a segment's thumbnails
// have been successfully written to disk. Must be called before Start.
func (m *Manager) OnRecordingReady(fn func(RecordingReadyMsg)) {
	m.onRecordingReady = fn
}

// OnDiskSpace registers a callback invoked whenever disk space is polled.
// Must be called before Start.
func (m *Manager) OnDiskSpace(fn func(DiskSpaceMsg)) {
	m.onDiskSpace = fn
}

// OnDVRState registers a callback invoked whenever the DVR recording state changes.
// Must be called before Start.
func (m *Manager) OnDVRState(fn func(DVRStateMsg)) {
	m.onDVRState = fn
}

// State returns the current DVR recording state.
func (m *Manager) State() RecordingState {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.state
}

// SetState transitions the DVR recording state and fires the callback.
// "off" → recordings and live streams are completely stopped (cameras still connect for live view).
// "paused" → live streaming continues but no MP4 files are written.
// "on" → full recording resumes.
func (m *Manager) SetState(s RecordingState) {
	m.mu.Lock()
	prev := m.state
	m.state = s
	m.mu.Unlock()
	if prev != s && m.onDVRState != nil {
		m.onDVRState(DVRStateMsg{Type: "dvrState", State: s})
	}
}

// LastDiskSpace returns the most recently polled disk space reading, or nil.
func (m *Manager) LastDiskSpace() *DiskSpaceMsg {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.lastDiskSpace
}

// CameraStatuses returns the current recording status of all configured cameras.
func (m *Manager) CameraStatuses() []CameraStatusMsg {
	msgs := make([]CameraStatusMsg, 0, len(m.cfg.Cameras))
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, cam := range m.cfg.Cameras {
		key := sanitizeName(cam.Name)
		msgs = append(msgs, CameraStatusMsg{
			Type:      "cameraStatus",
			Name:      cam.Name,
			Recording: m.recording[key],
		})
	}
	return msgs
}

// setRecording updates the recording state for a camera and fires the callback if changed.
func (m *Manager) setRecording(name, key string, recording bool) {
	m.mu.Lock()
	prev := m.recording[key]
	m.recording[key] = recording
	m.mu.Unlock()
	if prev != recording && m.onStatusChange != nil {
		m.onStatusChange(CameraStatusMsg{Type: "cameraStatus", Name: name, Recording: recording})
	}
}

// pickSessionDir selects a unique session directory name under root.
// It starts with "yyyy-mm-dd" and appends "-01", "-02", … until it finds a
// name that does not already exist, then creates and returns that directory.
func pickSessionDir(root string) (string, error) {
	base := time.Now().UTC().Format("2006-01-02")
	candidate := filepath.Join(root, base)
	if _, err := os.Stat(candidate); os.IsNotExist(err) {
		if err := os.MkdirAll(candidate, 0755); err != nil {
			return "", err
		}
		return candidate, nil
	}
	for i := 1; i <= 99; i++ {
		candidate = filepath.Join(root, fmt.Sprintf("%s-%02d", base, i))
		if _, err := os.Stat(candidate); os.IsNotExist(err) {
			if err := os.MkdirAll(candidate, 0755); err != nil {
				return "", err
			}
			return candidate, nil
		}
	}
	return "", fmt.Errorf("dvr: could not find a unique session directory under %s", root)
}

// SessionDir returns the session directory chosen at Start.
func (m *Manager) SessionDir() string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.sessionDir
}

// pollDiskSpace reads the filesystem stats for recordingsDir and broadcasts a DiskSpaceMsg.
func (m *Manager) pollDiskSpace() {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(m.cfg.RecordingsDir, &stat); err != nil {
		log.Println("dvr: disk space poll error:", err)
		return
	}
	total := float64(stat.Blocks) * float64(stat.Bsize)
	free := float64(stat.Bavail) * float64(stat.Bsize)
	used := total - float64(stat.Bfree)*float64(stat.Bsize)
	toGB := 1.0 / (1024 * 1024 * 1024)
	var usedPct float64
	if total > 0 {
		usedPct = used / total * 100
	}
	msg := DiskSpaceMsg{
		Type:    "diskSpace",
		TotalGB: total * toGB,
		UsedGB:  used * toGB,
		FreeGB:  free * toGB,
		UsedPct: usedPct,
	}
	m.mu.Lock()
	m.lastDiskSpace = &msg
	m.mu.Unlock()
	if m.onDiskSpace != nil {
		m.onDiskSpace(msg)
	}
}

// runDiskSpaceLoop polls disk space at the configured interval until ctx is cancelled.
func (m *Manager) runDiskSpaceLoop(ctx context.Context) {
	dur := m.pollDur
	if dur <= 0 {
		dur = time.Minute
	}
	m.pollDiskSpace() // immediate first poll
	ticker := time.NewTicker(dur)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			m.pollDiskSpace()
		}
	}
}

// Start launches the background recording loop for each camera.
// It returns immediately; all loops run until ctx is cancelled.
func (m *Manager) Start(ctx context.Context) {
	if len(m.cfg.Cameras) == 0 {
		return
	}
	if err := os.MkdirAll(m.cfg.RecordingsDir, 0755); err != nil {
		log.Println("dvr: cannot create recordings dir:", err)
		return
	}

	// Start disk space polling regardless of recording state.
	go m.runDiskSpaceLoop(ctx)

	// Broadcast initial DVR state.
	if m.onDVRState != nil {
		m.onDVRState(DVRStateMsg{Type: "dvrState", State: m.state})
	}

	if m.state == RecordingOff {
		log.Println("dvr: recording disabled, starting live-only camera loops")
	} else {
		dir, err := pickSessionDir(m.cfg.RecordingsDir)
		if err != nil {
			log.Println("dvr:", err)
			return
		}
		m.mu.Lock()
		m.sessionDir = dir
		m.mu.Unlock()
		log.Println("dvr: session dir:", dir)
	}

	for _, cam := range m.cfg.Cameras {
		go m.runCamera(ctx, cam)
	}
}

// segmentDur returns the configured segment duration, falling back to 600s.
func (m *Manager) segmentDur() int {
	if m.cfg.SegmentDuration > 0 {
		return m.cfg.SegmentDuration
	}
	return 600
}

// nextBoundary returns the UTC time of the next segment boundary at or after
// now, snapped to multiples of segSecs from the start of the current UTC day,
// but never crossing midnight (i.e. capped at the start of the next UTC day).
func nextBoundary(now time.Time, segSecs int) time.Time {
	now = now.UTC()
	midnight := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, time.UTC)
	seg := time.Duration(segSecs) * time.Second
	elapsed := now.Sub(time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC))
	next := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC).
		Add(((elapsed / seg) + 1) * seg)
	if next.After(midnight) {
		return midnight
	}
	return next
}

// makeFIFO creates a named pipe at path and returns any error.
func makeFIFO(path string) error {
	return syscall.Mkfifo(path, 0600)
}

// shouldRecord reports whether a camera should write MP4 files to disk.
// Nil means unset (default true); explicit false disables recording.
func shouldRecord(cam config.CameraConfig) bool {
	return cam.Record == nil || *cam.Record
}

// runCamera allocates per-camera resources (temp dir + FIFOs), starts reader
// goroutines for the live MPEG-TS and JPEG streams, then enters the recording loop.
func (m *Manager) runCamera(ctx context.Context, cam config.CameraConfig) {
	key := sanitizeName(cam.Name)

	tmpDir, err := os.MkdirTemp("", "velocipi-cam-"+key+"-")
	if err != nil {
		log.Printf("dvr[%s]: cannot create temp dir: %v", cam.Name, err)
		return
	}
	defer os.RemoveAll(tmpDir)

	tsFIFO := filepath.Join(tmpDir, "live.ts")
	jpegFIFO := filepath.Join(tmpDir, "snap.mjpeg")

	if err := makeFIFO(tsFIFO); err != nil {
		log.Printf("dvr[%s]: mkfifo ts: %v", cam.Name, err)
		return
	}
	if err := makeFIFO(jpegFIFO); err != nil {
		log.Printf("dvr[%s]: mkfifo jpeg: %v", cam.Name, err)
		return
	}

	lc := m.live[key]

	// openFIFO opens a named pipe for reading without blocking by using O_RDWR.
	// On Linux a FIFO opened O_RDWR never blocks (no need for a writer to be
	// present) and still delivers EOF/data correctly when the writer closes.
	openFIFO := func(path string) (*os.File, error) {
		return os.OpenFile(path, os.O_RDWR, os.ModeNamedPipe)
	}

	// readFIFOLoop opens the named pipe and calls fn with it. When fn returns
	// (EOF from ffmpeg finishing a segment), it reopens and calls fn again for
	// the next ffmpeg run. Exits when ctx is cancelled.
	readFIFOLoop := func(path string, fn func(*os.File)) {
		for {
			f, err := openFIFO(path)
			if err != nil {
				log.Printf("dvr[%s]: open fifo %s: %v", cam.Name, path, err)
				return
			}
			fn(f)
			f.Close()
			if ctx.Err() != nil {
				return
			}
		}
	}

	go readFIFOLoop(tsFIFO, func(f *os.File) {
		buf := make([]byte, 32*1024)
		for {
			n, err := f.Read(buf)
			if n > 0 {
				chunk := make([]byte, n)
				copy(chunk, buf[:n])
				lc.ts.send(chunk)
			}
			if err != nil {
				return
			}
		}
	})

	go readFIFOLoop(jpegFIFO, func(f *os.File) {
		splitJPEGs(f, lc.frame)
	})

	m.runLoop(ctx, cam, tsFIFO, jpegFIFO)
}

// splitJPEGs reads a concatenated MJPEG stream from r and publishes each
// complete JPEG frame (delimited by FF D8 ... FF D9) to fe.
func splitJPEGs(r io.Reader, fe *frameEntry) {
	br := bufio.NewReaderSize(r, 256*1024)
	var frame []byte
	inFrame := false

	for {
		b, err := br.ReadByte()
		if err != nil {
			return
		}
		if !inFrame {
			if b == 0xFF {
				next, err := br.ReadByte()
				if err != nil {
					return
				}
				if next == 0xD8 {
					frame = []byte{0xFF, 0xD8}
					inFrame = true
				}
			}
			continue
		}
		frame = append(frame, b)
		if len(frame) >= 4 && frame[len(frame)-2] == 0xFF && frame[len(frame)-1] == 0xD9 {
			fe.publish(frame)
			frame = nil
			inFrame = false
		}
	}
}

// thumbnailHeight returns the configured thumbnail height, falling back to 240px.
func (m *Manager) thumbnailHeight() int {
	if m.cfg.ThumbnailHeight > 0 {
		return m.cfg.ThumbnailHeight
	}
	return 240
}

// captureSegmentThumbs extracts the first frame of a finished MP4 segment as
// two JPEG files alongside the MP4: {base}_full.jpg (original resolution) and
// {base}_thumb.jpg (scaled to thumbnailHeight px tall).
// On success it fires the onRecordingReady callback.
func (m *Manager) captureSegmentThumbs(mp4File, cameraName string) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	base := strings.TrimSuffix(mp4File, ".mp4")
	h := fmt.Sprintf("%d", m.thumbnailHeight())

	thumbCmd := exec.CommandContext(ctx, "ffmpeg",
		"-i", mp4File,
		"-vf", "scale=-2:"+h,
		"-frames:v", "1",
		"-q:v", "2",
		"-y", base+"_thumb.jpg",
	)
	if err := thumbCmd.Run(); err != nil {
		log.Printf("dvr: thumb capture failed for %s: %v", mp4File, err)
		return
	}

	fullCmd := exec.CommandContext(ctx, "ffmpeg",
		"-i", mp4File,
		"-frames:v", "1",
		"-q:v", "2",
		"-y", base+"_full.jpg",
	)
	if err := fullCmd.Run(); err != nil {
		log.Printf("dvr: full capture failed for %s: %v", mp4File, err)
		return
	}

	if m.onRecordingReady != nil {
		// Derive session and filename from the mp4File path.
		// Path: {recordingsDir}/{session}/{filename}.mp4
		dir := filepath.Dir(mp4File)
		session := filepath.Base(dir)
		filename := strings.TrimSuffix(filepath.Base(mp4File), ".mp4")
		m.onRecordingReady(RecordingReadyMsg{
			Type:     "recordingReady",
			Camera:   cameraName,
			Session:  session,
			Filename: filename,
		})
	}

	// Enforce minimum free disk space by deleting oldest recordings.
	if m.cfg.MinFreeDisk > 0 {
		m.enforceMinFreeDisk()
	}
}

// enforceMinFreeDisk deletes the oldest recordings until at least MinFreeDisk GB is free.
// It re-polls disk space after each deletion and broadcasts updates.
func (m *Manager) enforceMinFreeDisk() {
	minFreeBytes := m.cfg.MinFreeDisk * 1024 * 1024 * 1024
	for {
		var stat syscall.Statfs_t
		if err := syscall.Statfs(m.cfg.RecordingsDir, &stat); err != nil {
			log.Println("dvr: disk space check error:", err)
			return
		}
		freeBytes := float64(stat.Bavail) * float64(stat.Bsize)
		if freeBytes >= minFreeBytes {
			return
		}

		// Find the oldest recording.
		recs, err := m.ListRecordings()
		if err != nil || len(recs) == 0 {
			log.Printf("dvr: minFreeDisk: %.1f GB free < %.1f GB required but no recordings to delete",
				freeBytes/1e9, m.cfg.MinFreeDisk)
			return
		}
		// ListRecordings returns sessions descending, time ascending.
		// The oldest is the last recording in the last (oldest) session, i.e. recs[len-1].
		oldest := recs[len(recs)-1]
		log.Printf("dvr: minFreeDisk: %.1f GB free < %.1f GB required, deleting %s/%s",
			freeBytes/1e9, m.cfg.MinFreeDisk, oldest.Session, oldest.Filename)
		if err := m.DeleteRecording(oldest.Session, oldest.Filename); err != nil {
			log.Printf("dvr: minFreeDisk: delete error: %v", err)
			return
		}
		// Re-poll and broadcast updated disk space.
		m.pollDiskSpace()
	}
}

// runLoop is the main per-camera restart loop. Each iteration:
//  1. Computes the UTC start time and determines the current day's subdir.
//  2. Calculates how many seconds until the next segment boundary (or midnight).
//  3. Runs a single ffmpeg with -t <duration> writing to:
//     - one MP4 file for archival (if recording is enabled for this camera)
//     - the MPEG-TS FIFO for live streaming
//     - the JPEG FIFO for thumbnail snapshots
//  4. On clean exit, captures first-frame thumbnails for the finished MP4.
//  5. On error, waits up to 5s then restarts.
func (m *Manager) runLoop(ctx context.Context, cam config.CameraConfig, tsFIFO, jpegFIFO string) {
	key := sanitizeName(cam.Name)
	segSecs := m.segmentDur()
	camRecord := shouldRecord(cam)

	defer m.setRecording(cam.Name, key, false)

	for {
		if ctx.Err() != nil {
			return
		}

		// Determine whether to write an MP4 this segment based on both
		// the per-camera record flag and the global DVR state.
		m.mu.RLock()
		dvrState := m.state
		sessDir := m.sessionDir
		m.mu.RUnlock()

		record := camRecord && dvrState == RecordingOn

		now := time.Now().UTC()
		boundary := nextBoundary(now, segSecs)

		// Ensure session dir exists when recording is active.
		if record && sessDir == "" {
			dir, err := pickSessionDir(m.cfg.RecordingsDir)
			if err != nil {
				log.Println("dvr:", err)
				record = false
			} else {
				m.mu.Lock()
				m.sessionDir = dir
				sessDir = dir
				m.mu.Unlock()
				log.Println("dvr: session dir:", dir)
			}
		}

		// Filename: {yyyy-mm-dd_hh-mm-ss}_{sanitized-cam-name}.mp4
		mp4File := filepath.Join(sessDir, fmt.Sprintf("%s_%s.mp4",
			now.Format("2006-01-02_15-04-05"), sanitizeName(cam.Name)))
		if record {
			log.Printf("dvr[%s]: starting → %s (until %s)", cam.Name, mp4File, boundary.Format("15:04:05Z"))
		}

		// ffmpeg writes two or three outputs from one input:
		//   0. (if record) MP4 file — stream-copy video + AAC audio
		//   1. MPEG-TS FIFO — stream-copy video for live browser streaming
		//   2. JPEG FIFO — decoded, scaled, 1/snapshotFPS fps thumbnails
		thumbFilter := fmt.Sprintf("[0:v]fps=%s,scale=-2:%d[vthumb]",
			snapshotFPS, m.thumbnailHeight())

		args := []string{
			"-rtsp_transport", "tcp",
			"-i", rtspURL(cam),
			"-filter_complex", thumbFilter,
		}

		if record {
			// Output 0: MP4 archival
			args = append(args, "-map", "0:v", "-c:v", "copy")
			if cam.Audio {
				args = append(args, "-map", "0:a?", "-c:a", "aac")
			}
			args = append(args,
				"-f", "mp4",
				"-movflags", "+faststart+empty_moov+default_base_moof",
				"-y", mp4File,
			)
		}

		// Output: MPEG-TS FIFO for live streaming
		args = append(args, "-map", "0:v", "-c:v", "copy")
		if cam.Audio {
			args = append(args, "-map", "0:a?", "-c:a", "aac")
		}
		args = append(args, "-f", "mpegts", tsFIFO)

		// Output: JPEG thumbnails
		args = append(args,
			"-map", "[vthumb]", "-c:v", "mjpeg", "-q:v", "5",
			"-f", "image2pipe",
			jpegFIFO,
		)

		// Use a deadline context so ffmpeg is killed exactly at the segment
		// boundary. We cannot rely on ffmpeg's -t flag alone because FIFO
		// outputs block indefinitely and prevent a clean exit.
		segCtx, cancelSeg := context.WithDeadline(ctx, boundary)
		cmd := exec.CommandContext(segCtx, "ffmpeg", args...)
		cmd.Stdout = nil
		if m.cfg.FFmpegLog {
			cmd.Stderr = os.Stderr
		}
		m.setRecording(cam.Name, key, true)
		runErr := cmd.Run()
		cancelSeg()

		// Distinguish clean boundary rollover (deadline elapsed, parent ctx still alive)
		// from a genuine error (camera offline, etc.).
		boundaryReached := segCtx.Err() == context.DeadlineExceeded && ctx.Err() == nil
		if runErr != nil && !boundaryReached {
			log.Printf("dvr[%s]: stopped (%v), retrying in 5s", cam.Name, runErr)
			m.setRecording(cam.Name, key, false)
			select {
			case <-ctx.Done():
				return
			case <-time.After(5 * time.Second):
			}
			continue
		}

		// Boundary rollover: capture first-frame thumbnails.
		if boundaryReached && record {
			go m.captureSegmentThumbs(mp4File, cam.Name)
		}

		select {
		case <-ctx.Done():
			return
		default:
		}
	}
}

// StreamMPEGTS subscribes to the live MPEG-TS broadcaster for the named camera
// and streams chunks to w until the client disconnects or ctx is cancelled.
func (m *Manager) StreamMPEGTS(ctx context.Context, name string, w http.ResponseWriter) error {
	m.mu.RLock()
	lc := m.live[sanitizeName(name)]
	m.mu.RUnlock()
	if lc == nil {
		return fmt.Errorf("unknown camera %q", name)
	}

	w.Header().Set("Content-Type", "video/mp2t")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")

	flusher, canFlush := w.(http.Flusher)
	if canFlush {
		flusher.Flush()
	}

	ch := lc.ts.subscribe()
	defer lc.ts.unsubscribe(ch)

	for {
		select {
		case <-ctx.Done():
			return nil
		case chunk, ok := <-ch:
			if !ok {
				return nil // dropped by broadcaster (too slow)
			}
			if _, err := w.Write(chunk); err != nil {
				return nil // client gone
			}
			if canFlush {
				flusher.Flush()
			}
		}
	}
}

// SelectCamera switches the active camera for an existing StreamActive session.
// clientID must match the id passed to StreamActive when the connection was opened.
// Returns an error if the camera name or client session is unknown.
func (m *Manager) SelectCamera(clientID, name string) error {
	key := sanitizeName(name)
	m.mu.Lock()
	if m.live[key] == nil {
		m.mu.Unlock()
		return fmt.Errorf("unknown camera %q", name)
	}
	sess := m.sessions[clientID]
	if sess == nil {
		m.mu.Unlock()
		return fmt.Errorf("unknown session %q", clientID)
	}
	sess.activeCam = key
	old := sess.switchNotify
	sess.switchNotify = make(chan struct{})
	m.mu.Unlock()
	close(old) // wake the StreamActive goroutine for this session
	return nil
}

// StreamActive streams MPEG-TS from initialCamera, then seamlessly swaps to
// whichever camera SelectCamera specifies — without the client reconnecting.
// clientID is an arbitrary string the caller uses to identify the session;
// the same value must be passed to SelectCamera to switch cameras.
func (m *Manager) StreamActive(ctx context.Context, clientID, initialCamera string, w http.ResponseWriter) error {
	initKey := sanitizeName(initialCamera)
	if m.live[initKey] == nil {
		return fmt.Errorf("unknown camera %q", initialCamera)
	}

	// Register the session so SelectCamera can find it.
	sess := &streamSession{
		activeCam:    initKey,
		switchNotify: make(chan struct{}),
	}
	m.mu.Lock()
	m.sessions[clientID] = sess
	m.mu.Unlock()
	defer func() {
		m.mu.Lock()
		delete(m.sessions, clientID)
		m.mu.Unlock()
	}()

	w.Header().Set("Content-Type", "video/mp2t")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")

	flusher, canFlush := w.(http.Flusher)
	if canFlush {
		flusher.Flush()
	}

	for {
		// Read current camera and notify channel atomically.
		m.mu.RLock()
		key := sess.activeCam
		notify := sess.switchNotify
		m.mu.RUnlock()

		lc := m.live[key]
		if lc == nil {
			return fmt.Errorf("no active camera")
		}

		ch := lc.ts.subscribe()
		done := false
		for !done {
			select {
			case <-ctx.Done():
				lc.ts.unsubscribe(ch)
				return nil
			case <-notify:
				// Camera switched — resubscribe to new broadcaster.
				done = true
			case chunk, ok := <-ch:
				if !ok {
					done = true // dropped by broadcaster; resubscribe
					continue
				}
				if _, err := w.Write(chunk); err != nil {
					lc.ts.unsubscribe(ch)
					return nil // client gone
				}
				if canFlush {
					flusher.Flush()
				}
			}
		}
		lc.ts.unsubscribe(ch)
	}
}

// StreamSnapshot serves a multipart/x-mixed-replace stream for the named camera.
// It sends the latest cached frame immediately (if any), then pushes a new
// frame each time the background loop captures one.
func (m *Manager) StreamSnapshot(ctx context.Context, name string, w http.ResponseWriter, r *http.Request) error {
	m.mu.RLock()
	lc := m.live[sanitizeName(name)]
	m.mu.RUnlock()
	if lc == nil {
		return fmt.Errorf("unknown camera %q", name)
	}

	boundary := "snapshotboundary"
	w.Header().Set("Content-Type", "multipart/x-mixed-replace; boundary="+boundary)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Connection", "close")

	flusher, canFlush := w.(http.Flusher)
	w.WriteHeader(http.StatusOK)
	if canFlush {
		flusher.Flush()
	}

	mw := multipart.NewWriter(w)
	mw.SetBoundary(boundary)

	writePart := func(data []byte) error {
		h := make(textproto.MIMEHeader)
		h.Set("Content-Type", "image/jpeg")
		h.Set("Content-Length", fmt.Sprintf("%d", len(data)))
		pw, err := mw.CreatePart(h)
		if err != nil {
			return err
		}
		if canFlush {
			flusher.Flush()
		}
		if _, err := pw.Write(data); err != nil {
			return err
		}
		if canFlush {
			flusher.Flush()
		}
		return nil
	}

	data, ready := lc.frame.latest()
	if len(data) > 0 {
		if err := writePart(data); err != nil {
			return nil
		}
	}

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-r.Context().Done():
			return nil
		case <-ready:
			data, ready = lc.frame.latest()
			if len(data) == 0 {
				continue
			}
			if err := writePart(data); err != nil {
				return nil
			}
		}
	}
}

// resolveEnv expands a single value that may be an env-var reference.
func resolveEnv(v string) string {
	if len(v) > 1 && v[0] == '$' {
		return os.Getenv(v[1:])
	}
	return v
}

// rtspURL builds the RTSP URL for a camera, injecting credentials if provided.
func rtspURL(cam config.CameraConfig) string {
	creds := ""
	username := resolveEnv(cam.Username)
	if username != "" {
		pw := resolveEnv(cam.Password)
		creds = fmt.Sprintf("%s:%s@", username, pw)
	}
	port := cam.Port
	if port == 0 {
		port = 554
	}
	return fmt.Sprintf("rtsp://%s%s:%d/", creds, cam.Host, port)
}

// sanitizeName makes a camera name safe to use as a directory/file component.
func sanitizeName(name string) string {
	r := strings.NewReplacer(
		"/", "-",
		"\\", "-",
		":", "-",
		"*", "-",
		"?", "-",
		"\"", "-",
		"<", "-",
		">", "-",
		"|", "-",
		" ", "_",
	)
	return r.Replace(name)
}
