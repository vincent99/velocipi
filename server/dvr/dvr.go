// Package dvr manages continuous recording of IP cameras to disk using ffmpeg.
// Each camera runs a single ffmpeg process that simultaneously writes MP4
// segments for archival and a live HLS playlist for browser viewing.
// All timestamps are UTC. Archival files are organised under per-day
// subdirectories: <recordingsDir>/<camera>/<yyyy-mm-dd>/<camera>-<hh-mm-ss>.mp4
package dvr

import (
	"context"
	"fmt"
	"log"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/config"
)

const defaultSnapshotInterval = 5 * time.Second

// frameEntry holds the latest snapshot for a camera and the subscribers waiting for the next one.
type frameEntry struct {
	mu        sync.Mutex
	data      []byte    // latest JPEG, nil until first capture
	updatedAt time.Time // when data was last set
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
	f.updatedAt = time.Now()
	old := f.ready
	f.ready = make(chan struct{})
	f.mu.Unlock()
	close(old)
}

// CameraStatusMsg is broadcast over WebSocket when a camera's recording state changes.
type CameraStatusMsg struct {
	Type      string `json:"type"`      // always "cameraStatus"
	Name      string `json:"name"`      // camera name (original, not sanitized)
	Recording bool   `json:"recording"` // true = actively recording
}

// Manager starts and supervises DVR recording for all configured cameras.
// Each camera gets one ffmpeg process that writes both archival MP4 segments
// and a live HLS playlist. Call HLSDir to get the playlist directory for a camera.
type Manager struct {
	mu             sync.RWMutex
	cfg            config.DVRConfig
	hlsDirs        map[string]string      // sanitized name → HLS temp dir
	recording      map[string]bool        // sanitized name → recording state
	frames         map[string]*frameEntry // sanitized name → latest snapshot + waiters
	onStatusChange func(CameraStatusMsg)
}

// New creates a Manager. Call Start to begin recording.
func New(cfg config.DVRConfig) *Manager {
	frames := make(map[string]*frameEntry, len(cfg.Cameras))
	for _, cam := range cfg.Cameras {
		frames[sanitizeName(cam.Name)] = newFrameEntry()
	}
	return &Manager{
		cfg:       cfg,
		hlsDirs:   make(map[string]string),
		recording: make(map[string]bool),
		frames:    frames,
	}
}

// OnStatusChange registers a callback invoked whenever a camera's recording
// state changes. Must be called before Start.
func (m *Manager) OnStatusChange(fn func(CameraStatusMsg)) {
	m.onStatusChange = fn
}

// CameraStatuses returns the current recording status of all configured cameras.
// Implements CameraStatusProvider for hub.go.
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

// Start launches background recording and snapshot loops for each camera.
// It returns immediately; all loops run until ctx is cancelled.
func (m *Manager) Start(ctx context.Context) {
	if len(m.cfg.Cameras) == 0 {
		return
	}
	if err := os.MkdirAll(m.cfg.RecordingsDir, 0755); err != nil {
		log.Println("dvr: cannot create recordings dir:", err)
		return
	}
	for _, cam := range m.cfg.Cameras {
		go m.runCamera(ctx, cam)
		go m.runSnapshotLoop(ctx, cam)
	}
}

// HLSDir returns the directory containing the live HLS playlist for the named
// camera, or an error if the name is unknown. The directory is populated as
// soon as the camera's ffmpeg process produces its first segment; callers
// should handle a temporarily missing stream.m3u8 gracefully.
func (m *Manager) HLSDir(name string) (string, error) {
	found := false
	for i := range m.cfg.Cameras {
		if m.cfg.Cameras[i].Name == name {
			found = true
			break
		}
	}
	if !found {
		return "", fmt.Errorf("unknown camera %q", name)
	}
	key := sanitizeName(name)
	m.mu.RLock()
	dir := m.hlsDirs[key]
	m.mu.RUnlock()
	if dir == "" {
		return "", fmt.Errorf("camera %q is not yet recording", name)
	}
	return dir, nil
}

