export interface NavMenuConfig {
  hideDelay: number; // ms
  cellWidth: number; // px
}

export interface Config {
  tail: string;
  navMenu: NavMenuConfig;
}

export interface PanelMeta {
  name: string;
  icon: string;
  sort?: number;
}
