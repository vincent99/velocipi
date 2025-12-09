import {Canvas} from 'skia-canvas'
import {RIO} from 'rpi-io'
import SPI, { SpiDevice} from 'spi-device'
import { logger } from '../logger'

export default class OLED {
  private static readonly PIN_DC = 5
  private static readonly PIN_RESET = 6

  // Command constants from display datasheet
  // private static readonly ENABLE_GRAY_SCALE_TABLE = 0x00
  private static readonly SET_COLUMN_ADDRESS = 0x15
  private static readonly WRITE_RAM = 0x5C
  // private static readonly READ_RAM = 0x5D
  private static readonly SET_ROW_ADDRESS = 0x75
  private static readonly SET_REMAP_DUAL_COM_LINE_MODE = 0xA0  // Re-map & Dual COM Line Mode
  private static readonly SET_DISPLAY_START_LINE = 0xA1
  private static readonly SET_DISPLAY_OFFSET = 0xA2
  // private static readonly SET_DISPLAY_MODE_ALL_OFF = 0xA4
  // private static readonly SET_DISPLAY_MODE_ALL_ON = 0xA5
  private static readonly SET_DISPLAY_MODE_NORMAL = 0xA6
  // private static readonly SET_DISPLAY_MODE_INVERSE = 0xA7
  // private static readonly PARTIAL_DISPLAY_ENABLE = 0xA8
  private static readonly PARTIAL_DISPLAY_DISABLE = 0xA9
  private static readonly SET_FUNCTION_SELECTION = 0xAB
  private static readonly DISPLAY_SLEEP_ON = 0xAE
  private static readonly DISPLAY_SLEEP_OFF = 0xAF
  private static readonly SET_PHASE_LENGTH = 0xB1
  private static readonly SET_FRONT_CLOCK_DIVIDER = 0xB3
  private static readonly DISPLAY_ENHANCEMENT_A = 0xB4
  private static readonly SET_GPIO = 0xB5
  private static readonly SET_SECOND_PRECHARGE_PERIOD = 0xB6
  // private static readonly SET_GRAY_SCALE_TABLE = 0xB8
  private static readonly SELECT_DEFAULT_LINEAR_GRAY_SCALE_TABLE = 0xB9
  private static readonly SET_PRECHARGE_VOLTAGE = 0xBB
  private static readonly SET_VCOMH_VOLTAGE = 0xBE
  private static readonly SET_CONTRAST_CURRENT = 0xC1
  private static readonly MASTER_CURRENT_CONTROL = 0xC7
  private static readonly SET_MULTIPLEX_RATIO = 0xCA
  private static readonly DISPLAY_ENHANCEMENT_B = 0xD1
  private static readonly SET_COMMAND_LOCK = 0xFD

  // Options for controlling VSL selection
  private static readonly ENABLE_EXTERNAL_VSL = 0x00
  // private static readonly ENABLE_INTERNAL_VSL = 0x02

  // Options for grayscale quality
  // private static readonly NORMAL_GRAYSCALE_QUALITY = 0xB0
  private static readonly ENHANCED_LOW_GRAY_SCALE_QUALITY = 0XF8

  // Options for display enhancement b
  private static readonly RESERVED_ENHANCEMENT = 0x00
  // private static readonly NORMAL_ENHANCEMENT = 0x02

  // Options for command lock
  // private static readonly COMMANDS_LOCK = 0x16
  private static readonly COMMANDS_UNLOCK = 0x12

  // Column and row maximums
  // private static readonly COLUMN_ADDRESS = 0x77
  // private static readonly ROW_ADDRESS = 0x7F

  private spi: SpiDevice;
  private dcPin: RIO;
  private resetPin: RIO;
  private width: number;
  private height: number;
  private flip: boolean
  private mainCanvas: Canvas;
  private overlayCanvas: Canvas;
  private framebuf: Buffer;
  private oddFrame: boolean;
  private profile: boolean;

