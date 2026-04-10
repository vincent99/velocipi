// Package blescan provides a shared BLE scan multiplexer.
//
// Multiple subsystems (TPMS, AirCon, etc.) register callbacks via Register,
// then a single call to Run starts the BLE adapter and fans scan results out
// to every registered callback. Run restarts automatically if the scan errors.
//
// Callers that need exclusive adapter access (e.g. GATT connect + discover)
// should call Pause() first. Pause stops the running scan and returns a resume
// function; call the resume function when done with the adapter.
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

	// pauseMu serialises pause requests. Pause() holds it for the duration of
	// the pause; the scan loop acquires+releases it at the top of each iteration
	// so it blocks while paused. globalAdapter is set once by Run().
	pauseMu       sync.Mutex
	globalAdapter *bluetooth.Adapter
)

// Register adds cb to the list of callbacks that receive every scan result.
// Safe to call before or after Run.
func Register(cb Callback) {
	mu.Lock()
	callbacks = append(callbacks, cb)
	mu.Unlock()
}

// Pause stops the active BLE scan so the caller can use the adapter exclusively
// (e.g. for GATT connect + service discovery). It returns a resume function
// that must be called when the exclusive operation is complete.
//
// Only one pause is active at a time; concurrent callers queue behind each other.
func Pause() func() {
	pauseMu.Lock()
	// Stop any currently-running scan so the adapter is free immediately.
	if globalAdapter != nil {
		_ = globalAdapter.StopScan()
	}
	return func() { pauseMu.Unlock() }
}

// Run enables the BLE adapter, starts scanning, and fans each scan result out
// to all registered callbacks. Restarts on error. Blocks until ctx is done.
func Run(ctx context.Context) {
	adapter := bluetooth.DefaultAdapter
	if err := adapter.Enable(); err != nil {
		log.Println("blescan: adapter enable:", err)
	}
	defer adapter.StopScan()

	mu.Lock()
	globalAdapter = adapter
	mu.Unlock()

	fanOut := func(a *bluetooth.Adapter, r bluetooth.ScanResult) {
		mu.RLock()
		cbs := callbacks
		mu.RUnlock()
		for _, cb := range cbs {
			cb(a, r)
		}
	}

	for {
		// Block here while a Pause() is active.
		pauseMu.Lock()
		pauseMu.Unlock()

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

		_ = adapter.StopScan() // clear any lingering scan before starting
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
