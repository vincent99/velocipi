import config from '../config'
import {openPromisified, type PromisifiedBus} from 'i2c-bus'
import { logger } from '../logger';

type MaybeNumber = number|undefined

interface ReadResult {
	bytesRead: number
	buffer: Buffer
}

interface WriteResult {
	bytesWritten: number
	buffer: Buffer
}

export default class i2c {
  ready: boolean
  device: number;
  bus: PromisifiedBus;

  constructor() {
    this.ready = false
    this.device = config.get('i2c.device')
    openPromisified(this.device).then((bus) => {
      this.ready = true
      this.bus = bus
    }).catch((err) => {
      logger.error(err)
    })
	}

	async waitReady(timeout=1000): Promise<boolean> {
		return new Promise((resolve, reject) => {
			const loop = setInterval(() => {
				if ( this.ready ) {
					resolve(true)
					clearTimeout(loop)
					clearTimeout(to)
				}
			}, 10)

			const to = setTimeout(() => {
				reject()
				clearTimeout(loop)
			}, timeout)

		})
	}

	scan(start: MaybeNumber, end: MaybeNumber): Promise<number[]> {
		return this.bus.scan(start as number, end as number)
	}

	wrap(address: number): Peripheral {
		return new Peripheral(this, address)
	}

	private bufferize(data: Buffer|Uint8Array): Buffer {
		if ( Array.isArray(data) ) {
			return Buffer.from(data)
		} else {
		 return data as Buffer
		}
	}

	writeBytes(addr: number, data: Buffer|Uint8Array): Promise<WriteResult> {
		const buf = this.bufferize(data)
		return this.bus.i2cWrite(addr, buf.length, buf) as Promise<WriteResult>
	}
  
	readBytesIntoBuffer(addr: number, len: number, buf: Buffer): Promise<ReadResult> {
		return this.bus.i2cRead(addr, len, buf) as Promise<ReadResult>
	}

	async readBytes(addr: number, len: number): Promise<Uint8Array> {
		const buf = Buffer.alloc(len)
		await this.readBytesIntoBuffer(addr, len, buf)
		return buf
	}

	// Register Read

	async readRegister(addr: number, reg: number, len: number): Promise<Uint8Array> {
		const buf = Buffer.alloc(len)
		await this.bus.readI2cBlock(addr, reg, len, buf)
		return buf
	}

	async readRegisterU8(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(1)
		await this.bus.readI2cBlock(addr, reg, 1, buf)
		return buf.at(0) as number
	}

	async readRegisterU16BE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(2)
		await this.bus.readI2cBlock(addr, reg, 2, buf)
		const out = buf[0]<<8 | buf[1]
		return out
	}

	async readRegisterU16LE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(2)
		await this.bus.readI2cBlock(addr, reg, 2, buf)
		const out = buf[1]<<8 | buf[0]
		return out
	}
	
	async readRegisterU24BE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(3)
		await this.bus.readI2cBlock(addr, reg, 3, buf)
		const out = buf[0] << 16 | buf[1] << 8 | buf[2]
		return out
	}

	async readRegisterU24LE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(3)
		await this.bus.readI2cBlock(addr, reg, 3, buf)
		const out = buf[2] << 16 | buf[1] << 8 | buf[0]
		return out
	}

	async readRegisterU32BE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(4)
		await this.bus.readI2cBlock(addr, reg, 4, buf)
		const out = buf[0] << 24 | buf[1] << 16 | buf[2] << 8 | buf[3]
		return out
	}

	async readRegisterU32LE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(4)
		await this.bus.readI2cBlock(addr, reg, 4, buf)
		const out = buf[3] << 24 | buf[2] << 16 | buf[1] << 8 | buf[0]
		return out
	}

	private signedToBits(num: number, bits=8): number {
		const bitMask = Math.pow(2,bits)-1
		num = num & bitMask

		const mid = Math.pow(2, bits - 1)
		const max = Math.pow(2, bits)

		if ( num >= mid ) {
			return num - max
		}
		return num
	}

