// SSD1327-based 4-bit grayscale OLED display over SPI.
// Ported from oled.ts; tested against a 256×64 panel.
//
// Wiring:
//
//	SPI MOSI/CLK/CS → standard SPI bus pins
//	DC pin          → GPIO output (low = command, high = data)
//	Reset pin       → GPIO output (low = reset, high = run)
package oled

import (
	"image"
	"image/color"
	"image/draw"
	"math"
	"time"

	"github.com/warthog618/go-gpiocdev"
	"periph.io/x/conn/v3/physic"
	"periph.io/x/conn/v3/spi"
	"periph.io/x/conn/v3/spi/spireg"
	"periph.io/x/host/v3"
)

// Command constants from the SSD1327 datasheet.
const (
	setColumnAddress                  = 0x15
	writeRAM                          = 0x5c
	setRowAddress                     = 0x75
	setRemapDualComLineMode           = 0xa0
	setDisplayStartLine               = 0xa1
	setDisplayOffset                  = 0xa2
	setDisplayModeNormal              = 0xa6
	partialDisplayDisable             = 0xa9
	setFunctionSelection              = 0xab
	displaySleepOn                    = 0xae
	displaySleepOff                   = 0xaf
	setPhaseLength                    = 0xb1
	setFrontClockDivider              = 0xb3
	displayEnhancementA               = 0xb4
	setGPIO                           = 0xb5
	setSecondPrechargePeriod          = 0xb6
	selectDefaultLinearGrayScaleTable = 0xb9
	setPrechargeVoltage               = 0xbb
	setVCOMHVoltage                   = 0xbe
	setContrastCurrent                = 0xc1
	masterCurrentControl              = 0xc7
	setMultiplexRatio                 = 0xca
	displayEnhancementB               = 0xd1
	setCommandLock                    = 0xfd

	enableExternalVSL           = 0x00
	enhancedLowGrayScaleQuality = 0xf8
	reservedEnhancement         = 0x00
	commandsUnlock              = 0x12

	// columnOffset is the hardware column offset for this panel.
	columnOffset = 0x1c
)

// Config holds the hardware configuration for the OLED.
type Config struct {
	// SPIPort is the spidev path, e.g. "/dev/spidev0.0".
	SPIPort string
	// SPISpeed is the SPI clock frequency.
	SPISpeed physic.Frequency
	// GPIOChip is the gpiochip device, e.g. "gpiochip0".
	GPIOChip string
	// DCPin is the BCM GPIO line number for the data/command pin.
	DCPin int
	// ResetPin is the BCM GPIO line number for the reset pin.
	ResetPin int
	// Flip reverses the frame buffer before writing (180° rotation).
	Flip bool
}

// OLED drives a 4-bit grayscale SSD1327 display over SPI.
type OLED struct {
	cfg      Config
	width    int
	height   int
	spiPort  spi.PortCloser
	spiConn  spi.Conn
	dcLine   *gpiocdev.Line
	rstLine  *gpiocdev.Line
	frameBuf []byte
	frameNum int64
}

// New opens the SPI bus and GPIO lines, then initialises the display.
// The caller supplies width and height in pixels.
func New(cfg Config, width, height int) (*OLED, error) {
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

	dcLine, err := gpiocdev.RequestLine(chip, cfg.DCPin,
		gpiocdev.AsOutput(0),
		gpiocdev.WithPullUp,
	)
	if err != nil {
		port.Close()
		return nil, err
	}

	rstLine, err := gpiocdev.RequestLine(chip, cfg.ResetPin,
		gpiocdev.AsOutput(1),
		gpiocdev.WithPullUp,
	)
	if err != nil {
		dcLine.Close()
		port.Close()
		return nil, err
	}

	o := &OLED{
		cfg:      cfg,
		width:    width,
		height:   height,
		spiPort:  port,
		spiConn:  conn,
		dcLine:   dcLine,
		rstLine:  rstLine,
		frameBuf: make([]byte, (width/2)*height),
	}

	if err := o.Init(); err != nil {
		o.Close()
		return nil, err
	}

	return o, nil
}

// Close puts the display to sleep and releases all hardware resources.
func (o *OLED) Close() {
	o.writeCmd(displaySleepOn)
	o.spiPort.Close()
	o.dcLine.Close()
	o.rstLine.Close()
}

