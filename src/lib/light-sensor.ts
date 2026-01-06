// Sparkfun VEML6030 ambient light sensor
// https://www.sparkfun.com/sparkfun-ambient-light-sensor-veml6030-qwiic.html
// https://cdn.sparkfun.com/assets/d/7/4/2/9/veml6030_datasheet.pdf

import I2C, { Peripheral } from "./i2c";

// --- Constants ---
const DEFAULT_ADDRESS = 0x48;

// 16-bit registers
const SETTING_REG = 0x00;
const H_THRESH_REG = 0x01;
const L_THRESH_REG = 0x02;
const POWER_SAVE_REG = 0x03;
const AMBIENT_LIGHT_DATA_REG = 0x04;
const WHITE_LIGHT_DATA_REG = 0x05;
const INTERRUPT_REG = 0x06;

// 16-bit register masks
const THRESH_MASK = 0x0;
const GAIN_MASK = 0x1800;
const INTEG_MASK = 0x03C0;
const PERS_PROT_MASK = 0x0030;
const INT_EN_MASK = 0x0002;
const INT_MASK = 0xC000;

// Register bit positions
const NO_SHIFT = 0x00;
const INT_EN_POS = 0x01;
const PSM_POS = 0x01;
const PERS_PROT_POS = 0x04;
const INTEG_POS = 0x06;
const GAIN_POS = 0xB;
const INT_POS = 0xE;

// Integration times (used in switch statements, not registers)
const INTEG_TIME_800 = 800;
const INTEG_TIME_400 = 400;
const INTEG_TIME_200 = 200;
const INTEG_TIME_100 = 100;
const INTEG_TIME_50 = 50;
const INTEG_TIME_25 = 25;

// Lux conversion lookup tables
const EIGHT_HIT: number[] = [ 0.0036, 0.0072, 0.0288, 0.0576 ];
const FOUR_HIT: number[] = [ 0.0072, 0.0144, 0.0576, 0.1152 ];
const TWO_HIT: number[] = [ 0.0144, 0.0288, 0.1152, 0.2304 ];
const ONE_HIT: number[] = [ 0.0288, 0.0576, 0.2304, 0.4608 ];
const FIFTY_HIT: number[] = [ 0.0576, 0.1152, 0.4608, 0.9216 ];
const TWENTY_FIVE_IT: number[] = [ 0.1152, 0.2304, 0.9216, 1.8432 ];

// --- Types and Enums ---

export interface Config {
  Address: number; // uint8
}

const defaultConfig: Config = {
  Address: DEFAULT_ADDRESS
}

export enum Interrupt {
  None = 0,
  Low = 2, // Corresponds to register value 2
  High = 1, // Corresponds to register value 1
}

// --- Main Class ---

export class LightSensor {
  private iface: Peripheral;
  private config: Config

  constructor(bus: I2C, config?: Partial<Config>) {
    this.config = { ...defaultConfig, ...config || {} }
    this.iface = bus.wrap(this.config.Address)
  }

  public async init(): Promise<void> {
    if (!(await this.iface.isConnected()) ) {
      throw new Error("Light sensor not found");
    }

    try {
      await this.setPower(true);
      await this.setGain(4);
      await this.setIntegrationTime(800);
      await this.setPersistenceProtect(8);
      await this.setInterruptEnabled(false);
      await this.setInterruptThresholds(100, 1000);
    } catch (err) {
      throw new Error(`Light sensor initialization failed: ${err}`);
    }
  }

  // -------- Power and Power Save --------

  public async setPower(on: boolean): Promise<void> {
    // Power bit (0) set to 0 (power on) or 1 (power off)
    const data = on ? 0 : 1;
    await this.writeRegister(SETTING_REG, 0x0001, data, NO_SHIFT);
  }

  public async getPower(): Promise<boolean> {
    const raw = await this.readRegister(SETTING_REG);
    // Bit 0: 0 = power on, 1 = power off
    return (raw & 0x0001) === 0;
  }

  public async setPowerSave(enabled: boolean, mode: number): Promise<void> {
    if (mode < 1 || mode > 4) {
      throw new Error("invalid power save mode");
    }

    let val: number;

    if (enabled) {
      val = 0;
    } else {
      val = 1;
    }

    // Bits 2:1 are power save mode (PSM: 0-3 maps to mode 1-4)
    val += (mode - 1) << PSM_POS;

    await this.writeRegister(POWER_SAVE_REG, 0x0007, val, NO_SHIFT);
  }

