console.log('Starting...');

import express, {json, urlencoded} from 'express'
import cors from 'cors'
import { Server as WSS } from 'ws'

import I2C from './hardware/i2c';
import { AirSensor } from './hardware/air-sensor';
import { LightSensor } from './hardware/light-sensor';
import OLED from './hardware/oled';

import { logger } from "./logger"
import config from './config'

import AirRoute from './routes/air'
import OledRoute from './routes/oled';
import LightRoute from './routes/light';


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

process.on('SIGINT', function() {
  logger.debug('Ctrl-C')
  clearInterval(timer)

  server.close(() => {
    console.log('Exiting')
    disp.clearOverlay()
    disp.clear()
    disp.blit()
    disp.close()
    console.log('Exiting for reals')
    process.exit(0)
  })
})


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



const als = bus.wrap(0x48)
const ctx = disp.getContext();

// const overlay = disp.getOverlayContext()
let timer: NodeJS.Timeout

(async function(){
  await bus.waitReady()
  await air.init()
  await light.init()
  await disp.init()

  console.log('ALS connected', await als.isConnected())
  try {
    const d = await als.readRegister(1,6)
    console.log('ALS:', d)
  } catch (e) {
    console.error(e)
  }

  // for ( let i = 0 ; i < 256 ; i++ ){
  //   let color = i.toString(16)
  //   if ( color.length < 2 ) {
  //     color = '0' + color
  //   }

  //   ctx.strokeStyle = `#${color}${color}${color}`
  //   ctx.strokeRect(i, 0, 1, 64)
  // }

  // let i = 0
  timer = setInterval(() => {
    // disp.clearOverlay()
    // overlay.fillStyle=`rgba(255,255,255,1)`
    // overlay.fillRect(i % (256+64) - 64, 16, 64, 32)
    // overlay.fillStyle=`rgba(0,0,0,0.5)`
    // overlay.fillRect(0, 48, 256, 16)
    // i+=2
    // disp.setBrightness(i%256)

    ctx.font = '16px Helvetica'
    ctx.fillStyle = 'rgba(255,0,0,1)'
    ctx.textAlign = 'center'
    ctx.fillText('Hello World', 128, 32, 256)

    ctx.strokeStyle='rgba(255,0,0,1)'
    for ( let x = 0 ; x < 128 ; x += 3 ) {
      for ( let y = 0 ; y < 32 ; y+= 3 ) {
        ctx.rect(x, y, 255-x, 63-y)
        ctx.stroke()
      }
    }

    disp.blit()
  }, 1000/30)

})();
