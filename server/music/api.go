package music

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/vincent99/velocipi/server/config"
)

// Song is the API representation of a song row.
type Song struct {
	ID          int64    `json:"id"`
	Path        string   `json:"path"`
	Hash        string   `json:"hash"`
	CoverID     *int64   `json:"coverId"`
	Added       string   `json:"added"`
	Updated     string   `json:"updated"`
	Deleted     *string  `json:"deleted"`
	Marked      bool     `json:"marked"`
	Favorite    bool     `json:"favorite"`
	Artist      string   `json:"artist"`
	Album       string   `json:"album"`
	ArtistSort  string   `json:"artistSort"`
	AlbumSort   string   `json:"albumSort"`
	Title       string   `json:"title"`
	DiscNumber  int      `json:"discNumber"`
	TrackNumber int      `json:"trackNumber"`
	TrackTotal  int      `json:"trackTotal"`
	Genre       []string `json:"genre"`
	Length      float64  `json:"length"`
	Year        int      `json:"year"`
	Plays       int      `json:"plays"`
	Format      string   `json:"format"`
	Bitrate     int      `json:"bitrate"`
}

// Album is the API representation of an album aggregate.
type Album struct {
	Artist     string `json:"artist"`
	ArtistSort string `json:"artistSort"`
	Album      string `json:"album"`
	AlbumSort  string `json:"albumSort"`
	CoverID    *int64 `json:"coverId"`
	Year       int    `json:"year"`
	TrackCount int    `json:"trackCount"`
}

// Artist is the API representation of an artist aggregate.
type Artist struct {
	Artist     string `json:"artist"`
	ArtistSort string `json:"artistSort"`
	AlbumCount int    `json:"albumCount"`
	TrackCount int    `json:"trackCount"`
}

// Genre is the API representation of a genre entry.
type Genre struct {
	Genre      string `json:"genre"`
	TrackCount int    `json:"trackCount"`
}

// Decade is the API representation of a decade entry.
type Decade struct {
	Decade     int `json:"decade"`
	TrackCount int `json:"trackCount"`
}

// PlaylistRow is the API representation of a playlist row.
type PlaylistRow struct {
	ID    int64   `json:"id"`
	Name  string  `json:"name"`
	Items []int64 `json:"items"`
}

// SmartSearchRow is the API representation of a smartsearch row.
type SmartSearchRow struct {
	ID    int64  `json:"id"`
	Name  string `json:"name"`
	Query string `json:"query"`
}

// SongsResponse wraps a song list with a total count.
type SongsResponse struct {
	Songs []Song `json:"songs"`
	Total int    `json:"total"`
}

type musicAPI struct {
	db        *DB
	player    *Player
	cfg       config.Config
	musicDir  string
	backupDir string
	isAdmin   func(*http.Request) bool
}

// RegisterRoutes registers all /music/* HTTP handlers on mux.
func RegisterRoutes(mux *http.ServeMux, db *DB, player *Player, cfg config.Config, isAdmin func(*http.Request) bool) {
	a := &musicAPI{db: db, player: player, cfg: cfg, musicDir: cfg.Storage.Music, backupDir: cfg.Storage.Backup, isAdmin: isAdmin}

	mux.HandleFunc("/music/songs", a.handleSongs)
	mux.HandleFunc("/music/albums", a.handleAlbums)
	mux.HandleFunc("/music/artists", a.handleArtists)
	mux.HandleFunc("/music/genres", a.handleGenres)
	mux.HandleFunc("/music/decades", a.handleDecades)
	mux.HandleFunc("/music/cover/", a.handleCover)
	mux.HandleFunc("/music/state", a.handleState)
	mux.HandleFunc("/music/queue", a.handleQueue)
	mux.HandleFunc("/music/queue/enqueue", a.handleEnqueue)
	mux.HandleFunc("/music/queue/append", a.handleAppend)
	mux.HandleFunc("/music/queue/insert-at", a.handleInsertAt)
	mux.HandleFunc("/music/queue/remove", a.handleQueueRemove)
	mux.HandleFunc("/music/queue/move", a.handleQueueMove)
	mux.HandleFunc("/music/control", a.handleControl)
	mux.HandleFunc("/music/sync", a.handleSync)
	mux.HandleFunc("/music/playlists", a.handlePlaylists)
	mux.HandleFunc("/music/playlists/", a.handlePlaylist) // PUT/DELETE /music/playlists/{id} and GET /music/playlists/{id}/songs
	mux.HandleFunc("/music/smartsearches", a.handleSmartSearches)
	mux.HandleFunc("/music/smartsearches/", a.handleSmartSearch) // GET /music/smartsearches/{id}/songs, DELETE /music/smartsearches/{id}
	mux.HandleFunc("/music/songs/", a.handleSongByIDOrAction)    // /music/songs/{id}, /music/songs/{id}/mark, /music/songs/{id}/delete
	mux.HandleFunc("/music/songs/delete", a.handleSongsDelete)   // POST /music/songs/delete — bulk delete (admin)
	mux.HandleFunc("/music/songs/edit", a.handleSongsEdit)       // POST /music/songs/edit — edit metadata for one or more songs
	mux.HandleFunc("/music/audio-devices", a.handleAudioDevices) // GET /music/audio-devices — list available mpv audio devices
}

