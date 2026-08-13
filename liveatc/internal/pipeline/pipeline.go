// Package pipeline wires the subsystems together: capture -> VAD segmentation
// -> per-transmission WAV -> whisper STT -> transcript persistence + broadcast.
//
// Audio enters through one or more Sources. A mono source feeds a single VAD
// "lane" tagged with its channel name. A stereo source detects, frame by frame,
// whether its two channels are joined (identical -> one "mono" lane) or split
// (independent radios -> separate left/right lanes), so the two radios are
// transcribed separately and each transmission is tagged with its channel.
package pipeline

import (
	"context"
	"encoding/json"
	"log/slog"
	"math"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/vincent99/liveatc/internal/audio"
	"github.com/vincent99/liveatc/internal/config"
	"github.com/vincent99/liveatc/internal/gps"
	"github.com/vincent99/liveatc/internal/ptt"
	"github.com/vincent99/liveatc/internal/session"
	"github.com/vincent99/liveatc/internal/stt"
	"github.com/vincent99/liveatc/internal/transcript"
	"github.com/vincent99/liveatc/internal/vad"
)

// SourceSpec describes one audio source, built by main. A mono source uses
// Capture + Scorer + Label; a stereo source uses Capture + ScorerL/ScorerR and
// the three labels + threshold.
type SourceSpec struct {
	Capture *audio.Capture
	Stereo  bool

	// mono
	Label  string
	Scorer vad.Scorer

	// stereo
	ScorerL        vad.Scorer
	ScorerR        vad.Scorer
	MonoLabel      string
	LeftLabel      string
	RightLabel     string
	SplitThreshold float64
}

// Deps are the collaborators the pipeline needs, built by main.
type Deps struct {
	Config      *config.Config
	Session     *session.Session
	Log         *slog.Logger
	Sources     []SourceSpec
	Transcriber *stt.Transcriber
	Store       *transcript.Store
	Writer      *transcript.Writer
	GPS         *gps.Store
	PTT         ptt.Monitor
	// LiveSource is true for unbounded live capture (ALSA / network stream),
	// where a full STT queue must be dropped rather than block capture. For a
	// bounded file source it is false, so emit applies backpressure and no
	// segment is lost (the run just paces to STT throughput).
	LiveSource bool
}

// Pipeline owns the runtime loops.
type Pipeline struct {
	Deps
	jobs chan sttJob
	wg   sync.WaitGroup

	// runCtx is the Run context; it lets emit's blocking (bounded-source) enqueue
	// bail out on shutdown instead of deadlocking on a full queue once the STT
	// workers have stopped pulling.
	runCtx context.Context
}

// sttJob is a finished segment awaiting transcription.
type sttJob struct {
	id       string
	channel  string
	wavPath  string
	relPath  string
	samples  []int16
	start    time.Time
	end      time.Time
	gpsStart gps.GPSFix
	gpsEnd   gps.GPSFix
	dir      string
	infoBase audio.INFO
}

// New builds a Pipeline from its deps.
func New(d Deps) *Pipeline {
	return &Pipeline{Deps: d, jobs: make(chan sttJob, 32)}
}

// lane is one independent VAD path tagged with a channel. It snapshots GPS at
// each transmission start and emits finished segments to the pipeline.
type lane struct {
	channel string
	seg     *vad.Segmenter
	gps     *gps.Store
	pending gps.GPSFix
}

func (p *Pipeline) newLane(channel string) *lane {
	vd := p.Config.VADDurations()
	l := &lane{channel: channel, gps: p.GPS}
	l.seg = vad.NewSegmenter(vad.Params{
		SampleRate:      p.Config.LiveATC.Audio.SampleRate,
		FrameSamples:    512,
		Threshold:       p.Config.LiveATC.VAD.Threshold,
		MinSpeech:       vd.MinSpeech,
		MinSilence:      vd.MinSilence,
		MaxSegment:      vd.MaxSegment,
		PreRoll:         vd.PreRoll,
		CarrierFloor:    p.Config.LiveATC.VAD.CarrierFloor,
		CarrierHangover: vd.CarrierHangover,
	}, time.Now)
	l.seg.OnSpeechStart = func(time.Time) { l.pending = l.gps.Snapshot() }
	l.seg.OnSegment = func(s vad.Segment) { p.emit(l.channel, s, l.pending) }
	return l
}

func (l *lane) feed(frame []int16, score float64) { l.seg.Feed(frame, score) }
func (l *lane) flush()                            { l.seg.Flush() }

// sttShutdownGrace bounds how long shutdown waits for an in-flight transcription
// to finish before cancelling it. Segments still queued (not yet started) at
// shutdown are dropped -- their WAVs are on disk and self-contained.
const sttShutdownGrace = 5 * time.Second

