package music

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os/exec"
	"strings"
	"time"
)

// LookupOptions controls the behaviour of a lookup run.
type LookupOptions struct {
	// Force re-queries songs that have already been looked up.
	Force bool
}

// Lookup performs AcoustID acoustic fingerprinting and MusicBrainz metadata
// enrichment for songs that have missing or incomplete metadata.
type Lookup struct {
	db   *DB
	cfg  MusicConfig
	opts LookupOptions
}

// NewLookup creates a Lookup.
func NewLookup(db *DB, cfg MusicConfig, opts LookupOptions) *Lookup {
	return &Lookup{db: db, cfg: cfg, opts: opts}
}

// mbMeta holds the metadata returned from MusicBrainz for a recording.
type mbMeta struct {
	Title       string
	Artist      string
	ArtistSort  string
	Album       string
	TrackNumber int
	TrackTotal  int
	DiscNumber  int
	Year        int
	Genres      []string
	ReleaseMBID string
}

// Run queries songs that need lookup and enriches them via AcoustID and MusicBrainz.
func (l *Lookup) Run(ctx context.Context) error {
	query := `SELECT id, path, title, artist, album, trackNumber, year, genre, coverId
	          FROM song WHERE deleted IS NULL`
	if !l.opts.Force {
		query += ` AND acoustidLookedUp = 0`
	}

	rows, err := l.db.db.QueryContext(ctx, query)
	if err != nil {
		return fmt.Errorf("lookup: query songs: %w", err)
	}
	defer rows.Close()

	type songRow struct {
		id          int64
		path        string
		title       string
		artist      string
		album       string
		trackNumber int
		year        int
		genreJSON   string
		coverID     *int64
	}
	var songs []songRow
	for rows.Next() {
		var sr songRow
		if err := rows.Scan(&sr.id, &sr.path, &sr.title, &sr.artist, &sr.album, &sr.trackNumber, &sr.year, &sr.genreJSON, &sr.coverID); err != nil {
			return fmt.Errorf("lookup: scan: %w", err)
		}
		songs = append(songs, sr)
	}
	rows.Close()

	if len(songs) == 0 {
		log.Println("lookup: no songs to process")
		return nil
	}
	log.Printf("lookup: processing %d songs", len(songs))

	// Rate limiter: MusicBrainz allows 1 req/sec; we use 1.1s between songs to
	// account for multiple MB requests per song.
	ticker := time.NewTicker(1100 * time.Millisecond)
	defer ticker.Stop()

	for i, sr := range songs {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if i > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
			}
		}

		var genre []string
		_ = json.Unmarshal([]byte(sr.genreJSON), &genre)

		filled, err := l.processOne(ctx, sr.id, sr.path, sr.title, sr.artist, sr.album, sr.trackNumber, sr.year, genre, sr.coverID)
		if err != nil {
			log.Printf("lookup: [%d/%d] %s: %v", i+1, len(songs), sr.path, err)
			// Mark as looked up even on error to avoid repeated failures.
			l.db.db.ExecContext(ctx, `UPDATE song SET acoustidLookedUp=1 WHERE id=?`, sr.id)
			continue
		}
		if len(filled) > 0 {
			log.Printf("lookup: [%d/%d] %s: filled %s", i+1, len(songs), sr.path, strings.Join(filled, ", "))
		} else {
			log.Printf("lookup: [%d/%d] %s: nothing to fill", i+1, len(songs), sr.path)
		}
	}

	return nil
}

