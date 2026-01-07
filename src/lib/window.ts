import { Canvas } from 'skia-canvas';
// import { millitime } from "../util/time";
import EventEmitter from 'events';
import { Page } from './page';
import { logger } from '../logger';
import { Expander } from './expander';
import debounce from 'p-debounce';

export enum Layer {
  _ALL,
  MENU,
  ALERT,
}

export enum Key {
  Left = 'left',
  Right = 'right',
  Up = 'up',
  Down = 'down',
  Knob = 'knob',
}

export enum Knob {
  Joy = 'joy',
  Outer = 'outer',
  Inner = 'inner',
}

enum KeyState {
  Up = 'up',
  Down = 'down',
  Held = 'held',
}

interface KeyMapping {
  key: Key;
  bits: number; // All of these bits must be 1 for a key to be down
  state?: KeyState;
  timer?: NodeJS.Timeout;
}

enum KnobState {
  None = 'none',
  Left = 'left',
  Right = 'right',
}

interface KnobMapping {
  knob: Knob;
  shift: number; // How many bits to shift-right to get the 2 bits to be the first 2
  state?: KnobState;
  lastClock?: number;
  timer?: NodeJS.Timeout;
}

const keyMap: KeyMapping[] = [
  { key: Key.Left, bits: 0b00010001 << 8 },
  { key: Key.Right, bits: 0b00001001 << 8 },
  { key: Key.Up, bits: 0b00000101 << 8 },
  { key: Key.Down, bits: 0b00000011 << 8 },
  { key: Key.Knob, bits: 0b00000001 },
];

const knobMap: KnobMapping[] = [
  { knob: Knob.Joy, shift: 13 },
  { knob: Knob.Outer, shift: 3 },
  { knob: Knob.Inner, shift: 1 },
];

const DEBOUNCE_KEY = 25;
const DEBOUNCE_KNOB = 100;
const HOLD = 333;

//eslint-disable-next-line @typescript-eslint/no-unsafe-declaration-merging
export declare interface Window {
  on(event: 'blit', listener: (frameNo: number) => void): this;

  on(event: 'keydown', listener: (which: Key) => void): this;
  on(event: 'keyheld', listener: (which: Key) => void): this;
  on(event: 'keyup', listener: (which: Key) => void): this;
  on(
    event: 'key',
    listener: (which: Key, duration: 'short' | 'long') => void
  ): this;
  on(
    event: 'knob',
    listener: (which: Knob, direction: 'left' | 'right') => void
  ): this;
}

//eslint-disable-next-line @typescript-eslint/no-unsafe-declaration-merging
export class Window extends EventEmitter {
  public width: number;
  public height: number;
  public gpu: boolean;
  private frameNum: number;
  public fps: number;
  private frameTimer: NodeJS.Timeout;

  public canvas: Canvas;
  public page: number;
  public nextPage: number;
  private pages: Page[];
  private overlays: Map<Layer, Canvas>;

  private debouncedKey: (m: KeyMapping, dir: 'down' | 'up') => void;

  constructor(width = 256, height = 64, fps = 60, gpu = true) {
    super();

    this.width = width;
    this.height = height;
    this.fps = fps;
    this.gpu = gpu;
    this.frameNum = 1;

    this.canvas = new Canvas(this.width, this.height);
    this.canvas.gpu = gpu;
    this.ctx.imageSmoothingEnabled = true;

    this.page = 0;
    this.nextPage = 1;
    this.pages = [];
    this.overlays = new Map();

    this.debouncedKey = debounce(this.keyEvent, DEBOUNCE_KEY);
  }

  init(expander: Expander) {
    expander.on('change', this.expanderChanged.bind(this));
    for (const m of keyMap) {
      m.state = KeyState.Up;
    }

    for (const m of knobMap) {
      m.state = KnobState.None;
    }

    clearTimeout(this.frameTimer);

    this.frameTimer = setInterval(() => {
      this.frame();
    }, 1000 / this.fps);
  }

  private expanderChanged(neu: number, old: number) {
    const diff = neu ^ old;

    for (const m of keyMap) {
      if ((diff & m.bits) === 0) {
        continue;
      }

      if ((neu & m.bits) === m.bits && m.state === 'up') {
        this.debouncedKey(m, 'down');
      } else if ((neu & m.bits) !== m.bits && m.state !== 'up') {
        this.debouncedKey(m, 'up');
      }
    }

    for (const m of knobMap) {
      const knobDiff = (diff >> m.shift) & 0b11;
      if (knobDiff === 0) {
        continue;
      }

      this.knobEvent(m, (neu >> m.shift) & 0b11);
    }
  }