// Run blocks until ctx is cancelled (or all sources end), then flushes and stops
// the STT workers before returning.
func (p *Pipeline) Run(ctx context.Context) error {
	p.runCtx = ctx

	sttCtx, sttCancel := context.WithCancel(context.Background())
	defer sttCancel()

	workers := p.Config.LiveATC.Whisper.Workers
	if workers <= 0 {
		workers = 2
	}
	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.sttWorker(i, ctx, sttCtx)
	}

	// Run each source; each blocks until ctx is cancelled (live) or EOF (file).
	var swg sync.WaitGroup
	for _, spec := range p.Sources {
		swg.Add(1)
		go func(s SourceSpec) {
			defer swg.Done()
			p.runSource(ctx, s)
		}(spec)
	}
	p.log().Info("pipeline running", "session", p.Session.ID, "sources", len(p.Sources))
	swg.Wait()

	// Cleanup: no more segments will be produced; drain the STT workers.
	close(p.jobs)
	drained := make(chan struct{})
	go func() { p.wg.Wait(); close(drained) }()
	if ctx.Err() != nil {
		select {
		case <-drained:
		case <-time.After(sttShutdownGrace):
			p.log().Warn("STT busy at shutdown; cancelling in-flight transcription and dropping queued segments")
			sttCancel()
			<-drained
		}
	} else {
		<-drained // clean end-of-input (file mode): drain fully
	}
	return nil
}

// runSource consumes one capture and routes its frames into lanes. Returns when
// the capture's frame channel closes (ctx cancel for live sources, EOF for a
// file). It starts the capture itself.
func (p *Pipeline) runSource(ctx context.Context, spec SourceSpec) {
	captureErr := make(chan error, 1)
	go func() { captureErr <- spec.Capture.Run(ctx) }()
	frames := spec.Capture.Frames()

	if !spec.Stereo {
		l := p.newLane(spec.Label)
		for f := range frames {
			if len(f.Chan) == 0 {
				continue
			}
			ch0 := f.Chan[0]
			l.feed(ch0, p.score(spec.Scorer, ch0))
		}
		l.flush()
		<-captureErr
		return
	}

	// Stereo: three lanes, only one mode active at a time. Flush the lanes being
	// deactivated on a mode change so no segment spans a join<->split transition.
	monoLane := p.newLane(spec.MonoLabel)
	com1 := p.newLane(spec.LeftLabel)
	com2 := p.newLane(spec.RightLabel)
	det := audio.NewSplitDetector(spec.SplitThreshold)
	prevSplit := false
	for f := range frames {
		if len(f.Chan) < 2 {
			continue
		}
		l, r := f.Chan[0], f.Chan[1]
		split := det.Update(l, r)
		if split != prevSplit {
			if split {
				monoLane.flush()
			} else {
				com1.flush()
				com2.flush()
			}
			prevSplit = split
		}
		// scorerL always sees L (used by the mono OR com1 lane); scorerR only in
		// split mode, so it isn't run when the right radio's lane is idle.
		sL := p.score(spec.ScorerL, l)
		if split {
			com1.feed(l, sL)
			com2.feed(r, p.score(spec.ScorerR, r))
		} else {
			monoLane.feed(l, sL)
		}
	}
	monoLane.flush()
	com1.flush()
	com2.flush()
	<-captureErr
}

// score runs a scorer, treating an error as silence so a hiccup can't wedge the
// stream.
func (p *Pipeline) score(s vad.Scorer, frame []int16) float64 {
	v, err := s.Score(frame)
	if err != nil {
		p.log().Debug("VAD score error", "err", err)
		return 0
	}
	return v
}

// emit persists the WAV + metadata and enqueues STT for one channel's segment.
func (p *Pipeline) emit(channel string, seg vad.Segment, gpsStart gps.GPSFix) {
	id := uuid.NewString()
	gpsEnd := p.GPS.Snapshot()
	sampleRate := p.Config.LiveATC.Audio.SampleRate

	wavPath := p.Session.AudioPath(seg.StartTime, id, "")
	info := audio.INFO{
		ICRD: seg.StartTime.UTC().Format(time.RFC3339),
		ISRC: "cockpit-intercom",
		IART: channel,
		ICMT: gpsCommentJSON(gpsStart, gpsEnd),
	}
	if err := audio.WriteWAV(wavPath, seg.Samples, sampleRate, info); err != nil {
		p.log().Error("write segment wav", "err", err, "path", wavPath)
		return
	}

	job := sttJob{
		id:       id,
		channel:  channel,
		wavPath:  wavPath,
		relPath:  p.Session.Rel(wavPath),
		samples:  seg.Samples,
		start:    seg.StartTime.UTC(),
		end:      seg.EndTime.UTC(),
		gpsStart: gpsStart,
		gpsEnd:   gpsEnd,
		dir:      p.direction(seg, gpsStart.Time),
		infoBase: info,
	}
	p.log().Info("segment captured",
		"id", id, "channel", channel, "dur_ms", job.end.Sub(job.start).Milliseconds(), "dir", job.dir, "file", job.relPath)

	if p.LiveSource {
		select {
		case p.jobs <- job:
		default:
			// Queue full on a live source: STT is falling behind and we can't pause
			// the stream. Keep the (self-contained) WAV, drop the STT step.
			p.log().Warn("STT queue full, segment saved without transcript", "id", id, "file", job.relPath)
		}
		return
	}
	// Bounded source (file replay): block so no segment is lost. Bail on shutdown.
	select {
	case p.jobs <- job:
	case <-p.runCtx.Done():
		p.log().Warn("shutting down, segment saved without transcript", "id", id, "file", job.relPath)
	}
}

