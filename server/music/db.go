package music

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// DB wraps an *sql.DB and provides music-specific helpers.
type DB struct {
	db     *sql.DB
	dbPath string
}

// Open opens (or creates) the SQLite database at dbPath.
func Open(dbPath string) (*DB, error) {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("music: open db: %w", err)
	}

	// Enable WAL mode and foreign keys.
	if _, err := db.Exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`); err != nil {
		db.Close()
		return nil, fmt.Errorf("music: pragma: %w", err)
	}

	return &DB{db: db, dbPath: dbPath}, nil
}

// Close closes the underlying database connection.
func (d *DB) Close() error {
	return d.db.Close()
}

// Backup copies the database file to backupDir/music-YYYY-MM-DD-HHMMSS.sqlite.
// Returns nil if the database file does not exist yet.
func (d *DB) Backup(backupDir string) error {
	if _, err := os.Stat(d.dbPath); os.IsNotExist(err) {
		return nil
	}
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		return fmt.Errorf("music: backup mkdir: %w", err)
	}
	dst := filepath.Join(backupDir, "music-"+time.Now().Format("2006-01-02-150405")+".sqlite")
	src, err := os.Open(d.dbPath)
	if err != nil {
		return fmt.Errorf("music: backup open src: %w", err)
	}
	defer src.Close()
	out, err := os.Create(dst)
	if err != nil {
		return fmt.Errorf("music: backup create dst: %w", err)
	}
	defer out.Close()
	if _, err := io.Copy(out, src); err != nil {
		return fmt.Errorf("music: backup copy: %w", err)
	}
	log.Println("music: backed up db to", dst)
	return nil
}

// Migrate reads all NNN-*.sql files from schemasDir, determines which have not
// been applied (based on state.dbVersion), backs up the DB before any migration,
// then applies pending migrations in a transaction.
func (d *DB) Migrate(schemasDir, backupDir string) error {
	// Ensure state table exists so we can read dbVersion.
	if _, err := d.db.Exec(`CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT 'null')`); err != nil {
		return fmt.Errorf("music: create state table: %w", err)
	}

	// Current version (0 means never migrated).
	var current int
	if err := d.GetState("dbVersion", &current); err != nil {
		current = 0
	}

	// Collect and sort migration files.
	entries, err := os.ReadDir(schemasDir)
	if err != nil {
		return fmt.Errorf("music: read schemas dir %q: %w", schemasDir, err)
	}

	type migration struct {
		num  int
		path string
	}
	var migrations []migration
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasSuffix(name, ".sql") {
			continue
		}
		parts := strings.SplitN(name, "-", 2)
		if len(parts) < 1 {
			continue
		}
		num, err := strconv.Atoi(parts[0])
		if err != nil {
			continue
		}
		migrations = append(migrations, migration{num: num, path: filepath.Join(schemasDir, name)})
	}
	sort.Slice(migrations, func(i, j int) bool {
		return migrations[i].num < migrations[j].num
	})

	// Find pending migrations.
	var pending []migration
	for _, m := range migrations {
		if m.num > current {
			pending = append(pending, m)
		}
	}
	if len(pending) == 0 {
		return nil
	}

	// Backup before first migration.
	if err := d.Backup(backupDir); err != nil {
		log.Println("music: backup warning:", err)
	}

	// Apply each pending migration.
	for _, m := range pending {
		data, err := os.ReadFile(m.path)
		if err != nil {
			return fmt.Errorf("music: read migration %s: %w", m.path, err)
		}
		tx, err := d.db.Begin()
		if err != nil {
			return fmt.Errorf("music: begin tx for migration %d: %w", m.num, err)
		}
		if _, err := tx.Exec(string(data)); err != nil {
			tx.Rollback()
			return fmt.Errorf("music: apply migration %d: %w", m.num, err)
		}
		// Update dbVersion inside the same transaction.
		vJSON, _ := json.Marshal(m.num)
		if _, err := tx.Exec(`INSERT INTO state(key,value) VALUES('dbVersion',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value`, string(vJSON)); err != nil {
			tx.Rollback()
			return fmt.Errorf("music: update dbVersion after migration %d: %w", m.num, err)
		}
		if err := tx.Commit(); err != nil {
			return fmt.Errorf("music: commit migration %d: %w", m.num, err)
		}
		log.Printf("music: applied migration %d (%s)", m.num, filepath.Base(m.path))
	}
	return nil
}

// GetState reads a JSON-encoded value from the state table into dest.
// Returns nil if the key is not found (dest is left unchanged).
func (d *DB) GetState(key string, dest any) error {
	var raw string
	err := d.db.QueryRow(`SELECT value FROM state WHERE key=?`, key).Scan(&raw)
	if err == sql.ErrNoRows {
		return nil
	}
	if err != nil {
		return fmt.Errorf("music: get state %q: %w", key, err)
	}
	return json.Unmarshal([]byte(raw), dest)
}

// SetState writes a JSON-encoded value to the state table.
func (d *DB) SetState(key string, val any) error {
	data, err := json.Marshal(val)
	if err != nil {
		return fmt.Errorf("music: marshal state %q: %w", key, err)
	}
	_, err = d.db.Exec(
		`INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value`,
		key, string(data),
	)
	if err != nil {
		return fmt.Errorf("music: set state %q: %w", key, err)
	}
	return nil
}

// OpenAndMigrate opens (or creates) the music.sqlite database and runs all
// pending schema migrations. It does not check minDbVersion, making it safe
// to call from the sync CLI regardless of server config.
func OpenAndMigrate(schemasDir, backupDir string) (*DB, error) {
	d, err := Open("music.sqlite")
	if err != nil {
		return nil, fmt.Errorf("cannot open db: %w", err)
	}
	if err := d.Migrate(schemasDir, backupDir); err != nil {
		d.Close()
		return nil, fmt.Errorf("migration error: %w", err)
	}
	return d, nil
}

// InitDB opens the music.sqlite database, runs migrations, and checks the
// minimum required version. Returns (nil, false) if the music subsystem should
// be disabled due to a migration error or version mismatch.
func InitDB(cfg MusicConfig, schemasDir, backupDir string) (*DB, bool) {
	d, err := OpenAndMigrate(schemasDir, backupDir)
	if err != nil {
		log.Println("music:", err)
		return nil, false
	}

	var version int
	if err := d.GetState("dbVersion", &version); err != nil {
		log.Println("music: cannot read dbVersion:", err)
		d.Close()
		return nil, false
	}
	if version < cfg.MinDbVersion {
		log.Printf("music: db version %d is below required minimum %d — music disabled", version, cfg.MinDbVersion)
		d.Close()
		return nil, false
	}

	return d, true
}
