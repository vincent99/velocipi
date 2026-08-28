// Package knob implements the bidirectional JSON serial protocol with the
// AC control knob's own hardware/hvac-knob/serial_link.py, over the same
// USB-CDC connection that also carries its MicroPython REPL/mpremote
// traffic in dev.
//
// Wire format: one JSON object per line, each with an "id". Requests this
// package sends get an `{"id": <same id>, "success": true/false}` response,
// matched back to the call that sent it; the knob also pushes unsolicited
// "state"/"settings" messages (its own id sequence, no response expected)
// whenever its own BLE connection to the AC controller sees new data --
// see serial_link.py's own docstring for the full wire protocol both sides
// implement.
//
// No reconnect logic: if the device disappears (unplugged, reset, etc.),
// the read loop ends and every subsequent send() call fails/times out.
// Restarting the whole process is currently the only recovery path -- add
// reconnect handling here if that turns out to matter in practice.
package knob

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/hardware/serial"
)

const baud = 115200 // USB-CDC ignores the actual rate, but serial.Open still requires a supported value

const requestTimeout = 3 * time.Second

// pingInterval/maxMissedPongs: a background loop (see pingLoop) sends a
// "ping" every pingInterval and expects a {"cmd":"pong"} back within
// requestTimeout; Connected() goes false once maxMissedPongs land in a row,
// independent of anything aircon-related -- this is purely "is the Pi<->knob
// serial link itself still alive", the thing hardware/aircon relies on to
// force its own Connected flag false when the knob's gone quiet rather than
// trusting a stale last-known aircon state.
const pingInterval = 3 * time.Second
const maxMissedPongs = 2

// inMsg covers every shape the knob can send: a response to one of our
// requests ({id, success, [error]}), a pong ({id, cmd:"pong"}), or an
// unsolicited push ({id, cmd:"state"/"settings", state/settings:{...}}).
type inMsg struct {
	ID       int             `json:"id"`
	Cmd      string          `json:"cmd"`
	Success  *bool           `json:"success"`
	Error    string          `json:"error"`
	State    json.RawMessage `json:"state"`
	Settings json.RawMessage `json:"settings"`
}

type Config struct {
	Device string
	// MinBrightness/MaxBrightness are in the *same* 0-100 units SetBrightness
	// takes and sends over the wire -- unlike hardware/lcd's raw-device-unit
	// range, this is just an extra floor/ceiling layered on top of whatever
	// abstract percentage a subscriber (see hardware/brightness) reports,
	// independent of the knob's own separate internal floor (see
	// hal.py's _BACKLIGHT_MIN_PCT on the knob side).
	MinBrightness int
	MaxBrightness int // <=0 defaults to 100
}

type Knob struct {
	f             *os.File
	minBrightness int
	maxBrightness int

	mu      sync.Mutex
	nextID  int
	pending map[int]chan inMsg

	stateMu      sync.RWMutex
	lastState    json.RawMessage
	lastSettings json.RawMessage
	linkUp       bool
	missedPongs  int

	cbMu       sync.RWMutex
	onState    func(json.RawMessage)
	onSettings func(json.RawMessage)
}

// New opens the serial device and starts the background read loop.
func New(cfg Config) (*Knob, error) {
	f, err := serial.Open(cfg.Device, baud)
	if err != nil {
		return nil, fmt.Errorf("knob: %w", err)
	}
	maxBrightness := cfg.MaxBrightness
	if maxBrightness <= 0 {
		maxBrightness = 100
	}
	k := &Knob{
		f:             f,
		minBrightness: cfg.MinBrightness,
		maxBrightness: maxBrightness,
		pending:       make(map[int]chan inMsg),
		linkUp:        true, // optimistic until pingLoop says otherwise -- see maxMissedPongs
	}
	go k.readLoop()
	go k.pingLoop()
	return k, nil
}

// Close releases the serial port.
func (k *Knob) Close() error {
	return k.f.Close()
}

// SetBrightness scales the given 0-100 percentage onto this knob's own
// configured min/maxBrightness range and sends it as a setBrightness command.
func (k *Knob) SetBrightness(pct float64) error {
	if pct < 0 {
		pct = 0
	} else if pct > 100 {
		pct = 100
	}
	scaled := float64(k.minBrightness) + float64(k.maxBrightness-k.minBrightness)*pct/100.0
	resp, err := k.send("setBrightness", map[string]any{"val": scaled})
	if err != nil {
		return err
	}
	return checkSuccess("setBrightness", resp)
}

