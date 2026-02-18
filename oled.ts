import { RIO } from 'rpi-io';
import SPI, { SpiDevice } from 'spi-device';
import { logger } from '../logger';
import { Canvas, CanvasRenderingContext2D } from 'skia-canvas';
import { sleep } from '../util/time';
import config from '../config';

export default class OLED {
  // Command constants from display datasheet
  // private static readonly ENABLE_GRAY_SCALE_TABLE = 0x00
  private static readonly SET_COLUMN_ADDRESS = 0x15;
  private static readonly WRITE_RAM = 0x5c;
  // private static readonly READ_RAM = 0x5D
  private static readonly SET_ROW_ADDRESS = 0x75;
  private static readonly SET_REMAP_DUAL_COM_LINE_MODE = 0xa0; // Re-map & Dual COM Line Mode
  private static readonly SET_DISPLAY_START_LINE = 0xa1;
  private static readonly SET_DISPLAY_OFFSET = 0xa2;
  // private static readonly SET_DISPLAY_MODE_ALL_OFF = 0xA4
  // private static readonly SET_DISPLAY_MODE_ALL_ON = 0xA5
  private static readonly SET_DISPLAY_MODE_NORMAL = 0xa6;
  // private static readonly SET_DISPLAY_MODE_INVERSE = 0xA7
  // private static readonly PARTIAL_DISPLAY_ENABLE = 0xA8
  private static readonly PARTIAL_DISPLAY_DISABLE = 0xa9;
  private static readonly SET_FUNCTION_SELECTION = 0xab;
  private static readonly DISPLAY_SLEEP_ON = 0xae;
  private static readonly DISPLAY_SLEEP_OFF = 0xaf;
  private static readonly SET_PHASE_LENGTH = 0xb1;
  private static readonly SET_FRONT_CLOCK_DIVIDER = 0xb3;
  private static readonly DISPLAY_ENHANCEMENT_A = 0xb4;
  private static readonly SET_GPIO = 0xb5;
  private static readonly SET_SECOND_PRECHARGE_PERIOD = 0xb6;
  // private static readonly SET_GRAY_SCALE_TABLE = 0xB8
  private static readonly SELECT_DEFAULT_LINEAR_GRAY_SCALE_TABLE = 0xb9;
  private static readonly SET_PRECHARGE_VOLTAGE = 0xbb;
  private static readonly SET_VCOMH_VOLTAGE = 0xbe;
  private static readonly SET_CONTRAST_CURRENT = 0xc1;
  private static readonly MASTER_CURRENT_CONTROL = 0xc7;
  private static readonly SET_MULTIPLEX_RATIO = 0xca;
  private static readonly DISPLAY_ENHANCEMENT_B = 0xd1;
  private static readonly SET_COMMAND_LOCK = 0xfd;

  // Options for controlling VSL selection
  private static readonly ENABLE_EXTERNAL_VSL = 0x00;
  // private static readonly ENABLE_INTERNAL_VSL = 0x02

  // Options for grayscale quality
  // private static readonly NORMAL_GRAYSCALE_QUALITY = 0xB0
  private static readonly ENHANCED_LOW_GRAY_SCALE_QUALITY = 0xf8;

  // Options for display enhancement b
  private static readonly RESERVED_ENHANCEMENT = 0x00;
  // private static readonly NORMAL_ENHANCEMENT = 0x02

  // Options for command lock
  // private static readonly COMMANDS_LOCK = 0x16
  private static readonly COMMANDS_UNLOCK = 0x12;

  // Column and row maximums
  // private static readonly COLUMN_ADDRESS = 0x77
  // private static readonly ROW_ADDRESS = 0x7F

  private spi: SpiDevice;
  private dcPin: RIO;
  private resetPin: RIO;
  public width: number;
  public height: number;
  private flip: boolean;
  private frameCanvas: Canvas;
  private frameCtx: CanvasRenderingContext2D;
  private frameBuf: Buffer;

  constructor(canvas: Canvas, flip = false) {
    this.frameCanvas = canvas;
    this.width = canvas.width;
    this.height = canvas.height;
    this.frameCtx = this.frameCanvas.getContext('2d');
    this.flip = flip;

    this.spi = SPI.openSync(
      config.get('oled.spiBus'),
      config.get('oled.spiDevice'),
      {
        maxSpeedHz: config.get('oled.spiSpeed'),
      }
    );

    this.dcPin = new RIO(config.get('oled.dataCommandPin'), 'output', {
      value: 0,
      bias: 'pull-up',
    });
    this.resetPin = new RIO(config.get('oled.resetPin'), 'output', {
      value: 1,
      bias: 'pull-up',
    });

    this.frameBuf = Buffer.alloc((this.width / 2) * this.height);
  }

  close() {
    this.writeCmd(OLED.DISPLAY_SLEEP_ON);
    this.spi.closeSync();
    this.dcPin.close();
    this.resetPin.close();
  }

