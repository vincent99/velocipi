// Package knob implements the bidirectional JSON serial protocol with the
// AC control knob's own hardware/aircon-knob/serial_link.py, over the same
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
	}
	go k.readLoop()
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
		return
	case "settings":
		k.stateMu.Lock()
		k.lastSettings = msg.Settings
		k.stateMu.Unlock()
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
