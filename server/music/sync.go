package music

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode"

	"github.com/dhowden/tag"
)

// musicExtensions is the set of file extensions the syncer will process.
var musicExtensions = map[string]bool{
	".mp3":  true,
	".m4a":  true,
	".flac": true,
	".ogg":  true,
	".wav":  true,
	".aac":  true,
	".opus": true,
	".wma":  true,
}

// leadingArticles are moved to the end when computing sort names.
var leadingArticles = []string{"The ", "A ", "An "}

// SyncOptions controls the behaviour of a sync run.
type SyncOptions struct {
	// Force re-reads metadata for all files, ignoring cached mtime.
	Force bool
	// Rename reorganises the music directory into
	// [artist]/[album]/[artist] - [album] - [NN] - [title].[ext] after syncing.
	Rename bool
}

// Syncer scans the music directory and synchronises files with the database.
type Syncer struct {
	db       *DB
	musicDir string
	cfg      MusicConfig
	opts     SyncOptions
}

// NewSyncer creates a Syncer.
func NewSyncer(db *DB, cfg MusicConfig, opts SyncOptions) *Syncer {
	return &Syncer{db: db, musicDir: cfg.MusicDir, cfg: cfg, opts: opts}
}

// relPath returns path relative to s.musicDir for log messages.
// Falls back to the full path if it can't be made relative.
func (s *Syncer) relPath(path string) string {
	rel, err := filepath.Rel(s.musicDir, path)
	if err != nil {
		return path
	}
	return rel
}

// songMeta holds all extracted metadata for one music file.
type songMeta struct {
	Path        string
	Hash        string
	Artist      string
	Album       string
	ArtistSort  string
	AlbumSort   string
	Title       string
	DiscNumber  int
	TrackNumber int
	TrackTotal  int
	Genre       []string
	Length      float64
	Year        int
	Format      string // e.g. "mp3", "flac"
	Bitrate     int    // kbps
	CoverData   []byte
	CoverType   string
	CoverHash   string
}

// Run walks the music directory and synchronises it with the database.
// It always runs Clean at the end.
func (s *Syncer) Run(ctx context.Context) error {
	// Backup before sync.
	if err := s.db.Backup("backup"); err != nil {
		log.Println("music sync: backup warning:", err)
	}

	// Walk all files.
	found := map[string]bool{}
	var toProcess []string
	var toDelete []string
	err := filepath.WalkDir(s.musicDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			log.Println("music sync: walk error:", err)
			return nil
		}
		if strings.HasPrefix(d.Name(), ".") {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if d.IsDir() || ctx.Err() != nil {
			return nil
		}
		if !musicExtensions[strings.ToLower(filepath.Ext(path))] {
			toDelete = append(toDelete, path)
			return nil
		}
		found[path] = true
		toProcess = append(toProcess, path)
		return nil
	})
	if err != nil {
		return fmt.Errorf("music sync: walk: %w", err)
	}

	log.Printf("music sync: found %d music files", len(toProcess))

	// Process each file.
	added, updated, skipped := 0, 0, 0
	total := len(toProcess)
	for i, path := range toProcess {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		action, err := s.processFile(path)
		if err != nil {
			log.Printf("music sync: [%d/%d] error %s: %v", i+1, total, s.relPath(path), err)
			continue
		}
		switch action {
		case "added":
			added++
			log.Printf("music sync: [%d/%d] added: %s", i+1, total, s.relPath(path))
		case "updated":
			updated++
			log.Printf("music sync: [%d/%d] updated: %s", i+1, total, s.relPath(path))
		default:
			skipped++
			if (i+1)%100 == 0 {
				log.Printf("music sync: [%d/%d] scanning…", i+1, total)
			}
		}
	}

	// Delete non-music files found during the walk (after processing so that
	// directory cover art is available for coverFromDir during the scan above).
	for _, path := range toDelete {
		if err := os.Remove(path); err != nil {
			log.Printf("music sync: delete non-music file %s: %v", s.relPath(path), err)
		} else {
			log.Printf("music sync: deleted non-music file %s", s.relPath(path))
		}
	}

	// Mark deleted songs (in DB but not found in FS).
	res, err := s.db.db.Exec(`
		UPDATE song SET deleted=CURRENT_TIMESTAMP
		WHERE deleted IS NULL AND path NOT IN (
			SELECT value FROM json_each(?)
		)`, mustMarshalPaths(toProcess))
	if err != nil {
		log.Println("music sync: mark deleted:", err)
	} else if n, _ := res.RowsAffected(); n > 0 {
		log.Printf("music sync: marked %d songs as deleted", n)
	}

	log.Printf("music sync: done — added=%d updated=%d skipped=%d", added, updated, skipped)

	// Always clean up after sync.
	if err := s.Clean(ctx); err != nil {
		log.Println("music sync: clean warning:", err)
	}

	// Optionally rename/reorganise.
	if s.opts.Rename {
		if err := s.RenameOrganise(ctx); err != nil {
			return fmt.Errorf("music sync: rename: %w", err)
		}
	}

	return nil
}