// SetClock sends the given time (converted to UTC) as a setClock command --
// callers wanting "set it to now" should just pass time.Now().
func (k *Knob) SetClock(t time.Time) error {
	resp, err := k.send("setClock", map[string]any{"val": t.UTC().Format(time.RFC3339)})
	if err != nil {
		return err
	}
	return checkSuccess("setClock", resp)
}

// LastState returns the most recent raw "state" payload pushed by the knob
// (nil if none received yet).
func (k *Knob) LastState() json.RawMessage {
	k.stateMu.RLock()
	defer k.stateMu.RUnlock()
	return k.lastState
}

// LastSettings returns the most recent raw "settings" payload pushed by the
// knob (nil if none received yet).
func (k *Knob) LastSettings() json.RawMessage {
	k.stateMu.RLock()
	defer k.stateMu.RUnlock()
	return k.lastSettings
}

// OnState registers fn to be called (synchronously, from the read loop --
// keep it fast, same expectation as any other single-consumer callback in
// this codebase) every time the knob pushes a new "state" message. Replaces
// any previously registered callback; only one caller (hardware/aircon) is
// expected to use this today.
func (k *Knob) OnState(fn func(json.RawMessage)) {
	k.cbMu.Lock()
	defer k.cbMu.Unlock()
	k.onState = fn
}

// OnSettings is OnState's counterpart for "settings" pushes.
func (k *Knob) OnSettings(fn func(json.RawMessage)) {
	k.cbMu.Lock()
	defer k.cbMu.Unlock()
	k.onSettings = fn
}

// Connected reports whether the Pi<->knob serial link itself is currently
// responding to pings -- see pingLoop/maxMissedPongs. Independent of
// whatever the knob's last-pushed aircon state said (that can go stale the
// instant the link drops, since nothing pushes a "the link just died"
// message -- there's nothing left to push it with).
func (k *Knob) Connected() bool {
	k.stateMu.RLock()
	defer k.stateMu.RUnlock()
	return k.linkUp
}

// pingLoop sends a "ping" every pingInterval for the life of the process,
// tracking consecutive non-pong responses (a timed-out or malformed reply
// both count) -- Connected() flips false once maxMissedPongs land in a row,
// and back to true on the next successful pong. Deliberately checks
// resp.Cmd == "pong" directly rather than going through send()+
// checkSuccess(): a pong reply has no "success" field at all, so
// checkSuccess would always treat it as a failure.
func (k *Knob) pingLoop() {
	ticker := time.NewTicker(pingInterval)
	defer ticker.Stop()
	for range ticker.C {
		resp, err := k.send("ping", nil)
		ok := err == nil && resp.Cmd == "pong"

		k.stateMu.Lock()
		if ok {
			k.missedPongs = 0
		} else {
			k.missedPongs++
		}
		k.linkUp = k.missedPongs < maxMissedPongs
		k.stateMu.Unlock()
	}
}

// SetAirconMode/Fan/Setpoint/Circulation/PanelTemp/Settings relay a command
// to serial_link.py's matching setMode/setFan/setSetpoint/setCirculation/
// setPanelTemp/setSettings handler, which itself just calls the equivalent
// AirconClient.set_*() method -- see serial_link.py's module docstring for
// why "success" here means "queued the debounced write", not "the
// controller confirmed it".
func (k *Knob) SetAirconMode(mode string) error {
	resp, err := k.send("setMode", map[string]any{"val": mode})
	if err != nil {
		return err
	}
	return checkSuccess("setMode", resp)
}

func (k *Knob) SetAirconFan(fan string) error {
	resp, err := k.send("setFan", map[string]any{"val": fan})
	if err != nil {
		return err
	}
	return checkSuccess("setFan", resp)
}

func (k *Knob) SetAirconSetpoint(fahrenheit float64) error {
	resp, err := k.send("setSetpoint", map[string]any{"val": fahrenheit})
	if err != nil {
		return err
	}
	return checkSuccess("setSetpoint", resp)
}

func (k *Knob) SetAirconCirculation(circ string) error {
	resp, err := k.send("setCirculation", map[string]any{"val": circ})
	if err != nil {
		return err
	}
	return checkSuccess("setCirculation", resp)
}

func (k *Knob) SetAirconPanelTemp(fahrenheit float64) error {
	resp, err := k.send("setPanelTemp", map[string]any{"val": fahrenheit})
	if err != nil {
		return err
	}
	return checkSuccess("setPanelTemp", resp)
}

