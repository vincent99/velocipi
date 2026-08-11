package config

import (
	"os"
	"path/filepath"
	"time"
)

// AudioConfig holds capture settings. See config.default.yaml for docs.
type AudioConfig struct {
	AudioDevice string `yaml:"audioDevice" json:"audioDevice"`
	SampleRate  int    `yaml:"sampleRate"  json:"sampleRate"`
	ArecordBin  string `yaml:"arecordBin"  json:"arecordBin"`
	FFmpegBin   string `yaml:"ffmpegBin"   json:"ffmpegBin"`
}

// VADConfig holds voice-activity-detection / segmentation parameters.
type VADConfig struct {
	Engine       string  `yaml:"engine"       json:"engine"`
	SileroPython string  `yaml:"sileroPython" json:"sileroPython"`
	SileroScript string  `yaml:"sileroScript" json:"sileroScript"`
	SileroOnnx   string  `yaml:"sileroOnnx"   json:"sileroOnnx"` // path to the Silero ONNX model; passed to the sidecar as SILERO_ONNX. Empty = torch.hub backend.
	Threshold    float64 `yaml:"threshold"    json:"threshold"`

	MinSpeechMs  int `yaml:"min_speech_ms"  json:"min_speech_ms"`
	MinSilenceMs int `yaml:"min_silence_ms" json:"min_silence_ms"`
	MaxSegmentMs int `yaml:"max_segment_ms" json:"max_segment_ms"`
	PreRollMs    int `yaml:"pre_roll_ms"    json:"pre_roll_ms"`

	// Carrier gate: bound transmissions by the radio carrier (frame energy)
	// instead of speech pauses. CarrierFloor is the RMS (0..32767) above which
	// the channel is "keyed"; CarrierHangoverMs is how long it must stay below
	// that to close the transmission. CarrierFloor 0 disables carrier gating.
	CarrierFloor      float64 `yaml:"carrier_floor"       json:"carrier_floor"`
	CarrierHangoverMs int     `yaml:"carrier_hangover_ms" json:"carrier_hangover_ms"`
}

// WhisperConfig holds whisper.cpp CLI integration settings.
type WhisperConfig struct {
	Binary   string `yaml:"binary"   json:"binary"`
	Model    string `yaml:"model"    json:"model"`
	ModelDir string `yaml:"modelDir" json:"modelDir"`
	ATCModel string `yaml:"atcModel" json:"atcModel"`
	Language string `yaml:"language" json:"language"`
	Threads  int    `yaml:"threads"  json:"threads"`
	Workers  int    `yaml:"workers"  json:"workers"`
}

// ModelPath returns the effective model file: the ATC model in ModelDir if
// configured and present, otherwise the default Model.
func (w WhisperConfig) ModelPath() string {
	if w.ATCModel != "" {
		p := filepath.Join(w.ModelDir, w.ATCModel)
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return w.Model
}

// LiveATCConfig groups all liveatc-specific subsystems.
type LiveATCConfig struct {
	// Addr is the internal transcript API / websocket server listen address.
	Addr string `yaml:"addr" json:"addr"`
	// LogLevel is the slog level: debug | info | warn | error.
	LogLevel string `yaml:"logLevel" json:"logLevel"`

	Audio   AudioConfig   `yaml:"audio"   json:"audio"`
	VAD     VADConfig     `yaml:"vad"     json:"vad"`
	Whisper WhisperConfig `yaml:"whisper" json:"whisper"`

	PTTPin       string `yaml:"pttPin"         json:"pttPin"`
	PTTChip      string `yaml:"pttChip"        json:"pttChip"`
	PTTActiveLow bool   `yaml:"pttActiveLow"   json:"pttActiveLow"`
	TxRMSThresh  int    `yaml:"txRmsThreshold" json:"txRmsThreshold"`
}

// StorageConfig holds filesystem roots.
type StorageConfig struct {
	LiveATC string `yaml:"liveatc" json:"liveatc"`
}

// Config is the subset of the shared velocipi configuration document that the
// intercom-stt process cares about. It reads the same config.default.yaml /
// config.yaml as the main velocipi backend; unrelated keys are ignored.
type Config struct {
	// TailNumber is the aircraft identifier (shared with velocipi), recorded in
	// the session manifest.
	TailNumber string        `yaml:"tailNumber" json:"tailNumber"`
	LiveATC    LiveATCConfig `yaml:"liveatc"    json:"liveatc"`
	Storage    StorageConfig `yaml:"storage"    json:"storage"`
}

// Derived, non-serialized durations populated by Load().
type Durations struct {
	MinSpeech       time.Duration
	MinSilence      time.Duration
	MaxSegment      time.Duration
	PreRoll         time.Duration
	CarrierHangover time.Duration
}

// VADDurations converts the millisecond VAD fields into time.Durations.
func (c *Config) VADDurations() Durations {
	ms := func(n int) time.Duration { return time.Duration(n) * time.Millisecond }
	return Durations{
		MinSpeech:       ms(c.LiveATC.VAD.MinSpeechMs),
		MinSilence:      ms(c.LiveATC.VAD.MinSilenceMs),
		MaxSegment:      ms(c.LiveATC.VAD.MaxSegmentMs),
		PreRoll:         ms(c.LiveATC.VAD.PreRollMs),
		CarrierHangover: ms(c.LiveATC.VAD.CarrierHangoverMs),
	}
}

// Load reads config.default.yaml then config.yaml (override) from dir, applies
// AUDIO_DEVICE env override, and returns the effective config.
func Load(dir string) (*Config, error) {
	res, err := LoadLayered[Config](
		filepath.Join(dir, "config.default.yaml"),
		filepath.Join(dir, "config.yaml"),
	)
	if err != nil {
		return nil, err
	}
	cfg := res.Effective

	// Env override for the audio device, per spec (AUDIO_DEVICE=hw:1,0).
	if dev := os.Getenv("AUDIO_DEVICE"); dev != "" {
		cfg.LiveATC.Audio.AudioDevice = dev
	}

	return cfg, nil
}
