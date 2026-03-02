import type { QueueEntryResponse } from './music';

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

export interface KeyEchoMsg {
  type: 'keyEcho';
  eventType: 'keydown' | 'keyup';
  key: LogicalKey;
}

export interface CameraStatusMsg {
  type: 'cameraStatus';
  name: string;
  recording: boolean;
}

export interface RecordingReadyMsg {
  type: 'recordingReady';
  camera: string;
  session: string;
  filename: string;
}

export type DVRRecordingState = 'on' | 'paused' | 'off';

export interface DVRStateMsg {
  type: 'dvrState';
  state: DVRRecordingState;
}

export interface DiskSpaceMsg {
  type: 'diskSpace';
  totalGB: number;
  usedGB: number;
  freeGB: number;
  usedPct: number;
}

export interface LocalCameraMsg {
  type: 'localCamera';
  camera: string;
}

export interface MusicStateMsg {
  type: 'musicState';
  currentSongId: number | null;
  queueIndex: number;
  status: 'playing' | 'paused' | 'stopped';
  shuffle: boolean;
  repeat: 'off' | 'song' | 'queue';
  elapsedSec: number;
  queueLength: number;
}

export interface MusicQueueMsg {
  type: 'musicQueue';
  currentIndex: number;
  entries: QueueEntryResponse[];
}

export type InboundWsMsg =
  | PingMsg
  | AirReadingMsg
  | LuxReadingMsg
  | TpmsMsg
  | LEDStateMsg
  | KeyEventMsg
  | KeyEchoMsg
  | CameraStatusMsg
  | RecordingReadyMsg
  | DVRStateMsg
  | DiskSpaceMsg
  | LocalCameraMsg
  | MusicStateMsg
  | MusicQueueMsg;

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

export interface NavigateMsg {
  type: 'navigate';
  path: string;
}

export interface SetLocalCameraMsg {
  type: 'setLocalCamera';
  camera: string;
}

export interface MusicControlMsg {
  type: 'musicControl';
  action:
    | 'play'
    | 'pause'
    | 'stop'
    | 'next'
    | 'prev'
    | 'seek'
    | 'skipForward'
    | 'skipBack'
    | 'setVolume'
    | 'setShuffle'
    | 'setRepeat'
    | 'jumpToIndex';
  value?: number; // seek: absolute seconds; skipForward/skipBack: delta seconds; setVolume: 0-100
  str?: string; // setRepeat: 'off'|'song'|'queue'; setShuffle: 'true'|'false'
}

export type OutboundWsMsg =
  | ReloadMsg
  | KeyMsg
  | LEDControlMsg
  | NavigateMsg
  | SetLocalCameraMsg
  | MusicControlMsg;
