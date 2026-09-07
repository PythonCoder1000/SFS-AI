"""
aoa_dragarea.py -- builds and queries a per-craft angle-of-attack (AoA)
-> {dragArea, centerOfDrag} empirical lookup table.

Why this exists: forward_sim.py currently freezes dragArea at the
starting sample's value for the whole prediction window -- fine for a
short, roughly-fixed-orientation coast, wrong in principle for a
general powered+rotating predictor (the actual stated goal, see
bookkeeping/active_state.md's "Abandoned paths"). dragArea (and
centerOfDrag) are deterministic functions of AoA alone for a FIXED
rigid craft design -- Aero_Rocket's own GetDragSurfaces/
GetExposedSurfaces/CalculateDragForce only care about the craft's
orientation relative to its velocity vector, not on position, absolute
time, or altitude. So instead of a live per-part geometry port
(blocked on the surface-mount-part gap, see high_level_checklist.md),
this builds an empirical table straight from real recorded telemetry
and interpolates.

Data source for this table: the 2026-08-31 aero-torque validation
flight (flight01_truth_2026-08-31_19-57-17.jsonl), chosen because it
was flown specifically to sweep a wide AoA range (a real capsule +
heat-shield reentry, post-separation) and already carries dragArea and
dragCopX/Y alongside orientation (rot) and velocity at every tick -- no
fresh calibration flight was needed; this script confirmed full
-180..+180 deg AoA coverage with a physically sensible dragArea pattern
(minimal near 0 deg AoA, rising ~2.5-2.8x at high AoA) before building
the table.

IMPORTANT CAVEAT discovered while wiring this into forward_sim.py: this
specific flight's altitude range is 81,510-91,078m, entirely above
Earth's 30,000m atmosphere ceiling (sfs_physics_reference.md section
1.1). The wide AoA sweep in this data is the craft FREELY TUMBLING in
vacuum from momentum conservation after stage separation, NOT real
atmosphere-driven weathercocking -- real atmospheric density (and
therefore real aero torque/force magnitude) is zero throughout this
window. This does NOT affect dragArea/centerOfDrag validity for THIS
table -- both are pure geometry functions of orientation, computed by
CalculateDragForce with no altitude/density dependency at all (confirmed
via IL, sfs_source_reference.md section C1.4) -- but it DOES mean this
flight cannot be used to derive or validate the actual aero TORQUE
magnitude or a craft's rb2d.inertia (see forward_sim.py's rotation
model docstring for the full explanation and what's needed instead).

AoA convention: heading = rot + 90 (matches sfs_source_reference.md
section B1.4's GetRotation() fallback path -- "first ControlModule's
transform.eulerAngles.z + 90f" -- which is in the same atan2(y,x)
frame as velocity heading). AoA = wrap(heading - velocity_heading) to
[-180, 180]. This offset choice is internally consistent (same
convention used to build the table and to query it); an error in the
absolute offset would only matter if this table's AoA were compared
against a DIFFERENT convention's angle, which nothing here does.

The table is PER CRAFT DESIGN -- it encodes one specific part list and
geometry (see `craft_signature`). Reusing it for a different rocket is
invalid; build a fresh table (same procedure, any flight with wide AoA
coverage) for a different design.
"""

import bisect
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Optional

VALUE_FIELDS = ("dragArea", "dragCopX", "dragCopY")


def _heading_deg(vx: float, vy: float) -> float:
    return math.degrees(math.atan2(vy, vx))


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def angle_of_attack(sample: dict) -> Optional[float]:
    """AoA in degrees, [-180, 180]. None if required fields are missing
    or velocity is ~zero (heading undefined)."""
    rot, vx, vy = sample.get("rot"), sample.get("vx"), sample.get("vy")
    if rot is None or vx is None or vy is None:
        return None
    if math.hypot(vx, vy) < 1e-6:
        return None
    rocket_heading = rot + 90.0
    vel_heading = _heading_deg(vx, vy)
    return _wrap180(rocket_heading - vel_heading)