// processOne handles lookup for a single song. Returns the list of field names that were filled.
func (l *Lookup) processOne(
	ctx context.Context,
	id int64, path, title, artist, album string,
	trackNumber, year int,
	genre []string,
	coverID *int64,
) ([]string, error) {
	// Step 1: generate fingerprint.
	duration, fingerprint, err := runFpcalc(path)
	if err != nil {
		return nil, fmt.Errorf("fpcalc: %w", err)
	}

	// Step 2: AcoustID lookup → MusicBrainz recording ID.
	recMBID, relMBID, score, err := acoustidLookup(ctx, l.cfg.AcoustIDKey, duration, fingerprint)
	if err != nil {
		return nil, fmt.Errorf("acoustid: %w", err)
	}
	if score < l.cfg.AcoustIDMinScore {
		l.db.db.ExecContext(ctx, `UPDATE song SET acoustidLookedUp=1 WHERE id=?`, id)
		return nil, nil
	}

	// Step 3: MusicBrainz recording metadata.
	mb, err := mbRecording(ctx, recMBID)
	if err != nil {
		return nil, fmt.Errorf("musicbrainz: %w", err)
	}
	if mb == nil {
		l.db.db.ExecContext(ctx, `UPDATE song SET acoustidLookedUp=1, mbid=? WHERE id=?`, recMBID, id)
		return nil, nil
	}
	if relMBID == "" {
		relMBID = mb.ReleaseMBID
	}

	// Step 4: fill only empty/zero fields.
	var filled []string
	fillStr := func(name string, cur *string, val string) {
		if *cur == "" && val != "" {
			*cur = val
			filled = append(filled, name)
		}
	}
	fillInt := func(name string, cur *int, val int) {
		if *cur == 0 && val != 0 {
			*cur = val
			filled = append(filled, name)
		}
	}

	fillStr("title", &title, mb.Title)
	fillStr("artist", &artist, mb.Artist)
	fillStr("album", &album, mb.Album)
	fillInt("trackNumber", &trackNumber, mb.TrackNumber)
	fillInt("year", &year, mb.Year)

	if len(genre) == 0 && len(mb.Genres) > 0 {
		genre = mb.Genres
		filled = append(filled, "genre")
	}

	// Recompute sort names if artist/album were filled.
	artistSort := sortName(artist)
	albumSort := sortName(album)

	// Normalise genre.
	genreJSON, _ := json.Marshal(genre)

	// Step 5: fetch cover art if still missing.
	var newCoverID *int64
	if coverID == nil && relMBID != "" {
		data, contentType, err := fetchCoverArt(ctx, relMBID)
		if err == nil && len(data) > 0 {
			h := sha256.Sum256(data)
			hash := hex.EncodeToString(h[:])
			newCoverID, err = l.storeCover(hash, contentType, data)
			if err != nil {
				log.Printf("lookup: store cover for song %d: %v", id, err)
				newCoverID = nil
			} else {
				filled = append(filled, "cover")
			}
		}
	}

	// Step 6: update the DB row.
	useCoverID := coverID
	if newCoverID != nil {
		useCoverID = newCoverID
	}

	_, err = l.db.db.ExecContext(ctx, `
		UPDATE song SET
			mbid=?, acoustidLookedUp=1,
			title=?, artist=?, artistSort=?, album=?, albumSort=?,
			trackNumber=?, year=?, genre=?, coverId=?
		WHERE id=?`,
		recMBID,
		title, artist, artistSort, album, albumSort,
		trackNumber, year, string(genreJSON), useCoverID,
		id,
	)
	if err != nil {
		return filled, fmt.Errorf("update song: %w", err)
	}

	return filled, nil
}

// storeCover finds or creates a cover row and returns its ID.
func (l *Lookup) storeCover(hash, contentType string, data []byte) (*int64, error) {
	var id int64
	err := l.db.db.QueryRow(`SELECT id FROM cover WHERE hash=?`, hash).Scan(&id)
	if err == nil {
		return &id, nil
	}
	res, err := l.db.db.Exec(
		`INSERT INTO cover(hash,contentType,data) VALUES(?,?,?)`,
		hash, contentType, data,
	)
	if err != nil {
		return nil, fmt.Errorf("insert cover: %w", err)
	}
	id, _ = res.LastInsertId()
	return &id, nil
}

// runFpcalc invokes fpcalc and returns the duration (seconds) and fingerprint string.
func runFpcalc(path string) (int, string, error) {
	out, err := exec.Command("fpcalc", "-json", path).Output()
	if err != nil {
		return 0, "", fmt.Errorf("fpcalc exec: %w", err)
	}
	var result struct {
		Duration    float64 `json:"duration"`
		Fingerprint string  `json:"fingerprint"`
	}
	if err := json.Unmarshal(out, &result); err != nil {
		return 0, "", fmt.Errorf("fpcalc parse: %w", err)
	}
	return int(result.Duration), result.Fingerprint, nil
}