// mustMarshalPaths marshals a []string to a JSON string for use with json_each.
func mustMarshalPaths(paths []string) string {
	b, _ := json.Marshal(paths)
	return string(b)
}

// processFile handles a single music file: check mtime, compute hash if needed,
// insert or update as required. Returns the action taken ("added", "updated", "skipped").
func (s *Syncer) processFile(path string) (string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("stat: %w", err)
	}
	mtime := info.ModTime().UTC().Truncate(time.Second)

	// Fast path: if path is in DB and mtime matches, skip (unless --force).
	if !s.opts.Force {
		var dbUpdated time.Time
		err := s.db.db.QueryRow(
			`SELECT updated FROM song WHERE path=? AND deleted IS NULL`, path,
		).Scan(&dbUpdated)
		if err == nil {
			// SQLite stores datetimes as UTC strings; parse & truncate for comparison.
			dbUpdated = dbUpdated.UTC().Truncate(time.Second)
			if dbUpdated.Equal(mtime) {
				return "skipped", nil
			}
		}
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read: %w", err)
	}
	h := sha256.Sum256(data)
	hash := hex.EncodeToString(h[:])

	// Check if this exact path is already in the DB.
	var dbID int64
	var dbHash string
	err = s.db.db.QueryRow(`SELECT id, hash FROM song WHERE path=?`, path).Scan(&dbID, &dbHash)
	if err == nil {
		// Path exists.
		if dbHash == hash && !s.opts.Force {
			// Hash unchanged — just refresh the mtime so we skip next time.
			s.db.db.Exec(`UPDATE song SET updated=? WHERE id=?`, mtime.Format(time.RFC3339), dbID)
			return "skipped", nil
		}
		// Hash changed (or --force) — re-read metadata and update.
		meta, err := extractMeta(path, data, hash)
		if err != nil {
			return "", fmt.Errorf("extract meta: %w", err)
		}
		meta, mtime, err = s.maybeTranscode(meta, mtime)
		if err != nil {
			log.Printf("music sync: transcode %s: %v", s.relPath(path), err)
		}
		coverID, err := s.ensureCover(meta, meta.Path)
		if err != nil {
			log.Printf("music sync: cover for %s: %v", s.relPath(meta.Path), err)
		}
		if err := s.updateSong(dbID, meta, coverID, mtime); err != nil {
			return "", fmt.Errorf("update: %w", err)
		}
		// Path may have changed due to transcoding.
		if meta.Path != path {
			s.db.db.Exec(`UPDATE song SET path=? WHERE id=?`, meta.Path, dbID)
		}
		return "updated", nil
	}

	// Path not in DB — check for a hash match (file moved).
	err = s.db.db.QueryRow(`SELECT id FROM song WHERE hash=?`, hash).Scan(&dbID)
	if err == nil {
		// Hash match: see if old path still exists.
		var oldPath string
		s.db.db.QueryRow(`SELECT path FROM song WHERE id=?`, dbID).Scan(&oldPath)
		if _, statErr := os.Stat(oldPath); os.IsNotExist(statErr) {
			// Old path gone — update existing entry with new path.
			meta, err := extractMeta(path, data, hash)
			if err != nil {
				return "", fmt.Errorf("extract meta: %w", err)
			}
			meta, mtime, err = s.maybeTranscode(meta, mtime)
			if err != nil {
				log.Printf("music sync: transcode %s: %v", s.relPath(path), err)
			}
			coverID, _ := s.ensureCover(meta, meta.Path)
			if err := s.updateSong(dbID, meta, coverID, mtime); err != nil {
				return "", fmt.Errorf("update moved: %w", err)
			}
			// Update path since it changed (moved or transcoded).
			s.db.db.Exec(`UPDATE song SET path=? WHERE id=?`, meta.Path, dbID)
			return "updated", nil
		}
		// Old path still exists — this is a genuine duplicate, add as new.
	}

	// Check for artist+album+title match (same song, different file).
	meta, err := extractMeta(path, data, hash)
	if err != nil {
		return "", fmt.Errorf("extract meta: %w", err)
	}
	meta, mtime, err = s.maybeTranscode(meta, mtime)
	if err != nil {
		log.Printf("music sync: transcode %s: %v", s.relPath(path), err)
	}

	if meta.Artist != "" && meta.Album != "" && meta.Title != "" {
		err = s.db.db.QueryRow(
			`SELECT id FROM song WHERE artist=? AND album=? AND title=? AND deleted IS NOT NULL LIMIT 1`,
			meta.Artist, meta.Album, meta.Title,
		).Scan(&dbID)
		if err == nil {
			// Was deleted, re-appear with same identity.
			coverID, _ := s.ensureCover(meta, meta.Path)
			s.db.db.Exec(`UPDATE song SET path=?,hash=?,deleted=NULL,updated=? WHERE id=?`, meta.Path, meta.Hash, mtime.Format(time.RFC3339), dbID)
			if err := s.updateSong(dbID, meta, coverID, mtime); err != nil {
				return "", err
			}
			return "updated", nil
		}
	}

	// Truly new song.
	coverID, _ := s.ensureCover(meta, meta.Path)
	if err := s.insertSong(meta, coverID, mtime); err != nil {
		return "", fmt.Errorf("insert: %w", err)
	}
	return "added", nil
}