// jsonOK writes a JSON response with 200 OK.
func jsonOK(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

// scanSong scans one song row (with genre as JSON text) into a Song struct.
func scanSong(rows *sql.Rows) (*Song, error) {
	var s Song
	var genreJSON string
	var deleted sql.NullString
	var coverID sql.NullInt64
	err := rows.Scan(
		&s.ID, &s.Path, &s.Hash, &coverID,
		&s.Added, &s.Updated, &deleted, &s.Marked, &s.Favorite,
		&s.Artist, &s.Album, &s.ArtistSort, &s.AlbumSort,
		&s.Title, &s.DiscNumber, &s.TrackNumber, &s.TrackTotal,
		&genreJSON, &s.Length, &s.Year, &s.Plays, &s.Format, &s.Bitrate,
	)
	if err != nil {
		return nil, err
	}
	if coverID.Valid {
		id := coverID.Int64
		s.CoverID = &id
	}
	if deleted.Valid {
		s.Deleted = &deleted.String
	}
	json.Unmarshal([]byte(genreJSON), &s.Genre)
	if s.Genre == nil {
		s.Genre = []string{}
	}
	return &s, nil
}

func (a *musicAPI) handleSongs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	q := r.URL.Query()
	search := q.Get("search")
	artist := q.Get("artist")
	album := q.Get("album")
	genre := q.Get("genre")
	decade := q.Get("decade")
	offset, _ := strconv.Atoi(q.Get("offset"))

	conds := []string{"deleted IS NULL"}
	args := []any{}

	if search != "" {
		like := "%" + search + "%"
		conds = append(conds, "(artist LIKE ? OR album LIKE ? OR title LIKE ?)")
		args = append(args, like, like, like)
	}
	if artist != "" {
		conds = append(conds, "artist=?")
		args = append(args, artist)
	}
	if album != "" {
		conds = append(conds, "album=?")
		args = append(args, album)
	}
	if genre != "" {
		conds = append(conds, "EXISTS (SELECT 1 FROM json_each(genre) WHERE value=?)")
		args = append(args, genre)
	}
	if decade != "" {
		d, _ := strconv.Atoi(decade)
		conds = append(conds, "year >= ? AND year < ?")
		args = append(args, d, d+10)
	}

	where := "WHERE " + strings.Join(conds, " AND ")

	// Total count.
	var total int
	a.db.db.QueryRow("SELECT COUNT(*) FROM song "+where, args...).Scan(&total)

	// Results (no limit by default; OFFSET only meaningful with external paging).
	query := "SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate FROM song " +
		where + " ORDER BY artistSort,albumSort,discNumber,trackNumber"
	queryArgs := args
	if offset > 0 {
		query += " OFFSET ?"
		queryArgs = append(args, offset)
	}
	rows, err := a.db.db.Query(query, queryArgs...)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	songs := []Song{}
	for rows.Next() {
		s, err := scanSong(rows)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		songs = append(songs, *s)
	}
	jsonOK(w, SongsResponse{Songs: songs, Total: total})
}