  private keyEvent(m: KeyMapping, dir: 'up' | 'down') {
    if (dir === 'down' && m.state === KeyState.Up) {
      clearTimeout(m.timer);
      m.state = KeyState.Down;
      this.emit('keydown', m.key);
      this.curPage?.onKeyDown(m.key);

      m.timer = setTimeout(() => {
        m.state = KeyState.Held;
        this.emit('keyheld', m.key);
        this.curPage?.onKeyHeld(m.key);
      }, HOLD);
    } else if (dir === 'up' && m.state !== 'up') {
      const len = m.state === KeyState.Held ? 'long' : 'short';

      clearTimeout(m.timer);
      this.emit('keyup', m.key);
      this.curPage?.onKeyUp(m.key);

      this.emit('key', m.key, len);
      this.curPage?.onKey(m.key, len);

      m.state = KeyState.Up;
    }
  }

  private knobEvent(m: KnobMapping, neu: number) {
    const clk = neu & 1;
    const dir = (neu >> 1) & 1;
    let state = KnobState.None;

    if (clk != m.lastClock) {
      // If spinning rapidly, ignore what direction the signal says
      // and just keep going the way we were going, because sometimes
      // a pluse is missed and the next is read backwards
      if (m.state && m.state !== KnobState.None) {
        state = m.state;
      } else if (clk === dir) {
        state = KnobState.Left;
      } else {
        state = KnobState.Right;
      }

      m.state = state;
      this.emit('knob', m.knob, state);
      this.curPage?.onKnob(m.knob, state);
    }

    m.lastClock = clk;
    clearTimeout(m.timer);

    m.timer = setTimeout(() => {
      clearTimeout(m.timer);
      m.state = KnobState.None;
    }, DEBOUNCE_KNOB);
  }

  public get ctx() {
    return this.canvas.getContext('2d');
  }

  public get curPage() {
    return this.pages[this.page];
  }

  close() {
    clearInterval(this.frameTimer);
  }

  addPage(page: Page) {
    this.pages[page.index] = page;
    return page;
  }

  private idxOrPage(input: number | Page): number {
    if (typeof input === 'number') {
      return input;
    } else {
      const num = this.pages.findIndex((p) => {
        return p === input;
      });
      if (num > 0) {
        return num;
      }
    }

    return 0;
  }

  activatePage(input: number | Page) {
    const idx = this.idxOrPage(input);
    this.page = idx;
  }

  removePage(input: number | Page) {
    const idx = this.idxOrPage(input);
    if (idx === this.page) {
      this.page = 0;
    }
    delete this.pages[idx];
  }

  getLayerCanvas(which: Layer) {
    if (which === Layer._ALL) {
      throw new Error("You can't do that");
    }

    let layer = this.overlays.get(which);

    if (!layer) {
      layer = new Canvas(this.width, this.height);
      layer.gpu = false;
      this.overlays.set(which, layer);
    }

    return layer;
  }

  getLayer(which: Layer) {
    return this.getLayerCanvas(which)?.getContext('2d');
  }

  clearLayer(which: Layer = Layer._ALL) {
    if (which === Layer._ALL) {
      this.overlays.forEach((_, k) => {
        this.clearLayer(k);
      });
    } else {
      const ctx = this.getLayer(which);
      ctx.clearRect(0, 0, this.width, this.height);
    }
  }
  async toPng(): Promise<Buffer> {
    return this.canvas.toBuffer('png');
  }

  private frame() {
    // const start = millitime()

    this.curPage?.frame(this.frameNum);
    // logger.debug(`${this.frameNum} frame render ${millitime(start)}ms`)

    this.flatten();
    // logger.debug(`${this.frameNum} flatten ${millitime(start)}ms`)

    this.emit('blit', this.frameNum);
    // logger.debug(`${this.frameNum} blit ${millitime(start)}ms`)

    this.frameNum++;
  }

  private flatten() {
    const ctx = this.ctx;

    // Clear
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, this.width, this.height);

    // Copy the current page
    if (this.curPage) {
      ctx.putImageData(
        this.curPage.ctx.getImageData(0, 0, this.width, this.height),
        0,
        0
      );
    } else {
      logger.warn(`No current page: ${this.page}, ${this.pages}`);
    }

    // Copy overlays
    this.overlays.forEach((l) => {
      ctx.drawImage(
        l.getContext('2d').getImageData(0, 0, this.width, this.height),
        0,
        0
      );
    });
  }
}
