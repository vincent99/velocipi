// Package stt wraps the whisper.cpp CLI (whisper-cli) as a subprocess: one
// invocation per WAV segment. Shelling out avoids cgo and keeps the model
// process isolated from the Go service.
package stt

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/vincent99/liveatc/internal/transcript"
)

// Result is the parsed transcription for one segment.
type Result struct {
	Text       string
	Words      []transcript.WordToken
	Confidence float32 // mean token probability
	Model      string
}

// Transcriber runs whisper-cli against WAV files.
type Transcriber struct {
	binary   string
	model    string
	language string
	threads  int
}

// New builds a Transcriber. modelPath is already resolved (base vs ATC model).
func New(binary, modelPath, language string, threads int) *Transcriber {
	if threads <= 0 {
		threads = 4
	}
	return &Transcriber{binary: binary, model: modelPath, language: language, threads: threads}
}

// Transcribe runs whisper-cli on wavPath and returns the parsed result.
//
// whisper.cpp flag notes (documented deviation from the original spec):
//   - The spec listed "--word-timestamps"; whisper.cpp has no such flag. Word
//     timing comes from the token offsets in the full JSON (-ojf), which we
//     merge back into whole words below.
//   - -oj / -ojf : write JSON (full, with per-token offsets + probabilities)
//   - -np        : no prints (the spec's --no-prints), suppresses progress
func (t *Transcriber) Transcribe(ctx context.Context, wavPath string) (Result, error) {
	tmpDir, err := os.MkdirTemp("", "liveatc-stt-")
	if err != nil {
		return Result{}, err
	}
	defer os.RemoveAll(tmpDir)
	outBase := filepath.Join(tmpDir, "out")

	cmd := exec.CommandContext(ctx, t.binary,
		"--model", t.model,
		"--language", t.language,
		"--threads", strconv.Itoa(t.threads),
		"--output-json-full",
		"--output-file", outBase,
		"--no-prints",
		"--file", wavPath,
	)
	if out, err := cmd.CombinedOutput(); err != nil {
		return Result{}, fmt.Errorf("whisper-cli: %w: %s", err, strings.TrimSpace(string(out)))
	}

	data, err := os.ReadFile(outBase + ".json")
	if err != nil {
		return Result{}, fmt.Errorf("read whisper json: %w", err)
	}
	res, err := parseWhisperJSON(data)
	if err != nil {
		return Result{}, err
	}
	res.Model = filepath.Base(t.model)
	return res, nil
}

// whisperJSON is the subset of whisper.cpp's -ojf output we consume.
type whisperJSON struct {
	Transcription []struct {
		Text   string `json:"text"`
		Tokens []struct {
			Text    string `json:"text"`
			Offsets struct {
				From int `json:"from"` // ms from clip start
				To   int `json:"to"`
			} `json:"offsets"`
			P float64 `json:"p"` // token probability
		} `json:"tokens"`
	} `json:"transcription"`
}

func parseWhisperJSON(data []byte) (Result, error) {
	var wj whisperJSON
	if err := json.Unmarshal(data, &wj); err != nil {
		return Result{}, fmt.Errorf("parse whisper json: %w", err)
	}

	var (
		textParts []string
		words     []transcript.WordToken
		cur       *transcript.WordToken
		curProbs  []float64
		allProbs  []float64
	)

	flush := func() {
		if cur == nil {
			return
		}
		cur.Word = strings.TrimSpace(cur.Word)
		if cur.Word != "" {
			cur.Confidence = meanF32(curProbs)
			words = append(words, *cur)
		}
		cur, curProbs = nil, nil
	}

	for _, seg := range wj.Transcription {
		textParts = append(textParts, strings.TrimSpace(seg.Text))
		for _, tok := range seg.Tokens {
			if isSpecialToken(tok.Text) {
				continue
			}
			allProbs = append(allProbs, tok.P)
			// whisper tokens carry a leading space at word boundaries; use that
			// to merge subword tokens back into whole words.
			if strings.HasPrefix(tok.Text, " ") || cur == nil {
				flush()
				cur = &transcript.WordToken{StartMs: tok.Offsets.From}
			}
			cur.Word += tok.Text
			cur.EndMs = tok.Offsets.To
			curProbs = append(curProbs, tok.P)
		}
	}
	flush()

	return Result{
		Text:       strings.TrimSpace(strings.Join(textParts, " ")),
		Words:      words,
		Confidence: meanF32(allProbs),
	}, nil
}

// isSpecialToken filters whisper control tokens like "[_BEG_]", "[_TT_123]".
func isSpecialToken(s string) bool {
	return strings.HasPrefix(strings.TrimSpace(s), "[_")
}

func meanF32(v []float64) float32 {
	if len(v) == 0 {
		return 0
	}
	var sum float64
	for _, x := range v {
		sum += x
	}
	return float32(sum / float64(len(v)))
}