func (a *musicAPI) handleAlbums(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	pct := a.cfg.Music.AlbumRequiredPercent
	rows, err := a.db.db.Query(`
		SELECT artist, artistSort, album, albumSort,
		       (SELECT coverId FROM song s2 WHERE s2.artist=s.artist AND s2.album=s.album AND s2.coverId IS NOT NULL AND s2.deleted IS NULL ORDER BY discNumber,trackNumber LIMIT 1) as coverId,
		       MAX(year) as year,
		       COUNT(CASE WHEN deleted IS NULL THEN 1 END) as trackCount
		FROM song s
		WHERE album != ''
		GROUP BY artist, album
		HAVING (COUNT(CASE WHEN deleted IS NULL THEN 1 END) * 100.0 / NULLIF(MAX(trackTotal),0)) >= ?
		    OR MAX(trackTotal) = 0
		ORDER BY artistSort, albumSort`, pct)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	albums := []Album{}
	for rows.Next() {
		var al Album
		var coverID sql.NullInt64
		if err := rows.Scan(&al.Artist, &al.ArtistSort, &al.Album, &al.AlbumSort, &coverID, &al.Year, &al.TrackCount); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if coverID.Valid {
			id := coverID.Int64
			al.CoverID = &id
		}
		albums = append(albums, al)
	}
	jsonOK(w, albums)
}

