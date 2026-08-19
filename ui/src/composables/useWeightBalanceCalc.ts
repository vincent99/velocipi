// Bridges the layout/station/position data model to the standalone CG math
// in lib/cgcalc.ts. This file is the only place that knows how to turn
// "seat 3B has Bob in it" into a plain (weight, arm) pair — cgcalc.ts itself
// never sees a Station or a Person.
import { computed, type Ref } from 'vue';
import type {
  CGLimitPoint,
  Layout,
  PositionValue,
  Station,
} from '@/types/weightbalance';
import {
  fuelBurnCurve,
  fuelWeightArm,
  moment,
  type CGCurvePoint,
  type WeightArm,
} from '@/lib/cgcalc';

/** Position key for an individual seat within a "row" station. */
export function rowSeatKey(stationId: string, seatId: string): string {
  return `${stationId}:${seatId}`;
}

export interface WeightBalanceCalc {
  totalCapacityGal: number;
  loadedGal: number;
  curve: CGCurvePoint[];
  ffw: CGCurvePoint;
  tow: CGCurvePoint;
  ldw: CGCurvePoint;
  zfw: CGCurvePoint;
  /** FFW is only meaningful (and should only be labeled) if tanks aren't already full. */
  showFFW: boolean;
  errors: string[];
}

/**
 * Live weight & balance calculation for the current layout + positions.
 * Recomputes whenever any of the inputs change — this is what drives the
 * diagram, the CG chart, and the error list.
 */
export function useWeightBalanceCalc(
  layout: Ref<Layout | null>,
  positions: Ref<Record<string, PositionValue>>,
  taxiFuelGal: Ref<number>,
  tripFuelGal: Ref<number>
) {
  return computed<WeightBalanceCalc | null>(() => {
    const l = layout.value;
    if (!l) {
      return null;
    }
    const pos = positions.value;

    const fixedItems = nonFuelWeightArms(l, pos);
    const fuelStations = l.stations.filter((s) => s.type === 'fuel');
    const totalCapacityGal = fuelStations.reduce(
      (sum, s) => sum + (s.capacityGal ?? 0),
      0
    );
    const loadedGal = fuelStations.reduce(
      (sum, s) => sum + (pos[s.id]?.gallons ?? 0),
      0
    );

    const { curve, ffw, tow, ldw, zfw } = fuelBurnCurve({
      fixedItems,
      totalCapacityGal,
      fuelAt: pooledFuelAt(l, fuelStations, totalCapacityGal),
      loadedGal,
      taxiFuelGal: taxiFuelGal.value,
      tripFuelGal: tripFuelGal.value,
      gearMoment: l.gearRetractionMoment,
    });

    const errors = computeErrors(l, pos, curve, tow, ldw, zfw);

    return {
      totalCapacityGal,
      loadedGal,
      curve,
      ffw,
      tow,
      ldw,
      zfw,
      showFFW: loadedGal < totalCapacityGal - 1e-9,
      errors,
    };
  });
}

/** Every occupied non-fuel position (seats, row-seats, cargo) plus the layout's empty weight/CG, as WeightArms. */
function nonFuelWeightArms(
  layout: Layout,
  positions: Record<string, PositionValue>
): WeightArm[] {
  const items: WeightArm[] = [
    { weight: layout.emptyWeight, arm: layout.emptyCG },
  ];
  for (const station of layout.stations) {
    if (station.type === 'fuel') {
      continue;
    }
    if (station.type === 'row') {
      for (const seat of station.seats ?? []) {
        const p = positions[rowSeatKey(station.id, seat.id)];
        items.push({ weight: p?.weight ?? 0, arm: station.arm });
      }
    } else {
      const p = positions[station.id];
      items.push({ weight: p?.weight ?? 0, arm: station.arm });
    }
  }
  return items;
}

/**
 * Builds the pooled fuelAt(gallons) function fuelBurnCurve needs when there's
 * more than one fuel station. Tanks are assumed to drain simultaneously in
 * proportion to their own capacity (e.g. tanks feeding "both") — so at a
 * given total-gallons-remaining level, each station's own share is
 * `gallons × (station capacity / total capacity)`. Each station's share is
 * then converted to a WeightArm with its own arm/variable-moment table
 * (fuelWeightArm), and the results are summed.
 */
function pooledFuelAt(
  layout: Layout,
  fuelStations: Station[],
  totalCapacityGal: number
): (gallons: number) => WeightArm {
  return (gallons: number): WeightArm => {
    if (totalCapacityGal <= 0) {
      return { weight: 0, arm: 0 };
    }
    let weight = 0;
    let momentSum = 0;
    for (const station of fuelStations) {
      const share = (station.capacityGal ?? 0) / totalCapacityGal;
      const wa = fuelWeightArm(
        gallons * share,
        layout.fuelWeightPerGallon,
        station.arm,
        station.variableMoment
      );
      weight += wa.weight;
      momentSum += moment(wa);
    }
    return { weight, arm: weight !== 0 ? momentSum / weight : 0 };
  };
}

