export interface Song {
  id: number;
  path: string;
  hash: string;
  coverId: number | null;
  added: string;
  updated: string;
  deleted: string | null;
  marked: boolean;
  favorite: boolean;
  artist: string;
  album: string;
  artistSort: string;
  albumSort: string;
  title: string;
  discNumber: number;
  trackNumber: number;
  trackTotal: number;
  genre: string[];
  length: number; // seconds
  year: number;
  plays: number;
  format: string; // e.g. "mp3", "flac"
  bitrate: number; // kbps
}

export interface Album {
  artist: string;
  artistSort: string;
  album: string;
  albumSort: string;
  coverId: number | null;
  year: number;
  trackCount: number;
}

export interface Artist {
  artist: string;
  artistSort: string;
  albumCount: number;
  trackCount: number;
}

export interface Genre {
  genre: string;
  trackCount: number;
}

export interface Decade {
  decade: number;
  trackCount: number;
}

export interface Playlist {
  id: number;
  name: string;
  items: number[];
}

export interface SmartSearch {
  id: number;
  name: string;
  query: string;
}

export interface SongsResponse {
  songs: Song[];
  total: number;
}

export interface LyricLine {
  timeSec: number;
  text: string;
}

export interface LyricsResponse {
  lines: LyricLine[];
}

export interface QueueEntryResponse {
  songId: number;
  song: Song | null;
  originalIndex: number;
}

export interface QueueResponse {
  currentIndex: number;
  entries: QueueEntryResponse[];
}
