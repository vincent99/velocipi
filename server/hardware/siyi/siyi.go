// Package siyi implements the Siyi SDK over UDP for gimbal cameras such as the
// A8 mini. The protocol uses binary framed packets on port 37260.
package siyi

import (
	"context"
	"encoding/binary"
	"fmt"
	"log"
	"math"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/hardware/g3x"
)

// FollowMode is the gimbal stabilisation mode.
type FollowMode int

const (
	ModeLock   FollowMode = 3
	ModeFollow FollowMode = 4
	ModeFPV    FollowMode = 5
)

// Manager handles the UDP connection to a single Siyi gimbal.
type Manager struct {
	cfg        config.CameraConfig
	addr       string // host:37260
	mu         sync.Mutex
	conn       *net.UDPConn
	seq        uint16
	attitude   GimbalAttitude
	onAttitude func(name string, att GimbalAttitude)
	bootMs     atomic.Uint32
}

// New creates a Siyi Manager for the given camera config.
// onAttitude is called each time a new attitude packet is received; it may be nil.
func New(cfg config.CameraConfig, onAttitude func(name string, att GimbalAttitude)) *Manager {
	return &Manager{
		cfg:        cfg,
		addr:       fmt.Sprintf("%s:%d", cfg.Host, ControlPort),
		onAttitude: onAttitude,
	}
}

// Start opens the UDP socket, runs the heartbeat (1 Hz), attitude poll (10 Hz),
// and receive loops. Blocks until ctx is cancelled.
func (m *Manager) Start(ctx context.Context) {
	addr, err := net.ResolveUDPAddr("udp", m.addr)
	if err != nil {
		log.Printf("siyi %s: resolve %s: %v", m.cfg.Name, m.addr, err)
		return
	}
	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		log.Printf("siyi %s: dial %s: %v", m.cfg.Name, m.addr, err)
		return
	}
	defer conn.Close()

	m.mu.Lock()
	m.conn = conn
	m.mu.Unlock()

	go m.recvLoop(ctx, conn)

	heartbeat := time.NewTicker(time.Second)
	attitude := time.NewTicker(100 * time.Millisecond)
	defer heartbeat.Stop()
	defer attitude.Stop()

	// Send initial heartbeat immediately.
	_ = m.sendRaw(conn, CmdHeartbeat, []byte{0x00})

	for {
		select {
		case <-ctx.Done():
			return
		case <-heartbeat.C:
			_ = m.sendRaw(conn, CmdHeartbeat, []byte{0x00})
			m.bootMs.Add(1000)
		case <-attitude.C:
			_ = m.sendRaw(conn, CmdAcquireAttitude, nil)
			m.bootMs.Add(100)
		}
	}
}

func (m *Manager) recvLoop(ctx context.Context, conn *net.UDPConn) {
	buf := make([]byte, 512)
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		_ = conn.SetReadDeadline(time.Now().Add(500 * time.Millisecond))
		n, err := conn.Read(buf)
		if err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				continue
			}
			return
		}
		cmdID, data, err := parsePacket(buf[:n])
		if err != nil {
			continue
		}
		if cmdID == CmdAcquireAttitude {
			att, err := parseAttitude(data)
			if err == nil {
				m.mu.Lock()
				m.attitude = att
				cb := m.onAttitude
				name := m.cfg.Name
				m.mu.Unlock()
				if cb != nil {
					cb(name, att)
				}
			}
		}
	}
}

func (m *Manager) sendRaw(conn *net.UDPConn, cmdID byte, data []byte) error {
	m.mu.Lock()
	seq := m.seq
	m.seq++
	m.mu.Unlock()

	pkt := buildPacket(seq, cmdID, data)
	_, err := conn.Write(pkt)
	return err
}

func (m *Manager) send(cmdID byte, data []byte) error {
	m.mu.Lock()
	conn := m.conn
	m.mu.Unlock()
	if conn == nil {
		return fmt.Errorf("siyi %s: not connected", m.cfg.Name)
	}
	return m.sendRaw(conn, cmdID, data)
}

// Host returns the IP/hostname of this gimbal.
func (m *Manager) Host() string {
	return m.cfg.Host
}

// Attitude returns the most recently received gimbal attitude.
func (m *Manager) Attitude() GimbalAttitude {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.attitude
}

// GimbalRotate sends a gimbal rotation command. yaw and pitch are rates in
// the range -100..+100 (positive = right/up).
func (m *Manager) GimbalRotate(yaw, pitch int8) error {
	return m.send(CmdGimbalRotation, []byte{byte(yaw), byte(pitch)})
}

