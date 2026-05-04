// Package thermalcam implements the UART serial protocol for the
// HM-TM5X-XRG/C series thermal camera modules.
// https://www.axisflying.com/products/axisflying-high-resolution-256192-384288-640512-thermal-imaging-camera-for-fpv-drone
//
// Protocol: 115200 8N1, framed packets:
//
//	BEGIN(0xF0) SIZE DevAddr(0x36) ClassAddr SubclassAddr Flag DATA... CHK END(0xFF)
//	SIZE = len(DATA) + 4
//	CHK  = low byte of (DevAddr + ClassAddr + SubclassAddr + Flag + sum(DATA))
package thermalcam

import (
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/vincent99/velocipi/server/hardware/serial"
)

const (
	devAddr   = 0x36
	beginByte = 0xF0
	endByte   = 0xFF
	flagWrite = 0x00
	flagRead  = 0x01
	flagOK    = 0x03
)

// ThermalCam communicates with a HM-TM5X-XRG/C thermal camera over UART.
type ThermalCam struct {
	mu sync.Mutex
	f  *os.File
}

// New opens the serial device and configures it for 115200 8N1.
func New(device string) (*ThermalCam, error) {
	f, err := serial.Open(device, 115200)
	if err != nil {
		return nil, fmt.Errorf("thermalcam: %w", err)
	}
	return &ThermalCam{f: f}, nil
}

// Close releases the serial port.
func (t *ThermalCam) Close() error {
	return t.f.Close()
}

// --- packet helpers ---

func checksum(classAddr, subclassAddr, flag byte, data []byte) byte {
	sum := uint32(devAddr) + uint32(classAddr) + uint32(subclassAddr) + uint32(flag)
	for _, b := range data {
		sum += uint32(b)
	}
	return byte(sum)
}

func buildPacket(classAddr, subclassAddr, flag byte, data []byte) []byte {
	n := len(data)
	size := byte(n + 4)
	chk := checksum(classAddr, subclassAddr, flag, data)
	pkt := make([]byte, 0, n+8)
	pkt = append(pkt, beginByte, size, devAddr, classAddr, subclassAddr, flag)
	pkt = append(pkt, data...)
	pkt = append(pkt, chk, endByte)
	return pkt
}

// readByte reads one byte, returning an error on timeout (0-byte read with VTIME).
func (t *ThermalCam) readByte() (byte, error) {
	var b [1]byte
	n, err := t.f.Read(b[:])
	if err != nil {
		return 0, err
	}
	if n == 0 {
		return 0, fmt.Errorf("thermalcam: read timeout")
	}
	return b[0], nil
}

// recv reads and validates one response packet, returning its fields.
func (t *ThermalCam) recv() (classAddr, subclassAddr, flag byte, data []byte, err error) {
	// Sync to BEGIN byte, discarding any leading garbage.
	var b byte
	for {
		b, err = t.readByte()
		if err != nil {
			return
		}
		if b == beginByte {
			break
		}
	}

	// SIZE byte.
	b, err = t.readByte()
	if err != nil {
		return
	}
	size := int(b)
	if size < 4 {
		err = fmt.Errorf("thermalcam: invalid SIZE %d", size)
		return
	}

	// Read SIZE bytes (DevAddr + ClassAddr + SubclassAddr + Flag + N*DATA) + CHK + END.
	body := make([]byte, size+2)
	for i := range body {
		body[i], err = t.readByte()
		if err != nil {
			return
		}
	}

	if body[0] != devAddr {
		err = fmt.Errorf("thermalcam: unexpected device addr 0x%02X", body[0])
		return
	}
	classAddr = body[1]
	subclassAddr = body[2]
	flag = body[3]

	n := size - 4
	data = make([]byte, n)
	copy(data, body[4:4+n])

	chkIdx := 4 + n
	if body[chkIdx+1] != endByte {
		err = fmt.Errorf("thermalcam: missing END byte")
		return
	}
	expected := checksum(classAddr, subclassAddr, flag, data)
	if body[chkIdx] != expected {
		err = fmt.Errorf("thermalcam: checksum mismatch: got 0x%02X want 0x%02X", body[chkIdx], expected)
		return
	}
	return
}

// write sends a write command and checks the success response.
func (t *ThermalCam) write(classAddr, subclassAddr byte, data []byte) error {
	t.mu.Lock()
	defer t.mu.Unlock()

	if _, err := t.f.Write(buildPacket(classAddr, subclassAddr, flagWrite, data)); err != nil {
		return err
	}
	_, _, flag, resp, err := t.recv()
	if err != nil {
		return err
	}
	if flag != flagOK {
		return fmt.Errorf("thermalcam: write error flag 0x%02X", flag)
	}
	if len(resp) > 0 && resp[0] == 0x00 {
		return fmt.Errorf("thermalcam: command not recognised")
	}
	return nil
}

