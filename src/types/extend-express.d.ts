import { AirSensor } from "../lib/air-sensor"
import { Expander } from "../lib/expander"
import I2C from "../lib/i2c"
import { LightSensor } from "../lib/light-sensor"
import OLED from "../lib/oled"
import { Window } from "../lib/window"

declare global {
  namespace Express {
    interface Locals {
      window: Window
      disp: OLED
      expander: Expander
      i2c: I2C
      air: AirSensor
      light: LightSensor
    }
  }
}
