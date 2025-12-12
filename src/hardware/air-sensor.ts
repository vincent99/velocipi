// Sparkfun BME280 temperature/pressure/humidity sensor
// https://www.sparkfun.com/sparkfun-atmospheric-sensor-breakout-bme280-qwiic.html
// https://cdn.sparkfun.com/assets/e/7/3/b/1/BME280_Datasheet.pdf

import I2C, { Peripheral } from "./i2c";

// --- Constants ---
const DEFAULT_ADDRESS = 0x77;
const CALIBRATION_A_REG = 0x88;
const CALIBRATION_B_REG = 0xE1;
const CALIBRATION_H1_REG = 0xA1;
const DATA_REG = 0xF7;
const CHIP_ID_REG = 0xD0; // Chip ID
const RESET_REG = 0xE0;
const CONFIG_HUM_RES = 0xF2; // Humidity config
const CONFIG_MEAS_RES = 0xF4; // Temp/Pressure config
const CONFIG_RES = 0xF5; // Other config

// --- Enums and Types ---

export enum RunMode {
  SLEEP = 0b00,
  FORCED = 0b01,
  NORMAL = 0b11,
}

export enum StandbyConfig {
  SB_1 = 0b000,
  SB_10 = 0b110, // Yes, they're out of order.
  SB_20 = 0b111,
  SB_62 = 0b001,
  SB_125 = 0b010,
  SB_250 = 0b011,
  SB_500 = 0b100,
  SB_1000 = 0b101,
}

export enum FilterConfig {
  FILTER_OFF = 0b000,
  FILTER_2 = 0b001,
  FILTER_4 = 0b010,
  FILTER_8 = 0b011,
  FILTER_16 = 0b100,
}

export enum OversampleConfig {
  SKIPPED = 0b000,
  OS_1 = 0b001,
  OS_2 = 0b010,
  OS_4 = 0b011,
  OS_8 = 0b100,
  OS_16 = 0b101,
}

export type Calibration = {
  T1: number; // uint16
  T2: number; // int16
  T3: number; // int16
  P1: number; // uint16
  P2: number; // int16
  P3: number; // int16
  P4: number; // int16
  P5: number; // int16
  P6: number; // int16
  P7: number; // int16
  P8: number; // int16
  P9: number; // int16
  H1: number; // uint8
  H2: number; // int16
  H3: number; // uint8
  H4: number; // int16
  H5: number; // int16
  H6: number; // int8
}

export type Config = {
  Address: number
  Mode: RunMode;
  Standby: StandbyConfig;
  Filter: FilterConfig;
  TempOversample: OversampleConfig;
  TempCorrectionC: number; // float32
  PressureOversample: OversampleConfig;
  HumidityOversample: OversampleConfig;
}

export type Reading = {
  tempC: number; // float32
  tempF: number; // float32
  pressureInches: number; // float32
  pressureMeters: number; // float32
  pressureFeet: number; // float32
  humidity: number; // float32
  dewpointC: number; // float32
  dewpointF: number; // float32
}

const defaultConfig: Config = {
  Mode: RunMode.NORMAL,
  Standby: StandbyConfig.SB_1,
  Filter: FilterConfig.FILTER_2,
  TempOversample: OversampleConfig.OS_16,
  PressureOversample: OversampleConfig.OS_16,
  HumidityOversample: OversampleConfig.OS_16,
  TempCorrectionC: 0,
  Address: DEFAULT_ADDRESS
}

// --- Main Class ---

export class AirSensor {
  private iface: Peripheral;
  private config: Config;
  private calibration: Calibration;
  private tFine: number; // int32 - compensated temperature intermediate value
  private referencePressure = 101325;

  constructor(bus: I2C, config?: Config) {
    this.config = { ...defaultConfig, ...config || {} }
    this.iface = bus.wrap(this.config.Address)
    this.calibration = {} as Calibration;
    this.tFine = 0;
    this.referencePressure = 101325.0;
  }