func (a *musicAPI) handleArtists(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	rows, err := a.db.db.Query(`
		SELECT artist, artistSort,
		       COUNT(DISTINCT album) as albumCount,
		       COUNT(*) as trackCount
		FROM song
		WHERE deleted IS NULL AND artist != ''
		GROUP BY artist
		ORDER BY artistSort`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	artists := []Artist{}
	for rows.Next() {
		var ar Artist
		if err := rows.Scan(&ar.Artist, &ar.ArtistSort, &ar.AlbumCount, &ar.TrackCount); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		artists = append(artists, ar)
	}
	jsonOK(w, artists)
}

func (a *musicAPI) handleGenres(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	rows, err := a.db.db.Query(`
		SELECT je.value, COUNT(*) as trackCount
		FROM song, json_each(genre) je
		WHERE deleted IS NULL AND je.value != ''
		GROUP BY je.value
		ORDER BY je.value`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	genres := []Genre{}
	for rows.Next() {
		var g Genre
		if err := rows.Scan(&g.Genre, &g.TrackCount); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		genres = append(genres, g)
	}
	jsonOK(w, genres)
}

func (a *musicAPI) handleDecades(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	rows, err := a.db.db.Query(`
		SELECT (year/10)*10 as decade, COUNT(*) as trackCount
		FROM song
		WHERE deleted IS NULL AND year > 0
		GROUP BY decade
		ORDER BY decade`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	decades := []Decade{}
	for rows.Next() {
		var d Decade
		if err := rows.Scan(&d.Decade, &d.TrackCount); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		decades = append(decades, d)
	}
	jsonOK(w, decades)
}

func (a *musicAPI) handleCover(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	idStr := strings.TrimPrefix(r.URL.Path, "/music/cover/")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	var contentType string
	var data []byte
	err = a.db.db.QueryRow(`SELECT contentType, data FROM cover WHERE id=?`, id).Scan(&contentType, &data)
	if err == sql.ErrNoRows {
		http.NotFound(w, r)
		return
	}
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "max-age=86400")
	w.Write(data)
}

func (a *musicAPI) handleState(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	jsonOK(w, a.player.StateMsg())
}

// QueueEntry is the API shape for one queue row (song + position metadata).
type QueueEntryResponse struct {
	SongID        int64 `json:"songId"`
	Song          *Song `json:"song"`
	OriginalIndex int   `json:"originalIndex"`
}

// QueueResponse is the full queue API response.
type QueueResponse struct {
	CurrentIndex int                  `json:"currentIndex"`
	Entries      []QueueEntryResponse `json:"entries"`
}

func (a *musicAPI) handleQueue(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		qs := a.player.QueueSnapshot()
		resp := QueueResponse{
			CurrentIndex: qs.CurrentIndex,
			Entries:      make([]QueueEntryResponse, 0, len(qs.Entries)),
		}
		for _, e := range qs.Entries {
			entry := QueueEntryResponse{SongID: e.SongID, OriginalIndex: e.OriginalIndex}
			rows, err := a.db.db.Query(
				`SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate FROM song WHERE id=?`,
				e.SongID,
			)
			if err == nil {
				if rows.Next() {
					if s, err := scanSong(rows); err == nil {
						entry.Song = s
					}
				}
				rows.Close()
			}
			resp.Entries = append(resp.Entries, entry)
		}
		jsonOK(w, resp)
	case http.MethodPost:
		var body struct {
			SongIDs []int64 `json:"songIds"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		ids, _ := json.Marshal(body.SongIDs)
		a.player.Control(ControlMsg{Action: "replace", Str: string(ids)})
		w.WriteHeader(http.StatusNoContent)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (a *musicAPI) handleEnqueue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		SongIDs []int64 `json:"songIds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	ids, _ := json.Marshal(body.SongIDs)
	a.player.Control(ControlMsg{Action: "enqueue", Str: string(ids)})
	w.WriteHeader(http.StatusNoContent)
}

func (a *musicAPI) handleAppend(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		SongIDs []int64 `json:"songIds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	ids, _ := json.Marshal(body.SongIDs)
	a.player.Control(ControlMsg{Action: "append", Str: string(ids)})
	w.WriteHeader(http.StatusNoContent)
}

func (a *musicAPI) handleInsertAt(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		SongIDs []int64 `json:"songIds"`
		Index   int     `json:"index"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	payload, _ := json.Marshal(struct {
		IDs   []int64 `json:"ids"`
		Index int     `json:"index"`
	}{body.SongIDs, body.Index})
	a.player.Control(ControlMsg{Action: "insertAt", Str: string(payload)})
	w.WriteHeader(http.StatusNoContent)
}

func (a *musicAPI) handleQueueRemove(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		Index int `json:"index"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	a.player.queue.RemoveAt(body.Index)
	a.player.saveState()
	a.player.broadcast()
	a.player.broadcastQueue()
	w.WriteHeader(http.StatusNoContent)
}

func (a *musicAPI) handleQueueMove(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		From int `json:"from"`
		To   int `json:"to"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	if !a.player.queue.MoveAt(body.From, body.To) {
		http.Error(w, "index out of range", http.StatusBadRequest)
		return
	}
	a.player.saveState()
	a.player.broadcast()
	a.player.broadcastQueue()
	w.WriteHeader(http.StatusNoContent)
}

func (a *musicAPI) handleControl(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var msg ControlMsg
	if err := json.NewDecoder(r.Body).Decode(&msg); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	a.player.Control(msg)
	w.WriteHeader(http.StatusNoContent)
}

// handleSongByIDOrAction handles:
//   - GET  /music/songs/{id}       — fetch a single song
//   - POST /music/songs/{id}/mark  — set/clear the mark flag
func (a *musicAPI) handleSongByIDOrAction(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/music/songs/")
	parts := strings.SplitN(rest, "/", 2)

	id, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}

	// /music/songs/{id}/mark
	if len(parts) == 2 && parts[1] == "mark" {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Marked bool `json:"marked"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		marked := 0
		if body.Marked {
			marked = 1
		}
		if _, err := a.db.db.Exec(`UPDATE song SET marked=? WHERE id=?`, marked, id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}

	// /music/songs/{id}/favorite
	if len(parts) == 2 && parts[1] == "favorite" {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Favorite bool `json:"favorite"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		fav := 0
		if body.Favorite {
			fav = 1
		}
		if _, err := a.db.db.Exec(`UPDATE song SET favorite=? WHERE id=?`, fav, id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}

	// /music/songs/{id}/lyrics — return parsed LRC lines (empty array if no file)
	if len(parts) == 2 && parts[1] == "lyrics" {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var songPath string
		err := a.db.db.QueryRow(`SELECT path FROM song WHERE id=? AND deleted IS NULL`, id).Scan(&songPath)
		if err == sql.ErrNoRows {
			http.NotFound(w, r)
			return
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		lrcData, err := os.ReadFile(lrcPath(songPath))
		var llines []LyricLine
		if err == nil {
			llines = parseLRC(lrcData)
		}
		if llines == nil {
			llines = []LyricLine{}
		}
		jsonOK(w, map[string][]LyricLine{"lines": llines})
		return
	}

	// /music/songs/{id} — single song lookup
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	rows, err := a.db.db.Query(
		`SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate FROM song WHERE id=?`,
		id,
	)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()
	if !rows.Next() {
		http.NotFound(w, r)
		return
	}
	s, err := scanSong(rows)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	jsonOK(w, s)
}

func (a *musicAPI) handleSync(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !a.isAdmin(r) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	go func() {
		syncer := NewSyncer(a.db, a.cfg.Music, a.musicDir, a.backupDir, SyncOptions{})
		if err := syncer.Run(context.Background()); err != nil {
			log.Println("music sync error:", err)
		}
	}()
	w.WriteHeader(http.StatusAccepted)
}

func (a *musicAPI) handlePlaylists(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		rows, err := a.db.db.Query(`SELECT id, name, items FROM playlist ORDER BY name`)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		defer rows.Close()
		playlists := []PlaylistRow{}
		for rows.Next() {
			var pl PlaylistRow
			var itemsJSON string
			if err := rows.Scan(&pl.ID, &pl.Name, &itemsJSON); err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			json.Unmarshal([]byte(itemsJSON), &pl.Items)
			if pl.Items == nil {
				pl.Items = []int64{}
			}
			playlists = append(playlists, pl)
		}
		jsonOK(w, playlists)

	case http.MethodPost:
		var body struct {
			Name  string  `json:"name"`
			Items []int64 `json:"items"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		if body.Items == nil {
			body.Items = []int64{}
		}
		itemsJSON, _ := json.Marshal(body.Items)
		res, err := a.db.db.Exec(`INSERT INTO playlist(name,items) VALUES(?,?)`, body.Name, string(itemsJSON))
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		id, _ := res.LastInsertId()
		jsonOK(w, map[string]int64{"id": id})

	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleSongsDelete handles POST /music/songs/delete — permanently deletes songs by ID (admin only).
func (a *musicAPI) handleSongsDelete(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !a.isAdmin(r) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	var body struct {
		IDs []int64 `json:"ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	if len(body.IDs) == 0 {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	idsJSON, _ := json.Marshal(body.IDs)
	if _, err := a.db.db.Exec(
		`DELETE FROM song WHERE id IN (SELECT value FROM json_each(?))`,
		string(idsJSON),
	); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (a *musicAPI) handlePlaylist(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/music/playlists/")
	parts := strings.SplitN(rest, "/", 2)
	id, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}

	// GET /music/playlists/{id}/songs — fetch full song objects in playlist order.
	if len(parts) == 2 && parts[1] == "songs" {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var itemsJSON string
		if err := a.db.db.QueryRow(`SELECT items FROM playlist WHERE id=?`, id).Scan(&itemsJSON); err != nil {
			if err == sql.ErrNoRows {
				http.NotFound(w, r)
			} else {
				http.Error(w, err.Error(), http.StatusInternalServerError)
			}
			return
		}
		var itemIDs []int64
		json.Unmarshal([]byte(itemsJSON), &itemIDs)
		if itemIDs == nil {
			itemIDs = []int64{}
		}
		// Fetch songs in order matching item IDs (preserve playlist order).
		if len(itemIDs) == 0 {
			jsonOK(w, SongsResponse{Songs: []Song{}, Total: 0})
			return
		}
		// Build an ORDER BY CASE to preserve playlist order.
		idsJSON, _ := json.Marshal(itemIDs)
		rows, err := a.db.db.Query(
			`SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate
			 FROM song WHERE id IN (SELECT value FROM json_each(?))`,
			string(idsJSON),
		)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		defer rows.Close()
		byID := map[int64]*Song{}
		for rows.Next() {
			s, err := scanSong(rows)
			if err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			byID[s.ID] = s
		}
		// Return in playlist order, skipping deleted/missing songs.
		songs := []Song{}
		for _, sid := range itemIDs {
			if s, ok := byID[sid]; ok {
				songs = append(songs, *s)
			}
		}
		jsonOK(w, SongsResponse{Songs: songs, Total: len(songs)})
		return
	}

	switch r.Method {
	case http.MethodPut:
		var body struct {
			Name  string  `json:"name"`
			Items []int64 `json:"items"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		if body.Items == nil {
			body.Items = []int64{}
		}
		itemsJSON, _ := json.Marshal(body.Items)
		if _, err := a.db.db.Exec(`UPDATE playlist SET name=?, items=? WHERE id=?`, body.Name, string(itemsJSON), id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)

	case http.MethodDelete:
		if _, err := a.db.db.Exec(`DELETE FROM playlist WHERE id=?`, id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)

	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleSmartSearches handles GET/POST /music/smartsearches.
func (a *musicAPI) handleSmartSearches(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		rows, err := a.db.db.Query(`SELECT id, name, query FROM smartsearch ORDER BY name`)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		defer rows.Close()
		result := []SmartSearchRow{}
		for rows.Next() {
			var sp SmartSearchRow
			if err := rows.Scan(&sp.ID, &sp.Name, &sp.Query); err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			result = append(result, sp)
		}
		jsonOK(w, result)

	case http.MethodPost:
		var body struct {
			Name  string `json:"name"`
			Query string `json:"query"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		body.Name = strings.TrimSpace(body.Name)
		body.Query = strings.TrimSpace(body.Query)
		if body.Name == "" || body.Query == "" {
			http.Error(w, "name and query are required", http.StatusBadRequest)
			return
		}
		if strings.Contains(body.Query, ";") {
			http.Error(w, "query may not contain semicolons", http.StatusBadRequest)
			return
		}
		res, err := a.db.db.Exec(`INSERT INTO smartsearch (name, query) VALUES (?, ?)`, body.Name, body.Query)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		id, _ := res.LastInsertId()
		jsonOK(w, SmartSearchRow{ID: id, Name: body.Name, Query: body.Query})

	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleSmartSearch handles requests to /music/smartsearches/{id}[/songs].
// GET /music/smartsearches/{id}/songs — execute the stored WHERE clause.
// DELETE /music/smartsearches/{id}   — delete the smart search.
func (a *musicAPI) handleSmartSearch(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/music/smartsearches/")
	parts := strings.SplitN(rest, "/", 2)
	id, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}

	// DELETE /music/smartsearches/{id}
	if len(parts) == 1 {
		if r.Method != http.MethodDelete {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if _, err := a.db.db.Exec(`DELETE FROM smartsearch WHERE id=?`, id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}

	// GET /music/smartsearches/{id}/songs
	if parts[1] != "songs" || r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}

	var query string
	if err := a.db.db.QueryRow(`SELECT query FROM smartsearch WHERE id=?`, id).Scan(&query); err != nil {
		if err == sql.ErrNoRows {
			http.NotFound(w, r)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}

	// Sanity check: reject queries containing a semicolon.
	if strings.Contains(query, ";") {
		http.Error(w, "query may not contain semicolons", http.StatusBadRequest)
		return
	}

	// query is a WHERE clause fragment, e.g. "length > 300"
	fullQuery := "SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate FROM song WHERE deleted IS NULL AND (" + query + ")"
	rows, err := a.db.db.Query(fullQuery)
	if err != nil {
		http.Error(w, "query error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()
	songs := []Song{}
	for rows.Next() {
		s, err := scanSong(rows)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		songs = append(songs, *s)
	}
	jsonOK(w, SongsResponse{Songs: songs, Total: len(songs)})
}

// handlePlaylistSongs handles GET /music/playlists/{id}/songs — fetch songs in playlist order.
// This is reached via the /music/playlists/ prefix handler.

// SongEditFields holds the metadata fields that may be updated by an edit request.
// Each field is a pointer so the caller can omit fields they don't want to change.
type SongEditFields struct {
	Title       *string   `json:"title"`
	Artist      *string   `json:"artist"`
	Album       *string   `json:"album"`
	ArtistSort  *string   `json:"artistSort"`
	AlbumSort   *string   `json:"albumSort"`
	TrackNumber *int      `json:"trackNumber"`
	TrackTotal  *int      `json:"trackTotal"`
	DiscNumber  *int      `json:"discNumber"`
	Year        *int      `json:"year"`
	Genre       *[]string `json:"genre"`
}

// SongEditRequest is the body of POST /music/songs/edit.
type SongEditRequest struct {
	IDs    []int64        `json:"ids"`
	Fields SongEditFields `json:"fields"`
}

// handleSongsEdit handles POST /music/songs/edit.
// It updates ID3 tags on the files, renames them to canonical paths, and
// updates the database to reflect the new metadata/path/hash.
func (a *musicAPI) handleSongsEdit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body SongEditRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	if len(body.IDs) == 0 {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	musicDir := a.musicDir

	for _, id := range body.IDs {
		// Load current song from DB.
		rows, err := a.db.db.Query(
			`SELECT id,path,hash,coverId,added,updated,deleted,marked,favorite,artist,album,artistSort,albumSort,title,discNumber,trackNumber,trackTotal,genre,length,year,plays,format,bitrate FROM song WHERE id=?`,
			id,
		)
		if err != nil {
			log.Printf("music edit: load song %d: %v", id, err)
			continue
		}
		if !rows.Next() {
			rows.Close()
			log.Printf("music edit: song %d not found", id)
			continue
		}
		song, err := scanSong(rows)
		rows.Close()
		if err != nil {
			log.Printf("music edit: scan song %d: %v", id, err)
			continue
		}

		// Apply incoming field overrides.
		newArtist := song.Artist
		newAlbum := song.Album
		newArtistSort := song.ArtistSort
		newAlbumSort := song.AlbumSort
		newTitle := song.Title
		newTrackNumber := song.TrackNumber
		newTrackTotal := song.TrackTotal
		newDiscNumber := song.DiscNumber
		newYear := song.Year
		newGenre := song.Genre

		f := body.Fields
		if f.Artist != nil {
			newArtist = *f.Artist
		}
		if f.Album != nil {
			newAlbum = *f.Album
		}
		if f.ArtistSort != nil {
			newArtistSort = *f.ArtistSort
		} else if f.Artist != nil {
			newArtistSort = sortName(newArtist)
		}
		if f.AlbumSort != nil {
			newAlbumSort = *f.AlbumSort
		} else if f.Album != nil {
			newAlbumSort = sortName(newAlbum)
		}
		if f.Title != nil {
			newTitle = *f.Title
		}
		if f.TrackNumber != nil {
			newTrackNumber = *f.TrackNumber
		}
		if f.TrackTotal != nil {
			newTrackTotal = *f.TrackTotal
		}
		if f.DiscNumber != nil {
			newDiscNumber = *f.DiscNumber
		}
		if f.Year != nil {
			newYear = *f.Year
		}
		if f.Genre != nil {
			newGenre = *f.Genre
		}

		// Write new tags via ffmpeg and move to canonical path.
		newPath, newHash, err := rewriteTags(song.Path, rewriteTagsArgs{
			Title:       newTitle,
			Artist:      newArtist,
			Album:       newAlbum,
			TrackNumber: newTrackNumber,
			TrackTotal:  newTrackTotal,
			DiscNumber:  newDiscNumber,
			Year:        newYear,
			Genre:       newGenre,
		}, musicDir, newArtist, newAlbum, newTrackNumber)
		if err != nil {
			log.Printf("music edit: rewrite tags for song %d (%s): %v", id, song.Path, err)
			http.Error(w, fmt.Sprintf("failed to rewrite tags for song %d: %v", id, err), http.StatusInternalServerError)
			return
		}

		// Update DB.
		genreJSON, _ := json.Marshal(newGenre)
		now := time.Now().UTC().Format(time.RFC3339)
		_, err = a.db.db.Exec(`
			UPDATE song SET
				path=?, hash=?, updated=?,
				artist=?, album=?, artistSort=?, albumSort=?,
				title=?, discNumber=?, trackNumber=?, trackTotal=?,
				genre=?, year=?
			WHERE id=?`,
			newPath, newHash, now,
			newArtist, newAlbum, newArtistSort, newAlbumSort,
			newTitle, newDiscNumber, newTrackNumber, newTrackTotal,
			string(genreJSON), newYear,
			id,
		)
		if err != nil {
			log.Printf("music edit: update DB for song %d: %v", id, err)
			http.Error(w, fmt.Sprintf("failed to update database for song %d: %v", id, err), http.StatusInternalServerError)
			return
		}
		log.Printf("music edit: updated song %d → %s", id, newPath)
	}

	w.WriteHeader(http.StatusNoContent)
}

type rewriteTagsArgs struct {
	Title       string
	Artist      string
	Album       string
	TrackNumber int
	TrackTotal  int
	DiscNumber  int
	Year        int
	Genre       []string
}

// rewriteTags uses ffmpeg to copy the audio stream and overwrite metadata tags,
// writes the result to a temp file, then moves it to the canonical destination path.
// Returns the final path and sha256 hash of the new file.
func rewriteTags(srcPath string, tags rewriteTagsArgs, musicDir, artist, album string, trackNumber int) (string, string, error) {
	ext := strings.ToLower(filepath.Ext(srcPath))
	dir := filepath.Dir(srcPath)

	trackStr := ""
	if tags.TrackNumber > 0 {
		if tags.TrackTotal > 0 {
			trackStr = fmt.Sprintf("%d/%d", tags.TrackNumber, tags.TrackTotal)
		} else {
			trackStr = fmt.Sprintf("%d", tags.TrackNumber)
		}
	}
	discStr := ""
	if tags.DiscNumber > 0 {
		discStr = fmt.Sprintf("%d", tags.DiscNumber)
	}
	genreStr := strings.Join(tags.Genre, "; ")

	metaArgs := []string{
		"-metadata", "title=" + tags.Title,
		"-metadata", "artist=" + tags.Artist,
		"-metadata", "album=" + tags.Album,
		"-metadata", "date=" + fmt.Sprintf("%d", tags.Year),
		"-metadata", "genre=" + genreStr,
	}
	if trackStr != "" {
		metaArgs = append(metaArgs, "-metadata", "track="+trackStr)
	}
	if discStr != "" {
		metaArgs = append(metaArgs, "-metadata", "disc="+discStr)
	}

	// Write to a temp file in the same directory so the rename is atomic.
	tmp, err := os.CreateTemp(dir, "edit-*"+ext)
	if err != nil {
		return "", "", fmt.Errorf("create temp: %w", err)
	}
	tmp.Close()
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath) // no-op once renamed

	args := []string{"-y", "-i", srcPath, "-map", "0", "-map_metadata", "0", "-codec", "copy"}
	args = append(args, metaArgs...)
	args = append(args, tmpPath)

	cmd := exec.Command("ffmpeg", args...)
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", fmt.Errorf("ffmpeg: %w\n%s", err, out)
	}

	// Compute sha256 of the new file.
	data, err := os.ReadFile(tmpPath)
	if err != nil {
		return "", "", fmt.Errorf("read temp: %w", err)
	}
	h := sha256.Sum256(data)
	newHash := hex.EncodeToString(h[:])

	// Determine canonical dest path.
	destPath := canonicalPath(musicDir, srcPath, artist, album, trackNumber, tags.Title)

	// Handle collision if different from source.
	if _, err := os.Stat(destPath); err == nil && destPath != srcPath {
		destExt := filepath.Ext(destPath)
		destBase := strings.TrimSuffix(filepath.Base(destPath), destExt)
		destDir := filepath.Dir(destPath)
		for i := 2; ; i++ {
			candidate := filepath.Join(destDir, fmt.Sprintf("%s (%d)%s", destBase, i, destExt))
			if _, err := os.Stat(candidate); os.IsNotExist(err) {
				destPath = candidate
				break
			}
		}
	}

	if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
		return "", "", fmt.Errorf("mkdir: %w", err)
	}

	if err := os.Rename(tmpPath, destPath); err != nil {
		return "", "", fmt.Errorf("rename to dest: %w", err)
	}

	// Remove old file if path changed.
	if srcPath != destPath {
		os.Remove(srcPath)
	}

	return destPath, newHash, nil
}

// AudioDevice is a single entry returned by GET /music/audio-devices.
type AudioDevice struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

// handleAudioDevices handles GET /music/audio-devices.
// It runs "mpv --audio-device=help", parses the output, and returns a curated
// list of useful output devices.
func (a *musicAPI) handleAudioDevices(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	out, err := exec.Command("mpv", "--audio-device=help").CombinedOutput()
	if err != nil {
		// mpv exits non-zero when printing help; that's fine — use whatever output we got.
		if len(out) == 0 {
			http.Error(w, "mpv not available", http.StatusInternalServerError)
			return
		}
	}

	devices := parseMpvAudioDevices(string(out))
	jsonOK(w, devices)
}

// parseMpvAudioDevices parses the output of "mpv --audio-device=help" and
// returns only "auto" and "alsa/sysdefault*" entries.
func parseMpvAudioDevices(output string) []AudioDevice {
	var devices []AudioDevice
	for _, line := range strings.Split(output, "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "'") {
			continue
		}
		// Each line: 'id' (human name)
		line = strings.TrimPrefix(line, "'")
		idx := strings.Index(line, "' (")
		if idx < 0 {
			continue
		}
		id := line[:idx]
		name := strings.TrimSuffix(line[idx+3:], ")")

		if id == "auto" || id == "alsa/sysdefault" || strings.HasPrefix(id, "alsa/sysdefault:") {
			devices = append(devices, AudioDevice{ID: id, Name: name})
		}
	}
	return devices
}
