package siyi

// crc16 computes a CRC-16/CCITT-FALSE (XModem variant) checksum:
// poly 0x1021, init 0x0000, no input/output reflection.
//
// Verification: packet bytes 55 66 01 01 00 00 00 00 00 → CRC 0x8B59.
func crc16(data []byte) uint16 {
	var crc uint16
	for _, b := range data {
		crc ^= uint16(b) << 8
		for i := 0; i < 8; i++ {
			if crc&0x8000 != 0 {
				crc = (crc << 1) ^ 0x1021
			} else {
				crc <<= 1
			}
		}
	}
	return crc
}
