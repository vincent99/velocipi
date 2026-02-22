package main

import (
	"context"
	"encoding/json"
	"log"
	"math"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sort"
	"strings"
	"syscall"
	"time"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/dvr"
	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/oled"
)

func main() {
	result := config.Load()
	cfg := result.Config
	defaults := result.Defaults
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	// Start LED blinking immediately as a startup indicator.
	// It will be turned off once the first frame blits to the OLED.
	if e := hardware.Expander(); e != nil {
		hardware.LED().Blink(e, 250*time.Millisecond)
	}

	// Initialise the OLED display. Non-fatal if the hardware isn't present.
	var display *oled.OLED
	if o, err := oled.New(oled.Config{
		SPIPort:  cfg.OLED.SPIPort,
		SPISpeed: cfg.OLEDSPIFreq,
		GPIOChip: cfg.OLED.GPIOChip,
		DCPin:    cfg.OLED.DCPin,
		ResetPin: cfg.OLED.ResetPin,
		Flip:     cfg.OLED.Flip,
	}, cfg.UI.Panel.Width, cfg.UI.Panel.Height); err != nil {
		log.Println("oled: init error (continuing without display):", err)
	} else {
		display = o
	}

	// Initialize hub immediately so wsHandler is never called with a nil hub.
	// browserCtx is set after the browser starts up below.
	hub = newHub(nil, cfg, display)

	// Start HTTP server first so the browser can reach /app when it navigates.
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", wsHandler)
	mux.HandleFunc("/screen", screenHandler)
	mux.HandleFunc("/config", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			var (
				data []byte
				err  error
			)
			if r.URL.Query().Get("full") == "true" {
				data, err = json.Marshal(struct {
					Config   *config.Config `json:"config"`
					Defaults *config.Config `json:"defaults"`
				}{cfg, defaults})
			} else {
				data, err = json.Marshal(cfg.UI)
			}
			if err != nil {
				http.Error(w, "config marshal error", http.StatusInternalServerError)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.Write(data)
		case http.MethodPost:
			var updated config.Config
			if err := json.NewDecoder(r.Body).Decode(&updated); err != nil {
				http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
				return
			}
			if err := config.SaveOverrides(updated, *defaults); err != nil {
				http.Error(w, "save error: "+err.Error(), http.StatusInternalServerError)
				return
			}
			*cfg = updated
			w.WriteHeader(http.StatusNoContent)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
	// /cameras — list configured cameras sorted by sort then alphabetically.
	mux.HandleFunc("/cameras", func(w http.ResponseWriter, r *http.Request) {
		type cameraInfo struct {
			Name string `json:"name"`
		}
		cams := make([]config.CameraConfig, len(cfg.DVR.Cameras))
		copy(cams, cfg.DVR.Cameras)
		sort.Slice(cams, func(i, j int) bool {
			si := math.MaxInt
			sj := math.MaxInt
			if cams[i].Sort != nil {
				si = *cams[i].Sort
			}
			if cams[j].Sort != nil {
				sj = *cams[j].Sort
			}
			if si != sj {
				return si < sj
			}
			return strings.ToLower(cams[i].Name) < strings.ToLower(cams[j].Name)
		})
		infos := make([]cameraInfo, 0, len(cams))
		for _, c := range cams {
			infos = append(infos, cameraInfo{Name: c.Name})
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(infos)
	})

	dvrManager := dvr.New(cfg.DVR)

	// /mpegts/{camera} — on-demand MPEG-TS stream piped directly from ffmpeg.
	// The browser plays this with mpegts.js via MSE. The stream runs until the
	// client disconnects or the server shuts down.
	mux.HandleFunc("/mpegts/", func(w http.ResponseWriter, r *http.Request) {
		cameraName := r.URL.Path[len("/mpegts/"):]
		if cameraName == "" {
			http.NotFound(w, r)
			return
		}
		if err := dvrManager.StreamMPEGTS(r.Context(), cameraName, w); err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
		}
	})

	// /mpegts/active?id=<clientID>&camera=<name> — persistent MPEG-TS stream
	// that starts on <name> and follows whichever camera the client selects via
	// /mpegts/select. Each client tab uses a unique id so selections are independent.
	mux.HandleFunc("/mpegts/active", func(w http.ResponseWriter, r *http.Request) {
		clientID := r.URL.Query().Get("id")
		camera := r.URL.Query().Get("camera")
		if clientID == "" || camera == "" {
			http.Error(w, "id and camera params required", http.StatusBadRequest)
			return
		}
		if err := dvrManager.StreamActive(r.Context(), clientID, camera, w); err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
		}
	})

	// /mpegts/select?id=<clientID>&camera=<name> — switches the active camera
	// for the given client session without reconnecting the stream.
	mux.HandleFunc("/mpegts/select", func(w http.ResponseWriter, r *http.Request) {
		clientID := r.URL.Query().Get("id")
		camera := r.URL.Query().Get("camera")
		if clientID == "" || camera == "" {
			http.Error(w, "id and camera params required", http.StatusBadRequest)
			return
		}
		if err := dvrManager.SelectCamera(clientID, camera); err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	// /snapshot/{camera} — multipart/x-mixed-replace stream of JPEG frames.
	// The server pushes a new frame each time the background snapshot loop
	// captures one; browsers update the <img> automatically.
	mux.HandleFunc("/snapshot/", func(w http.ResponseWriter, r *http.Request) {
		cameraName := r.URL.Path[len("/snapshot/"):]
		if cameraName == "" {
			http.NotFound(w, r)
			return
		}
		if err := dvrManager.StreamSnapshot(r.Context(), cameraName, w, r); err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
		}
	})

	mux.Handle("/", spaHandler("ui/dist"))
	handler := corsMiddleware(mux)

	addr := cfg.Addr
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatal(err)
	}
	log.Println("listening on", addr)

	go func() {
		if err := http.Serve(ln, handler); err != nil {
			log.Fatal(err)
		}
	}()

	// Init the headless browser (process starts but no page loaded yet).
	browserCtx, cancelBrowser := initBrowser(ctx)
	defer cancelBrowser()

	hub.mu.Lock()
	hub.browserCtx = browserCtx
	hub.mu.Unlock()

	// Navigate to the app now that the HTTP server is listening.
	if err := navigateTo(browserCtx, cfg.AppURL); err != nil {
		log.Println("browser: initial navigate error:", err)
	} else {
		log.Println("browser: app loaded")
	}

	// Start background loops.
	go hub.runAirSensorLoop(ctx)
	go hub.runLightSensorLoop(ctx)
	go hub.runTpmsLoop(ctx)
	go hub.runInputLoop(ctx)
	go hub.runScreencastLoop(ctx)

	// Connect DVR manager to hub for camera status broadcasts.
	hub.mu.Lock()
	hub.dvrManager = dvrManager
	hub.mu.Unlock()
	dvrManager.OnStatusChange(func(msg dvr.CameraStatusMsg) {
		hub.broadcastAll(msg)
	})

	// Start DVR recording for all configured cameras.
	dvrManager.Start(ctx)

	// Block until signal.
	<-ctx.Done()
	log.Println("shutting down...")

	// Turn off LED and clear OLED on exit.
	if e := hardware.Expander(); e != nil {
		hardware.LED().Off(e)
	}
	if display != nil {
		display.Close()
	}
}
