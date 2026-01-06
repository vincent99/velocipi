import { writeFile } from 'fs/promises';
import * as path from 'path';
import { LightSensor } from './light-sensor'; // Assume lightsensor.ts provides the interface
import { readFileSync } from 'fs';
import { clear, removeObject } from '../util/array';

// --- Constants ---
const DEFAULT_DEVICE = "/sys/class/backlight/10-0045";
const DESIRED_FILE = "brightness";
const MAX_FILE = "max_brightness";
const STEPS = 10; // Number of steps for smooth transition

// --- Types and Interfaces ---

export type Handler = (result: Result, controller: Brightness) => void;

// Configuration for the Brightness controller
export interface Config {
  device: string;
  speed: number; // Ticker interval in milliseconds
  minBrightness: number;
  maxBrightness: number;
  minLux: number; // Minimum lux reading for mapping
  maxLux: number; // Maximum lux reading for mapping
}

const defaultConfig: Config = {
  device: DEFAULT_DEVICE,
  speed: 1000,
  maxBrightness: 0,
  minBrightness: 1,
  maxLux: 100,
  minLux: 1
}

// Result structure for reading and listener callback
export interface Result {
  brightness: number;
  percent: number; // 0-100%
  lux: number;
}

// --- Main Class ---

export class Brightness {
  private device: string;
  private sensor: LightSensor;
  private config: Config;
  private listeners: Handler[] = [];

  private ticker: NodeJS.Timeout; // Ticker for periodic reading
  private changer: NodeJS.Timeout; // Ticker for smooth transition
  private current: number = 0; // Current actual brightness setting
  private target: number = 0; // Desired target brightness setting

  private constructor(sensor: LightSensor, config?: Partial<Config>) {
    this.config = {...defaultConfig, ...config}
    this.sensor = sensor

    if (!this.config.maxBrightness) {
      this.config.maxBrightness = this.readCurrent(MAX_FILE)
    }
  }

  private readCurrent(file: string): number {
    const filePath = path.join(this.config.device, file);

    try {
      // Read max_brightness from the filesystem
      const bytes = readFileSync(filePath, 'utf8');
      const val = parseInt(bytes.trim(), 10);

      if (isNaN(val) || val <= 0) {
        throw new Error(`Invalid brightness value in ${filePath}`);
      }

      return val
    } catch (err) {
      // Fallback or rethrow if reading fails
      throw new Error(`Could not read brightness from ${filePath}: ${err}`);
    }
  }

  public async init() {
    // Set up the main ticker for reading ambient light and setting the target
    this.ticker = setInterval(async () => {
      const val = await this.read();
      this.update(val);
    }, this.config.speed);

    this.current = this.readCurrent(DESIRED_FILE)

    return this.set((await this.read()).brightness);
  }

  public close() {
    clearInterval(this.ticker)
    clearInterval(this.changer);
    clear(this.listeners)
  }

  public async read(): Promise<Result> {
    const ambient = await this.sensor.getAmbientLux();

    let brightness: number;
    let percent: number;

    if (ambient <= this.config.minLux) {
      brightness = this.config.minBrightness;
      percent = 0;
    } else if (ambient >= this.config.maxLux) {
      brightness = this.config.maxBrightness;
      percent = 1;
    } else {
      // Linear mapping: (Lux - MinLux) / (MaxLux - MinLux)
      percent = (ambient - this.config.minLux) / (this.config.maxLux - this.config.minLux);
      // Map percentage to brightness range
      brightness = this.config.minBrightness + Math.round((this.config.maxBrightness - this.config.minBrightness) * percent);
    }

    // Clamp to defined min/max brightness
    brightness = Math.max(this.config.minBrightness, Math.min(this.config.maxBrightness, brightness));

    return {
      brightness: brightness,
      percent: 100 * percent,
      lux: ambient,
    };
  }

  public async listen(h: Handler) {
    this.listeners.push(h);

    // Immediately call the handler with the current reading
    const val = await this.read();

    h(val, this);

    return () => {
      removeObject(this.listeners, h)
    }
  }

  private update(val: Result): void {
    if (this.target === val.brightness) {
      return;
    }

    this.target = val.brightness;

    // Calculate step size for smooth transition
    let step = (val.brightness - this.current) / STEPS;

    // Use Math.ceil/floor to ensure the step size is always at least 1 (or -1)
    if (step > 0) {
      step = Math.ceil(step);
    } else if (step < 0) {
      step = Math.floor(step);
    }

    // Stop any existing transition
    clearInterval(this.changer);

    if (step === 0 || this.current === this.target) {
      return;
    }

    // Notify listeners that a target has been set
    for (const handler of this.listeners) {
      handler(val, this)
    }

    // Start the smooth transition ticker
    const intervalMs = Math.floor(this.config.speed / STEPS);
    this.changer = setInterval(async () => {
      let neu = Math.round(this.current + step);

      // Check if the new value has crossed or reached the target
      const targetReached = (step > 0 && neu >= this.target) || (step < 0 && neu <= this.target);

      if (targetReached) {
        neu = this.target;
        clearInterval(this.changer);
      }

      // Apply the new brightness
      await this.set(neu);
    }, intervalMs);
  }

  private async set(brightness: number): Promise<void> {
    if (brightness < this.config.minBrightness) {
      brightness = this.config.minBrightness;
    } else if (brightness > this.config.maxBrightness) {
      brightness = this.config.maxBrightness;
    }

    try {
      // Write the new brightness value to the filesystem
      await writeFile(path.join(this.device, DESIRED_FILE), String(brightness), { mode: 0o600 });
      this.current = brightness;
    } catch (e) {
      console.error(`Error setting brightness to ${brightness}:`, e);
    }
  }
}
