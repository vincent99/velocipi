package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"github.com/gorilla/websocket"
)

type wsMessage struct {
	Type string `json:"type"`
	Time string `json:"time,omitempty"`
	Data string `json:"data,omitempty"`
}

type client struct {
	conn       *websocket.Conn
	send       chan []byte
	mu         sync.Mutex
	screenshots bool
}

func (c *client) enableScreenshots() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.screenshots = true
}

func (c *client) isScreenshotsEnabled() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.screenshots
}

type Hub struct {
	mu         sync.RWMutex
	clients    map[*client]struct{}
	browserCtx context.Context
}

func newHub(browserCtx context.Context) *Hub {
	return &Hub{
		clients:    make(map[*client]struct{}),
		browserCtx: browserCtx,
	}
}

func (h *Hub) register(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.clients[c] = struct{}{}
	log.Println("hub: client registered, total:", len(h.clients))
}

func (h *Hub) unregister(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if _, ok := h.clients[c]; ok {
		delete(h.clients, c)
		close(c.send)
		log.Println("hub: client unregistered, total:", len(h.clients))
	}
}

func (h *Hub) screenshotClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	n := 0
	for c := range h.clients {
		if c.isScreenshotsEnabled() {
			n++
		}
	}
	return n
}

func (h *Hub) marshalAndSend(data []byte, filter func(*client) bool) {
	h.mu.RLock()
	snapshot := make([]*client, 0, len(h.clients))
	for c := range h.clients {
		if filter(c) {
			snapshot = append(snapshot, c)
		}
	}
	h.mu.RUnlock()

	for _, c := range snapshot {
		select {
		case c.send <- data:
		default:
		}
	}
}

// broadcast sends to clients that have requested screenshots.
func (h *Hub) broadcast(msg wsMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Println("hub marshal error:", err)
		return
	}
	h.marshalAndSend(data, func(c *client) bool { return c.isScreenshotsEnabled() })
}

// broadcastAll sends to every connected client.
func (h *Hub) broadcastAll(msg wsMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Println("hub marshal error:", err)
		return
	}
	h.marshalAndSend(data, func(*client) bool { return true })
}

// runScreenshotLoop takes screenshots of the global browser instance and
// broadcasts them to all connected clients. It only captures when at least
// one client is connected.
func (h *Hub) runScreenshotLoop(ctx context.Context) {
	interval := time.Second / 25

	pingTicker := time.NewTicker(1 * time.Second)
	defer pingTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case ts := <-pingTicker.C:
			h.broadcastAll(wsMessage{Type: "ping", Time: ts.Format(time.RFC3339)})
		default:
		}

		h.mu.RLock()
		bctx := h.browserCtx
		h.mu.RUnlock()

		if h.screenshotClientCount() == 0 || bctx == nil {
			time.Sleep(50 * time.Millisecond)
			continue
		}

		start := time.Now()
		var buf []byte
		if err := chromedp.Run(bctx, chromedp.CaptureScreenshot(&buf)); err != nil {
			log.Println("screenshot error:", err)
			time.Sleep(interval)
			continue
		}
		h.broadcast(wsMessage{Type: "screenshot", Data: base64.StdEncoding.EncodeToString(buf)})

		if elapsed := time.Since(start); elapsed < interval {
			time.Sleep(interval - elapsed)
		}
	}
}

// initBrowser starts the headless browser and loads the app page.
//
// On this platform (Raspberry Pi + chromium-headless-shell), Page.navigate to
// HTTP URLs never returns a CDP response, so the page is loaded by:
//  1. Fetching the HTML from the live server via Go's HTTP client.
//  2. Injecting a <base href> so relative URLs resolve to the real server.
//  3. Navigating to a data: URL containing the HTML — data: navigation works
//     reliably, and the <base href> ensures sub-resources and WebSocket
//     connections resolve against http://localhost:8080.
//
// Note: render-blocking external sub-resources (scripts without defer/async,
// external stylesheets) will still stall CaptureScreenshot. Keep app/index.html
// self-contained or use defer/async on scripts.
func initBrowser(ctx context.Context) (context.Context, context.CancelFunc) {
	allocCtx, cancelAlloc := chromedp.NewExecAllocator(ctx,
		chromedp.NoFirstRun,
		chromedp.NoDefaultBrowserCheck,
		chromedp.Flag("no-sandbox", true),
		chromedp.Flag("disable-dev-shm-usage", true),
		chromedp.Flag("disable-gpu", true),
		chromedp.WindowSize(256, 64),
		chromedp.ExecPath("/usr/bin/chromium-headless-shell"),
	)

	browserCtx, cancelBrowser := chromedp.NewContext(allocCtx, chromedp.WithLogf(log.Printf))

	// Fetch the app HTML from the live server.
	resp, err := http.Get("http://localhost:8080/app/")
	if err != nil {
		log.Println("browser: could not fetch app HTML:", err)
		cancelBrowser()
		cancelAlloc()
		return ctx, func() {}
	}
	htmlBytes, _ := io.ReadAll(resp.Body)
	resp.Body.Close()

	// Inject <base href> so relative URLs and ws:// resolve against the server.
	html := string(htmlBytes)
	const baseTag = `<base href="http://localhost:8080/app/">`
	if idx := strings.Index(html, "<head>"); idx >= 0 {
		html = html[:idx+6] + baseTag + html[idx+6:]
	} else {
		html = baseTag + html
	}

	// Navigate to a data: URL — returns immediately, fires loadEventFired.
	dataURL := "data:text/html;base64," + base64.StdEncoding.EncodeToString([]byte(html))
	if err := chromedp.Run(browserCtx, chromedp.ActionFunc(func(ctx context.Context) error {
		_, _, _, _, err := page.Navigate(dataURL).Do(ctx)
		return err
	})); err != nil {
		log.Println("browser: navigate error:", err)
		cancelBrowser()
		cancelAlloc()
		return ctx, func() {}
	}
	log.Println("browser: app loaded via data: URL")

	return browserCtx, func() {
		cancelBrowser()
		cancelAlloc()
	}
}
