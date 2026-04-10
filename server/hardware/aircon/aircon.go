// Package aircon implements a BLE GATT client for the AirCon controller.
//
// The controller exposes a single custom service with 7 characteristics:
//   - mode, fan, setpoint, circ, panel, delta — read/write/notify (UTF-8 strings)
//   - status — read/notify, JSON snapshot of all sensor readings
//
// All writable characteristic values are UTF-8 strings; floats are encoded as
// decimal strings (e.g. "72.50").
package aircon

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/hardware/blescan"
	"tinygo.org/x/bluetooth"
)

// BLE characteristic UUIDs from config.py.
const (
	uuidMode     = "aaaaaaaa-1111-cccc-00dd-000000000001" // rw string: "off"|"fan"|"auto"|"cool"
	uuidFan      = "aaaaaaaa-1111-cccc-00dd-000000000002" // rw string: "low"|"medium"|"high"
	uuidSetpoint = "aaaaaaaa-1111-cccc-00dd-000000000003" // rw float string °F
	uuidCirc     = "aaaaaaaa-1111-cccc-00dd-000000000004" // rw string: "recirc"|"fresh"
	uuidPanel    = "aaaaaaaa-1111-cccc-00dd-000000000005" // rw float string °F (panel sensor temp)
	uuidSettings = "aaaaaaaa-1111-cccc-00dd-000000000006" // rw JSON settings object
	uuidStatus   = "aaaaaaaa-1111-cccc-00dd-000000000007" // rn JSON status snapshot
)

// SettingValue holds a runtime value and its compile-time default.
type SettingValue struct {
	Value   float64 `json:"value"`
	Default float64 `json:"default"`
}

// statusPayload is the JSON structure sent by the status characteristic.
// comp is "on" | "off" | null (a string, not a bool).
type statusPayload struct {
	CurrentTemp *float64 `json:"curr"`
	Compressor  *string  `json:"comp"`
	CabinTemp   *float64 `json:"cabin"`
	BlowerTemp  *float64 `json:"blower"`
	ExhaustTemp *float64 `json:"exhaust"`
	BaggageTemp *float64 `json:"baggage"`
	TailTemp    *float64 `json:"tail"`
	Error       string   `json:"err"`
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
	OAT         *float64  `json:"oat,omitempty"` // outside air temp °F from G3X
}

// State is the complete current aircon controller state.
type State struct {
	Connected   bool                    `json:"connected"`
	Mode        string                  `json:"mode"`
	Fan         string                  `json:"fan"`
	Setpoint    float64                 `json:"setpoint"`
	Circulation string                  `json:"circulation"`
	PanelTemp   float64                 `json:"panelTemp"`
	Delta       float64                 `json:"delta"`    // convenience alias for Settings["delta"].Value
	Settings    map[string]SettingValue `json:"settings"` // all 6 tunable settings with defaults
	// Read-only status fields (from the status JSON characteristic)
	CurrentTemp *float64 `json:"currentTemp"`
	Compressor  *string  `json:"compressor"` // "on" | "off" | null
	CabinTemp   *float64 `json:"cabinTemp"`
	BlowerTemp  *float64 `json:"blowerTemp"`
	ExhaustTemp *float64 `json:"exhaustTemp"`
	BaggageTemp *float64 `json:"baggageTemp"`
	TailTemp    *float64 `json:"tailTemp"`
	Error       string   `json:"error"`
}

// Config holds the BLE client configuration.
type Config struct {
	// DeviceName is the BLE local name advertised by the AirCon controller
	// (e.g. "AirCon"). Required; if empty the client is disabled.
	DeviceName string
	// ServiceUUID is the 128-bit GATT service UUID advertised by the controller.
	ServiceUUID string
	// HistoryMinutes is how long to keep temperature history in memory.
	HistoryMinutes int
	// SampleIntervalSecs is how often a temperature sample is recorded.
	// Defaults to 10 seconds if zero.
	SampleIntervalSecs int
}

// charSet holds writable characteristic handles for an active connection.
type charSet struct {
	mode     bluetooth.DeviceCharacteristic
	fan      bluetooth.DeviceCharacteristic
	setpoint bluetooth.DeviceCharacteristic
	circ     bluetooth.DeviceCharacteristic
	panel    bluetooth.DeviceCharacteristic
	settings bluetooth.DeviceCharacteristic
}

