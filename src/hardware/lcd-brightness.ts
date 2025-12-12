import * as fs from 'fs/promises';
import * as path from 'path';
import LightSensor from './light-sensor'; // Assume lightsensor.ts provides the interface

// --- Constants ---
const DEFAULT_DEVICE = "/sys/class/backlight/10-0045";
const DESIRED_FILE = "brightness";
const MAX_FILE = "max_brightness";
const STEPS = 10; // Number of steps for smooth transition

// --- Types and Interfaces ---

// Handler function signature for listeners
export type Handler = (brightnessController: Brightness, result: Result) => void;

// Configuration for the Brightness controller
export interface Config {
    Device?: string;
    Sensor: LightSensor; // An instance of your LightSensor interface
    Speed?: number; // Ticker interval in milliseconds
    MinBrightness?: number;
    MaxBrightness?: number;
    MinLux?: number; // Minimum lux reading for mapping
    MaxLux?: number; // Maximum lux reading for mapping
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
    private listeners: Handler[] = [];

    private minBrightness: number;
    private maxBrightness: number;
    private minLux: number;
    private maxLux: number;

    private ticker: NodeJS.Timeout | null = null; // Ticker for periodic reading
    private changer: NodeJS.Timeout | null = null; // Ticker for smooth transition
    private speed: number; // Ticker interval in ms
    private current: number = 0; // Current actual brightness setting
    private target: number = 0; // Desired target brightness setting

    private constructor(config: Config, maxBrightnessVal: number) {
        this.device = config.Device || DEFAULT_DEVICE;
        this.sensor = config.Sensor;
        this.speed = config.Speed || 1000;

        // Min/Max Brightness
        this.maxBrightness = maxBrightnessVal;
        this.minBrightness = config.MinBrightness || 1;

        // Min/Max Lux
        this.maxLux = config.MaxLux || 100;
        this.minLux = config.MinLux || 0;
    }

    public static async NewBrightness(opt: Config): Promise<Brightness> {
        let maxBrightness: number;

        const dev = opt.Device || DEFAULT_DEVICE;

        if (opt.MaxBrightness) {
            maxBrightness = opt.MaxBrightness;
        } else {
            try {
                // Read max_brightness from the filesystem
                const filePath = path.join(dev, MAX_FILE);
                const bytes = await fs.readFile(filePath, 'utf8');
                const val = parseInt(bytes.trim(), 10);
                if (isNaN(val)) {
                    throw new Error(`Invalid max_brightness value in ${filePath}`);
                }
                maxBrightness = val;
            } catch (err) {
                // Fallback or rethrow if reading fails
                throw new Error(`Could not read max_brightness: ${err}`);
            }
        }

        const v = new Brightness(opt, maxBrightness);

        await v.Init();
        return v;
    }

    private async Init(): Promise<void> {
        // Set up the main ticker for reading ambient light and setting the target
        this.ticker = setInterval(() => {
            const val = this.Read();
            this.update(val);
        }, this.speed);

        // Read the initial actual brightness level
        try {
            const currentBytes = await fs.readFile(path.join(this.device, DESIRED_FILE), 'utf8');
            this.current = parseInt(currentBytes.trim(), 10);
            this.target = this.current; // Initialize target to current
        } catch (e) {
            console.error("Could not read initial brightness, starting at minBrightness.", e);
            this.current = this.minBrightness;
        }

        // Apply initial configuration
        const initialVal = this.Read();
        await this.set(initialVal.brightness);
    }

    public Read(): Result {
        // In a real TS environment (e.g., Node.js), this must be awaited.
        // For matching the sync Go signature, we assume `GetAmbientLux()` is sync
        // or we handle the promise resolution carefully.
        // Since `GetAmbientLux` in the Go original is not shown, we'll assume
        // a sync call or use a promise if possible. For simplicity here, we assume
        // the light sensor interface handles its own async logic or is mocked.
        // If `GetAmbientLux` is truly async, `Read` must be `async`.

        // Since the Go code's `Read` is NOT async (it handles the error via `_`),
        // we'll assume `GetAmbientLux` is synchronous or returns a default on error.
        const ambient = this.sensor.GetAmbientLux();

        let brightness: number;
        let percent: number;

        if (ambient <= this.minLux) {
            brightness = this.minBrightness;
            percent = 0;
        } else if (ambient >= this.maxLux) {
            brightness = this.maxBrightness;
            percent = 1;
        } else {
            // Linear mapping: (Lux - MinLux) / (MaxLux - MinLux)
            percent = (ambient - this.minLux) / (this.maxLux - this.minLux);
            // Map percentage to brightness range
            brightness = this.minBrightness + Math.round((this.maxBrightness - this.minBrightness) * percent);
        }

        // Clamp to defined min/max brightness
        brightness = Math.max(this.minBrightness, Math.min(this.maxBrightness, brightness));

        return {
            brightness: brightness,
            percent: 100 * percent,
            lux: ambient,
        };
    }

    public Listen(h: Handler): void {
        this.listeners.push(h);
        // Immediately call the handler with the current reading
        const val = this.Read();
        h(this, val);
    }

    public Stop(): void {
        if (this.ticker !== null) {
            clearInterval(this.ticker);
            this.ticker = null;
        }

        if (this.changer !== null) {
            clearInterval(this.changer);
            this.changer = null;
        }

        this.listeners = [];
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
        if (this.changer !== null) {
            clearInterval(this.changer);
            this.changer = null;
        }

        if (step === 0 || this.current === this.target) {
            return;
        }

        // Notify listeners that a target has been set
        for (const handler of this.listeners) {
            handler(this, val);
        }

        // Start the smooth transition ticker
        const intervalMs = Math.floor(this.speed / STEPS);
        this.changer = setInterval(async () => {
            let neu = Math.round(this.current + step);

            // Check if the new value has crossed or reached the target
            const targetReached = (step > 0 && neu >= this.target) || (step < 0 && neu <= this.target);

            if (targetReached) {
                neu = this.target;
                if (this.changer !== null) {
                    clearInterval(this.changer);
                    this.changer = null;
                }
            }

            // Apply the new brightness
            await this.set(neu);
        }, intervalMs);
    }

    private async set(brightness: number): Promise<void> {
        if (brightness < this.minBrightness) {
            brightness = this.minBrightness;
        } else if (brightness > this.maxBrightness) {
            brightness = this.maxBrightness;
        }

        try {
            // Write the new brightness value to the filesystem
            await fs.writeFile(path.join(this.device, DESIRED_FILE), String(brightness), { mode: 0o600 });
            this.current = brightness;
        } catch (e) {
            console.error(`Error setting brightness to ${brightness}:`, e);
        }
    }
}