// read sends a read command and returns the DATA bytes from the response.
func (t *ThermalCam) read(classAddr, subclassAddr byte) ([]byte, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if _, err := t.f.Write(buildPacket(classAddr, subclassAddr, flagRead, []byte{0x00})); err != nil {
		return nil, err
	}
	_, _, flag, data, err := t.recv()
	if err != nil {
		return nil, err
	}
	if flag != flagOK {
		return nil, fmt.Errorf("thermalcam: read error flag 0x%02X", flag)
	}
	return data, nil
}

// --- Information query commands (class 0x74) ---

// Model returns the module model string.
func (t *ThermalCam) Model() (string, error) {
	data, err := t.read(0x74, 0x02)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// FPGAVersion returns the 3-byte FPGA program version [major, minor, patch].
func (t *ThermalCam) FPGAVersion() ([3]byte, error) {
	data, err := t.read(0x74, 0x03)
	if err != nil {
		return [3]byte{}, err
	}
	if len(data) < 3 {
		return [3]byte{}, fmt.Errorf("thermalcam: short FPGA version response")
	}
	return [3]byte{data[0], data[1], data[2]}, nil
}

// FPGACompileTime returns the FPGA compilation date as a BCD-encoded uint32 (e.g. 20140820).
func (t *ThermalCam) FPGACompileTime() (uint32, error) {
	data, err := t.read(0x74, 0x04)
	if err != nil {
		return 0, err
	}
	if len(data) < 4 {
		return 0, fmt.Errorf("thermalcam: short FPGA compile time response")
	}
	return uint32(data[0])<<24 | uint32(data[1])<<16 | uint32(data[2])<<8 | uint32(data[3]), nil
}

// SoftwareVersion returns the 3-byte software version [major, minor, patch].
func (t *ThermalCam) SoftwareVersion() ([3]byte, error) {
	data, err := t.read(0x74, 0x05)
	if err != nil {
		return [3]byte{}, err
	}
	if len(data) < 3 {
		return [3]byte{}, fmt.Errorf("thermalcam: short SW version response")
	}
	return [3]byte{data[0], data[1], data[2]}, nil
}

// SoftwareCompileTime returns the software compilation date as a uint32.
func (t *ThermalCam) SoftwareCompileTime() (uint32, error) {
	data, err := t.read(0x74, 0x06)
	if err != nil {
		return 0, err
	}
	if len(data) < 4 {
		return 0, fmt.Errorf("thermalcam: short SW compile time response")
	}
	return uint32(data[0])<<24 | uint32(data[1])<<16 | uint32(data[2])<<8 | uint32(data[3]), nil
}

// CalibrationVersionTime returns the camera process calibration date as a uint32.
func (t *ThermalCam) CalibrationVersionTime() (uint32, error) {
	data, err := t.read(0x74, 0x0B)
	if err != nil {
		return 0, err
	}
	if len(data) < 4 {
		return 0, fmt.Errorf("thermalcam: short calibration version response")
	}
	return uint32(data[0])<<24 | uint32(data[1])<<16 | uint32(data[2])<<8 | uint32(data[3]), nil
}

// ISPVersion returns the ISP parameter version number.
func (t *ThermalCam) ISPVersion() (uint32, error) {
	data, err := t.read(0x74, 0x0C)
	if err != nil {
		return 0, err
	}
	if len(data) < 4 {
		return 0, fmt.Errorf("thermalcam: short ISP version response")
	}
	return uint32(data[0])<<24 | uint32(data[1])<<16 | uint32(data[2])<<8 | uint32(data[3]), nil
}

// --- Initialization state (class 0x7C, subclass 0x14) ---

// Ready returns true when the module has finished initializing and is outputting video.
func (t *ThermalCam) Ready() (bool, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	// Init state uses flag=0x00 (write) even though it's a query; response class differs.
	if _, err := t.f.Write(buildPacket(0x7C, 0x14, flagWrite, []byte{0x00})); err != nil {
		return false, err
	}
	_, _, flag, data, err := t.recv()
	if err != nil {
		return false, err
	}
	if flag != flagOK {
		return false, fmt.Errorf("thermalcam: ready error flag 0x%02X", flag)
	}
	if len(data) == 0 {
		return false, fmt.Errorf("thermalcam: empty ready response")
	}
	return data[0] == 0x01, nil
}

// --- Settings commands (write-only) ---

// SaveSettings persists the current module settings to non-volatile storage.
func (t *ThermalCam) SaveSettings() error {
	return t.write(0x74, 0x10, []byte{0x00})
}

// FactoryReset restores all module settings to factory defaults.
func (t *ThermalCam) FactoryReset() error {
	return t.write(0x74, 0x0F, []byte{0x00})
}

// FFC triggers a manual flat-field (shutter) calibration.
func (t *ThermalCam) FFC() error {
	return t.write(0x7C, 0x02, []byte{0x00})
}

// BackgroundCorrection performs a manual background correction.
func (t *ThermalCam) BackgroundCorrection() error {
	return t.write(0x7C, 0x03, []byte{0x00})
}

// VignettingCorrection performs vignetting correction; aim the lens at a uniform surface first.
func (t *ThermalCam) VignettingCorrection() error {
	return t.write(0x7C, 0x0C, []byte{0x02})
}

// --- Automatic shutter (class 0x7C, subclass 0x04 / 0x05) ---

// SetShutterMode sets the automatic shutter control mode.
func (t *ThermalCam) SetShutterMode(m ShutterMode) error {
	return t.write(0x7C, 0x04, []byte{byte(m)})
}

// ShutterMode reads the current automatic shutter control mode.
func (t *ThermalCam) ShutterMode() (ShutterMode, error) {
	data, err := t.read(0x7C, 0x04)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty shutter mode response")
	}
	return ShutterMode(data[0]), nil
}

