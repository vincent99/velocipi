package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"image/png"
	"io"
	"log"
	"math"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/cdproto/input"
	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	"github.com/gorilla/websocket"
	"github.com/vincent99/velocipi-go/config"
	"github.com/vincent99/velocipi-go/hardware"
	"github.com/vincent99/velocipi-go/hardware/airsensor"
	"github.com/vincent99/velocipi-go/hardware/expander"
	"github.com/vincent99/velocipi-go/hardware/oled"
	"github.com/vincent99/velocipi-go/hardware/tpms"
)

// Outbound message types. Each has a fixed Type field so the JSON consumer
// always knows exactly which fields will be present.

type PingMsg struct {
	Type string `json:"type"` // always "ping"
	Time string `json:"time"`
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

// Inbound message types from websocket clients.

type inboundMsg struct {
	Type string `json:"type"`
}

type inboundKeyMsg struct {
	EventType string `json:"eventType"` // "keydown" or "keyup"
	Key       string `json:"key"`
}

type client struct {
	conn *websocket.Conn
	send chan []byte
}

type Hub struct {
	mu            sync.RWMutex
	clients       map[*client]struct{}
	screenClients map[*client]struct{}
	browserCtx    context.Context
	cfg           *config.Config
	oled          *oled.OLED
}

func newHub(browserCtx context.Context, cfg *config.Config, o *oled.OLED) *Hub {
	return &Hub{
		clients:       make(map[*client]struct{}),
		screenClients: make(map[*client]struct{}),
		browserCtx:    browserCtx,
		cfg:           cfg,
		oled:          o,
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

func (h *Hub) registerScreen(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.screenClients[c] = struct{}{}
	log.Println("hub: screen client registered, total:", len(h.screenClients))
}

func (h *Hub) unregisterScreen(c *client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if _, ok := h.screenClients[c]; ok {
		delete(h.screenClients, c)
		close(c.send)
		log.Println("hub: screen client unregistered, total:", len(h.screenClients))
	}
}

func (h *Hub) screenshotClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.screenClients)
}

func (h *Hub) sendToClients(data []byte, clients map[*client]struct{}) {
	h.mu.RLock()
	snapshot := make([]*client, 0, len(clients))
	for c := range clients {
		snapshot = append(snapshot, c)
	}
	h.mu.RUnlock()

	for _, c := range snapshot {
		select {
		case c.send <- data:
		default:
		}
	}
}

// broadcastScreen sends raw PNG bytes as a binary frame to all /screen clients.
func (h *Hub) broadcastScreen(buf []byte) {
	h.sendToClients(buf, h.screenClients)
}

// broadcastAll sends to every /ws client.
func (h *Hub) broadcastAll(msg any) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Println("hub marshal error:", err)
		return
	}
	h.sendToClients(data, h.clients)
}

// sendReading sends the current air sensor reading to a single client.
func (h *Hub) sendReading(c *client) {
	s := hardware.AirSensor()
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
	s := hardware.AirSensor()
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
			h.sendToClients(data, h.clients)
		}
	}
}

// sendLux sends the current ambient lux reading to a single client.
func (h *Hub) sendLux(c *client) {
	s := hardware.LightSensor()
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
	s := hardware.LightSensor()
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
			h.sendToClients(data, h.clients)
		}
	}
}

// sendTpms sends the current state of all known tires to a single client.
func (h *Hub) sendTpms(c *client) {
	t := hardware.TPMS()
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
	t := hardware.TPMS()
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
			h.sendToClients(data, h.clients)
		}
	}
}

// runScreencastLoop uses Page.startScreencast to receive frames pushed by
// Chromium, forwarding each to screen clients and the OLED display.
// Ping messages are sent on a separate ticker.
func (h *Hub) runScreencastLoop(ctx context.Context) {
	pingTicker := time.NewTicker(h.cfg.PingInterval)
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

	minInterval := time.Second / time.Duration(h.cfg.ScreenshotFPS)
	var lastFrame time.Time

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

		if h.oled != nil {
			if img, err := png.Decode(bytes.NewReader(buf)); err == nil {
				h.oled.Blit(img)
			} else {
				log.Println("oled: png decode error:", err)
			}
		}

		h.broadcastScreen(buf)
	})

	// Start the screencast — Chromium will now push frames as they change.
	if err := chromedp.Run(bctx, page.StartScreencast().
		WithFormat(page.ScreencastFormatPng).
		WithMaxWidth(int64(h.cfg.OLEDWidth)).
		WithMaxHeight(int64(h.cfg.OLEDHeight)),
	); err != nil {
		log.Println("screencast: start error:", err)
		return
	}
	log.Println("screencast: started")

	<-ctx.Done()

	_ = chromedp.Run(bctx, page.StopScreencast())
}

// runInputLoop reads changes from the expander and fires chromedp keyboard events.
//
// Held inputs (joystick directions, knobCenter): keydown on press, keyup on release.
// Rotary encoders (outer, inner, joyKnob): single KeyEvent per detected step.
//
//	Outer knob:  '[' (left)  / ']' (right)
//	Inner knob:  ';' (left)  / '\'' (right)
//	Joy knob:    ',' (left)  / '.' (right)
func (h *Hub) runInputLoop(ctx context.Context) {
	e := hardware.Expander()
	if e == nil {
		log.Println("hub: expander unavailable, skipping input loop")
		return
	}

	cfg := config.Load()

	// Track previous quadrature state for each encoder.
	var prevInner, prevOuter, prevJoyKnob uint8

	for {
		select {
		case <-ctx.Done():
			return
		case ch, ok := <-e.Updates():
			if !ok {
				return
			}
			h.handleChange(ch, cfg, &prevInner, &prevOuter, &prevJoyKnob)
		}
	}
}

