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

export interface Config {
  tail: string;
  headerColor: string;
  panel: PanelConfig;
  navMenu: NavMenuConfig;
  keyMap: KeyMapConfig;
}

export interface PanelMeta {
  name: string;
  icon: string;
  sort?: number;
  headerScreen?: boolean; // default true
}
