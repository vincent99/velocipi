// Outbound messages (server → client, received on /ws)

export interface PingMsg {
  type: 'ping';
  time: string;
}

export interface AirReading {
  tempC: number;
  tempF: number;
  pressureInches: number;
  pressureMeters: number;
  pressureFeet: number;
  humidity: number;
  dewpointC: number;
  dewpointF: number;
}

export interface AirReadingMsg {
  type: 'airReading';
  reading: AirReading;
}

export interface LuxReadingMsg {
  type: 'luxReading';
  lux: number;
}

export type InflationState =
  | 'normal'
  | 'low'
  | 'flat'
  | 'decreasing'
  | 'increasing';
export type RotationState = 'still' | 'starting' | 'rolling';

export interface Tire {
  position: string;
  serial: string;
  updated: string;
  tempC: number;
  tempF: number;
  pressureRaw: number;
  pressureKpa: number;
  pressureBar: number;
  pressurePsi: number;
  voltage: number;
  battery: number;
  inflation: InflationState;
  rotation: RotationState;
  state: number;
}

export interface TpmsMsg {
  type: 'tpms';
  tire: Tire;
}

export type LEDMode = 'off' | 'on' | 'blink';

export interface LEDStateMsg {
  type: 'ledState';
  mode: LEDMode;
  rate?: number;
}

export type LogicalKey =
  | 'up'
  | 'down'
  | 'left'
  | 'right'
  | 'enter'
  | 'joy-left'
  | 'joy-right'
  | 'inner-left'
  | 'inner-right'
  | 'outer-left'
  | 'outer-right';

export interface KeyEventMsg {
  type: 'key';
  eventType: 'keydown' | 'keyup';
  key: LogicalKey;
}

export type InboundWsMsg =
  | PingMsg
  | AirReadingMsg
  | LuxReadingMsg
  | TpmsMsg
  | LEDStateMsg
  | KeyEventMsg;

// Outbound messages (client → server, sent on /ws)

export interface ReloadMsg {
  type: 'reload';
}

export interface KeyMsg {
  type: 'key';
  eventType: 'keydown' | 'keyup';
  key: LogicalKey;
}

export interface LEDControlMsg {
  type: 'led';
  state: LEDMode;
  rate?: number;
}

export type OutboundWsMsg = ReloadMsg | KeyMsg | LEDControlMsg;
