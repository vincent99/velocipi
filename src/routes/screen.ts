import { Router } from 'express'
import { logger } from '../logger'
import { Layer } from '../lib/window'

const router = Router()

router.get("/", async (req, res) => {
  const layer = parseInt(`${req.query.layer}`, 10) || Layer._ALL
  res.setHeader('Content-Type', 'image/png')
  if (layer === Layer._ALL) {
    res.end(await res.locals.window.toPng())
  } else {
    res.end(await res.locals.window.getLayerCanvas(layer).toBuffer('png'))
  }
})

router.get('/stream', (req, res) => {
  const boundary = '--pngstream';

  res.setHeader('Cache-Control', 'private, no-cache, no-store, max-age=0')
  res.setHeader('Content-Type', `multipart/x-mixed-replace; boundary="${boundary}"`)
  res.setHeader('Connection', 'close')
  res.setHeader('Pragma', 'no-cache')

  function write(buf: Buffer) {
    res.write(`--${boundary}\r\n`, 'ascii');
    res.write('Content-Type: image/png\r\n');
    res.write(`Content-Length: ${buf.length}\r\n\r\n`, 'ascii');
    res.write(buf, 'binary');
    res.write('\r\n', 'ascii');
  }

  let ended = false

  function end() {
    if (ended) {
      return
    }

    ended = true

    logger.info('Stopped streaming display')
    res.end()
  }

  logger.info('Started streaming display')
  res.locals.window.on('blit', async (num: number) => {
    if (num % 6 !== 0) {
      return
    }

    write(await res.locals.window.toPng())
  })

  req.on('close', end)
  res.on('finish', end);
  res.on('close', end);
  res.on('error', end);
})


export default router
