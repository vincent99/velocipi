CREATE TABLE IF NOT EXISTS cover (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash        TEXT    NOT NULL UNIQUE,
    added       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    contentType TEXT    NOT NULL DEFAULT 'image/jpeg',
    data        BLOB    NOT NULL
);

CREATE TABLE IF NOT EXISTS song (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL UNIQUE,
    hash        TEXT    NOT NULL UNIQUE,
    coverId     INTEGER REFERENCES cover(id),
    added       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted     DATETIME,
    marked      INTEGER NOT NULL DEFAULT 0,
    artist      TEXT    NOT NULL DEFAULT '',
    album       TEXT    NOT NULL DEFAULT '',
    artistSort  TEXT    NOT NULL DEFAULT '',
    albumSort   TEXT    NOT NULL DEFAULT '',
    title       TEXT    NOT NULL DEFAULT '',
    discNumber  INTEGER NOT NULL DEFAULT 0,
    trackNumber INTEGER NOT NULL DEFAULT 0,
    trackTotal  INTEGER NOT NULL DEFAULT 0,
    genre       TEXT    NOT NULL DEFAULT '[]' CHECK(json_valid(genre)),
    length      REAL    NOT NULL DEFAULT 0,
    year        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlist (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    items TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(items))
);

CREATE TABLE IF NOT EXISTS smartplaylist (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT 'null'
);