// Client is a BLE GATT client for the AirCon controller.
type Client struct {
	deviceName string
	svcUUID    bluetooth.UUID
	histDur    time.Duration

	mu             sync.RWMutex
	state          State
	history        []TempSample
	chars          *charSet // non-nil only while connected
	onChange       func(State)
	onSample       func(TempSample)
	oatProvider    func() *float64 // optional; returns current OAT in °F
	lastSentState  State
	sampleInterval time.Duration

	debounceMu    sync.Mutex
	debounceTimer *time.Timer
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

// New creates a new AirCon BLE client from the given configuration.
func New(cfg Config) (*Client, error) {
	svcUUID, err := bluetooth.ParseUUID(cfg.ServiceUUID)
	if err != nil {
		return nil, fmt.Errorf("aircon: invalid service UUID %q: %w", cfg.ServiceUUID, err)
	}
	histDur := time.Duration(cfg.HistoryMinutes) * time.Minute
	if histDur <= 0 {
		histDur = 30 * time.Minute
	}
	sampleInterval := time.Duration(cfg.SampleIntervalSecs) * time.Second
	if sampleInterval <= 0 {
		sampleInterval = 10 * time.Second
	}
	return &Client{
		deviceName:     cfg.DeviceName,
		svcUUID:        svcUUID,
		histDur:        histDur,
		sampleInterval: sampleInterval,
	}, nil
}

// resolveAddress scans for the device by BLE local name and returns its address.
// Registers a persistent blescan callback; after the first match the callback
// becomes a no-op.
func (c *Client) resolveAddress(ctx context.Context) (bluetooth.Address, error) {
	found := make(chan bluetooth.Address, 1)
	blescan.Register(func(_ *bluetooth.Adapter, r bluetooth.ScanResult) {
		if r.LocalName() == c.deviceName {
			select {
			case found <- r.Address:
			default:
			}
		}
	})
	log.Printf("aircon: scanning for BLE device %q...", c.deviceName)
	select {
	case addr := <-found:
		log.Printf("aircon: found %q at %s", c.deviceName, addr)
		return addr, nil
	case <-ctx.Done():
		return bluetooth.Address{}, ctx.Err()
	}
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

// Run resolves the device by name via BLE scan, then connects and maintains
// the connection indefinitely, reconnecting after a 5-second delay on
// disconnect. Blocks until ctx is cancelled.
func (c *Client) Run(ctx context.Context) {
	addr, err := c.resolveAddress(ctx)
	if err != nil {
		return // context cancelled
	}

	adapter := bluetooth.DefaultAdapter

	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		log.Printf("aircon: connecting to %q (%s)", c.deviceName, addr)
		if err := c.connectLoop(ctx, adapter, addr); err != nil && ctx.Err() == nil {
			log.Println("aircon: connection lost:", err)
		}

		c.mu.Lock()
		c.state.Connected = false
		c.chars = nil
		fn := c.onChange
		s := c.state
		c.mu.Unlock()

		if fn != nil {
			go fn(s)
		}

		select {
		case <-ctx.Done():
			return
		case <-time.After(5 * time.Second):
		}
	}
}

// connectLoop performs one connect → discover → subscribe → poll cycle.
func (c *Client) connectLoop(ctx context.Context, adapter *bluetooth.Adapter, addr bluetooth.Address) error {
	// Pause the shared BLE scan so the adapter is free for GATT operations.
	// BlueZ can fail service discovery with "Operation already in progress"
	// when a concurrent scan is running.
	resumeScan := blescan.Pause()
	device, err := adapter.Connect(addr, bluetooth.ConnectionParams{})
	if err != nil {
		resumeScan()
		return fmt.Errorf("connect: %w", err)
	}
	defer func() { _ = device.Disconnect() }()
	log.Println("aircon: connected")

	// DiscoverServices can time out if BlueZ hasn't finished its async GATT
	// discovery yet. Retry a few times before giving up.
	var svcs []bluetooth.DeviceService
	for attempt := 1; attempt <= 3; attempt++ {
		svcs, err = device.DiscoverServices([]bluetooth.UUID{c.svcUUID})
		if err == nil {
			break
		}
		log.Printf("aircon: discover services attempt %d/3: %v", attempt, err)
		if ctx.Err() != nil {
			resumeScan()
			return ctx.Err()
		}
		time.Sleep(2 * time.Second)
	}
	resumeScan() // scan can resume once service discovery is complete
	if err != nil {
		return fmt.Errorf("discover services: %w", err)
	}
	if len(svcs) == 0 {
		return fmt.Errorf("aircon service not found")
	}

	chars, err := svcs[0].DiscoverCharacteristics(nil)
	if err != nil {
		return fmt.Errorf("discover characteristics: %w", err)
	}

	charMap := make(map[string]*bluetooth.DeviceCharacteristic, len(chars))
	for i := range chars {
		uuid := strings.ToLower(chars[i].UUID().String())
		charMap[uuid] = &chars[i]
	}

	// Store writable characteristic handles.
	cs := &charSet{}
	if ch := charMap[uuidMode]; ch != nil {
		cs.mode = *ch
	}
	if ch := charMap[uuidFan]; ch != nil {
		cs.fan = *ch
	}
	if ch := charMap[uuidSetpoint]; ch != nil {
		cs.setpoint = *ch
	}
	if ch := charMap[uuidCirc]; ch != nil {
		cs.circ = *ch
	}
	if ch := charMap[uuidPanel]; ch != nil {
		cs.panel = *ch
	}
	if ch := charMap[uuidSettings]; ch != nil {
		cs.settings = *ch
	}

	c.readInitial(charMap)
	c.subscribeAll(charMap)

	c.mu.Lock()
	c.state.Connected = true
	c.chars = cs
	fn := c.onChange
	s := c.state
	c.mu.Unlock()

	if fn != nil {
		go fn(s)
	}

	// pollTicker detects disconnects; sampleTicker records history at a fixed rate.
	pollTicker := time.NewTicker(10 * time.Second)
	sampleTicker := time.NewTicker(c.sampleInterval)
	defer pollTicker.Stop()
	defer sampleTicker.Stop()
	c.appendHistory() // record one sample immediately on connect
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-sampleTicker.C:
			c.appendHistory()
		case <-pollTicker.C:
			ch := charMap[uuidMode]
			if ch == nil {
				continue
			}
			buf := make([]byte, 32)
			if _, err := ch.Read(buf); err != nil {
				return fmt.Errorf("poll read: %w", err)
			}
		}
	}
}

