package audio

import (
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"log/slog"
	"os/exec"
	"strings"
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
	Channels     int // 1 = mono, 2 = stereo (split-radio detection)
	FrameSamples int // samples per channel per emitted frame (512 for Silero @ 16k)
	ArecordBin   string
	FFmpegBin    string
	FastReplay   bool // ModeFile only: drop ffmpeg -re so the file plays as fast as possible
}

// Frame is one fixed-size block of captured audio, deinterleaved per channel.
// Chan[0] is mono/left, Chan[1] is right (present only for stereo). Each
// Chan[i] holds FrameSamples samples.
type Frame struct {
	Chan [][]int16
}

// Capture reads a raw s16le stream (1 or 2 channels) from its source, chops it
// into fixed-size per-channel frames, and publishes them on a channel. It never
// writes the continuous stream to disk.
type Capture struct {
	p      Params
	log    *slog.Logger
	frames chan Frame
}

// New builds a Capture. ringSamples is retained for API compatibility (unused).
func New(p Params, ringSamples int, log *slog.Logger) *Capture {
	if p.FrameSamples <= 0 {
		p.FrameSamples = 512
	}
	if p.Channels <= 0 {
		p.Channels = 1
	}
	return &Capture{
		p:      p,
		log:    log,
		frames: make(chan Frame, 64),
	}
}

// Frames is the stream of captured frames.
func (c *Capture) Frames() <-chan Frame { return c.frames }

// Channels reports how many channels this capture produces.
func (c *Capture) Channels() int { return c.p.Channels }

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

// readFrames reads FrameSamples*Channels*2 bytes at a time (interleaved
// s16le), deinterleaves into per-channel frames, and publishes them.
func (c *Capture) readFrames(ctx context.Context, r io.Reader) error {
	ch := c.p.Channels
	raw := make([]byte, c.p.FrameSamples*ch*2)
	for {
		if _, err := io.ReadFull(r, raw); err != nil {
			return err
		}
		frame := Frame{Chan: make([][]int16, ch)}
		for c0 := 0; c0 < ch; c0++ {
			frame.Chan[c0] = make([]int16, c.p.FrameSamples)
		}
		// Interleaved layout: [s0c0 s0c1 s1c0 s1c1 ...].
		for i := 0; i < c.p.FrameSamples; i++ {
			for c0 := 0; c0 < ch; c0++ {
				off := (i*ch + c0) * 2
				frame.Chan[c0][i] = int16(binary.LittleEndian.Uint16(raw[off:]))
			}
		}
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
	channels := fmt.Sprint(c.p.Channels)
	switch c.p.Mode {
	case ModeALSA:
		return exec.CommandContext(ctx, c.p.ArecordBin,
			"-D", c.p.Device,
			"-f", "S16_LE",
			"-r", rate,
			"-c", channels,
			"-t", "raw",
			"-q",
		)
	case ModeStream:
		// Live HTTP feeds (e.g. liveatc.net) routinely deliver a few seconds of
		// buffer and then stall -- the connection stays open but no more bytes
		// arrive. Without these options ffmpeg blocks on the read forever (no
		// EOF, no error), which silently wedges the whole pipeline. Auto-reconnect
		// on EOF / network errors, and bound socket reads with -rw_timeout so a
		// wedged connection errors out and Run() restarts us instead of hanging.
		return exec.CommandContext(ctx, c.p.FFmpegBin,
			"-hide_banner", "-loglevel", "error",
			"-reconnect", "1",
			"-reconnect_streamed", "1",
			"-reconnect_on_network_error", "1",
			"-reconnect_delay_max", "2",
			"-rw_timeout", "15000000", // 15s (microseconds): abort a stalled read
			"-i", c.p.StreamURL,
			"-ac", channels, "-ar", rate,
			"-f", "s16le", "-",
		)
	default: // ModeFile
		// -re paces playback at real time so wall-clock segment timestamps stay
		// realistic during testing. --fast drops it to replay as quickly as the
		// CPU allows (handy for soak-testing a long recording).
		args := []string{"-hide_banner", "-loglevel", "error"}
		if !c.p.FastReplay {
			args = append(args, "-re")
		}
		args = append(args, "-i", c.p.FilePath, "-ac", channels, "-ar", rate, "-f", "s16le", "-")
		return exec.CommandContext(ctx, c.p.FFmpegBin, args...)
	}
}

// logWriter forwards subprocess stderr lines to the structured logger. The
// source binaries run with error-only logging (ffmpeg -loglevel error, arecord
// -q), so anything that reaches here is worth surfacing at warn level -- a
// stalled/refused stream would otherwise be invisible.
type logWriter struct{ log *slog.Logger }

func (w *logWriter) Write(p []byte) (int, error) {
	if msg := strings.TrimSpace(string(p)); msg != "" {
		w.log.Warn("audio source stderr", "msg", msg)
	}
	return len(p), nil
}
