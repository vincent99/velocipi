// Package aircon exposes the AC controller's state/commands to the rest of
// the server. It no longer talks BLE directly -- that connection now lives
// entirely on the knob (hardware/aircon-knob/aircon_ble.py), which is
// already relaying commands and pushing state/settings over its own
// USB-serial link to the Pi (hardware/knob, hardware/aircon-knob/
// serial_link.py). This package is just a thin State/History-shaped view
// over that relay, so the rest of the server (server/aircon.go's WS
// broadcast wiring, the /aircon/state and /aircon/set HTTP routes) didn't
// need to change at all.
package aircon

import (
	"context"
	"encoding/json"
	"log"
	"reflect"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/hardware/knob"
)

// SettingValue holds a runtime value and its compile-time default.
//
// Marshals as a bare 2-element JSON array [value, default] (not a
// {"value":..,"default":..} object -- struct tags alone can't produce that,
// hence the custom MarshalJSON below) for backward compatibility with the
// existing UI (both the /aircon/state REST endpoint and the airConState
// websocket message serialize State.Settings this way already --
// ui/src/routes/remote/settings.vue expects the array shape). The knob's
// own "settings" push is actually an object ({"value":..,"default":..} per
// key, see serial_link.py's send_settings()) -- decoded via the unexported
// wireSettingValue below, not through SettingValue.UnmarshalJSON, which
// exists only so this type round-trips through Go's own encoding/json in
// either direction if something ever needs that.
type SettingValue struct {
	Value   float64
	Default float64
}

func (sv SettingValue) MarshalJSON() ([]byte, error) {
	return json.Marshal([2]float64{sv.Value, sv.Default})
}

func (sv *SettingValue) UnmarshalJSON(data []byte) error {
	var arr [2]float64
	if err := json.Unmarshal(data, &arr); err != nil {
		return err
	}
	sv.Value = arr[0]
	sv.Default = arr[1]
	return nil
}

// TempSample records all temperature readings at a point in time.
type TempSample struct {
	Time        time.Time `json:"time"`
	CurrentTemp *float64  `json:"currentTemp,omitempty"`
	CabinTemp   *float64  `json:"cabinTemp,omitempty"`
	BlowerTemp  *float64  `json:"blowerTemp,omitempty"`
	ExhaustTemp *float64  `json:"exhaustTemp,omitempty"`
	BaggageTemp *float64  `json:"baggageTemp,omitempty"`
	TailTemp    *float64  `json:"tailTemp,omitempty"`
	PanelTemp   *float64  `json:"panelTemp,omitempty"`
	OAT         *float64  `json:"oat,omitempty"` // outside air temp °F from Axis
}

// State is the complete current aircon controller state, as last reported
// by the knob (see wireState below for the raw shape it pushes).
type State struct {
	Connected   bool                    `json:"connected"`
	Mode        string                  `json:"mode"`
	Fan         string                  `json:"fan"`
	Setpoint    float64                 `json:"setpoint"`
	Circulation string                  `json:"circulation"`
	PanelTemp   float64                 `json:"panelTemp"`
	Delta       float64                 `json:"delta"`    // convenience alias for Settings["delta"].Value
	Settings    map[string]SettingValue `json:"settings"` // all tunable settings with defaults
	// Read-only status fields
	CurrentTemp       *float64 `json:"currentTemp"`
	Compressor        *string  `json:"compressor"` // "on" | "off" | null
	CabinTemp         *float64 `json:"cabinTemp"`
	BlowerTemp        *float64 `json:"blowerTemp"`
	ExhaustTemp       *float64 `json:"exhaustTemp"`
	BaggageTemp       *float64 `json:"baggageTemp"`
	TailTemp          *float64 `json:"tailTemp"`
	Error             string   `json:"error"`
	ControllerVersion string   `json:"controllerVersion"` // from the knob's "ver" field -- Go's State never carried this before
}

// wireState mirrors serial_link.py's send_state()'s "state" payload
// field-for-field (snake_case, matching AirconState's own attribute
// names on the knob).
type wireState struct {
	Connected         bool     `json:"connected"`
	Mode              string   `json:"mode"`
	Fan               string   `json:"fan"`
	Setpoint          float64  `json:"setpoint"`
	Circulation       string   `json:"circulation"`
	PanelTemp         float64  `json:"panel_temp"`
	CurrentTemp       *float64 `json:"current_temp"`
	Compressor        string   `json:"compressor"` // "" | "on" | "off" -- the knob never sends null, see handleState
	CabinTemp         *float64 `json:"cabin_temp"`
	BlowerTemp        *float64 `json:"blower_temp"`
	ExhaustTemp       *float64 `json:"exhaust_temp"`
	BaggageTemp       *float64 `json:"baggage_temp"`
	TailTemp          *float64 `json:"tail_temp"`
	Error             string   `json:"error"`
	ControllerVersion string   `json:"controller_version"`
}

