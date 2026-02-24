package main

import (
	"context"
	"log"
	"os"
	"os/exec"
)

// launchDisplayWindow starts a Chromium window on the local X display showing
// url. The process is killed when ctx is cancelled. This is best-effort:
// if chromium is not installed or DISPLAY is not set, the error is logged and
// the function returns without blocking startup.
func launchDisplayWindow(ctx context.Context, url string) {
	display := os.Getenv("DISPLAY")
	if display == "" {
		display = ":0"
	}

	args := []string{
		"--kiosk",
		"--no-sandbox",
		"--disable-infobars",
		"--noerrdialogs",
		"--disable-session-crashed-bubble",
		"--check-for-update-interval=31536000",
		"--password-store=basic",
		"--app=" + url,
	}

	// Try chromium-browser first (Raspberry Pi OS name), then chromium.
	binary := "chromium-browser"
	if _, err := exec.LookPath(binary); err != nil {
		binary = "chromium"
		if _, err := exec.LookPath(binary); err != nil {
			log.Println("display: chromium not found, skipping local display window")
			return
		}
	}

	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Env = append(os.Environ(), "DISPLAY="+display)
	cmd.Stdout = nil
	cmd.Stderr = nil

	log.Printf("display: launching %s on %s: %s", binary, display, url)
	if err := cmd.Start(); err != nil {
		log.Println("display: failed to start chromium:", err)
		return
	}

	// Wait in a goroutine so we can log unexpected exits.
	go func() {
		if err := cmd.Wait(); err != nil {
			if ctx.Err() == nil {
				log.Println("display: chromium exited:", err)
			}
		}
	}()
}
