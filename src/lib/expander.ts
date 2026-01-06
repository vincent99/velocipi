import EventEmitter from "events";
import I2C, { Peripheral } from "./i2c";
import { logger } from "../logger";
import { strPad } from "../util/string";

// --- Constants ---
const DEFAULT_ADDRESS = 0x20;
const DIRECTION_CONF = 0x00; // 0 = output, 1 = input
const POLARITY_CONF = 0x02;
const PULL_UP_CONF = 0x0C;
const INTERRUPT_ENABLE = 0x04;
const INTERRUPT_MODE = 0x08;
const INTERRUPT_COMPARE = 0x06;
const INTERRUPT = 0x0E;
const INTERRUPT_VALUE = 0x10;
const INPUT_VALUE = 0x12;
const OUTPUT_VALUE = 0x14;

// --- Types ---
export interface Config {
  address: number;
  interval: number
}

export interface InterruptResult {
  changed: boolean
  value: number
  previous: number
}

const defaultConfig: Config = {
  address: DEFAULT_ADDRESS,
  interval: 1000 / 120
}

// --- Main Class ---
export class Expander extends EventEmitter {
  private iface: Peripheral;
  private config: Config;
  private timer: NodeJS.Timeout;
  private previous: number;

  constructor(bus: I2C, config?: Config) {
    super()

    this.config = { ...defaultConfig, ...config || {} }
    this.iface = bus.wrap(this.config.address)
  }

  public async init(inputs = 0xFFFF) {
    if (!this.iface?.isConnected()) {
      throw new Error("Air sensor not found");
    }

    // Setup pins as input or output
    await this.setDirection(inputs);

    // Set polarity to normal (0xffff)
    await this.setPolarity(0xFFFF);

    // Set all pull-up resistors enabled (0xffff)
    await this.setPullUp(0xFFFF);

    this.previous = await this.read()

    // Set interrupts: enabled=inputs, mode=0x0000 (compare previous), value=0x0000 (comparison value)
    await this.getInterrupts(inputs, 0x0000, this.previous);

    this.timer = setInterval(async () => {
      const res = await this.readInterrupt()

      if (res.changed) {
        logger.info(`Changed: ${format(res.previous)} -> ${format(res.value)}`)
      }
    }, this.config.interval)
  }

  close() {
    clearInterval(this.timer)
  }

  // --- Configuration Methods ---

  public async setDirection(pins: number): Promise<void> {
    await this.iface.writeRegisterU16LE(DIRECTION_CONF, pins);
  }

  public async getDirection(): Promise<number> {
    return this.iface.readRegisterU16LE(DIRECTION_CONF);
  }

  public async setPolarity(pins: number): Promise<void> {
    await this.iface.writeRegisterU16LE(POLARITY_CONF, pins);
  }

  public async getPolarity(): Promise<number> {
    return this.iface.readRegisterU16LE(POLARITY_CONF);
  }

  public async setPullUp(pins: number): Promise<void> {
    await this.iface.writeRegisterU16LE(PULL_UP_CONF, pins);
  }

  public async getPullUp(): Promise<number> {
    return this.iface.readRegisterU16LE(PULL_UP_CONF);
  }

  public async getInterrupts(enabled: number, mode: number, value: number): Promise<void> {
    await this.iface.writeRegisterU16LE(INTERRUPT_ENABLE, enabled);
    await this.iface.writeRegisterU16LE(INTERRUPT_MODE, mode);
    await this.iface.writeRegisterU16LE(INTERRUPT_COMPARE, value);
  }

  public async getInterruptConfig(): Promise<{ enabled: number, mode: number, value: number }> {
    const enabled = await this.iface.readRegisterU16LE(INTERRUPT_ENABLE);
    const mode = await this.iface.readRegisterU16LE(INTERRUPT_MODE);
    const value = await this.iface.readRegisterU16LE(INTERRUPT_COMPARE);
    return { enabled, mode, value };
  }

  // --- I/O Methods ---

  public async read(): Promise<number> {
    return this.iface.readRegisterU16LE(INPUT_VALUE);
  }

  public async write(value: number): Promise<void> {
    await this.iface.writeRegisterU16LE(OUTPUT_VALUE, value);
  }

  public async readInterrupt(): Promise<InterruptResult> {
    const intr = await this.iface.readRegisterU16LE(INTERRUPT);
    const previous = this.previous

    if (intr === 0) {
      return { changed: false, value: previous, previous };
    }

    const value = await this.iface.readRegisterU16LE(INTERRUPT_VALUE);
    this.previous = value
    return { changed: true, value, previous };
  }
}

function format(val: number) {
  return strPad(`${(val >> 8).toString(2)}`, 8, '0', false) + ' ' + strPad(`${(val & 0xFF).toString(2)}`, 8, '0', false)
}
