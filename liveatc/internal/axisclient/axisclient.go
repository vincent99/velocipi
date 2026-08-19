// Package axisclient dials the velocipi server's websocket and feeds its
// aircraft position (axisState frames) into the GPS store. It is optional and
// additive: the push API (POST /api/gps, WS /ws/gps) keeps working regardless.
package axisclient

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"github.com/gorilla/websocket"

	"github.com/vincent99/liveatc/internal/gps"
)

// axisState is the subset of the server's "axisState" ws frame we consume. The
// server sends the whole avionics state; we map the position/velocity fields
// onto GPSFix.
type axisState struct {
	Type     string  `json:"type"`
	Lat      float64 `json:"lat"`
	Lon      float64 `json:"lon"`
	AltFt    float64 `json:"altFt"`
	Heading  float64 `json:"heading"`
	SpeedKts float64 `json:"speedKts"`
}

// Client consumes axisState frames from a velocipi websocket into a gps.Store.
type Client struct {
	url   string
	store *gps.Store
	log   *slog.Logger
}

// New builds a Client for the given ws URL (e.g. ws://localhost:8080/ws).
func New(url string, store *gps.Store, log *slog.Logger) *Client {
	return &Client{url: url, store: store, log: log}
}

const maxBackoff = 30 * time.Second

// Run maintains the connection until ctx is cancelled, reconnecting with backoff
// if the server is unreachable or the connection drops.
func (c *Client) Run(ctx context.Context) {
	backoff := time.Second
	for ctx.Err() == nil {
		conn, _, err := websocket.DefaultDialer.DialContext(ctx, c.url, nil)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			c.log.Warn("axis ws dial failed, retrying", "url", c.url, "err", err, "in", backoff)
			if !sleep(ctx, backoff) {
				return
			}
			backoff = grow(backoff)
			continue
		}
		c.log.Info("axis ws connected", "url", c.url)
		backoff = time.Second // reset on a successful connect
		c.readLoop(ctx, conn)
		if ctx.Err() != nil {
			return
		}
		// Brief pause before reconnecting after a drop.
		if !sleep(ctx, time.Second) {
			return
		}
	}
}

// readLoop reads frames until the connection errors or ctx is cancelled.
func (c *Client) readLoop(ctx context.Context, conn *websocket.Conn) {
	// Unblock the blocking ReadMessage when ctx is cancelled.
	stop := make(chan struct{})
	defer close(stop)
	go func() {
		select {
		case <-ctx.Done():
			_ = conn.Close()
		case <-stop:
		}
	}()
	defer conn.Close()

	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			if ctx.Err() == nil {
				c.log.Warn("axis ws read error, reconnecting", "err", err)
			}
			return
		}
		var m axisState
		if json.Unmarshal(data, &m) != nil || m.Type != "axisState" {
			continue // ignore other message types (ping, airReading, ...)
		}
		c.store.Update(gps.GPSFix{
			Lat:           m.Lat,
			Lon:           m.Lon,
			AltFt:         m.AltFt,
			HeadingDeg:    m.Heading,
			GroundspeedKt: m.SpeedKts,
			FixQuality:    1,
			Valid:         true,
		})
	}
}

func grow(b time.Duration) time.Duration {
	b *= 2
	if b > maxBackoff {
		return maxBackoff
	}
	return b
}

// sleep waits d, returning false if ctx is cancelled first.
func sleep(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}
