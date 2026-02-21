package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"image"
	"image/png"
	"log"
	"math"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/chromedp/cdproto/input"
	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	"github.com/gorilla/websocket"
	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/airsensor"
	"github.com/vincent99/velocipi/server/hardware/expander"
	"github.com/vincent99/velocipi/server/hardware/led"
	"github.com/vincent99/velocipi/server/hardware/oled"
	"github.com/vincent99/velocipi/server/hardware/tpms"
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

type LEDStateMsg struct {
	Type string `json:"type"`           // always "ledState"
	Mode string `json:"mode"`           // "off", "on", "blink"
	Rate int    `json:"rate,omitempty"` // blink rate in ms, only set when mode == "blink"
}

type KeyEchoMsg struct {
	Type      string `json:"type"`      // always "keyEcho"
	EventType string `json:"eventType"` // "keydown" or "keyup"
	Key       string `json:"key"`       // logical key name
}

// Inbound message types from websocket clients.

type inboundMsg struct {
	Type string `json:"type"`
}

type inboundKeyMsg struct {
	EventType string `json:"eventType"` // "keydown", "keyup", or "keypress"
	Key       string `json:"key"`
}

type inboundLEDMsg struct {
	State string `json:"state"`          // "off", "on", "blink"
	Rate  int    `json:"rate,omitempty"` // blink rate in ms, default 500
}

type inboundNavigateMsg struct {
	Path string `json:"path"` // URL path to navigate to, e.g. "/panel/test"
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

	lastFrameMu sync.RWMutex
	lastFrame   []byte // most recent decoded PNG from the screencast
}

