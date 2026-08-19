// Package weightbalance stores the data behind the remote UI's weight &
// balance planning section: saved people, aircraft layouts (stations, CG
// limits), and a timestamped history of completed load calculations.
//
// The server intentionally does not compute CG here -- the calculator page
// is fully interactive and needs to redraw as the user edits seats/fuel, so
// the authoritative math lives in the browser (ui/src/lib/cgcalc.ts). This
// package only persists whatever JSON + SVG snapshot the client already
// produced.
package weightbalance

// Person is a saved passenger/crew profile used to quickly fill a seat.
type Person struct {
	ID     string  `json:"id"`
	Name   string  `json:"name"`
	Weight float64 `json:"weight"` // lb
}

// CGLimitPoint is one vertex of a forward or aft CG limit line: at this
// weight, the limit is at this CG. Consecutive points are connected with
// straight lines to form the limit polygon's boundary.
type CGLimitPoint struct {
	CG     float64 `json:"cg"`     // in
	Weight float64 `json:"weight"` // lb
}

// Lateral is the left/right seating position of a seat or cargo item,
// used only to place it on the top-down diagram.
type Lateral string

const (
	LateralLeft   Lateral = "left"
	LateralCenter Lateral = "center"
	LateralRight  Lateral = "right"
	LateralFull   Lateral = "full"
)

// RowSeat is one seat within a "row" station. It has its own name, lateral
// position, and optional weight limit, but shares its parent row's arm.
type RowSeat struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Lateral     Lateral  `json:"lateral"`
	WeightLimit *float64 `json:"weightLimit,omitempty"`
	// IgnoreClear, when true, means the "Clear" button on the calculator
	// leaves this seat's occupant in place (e.g. the pilot).
	IgnoreClear bool `json:"ignoreClear,omitempty"`
}

// GallonMoment is one breakpoint of a fuel station's variable-moment table:
// at this many gallons on board, the tank's moment about the datum is this.
// Used to model tanks whose CG shifts non-linearly as they drain.
type GallonMoment struct {
	Gallons    float64 `json:"gallons"`
	MomentInLb float64 `json:"momentInLb"`
}

// StationType discriminates the four kinds of station a layout can define.
type StationType string

const (
	StationSeat  StationType = "seat"
	StationRow   StationType = "row"
	StationCargo StationType = "cargo"
	StationFuel  StationType = "fuel"
)

// Station is one loadable position in an aircraft layout. It is a single
// flat struct (not a Go interface) with a Type discriminator, matching this
// codebase's existing style for tagged variant config (see CameraConfig's
// Driver field) -- simpler to marshal/unmarshal and edit than a polymorphic
// type hierarchy for what is, in the end, just a handful of optional fields.
//
// Field applicability by Type:
//
//	seat:  Arm, WeightLimit, Lateral, IgnoreClear
//	row:   Arm, WeightLimit (total for the row), Seats
//	cargo: Arm, WeightLimit, Lateral
//	fuel:  Arm (used unless VariableMoment is set), WeightLimit, CapacityGal, VariableMoment
type Station struct {
	ID             string         `json:"id"`
	Type           StationType    `json:"type"`
	Name           string         `json:"name"`
	Arm            float64        `json:"arm"` // in
	WeightLimit    *float64       `json:"weightLimit,omitempty"`
	Lateral        Lateral        `json:"lateral,omitempty"`
	IgnoreClear    bool           `json:"ignoreClear,omitempty"`
	Seats          []RowSeat      `json:"seats,omitempty"`
	CapacityGal    float64        `json:"capacityGal,omitempty"`
	VariableMoment []GallonMoment `json:"variableMoment,omitempty"`
}

// Layout describes one aircraft seating/loading configuration: its empty
// weight/CG, weight limits, CG envelope, and the stations that can be
// loaded. Layouts are edited on the Setup screen and selected on the
// calculator screen.
type Layout struct {
	ID                   string  `json:"id"`
	Name                 string  `json:"name"`
	EmptyWeight          float64 `json:"emptyWeight"`          // lb
	EmptyCG              float64 `json:"emptyCG"`              // in
	GearRetractionMoment float64 `json:"gearRetractionMoment"` // in-lb; added while airborne (gear up) -- see cgcalc.ts
	MaxTakeoffWeight     float64 `json:"maxTakeoffWeight"`     // lb; 0 = not enforced
	MaxLandingWeight     float64 `json:"maxLandingWeight"`     // lb; 0 = not enforced
	MaxZeroFuelWeight    float64 `json:"maxZeroFuelWeight"`    // lb; 0 = not enforced
	FuelWeightPerGallon  float64 `json:"fuelWeightPerGallon"`  // lb/gal

	ForwardCGLimits []CGLimitPoint `json:"forwardCGLimits"`
	AftCGLimits     []CGLimitPoint `json:"aftCGLimits"`

	Stations []Station `json:"stations"`

	// Hash is never stored -- it's computed on the fly by handleLayouts from
	// the rest of this struct's JSON and returned to the client so it can
	// detect drift against a saved snapshot's LayoutHash. See hashLayout.
	Hash string `json:"hash,omitempty"`
}

// PositionValue is what's loaded into one station (or one row-seat) on the
// calculator: either a person (their saved weight is used) or a manually
// typed name/weight, a cargo weight, or a fuel quantity.
type PositionValue struct {
	PersonID *string `json:"personId,omitempty"`
	Name     string  `json:"name,omitempty"`    // display name; copied from the person or typed manually
	Weight   float64 `json:"weight,omitempty"`  // lb; seat/row-seat/cargo
	Gallons  float64 `json:"gallons,omitempty"` // fuel stations
}

// SavedWB is one saved weight & balance calculation: everything needed to
// restore the calculator screen exactly as it was, plus enough to detect if
// the layout it was computed against has since changed.
type SavedWB struct {
	SavedAt    string `json:"savedAt"` // RFC3339, stamped by the server
	LayoutID   string `json:"layoutId"`
	LayoutName string `json:"layoutName"`
	// LayoutHash is the layout's hash (see hashLayout) at the time of this
	// save. Compare against the current layout's computed Hash to warn the
	// user their loaded save no longer matches the layout definition.
	LayoutHash string `json:"layoutHash"`

	TaxiFuelGal float64 `json:"taxiFuelGal"`
	TripFuelGal float64 `json:"tripFuelGal"`

	// Positions is keyed by stationId for seat/cargo/fuel stations, or
	// "stationId:seatId" for an individual seat within a row station.
	Positions map[string]PositionValue `json:"positions"`
}
