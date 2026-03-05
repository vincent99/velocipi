package siyi

import (
	"context"
	"fmt"
	"log"
	"net"
	"sync"
	"time"
)

// AITracker communicates with the Siyi AI tracking module.
// It lives at a separate IP (default 192.168.144.60) but uses the same
// Siyi SDK packet format on port 37260.
//
// NOTE: The specific CMD_IDs for tracking control have not been confirmed from
// the manual. Until they are, only heartbeat is sent and stub methods are
// provided with TODO markers.
type AITracker struct {
	host     string
	mu       sync.Mutex
	conn     *net.UDPConn
	seq      uint16
	tracking bool
}

// NewAITracker creates an AITracker for the given host IP.
func NewAITracker(host string) *AITracker {
	return &AITracker{host: host}
}

// Start opens the UDP connection and sends a periodic heartbeat.
// Blocks until ctx is cancelled.
func (t *AITracker) Start(ctx context.Context) {
	addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%d", t.host, ControlPort))
	if err != nil {
		log.Printf("siyi ai_tracker: resolve %s: %v", t.host, err)
		return
	}
	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		log.Printf("siyi ai_tracker: dial %s: %v", t.host, err)
		return
	}
	defer conn.Close()

	t.mu.Lock()
	t.conn = conn
	t.mu.Unlock()

	go t.recvLoop(ctx, conn)

	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	_ = t.sendRaw(conn, CmdHeartbeat, []byte{0x00})

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			_ = t.sendRaw(conn, CmdHeartbeat, []byte{0x00})
		}
	}
}

func (t *AITracker) recvLoop(ctx context.Context, conn *net.UDPConn) {
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
		// Discard parsed packets for now; log unexpected responses at debug level.
		_, _, _ = parsePacket(buf[:n])
	}
}

func (t *AITracker) sendRaw(conn *net.UDPConn, cmdID byte, data []byte) error {
	t.mu.Lock()
	seq := t.seq
	t.seq++
	t.mu.Unlock()
	pkt := buildPacket(seq, cmdID, data)
	_, err := conn.Write(pkt)
	return err
}

func (t *AITracker) send(cmdID byte, data []byte) error {
	t.mu.Lock()
	conn := t.conn
	t.mu.Unlock()
	if conn == nil {
		return fmt.Errorf("siyi ai_tracker: not connected")
	}
	return t.sendRaw(conn, cmdID, data)
}

// EnableTracking enables or disables object tracking.
// TODO: fill in CMD_ID once confirmed from the AI tracking module manual.
func (t *AITracker) EnableTracking(enabled bool) error {
	// Placeholder — CMD_ID TBD.
	_ = enabled
	return fmt.Errorf("siyi ai_tracker: EnableTracking CMD_ID not yet confirmed")
}

// SetTargetType sets the type of object to track (e.g. person, vehicle).
// TODO: fill in CMD_ID once confirmed from the AI tracking module manual.
func (t *AITracker) SetTargetType(typ int) error {
	_ = typ
	return fmt.Errorf("siyi ai_tracker: SetTargetType CMD_ID not yet confirmed")
}

// SelectTarget locks on to a target at the given normalised screen coordinates.
// TODO: fill in CMD_ID once confirmed from the AI tracking module manual.
func (t *AITracker) SelectTarget(x, y int) error {
	_ = x
	_ = y
	return fmt.Errorf("siyi ai_tracker: SelectTarget CMD_ID not yet confirmed")
}

// Tracking returns whether tracking is currently believed to be active.
func (t *AITracker) Tracking() bool {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.tracking
}
