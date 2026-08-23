package weightbalance

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	RegisterRoutes(mux, t.TempDir())
	return httptest.NewServer(mux)
}

func doJSON(t *testing.T, method, url string, body any, out any) *http.Response {
	t.Helper()
	var reader *bytes.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal request body: %v", err)
		}
		reader = bytes.NewReader(data)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequest(method, url, reader)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, url, err)
	}
	if out != nil && resp.StatusCode < 300 {
		defer resp.Body.Close()
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			t.Fatalf("decode response from %s %s: %v", method, url, err)
		}
	}
	return resp
}

func TestPeopleRoundTrip(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	var got []Person
	doJSON(t, http.MethodGet, srv.URL+"/wb/people", nil, &got)
	if len(got) != 0 {
		t.Fatalf("expected no people initially, got %d", len(got))
	}

	people := []Person{
		{ID: "p1", Name: "Alice", Weight: 150},
		{ID: "p2", Name: "Bob", Weight: 200},
	}
	resp := doJSON(t, http.MethodPut, srv.URL+"/wb/people", people, nil)
	if resp.StatusCode != http.StatusNoContent {
		t.Fatalf("PUT /wb/people: expected 204, got %d", resp.StatusCode)
	}

	doJSON(t, http.MethodGet, srv.URL+"/wb/people", nil, &got)
	if len(got) != 2 || got[0].Name != "Alice" || got[1].Weight != 200 {
		t.Fatalf("unexpected people after round trip: %+v", got)
	}
}

func sampleLayout() Layout {
	return Layout{
		ID:                   "layout-1",
		Name:                 "4 Seat",
		EmptyWeight:          1500,
		EmptyCG:              80,
		GearRetractionMoment: 50,
		MaxTakeoffWeight:     2500,
		MaxLandingWeight:     2400,
		MaxZeroFuelWeight:    2300,
		FuelWeightPerGallon:  6,
		ForwardCGLimits: []CGLimitPoint{
			{CG: 78, Weight: 1500},
			{CG: 82, Weight: 2500},
		},
		AftCGLimits: []CGLimitPoint{
			{CG: 86, Weight: 1500},
			{CG: 90, Weight: 2500},
		},
		Stations: []Station{
			{ID: "pilot", Type: StationSeat, Name: "Pilot", Arm: 82, Lateral: LateralLeft, IgnoreClear: true},
			{
				ID: "row2", Type: StationRow, Name: "Row 2", Arm: 120,
				Seats: []RowItem{
					{ID: "r2l", Type: RowItemSeat, Name: "Left", Lateral: LateralLeft},
					{ID: "r2r", Type: RowItemCargo, Name: "Right", Lateral: LateralRight},
				},
			},
			{ID: "fuel", Type: StationFuel, Name: "Main Tank", Arm: 100, CapacityGal: 50},
		},
	}
}

func TestLayoutsRoundTripAndHash(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	layouts := []Layout{sampleLayout()}
	resp := doJSON(t, http.MethodPut, srv.URL+"/wb/layouts", layouts, nil)
	if resp.StatusCode != http.StatusNoContent {
		t.Fatalf("PUT /wb/layouts: expected 204, got %d", resp.StatusCode)
	}

	var got []Layout
	doJSON(t, http.MethodGet, srv.URL+"/wb/layouts", nil, &got)
	if len(got) != 1 {
		t.Fatalf("expected 1 layout, got %d", len(got))
	}
	if got[0].Hash == "" {
		t.Fatal("expected a computed hash on the returned layout")
	}
	firstHash := got[0].Hash

	// Fetching again with unchanged content must produce the same hash.
	var got2 []Layout
	doJSON(t, http.MethodGet, srv.URL+"/wb/layouts", nil, &got2)
	if got2[0].Hash != firstHash {
		t.Fatalf("hash changed with no content change: %q vs %q", firstHash, got2[0].Hash)
	}

	// Changing the content must change the hash.
	changed := got
	changed[0].EmptyWeight += 10
	doJSON(t, http.MethodPut, srv.URL+"/wb/layouts", changed, nil)
	var got3 []Layout
	doJSON(t, http.MethodGet, srv.URL+"/wb/layouts", nil, &got3)
	if got3[0].Hash == firstHash {
		t.Fatal("expected hash to change after modifying the layout")
	}
}

func TestSaveAndLoadLatest(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// No saves yet.
	resp := doJSON(t, http.MethodGet, srv.URL+"/wb/saved/latest", nil, nil)
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 before any save, got %d", resp.StatusCode)
	}

	body := struct {
		Data SavedWB `json:"data"`
		SVG  string  `json:"svg"`
	}{
		Data: SavedWB{
			LayoutID:   "layout-1",
			LayoutName: "4 Seat",
			LayoutHash: "deadbeef",
			Positions: map[string]PositionValue{
				"pilot": {Name: "Alice", Weight: 150},
				"fuel":  {Gallons: 20},
			},
		},
		SVG: "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
	}
	resp = doJSON(t, http.MethodPost, srv.URL+"/wb/save", body, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("POST /wb/save: expected 200, got %d", resp.StatusCode)
	}

	var latest SavedWB
	resp = doJSON(t, http.MethodGet, srv.URL+"/wb/saved/latest", nil, &latest)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("GET /wb/saved/latest: expected 200, got %d", resp.StatusCode)
	}
	if latest.LayoutID != "layout-1" || latest.Positions["pilot"].Weight != 150 {
		t.Fatalf("unexpected latest snapshot: %+v", latest)
	}
	if latest.SavedAt == "" {
		t.Fatal("expected server to stamp SavedAt")
	}

	// A second, later save becomes the new "latest".
	body.Data.LayoutName = "5 Seat"
	doJSON(t, http.MethodPost, srv.URL+"/wb/save", body, nil)
	var latest2 SavedWB
	doJSON(t, http.MethodGet, srv.URL+"/wb/saved/latest", nil, &latest2)
	if latest2.LayoutName != "5 Seat" {
		t.Fatalf("expected the second save to be latest, got %+v", latest2)
	}
}
