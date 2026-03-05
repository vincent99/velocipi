package siyi

import (
	"encoding/binary"
	"fmt"
)

const (
	stx0 = 0x55
	stx1 = 0x66
	ctrl = 0x01 // no need-ack, no ack frame

	// ControlPort is the UDP port used for gimbal and AI tracker commands.
	ControlPort = 37260

	// DownloadPort is the HTTP port used for SD card file access.
	DownloadPort = 82

	// CMD IDs
	CmdHeartbeat        = 0x00
	CmdFirmwareVersion  = 0x01
	CmdHardwareID       = 0x02
	CmdAutoFocus        = 0x04
	CmdManualZoom       = 0x05
	CmdManualFocus      = 0x06
	CmdGimbalRotation   = 0x07
	CmdCenter           = 0x08
	CmdGimbalConfig     = 0x0A
	CmdFuncFeedback     = 0x0B
	CmdPhoto            = 0x0C
	CmdAcquireAttitude  = 0x0D
	CmdAbsoluteZoom     = 0x0F
	CmdSetImageType     = 0x11
	CmdExternalAttitude = 0x22
	CmdSetTime          = 0x30
	CmdPositionData     = 0x3E

	// Photo function codes (CmdPhoto data byte)
	PhotoTakePicture  = 0x00
	PhotoHDRToggle    = 0x01
	PhotoRecordToggle = 0x02
	PhotoModeLock     = 0x03
	PhotoModeFollow   = 0x04
	PhotoModeFPV      = 0x05
)

// buildPacket creates a framed Siyi SDK packet.
// Layout: STX(2) + CTRL(1) + DATA_LEN(2 LE) + SEQ(2 LE) + CMD_ID(1) + DATA(n) + CRC16(2 LE)
func buildPacket(seq uint16, cmdID byte, data []byte) []byte {
	dataLen := len(data)
	// Header bytes before CRC: stx0 stx1 ctrl lenLo lenHi seqLo seqHi cmdID data...
	hdr := make([]byte, 0, 8+dataLen+2)
	hdr = append(hdr, stx0, stx1, ctrl)
	hdr = append(hdr, byte(dataLen), byte(dataLen>>8))
	hdr = append(hdr, byte(seq), byte(seq>>8))
	hdr = append(hdr, cmdID)
	hdr = append(hdr, data...)

	crc := crc16(hdr)
	hdr = append(hdr, byte(crc), byte(crc>>8))
	return hdr
}

// parsePacket validates and parses a received Siyi packet.
// Returns cmdID and payload data, or an error if malformed.
func parsePacket(pkt []byte) (cmdID byte, data []byte, err error) {
	if len(pkt) < 10 {
		return 0, nil, fmt.Errorf("siyi: packet too short (%d bytes)", len(pkt))
	}
	if pkt[0] != stx0 || pkt[1] != stx1 {
		return 0, nil, fmt.Errorf("siyi: bad STX %02x %02x", pkt[0], pkt[1])
	}
	dataLen := int(binary.LittleEndian.Uint16(pkt[3:5]))
	expected := 8 + dataLen + 2
	if len(pkt) < expected {
		return 0, nil, fmt.Errorf("siyi: packet too short for declared len %d", dataLen)
	}
	body := pkt[:8+dataLen]
	crcGot := binary.LittleEndian.Uint16(pkt[8+dataLen : 8+dataLen+2])
	crcWant := crc16(body)
	if crcGot != crcWant {
		return 0, nil, fmt.Errorf("siyi: CRC mismatch got %04x want %04x", crcGot, crcWant)
	}
	cmdID = pkt[7]
	data = pkt[8 : 8+dataLen]
	return cmdID, data, nil
}

// GimbalAttitude holds the parsed gimbal attitude from CmdAcquireAttitude response.
type GimbalAttitude struct {
	Yaw, Pitch, Roll             float32
	YawRate, PitchRate, RollRate float32
}

// parseAttitude decodes a 12-byte CmdAcquireAttitude response payload.
// 6 × int16 LE × 0.1 °: [yaw, pitch, roll, yawRate, pitchRate, rollRate]
// Note: yaw and yawRate are negated in the protocol.
func parseAttitude(data []byte) (GimbalAttitude, error) {
	if len(data) < 12 {
		return GimbalAttitude{}, fmt.Errorf("siyi: attitude payload too short (%d)", len(data))
	}
	vals := make([]float32, 6)
	for i := range vals {
		raw := int16(binary.LittleEndian.Uint16(data[i*2 : i*2+2]))
		vals[i] = float32(raw) * 0.1
	}
	return GimbalAttitude{
		Yaw:       -vals[0],
		Pitch:     vals[1],
		Roll:      vals[2],
		YawRate:   -vals[3],
		PitchRate: vals[4],
		RollRate:  vals[5],
	}, nil
}
