export interface PanelConfig {
  width: number;
  height: number;
}

export interface NavMenuConfig {
  hideDelay: number; // ms
  cellWidth: number; // px
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
  spiPort: string;
  spiSpeed: string;
  gpioChip: string;
  dcPin: number;
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
  sort?: number;
}

export interface DVRConfig {
  recordingsDir: string;
  segmentDuration: number; // seconds
  snapshotInterval: number; // seconds
  cameras: CameraConfig[];
}

export interface TireAddresses {
  nose: string[];
  left: string[];
  right: string[];
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
}

export interface FullConfigResponse {
  config: FullConfig;
  defaults: FullConfig;
}

export interface PanelMeta {
  name: string;
  icon: string;
  sort?: number;
  headerScreen?: boolean; // default true
}
