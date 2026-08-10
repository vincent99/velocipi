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
	var (
		configDir = flag.String("config", ".", "directory holding config.default.yaml / config.yaml")
		streamURL = flag.String("stream", "", "capture from a network stream (e.g. liveatc.net) instead of ALSA, for testing")
		filePath  = flag.String("file", "", "capture from a local audio file instead of ALSA, for testing")
		device    = flag.String("device", "", "override the ALSA capture device (else config/AUDIO_DEVICE)")
	)
	flag.Parse()

	cfg, err := config.Load(*configDir)
	if err != nil {
		panic(err)
	}
	if *device != "" {
		cfg.LiveATC.Audio.AudioDevice = *device
	}

	log := newLogger(cfg.LogLevel)

	// Session + manifest.
	modelPath := cfg.LiveATC.Whisper.ModelPath()
	sess := session.New(cfg.Storage.LiveATC, cfg.Aircraft, cfg.LiveATC.Audio.AudioDevice, modelPath)
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

	// Capture source.
	capParams := audio.Params{
		Mode:         audio.ModeALSA,
		Device:       cfg.LiveATC.Audio.AudioDevice,
		SampleRate:   cfg.LiveATC.Audio.SampleRate,
		FrameSamples: frameSamples,
		ArecordBin:   cfg.LiveATC.Audio.ArecordBin,
		FFmpegBin:    cfg.LiveATC.Audio.FFmpegBin,
	}
	switch {
	case *filePath != "":
		capParams.Mode, capParams.FilePath = audio.ModeFile, *filePath
	case *streamURL != "":
		capParams.Mode, capParams.StreamURL = audio.ModeStream, *streamURL
	}
	ringSamples := cfg.LiveATC.Audio.SampleRate * 3
	capture := audio.New(capParams, ringSamples, log)

	// VAD scorer (silero sidecar with energy fallback).
	scorer := vad.NewScorer(ctx, vad.EngineParams{
		Engine:       cfg.LiveATC.VAD.Engine,
		SileroPython: cfg.LiveATC.VAD.SileroPython,
		SileroScript: cfg.LiveATC.VAD.SileroScript,
		SampleRate:   cfg.LiveATC.Audio.SampleRate,
		FrameSamples: frameSamples,
		Threshold:    cfg.LiveATC.VAD.Threshold,
	}, log)
	defer scorer.Close()

	// STT.
	transcriber := stt.New(cfg.LiveATC.Whisper.Binary, modelPath, cfg.LiveATC.Whisper.Language, cfg.LiveATC.Whisper.Threads)

	// PTT monitor (optional; disabled when pttPin is empty or non-linux).
	pttMon := newPTT(cfg, log)
	defer pttMon.Close()

	// API server.
	apiSrv := api.New(cfg.Addr, store, gpsStore, sess, log)
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
		Capture:     capture,
		Scorer:      scorer,
		Transcriber: transcriber,
		Store:       store,
		Writer:      writer,
		GPS:         gpsStore,
		PTT:         pttMon,
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
