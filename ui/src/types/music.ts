export interface Song {
  id: number;
  path: string;
  hash: string;
  coverId: number | null;
  added: string;
  updated: string;
  deleted: string | null;
  marked: boolean;
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

export interface SongsResponse {
  songs: Song[];
  total: number;
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