// Init resets the display and sends the full initialisation sequence.
func (o *OLED) Init() error {
	if err := o.Reset(); err != nil {
		return err
	}

	o.writeCmd(setCommandLock, commandsUnlock)
	o.writeCmd(displaySleepOn)
	o.setAddress(0, 0, o.width/4-1, o.height-1)
	o.writeCmd(setFrontClockDivider, 0x91)
	o.writeCmd(setMultiplexRatio, 0x3f)
	o.writeCmd(setDisplayOffset, 0)
	o.writeCmd(setDisplayStartLine, 0)
	o.writeCmd(setRemapDualComLineMode,
		0b00010100,
		0b00010011,
	)
	o.writeCmd(setGPIO, 0)
	o.writeCmd(setFunctionSelection, 1)
	o.writeCmd(displayEnhancementA,
		enableExternalVSL|0xa0,
		enhancedLowGrayScaleQuality|0x05,
	)
	o.writeCmd(setContrastCurrent, 0xff)
	o.writeCmd(masterCurrentControl, 0xf)
	o.writeCmd(selectDefaultLinearGrayScaleTable)
	o.writeCmd(setPhaseLength, 0xe2)
	o.writeCmd(setSecondPrechargePeriod, 0x8)
	o.writeCmd(displayEnhancementB,
		reservedEnhancement|0xa2,
		0x20,
	)
	o.writeCmd(setPrechargeVoltage, 0x1f)
	o.writeCmd(setVCOMHVoltage, 0x7)
	o.writeCmd(setDisplayModeNormal)
	o.writeCmd(partialDisplayDisable)
	o.writeCmd(displaySleepOff)

	return nil
}

// SetBrightness sets the display contrast (0–255).
func (o *OLED) SetBrightness(b byte) {
	o.writeCmd(setContrastCurrent, b)
}

// Reset pulses the reset pin low for 200 ms then releases it.
func (o *OLED) Reset() error {
	if err := o.rstLine.SetValue(0); err != nil {
		return err
	}
	time.Sleep(200 * time.Millisecond)
	if err := o.rstLine.SetValue(1); err != nil {
		return err
	}
	time.Sleep(200 * time.Millisecond)

	black := image.NewRGBA(image.Rect(0, 0, o.width, o.height))
	draw.Draw(black, black.Bounds(), &image.Uniform{color.RGBA{0, 0, 0, 255}}, image.Point{}, draw.Src)

	o.Blit(black)
	o.Blit(black)

	return nil
}

// Blit converts img to 4-bit grayscale and writes it to the display using
// double buffering. num alternates between frames (even / odd) to avoid
// tearing while the panel scrolls to the new buffer.
func (o *OLED) Blit(img image.Image) {
	bounds := img.Bounds()
	buf := o.frameBuf

	framePtr := 0
	inc := 1
	if o.cfg.Flip {
		framePtr = len(buf) - 1
		inc = -1
	}

	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x += 2 {
			hi := toGray(img.At(x, y))
			lo := toGray(img.At(x+1, y))
			if o.cfg.Flip {
				buf[framePtr] = hi | (lo << 4)
			} else {
				buf[framePtr] = lo | (hi << 4)
			}
			framePtr += inc
		}
	}

	yStart := 0
	displayOffset := 0
	if o.frameNum%2 == 1 {
		yStart = o.height
		displayOffset = o.height
	}
	o.frameNum++

	// Write pixels into the off-screen buffer area.
	o.setAddress(0, yStart, o.width/4-1, yStart+o.height-1)

	const step = 4096
	for i := 0; i < len(buf); i += step {
		end := min(i+step, len(buf))
		o.writeData(buf[i:end])
	}

	// Flip the display start line to reveal the new frame.
	o.writeCmd(setDisplayStartLine, byte(displayOffset))
}

// Width returns the display width in pixels.
func (o *OLED) Width() int { return o.width }

// Height returns the display height in pixels.
func (o *OLED) Height() int { return o.height }

// -------------------------------------------------------------------------
// Private helpers
// -------------------------------------------------------------------------

func (o *OLED) spiWrite(data []byte) {
	_ = o.spiConn.Tx(data, nil)
}

func (o *OLED) writeData(data []byte) {
	_ = o.dcLine.SetValue(1)
	o.spiWrite(data)
}

func (o *OLED) writeCmd(cmd byte, data ...byte) {
	_ = o.dcLine.SetValue(0)
	o.spiWrite([]byte{cmd})
	if len(data) > 0 {
		o.writeData(data)
	}
}

func (o *OLED) setColumnAddress(start, end int) {
	o.writeCmd(setColumnAddress, byte(start), byte(end))
}

func (o *OLED) setRowAddress(start, end int) {
	o.writeCmd(setRowAddress, byte(start), byte(end))
}

func (o *OLED) setAddress(x0, y0, x1, y1 int) {
	o.setRowAddress(y0, y1)
	o.setColumnAddress(x0+columnOffset, x1+columnOffset)
	o.writeCmd(writeRAM)
}

// toGray converts a pixel to a 4-bit (0–15) grayscale value using the same
// weighted luminance formula as the original TypeScript implementation.
// It respects alpha by premultiplying before quantising.
func toGray(c interface{ RGBA() (r, g, b, a uint32) }) byte {
	r, g, b, a := c.RGBA()
	if a == 0 {
		return 0
	}
	// image.Color returns 16-bit channels; scale to 0–255.
	rf := float64(r>>8) * 0.30
	gf := float64(g>>8) * 0.59
	bf := float64(b>>8) * 0.11
	af := float64(a>>8) / 255.0
	gray := math.Round((rf+gf+bf)*af) / 16.0
	v := byte(gray)
	if v > 15 {
		v = 15
	}
	return v
}