// maybeTranscode transcodes the file if maxBitrate is set and the file's
// bitrate exceeds it by more than 10% (to avoid re-transcoding files whose
// bitrate is only slightly over due to encoder variance).
// It returns updated meta (with new path/hash/format/bitrate) and mtime.
func (s *Syncer) maybeTranscode(meta *songMeta, mtime time.Time) (*songMeta, time.Time, error) {
	if s.cfg.MaxBitrate <= 0 {
		return meta, mtime, nil
	}
	ceiling := int(float64(s.cfg.MaxBitrate) * 1.10)
	if meta.Bitrate <= ceiling {
		return meta, mtime, nil
	}
	log.Printf("music transcode: %s (bitrate=%dkbps > max=%dkbps)", s.relPath(meta.Path), meta.Bitrate, s.cfg.MaxBitrate)
	newPath, newHash, newMtime, err := transcodeFile(meta.Path, s.cfg.TranscodeFormat, s.cfg.MaxBitrate)
	if err != nil {
		return meta, mtime, err
	}
	// Re-probe the transcoded file for accurate format/bitrate/length.
	newLength, newFormat, newBitrate := probeAudio(newPath)
	updated := *meta
	updated.Path = newPath
	updated.Hash = newHash
	updated.Format = newFormat
	updated.Bitrate = newBitrate
	if newLength > 0 {
		updated.Length = newLength
	}
	log.Printf("music transcode: → %s (%s %dkbps)", s.relPath(newPath), newFormat, newBitrate)
	return &updated, newMtime, nil
}