  constructor(width=256, height=64, flip=false) {
    this.width = width
    this.height = height
    this.flip = flip
    this.profile = false

    this.spi = SPI.openSync(0, 0, {
      maxSpeedHz: 24000000,
      // maxSpeedHz: 250000000/20
    })

    this.dcPin = new RIO(OLED.PIN_DC, "output", {value: 0, bias: 'pull-up'})
    this.resetPin = new RIO(OLED.PIN_RESET, "output", {value: 1, bias: 'pull-up'})
    this.mainCanvas = new Canvas(this.width, this.height)
    this.overlayCanvas = new Canvas(this.width, this.height)
    this.framebuf = Buffer.alloc(this.width/2 * this.height)
    this.oddFrame = false
  }

  close() {
    this.spi.closeSync()
  }

  async init() {
    logger.debug('Display Initting')
    this.clear()
    this.clearOverlay()
    await this.reset()
    this.writeCmd(OLED.SET_COMMAND_LOCK, OLED.COMMANDS_UNLOCK)
    this.writeCmd(OLED.DISPLAY_SLEEP_ON)
    this.writeCmd(OLED.SET_FRONT_CLOCK_DIVIDER, 0xf2)
    this.writeCmd(OLED.SET_MULTIPLEX_RATIO, 0x3F)
    this.writeCmd(OLED.SET_DISPLAY_OFFSET, 0)
    this.writeCmd(OLED.SET_DISPLAY_START_LINE, 0)
    this.writeCmd(OLED.SET_REMAP_DUAL_COM_LINE_MODE, 0b00010100, 0x00010001)
    this.writeCmd(OLED.SET_GPIO, 0)
    this.writeCmd(OLED.SET_FUNCTION_SELECTION, 1)
    this.writeCmd(OLED.DISPLAY_ENHANCEMENT_A, OLED.ENABLE_EXTERNAL_VSL | 0xA0, OLED.ENHANCED_LOW_GRAY_SCALE_QUALITY | 0x05)
    this.writeCmd(OLED.SET_CONTRAST_CURRENT, 0xFF)
    this.writeCmd(OLED.MASTER_CURRENT_CONTROL, 15)
    this.writeCmd(OLED.SELECT_DEFAULT_LINEAR_GRAY_SCALE_TABLE)
    this.writeCmd(OLED.SET_PHASE_LENGTH, 0xF4)
    this.writeCmd(OLED.DISPLAY_ENHANCEMENT_B, OLED.RESERVED_ENHANCEMENT | 0xA2, 0x20)
    this.writeCmd(OLED.SET_PRECHARGE_VOLTAGE, 0x1F)
    this.writeCmd(OLED.SET_SECOND_PRECHARGE_PERIOD, 0x08)
    this.writeCmd(OLED.SET_VCOMH_VOLTAGE, 0x07)
    this.writeCmd(OLED.SET_DISPLAY_MODE_NORMAL)
    this.writeCmd(OLED.PARTIAL_DISPLAY_DISABLE)
    this.blit()
    this.writeCmd(OLED.DISPLAY_SLEEP_OFF)
    logger.debug('Display Initted')
  }

  getContext() {
    return this.mainCanvas.getContext('2d')
  }

  getOverlayContext() {
    return this.overlayCanvas.getContext('2d')
  }

  clear() {
    const ctx = this.getContext()
    ctx.fillStyle = "rgba(0,0,0,1)"
    ctx.fillRect(0, 0, this.width, this.height)
  }

  clearOverlay() {
    const ctx = this.getOverlayContext()
    ctx.clearRect(0,0, this.width, this.height)
  }

  setProfile(on=false) {
    this.profile = on
  }

  private async wait(ms: number): Promise<true> {
    return new Promise((resolve, _) => {
      setTimeout(resolve, ms)
    })
  }

  private async reset() {
    this.resetPin.write(0)
    await this.wait(200)
    this.resetPin.write(1)
    await this.wait(200)
  }


