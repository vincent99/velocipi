package i2c

// Copyright (c) 2025 Vincent Fiduccia
// Copyright (c) 2023 https://github.com/swdee
// Copyright (c) 2016 Denis Dyakov
// Copyright (c) 2013 Dave Cheney

// Package i2c provides low level control over the Linux i2c bus.
//
// Before usage you should load the i2c-dev kernel module
//
//	sudo modprobe i2c-dev
//
// Each i2c bus can address 127 independent i2c devices, and most
// Linux systems contain several buses.

import (
	"os"
	"syscall"
	"unsafe"
)

const (
	DEFAULT_DEVICE = "/dev/i2c-1"

	// constants from C files linux/i2c-dev.h and linux/i2c.h
	I2C_SLAVE = 0x0703
	I2C_M_RD  = 0x0001
	I2C_RDWR  = 0x0707
)

// I2C represents a connection to I2C-device.
type I2C struct {
	addr uint8
	dev  string
	rc   *os.File
}

// i2c_msg struct represents an I2C message
type i2c_msg struct {
	addr  uint16
	flags uint16
	len   uint16
	buf   uintptr
}

// i2c_rdwr_ioctl_data struct for I2C_RDWR ioctl operation
type i2c_rdwr_ioctl_data struct {
	msgs  uintptr
	nmsgs uint32
}

// New opens a connection for I2C-device.
// SMBus (System Management Bus) protocol over I2C
// supported as well: you should preliminary specify
// register address to read from, either write register
// together with the data in case of write operations.
func New(dev string, addr uint8) (*I2C, error) {
	if dev == "" {
		dev = DEFAULT_DEVICE
	}

	i2c := &I2C{
		addr: addr,
		dev:  dev,
	}

	f, err := os.OpenFile(dev, os.O_RDWR, 0600)

	if err != nil {
		return i2c, err
	}

	if err := ioctl(f.Fd(), I2C_SLAVE, uintptr(addr)); err != nil {
		return i2c, err
	}

	i2c.rc = f
	return i2c, nil
}

// GetAddr return device occupied address in the bus.
func (o *I2C) GetAddr() uint8 {
	return o.addr
}

// GetDev return full device name.
func (o *I2C) GetDev() string {
	return o.dev
}

// Low Level

func (o *I2C) ReadBytes(buf []byte) (int, error) {

	n, err := o.rc.Read(buf)

	if err != nil {
		return n, err
	}

	return n, nil
}

func (o *I2C) WriteBytes(buf []byte) (int, error) {
	return o.rc.Write(buf)
}

func (o *I2C) Batch(msgs []i2c_msg) error {
	data := i2c_rdwr_ioctl_data{
		msgs:  uintptr(unsafe.Pointer(&msgs[0])),
		nmsgs: uint32(len(msgs)),
	}

	err := ioctl(o.rc.Fd(), I2C_RDWR, uintptr(unsafe.Pointer(&data)))
	return err
}

// WriteThenReadBytes sends two I2C messages, the first to write some bytes then
// the second to read them.  This function allows us to perform a Write then Read
// without a I2C Stop condition occurring between the two messages which
// happens if WriteBytes() then ReadBytes() functions were called individually.
func (o *I2C) WriteThenReadBytes(writeBuf, readBuf []byte) error {
	msgs := []i2c_msg{
		{
			addr:  uint16(o.addr),
			flags: 0,
			len:   uint16(len(writeBuf)),
			buf:   uintptr(unsafe.Pointer(&writeBuf[0])),
		},
		{
			addr:  uint16(o.addr),
			flags: I2C_M_RD,
			len:   uint16(len(readBuf)),
			buf:   uintptr(unsafe.Pointer(&readBuf[0])),
		},
	}

	return o.Batch(msgs)
}

// Read Registers

func (o *I2C) ReadRegister(reg byte, n int) ([]byte, error) {

	buf := make([]byte, n)
	err := o.WriteThenReadBytes([]byte{reg}, buf)

	if err != nil {
		return nil, err
	}

	return buf, nil
}

func (o *I2C) ReadRegisterU8(reg byte) (byte, error) {
	buf, err := o.ReadRegister(reg, 1)
	if err != nil {
		return 0, err
	}

	return buf[0], nil
}

// ---------

func (o *I2C) ReadRegisterU16BE(reg byte) (uint16, error) {
	buf, err := o.ReadRegister(reg, 2)
	if err != nil {
		return 0, err
	}

	w := uint16(buf[0])<<8 | uint16(buf[1])

	return w, nil
}

func (o *I2C) ReadRegisterU16LE(reg byte) (uint16, error) {
	buf, err := o.ReadRegister(reg, 2)
	if err != nil {
		return 0, err
	}

	w := uint16(buf[1])<<8 | uint16(buf[0])

	return w, nil
}

func (o *I2C) ReadRegisterS16BE(reg byte) (int16, error) {
	buf, err := o.ReadRegister(reg, 2)
	if err != nil {
		return 0, err
	}

	w := int16(buf[0])<<8 | int16(buf[1])

	return w, nil
}

func (o *I2C) ReadRegisterS16LE(reg byte) (int16, error) {
	buf, err := o.ReadRegister(reg, 2)
	if err != nil {
		return 0, err
	}

	w := int16(buf[1])<<8 | int16(buf[0])

	return w, nil
}

// ---------

func (o *I2C) ReadRegisterU24BE(reg byte) (uint32, error) {
	buf, err := o.ReadRegister(reg, 3)
	if err != nil {
		return 0, err
	}

	w := uint32(buf[0])<<16 | uint32(buf[1])<<8 | uint32(buf[2])

	return w, nil
}