def craft_signature(sample: dict) -> str:
    """Cheap fingerprint of the craft design from one sample's
    heatParts (name list, order-preserved) plus partCount -- enough to
    flag "this table is for a different rocket" without needing a full
    geometry hash. Not a guarantee of exact-design match (e.g. two
    different fuel-tank heights would still fingerprint the same), just
    a sanity check."""
    parts = sample.get("heatParts") or []
    names = [p.get("name", "?") for p in parts]
    return f"partCount={sample.get('partCount')}|{','.join(names)}"


def build_table(samples: list[dict], bin_width_deg: float = 2.0,
                 min_samples_per_bin: int = 5,
                 value_fields: tuple = VALUE_FIELDS) -> dict:
    """Bins every sample by AoA and takes the median of each requested
    field per bin (default: dragArea, dragCopX, dragCopY -- the raw
    VELOCITY-FRAME center of drag, not yet rotated into world space).
    Requires partCount to be constant across `samples` (caller's job to
    pre-filter, or accept the mixed-geometry warning this returns)."""
    part_counts = {s.get("partCount") for s in samples if s.get("partCount") is not None}
    n_bins = int(round(360.0 / bin_width_deg))

    buckets: dict[int, dict[str, list[float]]] = {}
    skipped_no_aoa = 0
    for s in samples:
        aoa = angle_of_attack(s)
        vals = {f: s.get(f) for f in value_fields}
        if aoa is None or any(v is None for v in vals.values()):
            skipped_no_aoa += 1
            continue
        bin_idx = int((aoa + 180.0) // bin_width_deg) % n_bins
        b = buckets.setdefault(bin_idx, {f: [] for f in value_fields})
        for f in value_fields:
            b[f].append(vals[f])

    bins = []
    low_confidence_bins = []
    for bin_idx in range(n_bins):
        center = -180.0 + (bin_idx + 0.5) * bin_width_deg
        b = buckets.get(bin_idx)
        if not b or not b[value_fields[0]]:
            entry = {"aoa_center": round(center, 3), "count": 0}
            for f in value_fields:
                entry[f"median_{f}"] = None
                entry[f"stddev_{f}"] = None
            bins.append(entry)
            continue
        n = len(b[value_fields[0]])
        entry = {"aoa_center": round(center, 3), "count": n}
        for f in value_fields:
            vals = b[f]
            entry[f"median_{f}"] = statistics.median(vals)
            entry[f"stddev_{f}"] = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        bins.append(entry)
        if n < min_samples_per_bin:
            low_confidence_bins.append(bin_idx)

    empty_bins = [b["aoa_center"] for b in bins if b["count"] == 0]

    return {
        "bin_width_deg": bin_width_deg,
        "value_fields": list(value_fields),
        "craft_signature": craft_signature(samples[0]) if samples else None,
        "part_count_consistent": len(part_counts) == 1,
        "part_counts_seen": sorted(part_counts),
        "source_sample_count": len(samples),
        "skipped_samples_no_aoa": skipped_no_aoa,
        "empty_bin_count": len(empty_bins),
        "empty_bin_centers": empty_bins,
        "low_confidence_bin_count": len(low_confidence_bins),
        "bins": bins,
    }


def lookup_field(table: dict, aoa_deg: float, field: str = "dragArea") -> Optional[float]:
    """Linearly interpolates median_<field> between the two nearest
    populated bin centers, wrapping across the +/-180 boundary. Returns
    None only if the table has NO populated bins for this field at
    all (should not happen for a table built with reasonable AoA
    coverage).

    SPEEDUP 2026-09-07: this used to re-sort the whole bin list AND
    linear-scan every bracket on every single call -- harmless for one
    call, but this function is the actual hot path of forward_sim.py's
    integrator (profiled: 96% of a 10-minute forward-sim's wall-clock
    time, ~48k calls for a 6s/60Hz replay alone, growing linearly with
    duration). The table's bins never change between calls in any real
    use (same `table` dict reused for the whole simulated flight), so
    the sort is now done ONCE per (table, field) and cached directly on
    the table dict itself (a private "_lookup_cache" key, invisible to
    every other reader of "bins"/"bin_width_deg"/etc.), and the bracket
    search uses `bisect` (O(log n)) instead of a linear scan (O(n)).
    Purely a speed fix -- verified byte-for-byte identical output
    against the original implementation across the full -180..180
    sweep before promoting (see aoa_dragarea.py.bak-pre-lookup-speedup
    for the original this replaces, kept for that comparison)."""
    cache = table.setdefault("_lookup_cache", {})
    entry = cache.get(field)
    if entry is None:
        key = f"median_{field}"
        bins = [b for b in table["bins"] if b.get(key) is not None]
        if not bins:
            cache[field] = ()  # cache the "no data" result too, avoid re-scanning every call
            return None
        bins_sorted = sorted(bins, key=lambda b: b["aoa_center"])
        centers = [b["aoa_center"] for b in bins_sorted]
        values = [b[key] for b in bins_sorted]
        entry = (centers, values)
        cache[field] = entry
    if entry == ():
        return None
    centers, values = entry
    n = len(centers)
    aoa = _wrap180(aoa_deg)

    # bisect finds the first center > aoa; the bracket we want starts
    # one before that (wrapping to the last bin if aoa is before the
    # very first center).
    i = bisect.bisect_right(centers, aoa) - 1
    if i < 0:
        i = n - 1
    j = (i + 1) % n
    c0, c1 = centers[i], centers[j]
    span = (c1 - c0) if c1 > c0 else (c1 + 360.0 - c0)
    offset = (aoa - c0) if aoa >= c0 else (aoa + 360.0 - c0)
    if span == 0:
        return values[i]
    frac = offset / span
    return values[i] + frac * (values[j] - values[i])


def lookup_dragarea(table: dict, aoa_deg: float) -> Optional[float]:
    """Convenience wrapper, kept for backward compatibility with the
    original single-field table."""
    return lookup_field(table, aoa_deg, "dragArea")


def lookup_cop_velframe(table: dict, aoa_deg: float) -> Optional[tuple[float, float]]:
    """(dragCopX, dragCopY) interpolated at this AoA, in the RAW
    velocity-aligned frame CalculateDragForce outputs -- NOT yet
    rotated into world space. See forward_sim.py for the rotation step
    and the coordinate-frame caveat before using this for torque."""
    x = lookup_field(table, aoa_deg, "dragCopX")
    y = lookup_field(table, aoa_deg, "dragCopY")
    if x is None or y is None:
        return None
    return (x, y)


def build_from_flight(flight_path: str, out_path: str, bin_width_deg: float = 2.0) -> dict:
    samples = []
    with open(flight_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    table = build_table(samples, bin_width_deg=bin_width_deg)
    table["source_flight"] = str(Path(flight_path).name)
    Path(out_path).write_text(json.dumps(table, indent=None))
    return table


if __name__ == "__main__":
    flight_path = sys.argv[1]
    out_path = sys.argv[2]
    bin_width = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    table = build_from_flight(flight_path, out_path, bin_width)
    print(f"wrote {out_path}")
    print(f"source samples: {table['source_sample_count']}, "
          f"skipped (no AoA/fields): {table['skipped_samples_no_aoa']}")
    print(f"part_count_consistent: {table['part_count_consistent']} "
          f"(seen: {table['part_counts_seen']})")
    print(f"bins: {len(table['bins'])} @ {table['bin_width_deg']} deg width, "
          f"{table['empty_bin_count']} empty, "
          f"{table['low_confidence_bin_count']} low-confidence (<5 samples)")
    if table["empty_bin_centers"]:
        print(f"empty bin centers: {table['empty_bin_centers']}")