// SetShutterInterval sets the automatic shutter switching interval in minutes.
// Only effective when ShutterMode is ShutterTiming or ShutterFullAuto.
func (t *ThermalCam) SetShutterInterval(minutes uint16) error {
	return t.write(0x7C, 0x05, []byte{byte(minutes >> 8), byte(minutes)})
}

// ShutterInterval reads the current automatic shutter switching interval in minutes.
func (t *ThermalCam) ShutterInterval() (uint16, error) {
	data, err := t.read(0x7C, 0x05)
	if err != nil {
		return 0, err
	}
	if len(data) < 2 {
		return 0, fmt.Errorf("thermalcam: short shutter interval response")
	}
	return uint16(data[0])<<8 | uint16(data[1]), nil
}

// --- Image parameters (class 0x78) ---

// SetBrightness sets image brightness (0–100, default 50).
func (t *ThermalCam) SetBrightness(v uint8) error {
	return t.write(0x78, 0x02, []byte{v})
}

// Brightness reads the current image brightness (0–100).
func (t *ThermalCam) Brightness() (uint8, error) {
	data, err := t.read(0x78, 0x02)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty brightness response")
	}
	return data[0], nil
}

// SetContrast sets image contrast (0–100, default 50).
func (t *ThermalCam) SetContrast(v uint8) error {
	return t.write(0x78, 0x03, []byte{v})
}

// Contrast reads the current image contrast (0–100).
func (t *ThermalCam) Contrast() (uint8, error) {
	data, err := t.read(0x78, 0x03)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty contrast response")
	}
	return data[0], nil
}

// SetDetailEnhancement sets the digital detail enhancement level (0–100, default 50).
func (t *ThermalCam) SetDetailEnhancement(v uint8) error {
	return t.write(0x78, 0x10, []byte{v})
}

// DetailEnhancement reads the current detail enhancement level (0–100).
func (t *ThermalCam) DetailEnhancement() (uint8, error) {
	data, err := t.read(0x78, 0x10)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty detail enhancement response")
	}
	return data[0], nil
}

// SetStaticDenoising sets the static denoising level (0–100, default 50).
func (t *ThermalCam) SetStaticDenoising(v uint8) error {
	return t.write(0x78, 0x15, []byte{v})
}

// StaticDenoising reads the current static denoising level (0–100).
func (t *ThermalCam) StaticDenoising() (uint8, error) {
	data, err := t.read(0x78, 0x15)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty static denoising response")
	}
	return data[0], nil
}

// SetDynamicDenoising sets the dynamic denoising level (0–100, default 50).
func (t *ThermalCam) SetDynamicDenoising(v uint8) error {
	return t.write(0x78, 0x16, []byte{v})
}

// DynamicDenoising reads the current dynamic denoising level (0–100).
func (t *ThermalCam) DynamicDenoising() (uint8, error) {
	data, err := t.read(0x78, 0x16)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty dynamic denoising response")
	}
	return data[0], nil
}

// SetPalette sets the false-color palette (default PaletteWhiteHot).
func (t *ThermalCam) SetPalette(p Palette) error {
	return t.write(0x78, 0x20, []byte{byte(p)})
}

// GetPalette reads the currently active palette.
func (t *ThermalCam) GetPalette() (Palette, error) {
	data, err := t.read(0x78, 0x20)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty palette response")
	}
	return Palette(data[0]), nil
}

// SetMirroring sets the image mirroring mode (default MirrorNone).
func (t *ThermalCam) SetMirroring(m MirrorMode) error {
	return t.write(0x70, 0x11, []byte{byte(m)})
}

