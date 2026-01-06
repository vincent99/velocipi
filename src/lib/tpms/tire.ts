// --- Constants ---
const BATT_100 = 31;         // in 0.1V
const BATT_0 = 26;           // in 0.1V
const TEMP_OFFSET = 20;      // in °C
const PRESSURE_OFFSET = 146; // in 0.1 PSI

const BIT_FLAT = 0b10000000;
const BIT_ROLLING = 0b01000000;
const BIT_STILL = 0b00100000;
const BIT_STARTING = 0b00010000;
const BIT_DECREASING = 0b00001000;
const BIT_RISING = 0b00000100;
const BIT_LOW = 0b00000010;

// --- Enums and Types ---

export enum InflationState {
  FLAT = "flat",
  LOW = "low",
  DECREASING = "decreasing",
  STABLE = "stable",
  RISING = "rising",
}

export enum RotationState {
  UNKNOWN = "unknown",
  STILL = "still",
  STARTING = "starting",
  ROLLING = "rolling",
}

// --- Tire Class ---

export class Tire {
  public position: string;
  public serial: string;
  public updated: Date;

  public tempC: number = 0;
  public tempF: number = 0;

  public pressureRaw: number = 0;
  public pressureKpa: number = 0;
  public pressureBar: number = 0;
  public pressurePsi: number = 0;

  public voltage: number = 0;
  public battery: number = 0;

  public inflation: InflationState = InflationState.STABLE;
  public rotation: RotationState = RotationState.UNKNOWN;
  public state: number = 0; // byte

  constructor(position: string, serial: string) {
    this.position = position;
    this.serial = serial;
    this.updated = new Date(0); // Initialize to an epoch time
  }

  public ageInSeconds(): number {
    // Equivalent to time.Since(t.Updated).Seconds()
    return (Date.now() - this.updated.getTime()) / 1000;
  }

  /**
   * Updates the tire's state and converts raw data into usable metrics.
   * @param state The state byte (uint8).
   * @param voltage The voltage raw value (uint8, 0.1V units).
   * @param temperature The temperature raw value (uint8, 0.1C units).
   * @param pressure The pressure raw value (uint16, 0.1 PSI units).
   */
  public update(state: number, voltage: number, temperature: number, pressure: number): void {
    this.updated = new Date(); // time.Now()

    // Temperature Conversion
    this.tempC = temperature / 10.0 + TEMP_OFFSET;
    this.tempF = this.tempC * 9.0 / 5.0 + 32.0;

    // Pressure Conversion
    if (pressure <= PRESSURE_OFFSET) {
      this.pressurePsi = 0;
    } else {
      this.pressurePsi = (pressure - PRESSURE_OFFSET) / 10.0;
    }

    // Note: The Go code has a minor error/redundancy here where it calculates
    // PressureKpa twice with two different formulas. We will keep the second one,
    // which seems to be converting PSI to Bar, but calling it Kpa.
    // 1 PSI ≈ 6.894757 kPa. 1 PSI ≈ 0.06894757 Bar.
    this.pressureKpa = this.pressurePsi * 6.894757;
    this.pressureBar = this.pressurePsi * 0.06894757; // More accurate for the second Go line's factor

    // Voltage Conversion
    this.voltage = voltage / 10.0;

    // Battery Percentage
    if (voltage <= BATT_0) {
      this.battery = 0;
    } else if (voltage >= BATT_100) {
      this.battery = 100;
    } else {
      this.battery = (voltage - BATT_0) * 100.0 / (BATT_100 - BATT_0);
    }

    // Inflation State Logic
    if ((state & BIT_FLAT) > 0) {
      this.inflation = InflationState.FLAT;
    } else if ((state & BIT_LOW) > 0) {
      this.inflation = InflationState.LOW;
    } else if ((state & BIT_DECREASING) > 0) {
      this.inflation = InflationState.DECREASING;
    } else if ((state & BIT_RISING) > 0) {
      this.inflation = InflationState.RISING;
    } else {
      this.inflation = InflationState.STABLE;
    }

    // Rotation State Logic
    if ((state & BIT_STILL) > 0) {
      this.rotation = RotationState.STILL;
    } else if ((state & BIT_STARTING) > 0) {
      this.rotation = RotationState.STARTING;
    } else if ((state & BIT_ROLLING) > 0) {
      this.rotation = RotationState.ROLLING;
    } else {
      this.rotation = RotationState.UNKNOWN;
    }

    this.pressureRaw = pressure;
    this.state = state;
  }

  /**
   * Provides a formatted string representation of the tire's current state.
   * (Equivalent to the Go String() method)
   */
  public toString(): string {
    let out = this.position === "??" || !this.position ? `[${this.serial}]: ` : `${this.position}: `;

    // Using template literals for formatting approximation
    out += `Bat: ${this.battery.toFixed(0)}%`;
    out += `, Temp: ${this.tempF.toFixed(1)}°F`;
    out += `, Pres: ${this.pressurePsi.toFixed(1)} PSI (${this.pressureRaw.toFixed(1)})`;
    out += `, Inflation: ${this.inflation.toString().padEnd(10)}`;
    out += `, Rotation: ${this.rotation.toString().padEnd(10)}`;
    out += `, State: ${(this.state >>> 0).toString(2).padStart(8, '0')}`;
    out += `, Age: ${this.ageInSeconds().toFixed(1)}s`;

    return out;
  }
}
