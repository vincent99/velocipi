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
	clean := flag.Bool("clean", false, "delete songs marked deleted (not in any playlist) and orphaned cover art")
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

	syncer := music.NewSyncer(db, cfg.Music)
	if err := syncer.Run(ctx); err != nil {
		log.Fatal("musicsync:", err)
	}

	if *clean {
		if err := syncer.Clean(ctx); err != nil {
			log.Fatal("musicsync clean:", err)
		}
	}
}