// extractMeta reads ID3/tag metadata from data bytes.
func extractMeta(path string, data []byte, hash string) (*songMeta, error) {
	length, format, bitrate := probeAudio(path)

	t, err := tag.ReadFrom(bytes.NewReader(data))
	if err != nil {
		// Return minimal meta with path as title.
		return &songMeta{
			Path:    path,
			Hash:    hash,
			Title:   filepath.Base(path),
			Genre:   []string{},
			Length:  length,
			Format:  format,
			Bitrate: bitrate,
		}, nil
	}

	track, total := t.Track()
	disc, _ := t.Disc()
	genres := normalizeGenre(t.Genre())

	artist := strings.TrimSpace(t.Artist())
	album := strings.TrimSpace(t.Album())
	title := strings.TrimSpace(t.Title())
	if title == "" {
		title = filepath.Base(path)
	}
	artistSort := sortName(artist)
	albumSort := sortName(album)

	meta := &songMeta{
		Path:        path,
		Hash:        hash,
		Artist:      artist,
		Album:       album,
		ArtistSort:  artistSort,
		AlbumSort:   albumSort,
		Title:       title,
		DiscNumber:  disc,
		TrackNumber: track,
		TrackTotal:  total,
		Genre:       genres,
		Year:        t.Year(),
		Length:      length,
		Format:      format,
		Bitrate:     bitrate,
	}

	if pic := t.Picture(); pic != nil {
		meta.CoverData = pic.Data
		meta.CoverType = pic.MIMEType
		h := sha256.Sum256(pic.Data)
		meta.CoverHash = hex.EncodeToString(h[:])
	}

	return meta, nil
}

// normalizeGenre splits a genre string on commas and normalises each element
// to Title Case. Duplicates are removed.
func normalizeGenre(raw string) []string {
	if raw == "" {
		return []string{}
	}
	parts := strings.Split(raw, ",")
	seen := map[string]bool{}
	out := []string{}
	for _, p := range parts {
		g := toTitleCase(strings.TrimSpace(p))
		if g != "" && !seen[g] {
			seen[g] = true
			out = append(out, g)
		}
	}
	return out
}

// toTitleCase converts a string to Title Case per word.
func toTitleCase(s string) string {
	var b strings.Builder
	upper := true
	for _, r := range s {
		if unicode.IsSpace(r) || r == '-' || r == '/' {
			b.WriteRune(r)
			upper = true
		} else if upper {
			b.WriteRune(unicode.ToUpper(r))
			upper = false
		} else {
			b.WriteRune(unicode.ToLower(r))
		}
	}
	return b.String()
}

// sortName moves a leading article to the end: "The Who" → "Who, The".
func sortName(name string) string {
	for _, art := range leadingArticles {
		if strings.HasPrefix(name, art) {
			suffix := strings.TrimSuffix(art, " ")
			return strings.TrimPrefix(name, art) + ", " + suffix
		}
	}
	return name
}

// ensureCover finds or creates a cover entry for the song's embedded art.
// Falls back to a directory image or sibling songs for the same album.
func (s *Syncer) ensureCover(meta *songMeta, path string) (*int64, error) {
	// Use embedded cover if present.
	if len(meta.CoverData) > 0 {
		return s.findOrCreateCover(meta.CoverHash, meta.CoverType, meta.CoverData)
	}

	// Look for a single JPEG in the same directory.
	dir := filepath.Dir(path)
	if coverID, err := s.coverFromDir(dir); err == nil && coverID != nil {
		return coverID, nil
	}

	// Look through sibling songs with the same artist+album.
	if meta.Artist != "" && meta.Album != "" {
		var coverID sql.NullInt64
		err := s.db.db.QueryRow(
			`SELECT coverId FROM song WHERE artist=? AND album=? AND coverId IS NOT NULL AND deleted IS NULL ORDER BY discNumber, trackNumber LIMIT 1`,
			meta.Artist, meta.Album,
		).Scan(&coverID)
		if err == nil && coverID.Valid {
			id := coverID.Int64
			return &id, nil
		}
	}

	return nil, nil
}

