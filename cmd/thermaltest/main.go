// thermaltest verifies protocol packet math and probes a thermal camera.
//
// Usage:
//
//	go run ./cmd/thermaltest/ -dev /dev/ttyAMA4 [-verbose] [-brightness]
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"time"

	"github.com/vincent99/velocipi/server/hardware/thermalcam"
)

const (
	flagWrite = 0x00
	flagRead  = 0x01
)

func main() {
	dev := flag.String("dev", "/dev/ttyAMA0", "serial device")
	baud := flag.Int("baud", 115200, "baud rate")
	timeout := flag.Duration("timeout", 30*time.Second, "max time to wait for camera ready")
	verbose := flag.Bool("verbose", false, "log every sent/received byte")
	brightness := flag.Bool("brightness", false, "send SetBrightness(100) and show raw response instead of waiting for ready")
	flag.Parse()

	// --- Checksum / packet-building verification (no device needed) ---
	// Docs: SetBrightness(100) should produce TX = F0 05 36 78 02 00 64 14 FF
	//                          and RX            = F0 05 36 78 02 03 01 B4 FF
	wantTX := []byte{0xF0, 0x05, 0x36, 0x78, 0x02, 0x00, 0x64, 0x14, 0xFF}
	wantRX := []byte{0xF0, 0x05, 0x36, 0x78, 0x02, 0x03, 0x01, 0xB4, 0xFF}
	gotTX := thermalcam.PacketBytes(0x78, 0x02, flagWrite, []byte{0x64})
	if bytes.Equal(gotTX, wantTX) {
		log.Printf("checksum OK  — TX: % X", gotTX)
	} else {
		log.Printf("checksum FAIL — want: % X", wantTX)
		log.Printf("               got:  % X", gotTX)
	}
	log.Printf("expected RX         — RX: % X", wantRX)

	// --- Device probe ---
	log.Printf("opening %s at %d baud", *dev, *baud)
	cam, err := thermalcam.NewBaud(*dev, *baud)
	if err != nil {
		log.Fatalf("open error: %v", err)
	}
	defer cam.Close()
	cam.Verbose = *verbose

	if *brightness {
		log.Println("sending SetBrightness(100), reading raw response…")
		raw, sendErr := cam.RawExchange(
			thermalcam.PacketBytes(0x78, 0x02, flagWrite, []byte{0x64}),
			32, 2*time.Second,
		)
		if len(raw) > 0 {
			log.Printf("raw RX (%d bytes): % X", len(raw), raw)
			log.Printf("expected           % X", wantRX)
			if bytes.Equal(raw, wantRX) {
				log.Println("MATCH ✓")
			} else {
				log.Println("MISMATCH — check baud rate / protocol version")
			}
		}
		if sendErr != nil && sendErr != io.EOF {
			log.Printf("exchange error: %v", sendErr)
		}
		return
	}

	log.Printf("waiting for ready (timeout %s)…", *timeout)
	state, errs := cam.ReadState(*timeout)
	if state == nil {
		log.Fatalf("failed: %v", errs[0])
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(state)

	if len(errs) > 0 {
		fmt.Fprintf(os.Stderr, "\n%d error(s) reading params:\n", len(errs))
		for _, e := range errs {
			fmt.Fprintf(os.Stderr, "  %v\n", e)
		}
		os.Exit(1)
	}
}