func (k *Knob) SetAirconSettings(settings map[string]float64) error {
	resp, err := k.send("setSettings", map[string]any{"settings": settings})
	if err != nil {
		return err
	}
	return checkSuccess("setSettings", resp)
}

// send allocates an id, registers a pending response channel, and writes
// the request -- all under one lock, so concurrent callers' writes can
// never interleave on the wire. Blocks (unlocked) for the matching response
// or requestTimeout, whichever comes first.
func (k *Knob) send(cmd string, extra map[string]any) (inMsg, error) {
	k.mu.Lock()
	k.nextID++
	id := k.nextID
	ch := make(chan inMsg, 1)
	k.pending[id] = ch

	obj := map[string]any{"id": id, "cmd": cmd}
	for kk, v := range extra {
		obj[kk] = v
	}
	data, err := json.Marshal(obj)
	if err != nil {
		delete(k.pending, id)
		k.mu.Unlock()
		return inMsg{}, fmt.Errorf("knob: encode %s: %w", cmd, err)
	}
	data = append(data, '\n')

	_, err = k.f.Write(data)
	k.mu.Unlock()
	if err != nil {
		k.mu.Lock()
		delete(k.pending, id)
		k.mu.Unlock()
		return inMsg{}, fmt.Errorf("knob: write %s: %w", cmd, err)
	}

	select {
	case resp := <-ch:
		return resp, nil
	case <-time.After(requestTimeout):
		k.mu.Lock()
		delete(k.pending, id)
		k.mu.Unlock()
		return inMsg{}, fmt.Errorf("knob: %s request timed out", cmd)
	}
}

func checkSuccess(cmd string, msg inMsg) error {
	if msg.Success == nil || !*msg.Success {
		if msg.Error != "" {
			return fmt.Errorf("knob: %s failed: %s", cmd, msg.Error)
		}
		return fmt.Errorf("knob: %s failed", cmd)
	}
	return nil
}

// readLoop reads one newline-delimited JSON object at a time for the life
// of the connection, dispatching each to either a pending request or the
// state/settings push handlers. Reads a single byte at a time deliberately
// -- serial.Open configures VMIN=0/VTIME=20 (a 2s read timeout returning 0
// bytes, not an error, when nothing's arrived yet), and this connection can
// legitimately sit idle far longer than that between knob pushes, so this
// loop must tolerate any number of consecutive 0-byte reads rather than
// treating one as a failure (unlike thermalcam.go's readByte(), whose
// synchronous request/response protocol makes a single timeout a real
// error instead).
func (k *Knob) readLoop() {
	buf := make([]byte, 1)
	line := make([]byte, 0, 256)
	for {
		n, err := k.f.Read(buf)
		if err != nil {
			log.Println("knob: read error, ending read loop:", err)
			return
		}
		if n == 0 {
			continue
		}
		if buf[0] != '\n' {
			line = append(line, buf[0])
			continue
		}
		if len(line) > 0 {
			k.handleLine(line)
			line = line[:0]
		}
	}
}

func (k *Knob) handleLine(line []byte) {
	var msg inMsg
	if err := json.Unmarshal(line, &msg); err != nil {
		log.Println("knob: bad JSON from device:", err)
		return
	}

	switch msg.Cmd {
	case "state":
		// msg.State is already an independent copy -- json.RawMessage's own
		// UnmarshalJSON always copies its input rather than aliasing it, so
		// this doesn't alias readLoop's reused line buffer.
		k.stateMu.Lock()
		k.lastState = msg.State
		k.stateMu.Unlock()
		k.cbMu.RLock()
		fn := k.onState
		k.cbMu.RUnlock()
		if fn != nil {
			fn(msg.State)
		}
		return
	case "settings":
		k.stateMu.Lock()
		k.lastSettings = msg.Settings
		k.stateMu.Unlock()
		k.cbMu.RLock()
		fn := k.onSettings
		k.cbMu.RUnlock()
		if fn != nil {
			fn(msg.Settings)
		}
		return
	}

	// Otherwise it's a response (or pong) to one of our own requests,
	// matched by id.
	k.mu.Lock()
	ch, ok := k.pending[msg.ID]
	if ok {
		delete(k.pending, msg.ID)
	}
	k.mu.Unlock()
	if ok {
		ch <- msg
	}
}
