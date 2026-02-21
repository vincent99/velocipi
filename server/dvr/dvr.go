// Package dvr manages continuous recording of IP cameras to disk using ffmpeg.
// Each camera runs a single ffmpeg process that simultaneously writes 10-minute
// MKV segments for archival and a live HLS playlist for browser viewing.
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

const segmentDuration = 10 * 60 // 10 minutes in seconds

// Manager starts and supervises DVR recording for all configured cameras.
// Each camera gets one ffmpeg process that writes both archival MKV segments
// and a live HLS playlist. Call HLSDir to get the playlist directory for a camera.
type Manager struct {
	mu      sync.RWMutex
	cfg     config.DVRConfig
	hlsDirs map[string]string // sanitized name → HLS temp dir
}

// New creates a Manager. Call Start to begin recording.
func New(cfg config.DVRConfig) *Manager {
	return &Manager{
		cfg:     cfg,
		hlsDirs: make(map[string]string),
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
	// Validate the name against the config.
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

// runCamera is the per-camera goroutine. It launches two independent ffmpeg
// loops: one for archival MKV segments and one for the live HLS playlist.
func (m *Manager) runCamera(ctx context.Context, cam config.CameraConfig) {
	key := sanitizeName(cam.Name)
	recDir := filepath.Join(m.cfg.RecordingsDir, key)
	if err := os.MkdirAll(recDir, 0755); err != nil {
		log.Printf("dvr[%s]: cannot create camera dir: %v", cam.Name, err)
		return
	}

	// Allocate a persistent temp dir for HLS output. This dir lives for the
	// lifetime of the process so the playlist path never changes.
	hlsDir, err := os.MkdirTemp("", "velocipi-hls-"+key+"-")
	if err != nil {
		log.Printf("dvr[%s]: cannot create HLS dir: %v", cam.Name, err)
		return
	}
	defer os.RemoveAll(hlsDir)

	m.mu.Lock()
	m.hlsDirs[key] = hlsDir
	m.mu.Unlock()

	go m.runRecordLoop(ctx, cam, recDir)
	m.runHLSLoop(ctx, cam, hlsDir)
}

// runRecordLoop continuously records 10-minute MKV segments, restarting on failure.
func (m *Manager) runRecordLoop(ctx context.Context, cam config.CameraConfig, recDir string) {
	for {
		if ctx.Err() != nil {
			return
		}
		log.Printf("dvr[%s]: starting recording", cam.Name)
		ts := time.Now().Format("2006-01-02-15-04-05")
		outPath := filepath.Join(recDir, fmt.Sprintf("%s-%s.mkv", sanitizeName(cam.Name), ts))
		args := []string{
			"-rtsp_transport", "tcp",
			"-i", rtspURL(cam),
			"-t", fmt.Sprintf("%d", segmentDuration),
			"-c", "copy",
			"-y",
			outPath,
		}
		cmd := exec.CommandContext(ctx, "ffmpeg", args...)
		cmd.Stdout = nil
		cmd.Stderr = nil
		if err := cmd.Run(); err != nil && ctx.Err() == nil {
			log.Printf("dvr[%s]: recording stopped (%v), retrying in 5s", cam.Name, err)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(5 * time.Second):
		}
	}
}

// runHLSLoop continuously maintains a live HLS playlist, restarting on failure.
func (m *Manager) runHLSLoop(ctx context.Context, cam config.CameraConfig, hlsDir string) {
	playlist := filepath.Join(hlsDir, "stream.m3u8")
	segPattern := filepath.Join(hlsDir, "seg%05d.ts")
	for {
		if ctx.Err() != nil {
			return
		}
		log.Printf("dvr[%s]: starting HLS stream", cam.Name)
		args := []string{
			"-rtsp_transport", "tcp",
			"-i", rtspURL(cam),
			"-c", "copy",
			"-f", "hls",
			"-hls_time", "2",
			"-hls_list_size", "10",
			"-hls_flags", "delete_segments+append_list",
			"-hls_segment_filename", segPattern,
			"-y",
			playlist,
		}
		cmd := exec.CommandContext(ctx, "ffmpeg", args...)
		cmd.Stdout = nil
		cmd.Stderr = nil
		if err := cmd.Run(); err != nil && ctx.Err() == nil {
			log.Printf("dvr[%s]: HLS stopped (%v), retrying in 5s", cam.Name, err)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(5 * time.Second):
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
