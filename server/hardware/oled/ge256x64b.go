//go:build linux

// Noritake Itron GE256X64B-7032B OLED display driver over SPI.
//
// Wiring (CN2 serial connector, SPI mode selected via jumper J2+J3=SHORT+SHORT):
//
//	Pin 1 VCC     → 3.3 V
//	Pin 2 SIN     → SPI MOSI
//	Pin 3 GND     → Ground
//	Pin 4 SBUSY   → GPIO input (StatusPin — high=busy, low=ready)
//	Pin 5 SCK     → SPI clock
//	Pin 6 /RESET  → GPIO output (ResetPin — active low)
//	Pin 7 /CS     → SPI CS (hardware-managed by the SPI bus driver)
//
// Protocol summary (from datasheet DS-1859-0000-00):
//   - SPI Mode 0 (CPOL=0, CPHA=0), MSB first, max ~2.5 MHz (200 ns half-period).
//   - The display raises SBUSY while processing each byte; poll StatusPin
//     (high=busy, low=ready) before sending each byte.
//   - Display memory is 1-bit monochrome (no greyscale).
//   - Full-screen write uses the Real-time bit image command (§7.1.29):
//     1Fh 28h 66h 11h xL xH yL yH 01h d(1)…d(k)
//     x = width in pixels (little-endian), y = height/8 (little-endian),
//     k = x×y bytes, column-major order, B7 = top pixel of each 8-row band.
package oled

import (
	"image"
	"time"

	"github.com/warthog618/go-gpiocdev"
	"periph.io/x/conn/v3/spi"
	"periph.io/x/conn/v3/spi/spireg"
	"periph.io/x/host/v3"
)

// Noritake drives a GE256X64B-7032B monochrome OLED display over SPI.
type Noritake struct {
	cfg       Config
	width     int
	height    int
	spiPort   spi.PortCloser
	spiConn   spi.Conn
	sbusyLine *gpiocdev.Line
	rstLine   *gpiocdev.Line
	frameBuf  []byte // column-major, 8 pixels per byte
}

// NewGE256X64B opens the SPI bus and GPIO lines, resets the display, and
// sends the initialise command. The caller supplies width and height in pixels;
// height must be a multiple of 8.
func NewGE256X64B(cfg Config, width, height int) (*Noritake, error) {
	if _, err := host.Init(); err != nil {
		return nil, err
	}

	port, err := spireg.Open(cfg.SPIPort)
	if err != nil {
		return nil, err
	}

	conn, err := port.Connect(cfg.SPISpeed, spi.Mode0, 8)
	if err != nil {
		port.Close()
		return nil, err
	}

	chip := cfg.GPIOChip
	if chip == "" {
		chip = "gpiochip0"
	}

	// SBUSY is an input; high = busy, low = ready.
	sbusyLine, err := gpiocdev.RequestLine(chip, cfg.StatusPin,
		gpiocdev.AsInput,
	)
	if err != nil {
		port.Close()
		return nil, err
	}

	// /RESET is an output; start high (not in reset).
	rstLine, err := gpiocdev.RequestLine(chip, cfg.ResetPin,
		gpiocdev.AsOutput(1),
		gpiocdev.WithPullUp,
	)
	if err != nil {
		sbusyLine.Close()
		port.Close()
		return nil, err
	}

	// column-major frame buffer: width columns × (height/8) bands
	n := &Noritake{
		cfg:       cfg,
		width:     width,
		height:    height,
		spiPort:   port,
		spiConn:   conn,
		sbusyLine: sbusyLine,
		rstLine:   rstLine,
		frameBuf:  make([]byte, width*(height/8)),
	}

	if err := n.Init(); err != nil {
		n.Close()
		return nil, err
	}

	return n, nil
}

// Close puts the display into power-save mode and releases hardware resources.
func (n *Noritake) Close() {
	// Display power OFF (screen saver p=00h).
	n.write([]byte{0x1f, 0x28, 0x61, 0x40, 0x00})
	n.spiPort.Close()
	n.sbusyLine.Close()
	n.rstLine.Close()
}