  public async init() {
    if (!this.iface?.isConnected()) {
      throw new Error("air sensor not found");
    }

    const chipId = await this.iface.readRegisterU8(CHIP_ID_REG);

    if (chipId !== 0x58 && chipId !== 0x60) {
      throw new Error(`air sensor has unrecognized chip id: 0x${chipId.toString(16)}`);
    }

    // Read calibration registers
    const a = await this.iface.readRegister(CALIBRATION_A_REG, 26);
    const b = await this.iface.readRegister(CALIBRATION_B_REG, 8);
    const h1 = await this.iface.readRegisterU8(CALIBRATION_H1_REG);

    // Parse calibration values (Little Endian, as per BME280 datasheet)
    this.calibration = {
      T1: (a[ 1 ] << 8) | a[ 0 ],
      T2: toSigned16((a[ 3 ] << 8) | a[ 2 ]),
      T3: toSigned16((a[ 5 ] << 8) | a[ 4 ]),

      P1: (a[ 7 ] << 8) | a[ 6 ],
      P2: toSigned16((a[ 9 ] << 8) | a[ 8 ]),
      P3: toSigned16((a[ 11 ] << 8) | a[ 10 ]),
      P4: toSigned16((a[ 13 ] << 8) | a[ 12 ]),
      P5: toSigned16((a[ 15 ] << 8) | a[ 14 ]),
      P6: toSigned16((a[ 17 ] << 8) | a[ 16 ]),
      P7: toSigned16((a[ 19 ] << 8) | a[ 18 ]),
      P8: toSigned16((a[ 21 ] << 8) | a[ 20 ]),
      P9: toSigned16((a[ 23 ] << 8) | a[ 22 ]),

      H1: h1,
      H2: toSigned16((b[ 1 ] << 8) | b[ 0 ]),
      H3: b[ 2 ],
      H4: toSigned16((b[ 3 ] << 4) | (b[ 4 ] & 0x0F)),
      H5: toSigned16((b[ 5 ] << 4) | ((b[ 4 ] >> 4) & 0x0F)),
      H6: b[ 6 ] > 127 ? b[ 6 ] - 256 : b[ 6 ], // Convert uint8 to int8
    };

    await this.writeConfig();
  }

  public async reset() {
    await this.iface.writeRegisterU8(RESET_REG, 0xB6);
  }

  public async setConfig(config: Config) {
    this.config = {...defaultConfig, ...config}
    return this.writeConfig()
  }

  // -------- Config Methods --------
  private async writeConfig() {
    // Set mode to sleep before writing configuration registers
    await this.setMode(RunMode.SLEEP);

    let hum = await this.iface.readRegisterU8(CONFIG_HUM_RES);

    // Set humidity oversampling (bits 2:0)
    hum = (hum & 0b11111000) | this.config.HumidityOversample;

    // Set standby (bits 7:5) and filter (bits 4:2)
    const cfg = (this.config.Standby << 5) | (this.config.Filter << 2);

    // Set temp oversample (bits 7:5), pressure oversample (bits 4:2), and mode (bits 1:0)
    const meas = (this.config.TempOversample << 5) | (this.config.PressureOversample << 2) | this.config.Mode;

    await this.iface.writeRegisterU8(CONFIG_HUM_RES, hum);
    await this.iface.writeRegisterU8(CONFIG_RES, cfg);
    await this.iface.writeRegisterU8(CONFIG_MEAS_RES, meas);
  }

  public async getMode(): Promise<RunMode> {
    const cfg = await this.iface.readRegisterU8(CONFIG_MEAS_RES);
    // Mode is bits 1:0
    return cfg & 0b11;
  }

  public async setMode(val: RunMode) {
    let cfg = await this.iface.readRegisterU8(CONFIG_MEAS_RES);
    // Clear old mode bits (1:0) and set new mode bits
    cfg = (cfg & 0b11111100) | val;
    await this.iface.writeRegisterU8(CONFIG_MEAS_RES, cfg);
  }

  // -------- Reading Method (Compensation Logic) --------

