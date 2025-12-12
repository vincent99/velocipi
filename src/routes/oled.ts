import {Router} from 'express'
import { logger } from '../logger'

const router = Router()

router.get("/", (req, res) => {
  const scale = parseInt(`${req.query.scale}`, 10) || 1

  res.setHeader('Content-Type', 'image/png')
  res.end(res.locals.disp.toPng(scale))
})

router.get('/stream', (req, res) => {
  let timer: NodeJS.Timeout
  const scale = parseInt(`${req.query.scale}`, 10) || 1
  const rate = parseInt(`${req.query.rate}`, 10) || 10
  const boundary = '--pngstream';

    res.setHeader('Cache-Control', 'private, no-cache, no-store, max-age=0')
    res.setHeader('Content-Type',`multipart/x-mixed-replace; boundary="${boundary}"`)
    res.setHeader('Connection','close')
    res.setHeader('Pragma','no-cache')

    function write(buf: Buffer) {
      res.write(`--${boundary}\r\n`, 'ascii');
      res.write('Content-Type: image/png\r\n');
      res.write(`Content-Length: ${buf.length}\r\n\r\n`, 'ascii');
      res.write(buf, 'binary');
      res.write('\r\n', 'ascii');
    }

    let ended = false

    function end() {
      if (ended ) {
        return
      }

      ended = true

      logger.info('Stopped streaming display')
      res.end()
      clearTimeout(timer)
    }

    logger.info('Started streaming display')
    timer = setInterval(() => {
      write(res.locals.disp.toPng(scale))
    }, 1000/Math.max(1, rate))

    req.on('close', end)
    res.on('finish', end);
    res.on('close', end);
    res.on('error', end);
})


export default router