// snapshotInterval returns the configured snapshot capture interval.
func (m *Manager) snapshotInterval() time.Duration {
	if m.cfg.SnapshotInterval > 0 {
		return time.Duration(m.cfg.SnapshotInterval) * time.Second
	}
	return defaultSnapshotInterval
}

// fetchSnapshot grabs a single JPEG frame from the camera via ffmpeg,
// scaled down to 240px height (preserving aspect ratio).
func fetchSnapshot(ctx context.Context, cam config.CameraConfig) ([]byte, error) {
	args := []string{
		"-rtsp_transport", "tcp",
		"-i", rtspURL(cam),
		"-vframes", "1",
		"-vf", "scale=-2:240",
		"-f", "image2pipe",
		"-vcodec", "mjpeg",
		"-q:v", "5",
		"pipe:1",
	}
	cmd := exec.CommandContext(ctx, "ffmpeg", args...)
	data, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("ffmpeg snapshot: %w", err)
	}
	return data, nil
}

// runSnapshotLoop continuously captures frames for one camera and publishes
// them so StreamSnapshot clients receive updates immediately.
func (m *Manager) runSnapshotLoop(ctx context.Context, cam config.CameraConfig) {
	key := sanitizeName(cam.Name)
	interval := m.snapshotInterval()
	for {
		snapCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		data, err := fetchSnapshot(snapCtx, cam)
		cancel()
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			log.Printf("dvr[%s]: snapshot error: %v", cam.Name, err)
		} else {
			if fe := m.frames[key]; fe != nil {
				fe.publish(data)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(interval):
		}
	}
}

// StreamSnapshot serves a multipart/x-mixed-replace stream for the named camera.
// It sends the latest cached frame immediately (if any), then pushes a new
// frame each time the background snapshot loop captures one.
// The stream runs until the client disconnects or ctx is cancelled.
func (m *Manager) StreamSnapshot(ctx context.Context, name string, w http.ResponseWriter, r *http.Request) error {
	key := sanitizeName(name)
	fe, ok := m.frames[key]
	if !ok {
		return fmt.Errorf("unknown camera %q", name)
	}

	boundary := "snapshotboundary"
	w.Header().Set("Content-Type", "multipart/x-mixed-replace; boundary="+boundary)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Connection", "close")

	flusher, canFlush := w.(http.Flusher)

	// Commit the response headers and flush them to the client immediately.
	// Without this, Go's write buffer holds them until the first data write.
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
			// Flush the boundary+part headers before writing the body so the
			// client sees them without waiting for the buffer to fill.
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

	// Send the cached frame immediately so the thumbnail appears without waiting.
	data, ready := fe.latest()
	if len(data) > 0 {
		if err := writePart(data); err != nil {
			return nil // client gone
		}
	}

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-r.Context().Done():
			return nil
		case <-ready:
			data, ready = fe.latest()
			if len(data) == 0 {
				continue
			}
			if err := writePart(data); err != nil {
				return nil // client gone
			}
		}
	}
}

// resolveEnv expands a single value that may be an env-var reference.
// If the value starts with "$", the remainder is treated as an env var name
// and its value is returned. Otherwise the value is returned unchanged.
func resolveEnv(v string) string {
	if len(v) > 1 && v[0] == '$' {
		return os.Getenv(v[1:])
	}
	return v
}

// rtspURL builds the RTSP URL for a camera, injecting credentials if provided.
// Env-var references (e.g. "$MY_PASS") in Username and Password are resolved
// at call time so they never appear in persisted config or the API.
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

