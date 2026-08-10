package audio

import (
	"bytes"
	"encoding/binary"
	"os"
	"path/filepath"
)

// INFO holds the RIFF LIST/INFO metadata embedded in each segment WAV so the
// file is self-contained and independently useful.
//
//	ICRD -- ISO8601 timestamp of transmission start
//	ICMT -- JSON blob with GPS state at time of transmission
//	ISRC -- source, e.g. "cockpit-intercom"
//	IKEY -- transcript text (written back after STT completes)
type INFO struct {
	ICRD string // creation date
	ICMT string // comment (GPS JSON)
	ISRC string // source
	IKEY string // keywords -- we use it for the transcript
}

// WriteWAV writes 16-bit mono PCM at sampleRate to path (creating parent dirs),
// embedding the given INFO as a LIST/INFO chunk. Empty INFO fields are omitted.
func WriteWAV(path string, samples []int16, sampleRate int, info INFO) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}

	const (
		channels      = 1
		bitsPerSample = 16
	)
	blockAlign := channels * bitsPerSample / 8
	byteRate := sampleRate * blockAlign
	dataSize := len(samples) * 2

	listChunk := buildListInfo(info)

	var buf bytes.Buffer
	// RIFF header. riffSize = everything after "RIFF"+size (i.e. from "WAVE").
	riffSize := 4 + (8 + 16) + len(listChunk) + (8 + dataSize)
	buf.WriteString("RIFF")
	writeU32(&buf, uint32(riffSize))
	buf.WriteString("WAVE")

	// fmt chunk.
	buf.WriteString("fmt ")
	writeU32(&buf, 16)
	writeU16(&buf, 1) // PCM
	writeU16(&buf, channels)
	writeU32(&buf, uint32(sampleRate))
	writeU32(&buf, uint32(byteRate))
	writeU16(&buf, uint16(blockAlign))
	writeU16(&buf, bitsPerSample)

	// LIST/INFO chunk.
	buf.Write(listChunk)

	// data chunk.
	buf.WriteString("data")
	writeU32(&buf, uint32(dataSize))
	for _, s := range samples {
		writeU16(&buf, uint16(s))
	}

	return os.WriteFile(path, buf.Bytes(), 0o644)
}

// buildListInfo returns a complete "LIST"...."INFO"... chunk (with header) for
// the non-empty fields of info, or nil if all fields are empty.
func buildListInfo(info INFO) []byte {
	subs := []struct{ id, val string }{
		{"ICRD", info.ICRD},
		{"ISRC", info.ISRC},
		{"ICMT", info.ICMT},
		{"IKEY", info.IKEY},
	}

	var body bytes.Buffer
	body.WriteString("INFO")
	any := false
	for _, s := range subs {
		if s.val == "" {
			continue
		}
		any = true
		body.WriteString(s.id)
		// RIFF strings are NUL-terminated; the size includes the terminator and
		// the chunk is padded to an even length.
		data := append([]byte(s.val), 0)
		writeU32(&body, uint32(len(data)))
		body.Write(data)
		if len(data)%2 == 1 {
			body.WriteByte(0)
		}
	}
	if !any {
		return nil
	}

	var out bytes.Buffer
	out.WriteString("LIST")
	writeU32(&out, uint32(body.Len()))
	out.Write(body.Bytes())
	return out.Bytes()
}

func writeU16(b *bytes.Buffer, v uint16) { _ = binary.Write(b, binary.LittleEndian, v) }
func writeU32(b *bytes.Buffer, v uint32) { _ = binary.Write(b, binary.LittleEndian, v) }
