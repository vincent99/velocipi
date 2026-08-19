// Weight & balance center-of-gravity math.
//
// Everything in this file is deliberately standalone: it knows nothing about
// seats, layouts, people, or the calculator UI — only plain (weight, arm)
// numbers. That's on purpose. CG calculations are safety-relevant, so the
// core formula should be small enough to check by hand against a POH's own
// worked example (sum the weight column, sum the moment column, divide) and
// verified independently of how the rest of the app builds its inputs.
//
// The code that *does* know about seats/layouts/people lives in
// composables/useWeightBalanceCalc.ts, which calls into this file.

/** One item contributing to a weight-and-balance calculation: a weight (lb)
 * acting at a distance `arm` (in) from the aircraft's datum. */
export interface WeightArm {
  weight: number; // lb
  arm: number; // in, distance from the datum
}

/** An item's turning effect about the datum: weight × arm (in-lb). */
export function moment(item: WeightArm): number {
  return item.weight * item.arm;
}

export interface CGResult {
  totalWeight: number; // lb
  totalMoment: number; // in-lb
  cg: number; // in; 0 if totalWeight is 0 (CG is undefined with no weight — avoids a divide-by-zero)
}

/**
 * Sums a list of (weight, arm) items and derives the resulting center of
 * gravity. This is the textbook weight-and-balance formula used throughout
 * GA POHs:
 *
 *     CG = ΣMoment / ΣWeight = Σ(weight_i × arm_i) / Σ weight_i
 *
 * To verify: take a POH's sample loading table, list each row as a
 * WeightArm, call this function, and check totalWeight/totalMoment/cg match
 * the book's totals row.
 */
export function sumWeightArms(items: WeightArm[]): CGResult {
  let totalWeight = 0;
  let totalMoment = 0;
  for (const item of items) {
    totalWeight += item.weight;
    totalMoment += moment(item);
  }
  return {
    totalWeight,
    totalMoment,
    cg: totalWeight !== 0 ? totalMoment / totalWeight : 0,
  };
}

/** One breakpoint of a fuel tank's variable-moment table: at this many
 * gallons on board, the tank's moment about the datum is this. */
export interface GallonMoment {
  gallons: number;
  momentInLb: number;
}

/**
 * Returns the WeightArm contributed by a quantity of fuel in one tank.
 *
 * - If `table` is omitted/empty, fuel behaves like any other item: a
 *   constant arm, so moment = weight × arm.
 * - If `table` is given, it specifies moment (in-lb) as a function of
 *   gallons on board, sampled at specific breakpoints — some tanks' fuel CG
 *   shifts non-linearly as they drain because of the tank's shape. Moment is
 *   linearly interpolated between the two breakpoints bracketing `gallons`;
 *   outside the table's range the nearest endpoint's moment is used
 *   (clamped, not extrapolated), since the table only describes gallon
 *   levels actually achievable in the tank. `table` need not be pre-sorted.
 */
export function fuelWeightArm(
  gallons: number,
  weightPerGallon: number,
  arm: number,
  table?: GallonMoment[]
): WeightArm {
  const weight = gallons * weightPerGallon;
  if (!table || table.length === 0) {
    return { weight, arm };
  }
  const m = interpolateMoment(gallons, table);
  // Re-expressed as an arm so this item still composes via moment() = weight×arm.
  return { weight, arm: weight !== 0 ? m / weight : 0 };
}

function interpolateMoment(gallons: number, table: GallonMoment[]): number {
  const sorted = [...table].sort((a, b) => a.gallons - b.gallons);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  // table is non-empty (callers only reach here when table.length > 0), so
  // first/last always exist; the checks below just satisfy noUncheckedIndexedAccess.
  if (!first || !last) {
    return 0;
  }
  if (gallons <= first.gallons) {
    return first.momentInLb;
  }
  if (gallons >= last.gallons) {
    return last.momentInLb;
  }
  for (let i = 1; i < sorted.length; i++) {
    const hi = sorted[i];
    const lo = sorted[i - 1];
    if (hi && lo && gallons <= hi.gallons) {
      const frac = (gallons - lo.gallons) / (hi.gallons - lo.gallons);
      return lo.momentInLb + frac * (hi.momentInLb - lo.momentInLb);
    }
  }
  /* istanbul ignore next -- unreachable: loop above always returns once gallons <= last.gallons */
  return last.momentInLb;
}

