// musicsync scans the music directory and synchronises it with the music
// database. Run from the repository root:
//
//	go run ./cmd/musicsync/
package main

import (
	"context"
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/music"
)

func main() {
	force := flag.Bool("force", false, "re-read metadata for all files, ignoring cached mtime")
	rename := flag.Bool("rename", false, "reorganise music directory into [artist]/[album]/... structure")
	flag.Parse()

	result := config.Load()
	cfg := result.Config

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	db, err := music.OpenAndMigrate("schemas")
	if err != nil {
		log.Fatal("musicsync:", err)
	}
	defer db.Close()

	opts := music.SyncOptions{
		Force:  *force,
		Rename: *rename,
	}
	syncer := music.NewSyncer(db, cfg.Music, opts)
	if err := syncer.Run(ctx); err != nil {
		log.Fatal("musicsync:", err)
	}
}