/*
	private bitsToSigned(raw: number, bits=8): number {
		const bitMask = Math.pow(2,bits)-1
		const msbMask = 1 << (bits-1)
		if ( (raw & msbMask) === msbMask ) {
			return (~raw + 1) & bitMask
		} else {
			return raw & bitMask
		}
	}
	*/

	async readRegisterS16BE(addr: number, reg: number): Promise<number> {
		return this.signedToBits(await this.readRegisterU16BE(addr, reg), 16)
	}

	async readRegisterS16LE(addr: number, reg: number): Promise<number> {
		return this.signedToBits(await this.readRegisterU16LE(addr, reg), 16)
	}

	async readRegisterS24BE(addr: number, reg: number): Promise<number> {
		return this.signedToBits(await this.readRegisterU24BE(addr, reg), 24)
	}

	async readRegisterS24LE(addr: number, reg: number): Promise<number> {
		return this.signedToBits(await this.readRegisterU24LE(addr, reg), 24)
	}

	async readRegisterS32BE(addr: number, reg: number): Promise<number> {
		return this.signedToBits(await this.readRegisterU32BE(addr, reg), 32)
	}

	async readRegisterS32LE(addr: number, reg: number): Promise<number> {
		return this.signedToBits(await this.readRegisterU32LE(addr, reg), 32)
	}

	// Register Write
	async writeRegister(addr: number, reg: number, data: Buffer): Promise<WriteResult> {
		return this.bus.writeI2cBlock(addr, reg, data.length, data)
	}

	async writeRegisterU8(addr: number, reg: number, data: number): Promise<WriteResult> {
		return this.writeRegister(addr, reg, Buffer.from([data]))
	}

	async writeRegisterU16BE(addr: number, reg: number, data: number): Promise<WriteResult> {
		const bytes = [ data & 0xFF, (data >> 8) & 0xFF ]
		return this.writeRegister(addr, reg, Buffer.from(bytes))
	}

	async writeRegisterU16LE(addr: number, reg: number, data: number): Promise<WriteResult> {
		const bytes = [ (data >> 8) & 0xFF, data & 0xFF ]
		return this.writeRegister(addr, reg, Buffer.from(bytes))
	}

	async writeRegisterU24BE(addr: number, reg: number, data: number): Promise<WriteResult> {
		const bytes = [ data & 0xFF, (data >> 8) & 0xFF, (data >> 16) & 0xFF ]
		return this.writeRegister(addr, reg, Buffer.from(bytes))
	}

	async writeRegisterU24LE(addr: number, reg: number, data: number): Promise<WriteResult> {
		const bytes = [ (data >> 16) & 0xFF, (data >> 8) & 0xFF, data & 0xFF ]
		return this.writeRegister(addr, reg, Buffer.from(bytes))
	}

	async writeRegisterU32BE(addr: number, reg: number, data: number): Promise<WriteResult> {
		const bytes = [ data & 0xFF, (data >> 8) & 0xFF, (data >> 16) & 0xFF, (data >> 24) & 0xFF ]
		return this.writeRegister(addr, reg, Buffer.from(bytes))
	}

	async writeRegisterU32LE(addr: number, reg: number, data: number): Promise<WriteResult> {
		const bytes = [ (data >> 24) & 0xFF, (data >> 16) & 0xFF, (data >> 8) & 0xFF, data & 0xFF ]
		return this.writeRegister(addr, reg, Buffer.from(bytes))
	}
}


/*

	async writeRegisterS16BE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU16BE(addr, reg), 16)
	}

	async writeRegisterS16LE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU16LE(addr, reg), 16)
	}

	async writeRegisterS24BE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU24BE(addr, reg), 24)
	}

	async writeRegisterS24LE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU24LE(addr, reg), 24)
	}

	async writeRegisterS32BE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU32BE(addr, reg), 32)
	}

	async writeRegisterS32LE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU32LE(addr, reg), 32)
	}
}

/*

// WRITE SECTION


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

*/

export class Peripheral {
	i: i2c
	address: number

  constructor(bus: i2c, address: number) {
		this.i = bus
		this.address = address
	}

	async isConnected(): Promise<boolean> {
		try {
			await this.writeBytes(Buffer.from([]))
			return true
		} catch (e) {
			return false
		}
	}

	writeBytes(data: Buffer|Uint8Array): Promise<WriteResult> {
		return this.i.writeBytes(this.address, data)
	}
  
	readBytesIntoBuffer(len: number, buf: Buffer): Promise<ReadResult> {
		return this.i.readBytesIntoBuffer(this.address, len, buf)
	}

	async readBytes(len: number): Promise<Uint8Array> {
		return this.i.readBytes(this.address, len)
	}

