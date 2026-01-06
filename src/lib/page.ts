import { Canvas } from "skia-canvas"
import { Window } from "./window"
import EventEmitter from "events"

export class Page extends EventEmitter {
  window: Window
  name: string
  index: number
  canvas: Canvas

  constructor(window: Window, name: string) {
    super()

    this.name = name
    this.window = window
    this.index = window.nextPage++
    this.canvas = new Canvas(window.width, window.height)
    this.canvas.gpu = window.gpu
  }

  public get ctx() {
    return this.canvas.getContext('2d')
  }

  public activate() {
    this.window.page = this.index
  }

  public clear() {
    this.ctx.clearRect(0, 0, this.window.width, this.window.height)
  }

  public frame(num: number) {
    console.log('Render your frame here', num)
  }
}