  public async getPowerSave(): Promise<{ enabled: boolean, mode: number }> {
    const val = await this.readRegister(POWER_SAVE_REG);

    const enabled = (val & 0x1) === 0; // Bit 0: 0=enabled, 1=disabled
    const mode = ((val & 0x6) >> PSM_POS) + 1; // Bits 2:1

    return { enabled, mode };
  }

  // -------- Gain --------

  public async setGain(gain: number): Promise<void> {
    if (gain < 1 || gain > 4) {
      throw new Error("invalid gain");
    }

    let val: number = 0;

    switch (gain) {
      case 1: val = 0x02; break; // Gain 1/8
      case 2: val = 0x03; break; // Gain 1/4
      case 3: val = 0x00; break; // Gain 1
      case 4: val = 0x01; break; // Gain 2
    }

    await this.writeRegister(SETTING_REG, GAIN_MASK, val, GAIN_POS);
  }

  public async getGain(): Promise<number> {
    const raw = await this.readRegister(SETTING_REG);
    const val = (raw & GAIN_MASK) >> GAIN_POS;

    switch (val) {
      case 0x00: return 3; // Gain 1
      case 0x01: return 4; // Gain 2
      case 0x02: return 1; // Gain 1/8
      case 0x03: return 2; // Gain 1/4
      default:
        throw new Error("invalid gain received");
    }
  }

  // -------- Integration Time --------

  public async setIntegrationTime(time: number): Promise<void> {
    let val: number = 0;

    switch (time) {
      case INTEG_TIME_25: val = 0x0C; break;
      case INTEG_TIME_50: val = 0x08; break;
      case INTEG_TIME_100: val = 0x00; break;
      case INTEG_TIME_200: val = 0x01; break;
      case INTEG_TIME_400: val = 0x02; break;
      case INTEG_TIME_800: val = 0x03; break;
      default:
        throw new Error("invalid integration time");
    }

    await this.writeRegister(SETTING_REG, INTEG_MASK, val, INTEG_POS);
  }

  public async getIntegrationTime(): Promise<number> {
    const raw = await this.readRegister(SETTING_REG);
    const val = (raw & INTEG_MASK) >> INTEG_POS;

    switch (val) {
      case 0x0C: return INTEG_TIME_25;
      case 0x08: return INTEG_TIME_50;
      case 0x00: return INTEG_TIME_100;
      case 0x01: return INTEG_TIME_200;
      case 0x02: return INTEG_TIME_400;
      case 0x03: return INTEG_TIME_800;
      default:
        throw new Error("invalid integration time");
    }
  }

  // -------- Persistence Protect --------

  public async setPersistenceProtect(num: number): Promise<void> {
    let val: number = 0;

    switch (num) {
      case 1: val = 0x00; break;
      case 2: val = 0x01; break;
      case 4: val = 0x02; break;
      case 8: val = 0x03; break;
      default:
        throw new Error("invalid persistence protect");
    }

    await this.writeRegister(SETTING_REG, PERS_PROT_MASK, val, PERS_PROT_POS);
  }

  public async getPersistenceProtect(): Promise<number> {
    const raw = await this.readRegister(SETTING_REG);
    const val = (raw & PERS_PROT_MASK) >> PERS_PROT_POS;

    switch (val) {
      case 0x00: return 1;
      case 0x01: return 2;
      case 0x02: return 4;
      case 0x03: return 8; // Note: Go code had 0x04 for case 8, which is incorrect based on datasheet/bits
      default:
        throw new Error("invalid persistence protect");
    }
  }

  // -------- Interrupts --------

  public async setInterruptEnabled(enabled: boolean): Promise<void> {
    const data = enabled ? 1 : 0;
    await this.writeRegister(SETTING_REG, INT_EN_MASK, data, INT_EN_POS);
  }

  public async getInterruptEnabled(): Promise<boolean> {
    const raw = await this.readRegister(SETTING_REG);
    const val = (raw & INT_EN_MASK) >> INT_EN_POS;
    return val > 0;
  }

