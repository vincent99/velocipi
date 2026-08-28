// Package btmedia is a BlueZ D-Bus client exposing classic-Bluetooth device
// pairing/connection management and read-only AVRCP now-playing metadata
// (title/artist/album/status/position) for whichever device currently has
// an active AVRCP session. Transport control (Play/Pause/Next/Previous) is
// deliberately NOT exposed here -- sending an AVRCP Play command makes iOS
// switch its active audio route to this device (verified empirically, even
// when resuming a session this package itself just paused), which is never
// wanted for a device that isn't meant to carry real audio. Control instead
// goes through hardware/bthid (classic Bluetooth HID), which iOS routes to
// system media control without any audio-route side effects. AVRCP here is
// used purely to read metadata, which activates over the same classic Audio
// Sink (A2DP+AVRCP) profile pair regardless of which device is the phone's
// currently active audio route. See CLAUDE.md for background.
package btmedia

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"

	"github.com/godbus/dbus/v5"
)

const (
	bluezDest       = "org.bluez"
	bluezRootPath   = dbus.ObjectPath("/")
	bluezAgentRoot  = dbus.ObjectPath("/org/bluez")
	adapterIface    = "org.bluez.Adapter1"
	deviceIface     = "org.bluez.Device1"
	playerIface     = "org.bluez.MediaPlayer1"
	agentIface      = "org.bluez.Agent1"
	agentMgrIface   = "org.bluez.AgentManager1"
	agentObjPath    = dbus.ObjectPath("/velocipi/btagent")
	propsIface      = "org.freedesktop.DBus.Properties"
	objManagerIface = "org.freedesktop.DBus.ObjectManager"
)

// DeviceInfo is the API-facing snapshot of one classic Bluetooth device known to BlueZ.
type DeviceInfo struct {
	Address   string `json:"address"`
	Name      string `json:"name"`
	Paired    bool   `json:"paired"`
	Connected bool   `json:"connected"`
	Trusted   bool   `json:"trusted"`
}

// TrackInfo mirrors BlueZ's MediaPlayer1.Track property.
type TrackInfo struct {
	Title          string `json:"title"`
	Artist         string `json:"artist"`
	Album          string `json:"album"`
	Genre          string `json:"genre"`
	TrackNumber    int    `json:"trackNumber"`
	NumberOfTracks int    `json:"numberOfTracks"`
	Duration       int    `json:"duration"` // ms
}

// PlayerState is the API-facing snapshot of the currently active AVRCP session.
type PlayerState struct {
	DeviceAddress string    `json:"deviceAddress"`
	Track         TrackInfo `json:"track"`
	Status        string    `json:"status"`   // "playing"|"paused"|"stopped"|"forward-seek"|"reverse-seek"|"error"
	Position      int       `json:"position"` // ms
}

// Client wraps a system D-Bus connection to BlueZ, tracking one adapter's
// devices and the currently active AVRCP MediaPlayer1 session, if any.
type Client struct {
	conn        *dbus.Conn
	adapterPath dbus.ObjectPath

	mu         sync.Mutex
	devices    map[string]DeviceInfo // address -> info
	playerPath dbus.ObjectPath       // "" if no active AVRCP session
	player     *PlayerState

	onDevices func([]DeviceInfo)
	onPlayer  func(*PlayerState)
}

// New connects to the system D-Bus, locates the first Bluetooth adapter BlueZ
// exposes, registers a NoInputNoOutput pairing agent (this box has no
// keyboard/display, so pairing is always "just works"), and loads the
// current device/player snapshot.
func New() (*Client, error) {
	conn, err := dbus.SystemBus()
	if err != nil {
		return nil, fmt.Errorf("btmedia: system bus connect: %w", err)
	}

	objs, err := getManagedObjects(conn)
	if err != nil {
		return nil, fmt.Errorf("btmedia: get managed objects: %w", err)
	}

	var adapterPath dbus.ObjectPath
	for path, ifaces := range objs {
		if _, ok := ifaces[adapterIface]; ok {
			adapterPath = path
			break
		}
	}
	if adapterPath == "" {
		return nil, fmt.Errorf("btmedia: no bluetooth adapter found")
	}

	c := &Client{
		conn:        conn,
		adapterPath: adapterPath,
		devices:     make(map[string]DeviceInfo),
	}

	if call := c.adapterObj().Call(propsIface+".Set", 0, adapterIface, "Powered", dbus.MakeVariant(true)); call.Err != nil {
		log.Println("btmedia: power on adapter error:", call.Err)
	}

	c.loadSnapshot(objs)

	if err := c.registerAgent(); err != nil {
		log.Println("btmedia: agent registration error:", err)
	}

	return c, nil
}