export interface CGCurvePoint {
  gallons: number; // total gallons remaining at this point
  weight: number; // lb
  cg: number; // in
}

export interface FuelBurnCurveParams {
  /** Every non-fuel item on board: empty weight/CG, occupied seats, cargo. */
  fixedItems: WeightArm[];
  /** Total fuel system capacity (all tanks pooled), in gallons. */
  totalCapacityGal: number;
  /**
   * The fuel system's combined weight+arm at a given total-gallons-remaining
   * level (0..totalCapacityGal). A single tank can pass fuelWeightArm
   * directly; multiple tanks should pool their combined weight/moment at
   * that gallons level — see useWeightBalanceCalc.ts, which is the only
   * place that knows how many tanks there are.
   */
  fuelAt: (gallons: number) => WeightArm;
  /** Gallons currently loaded (the "ramp" fuel load, as entered on the calculator). */
  loadedGal: number;
  /** Gallons burned taxiing/running up before takeoff. */
  taxiFuelGal: number;
  /** Gallons burned in flight, from takeoff to landing. */
  tripFuelGal: number;
  /**
   * in-lb added to the moment while the gear is retracted — i.e. applied
   * only to the curve segment strictly between the takeoff and landing fuel
   * levels (airborne). The ramp→takeoff (taxi, on the ground) and
   * post-landing segments stay at the moment as entered (gear down). This
   * intentionally produces a small step in the line at the exact takeoff
   * and landing points — gear retracts right after liftoff and extends
   * right before touchdown, so the CG genuinely jumps there. Pass 0 to
   * disable (e.g. fixed-gear aircraft).
   */
  gearMoment: number;
  /** Number of evenly-spaced samples across the full capacity range. Default 40. */
  steps?: number;
}

export interface FuelBurnCurveResult {
  /** Samples ascending by gallons remaining, from 0 (empty) to totalCapacityGal (full). */
  curve: CGCurvePoint[];
  /** Full-fuel weight — only meaningful/shown if loadedGal < totalCapacityGal. */
  ffw: CGCurvePoint;
  /** Takeoff weight: loaded gallons minus taxi fuel. */
  tow: CGCurvePoint;
  /** Landing weight: takeoff gallons minus trip fuel. */
  ldw: CGCurvePoint;
  /** Zero-fuel weight: fixed items only, no fuel on board. */
  zfw: CGCurvePoint;
}

/**
 * Traces the aircraft's CG across the full range of fuel on board, from
 * empty tanks up to full, holding every other item (fixedItems) constant.
 * This is the line drawn on the CG envelope chart, and it also locates the
 * four marker points: FFW, TOW, LDW, ZFW.
 */
export function fuelBurnCurve(
  params: FuelBurnCurveParams
): FuelBurnCurveResult {
  const {
    fixedItems,
    totalCapacityGal,
    fuelAt,
    loadedGal,
    taxiFuelGal,
    tripFuelGal,
    gearMoment,
  } = params;
  const steps = params.steps ?? 40;

  const fixed = sumWeightArms(fixedItems);

  const takeoffGal = Math.max(loadedGal - taxiFuelGal, 0);
  const landingGal = Math.max(takeoffGal - tripFuelGal, 0);

  function pointAt(gallons: number): CGCurvePoint {
    const fuel = fuelAt(gallons);
    const weight = fixed.totalWeight + fuel.weight;
    let m = fixed.totalMoment + moment(fuel);
    // Gear-up adjustment: only for the airborne segment, strictly between
    // landing and takeoff gallons — see gearMoment's doc comment above.
    if (gallons < takeoffGal && gallons > landingGal) {
      m += gearMoment;
    }
    return { gallons, weight, cg: weight !== 0 ? m / weight : 0 };
  }

  // Evenly-spaced samples, plus the exact marker gallons so the drawn line
  // passes precisely through them (and shows the gear-retraction step cleanly).
  const sampleGallons = new Set<number>();
  for (let i = 0; i <= steps; i++) {
    sampleGallons.add((totalCapacityGal * i) / steps);
  }
  [0, totalCapacityGal, loadedGal, takeoffGal, landingGal].forEach((g) =>
    sampleGallons.add(g)
  );

  const curve = [...sampleGallons].sort((a, b) => a - b).map(pointAt);

  return {
    curve,
    ffw: pointAt(totalCapacityGal),
    tow: pointAt(takeoffGal),
    ldw: pointAt(landingGal),
    zfw: pointAt(0),
  };
}
