package vad

import (
	"bufio"
	"context"
	"encoding/binary"
	"fmt"
	"log/slog"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"
)

// readyTimeout bounds how long we wait for the sidecar to load its model and
// signal readiness. Generous because a first-run torch.hub download can be slow.
const readyTimeout = 60 * time.Second

// readyMarker is the stderr line the sidecar prints once its model is loaded.
const readyMarker = "__READY__"

// SileroScorer talks to the Python Silero-VAD sidecar over the child's
// stdin/stdout with dead-simple framing:
//
//	Go -> sidecar : FrameSamples*2 raw little-endian int16 bytes per frame
//	sidecar -> Go : one ASCII float line (speech probability) per frame
//
// Requests are strictly 1:1 and ordered, so a single mutex around
// write-then-read keeps the two sides in lockstep without extra bookkeeping.
type SileroScorer struct {
	cmd    *exec.Cmd
	stdin  *bufio.Writer
	stdinC interface{ Close() error }
	stdout *bufio.Reader
	log    *slog.Logger

	mu      sync.Mutex
	scratch []byte
}

// NewSileroScorer starts the sidecar. It returns an error if the process can't
// be launched; the caller may then fall back to the energy scorer.
func NewSileroScorer(ctx context.Context, python, script string, sampleRate, frameSamples int, threshold float64, log *slog.Logger) (*SileroScorer, error) {
	cmd := exec.CommandContext(ctx, python, script,
		"--sample-rate", strconv.Itoa(sampleRate),
		"--frame-samples", strconv.Itoa(frameSamples),
		"--threshold", strconv.FormatFloat(threshold, 'f', -1, 64),
	)
	stdinPipe, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		return nil, err
	}

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start silero sidecar (%s %s): %w", python, script, err)
	}

	// Scan stderr: forward everything to the log and signal readiness once the
	// sidecar has loaded its model. If import/load fails, the pipe closes
	// (EOF) before the marker and we treat that as "not ready".
	ready := make(chan struct{})
	go func() {
		sc := bufio.NewScanner(stderrPipe)
		signalled := false
		for sc.Scan() {
			line := sc.Text()
			if !signalled && strings.Contains(line, readyMarker) {
				signalled = true
				close(ready)
				continue
			}
			if msg := strings.TrimSpace(line); msg != "" {
				log.Debug("silero sidecar", "msg", msg)
			}
		}
	}()

	select {
	case <-ready:
	case <-time.After(readyTimeout):
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
		return nil, fmt.Errorf("silero sidecar not ready within %s", readyTimeout)
	}

	// The sidecar could still have exited right at/after the marker; a quick
	// check catches the obvious case without racing normal operation.
	if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
		return nil, fmt.Errorf("silero sidecar exited during startup")
	}

	return &SileroScorer{
		cmd:     cmd,
		stdin:   bufio.NewWriter(stdinPipe),
		stdinC:  stdinPipe,
		stdout:  bufio.NewReader(stdoutPipe),
		log:     log,
		scratch: make([]byte, frameSamples*2),
	}, nil
}

// Score sends one frame and reads back its speech probability.
func (s *SileroScorer) Score(frame []int16) (float64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if len(frame)*2 != len(s.scratch) {
		s.scratch = make([]byte, len(frame)*2)
	}
	for i, v := range frame {
		binary.LittleEndian.PutUint16(s.scratch[i*2:], uint16(v))
	}
	if _, err := s.stdin.Write(s.scratch); err != nil {
		return 0, fmt.Errorf("silero write: %w", err)
	}
	if err := s.stdin.Flush(); err != nil {
		return 0, fmt.Errorf("silero flush: %w", err)
	}

	line, err := s.stdout.ReadString('\n')
	if err != nil {
		return 0, fmt.Errorf("silero read: %w", err)
	}
	p, err := strconv.ParseFloat(strings.TrimSpace(line), 64)
	if err != nil {
		return 0, fmt.Errorf("silero parse %q: %w", line, err)
	}
	return p, nil
}

// Close shuts the sidecar down by closing its stdin (EOF) and reaping it.
func (s *SileroScorer) Close() error {
	_ = s.stdinC.Close()
	return s.cmd.Wait()
}
