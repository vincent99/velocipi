//go:build linux

// Package serial opens UART serial ports with termios configuration.
package serial

import (
	"fmt"
	"os"
	"syscall"

	"golang.org/x/sys/unix"
)

// Open opens a serial device at the given baud rate with 8N1 framing and no
// flow control. Reads time out after 2 seconds at the hardware level.
func Open(device string, baud int) (*os.File, error) {
	b, err := baudConst(baud)
	if err != nil {
		return nil, err
	}
	f, err := os.OpenFile(device, os.O_RDWR|syscall.O_NOCTTY, 0600)
	if err != nil {
		return nil, fmt.Errorf("serial: open %s: %w", device, err)
	}
	fd := int(f.Fd())
	term := unix.Termios{
		Iflag:  0,
		Oflag:  0,
		Cflag:  b | unix.CS8 | unix.CREAD | unix.CLOCAL,
		Lflag:  0,
		Ispeed: b,
		Ospeed: b,
	}
	term.Cc[unix.VMIN] = 0
	term.Cc[unix.VTIME] = 20 // 2-second timeout (units of 0.1 s)
	if err := unix.IoctlSetTermios(fd, unix.TCSETSF, &term); err != nil {
		f.Close()
		return nil, fmt.Errorf("serial: set termios: %w", err)
	}
	return f, nil
}

func baudConst(baud int) (uint32, error) {
	switch baud {
	case 4800:
		return unix.B4800, nil
	case 9600:
		return unix.B9600, nil
	case 19200:
		return unix.B19200, nil
	case 38400:
		return unix.B38400, nil
	case 57600:
		return unix.B57600, nil
	case 115200:
		return unix.B115200, nil
	default:
		return 0, fmt.Errorf("serial: unsupported baud rate %d", baud)
	}
}
