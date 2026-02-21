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
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/config"
)

const snapshotTTL = 5 * time.Second

type snapshotCache struct {
	data      []byte
	fetchedAt time.Time
}

// Manager starts and supervises DVR recording for all configured cameras.
// Each camera gets one ffmpeg process that writes both archival MP4 segments
// and a live HLS playlist. Call HLSDir to get the playlist directory for a camera.
type Manager struct {
	mu        sync.RWMutex
	cfg       config.DVRConfig
	hlsDirs   map[string]string         // sanitized name → HLS temp dir
	snapshots map[string]*snapshotCache // sanitized name → cached JPEG
	snapMu    sync.Mutex
}

// New creates a Manager. Call Start to begin recording.
func New(cfg config.DVRConfig) *Manager {
	return &Manager{
		cfg:       cfg,
		hlsDirs:   make(map[string]string),
		snapshots: make(map[string]*snapshotCache),
	}
}

// Start launches a background recording loop for each camera.
// It returns immediately; recording runs until ctx is cancelled.
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

// Snapshot returns a JPEG-encoded frame from the named camera's RTSP stream.
// Results are cached for snapshotTTL to avoid hammering the camera on rapid requests.
// The context controls the ffmpeg subprocess timeout.
func (m *Manager) Snapshot(ctx context.Context, name string) ([]byte, error) {
	var cam *config.CameraConfig
	for i := range m.cfg.Cameras {
		if m.cfg.Cameras[i].Name == name {
			cam = &m.cfg.Cameras[i]
			break
		}
	}
	if cam == nil {
		return nil, fmt.Errorf("unknown camera %q", name)
	}
	key := sanitizeName(name)

	m.snapMu.Lock()
	defer m.snapMu.Unlock()

	if c := m.snapshots[key]; c != nil && time.Since(c.fetchedAt) < snapshotTTL {
		return c.data, nil
	}

	// -vframes 1: grab exactly one frame
	// -f image2pipe: write raw image to stdout
	// -vcodec mjpeg: encode as JPEG
	// -q:v 5: quality 1 (best) – 31 (worst); 5 is a good balance
	args := []string{
		"-rtsp_transport", "tcp",
		"-i", rtspURL(*cam),
		"-vframes", "1",
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

	m.snapshots[key] = &snapshotCache{data: data, fetchedAt: time.Now()}
	return data, nil
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
	playlist := filepath.Join(hlsDir, "stream.m3u8")
	hlsSeg := filepath.Join(hlsDir, "seg%05d.ts")
	segSecs := m.segmentDur()

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
		if err := cmd.Run(); err != nil && ctx.Err() == nil {
			log.Printf("dvr[%s]: stopped (%v), retrying in 5s", cam.Name, err)
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
