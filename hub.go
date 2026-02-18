package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"log"
	"math"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"github.com/gorilla/websocket"
	"github.com/vincent99/velocipi-go/config"
	"github.com/vincent99/velocipi-go/hardware"
	"github.com/vincent99/velocipi-go/hardware/airsensor"
	"github.com/vincent99/velocipi-go/hardware/tpms"
)

// Outbound message types. Each has a fixed Type field so the JSON consumer
// always knows exactly which fields will be present.

type PingMsg struct {
	Type string `json:"type"` // always "ping"
	Time string `json:"time"`
}

type ScreenshotMsg struct {
	Type string `json:"type"` // always "screenshot"
	Data string `json:"data"`
}

type AirReadingMsg struct {
	Type    string            `json:"type"` // always "airReading"
	Reading airsensor.Reading `json:"reading"`
}

type LuxReadingMsg struct {
	Type string  `json:"type"` // always "luxReading"
	Lux  float64 `json:"lux"`
}

type TpmsMsg struct {
	Type string     `json:"type"` // always "tpms"
	Tire *tpms.Tire `json:"tire"`
}

// inboundMsg is used only for parsing the "type" field of client messages.
type inboundMsg struct {
	Type string `json:"type"`
}

type client struct {
	conn        *websocket.Conn
	send        chan []byte
	mu          sync.Mutex
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
	cfg        *config.Config
}

func newHub(browserCtx context.Context, cfg *config.Config) *Hub {
	return &Hub{
		clients:    make(map[*client]struct{}),
		browserCtx: browserCtx,
		cfg:        cfg,
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
func (h *Hub) broadcast(msg any) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Println("hub marshal error:", err)
		return
	}
	h.marshalAndSend(data, func(c *client) bool { return c.isScreenshotsEnabled() })
}

// broadcastAll sends to every connected client.
func (h *Hub) broadcastAll(msg any) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Println("hub marshal error:", err)
		return
	}
	h.marshalAndSend(data, func(*client) bool { return true })
}

// sendReading sends the current air sensor reading to a single client.
func (h *Hub) sendReading(c *client) {
	s := hardware.AirSensor(h.cfg)
	if s == nil {
		return
	}
	r, err := s.Read()
	if err != nil {
		log.Println("hub: airsensor read error:", err)
		return
	}
	data, err := json.Marshal(AirReadingMsg{Type: "airReading", Reading: *r})
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// runAirSensorLoop polls the air sensor and broadcasts any changed reading
// to all connected clients.
func (h *Hub) runAirSensorLoop(ctx context.Context) {
	s := hardware.AirSensor(h.cfg)
	if s == nil {
		log.Println("hub: airsensor unavailable, skipping poll loop")
		return
	}

	ticker := time.NewTicker(h.cfg.AirSensorInterval)
	defer ticker.Stop()

	var last *airsensor.Reading

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r, err := s.Read()
			if err != nil {
				log.Println("hub: airsensor read error:", err)
				continue
			}
			if last != nil && *r == *last {
				continue
			}
			last = r
			data, err := json.Marshal(AirReadingMsg{Type: "airReading", Reading: *r})
			if err != nil {
				continue
			}
			h.marshalAndSend(data, func(*client) bool { return true })
		}
	}
}

