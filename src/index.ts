console.log('Starting...');

import express, { json, urlencoded } from 'express';
import cors from 'cors';
import { Server as WSS } from 'ws';

import { RIO } from 'rpi-io';
import { Window, Layer } from './lib/window';
import I2C from './lib/i2c';
import { AirSensor } from './lib/air-sensor';
import { LightSensor } from './lib/light-sensor';
import { Expander } from './lib/expander';
import OLED from './lib/oled';

import { logger } from './logger';
import config from './config';

import AirRoute from './routes/air';
import ScreenRoute from './routes/screen';
import LightRoute from './routes/light';
import { Startup } from './page/startup';
import { Page } from './lib/page';

process.on('SIGTERM', function () {
  logger.warn('SIGTERM Received');
  exit();
});

process.on('SIGINT', function () {
  logger.debug('SIGINT Received');
  exit();
});

const i2c = new I2C();
const air = new AirSensor(i2c);
const expander = new Expander(i2c);
const light = new LightSensor(i2c);
const window = new Window(256, 64, 30, true);
const disp = new OLED(window.canvas, true);

const port = config.get('port');
const app = express();

app.use(cors({ origin: `http://localhost:${port}` }));
app.use(json());
app.use(urlencoded({ extended: true }));
app.use((_, res, next) => {
  res.locals.window = window;
  res.locals.disp = disp;
  res.locals.i2c = i2c;
  res.locals.air = air;
  res.locals.expander = expander;
  res.locals.light = light;
  next();
});

app.use('/air', AirRoute);
app.use('/light', LightRoute);
app.use('/screen', ScreenRoute);

const server = app
  .listen(port, '0.0.0.0', () => {
    logger.info(`Listening on port ${port}.`);
  })
  .on('error', (err: Error) => {
    logger.emerg(err);
  });

const wss = new WSS({ noServer: true });
wss.on('connection', (socket) => {
  socket.on('message', (message) => {
    logger.debug(`WebSocket: ${message}`);
  });
});

server.on('upgrade', (request, socket, head) => {
  wss.handleUpgrade(request, socket, head, (socket) => {
    wss.emit('connection', socket, request);
  });
});

function exit() {
  logger.info('Cleaning Up…');
  expander.close();
  window.close();
  disp.close();
  RIO.closeAll();
  server.close();
  logger.info('Bye');
  process.nextTick(() => {
    process.exit(0);
  });
}

(async function () {
  await i2c.waitReady();
  await disp.init();
  await air.init();
  await light.init();
  await expander.init(0xffff - 0x4000);

  // TUrn on the LED to show it works
  expander.write(0x4000);

  const startup = new Startup(window);
  window.addPage(startup);
  window.activatePage(startup);
  window.init(expander);
  window.on('blit', (num) => disp.blit(num));
  window.on('keydown', (key) => {
    logger.debug(`Key Down: ${key}`);
  });
  window.on('keyheld', (key) => {
    logger.debug(`Key Held: ${key}`);
  });
  window.on('key', (key, dur) => {
    logger.debug(`Key     : ${key} (${dur})`);
  });
  window.on('keyup', (key) => {
    logger.debug(`Key Up  : ${key}`);
  });
  window.on('knob', (knob, dir) => {
    logger.debug(`Knob: ${knob} -> ${dir}`);
  });

  startup.on('done', () => {
    expander.write(0);
    console.log('Startup done');
    const overlay = window.getLayer(Layer.ALERT);
    const page = new Page(window, 'Gradient');
    window.addPage(page);

    page.frame = function (i: number) {
      // console.log('Page frame', i)

      const ctx = page.ctx;

      for (let j = 0; j < 256; j++) {
        let color = ((j + i) % 256).toString(16);
        if (color.length < 2) {
          color = '0' + color;
        }

        ctx.strokeStyle = `#${color}${color}${color}`;
        ctx.strokeRect(j, 0, 1, 64);
      }

      ctx.font = '32px serif';
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.textAlign = 'center';
      ctx.fillText('Hello World', 128, 32, 256);

      overlay.clearRect(0, 0, 256, 64);
      overlay.fillStyle = `rgba(255,255,255,0.5)`;
      overlay.fillRect((i % (256 + 64)) - 64, 16, 64, 32);
    };

    page.activate();
  });
})();