func getManagedObjects(conn *dbus.Conn) (map[dbus.ObjectPath]map[string]map[string]dbus.Variant, error) {
	var result map[dbus.ObjectPath]map[string]map[string]dbus.Variant
	err := conn.Object(bluezDest, bluezRootPath).Call(objManagerIface+".GetManagedObjects", 0).Store(&result)
	return result, err
}

func (c *Client) loadSnapshot(objs map[dbus.ObjectPath]map[string]map[string]dbus.Variant) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for path, ifaces := range objs {
		if !strings.HasPrefix(string(path), string(c.adapterPath)+"/") {
			continue
		}
		if props, ok := ifaces[deviceIface]; ok {
			d := deviceInfoFromProps(props)
			if d.Address != "" {
				c.devices[d.Address] = d
			}
		}
		if props, ok := ifaces[playerIface]; ok {
			c.playerPath = path
			c.player = playerStateFromProps(path, props)
		}
	}
}

func deviceInfoFromProps(props map[string]dbus.Variant) DeviceInfo {
	var d DeviceInfo
	if v, ok := props["Address"]; ok {
		d.Address, _ = v.Value().(string)
	}
	if v, ok := props["Name"]; ok {
		d.Name, _ = v.Value().(string)
	} else if v, ok := props["Alias"]; ok {
		d.Name, _ = v.Value().(string)
	}
	if v, ok := props["Paired"]; ok {
		d.Paired, _ = v.Value().(bool)
	}
	if v, ok := props["Connected"]; ok {
		d.Connected, _ = v.Value().(bool)
	}
	if v, ok := props["Trusted"]; ok {
		d.Trusted, _ = v.Value().(bool)
	}
	return d
}

func playerStateFromProps(path dbus.ObjectPath, props map[string]dbus.Variant) *PlayerState {
	p := &PlayerState{DeviceAddress: addressFromDevicePath(path)}
	if v, ok := props["Status"]; ok {
		p.Status, _ = v.Value().(string)
	}
	if v, ok := props["Position"]; ok {
		p.Position = int(variantToUint32(v))
	}
	if v, ok := props["Track"]; ok {
		if trackMap, ok := v.Value().(map[string]dbus.Variant); ok {
			p.Track = trackInfoFromProps(trackMap)
		}
	}
	return p
}

func trackInfoFromProps(m map[string]dbus.Variant) TrackInfo {
	var t TrackInfo
	if v, ok := m["Title"]; ok {
		t.Title, _ = v.Value().(string)
	}
	if v, ok := m["Artist"]; ok {
		t.Artist, _ = v.Value().(string)
	}
	if v, ok := m["Album"]; ok {
		t.Album, _ = v.Value().(string)
	}
	if v, ok := m["Genre"]; ok {
		t.Genre, _ = v.Value().(string)
	}
	if v, ok := m["TrackNumber"]; ok {
		t.TrackNumber = int(variantToUint32(v))
	}
	if v, ok := m["NumberOfTracks"]; ok {
		t.NumberOfTracks = int(variantToUint32(v))
	}
	if v, ok := m["Duration"]; ok {
		t.Duration = int(variantToUint32(v))
	}
	return t
}

// variantToUint32 handles BlueZ numeric properties that may arrive as any of
// D-Bus's fixed-width uint types depending on the field.
func variantToUint32(v dbus.Variant) uint32 {
	switch n := v.Value().(type) {
	case uint32:
		return n
	case uint16:
		return uint32(n)
	case int32:
		return uint32(n)
	}
	return 0
}

// addressFromDevicePath extracts "AA:BB:CC:DD:EE:FF" from a BlueZ object path
// such as ".../dev_AA_BB_CC_DD_EE_FF" or ".../dev_AA_BB_CC_DD_EE_FF/player0".
func addressFromDevicePath(path dbus.ObjectPath) string {
	for _, part := range strings.Split(string(path), "/") {
		if strings.HasPrefix(part, "dev_") {
			return strings.ReplaceAll(strings.TrimPrefix(part, "dev_"), "_", ":")
		}
	}
	return ""
}

// agent implements org.bluez.Agent1 with NoInputNoOutput semantics -- this
// box has no keyboard/display, so every prompt just-works/auto-confirms.
type agent struct{}

func (a *agent) Release() *dbus.Error { return nil }

func (a *agent) RequestPinCode(device dbus.ObjectPath) (string, *dbus.Error) {
	return "0000", nil
}

func (a *agent) DisplayPinCode(device dbus.ObjectPath, pincode string) *dbus.Error {
	return nil
}

func (a *agent) RequestPasskey(device dbus.ObjectPath) (uint32, *dbus.Error) {
	return 0, nil
}