// acoustidLookup queries the AcoustID API and returns the best-scoring
// MusicBrainz recording MBID and release MBID.
func acoustidLookup(ctx context.Context, key string, duration int, fingerprint string) (recMBID, relMBID string, score float64, err error) {
	params := url.Values{
		"client":      {key},
		"duration":    {fmt.Sprintf("%d", duration)},
		"fingerprint": {fingerprint},
		"meta":        {"recordings+releases"},
	}
	reqURL := "https://api.acoustid.org/v2/lookup?" + params.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return "", "", 0, err
	}
	req.Header.Set("User-Agent", "velocipi/1.0")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", "", 0, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", "", 0, err
	}

	var result struct {
		Status  string `json:"status"`
		Results []struct {
			Score      float64 `json:"score"`
			Recordings []struct {
				ID       string `json:"id"`
				Releases []struct {
					ID string `json:"id"`
				} `json:"releases"`
			} `json:"recordings"`
		} `json:"results"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return "", "", 0, fmt.Errorf("acoustid parse: %w", err)
	}

	// Find the highest-scoring result with a recording.
	for _, res := range result.Results {
		if res.Score > score && len(res.Recordings) > 0 {
			score = res.Score
			recMBID = res.Recordings[0].ID
			if len(res.Recordings[0].Releases) > 0 {
				relMBID = res.Recordings[0].Releases[0].ID
			}
		}
	}
	return recMBID, relMBID, score, nil
}

// mbRecording fetches recording metadata from MusicBrainz by recording MBID.
func mbRecording(ctx context.Context, mbid string) (*mbMeta, error) {
	reqURL := fmt.Sprintf("https://musicbrainz.org/ws/2/recording/%s?inc=artist-credits+releases+genres&fmt=json", mbid)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "velocipi/1.0 (github.com/vincent99/velocipi)")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("musicbrainz: status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var rec struct {
		Title         string `json:"title"`
		ArtistCredits []struct {
			Artist struct {
				Name     string `json:"name"`
				SortName string `json:"sort-name"`
			} `json:"artist"`
		} `json:"artist-credit"`
		Genres []struct {
			Name string `json:"name"`
		} `json:"genres"`
		Releases []struct {
			ID    string `json:"id"`
			Title string `json:"title"`
			Date  string `json:"date"`
			Media []struct {
				Position   int `json:"position"`
				TrackCount int `json:"track-count"`
				Tracks     []struct {
					Number   string `json:"number"`
					Position int    `json:"position"`
				} `json:"tracks"`
			} `json:"media"`
		} `json:"releases"`
	}
	if err := json.Unmarshal(body, &rec); err != nil {
		return nil, fmt.Errorf("musicbrainz parse: %w", err)
	}

	meta := &mbMeta{Title: rec.Title}

	if len(rec.ArtistCredits) > 0 {
		meta.Artist = rec.ArtistCredits[0].Artist.Name
		meta.ArtistSort = rec.ArtistCredits[0].Artist.SortName
	}

	for _, g := range rec.Genres {
		if g.Name != "" {
			meta.Genres = append(meta.Genres, toTitleCase(g.Name))
		}
	}

	if len(rec.Releases) > 0 {
		rel := rec.Releases[0]
		meta.Album = rel.Title
		meta.ReleaseMBID = rel.ID
		// Parse year from date string (YYYY, YYYY-MM, or YYYY-MM-DD).
		if len(rel.Date) >= 4 {
			var y int
			fmt.Sscanf(rel.Date[:4], "%d", &y)
			meta.Year = y
		}
		if len(rel.Media) > 0 {
			media := rel.Media[0]
			meta.DiscNumber = media.Position
			meta.TrackTotal = media.TrackCount
			if len(media.Tracks) > 0 {
				meta.TrackNumber = media.Tracks[0].Position
			}
		}
	}

	return meta, nil
}

// fetchCoverArt retrieves the front cover image from Cover Art Archive for a release MBID.
// It follows the redirect to the actual image URL.
func fetchCoverArt(ctx context.Context, releaseMBID string) ([]byte, string, error) {
	reqURL := fmt.Sprintf("https://coverartarchive.org/release/%s/front", releaseMBID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, "", err
	}
	req.Header.Set("User-Agent", "velocipi/1.0 (github.com/vincent99/velocipi)")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, "", nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, "", fmt.Errorf("cover art archive: status %d", resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, "", err
	}

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "image/jpeg"
	}
	// Strip parameters (e.g. "image/jpeg; charset=utf-8").
	if idx := strings.Index(contentType, ";"); idx >= 0 {
		contentType = strings.TrimSpace(contentType[:idx])
	}

	return data, contentType, nil
}

// CheckLookupDeps verifies that fpcalc is available in PATH and that
// the AcoustID API key is configured.  Returns a non-nil error describing
// what is missing.
func CheckLookupDeps(cfg MusicConfig) error {
	if cfg.AcoustIDKey == "" {
		return fmt.Errorf("music.acoustidKey is not set in config (register a free key at https://acoustid.org/)")
	}
	if _, err := exec.LookPath("fpcalc"); err != nil {
		return fmt.Errorf("fpcalc not found in PATH (install chromaprint-tools: sudo apt install chromaprint-tools)")
	}
	return nil
}
