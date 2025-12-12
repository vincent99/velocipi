console.log('Starting...');

import express, {json, urlencoded} from 'express'
import cors from 'cors'
import { Server as WSS } from 'ws'

import { RIO } from 'rpi-io';
import I2C from './hardware/i2c';
import { AirSensor } from './hardware/air-sensor';
import { LightSensor } from './hardware/light-sensor';
import OLED from './hardware/oled';

import { logger } from "./logger"
import config from './config'

import AirRoute from './routes/air'
import OledRoute from './routes/oled';
import LightRoute from './routes/light';

process.on('SIGTERM', function() {
  logger.warn('SIGTERM Received')
  exit()
})

process.on('SIGINT', function() {
  logger.debug('SIGINT Received')
  exit()
})

const bus = new I2C();
const air = new AirSensor(bus)
const light = new LightSensor(bus)
const disp = new OLED(256, 64, true)

const port = config.get('port')
const app = express()

app.use(cors({origin: `http://localhost:${port}`}))
app.use(json());
app.use(urlencoded({ extended: true }));
app.use((_, res, next) => {
  res.locals.disp = disp
  res.locals.i2c = bus
  res.locals.air = air
  res.locals.light = light
  next()
})

app.use('/air', AirRoute)
app.use('/light', LightRoute)
app.use('/oled', OledRoute)

const server = app.listen(port, "0.0.0.0", () => {
  logger.info(`Listening on port ${port}.`);
}).on("error", (err: any) => {
  if (err.code === "EADDRINUSE") {
    logger.emerg("Error: address already in use");
  } else {
    logger.emerg(err);
  }
});

const wss = new WSS({ noServer: true });
wss.on('connection', socket => {
  socket.on('message', (message) => {
    logger.debug(`WebSocket: ${message}`)
  });
});

server.on('upgrade', (request, socket, head) => {
  wss.handleUpgrade(request, socket, head, socket => {
    wss.emit('connection', socket, request);
  });
});

function exit() {
  clearInterval(timer)

  server.close(() => {
    logger.info('Cleaning Up…')
    disp.clearOverlay()
    disp.clear()
    disp.blit()
    disp.close()
    RIO.closeAll()
    logger.info('Bye')
    process.exit(0)
  })
}

// import chromedriver from 'chromedriver'
// import {Builder, Browser} from 'selenium-webdriver'
// import {Options} from 'selenium-webdriver/chrome'

// (async function() {
//   console.log('Using ChromeDriver', chromedriver.path)
  
//   const builder = new Builder().forBrowser(Browser.CHROME)
//   const opt = new Options()
//   opt.setBinaryPath('/home/vincent/dev/velocipi/node_modules/chromedriver/lib/chromedriver/chromedriver')
//   builder.setChromeOptions(opt)
//   const driver = builder.build()
//   console.log('Built driver', driver)

//   await driver.get('https://apple.com')
//   const shot = await driver.takeScreenshot()
//   writeFileSync('browser.png', shot)
//   console.log(shot)
// })();



const ctx = disp.getContext();
const overlay = disp.getOverlayContext()
let timer: NodeJS.Timeout

(async function(){
  await bus.waitReady()
  await air.init()
  await light.init()
  await disp.init()

  for ( let i = 0 ; i < 256 ; i++ ){
    let color = i.toString(16)
    if ( color.length < 2 ) {
      color = '0' + color
    }

    ctx.strokeStyle = `#${color}${color}${color}`
    ctx.strokeRect(i, 0, 1, 64)
  }

  let i = 0
  timer = setInterval(() => {
    ctx.clearRect(0,0,256,64)
    for ( let j = 0 ; j < 256 ; j++ ){

      let color = ((j+i)%256).toString(16)
      if ( color.length < 2 ) {
        color = '0' + color
      }

      ctx.strokeStyle = `#${color}${color}${color}`
      ctx.strokeRect(j, 0, 1, 64)
    }

    disp.clearOverlay()

    ctx.font = '32px serif'
    ctx.fillStyle = 'rgba(255,255,255,0.5)'
    ctx.textAlign = 'center'
    ctx.fillText('Hello World', 128, 32, 256)

    overlay.fillStyle=`rgba(255,255,255,0.5)`
    overlay.fillRect(i % (256+64) - 64, 16, 64, 32)
    i+=2
    // disp.setBrightness(i%256)

    // ctx.strokeStyle='rgba(255,0,0,1)'
    // for ( let x = 0 ; x < 128 ; x += 3 ) {
    //   for ( let y = 0 ; y < 32 ; y+= 3 ) {
    //     ctx.rect(x, y, 255- (2*x), 63-(2*y))
    //     ctx.stroke()
    //   }
    // }

    disp.blit()
  }, 1000/60)

})();
