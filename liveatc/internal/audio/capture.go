package audio

import (
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"log/slog"
	"os/exec"
	"time"
)

// Mode selects the capture source.
type Mode int

const (
	ModeALSA   Mode = iota // live hardware via arecord (production)
	ModeStream             // network stream via ffmpeg (e.g. liveatc.net; testing)
	ModeFile               // local audio file via ffmpeg (testing)
)

// Params configures a Capture. Exactly one of Device/StreamURL/FilePath is used
// depending on Mode.
type Params struct {
	Mode         Mode
	Device       string // ALSA device, e.g. "hw:1,0"
	StreamURL    string // ffmpeg network input
	FilePath     string // ffmpeg local file input
	SampleRate   int
	FrameSamples int // samples per emitted frame (512 for Silero @ 16k)
	ArecordBin   string
	FFmpegBin    string
}

// Capture reads a raw s16le mono stream from its source, chops it into
// fixed-size frames, mirrors them into an in-memory ring buffer, and publishes
// them on a channel. It never writes the continuous stream to disk.
type Capture struct {
	p      Params
	log    *slog.Logger
	ring   *RingBuffer
	frames chan []int16
}

// New builds a Capture. ringSamples sets the in-memory history window.
func New(p Params, ringSamples int, log *slog.Logger) *Capture {
	if p.FrameSamples <= 0 {
		p.FrameSamples = 512
	}
	return &Capture{
		p:      p,
		log:    log,
		ring:   NewRingBuffer(ringSamples),
		frames: make(chan []int16, 64),
	}
}

// Frames is the stream of captured frames (each FrameSamples long).
func (c *Capture) Frames() <-chan []int16 { return c.frames }

// Ring exposes the recent-audio history buffer.
func (c *Capture) Ring() *RingBuffer { return c.ring }

// Run blocks until ctx is cancelled, reading from the source. Live sources
// (ALSA/stream) are restarted with backoff if they drop; a file source returns
// nil at EOF (used by tests to process a fixed clip and stop).
func (c *Capture) Run(ctx context.Context) error {
	defer close(c.frames)
	for {
		err := c.runOnce(ctx)
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if c.p.Mode == ModeFile {
			// A file plays through exactly once.
			return err
		}
		c.log.Warn("audio source ended, restarting", "err", err)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
}

func (c *Capture) runOnce(ctx context.Context) error {
	cmd := c.command(ctx)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	cmd.Stderr = &logWriter{log: c.log}

	c.log.Info("starting audio source", "cmd", cmd.String())
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start %s: %w", cmd.Path, err)
	}
	// Ensure the child is reaped / killed when we return.
	defer func() { _ = cmd.Wait() }()

	readErr := c.readFrames(ctx, stdout)
	// Cancellation kills the process via CommandContext; surface ctx first.
	if ctx.Err() != nil {
		return ctx.Err()
	}
	return readErr
}

// readFrames reads FrameSamples*2 bytes at a time, converts to int16, and
// publishes each frame.
func (c *Capture) readFrames(ctx context.Context, r io.Reader) error {
	frameBytes := c.p.FrameSamples * 2
	raw := make([]byte, frameBytes)
	for {
		if _, err := io.ReadFull(r, raw); err != nil {
			return err
		}
		frame := make([]int16, c.p.FrameSamples)
		for i := range frame {
			frame[i] = int16(binary.LittleEndian.Uint16(raw[i*2:]))
		}
		c.ring.Write(frame)
		select {
		case c.frames <- frame:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

// command builds the source subprocess. Documented deviations:
//   - ALSA: arecord emits headerless raw PCM (-t raw) at our exact rate/format,
//     so no resample is needed.
//   - Stream/File: ffmpeg decodes/normalizes anything to s16le mono @ rate. For
//     files we add -re so playback is paced at real time (keeps wall-clock
//     segment timestamps realistic during testing).
func (c *Capture) command(ctx context.Context) *exec.Cmd {
	rate := fmt.Sprint(c.p.SampleRate)
	switch c.p.Mode {
	case ModeALSA:
		return exec.CommandContext(ctx, c.p.ArecordBin,
			"-D", c.p.Device,
			"-f", "S16_LE",
			"-r", rate,
			"-c", "1",
			"-t", "raw",
			"-q",
		)
	case ModeStream:
		return exec.CommandContext(ctx, c.p.FFmpegBin,
			"-hide_banner", "-loglevel", "error",
			"-i", c.p.StreamURL,
			"-ac", "1", "-ar", rate,
			"-f", "s16le", "-",
		)
	default: // ModeFile
		return exec.CommandContext(ctx, c.p.FFmpegBin,
			"-hide_banner", "-loglevel", "error",
			"-re",
			"-i", c.p.FilePath,
			"-ac", "1", "-ar", rate,
			"-f", "s16le", "-",
		)
	}
}

// logWriter forwards subprocess stderr lines to the structured logger.
type logWriter struct{ log *slog.Logger }

func (w *logWriter) Write(p []byte) (int, error) {
	w.log.Debug("audio source stderr", "msg", string(p))
	return len(p), nil
}