// coverFromDir looks for a single JPEG image in dir and returns its cover ID.
func (s *Syncer) coverFromDir(dir string) (*int64, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var jpegFiles []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(e.Name()))
		if ext == ".jpg" || ext == ".jpeg" {
			jpegFiles = append(jpegFiles, filepath.Join(dir, e.Name()))
		}
	}
	if len(jpegFiles) != 1 {
		return nil, nil
	}
	imgData, err := os.ReadFile(jpegFiles[0])
	if err != nil {
		return nil, err
	}
	// Validate it's actually an image.
	if _, _, err := image.Decode(bytes.NewReader(imgData)); err != nil {
		return nil, err
	}
	h := sha256.Sum256(imgData)
	coverHash := hex.EncodeToString(h[:])
	return s.findOrCreateCover(coverHash, "image/jpeg", imgData)
}

// findOrCreateCover returns the cover ID for the given hash, creating a new
// row if one does not already exist.
func (s *Syncer) findOrCreateCover(hash, contentType string, data []byte) (*int64, error) {
	var id int64
	err := s.db.db.QueryRow(`SELECT id FROM cover WHERE hash=?`, hash).Scan(&id)
	if err == nil {
		return &id, nil
	}
	res, err := s.db.db.Exec(
		`INSERT INTO cover(hash,contentType,data) VALUES(?,?,?)`,
		hash, contentType, data,
	)
	if err != nil {
		return nil, fmt.Errorf("insert cover: %w", err)
	}
	id, _ = res.LastInsertId()
	return &id, nil
}

