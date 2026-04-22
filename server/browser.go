package main

import (
	"context"
	"fmt"
	"io/fs"
	"log"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
)

// findChromeHeadlessShell returns the path to the chrome-headless-shell binary.
// It first checks PATH, then searches the local ./chrome-headless-shell directory
// recursively for a file with the same base name.
func findChromeHeadlessShell() (string, error) {
	const bin = "chrome-headless-shell"
	if p, err := exec.LookPath(bin); err == nil {
		return p, nil
	}
	var found string
	_ = filepath.WalkDir("chrome-headless-shell", func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		if filepath.Base(path) == bin {
			found = path
			return fs.SkipAll
		}
		return nil
	})
	if found != "" {
		return found, nil
	}
	return "", fmt.Errorf("%s not found in PATH or ./chrome-headless-shell/", bin)
}

// initBrowser starts the headless Chromium instance.
// The app page is not loaded here — the caller must call navigateTo()
// once the HTTP server is ready.
func initBrowser(ctx context.Context) (context.Context, context.CancelFunc) {
	execPath, err := findChromeHeadlessShell()
	if err != nil {
		log.Println("browser:", err)
		return ctx, func() {}
	}
	log.Println("browser: using", execPath)

	allocCtx, cancelAlloc := chromedp.NewExecAllocator(ctx,
		chromedp.NoFirstRun,
		chromedp.NoDefaultBrowserCheck,
		chromedp.Flag("no-sandbox", true),
		chromedp.Flag("disable-dev-shm-usage", true),
		chromedp.Flag("disable-gpu", true),
		chromedp.Flag("password-store", "basic"),
		chromedp.WindowSize(256, 64),
		chromedp.ExecPath(execPath),
	)

	browserCtx, cancelBrowser := chromedp.NewContext(allocCtx, chromedp.WithLogf(log.Printf))

	// Trigger browser process creation with a no-op action.
	if err := chromedp.Run(browserCtx); err != nil {
		log.Println("browser: init error:", err)
		cancelBrowser()
		cancelAlloc()
		return ctx, func() {}
	}

	return browserCtx, func() {
		cancelBrowser()
		cancelAlloc()
	}
}

// navigateTo navigates the browser to url, waiting for the networkIdle event.
//
// On this platform (chromium-headless-shell on Raspberry Pi), page.Navigate
// never returns a CDP response for HTTP/HTTPS URLs, but the lifecycle events
// do fire. We listen on browserCtx (not a derived context — events are missed
// on child contexts) and wait for networkIdle before returning.
func navigateTo(browserCtx context.Context, url string) error {
	ready := make(chan struct{}, 1)
	chromedp.ListenTarget(browserCtx, func(ev any) {
		if v, ok := ev.(*page.EventLifecycleEvent); ok && v.Name == "networkIdle" {
			select {
			case ready <- struct{}{}:
			default:
			}
		}
	})

	go chromedp.Run(browserCtx, chromedp.ActionFunc(func(ctx context.Context) error {
		_, _, _, _, _ = page.Navigate(url).Do(ctx)
		return nil
	}))

	select {
	case <-ready:
		return nil
	case <-time.After(15 * time.Second):
		return fmt.Errorf("navigateTo %s: timed out waiting for networkIdle", url)
	case <-browserCtx.Done():
		return browserCtx.Err()
	}
}

// reload navigates the browser back to the app page.
func (h *Hub) reload() {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		log.Println("reload: no browser context")
		return
	}
	log.Println("reload: reloading app...")
	if err := navigateTo(bctx, h.cfg.AppURL); err != nil {
		log.Println("reload error:", err)
	} else {
		log.Println("reload: done")
	}
}

// navigate navigates the browser to a path relative to the app base URL.
func (h *Hub) navigate(path string) {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		log.Println("navigate: no browser context")
		return
	}
	base := strings.TrimRight(h.cfg.AppURL, "/")
	url := base + "/" + strings.TrimLeft(path, "/")
	log.Println("navigate:", url)
	if err := navigateTo(bctx, url); err != nil {
		log.Println("navigate error:", err)
	}
}
