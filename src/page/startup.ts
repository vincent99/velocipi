import { Image } from "skia-canvas";
import { Page } from "../lib/page";
import { Window } from "../lib/window";
import { readFileSync } from "fs";
import { logger } from "../logger";

const len = 60

export class Startup extends Page {
  logo: Image
  frames: number

  constructor(window: Window) {
    super(window, 'Startup')

    const img = readFileSync('./src/images/logo.svg')
    this.logo = new Image(img)

    window.activatePage(this)
  }

  public frame(num: number): void {
    this.clear()

    if (num > 2 * len) {
      logger.debug('Startup done')
      this.window.removePage(this)
      this.emit('done')
    } else if (num < len) {
      this.ctx.filter = `blur(${len - num}px)`
      this.ctx.drawImage(this.logo, 0, 0)
      this.ctx.filter = `blur(0)`
    } else {
      this.ctx.drawImage(this.logo, 0, 0)
    }
  }
}
