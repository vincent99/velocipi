package music

import (
	"bufio"
	"bytes"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// LyricLine is one timed lyric entry parsed from an LRC file.
type LyricLine struct {
	TimeSec float64 `json:"timeSec"`
	Text    string  `json:"text"`
}

// lrcTimestampRe matches [mm:ss.xx] or [mm:ss.xxx] timestamps inside an LRC line.
var lrcTimestampRe = regexp.MustCompile(`\[(\d{1,2}):(\d{2})\.(\d{2,3})\]`)

// lrcPath returns the companion .lrc path for a music file.
func lrcPath(musicPath string) string {
	ext := filepath.Ext(musicPath)
	return musicPath[:len(musicPath)-len(ext)] + ".lrc"
}

// parseLRC parses LRC file bytes into a slice of LyricLine sorted by time.
// Lines with no numeric timestamp (e.g. metadata tags like [ti:...]) are skipped.
func parseLRC(data []byte) []LyricLine {
	var out []LyricLine
	scanner := bufio.NewScanner(bytes.NewReader(data))
	for scanner.Scan() {
		raw := strings.TrimSpace(scanner.Text())
		if raw == "" {
			continue
		}
		matches := lrcTimestampRe.FindAllStringSubmatchIndex(raw, -1)
		if len(matches) == 0 {
			continue
		}
		// Text follows the last timestamp tag.
		text := strings.TrimSpace(raw[matches[len(matches)-1][1]:])
		for _, m := range matches {
			mm, _ := strconv.Atoi(raw[m[2]:m[3]])
			ss, _ := strconv.Atoi(raw[m[4]:m[5]])
			frac := raw[m[6]:m[7]]
			var cs int
			switch len(frac) {
			case 2:
				cs, _ = strconv.Atoi(frac)
			case 3:
				ms, _ := strconv.Atoi(frac)
				cs = ms / 10
			}
			out = append(out, LyricLine{
				TimeSec: float64(mm*60+ss) + float64(cs)/100.0,
				Text:    text,
			})
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].TimeSec < out[j].TimeSec })
	return out
}