  public async setInterruptThresholds(lowLux: number, highLux: number): Promise<void> {
    if (lowLux < 0 || lowLux > 120000) {
      throw new Error("invalid low lux value");
    }
    if (highLux < 0 || highLux > 120000) {
      throw new Error("invalid high lux value");
    }

    const lowBits = await this.luxToBits(lowLux);
    const highBits = await this.luxToBits(highLux);

    await this.writeRegister(L_THRESH_REG, THRESH_MASK, lowBits, NO_SHIFT);
    await this.writeRegister(H_THRESH_REG, THRESH_MASK, highBits, NO_SHIFT);
  }

  public async getInterruptThresholds(): Promise<{ low: number, high: number }> {
    const lowBits = await this.readRegister(L_THRESH_REG);
    const highBits = await this.readRegister(H_THRESH_REG);

    const low = await this.bitsToLux(lowBits);
    const high = await this.bitsToLux(highBits);

    return { low, high };
  }

  public async readInterrupt(): Promise<Interrupt> {
    const raw = await this.readRegister(INTERRUPT_REG);
    const val = (raw & INT_MASK) >> INT_POS;

    switch (val) {
      case 0: return Interrupt.None;
      case 1: return Interrupt.High;
      case 2: return Interrupt.Low;
      default:
        throw new Error("invalid interrupt state");
    }
  }

  // -------- Data Reading --------

  // Public method, required by brightness.go
  public async getAmbientLux(): Promise<number> {
    const bits = await this.readRegister(AMBIENT_LIGHT_DATA_REG);
    return this.bitsToLuxCompensated(bits);
  }

  public async getWhiteLux(): Promise<number> {
    const bits = await this.readRegister(WHITE_LIGHT_DATA_REG);
    return this.bitsToLuxCompensated(bits);
  }

  // -------- Internal Helper Methods --------

  private async readRegister(reg: number): Promise<number> {
    // Reads a 16-bit register value in Little-Endian format
    return this.iface.readRegisterU16LE(reg);
  }

  private async writeRegister(reg: number, mask: number, data: number, shift: number): Promise<void> {
    if (shift > 0) {
      data = data << shift;
    }

    let val: number;

    if (mask > 0) {
      // Read current value
      const currentVal = await this.readRegister(reg);

      // Clear old masked bits (val & ^mask) and set new bits (data & mask)
      val = (currentVal & ~mask) | (data & mask);
    } else {
      // No mask means write the raw data
      val = data;
    }

    await this.iface.writeRegisterU16LE(reg, val);
  }

  private async luxToBitFactor(): Promise<number> {
    const gain = await this.getGain();
    const integration = await this.getIntegrationTime();

    const index = gain - 1;
    let factor: number;

    switch (integration) {
      case INTEG_TIME_800: factor = EIGHT_HIT[ index ]; break;
      case INTEG_TIME_400: factor = FOUR_HIT[ index ]; break;
      case INTEG_TIME_200: factor = TWO_HIT[ index ]; break;
      case INTEG_TIME_100: factor = ONE_HIT[ index ]; break;
      case INTEG_TIME_50: factor = FIFTY_HIT[ index ]; break;
      case INTEG_TIME_25: factor = TWENTY_FIVE_IT[ index ]; break;
      default:
        throw new Error("unsupported integration time");
    }

    return factor;
  }

  private async luxToBits(lux: number): Promise<number> {
    const factor = await this.luxToBitFactor();
    return Math.round(lux / factor); // Return as number (TypeScript equivalent of uint16)
  }

  private async bitsToLux(bits: number): Promise<number> {
    const factor = await this.luxToBitFactor();
    return Math.round(bits * factor); // Return as number (TypeScript equivalent of int)
  }

  private async bitsToLuxCompensated(bits: number): Promise<number> {
    const val = await this.bitsToLux(bits);
    const flux = val; // Use val as float64 equivalent

    if (val <= 1000) {
      return flux;
    }

    // Polynomial compensation formula from the VEML6030 datasheet
    // Using standard Math for calculation. For extreme precision, dedicated high-precision libraries might be needed.
    const compensated = (
      (0.00000000000060135 * Math.pow(flux, 4)) -
      (0.0000000093924 * Math.pow(flux, 3)) +
      (0.000081488 * Math.pow(flux, 2)) +
      (1.0023 * flux)
    );

    return compensated;
  }
}
