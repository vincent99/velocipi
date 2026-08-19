package weightbalance

import (
	"encoding/json"
	"net/http"
)

type api struct {
	store *store
}

// RegisterRoutes registers all /wb/* HTTP handlers on mux. storageDir is
// cfg.Storage.WeightBalance (already resolved to an absolute path).
func RegisterRoutes(mux *http.ServeMux, storageDir string) {
	a := &api{store: newStore(storageDir)}

	mux.HandleFunc("/wb/people", a.handlePeople)
	mux.HandleFunc("/wb/layouts", a.handleLayouts)
	mux.HandleFunc("/wb/save", a.handleSave)
	mux.HandleFunc("/wb/saved/latest", a.handleLatest)
}

// handlePeople: GET returns the saved people list; PUT replaces it wholesale
// (the Setup screen edits the table client-side and saves it all at once,
// same pattern as POST /config).
func (a *api) handlePeople(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		people, err := a.store.loadPeople()
		if err != nil {
			http.Error(w, "load error: "+err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSONResponse(w, people)
	case http.MethodPut:
		var people []Person
		if err := json.NewDecoder(r.Body).Decode(&people); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		if err := a.store.savePeople(people); err != nil {
			http.Error(w, "save error: "+err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleLayouts: GET returns the saved layouts, each annotated with a
// computed Hash (see hashLayout) so the calculator can detect a layout
// changing since a saved snapshot was made. PUT replaces the list wholesale.
func (a *api) handleLayouts(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		layouts, err := a.store.loadLayouts()
		if err != nil {
			http.Error(w, "load error: "+err.Error(), http.StatusInternalServerError)
			return
		}
		for i := range layouts {
			layouts[i].Hash = hashLayout(layouts[i])
		}
		writeJSONResponse(w, layouts)
	case http.MethodPut:
		var layouts []Layout
		if err := json.NewDecoder(r.Body).Decode(&layouts); err != nil {
			http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		if err := a.store.saveLayouts(layouts); err != nil {
			http.Error(w, "save error: "+err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleSave: POST { data: SavedWB, svg: string } writes a new timestamped
// snapshot pair. The server stamps SavedAt itself (avoids client clock skew)
// and returns the timestamp used.
func (a *api) handleSave(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		Data SavedWB `json:"data"`
		SVG  string  `json:"svg"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	stamp, err := a.store.saveSnapshot(body.Data, body.SVG)
	if err != nil {
		http.Error(w, "save error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSONResponse(w, struct {
		Stamp string `json:"stamp"`
	}{stamp})
}

// handleLatest: GET returns the most recently saved SavedWB, or 404 if none
// exist yet (used to restore the calculator on first load).
func (a *api) handleLatest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	data, ok, err := a.store.loadLatestSnapshot()
	if err != nil {
		http.Error(w, "load error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if !ok {
		http.Error(w, "no saved weight & balance yet", http.StatusNotFound)
		return
	}
	writeJSONResponse(w, data)
}

func writeJSONResponse(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}
