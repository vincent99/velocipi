package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"image"
	"image/png"
	"log"
	"os"
	"sync/atomic"
	"time"

	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"github.com/vincent99/velocipi/server/hardware"
)

// pngToImage opens a PNG file and returns it as an image.
func pngToImage(path string) (image.Image, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return png.Decode(f)
}

// runScreencastLoop uses Page.startScreencast to receive frames pushed by
// Chromium, forwarding each to screen clients and the OLED display.
// Ping messages are sent on a separate ticker.
func (h *Hub) runScreencastLoop(ctx context.Context) {
	pingTicker := time.NewTicker(h.cfg.PingIntervalDur)
	defer pingTicker.Stop()

	// Send pings independently of the screencast.
	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			case ts := <-pingTicker.C:
				h.broadcastAll(PingMsg{Type: "ping", Time: ts.Format(time.RFC3339)})
			}
		}
	}()

	// Wait for the browser context to be ready.
	var bctx context.Context
	for {
		h.mu.RLock()
		bctx = h.browserCtx
		h.mu.RUnlock()
		if bctx != nil {
			break
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(50 * time.Millisecond):
		}
	}

	minInterval := time.Second / time.Duration(h.cfg.Screen.FPS)
	var lastFrame time.Time

	// splashDone is set to true once the splash screen has finished displaying.
	// Until then, screencast frames are acked but not blitted to the OLED.
	var splashDone atomic.Bool

	// Listen for screencast frames pushed by Chromium.
	chromedp.ListenTarget(bctx, func(ev any) {
		frame, ok := ev.(*page.EventScreencastFrame)
		if !ok {
			return
		}

		// Ack immediately so Chromium keeps sending frames regardless of throttle.
		go func() {
			_ = chromedp.Run(bctx, page.ScreencastFrameAck(frame.SessionID))
		}()

		// Throttle output to the configured FPS.
		now := time.Now()
		if now.Sub(lastFrame) < minInterval {
			return
		}
		lastFrame = now

		buf, err := base64.StdEncoding.DecodeString(frame.Data)
		if err != nil {
			log.Println("screencast: base64 decode error:", err)
			return
		}

		// Always store the latest frame so new clients and post-splash blit have it.
		h.lastFrameMu.Lock()
		h.lastFrame = buf
		h.lastFrameMu.Unlock()

		// Forward to browser clients regardless of splash state.
		h.broadcastScreen(buf)

		// Don't blit to OLED until splash is done.
		if !splashDone.Load() {
			return
		}

		if h.oled != nil {
			if img, err := png.Decode(bytes.NewReader(buf)); err == nil {
				h.oled.Blit(img)
			} else {
				log.Println("oled: png decode error:", err)
			}
		}
	})

	// Start the screencast — Chromium will now push frames as they change.
	if err := chromedp.Run(bctx, page.StartScreencast().
		WithFormat(page.ScreencastFormatPng).
		WithMaxWidth(int64(h.cfg.UI.Panel.Width)).
		WithMaxHeight(int64(h.cfg.UI.Panel.Height)),
	); err != nil {
		log.Println("screencast: start error:", err)
		return
	}
	log.Println("screencast: started")

	// Show the splash screen on the OLED for 5 seconds, then hand off to
	// the live screencast and turn the LED off.
	go func() {
		if h.oled != nil {
			if img, err := pngToImage(h.cfg.Screen.SplashImage); err != nil {
				log.Println("splash: load error:", err)
			} else {
				h.oled.Blit(img)
				log.Println("splash: showing logo")
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(h.cfg.SplashDurationDur):
		}
		splashDone.Store(true)
		log.Println("splash: done, switching to screencast")
		// Blit the last received frame immediately so the OLED updates
		// even if Chromium hasn't sent a new frame since the splash started.
		h.lastFrameMu.RLock()
		buf := h.lastFrame
		h.lastFrameMu.RUnlock()
		if buf != nil && h.oled != nil {
			if img, err := png.Decode(bytes.NewReader(buf)); err == nil {
				h.oled.Blit(img)
			}
		}
		if e := hardware.Expander(); e != nil {
			hardware.LED().Off(e)
		}
	}()

	<-ctx.Done()

	_ = chromedp.Run(bctx, page.StopScreencast())
}