/** Piecewise-linear lookup of a CG limit table at a given weight; clamped at the table's ends. Null if the table is empty (not configured). */
function limitCGAt(table: CGLimitPoint[], weight: number): number | null {
  if (table.length === 0) {
    return null;
  }
  const sorted = [...table].sort((a, b) => a.weight - b.weight);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  // table is non-empty (checked above), so first/last always exist; the
  // checks below just satisfy noUncheckedIndexedAccess.
  if (!first || !last) {
    return null;
  }
  if (weight <= first.weight) {
    return first.cg;
  }
  if (weight >= last.weight) {
    return last.cg;
  }
  for (let i = 1; i < sorted.length; i++) {
    const hi = sorted[i];
    const lo = sorted[i - 1];
    if (hi && lo && weight <= hi.weight) {
      const frac = (weight - lo.weight) / (hi.weight - lo.weight);
      return lo.cg + frac * (hi.cg - lo.cg);
    }
  }
  /* istanbul ignore next */
  return last.cg;
}

function fmt(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/**
 * Constraint checks: per-station/seat weight limits (always), plus MTOW /
 * MLW / MZFW and CG envelope violations restricted to the TOW→ZFW portion
 * of the curve — the FFW→TOW segment (more fuel than actually loaded) is
 * informational only, per the calculator's spec.
 */
function computeErrors(
  layout: Layout,
  positions: Record<string, PositionValue>,
  curve: CGCurvePoint[],
  tow: CGCurvePoint,
  ldw: CGCurvePoint,
  zfw: CGCurvePoint
): string[] {
  const errors: string[] = [];

  for (const station of layout.stations) {
    if (station.type === 'row') {
      let rowTotal = 0;
      for (const seat of station.seats ?? []) {
        const p = positions[rowSeatKey(station.id, seat.id)];
        const w = p?.weight ?? 0;
        rowTotal += w;
        if (seat.weightLimit != null && w > seat.weightLimit) {
          errors.push(
            `${p?.name || seat.name} (${station.name}) is ${fmt(w)} lb, over its ${fmt(seat.weightLimit)} lb limit.`
          );
        }
      }
      if (station.weightLimit != null && rowTotal > station.weightLimit) {
        errors.push(
          `${station.name} total is ${fmt(rowTotal)} lb, over its ${fmt(station.weightLimit)} lb limit.`
        );
      }
    } else if (station.type === 'fuel') {
      const g = positions[station.id]?.gallons ?? 0;
      if (station.capacityGal != null && g > station.capacityGal + 1e-9) {
        errors.push(
          `${station.name} has ${fmt(g)} gal, over its ${fmt(station.capacityGal)} gal capacity.`
        );
      }
    } else {
      const p = positions[station.id];
      const w = p?.weight ?? 0;
      if (station.weightLimit != null && w > station.weightLimit) {
        errors.push(
          `${p?.name || station.name} is ${fmt(w)} lb, over its ${fmt(station.weightLimit)} lb limit.`
        );
      }
    }
  }

  if (layout.maxTakeoffWeight > 0 && tow.weight > layout.maxTakeoffWeight) {
    errors.push(
      `Takeoff weight ${fmt(tow.weight)} lb exceeds max takeoff weight ${fmt(layout.maxTakeoffWeight)} lb.`
    );
  }
  if (layout.maxLandingWeight > 0 && ldw.weight > layout.maxLandingWeight) {
    errors.push(
      `Landing weight ${fmt(ldw.weight)} lb exceeds max landing weight ${fmt(layout.maxLandingWeight)} lb.`
    );
  }
  if (layout.maxZeroFuelWeight > 0 && zfw.weight > layout.maxZeroFuelWeight) {
    errors.push(
      `Zero-fuel weight ${fmt(zfw.weight)} lb exceeds max zero-fuel weight ${fmt(layout.maxZeroFuelWeight)} lb.`
    );
  }

  if (layout.forwardCGLimits.length > 0 || layout.aftCGLimits.length > 0) {
    const relevant = curve.filter((pt) => pt.gallons <= tow.gallons + 1e-9);
    const fwdViolation = relevant.find((pt) => {
      const fwd = limitCGAt(layout.forwardCGLimits, pt.weight);
      return fwd != null && pt.cg < fwd - 1e-9;
    });
    if (fwdViolation) {
      const fwd = limitCGAt(layout.forwardCGLimits, fwdViolation.weight)!;
      errors.push(
        `CG ${fwdViolation.cg.toFixed(2)} in at ${fmt(fwdViolation.weight)} lb is forward of the ${fwd.toFixed(2)} in limit.`
      );
    }
    const aftViolation = relevant.find((pt) => {
      const aft = limitCGAt(layout.aftCGLimits, pt.weight);
      return aft != null && pt.cg > aft + 1e-9;
    });
    if (aftViolation) {
      const aft = limitCGAt(layout.aftCGLimits, aftViolation.weight)!;
      errors.push(
        `CG ${aftViolation.cg.toFixed(2)} in at ${fmt(aftViolation.weight)} lb is aft of the ${aft.toFixed(2)} in limit.`
      );
    }
  }

  return errors;
}