// wireSettingValue mirrors one entry of serial_link.py's send_settings()
// payload -- see SettingValue's own doc comment for why this isn't just
// SettingValue itself.
type wireSettingValue struct {
	Value   float64 `json:"value"`
	Default float64 `json:"default"`
}

// Config holds this package's own settings -- transport (the knob serial
// link) is injected into New() instead, since hardware.Knob() is itself a
// singleton the rest of the server may also use directly.
type Config struct {
	// HistoryMinutes is how long to keep temperature history in memory.
	HistoryMinutes int
	// SampleIntervalSecs is how often a temperature sample is recorded.
	// Defaults to 10 seconds if zero.
	SampleIntervalSecs int
}

// Client is a State/History view over the knob's relayed aircon connection.
type Client struct {
	knob    *knob.Knob
	histDur time.Duration

	mu             sync.RWMutex
	state          State
	history        []TempSample
	onChange       func(State)
	onSample       func(TempSample)
	oatProvider    func() *float64 // optional; returns current OAT in °F
	lastSentState  State
	sampleInterval time.Duration

	debounceMu    sync.Mutex
	debounceTimer *time.Timer
}

// New creates a Client relaying through the given knob connection.
func New(cfg Config, k *knob.Knob) *Client {
	histDur := time.Duration(cfg.HistoryMinutes) * time.Minute
	if histDur <= 0 {
		histDur = 30 * time.Minute
	}
	sampleInterval := time.Duration(cfg.SampleIntervalSecs) * time.Second
	if sampleInterval <= 0 {
		sampleInterval = 10 * time.Second
	}
	return &Client{
		knob:           k,
		histDur:        histDur,
		sampleInterval: sampleInterval,
	}
}

// OnSample registers a callback invoked (from a goroutine) whenever a new
// temperature sample is appended to history.
func (c *Client) OnSample(fn func(TempSample)) {
	c.mu.Lock()
	c.onSample = fn
	c.mu.Unlock()
}

// SetOATProvider registers a function that returns the current outside air
// temperature in °F. If set, each history sample will include OAT.
func (c *Client) SetOATProvider(fn func() *float64) {
	c.mu.Lock()
	c.oatProvider = fn
	c.mu.Unlock()
}

// OnChange registers a callback invoked (from a goroutine) whenever the state
// changes. Replaces any previously registered callback.
func (c *Client) OnChange(fn func(State)) {
	c.mu.Lock()
	c.onChange = fn
	c.mu.Unlock()
}

// GetState returns a snapshot of the current state.
func (c *Client) GetState() State {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.state
}

// History returns a copy of the in-memory temperature history.
func (c *Client) History() []TempSample {
	c.mu.RLock()
	defer c.mu.RUnlock()
	out := make([]TempSample, len(c.history))
	copy(out, c.history)
	return out
}

// linkCheckInterval governs how often Run re-evaluates the knob link's own
// liveness (knob.Connected(), driven by its ping/pong watchdog) even absent
// any new state push -- needed because a genuinely dead link produces no
// more pushes at all, so relying solely on handleState's own override would
// never fire again once the link is actually gone.
const linkCheckInterval = 2 * time.Second

// Run subscribes to the knob's state/settings pushes and records history
// samples at Config.SampleIntervalSecs. Blocks until ctx is cancelled.
func (c *Client) Run(ctx context.Context) {
	c.knob.OnState(c.handleState)
	c.knob.OnSettings(c.handleSettings)

	sampleTicker := time.NewTicker(c.sampleInterval)
	defer sampleTicker.Stop()
	linkTicker := time.NewTicker(linkCheckInterval)
	defer linkTicker.Stop()

	c.checkLink() // pick up the knob's already-known link state immediately, don't wait a full tick

	for {
		select {
		case <-ctx.Done():
			c.knob.OnState(nil)
			c.knob.OnSettings(nil)
			return
		case <-sampleTicker.C:
			c.appendHistory()
		case <-linkTicker.C:
			c.checkLink()
		}
	}
}

// checkLink forces state.Connected false whenever the knob link itself
// isn't responding to pings, regardless of what the last-pushed aircon
// state said -- the knob could very well still think it's BLE-connected to
// the controller in whatever state it was in right before the Pi lost
// contact with *it*, and there's nothing left to push a correction once
// that link is down. notifyChange() no-ops if this doesn't actually change
// anything (see its own dedupe-by-DeepEqual logic).
func (c *Client) checkLink() {
	c.mu.Lock()
	if !c.knob.Connected() {
		c.state.Connected = false
	}
	c.mu.Unlock()
	c.notifyChange()
}