  async init() {
    logger.debug('Display Initting');
    await this.reset();
    this.writeCmd(OLED.SET_COMMAND_LOCK, OLED.COMMANDS_UNLOCK);
    this.writeCmd(OLED.DISPLAY_SLEEP_ON);
    this.setAddress(0, 0, this.width / 4 - 1, this.height - 1);
    this.writeCmd(OLED.SET_FRONT_CLOCK_DIVIDER, 0x91); // B3
    this.writeCmd(OLED.SET_MULTIPLEX_RATIO, 0x3f);
    this.writeCmd(OLED.SET_DISPLAY_OFFSET, 0);
    this.writeCmd(OLED.SET_DISPLAY_START_LINE, 0);
    this.writeCmd(
      OLED.SET_REMAP_DUAL_COM_LINE_MODE,
      ///--------- Always 0
      //||/------- Always 0
      //|||/------ 0: Disable COM split, 1: Enable
      //||||/----- 0: Scan from beginning, 1: Scan from end
      //|||||/---- Always 0
      //||||||/--- 0: Normal, 1: Flip pixel nibbles
      //|||||||/-- 0: Normal, 1: Flip columns left-to-right
      //||||||||/- 0: Scan addresses horizontally, 1: Vertically
      0b00010100,

      ///--------- Always 0
      //||/------- Always 0
      //|||/------ Always 0
      //||||/----- 0: Disable Dual COM mode, 1: Enable
      //|||||/---- Always 0
      //||||||/--- Always 0
      //|||||||/-- Always 1
      //||||||||/- Always 1
      0x00010011
    ); // A0
    this.writeCmd(OLED.SET_GPIO, 0); // B5
    this.writeCmd(OLED.SET_FUNCTION_SELECTION, 1); // AB
    this.writeCmd(
      OLED.DISPLAY_ENHANCEMENT_A,
      OLED.ENABLE_EXTERNAL_VSL | 0xa0,
      OLED.ENHANCED_LOW_GRAY_SCALE_QUALITY | 0x05
    );
    this.writeCmd(OLED.SET_CONTRAST_CURRENT, 0xff); // C1
    this.writeCmd(OLED.MASTER_CURRENT_CONTROL, 0xf);
    this.writeCmd(OLED.SELECT_DEFAULT_LINEAR_GRAY_SCALE_TABLE);
    this.writeCmd(OLED.SET_PHASE_LENGTH, 0xe2); // B1
    this.writeCmd(OLED.SET_SECOND_PRECHARGE_PERIOD, 0x8); // B6
    this.writeCmd(
      OLED.DISPLAY_ENHANCEMENT_B,
      OLED.RESERVED_ENHANCEMENT | 0xa2,
      0x20
    );
    this.writeCmd(OLED.SET_PRECHARGE_VOLTAGE, 0x1f); // BB
    this.writeCmd(OLED.SET_VCOMH_VOLTAGE, 0x7); // BE
    this.writeCmd(OLED.SET_DISPLAY_MODE_NORMAL);
    this.writeCmd(OLED.PARTIAL_DISPLAY_DISABLE);
    this.writeCmd(OLED.DISPLAY_SLEEP_OFF);
    logger.debug('Display Initted');
  }

  setBrightness(byte: number) {
    this.writeCmd(OLED.SET_CONTRAST_CURRENT, byte & 0xff);
    // this.writeCmd(OLED.MASTER_CURRENT_CONTROL, 15)
  }

  async toPng(): Promise<Buffer> {
    return this.frameCanvas.toBuffer('png');
  }

  // -------------------------------------
  // Private
  // -------------------------------------

  public async reset() {
    this.resetPin.write(0);
    await sleep(200);
    this.resetPin.write(1);
    await sleep(200);
  }

  private spiWrite(send: Buffer) {
    this.spi.transferSync([
      {
        sendBuffer: send,
        byteLength: send.byteLength,
      },
    ]);
  }

  private writeData(data: Buffer) {
    this.dcPin.write(1);
    this.spiWrite(data);
  }

  private writeCmd(cmd: number, ...data: number[]) {
    this.dcPin.write(0);

    if (data?.length) {
      this.spiWrite(Buffer.from([cmd]));
      return this.writeData(Buffer.from(data));
    } else {
      return this.spiWrite(Buffer.from([cmd]));
    }
  }

  private setColumnAddress(start: number, end: number) {
    this.writeCmd(OLED.SET_COLUMN_ADDRESS, start, end);
  }

  private setRowAddress(start: number, end: number) {
    this.writeCmd(OLED.SET_ROW_ADDRESS, start, end);
  }

  private setAddress(
    x0: number,
    y0: number,
    x1: number,
    y1: number,
    offset = 0x1c
  ) {
    this.setRowAddress(y0, y1);
    this.setColumnAddress(x0 + offset, x1 + offset);
    this.writeCmd(OLED.WRITE_RAM);
  }

  // 2. Convert to grayscale
  // 3. Write out SPI off-screen
  // 4. Move screen to show new frame
  public async blit(num: number) {
    // 1. Save current frame
    const image = this.frameCtx.getImageData(0, 0, this.width, this.height);
    const buf = this.frameBuf;

    // 2. Convert to 4-bit gray in frameBuff
    let framePtr = this.flip ? (this.width / 2) * this.height - 1 : 0;
    const inc = this.flip ? -1 : 1;
    const px = image.data;
    let limit = px.byteLength;

    for (let p = 0; p < limit; p += 8) {
      buf[framePtr] =
        toGray(px[p], px[p + 1], px[p + 2], px[p + 3]) |
        (toGray(px[p + 4], px[p + 5], px[p + 6], px[p + 7]) << 4);
      framePtr += inc;
    }

    const yStart = num % 2 === 1 ? this.height : 0;
    const displayOffset = num % 2 === 1 ? this.height : 0;
    const step = 4096;

    // 3. Double buffering… Move to an area that's not on screen right now
    this.setAddress(0, yStart, this.width / 4 - 1, yStart + this.height - 1);

    // Write pixels there
    limit = buf.byteLength / step;
    for (let i = 0; i < limit; i++) {
      this.writeData(buf.subarray(step * i, step * (i + 1)));
    }

    // 4. Move the active screen to the new pixels
    this.writeCmd(OLED.SET_DISPLAY_START_LINE, displayOffset);
  }
}

function toGray(r: number, g: number, b: number, a: number) {
  return Math.round(((0.3 * r + 0.59 * g + 0.11 * b) * a) / 255) >> 4;
}
