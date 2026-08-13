// Command intercom-stt continuously records cockpit-intercom audio, detects
// individual transmissions (VAD), transcribes them with whisper.cpp, tags each
// with GPS metadata, and writes timestamped audio + a structured transcript to
// disk while exposing the data over an internal API/websocket.
//
// It runs as a standalone process, separate from the main velocipi backend.
package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/vincent99/liveatc/internal/api"
	"github.com/vincent99/liveatc/internal/audio"
	"github.com/vincent99/liveatc/internal/config"
	"github.com/vincent99/liveatc/internal/gps"
	"github.com/vincent99/liveatc/internal/pipeline"
	"github.com/vincent99/liveatc/internal/ptt"
	"github.com/vincent99/liveatc/internal/session"
	"github.com/vincent99/liveatc/internal/stt"
	"github.com/vincent99/liveatc/internal/transcript"
	"github.com/vincent99/liveatc/internal/vad"
)

const frameSamples = 512 // Silero's fixed window at 16 kHz

func main() {
	var streams streamList
	var (
		configDir = flag.String("config", "..", "directory holding the shared velocipi config.default.yaml / config.yaml (defaults to the repo root, one level up from liveatc/)")
		filePath  = flag.String("file", "", "capture from a local audio file instead of ALSA, for testing")
		device    = flag.String("device", "", "override the ALSA capture device (else config/AUDIO_DEVICE)")
		fast      = flag.Bool("fast", false, "with --file: replay as fast as the CPU allows instead of at real time (segment wall-clock timestamps/durations will be compressed; audio + transcripts are unaffected)")
	)
	flag.Var(&streams, "stream", "capture from a network stream instead of ALSA; repeatable. Form name=url (or just url); the name tags each transmission's channel. e.g. --stream com1=http://a --stream com2=http://b")
	flag.Parse()

	cfg, err := config.Load(*configDir)
	if err != nil {
		panic(err)
	}
	if *device != "" {
		cfg.LiveATC.Audio.AudioDevice = *device
	}

	log := newLogger(cfg.LiveATC.LogLevel)

	// Session + manifest. Record the *actual* capture source: the ALSA device by
	// default, or the --stream URL / --file path when those override it, so the
	// manifest reflects what was really captured rather than the config default.
	modelPath := cfg.LiveATC.Whisper.ModelPath()
	source := cfg.LiveATC.Audio.AudioDevice
	switch {
	case *filePath != "":
		source = *filePath
	case len(streams) > 0:
		source = "streams: " + streams.String()
	}
	sess := session.New(cfg.Storage.LiveATC, cfg.TailNumber, source, modelPath)
	if err := sess.WriteManifest(); err != nil {
		log.Error("write session manifest", "err", err)
	}
	log.Info("session started", "id", sess.ID, "root", sess.Root, "model", modelPath)

	// Graceful shutdown on SIGINT/SIGTERM.
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Stores.
	store := transcript.NewStore(1000)
	gpsStore := gps.NewStore()

	// Transcript disk writers.
	writer, err := transcript.NewWriter(sess.JSONLPath(), sess.TextPath())
	if err != nil {
		log.Error("open transcript writer", "err", err)
		os.Exit(1)
	}
	defer writer.Close()

	// Audio sources + per-channel VAD scorers.
	base := audio.Params{
		SampleRate:   cfg.LiveATC.Audio.SampleRate,
		FrameSamples: frameSamples,
		ArecordBin:   cfg.LiveATC.Audio.ArecordBin,
		FFmpegBin:    cfg.LiveATC.Audio.FFmpegBin,
	}
	monoLabel := labelOr(cfg.LiveATC.Audio.MonoLabel, "mono")
	leftLabel := labelOr(cfg.LiveATC.Audio.LeftLabel, "com1")
	rightLabel := labelOr(cfg.LiveATC.Audio.RightLabel, "com2")

	var scorers []vad.Scorer
	newScorer := func() vad.Scorer {
		s := vad.NewScorer(ctx, vad.EngineParams{
			Engine:       cfg.LiveATC.VAD.Engine,
			SileroPython: cfg.LiveATC.VAD.SileroPython,
			SileroScript: cfg.LiveATC.VAD.SileroScript,
			SileroOnnx:   cfg.LiveATC.VAD.SileroOnnx,
			SampleRate:   cfg.LiveATC.Audio.SampleRate,
			FrameSamples: frameSamples,
			Threshold:    cfg.LiveATC.VAD.Threshold,
		}, log)
		scorers = append(scorers, s)
		return s
	}
	defer func() {
		for _, s := range scorers {
			_ = s.Close()
		}
	}()

	var specs []pipeline.SourceSpec
	// addChanneled builds one source from p, honoring audio.channels: 2 = stereo
	// (detect join/split per radio -> mono/com1/com2 labels), 1 = mono (lbl).
	addChanneled := func(p audio.Params, lbl string) {
		if cfg.LiveATC.Audio.Channels == 2 {
			p.Channels = 2
			specs = append(specs, pipeline.SourceSpec{
				Capture: audio.New(p, 0, log), Stereo: true,
				ScorerL: newScorer(), ScorerR: newScorer(),
				MonoLabel: monoLabel, LeftLabel: leftLabel, RightLabel: rightLabel,
				SplitThreshold: cfg.LiveATC.Audio.SplitThreshold,
			})
			return
		}
		p.Channels = 1
		specs = append(specs, pipeline.SourceSpec{
			Capture: audio.New(p, 0, log), Label: lbl, Scorer: newScorer(),
		})
	}

	switch {
	case len(streams) > 1:
		// Multiple named streams: each is its own mono channel named after the
		// stream (naming them is how you separate radios, so no split detection).
		for i, entry := range streams {
			name, url := parseStream(entry)
			if name == "" {
				name = "stream" + strconv.Itoa(i+1)
			}
			p := base
			p.Mode, p.StreamURL, p.Channels = audio.ModeStream, url, 1
			specs = append(specs, pipeline.SourceSpec{
				Capture: audio.New(p, 0, log), Label: name, Scorer: newScorer(),
			})
		}
	case len(streams) == 1:
		// A single stream behaves like the device/file: with channels: 2 it does
		// join/split detection (labels mono/com1/com2, name ignored); with
		// channels: 1 it's one mono channel labelled by the stream name (or mono).
		name, url := parseStream(streams[0])
		lbl := monoLabel
		if name != "" {
			lbl = name
		}
		p := base
		p.Mode, p.StreamURL = audio.ModeStream, url
		addChanneled(p, lbl)
	case *filePath != "":
		p := base
		p.Mode, p.FilePath, p.FastReplay = audio.ModeFile, *filePath, *fast
		addChanneled(p, monoLabel)
	default: // ALSA device
		p := base
		p.Mode, p.Device = audio.ModeALSA, cfg.LiveATC.Audio.AudioDevice
		addChanneled(p, monoLabel)
	}

	// STT.
	transcriber := stt.New(cfg.LiveATC.Whisper.Binary, modelPath, cfg.LiveATC.Whisper.Language, cfg.LiveATC.Whisper.Threads, cfg.LiveATC.Whisper.Prompt)
	if p := cfg.LiveATC.Whisper.Prompt; p != "" {
		est := stt.EstimatePromptTokens(p)
		if est > stt.PromptTokenLimit {
			log.Warn("whisper prompt likely exceeds the initial-prompt limit; whisper.cpp keeps only the LAST ~limit tokens (the front is dropped)",
				"estimated_tokens", est, "limit", stt.PromptTokenLimit)
		} else {
			log.Info("whisper prompt", "estimated_tokens", est, "limit", stt.PromptTokenLimit)
		}
	}

	// PTT monitor (optional; disabled when pttPin is empty or non-linux).
	pttMon := newPTT(cfg, log)
	defer pttMon.Close()

	// API server.
	apiSrv := api.New(cfg.LiveATC.Addr, cfg.Storage.LiveATC, cfg.LiveATC.UIDir, store, writer, gpsStore, sess, log)
	go func() {
		if err := apiSrv.Start(); err != nil {
			log.Error("api server", "err", err)
		}
	}()

	// Pipeline (blocks until ctx cancelled + queues drained).
	p := pipeline.New(pipeline.Deps{
		Config:      cfg,
		Session:     sess,
		Log:         log,
		Sources:     specs,
		Transcriber: transcriber,
		Store:       store,
		Writer:      writer,
		GPS:         gpsStore,
		PTT:         pttMon,
		// A file source is bounded, so block on a full STT queue (backpressure)
		// instead of dropping segments; live sources drop to avoid wedging.
		LiveSource: *filePath == "",
	})

	if err := p.Run(ctx); err != nil {
		log.Error("pipeline exited", "err", err)
	}

	// Shut the API down cleanly.
	shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = apiSrv.Shutdown(shutCtx)

	log.Info("shutdown complete", "session", sess.ID)
}

