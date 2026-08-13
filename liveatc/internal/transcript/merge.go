package transcript

import (
	"strings"
	"time"
)

// Merge combines an earlier transmission a with the immediately-later one b into
// a single record, as if it had been one transmission all along. The result
// keeps a's identity (ID, SessionID, AudioFile, StartTime) -- the caller is
// expected to concatenate a's then b's audio into a's WAV and delete b.
//
// Field handling:
//   - Transcript / Words: a then b (b's word offsets shifted past a's audio).
//   - Duration: sum (the concatenated audio length); EndTime: b's.
//   - GPS: start from a, end from b. Direction: kept if equal, else "unknown".
//   - Confidence: duration-weighted mean.
//   - Correction/Reviewed: if either had a correction, the merged correction is
//     their combined best text and it's marked reviewed; otherwise it's reviewed
//     only if both were.
func Merge(a, b TransmissionRecord, now time.Time) TransmissionRecord {
	m := a // inherits ID, SessionID, AudioFile, StartTime, GPSStart, ModelUsed

	m.Transcript = joinText(a.Transcript, b.Transcript)
	m.Words = mergeWords(a.Words, b.Words, a.DurationMs)
	m.DurationMs = a.DurationMs + b.DurationMs
	m.EndTime = b.EndTime
	m.GPSEnd = b.GPSEnd

	if a.Direction != b.Direction {
		m.Direction = "unknown"
	}
	if td := a.DurationMs + b.DurationMs; td > 0 {
		m.Confidence = (a.Confidence*float32(a.DurationMs) + b.Confidence*float32(b.DurationMs)) / float32(td)
	}

	if a.Correction != "" || b.Correction != "" {
		at := a.Correction
		if at == "" {
			at = a.Transcript
		}
		bt := b.Correction
		if bt == "" {
			bt = b.Transcript
		}
		m.Correction = joinText(at, bt)
		m.Reviewed, m.ReviewedAt, m.CorrectedAt = true, now, now
	} else {
		m.Correction = ""
		m.CorrectedAt = time.Time{}
		m.Reviewed = a.Reviewed && b.Reviewed
		if m.Reviewed {
			m.ReviewedAt = now
		} else {
			m.ReviewedAt = time.Time{}
		}
	}
	return m
}

func joinText(a, b string) string {
	return strings.TrimSpace(strings.TrimSpace(a) + " " + strings.TrimSpace(b))
}

// mergeWords appends b's word tokens after a's, shifting b's timings by offsetMs
// (the length of a's audio) so they line up with the concatenated audio.
func mergeWords(a, b []WordToken, offsetMs int) []WordToken {
	out := make([]WordToken, 0, len(a)+len(b))
	out = append(out, a...)
	for _, w := range b {
		w.StartMs += offsetMs
		w.EndMs += offsetMs
		out = append(out, w)
	}
	return out
}