// jsKeyToKb maps JavaScript e.key values to their chromedp/kb rune constants.
// kb uses private Unicode codepoints for non-printable keys.
var jsKeyToKb = map[string]string{
	"ArrowLeft":  kb.ArrowLeft,
	"ArrowRight": kb.ArrowRight,
	"ArrowUp":    kb.ArrowUp,
	"ArrowDown":  kb.ArrowDown,
	"Enter":      kb.Enter,
}

func (h *Hub) dispatchKey(typ input.KeyType, key string) {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		return
	}

	// Translate JS key name to kb rune constant if needed.
	if mapped, ok := jsKeyToKb[key]; ok {
		key = mapped
	}

	runes := []rune(key)
	if len(runes) == 0 {
		return
	}
	params := kb.Encode(runes[0])
	if len(params) == 0 {
		return
	}

	// Find the matching event type entry (keyDown is first, keyUp is last).
	var p *input.DispatchKeyEventParams
	for _, candidate := range params {
		if candidate.Type == typ {
			p = candidate
			break
		}
	}
	if p == nil {
		return
	}

	if err := chromedp.Run(bctx, chromedp.ActionFunc(func(ctx context.Context) error {
		return p.Do(ctx)
	})); err != nil {
		log.Println("hub: key dispatch error:", err)
	}
}

// handleKeyMsg is called when a browser client sends a "key" websocket message.
// It forwards the event into the chromedp browser instance.
func (h *Hub) handleKeyMsg(eventType, key string) {
	allowed := map[string]bool{
		"ArrowLeft": true, "ArrowRight": true, "ArrowUp": true, "ArrowDown": true,
		"Enter": true, "[": true, "]": true, ";": true, "'": true, ",": true, ".": true,
	}
	if !allowed[key] {
		return
	}
	switch eventType {
	case "keydown":
		h.dispatchKey(input.KeyDown, key)
	case "keyup":
		h.dispatchKey(input.KeyUp, key)
	case "keypress":
		h.sendKeyEvent(key)
	}
}

func (h *Hub) sendKeyEvent(key string) {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		return
	}
	if err := chromedp.Run(bctx, chromedp.KeyEvent(key)); err != nil {
		log.Println("hub: key event error:", err)
	}
}

// encoderKey returns the key to fire for a 2-bit quadrature encoder step,
// or "" if no step is detected. leftKey/rightKey are the keys for each direction.
func encoderKey(prev, cur uint8, leftKey, rightKey string) string {
	if prev == cur {
		return ""
	}
	// Only fire on rising clock edge (clk bit = 1).
	clk := cur & 1
	if clk != 1 {
		return ""
	}
	dir := (cur >> 1) & 1
	if clk == dir {
		return leftKey
	}
	return rightKey
}

func (h *Hub) handleChange(ch expander.Change, cfg *config.Config, prevInner, prevOuter, prevJoyKnob *uint8) {
	v := ch.Value
	p := ch.Previous

	bit := func(val uint16, n uint) bool { return val>>n&1 == 1 }
	pressed := func(n uint) bool { return !bit(p, n) && bit(v, n) }
	released := func(n uint) bool { return bit(p, n) && !bit(v, n) }

	// Joystick directions: keydown on press, keyup on release.
	// Direction bits only count when joyCenter is held.
	for _, d := range []struct {
		bit uint
		key string
	}{
		{cfg.BitJoyLeft, kb.ArrowLeft},
		{cfg.BitJoyRight, kb.ArrowRight},
		{cfg.BitJoyUp, kb.ArrowUp},
		{cfg.BitJoyDown, kb.ArrowDown},
	} {
		if pressed(d.bit) && bit(v, cfg.BitJoyCenter) {
			h.dispatchKey(input.KeyDown, d.key)
		}
		if released(d.bit) || (pressed(d.bit) && !bit(v, cfg.BitJoyCenter)) {
			h.dispatchKey(input.KeyUp, d.key)
		}
	}

	// Knob center: keydown on press, keyup on release.
	if pressed(cfg.BitKnobCenter) {
		h.dispatchKey(input.KeyDown, kb.Enter)
	}
	if released(cfg.BitKnobCenter) {
		h.dispatchKey(input.KeyUp, kb.Enter)
	}

	// Outer rotary encoder (bits BitKnobOuter and BitKnobOuter+1): '[' / ']'.
	curOuter := uint8(v>>cfg.BitKnobOuter) & 0x3
	if key := encoderKey(*prevOuter, curOuter, "[", "]"); key != "" {
		h.sendKeyEvent(key)
	}
	*prevOuter = curOuter

	// Inner rotary encoder (bits BitKnobInner and BitKnobInner+1): ';' / '\''.
	curInner := uint8(v>>cfg.BitKnobInner) & 0x3
	if key := encoderKey(*prevInner, curInner, ";", "'"); key != "" {
		h.sendKeyEvent(key)
	}
	*prevInner = curInner

	// Joy knob rotary encoder (bits BitJoyKnob and BitJoyKnob+1): ',' / '.'.
	curJoyKnob := uint8(v>>cfg.BitJoyKnob) & 0x3
	if key := encoderKey(*prevJoyKnob, curJoyKnob, ",", "."); key != "" {
		h.sendKeyEvent(key)
	}
	*prevJoyKnob = curJoyKnob
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