// Init resets the display and sends the initialise command.
func (n *Noritake) Init() error {
	if err := n.Reset(); err != nil {
		return err
	}
	// ESC @ — restore all settings to defaults (returns to text mode).
	n.write([]byte{0x1b, 0x40})
	// US f 1 — select graphic (bit-image) draw mode.
	n.write([]byte{0x1f, 0x66, 0x01})
	// FF — clear screen.
	n.write([]byte{0x0c})
	return nil
}

// SetBrightness sets the brightness level. b is mapped from the 0–255 range
// into the display's 1–8 scale (per command US X n, §7.1.22).
func (n *Noritake) SetBrightness(b byte) {
	level := byte(1 + int(b)*7/255) // map [0,255] → [1,8]
	if level < 1 {
		level = 1
	}
	if level > 8 {
		level = 8
	}
	n.write([]byte{0x1f, 0x58, level})
}

// Reset pulses /RESET low for 5 ms then waits for the display to boot.
func (n *Noritake) Reset() error {
	if err := n.rstLine.SetValue(0); err != nil {
		return err
	}
	time.Sleep(5 * time.Millisecond)
	if err := n.rstLine.SetValue(1); err != nil {
		return err
	}
	// The display needs time to complete its internal reset sequence.
	time.Sleep(100 * time.Millisecond)
	return nil
}

// Blit converts img to 1-bit monochrome and writes a full-screen image.
// The image is quantised: pixels with luma ≥ 128 are white, others black.
// Pixels are packed column-major, B7 = topmost pixel of each 8-row band.
func (n *Noritake) Blit(img image.Image) {
	bounds := img.Bounds()
	bands := n.height / 8
	buf := n.frameBuf

	// Clear the frame buffer.
	for i := range buf {
		buf[i] = 0
	}

	for y := bounds.Min.Y; y < bounds.Max.Y && y < n.height; y++ {
		band := y / 8
		bit := uint(7 - (y % 8)) // B7 = top pixel
		for x := bounds.Min.X; x < bounds.Max.X && x < n.width; x++ {
			if lumaOver128(img.At(x, y)) {
				col := x
				if n.cfg.Flip {
					col = n.width - 1 - x
					band = bands - 1 - (y / 8)
					bit = uint(y % 8) // reversed vertical
				}
				buf[col*bands+band] |= 1 << bit
			}
		}
	}

	// Position cursor at (0, 0).
	// US $ xL xH yL yH — x in 1-dot units, y in 8-dot units.
	n.write([]byte{0x1f, 0x24, 0x00, 0x00, 0x00, 0x00})

	// Real-time bit image: 1Fh 28h 66h 11h xL xH yL yH g d(1)...d(k)
	xL := byte(n.width & 0xff)
	xH := byte(n.width >> 8)
	yVal := n.height / 8
	yL := byte(yVal & 0xff)
	yH := byte(yVal >> 8)
	header := []byte{0x1f, 0x28, 0x66, 0x11, xL, xH, yL, yH, 0x01}
	n.write(header)
	n.write(buf)
}

// Width returns the display width in pixels.
func (n *Noritake) Width() int { return n.width }

// Height returns the display height in pixels.
func (n *Noritake) Height() int { return n.height }

// -------------------------------------------------------------------------
// Private helpers
// -------------------------------------------------------------------------

// write sends data one byte at a time, waiting for SBUSY to go low before
// each byte.
func (n *Noritake) write(data []byte) {
	buf := [1]byte{}
	for _, b := range data {
		for {
			v, err := n.sbusyLine.Value()
			if err != nil || v == 0 {
				break
			}
		}
		buf[0] = b
		_ = n.spiConn.Tx(buf[:], nil)
	}
}

// lumaOver128 returns true when the pixel's luminance is ≥ 128.
func lumaOver128(c interface{ RGBA() (r, g, b, a uint32) }) bool {
	r, g, b, a := c.RGBA()
	if a == 0 {
		return false
	}
	// 16-bit channels → 0–255 weighted luma, premultiplied.
	luma := (float64(r>>8)*0.30 + float64(g>>8)*0.59 + float64(b>>8)*0.11) *
		(float64(a>>8) / 255.0)
	return luma >= 128
}