// insertSong adds a new song row, storing the file mtime in the updated field.
func (s *Syncer) insertSong(meta *songMeta, coverID *int64, mtime time.Time) error {
	genreJSON, _ := json.Marshal(meta.Genre)
	_, err := s.db.db.Exec(`
		INSERT INTO song(path,hash,coverId,updated,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,format,bitrate)
		VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
		meta.Path, meta.Hash, coverID, mtime.Format(time.RFC3339),
		meta.Artist, meta.Album, meta.ArtistSort, meta.AlbumSort, meta.Title,
		meta.DiscNumber, meta.TrackNumber, meta.TrackTotal,
		string(genreJSON), meta.Length, meta.Year, meta.Format, meta.Bitrate,
	)
	return err
}

// updateSong updates all metadata fields for an existing song row, storing mtime in updated.
func (s *Syncer) updateSong(id int64, meta *songMeta, coverID *int64, mtime time.Time) error {
	genreJSON, _ := json.Marshal(meta.Genre)
	_, err := s.db.db.Exec(`
		UPDATE song SET
			hash=?, coverId=?, updated=?, deleted=NULL,
			artist=?, album=?, artistSort=?, albumSort=?, title=?,
			discNumber=?, trackNumber=?, trackTotal=?, genre=?, length=?, year=?,
			format=?, bitrate=?
		WHERE id=?`,
		meta.Hash, coverID, mtime.Format(time.RFC3339),
		meta.Artist, meta.Album, meta.ArtistSort, meta.AlbumSort, meta.Title,
		meta.DiscNumber, meta.TrackNumber, meta.TrackTotal,
		string(genreJSON), meta.Length, meta.Year, meta.Format, meta.Bitrate,
		id,
	)
	return err
}

// Clean removes songs that are marked deleted and not referenced by any
// playlist, then removes cover art rows that are no longer referenced by any song.
func (s *Syncer) Clean(ctx context.Context) error {
	// Delete songs that are marked deleted and not in any playlist's items JSON.
	// playlist.items is a JSON array of song IDs; json_each expands it.
	res, err := s.db.db.ExecContext(ctx, `
		DELETE FROM song
		WHERE deleted IS NOT NULL
		  AND id NOT IN (
		    SELECT CAST(je.value AS INTEGER)
		    FROM playlist, json_each(playlist.items) AS je
		  )
	`)
	if err != nil {
		return fmt.Errorf("clean songs: %w", err)
	}
	songsDel, _ := res.RowsAffected()

	// Delete cover art rows not referenced by any remaining song.
	res, err = s.db.db.ExecContext(ctx, `
		DELETE FROM cover
		WHERE id NOT IN (
		    SELECT coverId FROM song WHERE coverId IS NOT NULL
		)
	`)
	if err != nil {
		return fmt.Errorf("clean covers: %w", err)
	}
	coversDel, _ := res.RowsAffected()

	log.Printf("music sync clean: removed %d deleted songs, %d orphaned covers", songsDel, coversDel)
	return nil
}

// artistLetterDir returns the single-letter (lowercase) bucket directory for an
// artist name: "a"–"z" for alphabetic first characters, "#" for digits, and
// "other" for anything else (including empty strings).
func artistLetterDir(artist string) string {
	runes := []rune(artist)
	if len(runes) == 0 {
		return "other"
	}
	r := runes[0]
	if unicode.IsLetter(r) {
		return strings.ToLower(string(r))
	}
	if unicode.IsDigit(r) {
		return "#"
	}
	return "other"
}

// canonicalPath returns the ideal destination path for a song given its metadata
// and musicDir. It does not check for collisions — callers must do that.
func canonicalPath(musicDir, currentPath, artist, album string, trackNumber int, title string) string {
	ext := strings.ToLower(filepath.Ext(currentPath))

	if artist == "" {
		artist = "Unknown"
	}
	if album == "" {
		album = "Unknown"
	}

	var trackPart string
	if trackNumber > 0 {
		trackPart = fmt.Sprintf("%02d", trackNumber)
	} else {
		trackPart = "00"
	}
	if title == "" {
		title = strings.TrimSuffix(filepath.Base(currentPath), filepath.Ext(currentPath))
	}

	letterDir := artistLetterDir(artist)
	artistDir := safeFilename(artist)
	albumDir := safeFilename(album)
	filename := safeFilename(fmt.Sprintf("%s - %s - %s - %s", artist, album, trackPart, title)) + ext
	return filepath.Join(musicDir, letterDir, artistDir, albumDir, filename)
}

// safeFilename replaces characters that are unsafe in filenames with underscores.
func safeFilename(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch r {
		case '/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00':
			b.WriteRune('_')
		default:
			b.WriteRune(r)
		}
	}
	return strings.TrimSpace(b.String())
}

// RenameOrganise moves music files into
// [musicDir]/[letter]/[artist]/[album]/[artist] - [album] - [NN] - [title].[ext]
// and updates the database paths accordingly.
// It also deletes dot-files/dirs and empty directories inside musicDir.
func (s *Syncer) RenameOrganise(ctx context.Context) error {
	log.Println("music rename: starting")

	// Fetch all non-deleted songs.
	rows, err := s.db.db.QueryContext(ctx,
		`SELECT id, path, artist, album, trackNumber, title FROM song WHERE deleted IS NULL`,
	)
	if err != nil {
		return fmt.Errorf("query songs: %w", err)
	}
	type songRow struct {
		id     int64
		path   string
		artist string
		album  string
		track  int
		title  string
	}
	var songs []songRow
	for rows.Next() {
		var sr songRow
		if err := rows.Scan(&sr.id, &sr.path, &sr.artist, &sr.album, &sr.track, &sr.title); err != nil {
			rows.Close()
			return fmt.Errorf("scan: %w", err)
		}
		songs = append(songs, sr)
	}
	rows.Close()

	moved := 0
	for _, sr := range songs {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		// Verify file still exists.
		if _, err := os.Stat(sr.path); err != nil {
			continue
		}

		destPath := canonicalPath(s.musicDir, sr.path, sr.artist, sr.album, sr.track, sr.title)
		destDir := filepath.Dir(destPath)

		// Nothing to do if already in the right place.
		if sr.path == destPath {
			continue
		}

		// Create destination directory.
		if err := os.MkdirAll(destDir, 0755); err != nil {
			log.Printf("music rename: mkdir %s: %v", s.relPath(destDir), err)
			continue
		}

		// Handle collision: if dest exists and is a different song, add suffix.
		if _, err := os.Stat(destPath); err == nil && destPath != sr.path {
			destExt := filepath.Ext(destPath)
			destBase := strings.TrimSuffix(filepath.Base(destPath), destExt)
			for i := 2; ; i++ {
				candidate := filepath.Join(destDir, fmt.Sprintf("%s (%d)%s", destBase, i, destExt))
				if _, err := os.Stat(candidate); os.IsNotExist(err) {
					destPath = candidate
					break
				}
			}
		}

		if err := os.Rename(sr.path, destPath); err != nil {
			log.Printf("music rename: move %s → %s: %v", s.relPath(sr.path), s.relPath(destPath), err)
			continue
		}
		// Update DB path and mtime.
		info, _ := os.Stat(destPath)
		var newMtime string
		if info != nil {
			newMtime = info.ModTime().UTC().Truncate(time.Second).Format(time.RFC3339)
		} else {
			newMtime = time.Now().UTC().Format(time.RFC3339)
		}
		s.db.db.Exec(`UPDATE song SET path=?, updated=? WHERE id=?`, destPath, newMtime, sr.id)
		log.Printf("music rename: %s → %s", s.relPath(sr.path), s.relPath(destPath))
		moved++
	}
	log.Printf("music rename: moved %d files", moved)

	// Delete dot-files and dot-directories inside musicDir.
	s.deleteDotEntries()

	// Delete empty directories (repeat until none remain).
	s.deleteEmptyDirs()

	return nil
}

// deleteDotEntries removes files and directories whose names start with '.'
// anywhere inside musicDir.
func (s *Syncer) deleteDotEntries() {
	filepath.WalkDir(s.musicDir, func(path string, d os.DirEntry, err error) error {
		if err != nil || path == s.musicDir {
			return nil
		}
		if strings.HasPrefix(d.Name(), ".") {
			if d.IsDir() {
				os.RemoveAll(path)
				log.Printf("music rename: removed dot-dir %s", s.relPath(path))
				return filepath.SkipDir
			}
			os.Remove(path)
			log.Printf("music rename: removed dot-file %s", s.relPath(path))
		}
		return nil
	})
}

// deleteEmptyDirs removes empty directories inside musicDir, repeating until
// no more empty dirs are found.
func (s *Syncer) deleteEmptyDirs() {
	for {
		removed := 0
		filepath.WalkDir(s.musicDir, func(path string, d os.DirEntry, err error) error {
			if err != nil || !d.IsDir() || path == s.musicDir {
				return nil
			}
			entries, err := os.ReadDir(path)
			if err != nil {
				return nil
			}
			if len(entries) == 0 {
				os.Remove(path)
				log.Printf("music rename: removed empty dir %s", s.relPath(path))
				removed++
			}
			return nil
		})
		if removed == 0 {
			break
		}
	}
}

// probeAudio uses ffprobe to get the duration (seconds), codec name (format),
// and bitrate (kbps) of a media file.
// Returns zero values if ffprobe is unavailable or parsing fails.
func probeAudio(path string) (length float64, format string, bitrateKbps int) {
	type ffprobeOutput struct {
		Streams []struct {
			CodecName string `json:"codec_name"`
		} `json:"streams"`
		Format struct {
			Duration string `json:"duration"`
			BitRate  string `json:"bit_rate"`
		} `json:"format"`
	}

	out, err := exec.Command("ffprobe",
		"-v", "error",
		"-show_entries", "stream=codec_name:format=duration,bit_rate",
		"-of", "json",
		path,
	).Output()
	if err != nil {
		return
	}

	var result ffprobeOutput
	if err := json.Unmarshal(out, &result); err != nil {
		return
	}

	length, _ = strconv.ParseFloat(result.Format.Duration, 64)

	if len(result.Streams) > 0 {
		format = result.Streams[0].CodecName
	}

	if br, err := strconv.ParseInt(result.Format.BitRate, 10, 64); err == nil {
		bitrateKbps = int(br / 1000)
	}

	return
}

// transcodeArgs returns the ffmpeg codec arguments and output file extension
// for the given format and target bitrate.
//
//   - aac  → native aac encoder, ABR mode (-b:a), .m4a container
//   - mp3  → libmp3lame, best-quality CBR (-b:a -compression_level 0), .mp3
//   - anything else → generic -c:a codec -b:a, extension = "."+format
func transcodeArgs(transcodeFormat string, maxBitrateKbps int) (codecArgs []string, ext string) {
	bitrateFlag := fmt.Sprintf("%dk", maxBitrateKbps)
	switch strings.ToLower(transcodeFormat) {
	case "aac":
		// Use ffmpeg's native AAC encoder in ABR mode.  The aac_adtstoasc
		// bitstream filter is applied automatically for .m4a by ffmpeg.
		codecArgs = []string{"-c:a", "aac", "-b:a", bitrateFlag}
		ext = ".m4a"
	case "mp3":
		// libmp3lame with -compression_level 0 gives the best quality at the
		// chosen CBR target (slowest encode, highest quality algorithm).
		codecArgs = []string{"-c:a", "libmp3lame", "-b:a", bitrateFlag, "-compression_level", "0"}
		ext = ".mp3"
	default:
		codecArgs = []string{"-c:a", transcodeFormat, "-b:a", bitrateFlag}
		ext = "." + strings.ToLower(transcodeFormat)
	}
	return
}

// transcodeFile transcodes path to transcodeFormat at maxBitrateKbps.
// It copies all metadata tags from the original, writes to a temp file,
// replaces the original, and returns the new path. The hash and mtime of
// the new file are also returned.
func transcodeFile(path, transcodeFormat string, maxBitrateKbps int) (newPath string, newHash string, newMtime time.Time, err error) {
	codecArgs, ext := transcodeArgs(transcodeFormat, maxBitrateKbps)

	// Build new path: same dir + base (no old ext) + new ext.
	dir := filepath.Dir(path)
	base := strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
	newPath = filepath.Join(dir, base+ext)

	// Avoid clobbering a different existing file.
	if newPath != path {
		if _, statErr := os.Stat(newPath); statErr == nil {
			// Already exists — use a temp name.
			tmp, tmpErr := os.CreateTemp(dir, "transcode-*"+ext)
			if tmpErr != nil {
				err = fmt.Errorf("create temp: %w", tmpErr)
				return
			}
			tmp.Close()
			newPath = tmp.Name()
		}
	}

	args := []string{"-y", "-i", path, "-map_metadata", "0"}
	args = append(args, codecArgs...)
	args = append(args, "-vn", newPath)

	cmd := exec.Command("ffmpeg", args...)
	if out, runErr := cmd.CombinedOutput(); runErr != nil {
		err = fmt.Errorf("ffmpeg: %w\n%s", runErr, string(out))
		return
	}

	// Remove original if we wrote to a new path.
	if newPath != path {
		if removeErr := os.Remove(path); removeErr != nil {
			log.Printf("music transcode: remove original %s: %v", path, removeErr)
		}
	}

	// Compute new hash.
	data, readErr := os.ReadFile(newPath)
	if readErr != nil {
		err = fmt.Errorf("read transcoded: %w", readErr)
		return
	}
	h := sha256.Sum256(data)
	newHash = hex.EncodeToString(h[:])

	info, statErr := os.Stat(newPath)
	if statErr != nil {
		err = fmt.Errorf("stat transcoded: %w", statErr)
		return
	}
	newMtime = info.ModTime().UTC().Truncate(time.Second)
	return
}

// fileReader implements io.ReadSeeker over a []byte so tag.ReadFrom can seek.
type fileReader struct {
	r io.ReadSeeker
}

func newFileReader(data []byte) io.ReadSeeker {
	return bytes.NewReader(data)
}
