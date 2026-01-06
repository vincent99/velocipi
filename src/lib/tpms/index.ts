import noble, { Peripheral } from '@stoprocent/noble';
import { Tire } from './tire'
import { clear } from '../../util/array';
import { checkCrc } from './crc';
import { logger } from '../../logger';

export type Handler = (tire: Tire, tpms: TPMS) => void;

export class TPMS {
  private tires: Map<string, Tire> = new Map();
  private listeners: Handler[];

  constructor() {
    this.listeners = [];
  }

  private powerOn() {
    return new Promise<void>((resolve, reject) => {
      // Wait for noble to be powered on
      noble.on('stateChange', (state) => {
        if (state === 'poweredOn') {
          resolve();
        } else if (state !== 'unknown' && state !== 'resetting') {
          // Reject on states like 'poweredOff', 'unauthorized', 'unsupported'
          reject(new Error(`Bluetooth adapter state is: ${state}`));
        }
      });

      // Check current state in case it's already poweredOn
      if (noble.state === 'poweredOn') {
        resolve();
      }
    });
  }
  
  public async init() {
    await this.powerOn()
    noble.on('discover', this.onDiscover.bind(this));
    noble.startScanning([], true); // Scan for all services, allow duplicates

    logger.debug("Started scanning for TPMS devices...");
  }

  public close() {
    clear(this.listeners)
    noble.stopScanning();
    noble.removeListener('discover', this.onDiscover.bind(this));
  }

  private getPosition(address: string): string {
    const lowerCaseAddress = address.toLowerCase();
    let position = "??";

    // Mappings from the Go code (using MAC and UUID for different devices/systems)
    switch (lowerCaseAddress) {
      case "4a:a0:00:00:eb:02":
      case "ae3806cb-ea50-2187-4d1d-10010147721a":
        position = "FL";
        break;
      case "4a:85:00:00:3a:50":
      case "bc7ac313-2870-3c1f-c2bc-6047a80b58c2":
        position = "FR";
        break;
      case "4a:88:00:00:72:70":
      case "24237bb2-4496-36b6-a755-64e9de75ac6c":
        position = "RL";
        break;
      case "4a:85:00:00:d7:38":
      case "99633f0c-d627-5f15-7d5d-f171b5a745e7":
        position = "RR";
        break;
    }

    return position;
  }

  /**
   * Handles the 'discover' event from noble (equivalent to the Go scan function).
   * @param peripheral The discovered BLE peripheral.
   */
  private onDiscover(peripheral: Peripheral): void {
    const name = peripheral.advertisement.localName;
    const mfrData = peripheral.advertisement.manufacturerData;

    if (name !== "BR" || !mfrData || mfrData.length !== 7) {
      return;
    }

    const address = peripheral.address.toLowerCase();
    const data = new Uint8Array(mfrData);

    if (!checkCrc(data)) {
      logger.error(`Received data with invalid CRC from ${address}: ${Buffer.from(data).toString('hex')}`);
      return;
    }

    let tire = this.tires.get(address);
    if (!tire) {
      const position = this.getPosition(address);
      tire = new Tire(position, address);
      this.tires.set(address, tire);
      logger.info(`Found Tire (${address}) ${position}`);
    }

    const state = data[2];
    const voltage = data[3];
    const temperature = data[4];
    const pressure = (data[5] << 8) | data[6];

    tire.update(state, voltage, temperature, pressure);

    logger.info(`Updated Tire ${tire.toString()}`);

    for (const handler of this.listeners) {
      handler(tire, this)
    }
  }
}