// sendLux sends the current ambient lux reading to a single client.
func (h *Hub) sendLux(c *client) {
	s := hardware.LightSensor(h.cfg)
	if s == nil {
		return
	}
	lux, err := s.GetAmbientLux()
	if err != nil {
		log.Println("hub: lightsensor read error:", err)
		return
	}
	data, err := json.Marshal(LuxReadingMsg{Type: "luxReading", Lux: lux})
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// runLightSensorLoop polls the light sensor and broadcasts any changed lux
// value to all connected clients.
func (h *Hub) runLightSensorLoop(ctx context.Context) {
	s := hardware.LightSensor(h.cfg)
	if s == nil {
		log.Println("hub: lightsensor unavailable, skipping poll loop")
		return
	}

	ticker := time.NewTicker(h.cfg.LightSensorInterval)
	defer ticker.Stop()

	const threshold = 1.0 // lux change required to trigger a broadcast
	last := -1.0

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			lux, err := s.GetAmbientLux()
			if err != nil {
				log.Println("hub: lightsensor read error:", err)
				continue
			}
			if last >= 0 && math.Abs(lux-last) < threshold {
				continue
			}
			last = lux
			data, err := json.Marshal(LuxReadingMsg{Type: "luxReading", Lux: lux})
			if err != nil {
				continue
			}
			h.marshalAndSend(data, func(*client) bool { return true })
		}
	}
}

// sendTpms sends the current state of all known tires to a single client.
func (h *Hub) sendTpms(c *client) {
	t := hardware.TPMS(h.cfg)
	if t == nil {
		return
	}
	for _, tire := range t.Tires() {
		data, err := json.Marshal(TpmsMsg{Type: "tpms", Tire: tire})
		if err != nil {
			continue
		}
		select {
		case c.send <- data:
		default:
		}
	}
}

// runTpmsLoop listens for tire updates and broadcasts each change to all clients.
func (h *Hub) runTpmsLoop(ctx context.Context) {
	t := hardware.TPMS(h.cfg)
	if t == nil {
		log.Println("hub: tpms unavailable, skipping loop")
		return
	}

	for {
		select {
		case <-ctx.Done():
			return
		case tire := <-t.Updates():
			data, err := json.Marshal(TpmsMsg{Type: "tpms", Tire: tire})
			if err != nil {
				continue
			}
			h.marshalAndSend(data, func(*client) bool { return true })
		}
	}
}

// runScreenshotLoop takes screenshots of the global browser instance and
// broadcasts them to all connected clients. It only captures when at least
// one client is connected.
func (h *Hub) runScreenshotLoop(ctx context.Context) {
	interval := time.Second / time.Duration(h.cfg.ScreenshotFPS)

	pingTicker := time.NewTicker(h.cfg.PingInterval)
	defer pingTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case ts := <-pingTicker.C:
			h.broadcastAll(PingMsg{Type: "ping", Time: ts.Format(time.RFC3339)})
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
		h.broadcast(ScreenshotMsg{Type: "screenshot", Data: base64.StdEncoding.EncodeToString(buf)})

		if elapsed := time.Since(start); elapsed < interval {
			time.Sleep(interval - elapsed)
		}
	}
}

// loadAppPage fetches app/index.html from the live server, injects a <base href>,
// and navigates the given browser context to a data: URL containing the HTML.
func loadAppPage(browserCtx context.Context) error {
	resp, err := http.Get("http://localhost:8080/app/")
	if err != nil {
		return err
	}
	htmlBytes, _ := io.ReadAll(resp.Body)
	resp.Body.Close()

	html := string(htmlBytes)
	const baseTag = `<base href="http://localhost:8080/app/">`
	if idx := strings.Index(html, "<head>"); idx >= 0 {
		html = html[:idx+6] + baseTag + html[idx+6:]
	} else {
		html = baseTag + html
	}

	dataURL := "data:text/html;base64," + base64.StdEncoding.EncodeToString([]byte(html))
	return chromedp.Run(browserCtx, chromedp.ActionFunc(func(ctx context.Context) error {
		_, _, _, _, err := page.Navigate(dataURL).Do(ctx)
		return err
	}))
}

// reload re-fetches and re-injects the app HTML into the existing browser instance.
func (h *Hub) reload() {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		log.Println("reload: no browser context")
		return
	}
	log.Println("reload: reloading app...")
	if err := loadAppPage(bctx); err != nil {
		log.Println("reload error:", err)
	} else {
		log.Println("reload: done")
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

	if err := loadAppPage(browserCtx); err != nil {
		log.Println("browser: load error:", err)
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