// readInitial reads the current value of all characteristics and updates state.
func (c *Client) readInitial(charMap map[string]*bluetooth.DeviceCharacteristic) {
	readStr := func(uuid string) string {
		ch, ok := charMap[uuid]
		if !ok {
			return ""
		}
		buf := make([]byte, 256)
		n, err := ch.Read(buf)
		if err != nil {
			return ""
		}
		return strings.TrimRight(string(buf[:n]), "\x00")
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	if v := readStr(uuidMode); v != "" {
		c.state.Mode = v
	}
	if v := readStr(uuidFan); v != "" {
		c.state.Fan = v
	}
	if v := readStr(uuidSetpoint); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			c.state.Setpoint = f
		}
	}
	if v := readStr(uuidCirc); v != "" {
		c.state.Circulation = v
	}
	if v := readStr(uuidPanel); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			c.state.PanelTemp = f
		}
	}
	if v := readStr(uuidSettings); v != "" {
		c.applySettingsJSON([]byte(v))
	}
	if v := readStr(uuidStatus); v != "" {
		c.applyStatusJSON([]byte(v))
	}
}

// subscribeAll enables notifications on all 7 characteristics.
func (c *Client) subscribeAll(charMap map[string]*bluetooth.DeviceCharacteristic) {
	subscribe := func(uuid string, handler func([]byte)) {
		ch, ok := charMap[uuid]
		if !ok {
			return
		}
		if err := ch.EnableNotifications(handler); err != nil {
			log.Printf("aircon: EnableNotifications %s: %v", uuid, err)
		}
	}

	subscribe(uuidMode, func(buf []byte) {
		v := strings.TrimRight(string(buf), "\x00")
		c.mu.Lock()
		c.state.Mode = v
		c.mu.Unlock()
		c.notifyChange()
	})
	subscribe(uuidFan, func(buf []byte) {
		v := strings.TrimRight(string(buf), "\x00")
		c.mu.Lock()
		c.state.Fan = v
		c.mu.Unlock()
		c.notifyChange()
	})
	subscribe(uuidSetpoint, func(buf []byte) {
		v := strings.TrimRight(string(buf), "\x00")
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			c.mu.Lock()
			c.state.Setpoint = f
			c.mu.Unlock()
			c.notifyChange()
		}
	})
	subscribe(uuidCirc, func(buf []byte) {
		v := strings.TrimRight(string(buf), "\x00")
		c.mu.Lock()
		c.state.Circulation = v
		c.mu.Unlock()
		c.notifyChange()
	})
	subscribe(uuidPanel, func(buf []byte) {
		v := strings.TrimRight(string(buf), "\x00")
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			c.mu.Lock()
			c.state.PanelTemp = f
			c.mu.Unlock()
			c.notifyChange()
		}
	})
	subscribe(uuidSettings, func(buf []byte) {
		c.mu.Lock()
		c.applySettingsJSON(buf)
		c.mu.Unlock()
		c.notifyChange()
	})
	subscribe(uuidStatus, func(buf []byte) {
		c.mu.Lock()
		c.applyStatusJSON(buf)
		c.mu.Unlock()
		c.notifyChange()
	})
}