// runCamera is the per-camera goroutine. It allocates a persistent HLS temp dir
// (stable for the process lifetime so the playlist URL never changes) and then
// enters the recording loop.
func (m *Manager) runCamera(ctx context.Context, cam config.CameraConfig) {
	key := sanitizeName(cam.Name)
	camBase := filepath.Join(m.cfg.RecordingsDir, key)

	// Allocate a persistent temp dir for HLS output.
	hlsDir, err := os.MkdirTemp("", "velocipi-hls-"+key+"-")
	if err != nil {
		log.Printf("dvr[%s]: cannot create HLS dir: %v", cam.Name, err)
		return
	}
	defer os.RemoveAll(hlsDir)

	m.mu.Lock()
	m.hlsDirs[key] = hlsDir
	m.mu.Unlock()

	m.runLoop(ctx, cam, camBase, hlsDir)
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
	// How far into the day are we?
	elapsed := now.Sub(time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC))
	// Next segment boundary within the day.
	next := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC).
		Add(((elapsed / seg) + 1) * seg)
	if next.After(midnight) {
		return midnight
	}
	return next
}

// runLoop is the main per-camera restart loop. Each iteration:
//  1. Computes the UTC start time and determines the current day's subdir.
//  2. Calculates how many seconds until the next segment boundary (or midnight).
//  3. Runs a single ffmpeg with -t <duration> writing one MP4 file plus HLS.
//  4. On normal exit (or error), waits up to 5s then restarts.
//
// Because each ffmpeg run is bounded by -t, it naturally stops before midnight
// so the next iteration can open a new day directory. The HLS output is
// continuous — ffmpeg appends to the rolling playlist across restarts because
// hls_flags=append_list is set.
//
// tee syntax requires -map before -f tee, and format options in [...] brackets.
func (m *Manager) runLoop(ctx context.Context, cam config.CameraConfig, camBase, hlsDir string) {
	key := sanitizeName(cam.Name)
	playlist := filepath.Join(hlsDir, "stream.m3u8")
	hlsSeg := filepath.Join(hlsDir, "seg%05d.ts")
	segSecs := m.segmentDur()

	defer m.setRecording(cam.Name, key, false)

	for {
		if ctx.Err() != nil {
			return
		}

		now := time.Now().UTC()
		boundary := nextBoundary(now, segSecs)
		duration := int(boundary.Sub(now).Seconds())
		if duration <= 0 {
			duration = 1
		}

		// Ensure the daily subdir exists.
		dayDir := filepath.Join(camBase, now.Format("2006-01-02"))
		if err := os.MkdirAll(dayDir, 0755); err != nil {
			log.Printf("dvr[%s]: cannot create day dir: %v", cam.Name, err)
			m.setRecording(cam.Name, key, false)
			select {
			case <-ctx.Done():
				return
			case <-time.After(5 * time.Second):
			}
			continue
		}

		mp4File := filepath.Join(dayDir, fmt.Sprintf("%s_%s_%s.mp4", sanitizeName(cam.Name), now.Format("2006-01-02-15"), now.Format("03-04-05")))
		log.Printf("dvr[%s]: starting → %s (%ds)", cam.Name, mp4File, duration)

		teeOut := fmt.Sprintf(
			"[f=mp4:movflags=+faststart+empty_moov+default_base_moof]%s"+
				"|[f=hls:hls_time=2:hls_list_size=10:hls_flags=delete_segments+append_list:hls_segment_filename=%s]%s",
			mp4File, hlsSeg, playlist,
		)
		args := []string{
			"-rtsp_transport", "tcp",
			"-i", rtspURL(cam),
			"-t", fmt.Sprintf("%d", duration),
			"-c", "copy",
			"-map", "0",
			"-f", "tee",
			"-y",
			teeOut,
		}
		cmd := exec.CommandContext(ctx, "ffmpeg", args...)
		cmd.Stdout = nil
		cmd.Stderr = nil
		m.setRecording(cam.Name, key, true)
		if err := cmd.Run(); err != nil && ctx.Err() == nil {
			log.Printf("dvr[%s]: stopped (%v), retrying in 5s", cam.Name, err)
			m.setRecording(cam.Name, key, false)
			select {
			case <-ctx.Done():
				return
			case <-time.After(5 * time.Second):
			}
			continue
		}

		// Normal exit (segment boundary reached). Restart immediately.
		select {
		case <-ctx.Done():
			return
		default:
		}
	}
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
