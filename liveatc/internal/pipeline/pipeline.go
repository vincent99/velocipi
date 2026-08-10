// Package pipeline wires the subsystems together: capture -> VAD segmentation
// -> per-transmission WAV -> whisper STT -> transcript persistence + broadcast.
package pipeline

import (
	"context"
	"encoding/json"
	"log/slog"
	"math"
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

// Deps are the collaborators the pipeline needs, built by main.
type Deps struct {
	Config      *config.Config
	Session     *session.Session
	Log         *slog.Logger
	Capture     *audio.Capture
	Scorer      vad.Scorer
	Transcriber *stt.Transcriber
	Store       *transcript.Store
	Writer      *transcript.Writer
	GPS         *gps.Store
	PTT         ptt.Monitor
}

// Pipeline owns the runtime loops.
type Pipeline struct {
	Deps
	seg  *vad.Segmenter
	jobs chan sttJob
	wg   sync.WaitGroup

	// pendingGPSStart is captured at transmission start and consumed when the
	// segment ends. The segmenter is single-goroutine so no lock is needed.
	pendingGPSStart gps.GPSFix
}

// sttJob is a finished segment awaiting transcription.
type sttJob struct {
	id       string
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
	vd := d.Config.VADDurations()
	p := &Pipeline{
		Deps: d,
		jobs: make(chan sttJob, 32),
	}
	p.seg = vad.NewSegmenter(vad.Params{
		SampleRate:   d.Config.LiveATC.Audio.SampleRate,
		FrameSamples: 512,
		Threshold:    d.Config.LiveATC.VAD.Threshold,
		MinSpeech:    vd.MinSpeech,
		MinSilence:   vd.MinSilence,
		MaxSegment:   vd.MaxSegment,
		PreRoll:      vd.PreRoll,
	}, time.Now)
	p.seg.OnSpeechStart = p.onSpeechStart
	p.seg.OnSegment = p.onSegment
	return p
}

// Run blocks until ctx is cancelled, then flushes the in-progress segment and
// drains queued STT jobs before returning.
func (p *Pipeline) Run(ctx context.Context) error {
	// STT worker pool. Workers use context.Background so queued jobs still
	// finish after ctx (SIGTERM) is cancelled.
	workers := p.Config.LiveATC.Whisper.Workers
	if workers <= 0 {
		workers = 2
	}
	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.sttWorker(i)
	}

	// Capture runs in its own goroutine; we consume its frames here.
	captureErr := make(chan error, 1)
	go func() { captureErr <- p.Capture.Run(ctx) }()

	p.log().Info("pipeline running", "session", p.Session.ID)
	p.consume(ctx)

	// Cleanup: flush any held transmission, then stop STT workers once drained.
	p.seg.Flush()
	close(p.jobs)
	p.wg.Wait()

	<-captureErr // let capture unwind
	return nil
}

// consume scores each frame and drives the segmenter until frames stop.
func (p *Pipeline) consume(ctx context.Context) {
	frames := p.Capture.Frames()
	for {
		select {
		case <-ctx.Done():
			// Drain whatever capture already produced, then stop.
			for frame := range frames {
				p.feed(frame)
			}
			return
		case frame, ok := <-frames:
			if !ok {
				return
			}
			p.feed(frame)
		}
	}
}

func (p *Pipeline) feed(frame []int16) {
	score, err := p.Scorer.Score(frame)
	if err != nil {
		// A scorer hiccup shouldn't wedge the stream; treat as silence.
		p.log().Debug("VAD score error", "err", err)
		score = 0
	}
	p.seg.Feed(frame, score)
}

// onSpeechStart snapshots GPS at the start of a confirmed transmission.
func (p *Pipeline) onSpeechStart(time.Time) {
	p.pendingGPSStart = p.GPS.Snapshot()
}

// onSegment persists the WAV + metadata and enqueues STT.
func (p *Pipeline) onSegment(seg vad.Segment) {
	id := uuid.NewString()
	gpsStart := p.pendingGPSStart
	gpsEnd := p.GPS.Snapshot()
	sampleRate := p.Config.LiveATC.Audio.SampleRate

	// callsign hint is filled in by a later post-processing pass; empty for now.
	wavPath := p.Session.AudioPath(seg.StartTime, "")

	info := audio.INFO{
		ICRD: seg.StartTime.UTC().Format(time.RFC3339),
		ISRC: "cockpit-intercom",
		ICMT: gpsCommentJSON(gpsStart, gpsEnd),
	}
	if err := audio.WriteWAV(wavPath, seg.Samples, sampleRate, info); err != nil {
		p.log().Error("write segment wav", "err", err, "path", wavPath)
		return
	}

	job := sttJob{
		id:       id,
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
		"id", id, "dur_ms", job.end.Sub(job.start).Milliseconds(), "dir", job.dir, "file", job.relPath)

	select {
	case p.jobs <- job:
	default:
		// Queue full: STT is falling behind. Drop the STT step but keep the WAV
		// (still self-contained on disk) rather than blocking capture.
		p.log().Warn("STT queue full, segment saved without transcript", "id", id, "file", job.relPath)
	}
}

// direction classifies tx/rx/unknown. See package ptt for the two strategies.
func (p *Pipeline) direction(seg vad.Segment, start time.Time) string {
	if p.PTT.Enabled() {
		// GPIO is definitive: keyed during the transmission => tx, else rx.
		if p.PTT.ActiveSince(seg.StartTime) {
			return "tx"
		}
		return "rx"
	}
	// Audio-level heuristic: louder sidetone suggests our own transmission.
	if th := p.Config.LiveATC.TxRMSThresh; th > 0 {
		if meanRMS(seg.Samples) > float64(th) {
			return "tx"
		}
	}
	return "unknown"
}

// sttWorker transcribes queued segments, writes the transcript back into the
// WAV, and publishes the completed record.
func (p *Pipeline) sttWorker(n int) {
	defer p.wg.Done()
	log := p.log().With("worker", n)
	for job := range p.jobs {
		// Background context: a queued job must finish even during shutdown.
		res, err := p.Transcriber.Transcribe(context.Background(), job.wavPath)
		if err != nil {
			log.Error("transcription failed", "id", job.id, "err", err)
			// Still publish a record (empty transcript) so the segment is tracked.
			res = stt.Result{Model: "error"}
		}

		// Write the transcript back into the WAV (IKEY) so the file is
		// self-contained (rewrite from retained samples + base INFO).
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
			ModelUsed:  res.Model,
		}
		if err := p.Writer.Append(rec); err != nil {
			log.Error("append transcript", "id", job.id, "err", err)
		}
		p.Store.Add(rec)
		log.Info("transcribed", "id", job.id, "text", res.Text)
	}
}

func (p *Pipeline) log() *slog.Logger { return p.Log }

// gpsComment is the shape embedded in the WAV ICMT chunk + serialized to JSON.
// End is a pointer so it is omitted entirely when identical to Start (a struct
// value can't be omitted via omitempty).
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