	// Register Read
	async readRegister(reg: number, len: number): Promise<Uint8Array> {
		return this.i.readRegister(this.address, reg, len)
	}

	async readRegisterU8(reg: number): Promise<number> {
		return this.i.readRegisterU8(this.address, reg)
	}

	async readRegisterU16BE(reg: number): Promise<number> {
		return this.i.readRegisterU16BE(this.address, reg)
	}

	async readRegisterU16LE(reg: number): Promise<number> {
		return this.i.readRegisterU16LE(this.address, reg)
	}
	
	async readRegisterU24BE(reg: number): Promise<number> {
		return this.i.readRegisterU24BE(this.address, reg)
	}

	async readRegisterU24LE(reg: number): Promise<number> {
		return this.i.readRegisterU24LE(this.address, reg)
	}

	async readRegisterU32BE(reg: number): Promise<number> {
		return this.i.readRegisterU32BE(this.address, reg)
	}

	async readRegisterU32LE(reg: number): Promise<number> {
		return this.i.readRegisterU32LE(this.address, reg)
	}

	async readRegisterS16BE(reg: number): Promise<number> {
		return this.i.readRegisterS16BE(this.address, reg)
	}

	async readRegisterS16LE(reg: number): Promise<number> {
		return this.i.readRegisterS16LE(this.address, reg)
	}

	async readRegisterS24BE(reg: number): Promise<number> {
		return this.i.readRegisterS24BE(this.address, reg)
	}

	async readRegisterS24LE(reg: number): Promise<number> {
		return this.i.readRegisterS24LE(this.address, reg)
	}

	async readRegisterS32BE(reg: number): Promise<number> {
		return this.i.readRegisterS32BE(this.address, reg)
	}

	async readRegisterS32LE(reg: number): Promise<number> {
		return this.i.readRegisterS32LE(this.address, reg)
	}

	// Register Write
	async writeRegister(reg: number, data: Buffer): Promise<WriteResult> {
		return this.i.writeRegister(this.address, reg, data)
	}

	async writeRegisterU8(reg: number, data: number): Promise<WriteResult> {
		return this.i.writeRegisterU8(this.address, reg, data)
	}

	async writeRegisterU16BE(reg: number, data: number): Promise<WriteResult> {
		return this.i.writeRegisterU16BE(this.address, reg, data)
	}

	async writeRegisterU16LE(reg: number, data: number): Promise<WriteResult> {
		return this.i.writeRegisterU16LE(this.address, reg, data)
	}
}

/*
	async writeRegisterU16LE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(2)
		await this.bus.writeI2cBlock(addr, reg, 2, buf)
		const out = buf[1]<<8 | buf[0]
		return out
	}
	
	async writeRegisterU24BE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(3)
		await this.bus.writeI2cBlock(addr, reg, 3, buf)
		const out = buf[0] << 16 | buf[1] << 8 | buf[2]
		return out
	}

	async writeRegisterU24LE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(3)
		await this.bus.writeI2cBlock(addr, reg, 3, buf)
		const out = buf[2] << 16 | buf[1] << 8 | buf[0]
		return out
	}

	async writeRegisterU32BE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(4)
		await this.bus.writeI2cBlock(addr, reg, 4, buf)
		const out = buf[0] << 24 | buf[1] << 16 | buf[2] << 8 | buf[3]
		return out
	}

	async writeRegisterU32LE(addr: number, reg: number): Promise<number> {
		const buf = Buffer.alloc(4)
		await this.bus.writeI2cBlock(addr, reg, 4, buf)
		const out = buf[3] << 24 | buf[2] << 16 | buf[1] << 8 | buf[0]
		return out
	}

	private twosComplement(num: number, bits=8): number {
		const mid = Math.pow(2, bits - 1)
		const max = Math.pow(2, bits)

		if ( num >= mid ) {
			return num - max
		}
		return num
	}

	async writeRegisterS16BE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU16BE(addr, reg), 16)
	}

	async writeRegisterS16LE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU16LE(addr, reg), 16)
	}

	async writeRegisterS24BE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU24BE(addr, reg), 24)
	}

	async writeRegisterS24LE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU24LE(addr, reg), 24)
	}

	async writeRegisterS32BE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU32BE(addr, reg), 32)
	}

	async writeRegisterS32LE(addr: number, reg: number): Promise<number> {
		return this.twosComplement(await this.writeRegisterU32LE(addr, reg), 32)
	}
}
*/
