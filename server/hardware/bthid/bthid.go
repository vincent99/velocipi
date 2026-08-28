// Package bthid emulates a classic Bluetooth (BR/EDR) HID device exposing a
// Consumer Control report (Play/Pause toggle, Next, Previous, Volume Up/
// Down) plus a standard Keyboard report (any letter or F-key) -- this is
// what a real Bluetooth keyboard sends, and unlike AVRCP or a BLE/HOGP
// peripheral, iOS reliably routes it into system media control / text input
// without ever changing the phone's active audio route.
//
// This was arrived at empirically after two dead ends, in order:
//  1. AVRCP transport control (see hardware/btmedia) -- Play makes iOS
//     switch its active audio route to this device, even when resuming a
//     session this same code just paused. Unfixable from the accessory side.
//  2. A fully spec-correct BLE HID-over-GATT (HOGP) peripheral -- confirmed
//     iOS bonded, discovered, and subscribed to it correctly (StartNotify
//     fired), yet never routed ANY of its reports (media keys, volume, even
//     plain keyboard letters) into any system action. iOS's HID/media-key
//     routing appears to only trust the classic BT HID profile, not BLE.
//
// BlueZ has no D-Bus convenience layer for classic HID device-role
// emulation (its old `hidd` device-role daemon was removed years ago), so
// this registers a custom profile via ProfileManager1, hand-builds the SDP
// record (including the raw HID Report Descriptor, hex-encoded), and speaks
// the HIDP wire protocol directly over the raw L2CAP sockets BlueZ hands
// over via NewConnection.
//
// Deployment requirement: BlueZ's built-in "input" plugin (classic HID
// *host* role, used for connecting external keyboards/mice to the Pi
// itself -- unused by this project otherwise) permanently claims UUID
// 0x1124, which conflicts with registering it ourselves for the *device*
// role here. bluetoothd must run with -P input, via a systemd override
// (main.conf's DisablePlugins key doesn't do this on newer BlueZ):
//
//	# /etc/systemd/system/bluetooth.service.d/override.conf
//	[Service]
//	ExecStart=
//	ExecStart=/usr/libexec/bluetooth/bluetoothd -P input
//
// then `systemctl daemon-reload && systemctl restart bluetooth`.
package bthid

import (
	"fmt"
	"log"
	"os"
	"sync"
	"time"

	"github.com/godbus/dbus/v5"
)

const (
	bluezDest      = "org.bluez"
	profileMgrPath = dbus.ObjectPath("/org/bluez")
	ctrlPath       = dbus.ObjectPath("/velocipi/hidctrl")
	intrPath       = dbus.ObjectPath("/velocipi/hidintr")
	hidUUID        = "00001124-0000-1000-8000-00805f9b34fb"
	// intrUUID is a distinct placeholder -- BlueZ's ProfileManager1 refuses
	// to register the same UUID twice, but classic HID needs two separate
	// L2CAP channels (control + interrupt) registered independently. Only
	// the control registration's ServiceRecord is ever actually published
	// to remote SDP browsers (it already declares both PSMs), so this
	// second UUID's identity doesn't matter beyond satisfying the API.
	intrUUID = "00001124-0000-1000-8000-00805f9b34fc"
	psmCtrl  = uint16(0x11) // HID Control channel
	psmIntr  = uint16(0x13) // HID Interrupt channel

	consumerReportID = 0x01
	keyboardReportID = 0x02
)

