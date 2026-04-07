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
}

// State is the complete current aircon controller state.
type State struct {
	Connected   bool     `json:"connected"`
	Mode        string   `json:"mode"`
	Fan         string   `json:"fan"`
	Setpoint    float64  `json:"setpoint"`
	Circulation string   `json:"circulation"`
	PanelTemp   float64                 `json:"panelTemp"`
	Delta       float64                 `json:"delta"`    // convenience alias for Settings["delta"].Value
	Settings    map[string]SettingValue `json:"settings"` // all 6 tunable settings with defaults
	// Read-only status fields (from the status JSON characteristic)
	CurrentTemp *float64 `json:"currentTemp"`
	Compressor  *string  `json:"compressor"` // "on" | "off" | null
	CabinTemp   *float64 `json:"cabinTemp"`
	BlowerTemp   *float64 `json:"blowerTemp"`
	ExhaustTemp  *float64 `json:"exhaustTemp"`
	BaggageTemp  *float64 `json:"baggageTemp"`
	TailTemp     *float64 `json:"tailTemp"`
	Error        string   `json:"error"`
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

	mu       sync.RWMutex
	state    State
	history  []TempSample
	chars    *charSet // non-nil only while connected
	onChange func(State)
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
	return &Client{
		deviceName: cfg.DeviceName,
		svcUUID:    svcUUID,
		histDur:    histDur,
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
	device, err := adapter.Connect(addr, bluetooth.ConnectionParams{})
	if err != nil {
		return fmt.Errorf("connect: %w", err)
	}
	defer func() { _ = device.Disconnect() }()
	log.Println("aircon: connected")

	svcs, err := device.DiscoverServices([]bluetooth.UUID{c.svcUUID})
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

	c.appendHistory()
	if fn != nil {
		go fn(s)
	}

	// Poll to detect disconnect: read mode characteristic every 10s.
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
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
			c.appendHistory()
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
		c.appendHistory()
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

// notifyChange fires the onChange callback with the current state.
func (c *Client) notifyChange() {
	c.mu.RLock()
	fn := c.onChange
	s := c.state
	c.mu.RUnlock()
	if fn != nil {
		go fn(s)
	}
}

// appendHistory appends the current temperature readings to history and trims
// entries older than histDur.
func (c *Client) appendHistory() {
	c.mu.Lock()
	defer c.mu.Unlock()

	panel := c.state.PanelTemp
	s := TempSample{
		Time:        time.Now(),
		CurrentTemp: c.state.CurrentTemp,
		CabinTemp:   c.state.CabinTemp,
		BlowerTemp:  c.state.BlowerTemp,
		ExhaustTemp: c.state.ExhaustTemp,
		BaggageTemp: c.state.BaggageTemp,
		TailTemp:    c.state.TailTemp,
		PanelTemp:   &panel,
	}
	c.history = append(c.history, s)

	cutoff := time.Now().Add(-c.histDur)
	i := 0
	for i < len(c.history) && c.history[i].Time.Before(cutoff) {
		i++
	}
	if i > 0 {
		c.history = c.history[i:]
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