// Mirroring reads the current image mirroring mode.
func (t *ThermalCam) Mirroring() (MirrorMode, error) {
	data, err := t.read(0x70, 0x11)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, fmt.Errorf("thermalcam: empty mirroring response")
	}
	return MirrorMode(data[0]), nil
}

// --- Defective pixel correction (class 0x78, subclass 0x1A) ---

// SetCursorDisplay shows or hides the on-screen cursor used for defective pixel correction.
func (t *ThermalCam) SetCursorDisplay(on bool) error {
	var v byte
	if on {
		v = 0x0F
	}
	return t.write(0x78, 0x1A, []byte{v})
}

// MoveCursor moves the cursor one step in the given direction.
func (t *ThermalCam) MoveCursor(dir CursorDir) error {
	return t.write(0x78, 0x1A, []byte{byte(dir)})
}

// MoveCursorN moves the cursor n pixels (1–15) in the given direction.
func (t *ThermalCam) MoveCursorN(dir CursorDir, n uint8) error {
	if n == 0 || n > 15 {
		return fmt.Errorf("thermalcam: MoveCursorN n must be 1–15, got %d", n)
	}
	// Encode: upper nibble = direction offset (2..5 → 2,3,4,5), lower nibble = n.
	// Protocol encodes as 0x2N, 0x3N, 0x4N, 0x5N for up/down/left/right.
	var base byte
	switch dir {
	case CursorUp:
		base = 0x20
	case CursorDown:
		base = 0x30
	case CursorLeft:
		base = 0x40
	case CursorRight:
		base = 0x50
	default:
		return fmt.Errorf("thermalcam: MoveCursorN unsupported direction %d", dir)
	}
	return t.write(0x78, 0x1A, []byte{base | n})
}

// AddDefectivePixel marks the pixel at the current cursor position as defective.
func (t *ThermalCam) AddDefectivePixel() error {
	return t.write(0x78, 0x1A, []byte{0x0D})
}

// RemoveDefectivePixel removes the pixel at the current cursor position from the defective list.
func (t *ThermalCam) RemoveDefectivePixel() error {
	return t.write(0x78, 0x1A, []byte{0x0E})
}

// --- State snapshot ---

// ReadState polls until the camera is ready (up to timeout), then reads all
// queryable parameters and returns them as a State. Fields that fail are left
// at their zero value; any errors are accumulated and returned alongside the
// partial state.
func (t *ThermalCam) ReadState(timeout time.Duration) (*State, []error) {
	deadline := time.Now().Add(timeout)
	for {
		ready, err := t.Ready()
		if err != nil {
			if time.Now().After(deadline) {
				return nil, []error{fmt.Errorf("thermalcam: timed out waiting for ready: %w", err)}
			}
		} else if ready {
			break
		} else if time.Now().After(deadline) {
			return nil, []error{fmt.Errorf("thermalcam: timed out waiting for ready")}
		}
		time.Sleep(2 * time.Second)
	}

	s := &State{}
	var errs []error

	try := func(err error) {
		if err != nil {
			errs = append(errs, err)
		}
	}

	fmtVersion := func(v [3]byte, err error) string {
		if err != nil {
			return ""
		}
		return fmt.Sprintf("%d.%d.%d", v[0], v[1], v[2])
	}
	fmtDate := func(d uint32, err error) string {
		if err != nil {
			return ""
		}
		return fmt.Sprintf("%04d-%02d-%02d", d/10000, (d/100)%100, d%100)
	}

	var err error

	s.Model, err = t.Model()
	try(err)

	v3, err := t.FPGAVersion()
	s.FPGAVersion = fmtVersion(v3, err)
	try(err)

	u32, err := t.FPGACompileTime()
	s.FPGACompileTime = fmtDate(u32, err)
	try(err)

	v3, err = t.SoftwareVersion()
	s.SoftwareVersion = fmtVersion(v3, err)
	try(err)

	u32, err = t.SoftwareCompileTime()
	s.SoftwareCompileTime = fmtDate(u32, err)
	try(err)

	u32, err = t.CalibrationVersionTime()
	s.CalibrationDate = fmtDate(u32, err)
	try(err)

	s.ISPVersion, err = t.ISPVersion()
	try(err)

	sm, err := t.ShutterMode()
	s.ShutterMode = sm.String()
	try(err)

	s.ShutterIntervalMin, err = t.ShutterInterval()
	try(err)

	s.Brightness, err = t.Brightness()
	try(err)

	s.Contrast, err = t.Contrast()
	try(err)

	s.DetailEnhancement, err = t.DetailEnhancement()
	try(err)

	s.StaticDenoising, err = t.StaticDenoising()
	try(err)

	s.DynamicDenoising, err = t.DynamicDenoising()
	try(err)

	p, err := t.GetPalette()
	s.Palette = p.String()
	try(err)

	m, err := t.Mirroring()
	s.Mirroring = m.String()
	try(err)

	return s, errs
}