// reportDescriptor: two Report IDs sharing one HID service, same as a real
// keyboard combining its media-key row with its main keyboard --
//
//	Report ID 1 (Consumer Control): Play/Pause toggle, Next, Previous,
//	  Volume Up, Volume Down.
//	Report ID 2 (Keyboard/Keypad): standard modifier byte + up to 6
//	  simultaneous keys, covering the full keyboard usage table (letters,
//	  F-keys, etc -- see PressKey/Letter/FunctionKey).
var reportDescriptor = []byte{
	// ---- Consumer Control (Report ID 1) ----
	0x05, 0x0C, //   Usage Page (Consumer)
	0x09, 0x01, //   Usage (Consumer Control)
	0xA1, 0x01, //   Collection (Application)
	0x85, consumerReportID, //     Report ID (1)
	0x15, 0x00, //     Logical Minimum (0)
	0x25, 0x01, //     Logical Maximum (1)
	0x75, 0x01, //     Report Size (1)
	0x95, 0x05, //     Report Count (5)
	0x09, 0xCD, //     Usage (Play/Pause)
	0x09, 0xB5, //     Usage (Scan Next Track)
	0x09, 0xB6, //     Usage (Scan Previous Track)
	0x09, 0xE9, //     Usage (Volume Increment)
	0x09, 0xEA, //     Usage (Volume Decrement)
	0x81, 0x02, //     Input (Data,Var,Abs)
	0x95, 0x01, //     Report Count (1)
	0x75, 0x03, //     Report Size (3)
	0x81, 0x03, //     Input (Const,Var,Abs) -- padding to byte boundary
	0xC0, //   End Collection

	// ---- Keyboard (Report ID 2) ----
	0x05, 0x01, //   Usage Page (Generic Desktop)
	0x09, 0x06, //   Usage (Keyboard)
	0xA1, 0x01, //   Collection (Application)
	0x85, keyboardReportID, //     Report ID (2)
	0x05, 0x07, //     Usage Page (Keyboard/Keypad)
	0x19, 0xE0, //     Usage Minimum (Left Control)
	0x29, 0xE7, //     Usage Maximum (Right GUI)
	0x15, 0x00, //     Logical Minimum (0)
	0x25, 0x01, //     Logical Maximum (1)
	0x75, 0x01, //     Report Size (1)
	0x95, 0x08, //     Report Count (8)
	0x81, 0x02, //     Input (Data,Var,Abs) -- modifier byte
	0x95, 0x01, //     Report Count (1)
	0x75, 0x08, //     Report Size (8)
	0x81, 0x01, //     Input (Const,Array,Abs) -- reserved byte
	0x95, 0x06, //     Report Count (6)
	0x75, 0x08, //     Report Size (8)
	0x15, 0x00, //     Logical Minimum (0)
	0x25, 0x65, //     Logical Maximum (101)
	0x05, 0x07, //     Usage Page (Keyboard/Keypad)
	0x19, 0x00, //     Usage Minimum (0)
	0x29, 0x65, //     Usage Maximum (101)
	0x81, 0x00, //     Input (Data,Array,Abs) -- up to 6 simultaneous keycodes
	0xC0, //   End Collection
}

