// Types mirroring server/weightbalance/types.go — the JSON shapes exchanged
// with the /wb/* API. Keep in sync with the Go structs.

export interface Person {
  id: string;
  name: string;
  weight: number; // lb
}

// One vertex of a forward or aft CG limit line: at this weight, the limit is
// at this CG. Consecutive points are connected with straight lines to form
// the limit polygon's boundary.
export interface CGLimitPoint {
  cg: number; // in
  weight: number; // lb
}

export type Lateral = 'left' | 'center' | 'right' | 'full';

// One seat within a "row" station. Has its own name/lateral/weight limit,
// but shares its parent row's arm.
export interface RowSeat {
  id: string;
  name: string;
  lateral: Lateral;
  weightLimit?: number;
  /** If true, the calculator's "Clear" button leaves this seat's occupant in place. */
  ignoreClear?: boolean;
}

// One breakpoint of a fuel station's variable-moment table: at this many
// gallons on board, the tank's moment about the datum is this.
export interface GallonMoment {
  gallons: number;
  momentInLb: number;
}

export type StationType = 'seat' | 'row' | 'cargo' | 'fuel';

// One loadable position in an aircraft layout. A single flat shape with a
// `type` discriminator rather than a variant type, mirroring the Go Station
// struct — field applicability by type:
//   seat:  arm, weightLimit, lateral, ignoreClear
//   row:   arm, weightLimit (total for the row), seats
//   cargo: arm, weightLimit, lateral
//   fuel:  arm (used unless variableMoment set), weightLimit, capacityGal, variableMoment
export interface Station {
  id: string;
  type: StationType;
  name: string;
  arm: number; // in
  weightLimit?: number;
  lateral?: Lateral;
  ignoreClear?: boolean;
  seats?: RowSeat[];
  capacityGal?: number;
  variableMoment?: GallonMoment[];
}

export interface Layout {
  id: string;
  name: string;
  emptyWeight: number; // lb
  emptyCG: number; // in
  /** in-lb; added to the moment while airborne (gear retracted) — see cgcalc.ts fuelBurnCurve's gearMoment param. */
  gearRetractionMoment: number;
  maxTakeoffWeight: number; // lb; 0 = not enforced
  maxLandingWeight: number; // lb; 0 = not enforced
  maxZeroFuelWeight: number; // lb; 0 = not enforced
  fuelWeightPerGallon: number; // lb/gal

  forwardCGLimits: CGLimitPoint[];
  aftCGLimits: CGLimitPoint[];

  stations: Station[];

  /** Computed server-side (SHA-256 of the rest of this layout); compare against a SavedWB's layoutHash. */
  hash?: string;
}

// What's loaded into one station (or one row-seat) on the calculator.
export interface PositionValue {
  personId?: string;
  name?: string; // display name; copied from the person or typed manually
  weight?: number; // lb; seat/row-seat/cargo
  gallons?: number; // fuel stations
}

// One saved weight & balance calculation.
export interface SavedWB {
  savedAt: string; // RFC3339, stamped by the server
  layoutId: string;
  layoutName: string;
  layoutHash: string;
  taxiFuelGal: number;
  tripFuelGal: number;
  /** Keyed by stationId, or "stationId:seatId" for a seat within a row station. */
  positions: Record<string, PositionValue>;
}