// handleState is registered with knob.OnState -- called synchronously from
// the knob's own read loop each time it pushes a new "state" message, so
// this (and everything it calls) needs to stay fast/non-blocking.
func (c *Client) handleState(raw json.RawMessage) {
	var w wireState
	if err := json.Unmarshal(raw, &w); err != nil {
		log.Printf("aircon: state JSON parse error: %v", err)
		return
	}

	var compressor *string
	if w.Compressor != "" {
		compressor = &w.Compressor
	}

	c.mu.Lock()
	c.state.Connected = w.Connected && c.knob.Connected()
	c.state.Mode = w.Mode
	c.state.Fan = w.Fan
	c.state.Setpoint = w.Setpoint
	c.state.Circulation = w.Circulation
	c.state.PanelTemp = w.PanelTemp
	c.state.CurrentTemp = w.CurrentTemp
	c.state.Compressor = compressor
	c.state.CabinTemp = w.CabinTemp
	c.state.BlowerTemp = w.BlowerTemp
	c.state.ExhaustTemp = w.ExhaustTemp
	c.state.BaggageTemp = w.BaggageTemp
	c.state.TailTemp = w.TailTemp
	c.state.Error = w.Error
	c.state.ControllerVersion = w.ControllerVersion
	c.mu.Unlock()

	c.notifyChange()
}

// handleSettings is registered with knob.OnSettings -- same call-context
// caveat as handleState above.
func (c *Client) handleSettings(raw json.RawMessage) {
	var wire map[string]wireSettingValue
	if err := json.Unmarshal(raw, &wire); err != nil {
		log.Printf("aircon: settings JSON parse error: %v", err)
		return
	}
	settings := make(map[string]SettingValue, len(wire))
	for k, v := range wire {
		settings[k] = SettingValue{Value: v.Value, Default: v.Default}
	}

	c.mu.Lock()
	c.state.Settings = settings
	if d, ok := settings["delta"]; ok {
		c.state.Delta = d.Value
	}
	c.mu.Unlock()

	c.notifyChange()
}

// notifyChange schedules the onChange callback to fire after a short debounce
// window. Bursts of near-simultaneous state/settings pushes are coalesced
// into a single broadcast.
func (c *Client) notifyChange() {
	c.mu.RLock()
	fn := c.onChange
	c.mu.RUnlock()
	if fn == nil {
		return
	}
	c.debounceMu.Lock()
	if c.debounceTimer != nil {
		c.debounceTimer.Stop()
	}
	c.debounceTimer = time.AfterFunc(300*time.Millisecond, func() {
		c.mu.Lock()
		fn2 := c.onChange
		s := c.state
		changed := !reflect.DeepEqual(s, c.lastSentState)
		if changed {
			c.lastSentState = s
		}
		c.mu.Unlock()
		if fn2 != nil && changed {
			fn2(s)
		}
	})
	c.debounceMu.Unlock()
}

// appendHistory appends the current temperature readings to history, trims
// entries older than histDur, and fires onSample with the new sample.
func (c *Client) appendHistory() {
	c.mu.Lock()

	panel := c.state.PanelTemp
	var oat *float64
	if c.oatProvider != nil {
		oat = c.oatProvider()
	}
	sample := TempSample{
		Time:        time.Now(),
		CurrentTemp: c.state.CurrentTemp,
		CabinTemp:   c.state.CabinTemp,
		BlowerTemp:  c.state.BlowerTemp,
		ExhaustTemp: c.state.ExhaustTemp,
		BaggageTemp: c.state.BaggageTemp,
		TailTemp:    c.state.TailTemp,
		PanelTemp:   &panel,
		OAT:         oat,
	}
	c.history = append(c.history, sample)

	cutoff := time.Now().Add(-c.histDur)
	i := 0
	for i < len(c.history) && c.history[i].Time.Before(cutoff) {
		i++
	}
	if i > 0 {
		c.history = c.history[i:]
	}

	fn := c.onSample
	c.mu.Unlock()

	if fn != nil {
		go fn(sample)
	}
}

// SetMode sets the mode ("off", "fan", "auto", "cool").
func (c *Client) SetMode(mode string) error { return c.knob.SetAirconMode(mode) }

// SetFan sets the fan speed ("low", "medium", "high").
func (c *Client) SetFan(fan string) error { return c.knob.SetAirconFan(fan) }

// SetSetpoint sets the setpoint temperature (°F).
func (c *Client) SetSetpoint(sp float64) error { return c.knob.SetAirconSetpoint(sp) }

// SetCirculation sets the circulation mode ("recirc", "fresh").
func (c *Client) SetCirculation(circ string) error { return c.knob.SetAirconCirculation(circ) }

// SetPanelTemp sets the panel sensor temperature (°F). Not yet driven by
// anything on the Pi side -- planned: pushing a front-of-plane temperature
// reading down to the controller. No knob UI exposes this for manual entry.
func (c *Client) SetPanelTemp(temp float64) error { return c.knob.SetAirconPanelTemp(temp) }

// SetSettings writes a partial or full settings update. Only the keys
// present in the map are sent; the controller ignores unknown keys.
func (c *Client) SetSettings(settings map[string]float64) error {
	return c.knob.SetAirconSettings(settings)
}