// applySettingsJSON unmarshals the settings characteristic JSON and updates state.
// Accepts both {key: float} and {key: {value: float, default: float}} formats.
// Must be called with c.mu held for write.
func (c *Client) applySettingsJSON(data []byte) {
	data = []byte(strings.TrimRight(string(data), "\x00"))
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		log.Printf("aircon: settings JSON parse error: %v (data: %q)", err, data)
		return
	}
	settings := make(map[string]SettingValue, len(raw))
	for k, v := range raw {
		var sv SettingValue
		var f float64
		if err := json.Unmarshal(v, &f); err == nil {
			sv = SettingValue{Value: f, Default: f}
		} else if err := json.Unmarshal(v, &sv); err == nil {
			// already {value, default}
		} else {
			continue
		}
		settings[k] = sv
	}
	c.state.Settings = settings
	if d, ok := settings["delta"]; ok {
		c.state.Delta = d.Value
	}
}

// applyStatusJSON unmarshals the status characteristic JSON and updates state.
// Must be called with c.mu held for write.
func (c *Client) applyStatusJSON(data []byte) {
	data = []byte(strings.TrimRight(string(data), "\x00"))
	var p statusPayload
	if err := json.Unmarshal(data, &p); err != nil {
		log.Printf("aircon: status JSON parse error: %v (data: %q)", err, data)
		return
	}
	c.state.CurrentTemp = p.CurrentTemp
	c.state.Compressor = p.Compressor // "on" | "off" | null
	c.state.CabinTemp = p.CabinTemp
	c.state.BlowerTemp = p.BlowerTemp
	c.state.ExhaustTemp = p.ExhaustTemp
	c.state.BaggageTemp = p.BaggageTemp
	c.state.TailTemp = p.TailTemp
	if p.Error != "" {
		c.state.Error = p.Error
	} else {
		c.state.Error = ""
	}
}

// notifyChange schedules the onChange callback to fire after a short debounce
// window. Rapid-fire BLE notifications (one per characteristic) are coalesced
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

// SetMode writes the mode characteristic ("off", "fan", "auto", "max").
func (c *Client) SetMode(mode string) error {
	return c.writeStr(func(cs *charSet) bluetooth.DeviceCharacteristic { return cs.mode }, mode)
}

// SetFan writes the fan speed characteristic ("low", "medium", "high").
func (c *Client) SetFan(fan string) error {
	return c.writeStr(func(cs *charSet) bluetooth.DeviceCharacteristic { return cs.fan }, fan)
}

// SetSetpoint writes the setpoint temperature (°F).
func (c *Client) SetSetpoint(sp float64) error {
	return c.writeStr(func(cs *charSet) bluetooth.DeviceCharacteristic { return cs.setpoint }, fmt.Sprintf("%.2f", sp))
}

// SetCirculation writes the circulation mode ("recirc", "fresh").
func (c *Client) SetCirculation(circ string) error {
	return c.writeStr(func(cs *charSet) bluetooth.DeviceCharacteristic { return cs.circ }, circ)
}

// SetPanelTemp writes the panel sensor temperature (°F).
func (c *Client) SetPanelTemp(temp float64) error {
	return c.writeStr(func(cs *charSet) bluetooth.DeviceCharacteristic { return cs.panel }, fmt.Sprintf("%.2f", temp))
}

// SetSettings writes a partial or full settings update to characteristic 0006.
// Only the keys present in the map are sent; the Pico ignores unknown keys.
func (c *Client) SetSettings(settings map[string]float64) error {
	data, err := json.Marshal(settings)
	if err != nil {
		return fmt.Errorf("aircon: marshal settings: %w", err)
	}
	return c.writeStr(func(cs *charSet) bluetooth.DeviceCharacteristic { return cs.settings }, string(data))
}

func (c *Client) writeStr(sel func(*charSet) bluetooth.DeviceCharacteristic, value string) error {
	c.mu.RLock()
	cs := c.chars
	c.mu.RUnlock()
	if cs == nil {
		return fmt.Errorf("aircon: not connected")
	}
	ch := sel(cs)
	_, err := ch.WriteWithoutResponse([]byte(value))
	return err
}
