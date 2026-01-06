import { CanvasRenderingContext2D, Window } from "skia-canvas";
import { WindowEvent } from "../lib/oled";

type RenderFn = (ctx: CanvasRenderingContext2D, frame: number) => Promise<void>

export function animate(window: Window, frames: number, fn: RenderFn): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      let first: number
      let cur: number

      function frame(e: WindowEvent) {
        if (!first) {
          first = e.frame
        }
        cur = e.frame - first

        fn(window.ctx, cur)

        if (cur >= frames) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          window.off('frame', frame as any)
          resolve()
        }
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      window.on('frame', frame as any)
    } catch {
      reject()
    }
  })
}