func (a *agent) DisplayPasskey(device dbus.ObjectPath, passkey uint32, entered uint16) *dbus.Error {
	return nil
}

func (a *agent) RequestConfirmation(device dbus.ObjectPath, passkey uint32) *dbus.Error {
	return nil
}

func (a *agent) RequestAuthorization(device dbus.ObjectPath) *dbus.Error {
	return nil
}

func (a *agent) AuthorizeService(device dbus.ObjectPath, uuid string) *dbus.Error {
	return nil
}

func (a *agent) Cancel() *dbus.Error { return nil }

func (c *Client) registerAgent() error {
	if err := c.conn.Export(&agent{}, agentObjPath, agentIface); err != nil {
		return err
	}
	obj := c.conn.Object(bluezDest, bluezAgentRoot)
	if call := obj.Call(agentMgrIface+".RegisterAgent", 0, agentObjPath, "NoInputNoOutput"); call.Err != nil {
		return call.Err
	}
	return obj.Call(agentMgrIface+".RequestDefaultAgent", 0, agentObjPath).Err
}

func (c *Client) adapterObj() dbus.BusObject {
	return c.conn.Object(bluezDest, c.adapterPath)
}

func (c *Client) devicePath(address string) dbus.ObjectPath {
	return dbus.ObjectPath(string(c.adapterPath) + "/dev_" + strings.ReplaceAll(address, ":", "_"))
}

func (c *Client) deviceObj(address string) dbus.BusObject {
	return c.conn.Object(bluezDest, c.devicePath(address))
}

// StartDiscovery makes the adapter discoverable/pairable and begins scanning
// for nearby devices; discovered devices show up via OnDeviceChange.
func (c *Client) StartDiscovery() error {
	c.adapterObj().Call(propsIface+".Set", 0, adapterIface, "Discoverable", dbus.MakeVariant(true))
	c.adapterObj().Call(propsIface+".Set", 0, adapterIface, "Pairable", dbus.MakeVariant(true))
	return c.adapterObj().Call(adapterIface+".StartDiscovery", 0).Err
}

func (c *Client) StopDiscovery() error {
	return c.adapterObj().Call(adapterIface+".StopDiscovery", 0).Err
}

// Pair pairs with the device at address, trusts it (so future reconnects
// don't require re-authorization), then connects.
func (c *Client) Pair(address string) error {
	obj := c.deviceObj(address)
	if call := obj.Call(deviceIface+".Pair", 0); call.Err != nil {
		return call.Err
	}
	if call := obj.Call(propsIface+".Set", 0, deviceIface, "Trusted", dbus.MakeVariant(true)); call.Err != nil {
		return call.Err
	}
	return obj.Call(deviceIface+".Connect", 0).Err
}

func (c *Client) Connect(address string) error {
	return c.deviceObj(address).Call(deviceIface+".Connect", 0).Err
}

func (c *Client) Disconnect(address string) error {
	return c.deviceObj(address).Call(deviceIface+".Disconnect", 0).Err
}

// Forget unpairs and removes the device entirely.
func (c *Client) Forget(address string) error {
	return c.adapterObj().Call(adapterIface+".RemoveDevice", 0, c.devicePath(address)).Err
}

// OnDeviceChange registers cb to be called with the full device list
// whenever any tracked device appears, disappears, or changes.
func (c *Client) OnDeviceChange(cb func([]DeviceInfo)) { c.onDevices = cb }

// OnPlayerChange registers cb to be called whenever the active AVRCP
// session's track/status/position changes, or with nil when it goes away.
func (c *Client) OnPlayerChange(cb func(*PlayerState)) { c.onPlayer = cb }

func (c *Client) Devices() []DeviceInfo {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]DeviceInfo, 0, len(c.devices))
	for _, d := range c.devices {
		out = append(out, d)
	}
	return out
}

func (c *Client) Player() *PlayerState {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.player == nil {
		return nil
	}
	p := *c.player
	return &p
}

// Run watches BlueZ's D-Bus signals for device and AVRCP player changes,
// invoking the registered callbacks, until ctx is cancelled.
func (c *Client) Run(ctx context.Context) {
	if err := c.conn.AddMatchSignal(dbus.WithMatchInterface(objManagerIface)); err != nil {
		log.Println("btmedia: add match (object manager) error:", err)
	}
	if err := c.conn.AddMatchSignal(
		dbus.WithMatchInterface(propsIface),
		dbus.WithMatchMember("PropertiesChanged"),
	); err != nil {
		log.Println("btmedia: add match (properties changed) error:", err)
	}

	ch := make(chan *dbus.Signal, 32)
	c.conn.Signal(ch)
	defer c.conn.RemoveSignal(ch)

	for {
		select {
		case <-ctx.Done():
			return
		case sig, ok := <-ch:
			if !ok {
				return
			}
			c.handleSignal(sig)
		}
	}
}

