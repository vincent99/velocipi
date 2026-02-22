// thumbnails scans a recordings directory and:
//   - generates missing _thumb.jpg and _full.jpg for every .mp4 that lacks them
//   - deletes _thumb.jpg / _full.jpg files that have no matching .mp4
//
// Usage:
//
//	thumbnails [--dir <recordingsDir>] [--height <px>] [--dry-run]
//
// Defaults: dir="recordings", height=240.
package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func main() {
	dir := flag.String("dir", "recordings", "recordings root directory")
	height := flag.Int("height", 240, "thumbnail height in pixels")
	dryRun := flag.Bool("dry-run", false, "print actions without executing them")
	flag.Parse()

	if err := run(*dir, *height, *dryRun); err != nil {
		log.Fatal(err)
	}
}

func run(root string, height int, dryRun bool) error {
	dayEntries, err := os.ReadDir(root)
	if os.IsNotExist(err) {
		return fmt.Errorf("directory %q does not exist", root)
	}
	if err != nil {
		return err
	}

	var generated, deleted, skipped int

	for _, dayEntry := range dayEntries {
		if !dayEntry.IsDir() {
			continue
		}
		dayDir := filepath.Join(root, dayEntry.Name())
		files, err := os.ReadDir(dayDir)
		if err != nil {
			log.Printf("skip %s: %v", dayDir, err)
			continue
		}

		// Collect all basenames (without extension) of mp4 files.
		mp4Bases := make(map[string]struct{})
		for _, f := range files {
			if !f.IsDir() && strings.HasSuffix(f.Name(), ".mp4") {
				mp4Bases[strings.TrimSuffix(f.Name(), ".mp4")] = struct{}{}
			}
		}

		// For each MP4, generate missing thumbnails.
		for base := range mp4Bases {
			mp4File := filepath.Join(dayDir, base+".mp4")
			thumbFile := filepath.Join(dayDir, base+"_thumb.jpg")
			fullFile := filepath.Join(dayDir, base+"_full.jpg")

			needThumb := !fileExists(thumbFile)
			needFull := !fileExists(fullFile)

			if !needThumb && !needFull {
				skipped++
				continue
			}

			if needThumb {
				if dryRun {
					fmt.Printf("[dry-run] generate thumb: %s\n", thumbFile)
				} else {
					fmt.Printf("generating thumb: %s\n", thumbFile)
					if err := ffmpegFrame(mp4File, "scale=-2:"+fmt.Sprint(height), thumbFile); err != nil {
						log.Printf("thumb failed for %s: %v", mp4File, err)
					} else {
						generated++
					}
				}
			}

			if needFull {
				if dryRun {
					fmt.Printf("[dry-run] generate full:  %s\n", fullFile)
				} else {
					fmt.Printf("generating full:  %s\n", fullFile)
					if err := ffmpegFrame(mp4File, "", fullFile); err != nil {
						log.Printf("full failed for %s: %v", mp4File, err)
					} else {
						generated++
					}
				}
			}
		}

		// Delete orphaned JPEG files (no matching MP4).
		for _, f := range files {
			if f.IsDir() {
				continue
			}
			name := f.Name()
			var base string
			switch {
			case strings.HasSuffix(name, "_thumb.jpg"):
				base = strings.TrimSuffix(name, "_thumb.jpg")
			case strings.HasSuffix(name, "_full.jpg"):
				base = strings.TrimSuffix(name, "_full.jpg")
			default:
				continue
			}
			if _, ok := mp4Bases[base]; ok {
				continue // MP4 exists, not orphaned
			}
			path := filepath.Join(dayDir, name)
			if dryRun {
				fmt.Printf("[dry-run] delete orphan: %s\n", path)
			} else {
				fmt.Printf("deleting orphan: %s\n", path)
				if err := os.Remove(path); err != nil {
					log.Printf("remove failed: %v", err)
				} else {
					deleted++
				}
			}
		}
	}

	if dryRun {
		fmt.Println("[dry-run] done (no changes made)")
	} else {
		fmt.Printf("done: %d generated, %d deleted, %d already complete\n", generated, deleted, skipped)
	}
	return nil
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func ffmpegFrame(input, vf, output string) error {
	args := []string{"-i", input}
	if vf != "" {
		args = append(args, "-vf", vf)
	}
	args = append(args, "-frames:v", "1", "-q:v", "2", "-y", output)
	cmd := exec.Command("ffmpeg", args...)
	// Suppress ffmpeg's verbose output; show only on error.
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w\n%s", err, out)
	}
	return nil
}
