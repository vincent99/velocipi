package main

import (
	"context"
	"encoding/json"
	"log"
	"math"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"

	"github.com/vincent99/velocipi/server/config"
	"github.com/vincent99/velocipi/server/dvr"
	"github.com/vincent99/velocipi/server/hardware"
	"github.com/vincent99/velocipi/server/hardware/oled"
	"github.com/vincent99/velocipi/server/hardware/siyi"
	"github.com/vincent99/velocipi/server/music"
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
	var display oled.Display
	oledCfg := oled.Config{
		SPIPort:   cfg.SPIDevice,
		SPISpeed:  cfg.OLEDSPIFreq,
		GPIOChip:  cfg.OLED.GPIOChip,
		StatusPin: cfg.OLED.StatusPin,
		ResetPin:  cfg.OLED.ResetPin,
		Flip:      cfg.OLED.Flip,
	}
	switch cfg.OLED.Driver {
	case "ge256x64b":
		if o, err := oled.NewGE256X64B(oledCfg, cfg.UI.Panel.Width, cfg.UI.Panel.Height); err != nil {
			log.Println("oled: init error (continuing without display):", err)
		} else {
			display = o
		}
	default: // "ssd1327" or empty
		if o, err := oled.NewSSD1327(oledCfg, cfg.UI.Panel.Width, cfg.UI.Panel.Height); err != nil {
			log.Println("oled: init error (continuing without display):", err)
		} else {
			display = o
		}
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
			Name   string `json:"name"`
			Driver string `json:"driver"`
			Audio  bool   `json:"audio"`
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
			driver := c.Driver
			if driver == "" {
				driver = "rtsp"
			}
			infos = append(infos, cameraInfo{Name: c.Name, Driver: driver, Audio: c.Audio})
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(infos)
	})

	dvrManager := dvr.New(cfg.DVR, cfg.Storage.DVR, cfg.DVRDiskSpacePollDur)

	// /dvr/state — GET returns current DVR state; PUT sets it (admin only).
	mux.HandleFunc("/dvr/state", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(struct {
				State string `json:"state"`
			}{State: string(dvrManager.State())})
		case http.MethodPut:
			if !isAdmin(r) {
				http.Error(w, "forbidden", http.StatusForbidden)
				return
			}
			var body struct {
				State string `json:"state"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
				return
			}
			s := dvr.RecordingState(body.State)
			if s != dvr.RecordingOn && s != dvr.RecordingPaused && s != dvr.RecordingOff {
				http.Error(w, "state must be on, paused, or off", http.StatusBadRequest)
				return
			}
			dvrManager.SetState(s)
			w.WriteHeader(http.StatusNoContent)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

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

	// /snapshot/{camera} — snapshot endpoint.
	// Without query params: multipart/x-mixed-replace stream of JPEG frames.
	// With ?single: returns the latest frame as a single image/jpeg response.
	mux.HandleFunc("/snapshot/", func(w http.ResponseWriter, r *http.Request) {
		cameraName := r.URL.Path[len("/snapshot/"):]
		if cameraName == "" {
			http.NotFound(w, r)
			return
		}
		if _, ok := r.URL.Query()["single"]; ok {
			if err := dvrManager.SingleSnapshot(cameraName, w); err != nil {
				http.Error(w, err.Error(), http.StatusNotFound)
			}
			return
		}
		if err := dvrManager.StreamSnapshot(r.Context(), cameraName, w, r); err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
		}
	})

	// /admin — sets or clears the admin cookie then redirects to /remote/home.
	// /admin       → sets admin=true cookie (1 year)
	// /admin?off   → clears cookie
	mux.HandleFunc("/admin", func(w http.ResponseWriter, r *http.Request) {
		if _, off := r.URL.Query()["off"]; off {
			http.SetCookie(w, &http.Cookie{Name: "admin", Value: "", MaxAge: -1, Path: "/"})
		} else {
			http.SetCookie(w, &http.Cookie{Name: "admin", Value: "true", MaxAge: 86400 * 365, Path: "/"})
		}
		http.Redirect(w, r, "/remote/home", http.StatusFound)
	})

	// /recordings — list, serve, and delete archived MP4 segments.
	mux.HandleFunc("/recordings", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		list, err := dvrManager.ListRecordings()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(list)
	})

	// /recordings/session/{session} — DELETE removes an entire session directory.
	mux.HandleFunc("/recordings/session/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if !isAdmin(r) {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		session := r.URL.Path[len("/recordings/session/"):]
		if err := dvrManager.DeleteSession(session); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	// /recordings/hour/{session}/{hour} — DELETE removes all recordings in a given hour.
	mux.HandleFunc("/recordings/hour/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if !isAdmin(r) {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		rest := r.URL.Path[len("/recordings/hour/"):]
		parts := strings.SplitN(rest, "/", 2)
		if len(parts) != 2 {
			http.Error(w, "expected /recordings/hour/{session}/{hour}", http.StatusBadRequest)
			return
		}
		if err := dvrManager.DeleteHour(parts[0], parts[1]); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	// /recordings/{session}/{file} — serve or delete a recording file (mp4, _thumb.jpg, _full.jpg).
	// DELETE /recordings/{session}/{filename-no-ext} — delete single recording.
	mux.HandleFunc("/recordings/", func(w http.ResponseWriter, r *http.Request) {
		rest := r.URL.Path[len("/recordings/"):]
		switch r.Method {
		case http.MethodDelete:
			if !isAdmin(r) {
				http.Error(w, "forbidden", http.StatusForbidden)
				return
			}
			// rest is "{session}/{filename-no-ext}"
			parts := strings.SplitN(rest, "/", 2)
			if len(parts) != 2 {
				http.Error(w, "expected /recordings/{session}/{filename}", http.StatusBadRequest)
				return
			}
			if err := dvrManager.DeleteRecording(parts[0], parts[1]); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			w.WriteHeader(http.StatusNoContent)
		case http.MethodGet:
			// Serve static files from recordingsDir.
			// rest is "{session}/{file.ext}"
			http.ServeFile(w, r, filepath.Join(cfg.Storage.DVR, rest))
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	// /siyi/{camera}/{action} — Siyi gimbal control routes.
	// Camera name is URL-decoded from the path segment.
	lookupSiyi := func(name string) *siyi.Manager {
		hub.mu.RLock()
		m := hub.siyiManagers[name]
		hub.mu.RUnlock()
		return m
	}
	mux.HandleFunc("/siyi/", func(w http.ResponseWriter, r *http.Request) {
		// path: /siyi/{camera}/{action}
		rest := r.URL.Path[len("/siyi/"):]
		slashIdx := strings.IndexByte(rest, '/')
		if slashIdx < 0 {
			http.NotFound(w, r)
			return
		}
		cameraName := rest[:slashIdx]
		action := rest[slashIdx+1:]

		mgr := lookupSiyi(cameraName)
		if mgr == nil {
			http.Error(w, "camera not found or not siyi driver", http.StatusNotFound)
			return
		}

		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)

		var err error
		switch action {
		case "gimbal":
			yaw := int8(jsonInt(body, "yaw"))
			pitch := int8(jsonInt(body, "pitch"))
			err = mgr.GimbalRotate(yaw, pitch)
		case "zoom":
			if v, ok := body["absolute"]; ok {
				err = mgr.AbsoluteZoom(float32(toFloat(v)))
			} else {
				err = mgr.ZoomRate(int8(jsonInt(body, "direction")))
			}
		case "photo":
			err = mgr.TakePhoto()
		case "video":
			err = mgr.ToggleVideo()
		case "center":
			err = mgr.Center()
		case "focus":
			if jsonStr(body, "mode") == "auto" {
				err = mgr.AutoFocus()
			} else {
				err = mgr.ManualFocus(int8(jsonInt(body, "direction")))
			}
		case "mode":
			switch jsonStr(body, "mode") {
			case "lock":
				err = mgr.SetMode(siyi.ModeLock)
			case "follow":
				err = mgr.SetMode(siyi.ModeFollow)
			case "fpv":
				err = mgr.SetMode(siyi.ModeFPV)
			default:
				http.Error(w, "unknown mode", http.StatusBadRequest)
				return
			}
		case "files":
			// GET override for file listing (POST not ideal but kept consistent)
			dl := siyi.NewDownloader(mgr.Host(), cfg.Storage.Snaps)
			photos, err1 := dl.ListPhotos(r.Context())
			videos, err2 := dl.ListVideos(r.Context())
			if err1 != nil || err2 != nil {
				http.Error(w, "list error", http.StatusInternalServerError)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"photos": photos, "videos": videos})
			return
		case "download":
			fileURL := r.URL.Query().Get("url")
			fileName := r.URL.Query().Get("name")
			if fileURL == "" || fileName == "" {
				http.Error(w, "url and name params required", http.StatusBadRequest)
				return
			}
			dl := siyi.NewDownloader(mgr.Host(), cfg.Storage.Snaps)
			dest, dlErr := dl.Download(r.Context(), siyi.MediaFile{Name: fileName, URL: fileURL})
			if dlErr != nil {
				http.Error(w, dlErr.Error(), http.StatusInternalServerError)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]string{"path": dest})
			return
		default:
			http.NotFound(w, r)
			return
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
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
	go hub.runG3XLoop(ctx)

	// Start Siyi managers for cameras with driver: "siyi".
	siyiManagers := make(map[string]*siyi.Manager)
	for _, cam := range cfg.DVR.Cameras {
		if cam.Driver != "siyi" {
			continue
		}
		mgr := siyi.New(cam, func(name string, att siyi.GimbalAttitude) {
			hub.broadcastAll(SiyiAttitudeMsg{
				Type: "siyiAttitude", Camera: name,
				Yaw: att.Yaw, Pitch: att.Pitch, Roll: att.Roll,
				YawRate: att.YawRate, PitchRate: att.PitchRate, RollRate: att.RollRate,
			})
		})
		siyiManagers[cam.Name] = mgr
		go mgr.Start(ctx)
		log.Printf("siyi: started manager for camera %q at %s", cam.Name, cam.Host)

		if cam.SiyiAIHost != "" {
			tracker := siyi.NewAITracker(cam.SiyiAIHost)
			go tracker.Start(ctx)
			log.Printf("siyi: started AI tracker for camera %q at %s", cam.Name, cam.SiyiAIHost)
		}
	}
	hub.mu.Lock()
	hub.siyiManagers = siyiManagers
	hub.mu.Unlock()

	// Connect DVR manager to hub for camera status broadcasts.
	hub.mu.Lock()
	hub.dvrManager = dvrManager
	hub.mu.Unlock()
	dvrManager.OnStatusChange(func(msg dvr.CameraStatusMsg) {
		hub.broadcastAll(msg)
	})
	dvrManager.OnRecordingReady(func(msg dvr.RecordingReadyMsg) {
		hub.broadcastAll(RecordingReadyMsg{
			Type:     msg.Type,
			Camera:   msg.Camera,
			Session:  msg.Session,
			Filename: msg.Filename,
		})
	})
	dvrManager.OnDiskSpace(func(msg dvr.DiskSpaceMsg) {
		hub.broadcastAll(msg)
	})
	dvrManager.OnDVRState(func(msg dvr.DVRStateMsg) {
		hub.broadcastAll(msg)
	})

	// Start DVR recording for all configured cameras.
	dvrManager.Start(ctx)

	// Initialize music subsystem (requires mpv in PATH; disabled gracefully otherwise).
	musicDB, musicEnabled := music.InitDB(cfg.Music, "schemas", cfg.Storage.Backup)
	if musicEnabled {
		defer musicDB.Close()
		player := music.NewPlayer(musicDB, cfg.Music, hub)
		hub.SetMusicPlayer(player)
		go player.Run(ctx)
		music.RegisterRoutes(mux, musicDB, player, *cfg, isAdmin)
	}

	// Initialize localCamera to the first camera (same sort as /cameras handler).
	if len(cfg.DVR.Cameras) > 0 {
		sorted := make([]config.CameraConfig, len(cfg.DVR.Cameras))
		copy(sorted, cfg.DVR.Cameras)
		sort.Slice(sorted, func(i, j int) bool {
			si := math.MaxInt
			sj := math.MaxInt
			if sorted[i].Sort != nil {
				si = *sorted[i].Sort
			}
			if sorted[j].Sort != nil {
				sj = *sorted[j].Sort
			}
			if si != sj {
				return si < sj
			}
			return strings.ToLower(sorted[i].Name) < strings.ToLower(sorted[j].Name)
		})
		hub.mu.Lock()
		hub.localCamera = sorted[0].Name
		hub.mu.Unlock()
	}

	// Launch Chromium window on the local display showing the camera page.
	// AppURL is http://localhost:<VELOCIPI_PORT>/panel/ so strip the path.
	displayBase := cfg.AppURL
	if u, err := url.Parse(cfg.AppURL); err == nil {
		displayBase = u.Scheme + "://" + u.Host
	}
	go launchDisplayWindow(ctx, displayBase+"/local/camera")

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

// jsonInt extracts an integer value from a decoded JSON body map.
func jsonInt(m map[string]any, key string) int {
	if v, ok := m[key]; ok {
		return int(toFloat(v))
	}
	return 0
}

// jsonStr extracts a string value from a decoded JSON body map.
func jsonStr(m map[string]any, key string) string {
	if v, ok := m[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

// toFloat converts a JSON-decoded number (float64) or string to float64.
func toFloat(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int:
		return float64(n)
	}
	return 0
}
