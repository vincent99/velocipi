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

export interface StorageConfig {
  dvr: string;
  music: string;
  backup: string;
  snaps: string;
}

export interface CameraConfig {
  name: string;
  driver: string; // "rtsp" (default/empty) or "siyi"
  host: string;
  port: number;
  username: string;
  password: string;
  audio: boolean;
  record?: boolean;
  sort?: number;
  siyiAIHost: string; // IP of AI tracking module; empty = disabled
}

export interface DVRConfig {
  segmentDuration: number; // seconds
  thumbnailHeight: number;
  record: boolean; // enable recording on startup
  minFreeDisk: number; // minimum free disk space in GB; 0 = disabled
  diskSpacePoll: string; // poll interval, e.g. "1m"
  cameras: CameraConfig[];
}

export interface TireAddresses {
  nose: string[];
  left: string[];
  right: string[];
}

export interface MusicConfig {
  volume: number;
  audioDevice: string; // mpv --audio-device value; "auto" = let mpv choose
  albumRequiredPercent: number;
  minDbVersion: number;
  maxBitrate: number; // kbps; 0 = no limit
  transcodeFormat: string; // e.g. "aac", "mp3"
  playedRequiredPercent: number; // % elapsed before a skip counts as a play
  acoustidKey: string; // AcoustID API key (register free at acoustid.org)
  acoustidMinScore: number; // minimum AcoustID match score (0.0–1.0) to accept a result
}

export interface FullConfig {
  addr: string;
  appUrl: string;
  i2cDevice: string;
  spiDevice: string;
  pingInterval: string;
  storage: StorageConfig;
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