func newHub(browserCtx context.Context, cfg *config.Config, o *oled.OLED) *Hub {
	h := &Hub{
		clients:       make(map[*client]struct{}),
		screenClients: make(map[*client]struct{}),
		browserCtx:    browserCtx,
		cfg:           cfg,
		oled:          o,
	}
	// Broadcast LED state to all clients whenever it changes.
	hardware.LED().OnChange(func(s led.State) {
		h.broadcastAll(ledStateMsg(s))
	})
	return h
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
	h.screenClients[c] = struct{}{}
	log.Println("hub: screen client registered, total:", len(h.screenClients))
	h.mu.Unlock()

	// Send the most recent frame immediately so the client doesn't see a blank screen.
	h.lastFrameMu.RLock()
	buf := h.lastFrame
	h.lastFrameMu.RUnlock()
	if buf != nil {
		select {
		case c.send <- buf:
		default:
		}
	}
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

// broadcastKeyEcho notifies all clients that a logical key event was dispatched.
func (h *Hub) broadcastKeyEcho(logical, eventType string) {
	h.broadcastAll(KeyEchoMsg{Type: "keyEcho", EventType: eventType, Key: logical})
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

	ticker := time.NewTicker(h.cfg.AirSensorIntervalDur)
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

	ticker := time.NewTicker(h.cfg.LightSensorIntervalDur)
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

// runInputLoop reads changes from the expander and fires chromedp keyboard events.
//
// Held inputs (joystick directions, knobCenter): keydown on press, keyup on release.
// Rotary encoders (outer, inner, joyKnob): single KeyEvent per detected step.
func (h *Hub) runInputLoop(ctx context.Context) {
	e := hardware.Expander()
	if e == nil {
		log.Println("hub: expander unavailable, skipping input loop")
		return
	}

	cfg := h.cfg

	inner := &knobState{prev: 0b11}
	outer := &knobState{prev: 0b11}
	joyKnob := &knobState{prev: 0b11}

	for {
		select {
		case <-ctx.Done():
			return
		case ch, ok := <-e.Updates():
			if !ok {
				return
			}
			h.handleChange(ch, cfg, inner, outer, joyKnob)
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

// logicalToJS returns a map from logical action names to the JS key values
// configured in config.yaml (ui.keyMap).
func (h *Hub) logicalToJS() map[string]string {
	km := h.cfg.UI.KeyMap
	return map[string]string{
		"up":          km.Up,
		"down":        km.Down,
		"left":        km.Left,
		"right":       km.Right,
		"enter":       km.Enter,
		"joy-left":    km.JoyLeft,
		"joy-right":   km.JoyRight,
		"inner-left":  km.InnerLeft,
		"inner-right": km.InnerRight,
		"outer-left":  km.OuterLeft,
		"outer-right": km.OuterRight,
	}
}

// dispatchLogical translates a logical name to a JS key, dispatches it to the
func (h *Hub) dispatchLogical(typ input.KeyType, logical string) {
	jsKey, ok := h.logicalToJS()[logical]
	if !ok {
		return
	}
	h.dispatchKey(typ, jsKey)
	eventType := "keydown"
	if typ == input.KeyUp {
		eventType = "keyup"
	}
	h.broadcastKeyEcho(logical, eventType)
}

func (h *Hub) dispatchKey(typ input.KeyType, jsKey string) {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		return
	}

	key := jsKey
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
		return
	}

}

// ledStateMsg builds a LEDStateMsg from a led.State.
func ledStateMsg(s led.State) LEDStateMsg {
	msg := LEDStateMsg{Type: "ledState", Mode: s.Mode}
	if s.Mode == "blink" {
		msg.Rate = int(s.Rate.Milliseconds())
	}
	return msg
}

// sendLEDState sends the current LED state to a single client.
func (h *Hub) sendLEDState(c *client) {
	l := hardware.LED()
	data, err := json.Marshal(ledStateMsg(l.CurrentState()))
	if err != nil {
		return
	}
	select {
	case c.send <- data:
	default:
	}
}

// handleLEDMsg controls the expander LED from a websocket message.
func (h *Hub) handleLEDMsg(state string, rateMs int) {
	e := hardware.Expander()
	if e == nil {
		return
	}
	l := hardware.LED()
	switch state {
	case "on":
		l.On(e)
	case "off":
		l.Off(e)
	case "blink":
		if rateMs <= 0 {
			rateMs = 500
		}
		l.Blink(e, time.Duration(rateMs)*time.Millisecond)
	}
}

// handleKeyMsg is called when a browser client sends a "key" websocket message.
// It forwards the event into the chromedp browser instance.
func (h *Hub) handleKeyMsg(eventType, key string) {
	jsKey, ok := h.logicalToJS()[key]
	if !ok {
		return
	}
	switch eventType {
	case "keydown":
		h.dispatchKey(input.KeyDown, jsKey)
	case "keyup":
		h.dispatchKey(input.KeyUp, jsKey)
	}
	h.broadcastKeyEcho(key, eventType)
}

func (h *Hub) sendLogical(logical string) {
	jsKey, ok := h.logicalToJS()[logical]
	if !ok {
		return
	}
	h.sendKeyEvent(jsKey)
	h.broadcastKeyEcho(logical, "keydown")
}

func (h *Hub) sendKeyEvent(jsKey string) {
	h.mu.RLock()
	bctx := h.browserCtx
	h.mu.RUnlock()
	if bctx == nil {
		return
	}
	if err := chromedp.Run(bctx, chromedp.KeyEvent(jsKey)); err != nil {
		log.Println("hub: key event error:", err)
	}
}

// quadTable maps (prev<<2)|cur to a step direction for all 16 possible
// 2-bit quadrature transitions. Valid single steps are ±1; invalid
// transitions (same state or 2-step jumps) are 0.
//
// Observed sequence for one right detent: 11→10→00→01→11 (+4 steps)
// Observed sequence for one left detent:  11→01→00→10→11 (-4 steps)
var quadTable = [16]int{
	//        cur: 00  01  10  11
	/* prev 00 */ 0, +1, -1, 0,
	/* prev 01 */ -1, 0, 0, +1,
	/* prev 10 */ +1, 0, 0, -1,
	/* prev 11 */ 0, -1, +1, 0,
}

// knobState accumulates quadrature steps and emits once per detent (2 steps).
type knobState struct {
	prev        uint8
	accumulated int
}

// update takes a new 2-bit quadrature sample and returns -1, 0, or +1 when
// a full detent (2 steps) is reached.
func (k *knobState) update(cur uint8) int {
	k.accumulated += quadTable[(k.prev<<2)|cur]
	k.prev = cur
	if k.accumulated >= 2 {
		k.accumulated = 0
		return +1
	}
	if k.accumulated <= -2 {
		k.accumulated = 0
		return -1
	}
	return 0
}

func (h *Hub) handleChange(ch expander.Change, cfg *config.Config, inner, outer, joyKnob *knobState) {
	v := ch.Value
	p := ch.Previous

	bit := func(val uint16, n uint) bool { return val>>n&1 == 1 }
	pressed := func(n uint) bool { return !bit(p, n) && bit(v, n) }
	released := func(n uint) bool { return bit(p, n) && !bit(v, n) }

	// Joystick directions: center bit drives press/release.
	// keydown fires when center is pressed, for each direction bit currently held.
	// keyup fires when center is released, for each direction bit that was held.
	bits := cfg.Expander.Bits
	dirs := []struct {
		bit     uint
		logical string
	}{
		{bits.JoyLeft, "left"},
		{bits.JoyRight, "right"},
		{bits.JoyUp, "up"},
		{bits.JoyDown, "down"},
	}
	if pressed(bits.JoyCenter) {
		for _, d := range dirs {
			if bit(v, d.bit) {
				h.dispatchLogical(input.KeyDown, d.logical)
			}
		}
	}
	if released(bits.JoyCenter) {
		for _, d := range dirs {
			if bit(p, d.bit) {
				h.dispatchLogical(input.KeyUp, d.logical)
			}
		}
	}

	// Knob center: keydown on press, keyup on release.
	if pressed(bits.KnobCenter) {
		h.dispatchLogical(input.KeyDown, "enter")
	}
	if released(bits.KnobCenter) {
		h.dispatchLogical(input.KeyUp, "enter")
	}

	// Rotary encoders: update returns -1 (left), 0 (none), or 1 (right).
	if d := outer.update(uint8(v>>bits.KnobOuter) & 0x3); d == -1 {
		h.sendLogical("outer-left")
	} else if d == 1 {
		h.sendLogical("outer-right")
	}

	if d := inner.update(uint8(v>>bits.KnobInner) & 0x3); d == -1 {
		h.sendLogical("inner-left")
	} else if d == 1 {
		h.sendLogical("inner-right")
	}

	if d := joyKnob.update(uint8(v>>bits.JoyKnob) & 0x3); d == -1 {
		h.sendLogical("joy-left")
	} else if d == 1 {
		h.sendLogical("joy-right")
	}
}

// navigateTo navigates the browser to url, waiting for the load event.
//
// On this platform (chromium-headless-shell on Raspberry Pi), page.Navigate
// never returns a CDP response for HTTP/HTTPS URLs, but the load event fires
// correctly. We fire the navigate in a goroutine and wait for the event.
func navigateTo(browserCtx context.Context, url string) error {
	// On this platform (chromium-headless-shell on Raspberry Pi), page.Navigate
	// never returns a CDP response for HTTP URLs. The lifecycle events do fire,
	// so we listen on browserCtx (not a derived context — events are missed on
	// child contexts) and wait for networkIdle before returning.
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

// initBrowser starts the headless Chromium instance.
// The app page is not loaded here — the caller must call hub.reload() or
// navigateTo() once the HTTP server is ready.
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
