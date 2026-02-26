export type TimeFormat = string;

export interface PanelConfig {
  width: number;
  height: number;
  controlBackground: string;
  controlBorder: string;
  controlText: string;
  selectedBackground: string;
  selectedBorder: string;
  selectedText: string;
  activeBackground: string;
  activeBorder: string;
  activeText: string;
  homeTimezone: string;
  timeFormat: TimeFormat;
}

export interface NavMenuConfig {
  hideDelay: number; // ms
  cellWidth: number; // px
  longPressMs: number; // ms to hold enter before it counts as a long press (cancel)
}

export interface KeyMapConfig {
  up: string;
  down: string;
  left: string;
  right: string;
  enter: string;
  joyLeft: string;
  joyRight: string;
  innerLeft: string;
  innerRight: string;
  outerLeft: string;
  outerRight: string;
}

// UIConfig — subset served by GET /config (no ?full=true)
export interface Config {
  tail: string;
  headerColor: string;
  adminHeaderColor: string;
  panel: PanelConfig;
  navMenu: NavMenuConfig;
  keyMap: KeyMapConfig;
}

// Full config — served by GET /config?full=true and accepted by POST /config
export interface SensorConfig {
  address: number;
  interval: string;
}

export interface ExpanderBits {
  knobCenter: number;
  knobInner: number;
  knobOuter: number;
  led: number;
  joyCenter: number;
  joyDown: number;
  joyUp: number;
  joyRight: number;
  joyLeft: number;
  joyKnob: number;
}

export interface ExpanderConfig {
  address: number;
  interval: string;
  bits: ExpanderBits;
}

export interface OLEDConfig {
  driver: string; // "ssd1327" or "ge256x64b"
  spiPort: string;
  spiSpeed: string;
  gpioChip: string;
  statusPin: number;
  resetPin: number;
  flip: boolean;
}

export interface ScreenConfig {
  splashImage: string;
  splashDuration: string;
  fps: number;
}

export interface CameraConfig {
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  audio: boolean;
  record?: boolean;
  sort?: number;
}

export interface DVRConfig {
  recordingsDir: string;
  segmentDuration: number; // seconds
  thumbnailHeight: number;
  cameras: CameraConfig[];
}

export interface TireAddresses {
  nose: string[];
  left: string[];
  right: string[];
}

export interface MusicConfig {
  musicDir: string;
  volume: number;
  albumRequiredPercent: number;
  minDbVersion: number;
  maxBitrate: number; // kbps; 0 = no limit
  transcodeFormat: string; // e.g. "aac", "mp3"
  playedRequiredPercent: number; // % elapsed before a skip counts as a play
}

export interface FullConfig {
  addr: string;
  appUrl: string;
  i2cDevice: string;
  pingInterval: string;
  airSensor: SensorConfig;
  dvr: DVRConfig;
  expander: ExpanderConfig;
  lightSensor: SensorConfig;
  oled: OLEDConfig;
  screen: ScreenConfig;
  tires: TireAddresses;
  ui: Config;
  music: MusicConfig;
}

export interface FullConfigResponse {
  config: FullConfig;
  defaults: FullConfig;
}

export interface PanelMeta {
  name: string;
  icon: string;
  iconStyle?: string; // uicons style prefix: 'sr' (default), 'rr', 'ss', 'rs', 'br', 'bs', etc.
  sort?: number;
  headerScreen?: boolean; // default true
  admin?: boolean; // if true, only shown when admin cookie is present
}
