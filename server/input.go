package main

import (
	"context"
	"log"

	"github.com/chromedp/cdproto/input"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	cfg "github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/expander"
)

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
// browser, and broadcasts a key echo to all WS clients.
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

func (h *Hub) handleChange(ch expander.Change, config *cfg.Config, inner, outer, joyKnob *knobState) {
	v := ch.Value
	p := ch.Previous

	bit := func(val uint16, n uint) bool { return val>>n&1 == 1 }
	pressed := func(n uint) bool { return !bit(p, n) && bit(v, n) }
	released := func(n uint) bool { return bit(p, n) && !bit(v, n) }

	// Joystick directions: center bit drives press/release.
	// keydown fires when center is pressed, for each direction bit currently held.
	// keyup fires when center is released, for each direction bit that was held.
	bits := config.Expander.Bits
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

	config := h.cfg

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
			h.handleChange(ch, config, inner, outer, joyKnob)
		}
	}
}