  private spiWrite(send: Buffer) {
    this.spi.transferSync([{
      sendBuffer: send,
      byteLength: send.byteLength,
    }])
  }

  private writeData(data: Buffer) {
    this.dcPin.write(1)
    this.spiWrite(data) 
  }

  private writeCmd(cmd: number, ...data: number[]) {
    this.dcPin.write(0)

    if ( data?.length) {
      this.spiWrite(Buffer.from([cmd]))
      return this.writeData(Buffer.from(data))
    } else {
      return this.spiWrite(Buffer.from([cmd]))
    }
  }

  private setColumnAddress(start: number, end: number) {
    this.writeCmd(OLED.SET_COLUMN_ADDRESS, start, end)
  }

  private setRowAddress(start: number, end: number) {
    this.writeCmd(OLED.SET_ROW_ADDRESS, start, end)
  }

  private setAddress(x0: number, y0: number, x1: number, y1: number, offset=28) {
    this.setRowAddress(y0, y1)
    this.setColumnAddress(x0 + offset, x1 + offset)
    this.writeCmd(OLED.WRITE_RAM)
  }

  // Combine the main and overlay canvases into the framebuffer to be blitted to the OLED
  private render() {
    const start = millitime()
    const end = this.width/2 * this.height - 1
    let framePtr = this.flip ? end : 0
    let inc = this.flip ? -1 : 1

    let base = this.getContext().getImageData(0, 0, this.width, this.height).data
    const overlay = this.getOverlayContext().getImageData(0, 0, this.width, this.height).data

    function gray(r: number, g: number, b: number) {
      return (r+g+b)/3
    }

    function quantize(g: number) {
      return Math.round(g) >> 4
    }

    function alpha(base: number, neu: number, alpha: number) {
      return (alpha * neu) + ((1-alpha)*base)
    }

    function colorForPixel(ptr: number) {
      const lower = gray(base[ptr], base[ptr+1], base[ptr+2])
      const lowerAlpha = base[ptr+3]/255
      const upperAlpha  = overlay[ptr+3]/255

      const a = alpha(0, lower, lowerAlpha)

      if ( upperAlpha === 0 ) {
        return quantize(a)
      } else {
        const upper = gray(overlay[ptr], overlay[ptr+1], overlay[ptr+2])
        return quantize(alpha(a, upper, upperAlpha))
      }
    }

    for ( let imgPtr = 0 ; imgPtr < base.byteLength ; imgPtr += 8 ) {
      this.framebuf[framePtr] = colorForPixel(imgPtr) << 4 | colorForPixel(imgPtr+4)
      framePtr += inc
    }

    if ( this.profile ){
      logger.debug(`Rendered in ${millitime(start)}`)
    }
  }

  blit() {
    this.render()

    const start = millitime()

    let yStart = 0
    let displayOffset = 0

    if ( this.oddFrame ) {
      yStart = this.height
      displayOffset = this.height
    }

    this.setAddress(0, yStart, this.width/4 - 1, yStart + this.height-1)

    const step = 4096
    for ( let i = 0 ; i < this.framebuf.byteLength/step ; i++ ) {
      this.writeData(this.framebuf.subarray(step*i, step*(i+1)))
    }

    this.writeCmd(OLED.SET_DISPLAY_START_LINE, displayOffset)

    if ( this.profile ) {
      logger.debug(`Sent in ${millitime(start)}, ${yStart} ${displayOffset}`)
    }

    this.oddFrame = !this.oddFrame
  }

  setBrightness(byte: number) {
    this.writeCmd(OLED.SET_CONTRAST_CURRENT, byte & 0xFF)
    // this.writeCmd(OLED.MASTER_CURRENT_CONTROL, 15)
  }
}

function millitime(then?: number) {
  const hr = process.hrtime()
  const now = hr[0] * 1000 + hr[1]/1000000;

  if ( then ) {
    return Math.round((now - then) * 1000) / 1000
  } else {
    return now
  }
}