func (c *Client) handleSignal(sig *dbus.Signal) {
	switch sig.Name {
	case objManagerIface + ".InterfacesAdded":
		c.handleInterfacesAdded(sig)
	case objManagerIface + ".InterfacesRemoved":
		c.handleInterfacesRemoved(sig)
	case propsIface + ".PropertiesChanged":
		c.handlePropertiesChanged(sig)
	}
}

func (c *Client) handleInterfacesAdded(sig *dbus.Signal) {
	if len(sig.Body) != 2 {
		return
	}
	path, ok := sig.Body[0].(dbus.ObjectPath)
	if !ok {
		return
	}
	ifaces, ok := sig.Body[1].(map[string]map[string]dbus.Variant)
	if !ok {
		return
	}

	devicesChanged := false
	if props, ok := ifaces[deviceIface]; ok {
		d := deviceInfoFromProps(props)
		if d.Address != "" {
			c.mu.Lock()
			c.devices[d.Address] = d
			c.mu.Unlock()
			devicesChanged = true
		}
	}
	if props, ok := ifaces[playerIface]; ok {
		c.mu.Lock()
		c.playerPath = path
		c.player = playerStateFromProps(path, props)
		p := *c.player
		c.mu.Unlock()
		if c.onPlayer != nil {
			c.onPlayer(&p)
		}
	}
	if devicesChanged && c.onDevices != nil {
		c.onDevices(c.Devices())
	}
}

func (c *Client) handleInterfacesRemoved(sig *dbus.Signal) {
	if len(sig.Body) != 2 {
		return
	}
	path, ok := sig.Body[0].(dbus.ObjectPath)
	if !ok {
		return
	}
	ifaceNames, ok := sig.Body[1].([]string)
	if !ok {
		return
	}

	devicesChanged := false
	for _, name := range ifaceNames {
		switch name {
		case deviceIface:
			addr := addressFromDevicePath(path)
			c.mu.Lock()
			delete(c.devices, addr)
			c.mu.Unlock()
			devicesChanged = true
		case playerIface:
			c.mu.Lock()
			isCurrent := c.playerPath == path
			if isCurrent {
				c.playerPath = ""
				c.player = nil
			}
			c.mu.Unlock()
			if isCurrent && c.onPlayer != nil {
				c.onPlayer(nil)
			}
		}
	}
	if devicesChanged && c.onDevices != nil {
		c.onDevices(c.Devices())
	}
}

func (c *Client) handlePropertiesChanged(sig *dbus.Signal) {
	if len(sig.Body) < 2 {
		return
	}
	iface, ok := sig.Body[0].(string)
	if !ok {
		return
	}
	changed, ok := sig.Body[1].(map[string]dbus.Variant)
	if !ok {
		return
	}

	switch iface {
	case deviceIface:
		addr := addressFromDevicePath(sig.Path)
		c.mu.Lock()
		d, known := c.devices[addr]
		if !known {
			c.mu.Unlock()
			return
		}
		applyDeviceChanges(&d, changed)
		c.devices[addr] = d
		c.mu.Unlock()
		if c.onDevices != nil {
			c.onDevices(c.Devices())
		}
	case playerIface:
		c.mu.Lock()
		if c.playerPath != sig.Path || c.player == nil {
			c.mu.Unlock()
			return
		}
		applyPlayerChanges(c.player, changed)
		p := *c.player
		c.mu.Unlock()
		if c.onPlayer != nil {
			c.onPlayer(&p)
		}
	}
}

func applyDeviceChanges(d *DeviceInfo, changed map[string]dbus.Variant) {
	if v, ok := changed["Name"]; ok {
		d.Name, _ = v.Value().(string)
	}
	if v, ok := changed["Paired"]; ok {
		d.Paired, _ = v.Value().(bool)
	}
	if v, ok := changed["Connected"]; ok {
		d.Connected, _ = v.Value().(bool)
	}
	if v, ok := changed["Trusted"]; ok {
		d.Trusted, _ = v.Value().(bool)
	}
}

func applyPlayerChanges(p *PlayerState, changed map[string]dbus.Variant) {
	if v, ok := changed["Status"]; ok {
		p.Status, _ = v.Value().(string)
	}
	if v, ok := changed["Position"]; ok {
		p.Position = int(variantToUint32(v))
	}
	if v, ok := changed["Track"]; ok {
		if trackMap, ok := v.Value().(map[string]dbus.Variant); ok {
			p.Track = trackInfoFromProps(trackMap)
		}
	}
}