// ZoomRate sends a manual zoom command. direction: 1=zoom in, 0=stop, -1=zoom out.
func (m *Manager) ZoomRate(direction int8) error {
	var b byte
	switch {
	case direction > 0:
		b = 0x01
	case direction < 0:
		b = 0xFF
	default:
		b = 0x00
	}
	return m.send(CmdManualZoom, []byte{b})
}

// AbsoluteZoom sets zoom level. z is e.g. 2.0 for 2× or 10.5 for 10.5×.
func (m *Manager) AbsoluteZoom(z float32) error {
	intPart := uint8(z)
	fracPart := uint8(math.Round(float64(z-float32(intPart)) * 10))
	return m.send(CmdAbsoluteZoom, []byte{intPart, fracPart})
}

// Center re-centres the gimbal.
func (m *Manager) Center() error {
	return m.send(CmdCenter, nil)
}

// TakePhoto triggers a photo capture.
func (m *Manager) TakePhoto() error {
	return m.send(CmdPhoto, []byte{PhotoTakePicture})
}

// ToggleVideo starts or stops video recording.
func (m *Manager) ToggleVideo() error {
	return m.send(CmdPhoto, []byte{PhotoRecordToggle})
}

// SetMode sets the gimbal stabilisation mode.
func (m *Manager) SetMode(mode FollowMode) error {
	return m.send(CmdPhoto, []byte{byte(mode)})
}

// AutoFocus triggers auto-focus.
func (m *Manager) AutoFocus() error {
	return m.send(CmdAutoFocus, nil)
}

// ManualFocus adjusts focus. direction: 1=far, 0=stop, -1=near.
func (m *Manager) ManualFocus(direction int8) error {
	var b byte
	switch {
	case direction > 0:
		b = 0x01
	case direction < 0:
		b = 0xFF
	default:
		b = 0x00
	}
	return m.send(CmdManualFocus, []byte{b})
}

// SendAttitude sends the aircraft attitude to the gimbal (CmdExternalAttitude).
// Payload: uint32 bootMs | float32 roll_rad | float32 pitch_rad | float32 yaw_rad |
//
//	float32 rollRate | float32 pitchRate | float32 yawRate  (28 bytes total)
func (m *Manager) SendAttitude(state g3x.State) error {
	buf := make([]byte, 28)
	binary.LittleEndian.PutUint32(buf[0:4], m.bootMs.Load())
	toRad := func(deg float64) float32 { return float32(deg * math.Pi / 180.0) }
	binary.LittleEndian.PutUint32(buf[4:8], math.Float32bits(toRad(state.Roll)))
	binary.LittleEndian.PutUint32(buf[8:12], math.Float32bits(toRad(state.Pitch)))
	binary.LittleEndian.PutUint32(buf[12:16], math.Float32bits(toRad(state.Yaw)))
	// Rates are zero for the mock G3X.
	binary.LittleEndian.PutUint32(buf[16:20], math.Float32bits(0))
	binary.LittleEndian.PutUint32(buf[20:24], math.Float32bits(0))
	binary.LittleEndian.PutUint32(buf[24:28], math.Float32bits(0))
	return m.send(CmdExternalAttitude, buf)
}

// SendGPS sends aircraft GPS data to the gimbal (CmdPositionData).
// Payload: uint32 bootMs | int32 lat×1e7 | int32 lon×1e7 | int32 altMSL_mm |
//
//	int32 altEllipsoid_mm | int32 velN_mms | int32 velE_mms | int32 velD_mms (32 bytes)
func (m *Manager) SendGPS(state g3x.State) error {
	buf := make([]byte, 32)
	binary.LittleEndian.PutUint32(buf[0:4], m.bootMs.Load())

	latE7 := int32(state.Lat * 1e7)
	lonE7 := int32(state.Lon * 1e7)
	altMSLmm := int32(state.AltFt * 0.3048 * 1000) // ft → mm

	// Velocity from speed and heading.
	headingRad := state.Heading * math.Pi / 180.0
	speedMs := state.SpeedKts * 0.514444
	velN := int32(speedMs * math.Cos(headingRad) * 1000)
	velE := int32(speedMs * math.Sin(headingRad) * 1000)

	binary.LittleEndian.PutUint32(buf[4:8], uint32(latE7))
	binary.LittleEndian.PutUint32(buf[8:12], uint32(lonE7))
	binary.LittleEndian.PutUint32(buf[12:16], uint32(altMSLmm))
	binary.LittleEndian.PutUint32(buf[16:20], uint32(altMSLmm)) // ellipsoid ≈ MSL for mock
	binary.LittleEndian.PutUint32(buf[20:24], uint32(velN))
	binary.LittleEndian.PutUint32(buf[24:28], uint32(velE))
	binary.LittleEndian.PutUint32(buf[28:32], 0) // velD = 0
	return m.send(CmdPositionData, buf)
}
