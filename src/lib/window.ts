import { Canvas } from "skia-canvas";
// import { millitime } from "../util/time";
import EventEmitter from "events";
import { Page } from "./page";
import { logger } from "../logger";

export enum Layer {
  _ALL,
  MENU,
  ALERT
}

type Blitter = (num: number) => void;

export class Window extends EventEmitter {
  public width: number;
  public height: number;
  public gpu: boolean
  private frameNum: number;
  public fps: number;
  private timer: NodeJS.Timeout;
  public blit: Blitter;

  public canvas: Canvas;
  public page: number;
  public nextPage: number;
  private pages: Page[]
  private overlays: Map<Layer, Canvas>

  constructor(width = 256, height = 64, fps = 60, gpu = true) {
    super()

    this.width = width;
    this.height = height;
    this.fps = fps
    this.gpu = gpu
    this.frameNum = 1;

    this.canvas = new Canvas(this.width, this.height)
    this.canvas.gpu = gpu
    this.ctx.imageSmoothingEnabled = true

    this.page = 0
    this.nextPage = 1
    this.pages = []
    this.overlays = new Map()
  }

  init() {
    clearTimeout(this.timer)

    this.timer = setInterval(() => {
      this.frame()
    }, 1000 / this.fps)
  }

  public get ctx() {
    return this.canvas.getContext('2d')
  }

  public get curPage() {
    return this.pages[ this.page ]
  }

  close() {
    clearInterval(this.timer)
  }

  addPage(page: Page) {
    this.pages[ page.index ] = page
    return page
  }

  private idxOrPage(input: number | Page): number {
    if (typeof input === 'number') {
      return input
    } else {
      const num = this.pages.findIndex((p) => { return p === input })
      if (num > 0) {
        return num
      }
    }

    return 0
  }

  activatePage(input: number | Page) {
    const idx = this.idxOrPage(input)
    this.page = idx
  }

  removePage(input: number | Page) {
    const idx = this.idxOrPage(input)
    if (idx === this.page) {
      this.page = 0
    }
    delete this.pages[ idx ]
  }

  getLayerCanvas(which: Layer) {
    if (which === Layer._ALL) {
      throw new Error("You can't do that")
    }

    let layer = this.overlays.get(which)

    if (!layer) {
      layer = new Canvas(this.width, this.height)
      layer.gpu = false
      this.overlays.set(which, layer)
    }

    return layer
  }

  getLayer(which: Layer) {
    return this.getLayerCanvas(which)?.getContext('2d')
  }

  clearLayer(which: Layer = Layer._ALL) {
    if (which === Layer._ALL) {
      this.overlays.forEach((_, k) => {
        this.clearLayer(k)
      })
    } else {
      const ctx = this.getLayer(which)
      ctx.clearRect(0, 0, this.width, this.height)
    }
  }
  async toPng(): Promise<Buffer> {
    return this.canvas.toBuffer('png')
  }

  private frame() {
    // const start = millitime()

    this.curPage?.frame(this.frameNum)
    // logger.debug(`${this.frameNum} frame render ${millitime(start)}ms`)

    this.flatten()
    // logger.debug(`${this.frameNum} flatten ${millitime(start)}ms`)

    // this.emit('blit', this.frameNum)
    this.blit(this.frameNum)
    // logger.debug(`${this.frameNum} blit ${millitime(start)}ms`)

    this.frameNum++;
  }

  private flatten() {
    const ctx = this.ctx

    // Clear
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, this.width, this.height)

    // Copy the current page
    if (this.curPage) {
      ctx.putImageData(this.curPage.ctx.getImageData(0, 0, this.width, this.height), 0, 0)
    } else {
      logger.warn(`No current page: ${this.page}, ${this.pages}`)
    }

    // Copy overlays
    this.overlays.forEach((l) => {
      ctx.drawImage(l.getContext('2d').getImageData(0, 0, this.width, this.height), 0, 0)
    })
  }
}
