import { AirSensor } from "../hardware/air-sensor"
import I2C from "../hardware/i2c"
import { LightSensor } from "../hardware/light-sensor"
import OLED from "../hardware/oled"

declare global {
  namespace Express {
    interface Locals {
      disp: OLED
      i2c: I2C
      air: AirSensor
      light: LightSensor
    }
  }
}
