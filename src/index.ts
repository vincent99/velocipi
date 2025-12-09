console.log('Starting...');

import express, {json, urlencoded} from 'express'
import cors from 'cors'
import { Server as WSS } from 'ws'
import { logger } from "./logger"
import i2c from './hardware/i2c';
import oled from './hardware/oled';

import config from './config'

const port = config.get('port')
const app = express();

app.use(cors({
  origin: `http://localhost:${port}`
}))
app.use(json());
app.use(urlencoded({ extended: true }));

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



const bus = new i2c();
const als = bus.wrap(0x48)
const disp = new oled(256, 64, true)
const ctx = disp.getContext()
const overlay = disp.getOverlayContext()
let timer: NodeJS.Timeout

(async function(){
  await disp.init()
  // disp.setProfile(true)

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
    disp.clearOverlay()
    overlay.fillStyle=`rgba(255,255,255,1)`
    overlay.fillRect(i % (256+64) - 64, 16, 64, 32)
    overlay.fillStyle=`rgba(0,0,0,0.5)`
    overlay.fillRect(0, 48, 256, 16)
    i+=2
    // disp.setBrightness(i%256)
    disp.blit()
  }, 1000/30)

})();

(async function(){
  await bus.waitReady()

  console.log('ALS connected', await als.isConnected())
  try {
    const d = await als.readRegister(1,6)
    console.log('ALS:', d)
  } catch (e) {
    console.error(e)
  }
})();
