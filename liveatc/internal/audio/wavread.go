package audio

import (
	"encoding/binary"
	"fmt"
	"os"
)

// ReadWAV reads a 16-bit PCM WAV file (as written by WriteWAV) and returns its
// samples plus sample rate. It walks the RIFF chunks so LIST/INFO metadata is
// skipped; only the `fmt ` and `data` chunks are used. Assumes 16-bit samples.
func ReadWAV(path string) ([]int16, int, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, 0, err
	}
	if len(data) < 12 || string(data[0:4]) != "RIFF" || string(data[8:12]) != "WAVE" {
		return nil, 0, fmt.Errorf("not a RIFF/WAVE file: %s", path)
	}

	sampleRate := 0
	var samples []int16
	pos := 12
	for pos+8 <= len(data) {
		id := string(data[pos : pos+4])
		size := int(binary.LittleEndian.Uint32(data[pos+4 : pos+8]))
		body := pos + 8
		if size < 0 || body+size > len(data) {
			size = len(data) - body // tolerate a truncated final chunk
		}
		switch id {
		case "fmt ":
			if size >= 16 {
				sampleRate = int(binary.LittleEndian.Uint32(data[body+4 : body+8]))
			}
		case "data":
			n := size / 2
			samples = make([]int16, n)
			for i := 0; i < n; i++ {
				samples[i] = int16(binary.LittleEndian.Uint16(data[body+i*2:]))
			}
		}
		pos = body + size
		if size%2 == 1 {
			pos++ // chunks are word-aligned
		}
	}
	return samples, sampleRate, nil
}