func (o *I2C) ReadRegisterU24LE(reg byte) (uint32, error) {
	buf, err := o.ReadRegister(reg, 3)
	if err != nil {
		return 0, err
	}

	w := uint32(buf[2])<<16 | uint32(buf[1])<<8 | uint32(buf[0])

	return w, nil
}

// ---------

func (o *I2C) ReadRegisterU32BE(reg byte) (uint32, error) {
	buf, err := o.ReadRegister(reg, 4)
	if err != nil {
		return 0, err
	}

	w := uint32(buf[0])<<24 | uint32(buf[1])<<16 | uint32(buf[2])<<8 | uint32(buf[3])

	return w, nil
}

func (o *I2C) ReadRegisterU32LE(reg byte) (uint32, error) {
	buf, err := o.ReadRegister(reg, 4)
	if err != nil {
		return 0, err
	}

	w := uint32(buf[3])<<24 | uint32(buf[2])<<16 | uint32(buf[1])<<8 | uint32(buf[0])

	return w, nil
}

func (o *I2C) ReadRegisterS32BE(reg byte) (int32, error) {
	buf, err := o.ReadRegister(reg, 4)
	if err != nil {
		return 0, err
	}

	w := int32(buf[0])<<24 | int32(buf[1])<<16 | int32(buf[2])<<8 | int32(buf[3])

	return w, nil
}

func (o *I2C) ReadRegisterS32LE(reg byte) (int32, error) {
	buf, err := o.ReadRegister(reg, 4)
	if err != nil {
		return 0, err
	}

	w := int32(buf[3])<<24 | int32(buf[2])<<16 | int32(buf[1])<<8 | int32(buf[0])

	return w, nil
}

// ---------

// WRITE SECTION

func (o *I2C) WriteRegisterBytes(reg byte, buf []byte) (int, error) {
	b := append([]byte{reg}, buf...)
	return o.WriteBytes(b)
}

// ---------

func (o *I2C) WriteRegisterU8(reg byte, value byte) error {
	_, err := o.WriteRegisterBytes(reg, []byte{value})
	return err
}

// ---------

func (o *I2C) WriteRegisterU16BE(reg byte, value uint16) error {
	buf := []byte{byte((value & 0xFF00) >> 8), byte(value & 0xFF)}

	_, err := o.WriteRegisterBytes(reg, buf)

	return err
}

func (o *I2C) WriteRegisterU16LE(reg byte, value uint16) error {
	buf := []byte{byte(value & 0xFF), byte((value & 0xFF00) >> 8)}

	_, err := o.WriteRegisterBytes(reg, buf)

	return err
}

func (o *I2C) WriteRegisterS16BE(reg byte, value int16) error {
	buf := []byte{byte((uint16(value) & 0xFF00) >> 8), byte(value & 0xFF)}

	_, err := o.WriteRegisterBytes(reg, buf)

	return err
}

func (o *I2C) WriteRegisterS16LE(reg byte, value int16) error {
	buf := []byte{byte(value & 0xFF), byte((uint16(value) & 0xFF00) >> 8)}
	_, err := o.WriteRegisterBytes(reg, buf)
	return err
}

// ---------

func (o *I2C) WriteRegisterU24BE(reg byte, value uint32) error {
	buf := []byte{byte(value >> 16 & 0xFF), byte(value >> 8 & 0xFF), byte(value & 0xFF)}
	_, err := o.WriteRegisterBytes(reg, buf)
	return err
}

func (o *I2C) WriteRegisterU24LE(reg byte, value uint32) error {
	buf := []byte{byte(value & 0xFF), byte(value >> 8 & 0xFF), byte(value >> 16 & 0xFF)}
	_, err := o.WriteRegisterBytes(reg, buf)
	return err
}

// ---------

func (o *I2C) WriteRegisterU32BE(reg byte, value uint32) error {
	buf := []byte{byte(value >> 24 & 0xFF), byte(value >> 16 & 0xFF), byte(value >> 8 & 0xFF), byte(value & 0xFF)}
	_, err := o.WriteRegisterBytes(reg, buf)
	return err
}

func (o *I2C) WriteRegisterU32LE(reg byte, value uint32) error {
	buf := []byte{byte(value & 0xFF), byte(value >> 8 & 0xFF), byte(value >> 16 & 0xFF), byte(value >> 24 & 0xFF)}
	_, err := o.WriteRegisterBytes(reg, buf)
	return err
}

func (o *I2C) WriteRegisterS32BE(reg byte, value int32) error {
	buf := []byte{byte((uint32(value) & 0xFF000000) >> 24), byte(value >> 16 & 0xFF), byte(value >> 8 & 0xFF), byte(value & 0xFF)}

	_, err := o.WriteRegisterBytes(reg, buf)

	return err
}

func (o *I2C) WriteRegisterS32LE(reg byte, value int32) error {
	buf := []byte{byte(value & 0xFF), byte(value >> 8 & 0xFF), byte(value >> 16 & 0xFF), byte((uint32(value) & 0xFF000000) >> 24)}
	_, err := o.WriteRegisterBytes(reg, buf)
	return err
}

// Close I2C-connection.
func (o *I2C) Close() error {
	return o.rc.Close()
}

func ioctl(fd, cmd, arg uintptr) error {

	if _, _, err := syscall.Syscall(syscall.SYS_IOCTL, fd, cmd, arg); err != 0 {

		return err
	}

	return nil
}