// streamList collects repeated --stream flags.
type streamList []string

func (s *streamList) String() string { return strings.Join(*s, ",") }
func (s *streamList) Set(v string) error {
	*s = append(*s, v)
	return nil
}

// parseStream splits a "name=url" stream spec; a bare url yields an empty name.
func parseStream(entry string) (name, url string) {
	if i := strings.IndexByte(entry, '='); i > 0 {
		return entry[:i], entry[i+1:]
	}
	return "", entry
}

func labelOr(v, def string) string {
	if v == "" {
		return def
	}
	return v
}

// newPTT builds the PTT monitor if a pin is configured; otherwise returns the
// disabled no-op monitor.
func newPTT(cfg *config.Config, log *slog.Logger) ptt.Monitor {
	pin := cfg.LiveATC.PTTPin
	if pin == "" {
		return ptt.Disabled()
	}
	offset, err := strconv.Atoi(pin)
	if err != nil {
		log.Warn("invalid pttPin (want GPIO offset integer); PTT disabled", "pttPin", pin, "err", err)
		return ptt.Disabled()
	}
	mon, err := ptt.New(cfg.LiveATC.PTTChip, offset, cfg.LiveATC.PTTActiveLow, log)
	if err != nil {
		log.Warn("PTT monitor unavailable; using audio-level heuristic", "err", err)
		return ptt.Disabled()
	}
	return mon
}

// newLogger returns a structured JSON logger at the configured level.
func newLogger(level string) *slog.Logger {
	var lvl slog.Level
	switch level {
	case "debug":
		lvl = slog.LevelDebug
	case "warn":
		lvl = slog.LevelWarn
	case "error":
		lvl = slog.LevelError
	default:
		lvl = slog.LevelInfo
	}
	h := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: lvl})
	return slog.New(h)
}
