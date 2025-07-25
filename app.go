package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"velocity/hardware/lightsensor"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App struct
type App struct {
	ctx      context.Context
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

	fmt.Println("Connecting")
	light, err := lightsensor.NewLightSensor()
	if err != nil {
		log.Fatal("Failed to find light sensor", err)
	}

	fmt.Println("Connected", light.IsConnected())

	power, _ := light.GetPower()
	fmt.Println("Power", power)

	powerSave, mode, _ := light.GetPowerSave()
	fmt.Println("Power Save", powerSave, mode)

	gain, _ := light.GetGain()
	fmt.Println("Gain", gain)

	integration, _ := light.GetIntegrationTime()
	fmt.Println("Integration", integration)

	protect, _ := light.GetPersistenceProtect()
	fmt.Println("Protect", protect)

	interrupt, _ := light.GetInterruptEnabled()
	low, high, _ := light.GetInterruptThresholds()
	fmt.Println("Interrupt", interrupt, low, high)

	quit := make(chan struct{})
	a.stopTick = quit

	go func() {
		for {
			select {
			case <-ticker.C:
				t := time.Now().Format(time.DateTime)
				ambient, _ := light.GetAmbientLux()
				white, _ := light.GetWhiteLux()
				fmt.Println("Tick: ", t, ", Ambient: ", ambient, ", White:", white)
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