  public async read(): Promise<Reading> {
    const raw = await this.iface.readRegister(DATA_REG, 8);

    // Parse raw data (MSB-LSB-XLSB format)
    // Pressure: raw[0:2] (20-bit, bits 3:0 of raw[2] are LSBs)
    const p = (raw[ 0 ] << 12) | (raw[ 1 ] << 4) | (raw[ 2 ] >> 4);

    // Temperature: raw[3:5] (20-bit, bits 3:0 of raw[5] are LSBs)
    const t = (raw[ 3 ] << 12) | (raw[ 4 ] << 4) | (raw[ 5 ] >> 4);

    // Humidity: raw[6:7] (16-bit)
    const h = (raw[ 6 ] << 8) | raw[ 7 ];

    // --- 1. Temperature Compensation (t_fine calculation) ---
    const _t1 = (t >> 3) - (this.calibration.T1 << 1);
    const _t2 = (((t >> 4) - this.calibration.T1) * ((t >> 4) - this.calibration.T1)) >> 12;

    const t1 = (_t1 * this.calibration.T2) >> 11;
    const t2 = (_t2 * this.calibration.T3) >> 14;

    this.tFine = t1 + t2;

    const celsius = (((this.tFine * 5 + 128) >> 8) / 100) + this.config.TempCorrectionC;
    const fahrenheit = (celsius * 9) / 5 + 32;

    // --- 2. Pressure Compensation ---
    function shiftl(num: bigint|number, by: number) {
      return BigInt(num) << BigInt(by)
    }

    function shiftr(num: bigint|number, by: number) {
      return BigInt(num) >> BigInt(by)
    }

    let p1 = BigInt(this.tFine - 128000);
    let p2 = BigInt(p1 * p1 * BigInt(this.calibration.P6));

    p2 = p2 + shiftl(p1 * BigInt(this.calibration.P5), 17)
    p2 = p2 + shiftl(this.calibration.P4, 35);
    p1 = shiftr(p1 * p1 * BigInt(this.calibration.P3), 8) + shiftl(p1 * BigInt(this.calibration.P2), 12)
    p1 = shiftr((shiftl(1,47) + p1) * BigInt(this.calibration.P1), 33)

    let press = 0;
    if (p1 !== BigInt(0)) {
      let pA = BigInt(1048576 - p)
      pA = ((shiftl(pA, 31) - p2) * BigInt(3125)) / p1
      p1 = shiftr(BigInt(this.calibration.P9) * shiftr(pA, 13) * shiftr(pA, 13), 25)
      p2 = shiftr(BigInt(this.calibration.P8) * pA, 19)

      pA = shiftr(pA + p1 + p2, 8) + shiftl(this.calibration.P7, 4)
      press = parseInt(BigInt(pA / BigInt(256)).toString(), 10); // Pressure in Pa
    }

    // --- 3. Altitude and Unit Conversions ---

    const inches = press / 3386.39; // Pa to inHg

    // Altitude (meters) formula: H = 44330.77 * (1 - (P/P_ref)^(1/5.255)) - Uses 1/0.190263 ~ 5.255
    const meters = (-44330.77) * (Math.pow(press / this.referencePressure, 0.190263) - 1.0);
    const feet = meters * 3.28084;

    // --- 4. Humidity Compensation ---
    let h1 = this.tFine - 76800;

    h1 = (
      ((
        ((h << 14) - (this.calibration.H4 << 20) - (this.calibration.H5 * h1)) + 16384
      ) >> 15) * (
        ((
          (
            (((h1 * this.calibration.H6) >> 10) * (
              ((h1 * this.calibration.H3) >> 11) + 32768
            )) >> 10
          ) + 2097152
        ) * this.calibration.H2 + 8192
        ) >> 14
      )
    )

    h1 = h1 - (((((h1 >> 15) * (h1 >> 15)) >> 7) * this.calibration.H1) >> 4);

    // Clamp to 0-100% (with factor 1024.0)
    h1 = Math.min(Math.max(h1, 0), 419430400);

    const humidity = (h1 >> 12) / 1024.0; // %RH

    // --- 5. Dewpoint Calculation (Magnus formula approximation) ---

    const ratio = 373.15 / (273.15 + celsius);
    let rhs = -7.90298 * (ratio - 1);
    rhs += 5.02808 * Math.log10(ratio);
    rhs += -1.3816e-7 * (Math.pow(10, (11.344 * (1 - 1 / ratio))) - 1);
    rhs += 8.1328e-3 * (Math.pow(10, (-3.49149 * (ratio - 1))) - 1);
    rhs += Math.log10(1013.246);
    const vp = Math.pow(10, rhs - 3) * humidity; // Vapor Pressure
    const th = Math.log(vp / 0.61078);

    const dewpointCelsius = (241.88 * th) / (17.558 - th);
    const dewpointFahrenheit = (dewpointCelsius * 9) / 5 + 32;

    return {
      tempC: celsius,
      tempF: fahrenheit,
      pressureInches: inches,
      pressureMeters: meters,
      pressureFeet: feet,
      humidity: humidity,
      dewpointC: dewpointCelsius,
      dewpointF: dewpointFahrenheit,
    };
  }
}

function toSigned16(val: number): number {
  return (val & 0x8000) ? val - 0x10000 : val;
}
