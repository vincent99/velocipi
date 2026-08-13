// Mirrors the Go types in internal/transcript and internal/session.

export interface GPSFix {
  time: string;
  lat: number;
  lon: number;
  alt_ft: number;
  heading_deg: number;
  groundspeed_kt: number;
  fix_quality: number;
  valid: boolean;
}

export interface WordToken {
  word: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
}

export interface TransmissionRecord {
  id: string;
  session_id: string;
  start_time: string;
  end_time: string;
  duration_ms: number;
  audio_file: string;
  transcript: string;
  words: WordToken[] | null;
  gps_start: GPSFix;
  gps_end: GPSFix;
  confidence: number;
  direction: string; // "rx" | "tx" | "unknown"
  channel?: string; // "mono" | "com1" | "com2" | stream name
  model_used: string;
  correction?: string;
  corrected_at?: string;
  reviewed?: boolean;
  reviewed_at?: string;
}

export interface SessionManifest {
  session_id: string;
  start_time: string;
  aircraft: string;
  audio_device: string;
  model: string;
  storage_root: string;
  live: boolean;
}
