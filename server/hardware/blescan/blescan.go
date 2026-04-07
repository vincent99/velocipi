// Package blescan provides a shared BLE scan multiplexer.
//
// Multiple subsystems (TPMS, AirCon, etc.) register callbacks via Register,
// then a single call to Run starts the BLE adapter and fans scan results out
// to every registered callback. Run restarts automatically if the scan errors.
package blescan

import (
	"context"
	"log"
	"sync"
	"time"

	"tinygo.org/x/bluetooth"
)

type Callback func(*bluetooth.Adapter, bluetooth.ScanResult)

var (
	mu        sync.RWMutex
	callbacks []Callback
)

// Register adds cb to the list of callbacks that receive every scan result.
// Safe to call before or after Run.
func Register(cb Callback) {
	mu.Lock()
	callbacks = append(callbacks, cb)
	mu.Unlock()
}

// Run enables the BLE adapter, starts scanning, and fans each scan result out
// to all registered callbacks. Restarts on error. Blocks until ctx is done.
func Run(ctx context.Context) {
	adapter := bluetooth.DefaultAdapter
	if err := adapter.Enable(); err != nil {
		log.Println("blescan: adapter enable:", err)
	}

	fanOut := func(a *bluetooth.Adapter, r bluetooth.ScanResult) {
		mu.RLock()
		cbs := callbacks
		mu.RUnlock()
		for _, cb := range cbs {
			cb(a, r)
		}
	}

	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		// Stop the scan when the context is cancelled.
		scanDone := make(chan struct{})
		go func() {
			select {
			case <-ctx.Done():
				_ = adapter.StopScan()
			case <-scanDone:
			}
		}()

		if err := adapter.Scan(fanOut); err != nil && ctx.Err() == nil {
			log.Println("blescan: scan error:", err)
		}
		close(scanDone)

		if ctx.Err() != nil {
			return
		}

		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Second):
		}
	}
}