// direction classifies tx/rx/unknown. See package ptt for the two strategies.
func (p *Pipeline) direction(seg vad.Segment, start time.Time) string {
	if p.PTT.Enabled() {
		if p.PTT.ActiveSince(seg.StartTime) {
			return "tx"
		}
		return "rx"
	}
	if th := p.Config.LiveATC.TxRMSThresh; th > 0 {
		if meanRMS(seg.Samples) > float64(th) {
			return "tx"
		}
	}
	return "unknown"
}

// sttWorker transcribes queued segments, writes the transcript back into the
// WAV, and publishes the completed record.
func (p *Pipeline) sttWorker(n int, ctx, sttCtx context.Context) {
	defer p.wg.Done()
	log := p.log().With("worker", n)
	for {
		var job sttJob
		select {
		case <-ctx.Done():
			return
		default:
		}
		select {
		case <-ctx.Done():
			return
		case j, ok := <-p.jobs:
			if !ok {
				return
			}
			job = j
		}

		res, err := p.Transcriber.Transcribe(sttCtx, job.wavPath)
		// A configured --prompt can make whisper.cpp error or emit nothing on some
		// clips; since segments are VAD-gated speech, retry once without it.
		if p.Transcriber.HasPrompt() && sttCtx.Err() == nil &&
			(err != nil || strings.TrimSpace(res.Text) == "") {
			log.Warn("transcription empty/failed with --prompt; retrying without it",
				"id", job.id, "err", err)
			if r2, e2 := p.Transcriber.TranscribeWithoutPrompt(sttCtx, job.wavPath); e2 == nil {
				res, err = r2, nil
			}
		}
		if err != nil {
			if sttCtx.Err() != nil {
				return
			}
			log.Error("transcription failed", "id", job.id, "err", err)
			res = stt.Result{Model: "error"}
		}

		info := job.infoBase
		info.IKEY = res.Text
		if err := audio.WriteWAV(job.wavPath, job.samples, p.Config.LiveATC.Audio.SampleRate, info); err != nil {
			log.Warn("rewrite wav with transcript failed", "id", job.id, "err", err)
		}

		rec := transcript.TransmissionRecord{
			ID:         job.id,
			SessionID:  p.Session.ID,
			StartTime:  job.start,
			EndTime:    job.end,
			DurationMs: int(job.end.Sub(job.start).Milliseconds()),
			AudioFile:  job.relPath,
			Transcript: res.Text,
			Words:      res.Words,
			GPSStart:   job.gpsStart,
			GPSEnd:     job.gpsEnd,
			Confidence: res.Confidence,
			Direction:  job.dir,
			Channel:    job.channel,
			ModelUsed:  res.Model,
		}
		if err := p.Writer.Append(rec); err != nil {
			log.Error("append transcript", "id", job.id, "err", err)
		}
		p.Store.Add(rec)
		log.Info("transcribed", "id", job.id, "channel", job.channel, "text", res.Text)
	}
}

func (p *Pipeline) log() *slog.Logger { return p.Log }

// gpsComment is the shape embedded in the WAV ICMT chunk + serialized to JSON.
type gpsComment struct {
	Start    gps.GPSFix  `json:"start"`
	End      *gps.GPSFix `json:"end,omitempty"`
	GPSValid bool        `json:"gps_valid"`
}

func gpsCommentJSON(start, end gps.GPSFix) string {
	c := gpsComment{Start: start, GPSValid: start.Valid}
	if end != start {
		c.End = &end
	}
	b, err := json.Marshal(c)
	if err != nil {
		return ""
	}
	return string(b)
}

func meanRMS(samples []int16) float64 {
	if len(samples) == 0 {
		return 0
	}
	var sum float64
	for _, s := range samples {
		f := float64(s)
		sum += f * f
	}
	return math.Sqrt(sum / float64(len(samples)))
}
