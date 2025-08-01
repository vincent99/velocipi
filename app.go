package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"velocity/hardware/brightness"
	"velocity/hardware/lightsensor"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App struct
type App struct {
	ctx    context.Context
	light  *lightsensor.LightSensor
	bright *brightness.Brightness

	stopTick chan struct{}
}

// NewApp creates a new App application struct
func NewApp() *App {
	return &App{}
}

// startup is called when the app starts. The context is saved
// so we can call the runtime methods
func (a *App) startup(ctx context.Context) {
	fmt.Println("Startup")
	a.ctx = ctx
}

func (a *App) ready(ctx context.Context) {
	fmt.Println("Ready")
	ticker := time.NewTicker(10 * time.Second)

	light, err := lightsensor.NewLightSensor()
	if err != nil {
		log.Fatal("Failed to find light sensor", err)
	}

	bright, err := brightness.NewBrightness(&brightness.Config{
		Sensor:        light,
		MinBrightness: 40,
		MinLux:        5,
		MaxLux:        100,
	})
	if err != nil {
		log.Fatal("Failed to find brightness control", err)
	}

	a.light = light
	a.bright = bright

	quit := make(chan struct{})
	a.stopTick = quit

	go func() {
		for {
			select {
			case <-ticker.C:
				t := time.Now().Format(time.DateTime)
				runtime.EventsEmit(ctx, "foo", t)
			case <-quit:
				ticker.Stop()
				return
			}
		}
	}()

}

func (a *App) unload(ctx context.Context) (prevent bool) {
	fmt.Println("Unloading")
	close(a.stopTick)

	return false
}

func (a *App) shutdown(ctx context.Context) {
	fmt.Println("Shutdown")
}

// Greet returns a greeting for the given name
func (a *App) Greet(name string) string {
	return fmt.Sprintf("Hello %s, It's show time!", name)
}