func sdpRecordXML() string {
	hexDesc := fmt.Sprintf("%x", reportDescriptor)
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001">
    <sequence><uuid value="0x1124"/></sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence><uuid value="0x0100"/><uint16 value="0x0011"/></sequence>
      <sequence><uuid value="0x0011"/></sequence>
    </sequence>
  </attribute>
  <attribute id="0x0005">
    <sequence><uuid value="0x1002"/></sequence>
  </attribute>
  <attribute id="0x0006">
    <sequence><uint16 value="0x656e"/><uint16 value="0x006a"/><uint16 value="0x0100"/></sequence>
  </attribute>
  <attribute id="0x0009">
    <sequence><sequence><uuid value="0x1124"/><uint16 value="0x0101"/></sequence></sequence>
  </attribute>
  <attribute id="0x000d">
    <sequence>
      <sequence>
        <sequence><uuid value="0x0100"/><uint16 value="0x0013"/></sequence>
        <sequence><uuid value="0x0011"/></sequence>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100"><text value="Velocipi Remote"/></attribute>
  <attribute id="0x0101"><text value="Media remote"/></attribute>
  <attribute id="0x0102"><text value="Velocipi"/></attribute>
  <attribute id="0x0200"><uint16 value="0x0100"/></attribute>
  <attribute id="0x0201"><uint16 value="0x0111"/></attribute>
  <attribute id="0x0202"><uint8 value="0x40"/></attribute>
  <attribute id="0x0203"><uint8 value="0x00"/></attribute>
  <attribute id="0x0204"><boolean value="true"/></attribute>
  <attribute id="0x0205"><boolean value="true"/></attribute>
  <attribute id="0x0206">
    <sequence>
      <sequence>
        <uint8 value="0x22"/>
        <text encoding="hex" value="%s"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0207">
    <sequence><sequence><uint16 value="0x0409"/><uint16 value="0x0100"/></sequence></sequence>
  </attribute>
  <attribute id="0x020b"><uint16 value="0x0101"/></attribute>
  <attribute id="0x020d"><boolean value="true"/></attribute>
</record>`, hexDesc)
}

// Client owns the two classic-HID L2CAP profile registrations (control +
// interrupt) and lets callers send Consumer Control input reports over
// whichever interrupt channel is currently connected.
type Client struct {
	conn *dbus.Conn

	mu       sync.Mutex
	intrConn *os.File // nil until a host connects the interrupt channel
}

// New connects to the system D-Bus and registers both classic HID profile
// channels (control PSM 0x11, interrupt PSM 0x13).
func New() (*Client, error) {
	conn, err := dbus.SystemBus()
	if err != nil {
		return nil, fmt.Errorf("bthid: system bus connect: %w", err)
	}

	c := &Client{conn: conn}

	if err := c.registerProfile(ctrlPath, "control", hidUUID, psmCtrl); err != nil {
		return nil, fmt.Errorf("bthid: register control profile: %w", err)
	}
	if err := c.registerProfile(intrPath, "interrupt", intrUUID, psmIntr); err != nil {
		return nil, fmt.Errorf("bthid: register interrupt profile: %w", err)
	}

	return c, nil
}

func (c *Client) registerProfile(path dbus.ObjectPath, name, uuid string, psm uint16) error {
	if err := c.conn.Export(&profile{client: c, name: name}, path, "org.bluez.Profile1"); err != nil {
		return err
	}
	opts := map[string]dbus.Variant{
		"Name":                  dbus.MakeVariant("Velocipi HID (" + name + ")"),
		"Role":                  dbus.MakeVariant("server"),
		"PSM":                   dbus.MakeVariant(psm),
		"RequireAuthentication": dbus.MakeVariant(false),
		"RequireAuthorization":  dbus.MakeVariant(false),
		"AutoConnect":           dbus.MakeVariant(true),
	}
	if name == "control" {
		opts["ServiceRecord"] = dbus.MakeVariant(sdpRecordXML())
	}
	return c.conn.Object(bluezDest, profileMgrPath).Call("org.bluez.ProfileManager1.RegisterProfile", 0, path, uuid, opts).Err
}

// profile implements org.bluez.Profile1 for one of the two HID channels.
type profile struct {
	client *Client
	name   string
}

func (p *profile) Release() *dbus.Error { return nil }

func (p *profile) RequestDisconnection(device dbus.ObjectPath) *dbus.Error {
	if p.name == "interrupt" {
		p.client.mu.Lock()
		p.client.intrConn = nil
		p.client.mu.Unlock()
	}
	return nil
}

func (p *profile) NewConnection(device dbus.ObjectPath, fd dbus.UnixFD, properties map[string]dbus.Variant) *dbus.Error {
	f := os.NewFile(uintptr(fd), p.name)
	if p.name == "interrupt" {
		p.client.mu.Lock()
		p.client.intrConn = f
		p.client.mu.Unlock()
	}
	go p.readLoop(f)
	return nil
}

// readLoop discards whatever the host sends (we don't need GET_REPORT/SET_
// PROTOCOL support for a report-only device), acknowledging control-channel
// transactions with a HIDP HANDSHAKE so the host doesn't consider them
// failed.
func (p *profile) readLoop(f *os.File) {
	buf := make([]byte, 64)
	for {
		n, err := f.Read(buf)
		if err != nil {
			return
		}
		if p.name == "control" && n > 0 {
			if _, err := f.Write([]byte{0x00}); err != nil { // HANDSHAKE, result=successful
				log.Println("bthid: control handshake write error:", err)
			}
		}
	}
}

func (c *Client) sendReport(reportID byte, data []byte) error {
	c.mu.Lock()
	f := c.intrConn
	c.mu.Unlock()
	if f == nil {
		return fmt.Errorf("bthid: no device connected")
	}
	packet := append([]byte{0xA1, reportID}, data...) // 0xA1 = HIDP DATA transaction, Input report
	_, err := f.Write(packet)
	return err
}

// sendReportPulse sends a press followed by a release, with a brief hold in
// between -- matches how the working spike sent these (untested without the
// delay).
func (c *Client) sendReportPulse(reportID byte, press, release []byte) error {
	if err := c.sendReport(reportID, press); err != nil {
		return err
	}
	time.Sleep(80 * time.Millisecond)
	return c.sendReport(reportID, release)
}

func (c *Client) sendConsumerKey(bit byte) error {
	return c.sendReportPulse(consumerReportID, []byte{bit}, []byte{0x00})
}

// PlayPause sends the Consumer Control Play/Pause toggle -- there is no
// separate Play vs Pause usage code; the connected device flips its own
// playback state.
func (c *Client) PlayPause() error { return c.sendConsumerKey(0x01) }

func (c *Client) Next() error { return c.sendConsumerKey(0x02) }

func (c *Client) Previous() error { return c.sendConsumerKey(0x04) }

func (c *Client) VolumeUp() error { return c.sendConsumerKey(0x08) }

func (c *Client) VolumeDown() error { return c.sendConsumerKey(0x10) }

// PressKey sends a standard Keyboard/Keypad usage code (USB HID Usage
// Tables, page 0x07) as a press+release, with no modifier keys held. Use
// Letter or FunctionKey to compute usage codes for common keys, or pass a
// raw usage code directly for anything else on that page.
func (c *Client) PressKey(usage byte) error {
	press := []byte{0x00, 0x00, usage, 0x00, 0x00, 0x00, 0x00, 0x00} // modifier, reserved, keycode x6
	release := []byte{0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
	return c.sendReportPulse(keyboardReportID, press, release)
}

// Letter returns the Keyboard/Keypad usage code for a lowercase ASCII
// letter ('a'-'z').
func Letter(c byte) byte { return 0x04 + (c - 'a') }

// FunctionKey returns the Keyboard/Keypad usage code for F1 (n=1) through
// F12 (n=12).
func FunctionKey(n int) byte { return 0x3A + byte(n-1) }
