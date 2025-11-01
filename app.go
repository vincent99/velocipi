package main

import (
	"context"
	"fmt"
	"time"

	"velocity/hardware/brightness"
	"velocity/hardware/lightsensor"
	"velocity/hardware/tpms"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App struct
type App struct {
	ctx    context.Context
	light  *lightsensor.LightSensor
	bright *brightness.Brightness

	stopTick chan bool
}

// NewApp creates a new App application struct
func NewApp() *App {
	return &App{
	}
}

// startup is called when the app starts. The context is saved
// so we can call the runtime methods
func (a *App) startup(ctx context.Context) {
	fmt.Println("Startup")
	a.ctx = ctx
}

func (a *App) ready(ctx context.Context) {
	fmt.Println("Ready")
	ticker := time.NewTicker(1 * time.Second)

	_, err := tpms.Listen(func (t *tpms.Tire) {
		runtime.EventsEmit(ctx, "tire", t)
	})

	if err != nil {
		fmt.Println("Failed to init TPMS", err)
	}

	// wave3, err := wave.New()
	// if err != nil {
	// 	fmt.Println("Failed to init EcoFlow Wave", err)
	// }

	// err = wave3.Connect()
	// if err != nil {
	// 	fmt.Println("Failed to find EcoFlow Wave", err)
	// }

	light, err := lightsensor.NewLightSensor()
	if err != nil {
		fmt.Println("Failed to find light sensor", err)
	}

	bright, err := brightness.NewBrightness(&brightness.Config{
		Sensor:        light,
		Speed: 	       500,
		MinBrightness: 40,
		MinLux:        2,
		MaxLux:        100,
	})
	if err != nil {
		fmt.Println("Failed to find brightness control", err)
	}

	a.light = light
	a.bright = bright

	quit := make(chan bool)
	a.stopTick = quit

	go func() {
		for {
			select {
			case <-ticker.C:
				t := time.Now()
				runtime.EventsEmit(ctx, "ticker", t)
			case <-quit:
				ticker.Stop()
				return
			}
		}
	}()

}

func (a *App) unload(ctx context.Context) (prevent bool) {
	fmt.Println("Unloading")
	a.stopTick <- true
	return false
}

func (a *App) shutdown(ctx context.Context) {
	fmt.Println("Shutdown")
}

/*
// Greet returns a greeting for the given name
func (a *App) Greet(name string) string {
	return fmt.Sprintf("Hello %s, It's show time!", name)
}
*/
