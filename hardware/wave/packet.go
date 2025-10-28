package wave

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"fmt"

	"github.com/sigurn/crc16"
)

const (
	FRAME_TYPE_COMMAND = 0x00
	FRAME_TYPE_PROTOCOL = 0x01
	FRAME_TYPE_PROTOCOL_INT = 0x10

	PAYLOAD_TYPE_VX_PROTOCOL = 0x00
	PAYYLOAD_TYPE_ODM_PROTOCOL = 0x04
)

type Packet struct {
	frameType byte
	payloadType byte
	payload []byte
	cmdId byte
	version byte
	key []byte
	iv []byte
}

func NewPacket(frameType byte, payloadType byte, payload []byte) (*Packet) {
	ep := &Packet{
		frameType: frameType,
		payloadType: payloadType,
		payload: payload,
	}

	return ep
}
func NewPacketFull(frameType byte, payloadType byte, payload []byte, cmdId byte, version byte, key []byte, iv []byte) (*Packet) {
	ep := &Packet{
		frameType: frameType,
		payloadType: payloadType,
		payload: payload,
		cmdId: cmdId,
		version: version,
		key: key,
		iv: iv,
	}

	return ep
}

func (ep *Packet) encryptedPayload() ([]byte) {
	if ep.key == nil || ep.iv == nil {
		return ep.payload
	}

	plaintext := PKCS7Padding(ep.payload)
	block, err := aes.NewCipher(ep.key)
	if err != nil {
		panic(err)
	}

	ciphertext := make([]byte, len(plaintext))
	mode := cipher.NewCBCEncrypter(block, ep.iv)
	mode.CryptBlocks(ciphertext, plaintext)

	return ciphertext
}

func (ep *Packet) ToBytes() ([]byte) {
	payload := ep.encryptedPayload()
	size := len(payload) + 2 // for the crc

	if size > 0xffff {
		panic("Payload too large")
	}

	prefix := []byte{0x5a, 0x5a, ep.frameType << 4, 0x01, byte(size & 0xff), byte(size >> 8)}
	data := append(prefix, payload...)
	checksum := crc16.Checksum((data), crc16.MakeTable(crc16.CRC16_ARC))

	return append(data, byte(checksum & 0xff), byte(checksum>>8))
}

func PKCS7Padding(ciphertext []byte) []byte {
    padding := aes.BlockSize - len(ciphertext) % aes.BlockSize
    padtext := bytes.Repeat([]byte{byte(padding)}, padding)
    return append(ciphertext, padtext...)
}

func PKCS7UnPadding(plantText []byte) []byte {
    length   := len(plantText)
    unpadding := int(plantText[length-1])
    return plantText[:(length - unpadding)]
}

func ParseSimple(data []byte) ([]byte, error) {
	header := data[0:6]
	len := int(uint16(header[4]) | uint16(header[5])<<8)
	end := 6 + len
	checksum := data[end-2:end]
	payload := data[6:end-2]

	// Check the payload CRC16
	if crc16.Checksum(data[0:end-2], crc16.MakeTable(crc16.CRC16_ARC)) != uint16(checksum[0]) + uint16(checksum[1])<<8 {
		return nil, fmt.Errorf("ParseSimple: ERROR: Unable to parse simple packet - incorrect CRC16: %s", hex.EncodeToString(data[0:end]))
	}

	return payload, nil
}
