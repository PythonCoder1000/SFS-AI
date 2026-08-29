"""
analyze_dragarea.py -- validate the live-tested dragArea reflection path
against real measured deceleration, the same way every other confirmed
formula in this project (gravity, thrust, rotation, staging) has been
validated: predict from the formula, measure from real telemetry,
compare.

dragArea itself is already confirmed to compute *something real* --
sfs_probe_dragarea.json returned real numbers on the first live run
(2026-08-27/28, see mod_changelog.md v0.27.0). What hasn't been checked
yet is whether the FORCE it produces, when combined with gravity, actually
predicts the rocket's real acceleration during flight. That's what this
script does.

Requires a truth.jsonl (or archived flight file) recorded with v0.28.0+,
which samples dragArea/dragCopX/dragCopY/dragSurfaces/dragExposed on
every tick automatically in full telemetry mode -- no manual 'dragarea'
polling needed, the whole flight already has matched drag+velocity+
altitude+mass data.

Usage:
    python3 analyze_dragarea.py <path-to-truth.jsonl> [--stride N]

    --stride N   Use every Nth sample instead of every consecutive pair
                 (default 1). Higher stride = less finite-difference
                 noise per comparison, fewer comparison points overall.
                 Try 5-10 if consecutive-tick results look noisy.

What it does:
    1. Reads the telemetry file, one JSON object per line (full-mode
       schema -- needs px, py, vx, vy, h, m, dragArea, body at minimum).
    2. Finds coasting segments: consecutive samples where mass is flat
       (no thrust -- same proxy CheckAutoStop() already uses in
       SFSProbe.cs) and altitude is inside the atmosphere.
    3. For each --stride-spaced pair within a coasting segment, computes:
       - measured acceleration: finite difference of (vx, vy) over the
         real elapsed time between the two samples
       - predicted acceleration: gravity (mu/r^2, confirmed formula,
         sfs_physics_reference.md section 2.1) + drag (1.5 * dragArea *
         |v|^2 * density(h) / mass, confirmed via ApplyForce's real IL
         body, section 2.3 and sfs_source_reference.md section C1.5)
    4. Reports per-pair and aggregate error (magnitude and direction)
       between predicted and measured.

Known limitations, honestly stated rather than hidden:
    - Only Earth's atmosphere constants (rho0, curve) are known/hardcoded
      right now -- see PLANET_CONSTANTS below. Samples from other bodies
      are skipped with a warning, not silently mispredicted.
    - CalculateDragForce's dx<0.01f segment-cull threshold (found during
      the doc-writing pass, 2026-08-28) is already baked into the engine's
      own dragArea number by the time we read it -- this script doesn't
      need to reimplement that, it's just using the game's own live
      output. Only the FORCE APPLICATION formula (this script) is a
      reimplementation, not the dragArea computation itself.
    - ApplyParachuteDrag bypasses this entirely (see sfs_source_reference.md
      C1.5) -- this script will silently under/over-predict on any flight
      where a parachute is deployed. Not detected or filtered yet.
    - Rotation/torque is not modeled here -- only translational
      acceleration is checked. A tumbling rocket's dragArea reading
      itself may also be less stable tick-to-tick; that's a separate
      question from whether this script's math is right.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Confirmed planetary constants (sfs_physics_reference.md section 1.1).
# Only Earth is populated -- extend this table as other bodies get
# confirmed live, don't guess values for bodies not yet measured.
# ---------------------------------------------------------------------------
PLANET_CONSTANTS = {
    "Earth": {
        "radius_m": 314970.0,
        "mu": 972219788820.0,          # Planet.mass, i.e. G*M in this game's units
        "atmosphere_height_m": 30000.0,  # AtmosphereHeightPhysics
        "rho0": 0.005,
        "curve": 10.0,
    },
}

# Mass-flatness threshold for the "coasting" proxy -- same value
# CheckAutoStop() uses in SFSProbe.cs (Math.Abs(mass - lastMass) < 0.0005f).
MASS_FLAT_THRESHOLD = 0.0005


def load_samples(path: Path) -> list[dict]:
    samples = []
    with path.open() as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: skipping malformed line {line_no}: {e}", file=sys.stderr)
    return samples


def atmospheric_density(h: float, body: dict) -> float:
    """rho(h) = (e^(-curve*h/H) - e^(-curve)) * rho0 for 0<=h<=H, else 0.
    Confirmed via IL, sfs_physics_reference.md section 2.3."""
    H = body["atmosphere_height_m"]
    if h < 0 or h > H:
        return 0.0
    curve = body["curve"]
    return (math.exp(-curve * h / H) - math.exp(-curve)) * body["rho0"]


def predicted_acceleration(sample: dict, body: dict) -> Optional[tuple[float, float]]:
    """Gravity + drag, in world-frame (x, y) m/s^2. Returns None if the
    sample is missing a required field or dragArea wasn't available that
    tick (TryComputeDragArea returned false -> null in the telemetry)."""
    px, py = sample.get("px"), sample.get("py")
    vx, vy = sample.get("vx"), sample.get("vy")
    m = sample.get("m")
    drag_area = sample.get("dragArea")

    if None in (px, py, vx, vy, m) or drag_area is None or m <= 0:
        return None

    r = math.hypot(px, py)
    if r == 0:
        return None

    # Gravity: g(r) = mu/r^2, directed toward the planet center.
    g_mag = body["mu"] / (r * r)
    gx = -g_mag * (px / r)
    gy = -g_mag * (py / r)

    # Drag: confirmed force-application formula from ApplyForce's real IL
    # body (sfs_source_reference.md C1.5): force = -v_hat * (1.5 * dragArea
    # * |v|^2 * density), applied via AddForceAtPosition (mass-normalized,
    # i.e. plain F=ma, no extra unit-conversion constant needed here --
    # unlike thrust's explicit 9.8 tonnes-force factor).
    v_mag = math.hypot(vx, vy)
    h = sample.get("h", 0.0)
    density = atmospheric_density(h, body)
    if v_mag > 0 and density > 0:
        drag_force_mag = 1.5 * drag_area * v_mag * v_mag * density
        ax_drag = -(vx / v_mag) * drag_force_mag / m
        ay_drag = -(vy / v_mag) * drag_force_mag / m
    else:
        ax_drag = ay_drag = 0.0

    return gx + ax_drag, gy + ay_drag


def find_coasting_pairs(samples: list[dict], stride: int):
    """Yields (i, j) index pairs, j = i+stride, where mass is flat across
    the WHOLE span (no thrust anywhere in between), partCount stays
    constant across the whole span (no crash/separation/destruction --
    those cause velocity discontinuities that aren't real physics), and
    both samples are inside the atmosphere with real telemetry present.
    """
    n = len(samples)
    for i in range(0, n - stride):
        j = i + stride
        a, b = samples[i], samples[j]
        if "m" not in a or "m" not in b:
            continue
        # Check mass stays flat across every intermediate tick too, not
        # just endpoints -- a burn that starts and stops within the span
        # would otherwise be invisible to an endpoint-only check.
        flat = all(
            abs(samples[k].get("m", a["m"]) - a["m"]) < MASS_FLAT_THRESHOLD
            for k in range(i, j + 1)
        )
        if not flat:
            continue
        # Same idea for partCount -- a crash/separation/destruction event
        # anywhere in the span means the velocity data around it isn't
        # clean coasting physics (collision impulses, debris, camera/
        # rocket-object handoff), even if mass happens to look flat.
        base_parts = a.get("partCount")
        if base_parts is not None:
            parts_stable = all(
                samples[k].get("partCount", base_parts) == base_parts
                for k in range(i, j + 1)
            )
            if not parts_stable:
                continue
        h_a, h_b = a.get("h"), b.get("h")
        if h_a is None or h_b is None:
            continue
        # Require comfortably above ground, not just h>=0 -- right at/near
        # the surface is the bounce/impact zone, where a real ground-
        # collision velocity discontinuity happens. That's genuine
        # physics, just not the gravity+drag-only physics this script
        # models, so it doesn't belong in a coasting-pair comparison.
        if h_a < 5.0 or h_b < 5.0:
            continue
        yield i, j


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("telemetry_file", type=Path, help="Path to a truth.jsonl (live or archived)")
    parser.add_argument("--stride", type=int, default=1, help="Sample spacing (default: 1, every consecutive pair)")
    parser.add_argument("--max-report", type=int, default=20, help="Max individual comparisons to print (default: 20)")
    args = parser.parse_args()

    if not args.telemetry_file.exists():
        print(f"ERROR: file not found: {args.telemetry_file}", file=sys.stderr)
        sys.exit(1)

    samples = load_samples(args.telemetry_file)
    if len(samples) < args.stride + 1:
        print(f"ERROR: only {len(samples)} samples loaded, need at least {args.stride + 1} for stride={args.stride}", file=sys.stderr)
        sys.exit(1)

    has_drag_field = any("dragArea" in s for s in samples)
    if not has_drag_field:
        print("ERROR: no 'dragArea' field found in any sample. This file was "
              "likely recorded before v0.28.0, or in scoped mode without "
              "'computed:dragArea' requested. Re-record with v0.28.0+ full "
              "telemetry (or scoped mode including computed:dragArea).", file=sys.stderr)
        sys.exit(1)

    results = []
    skipped_wrong_body = 0
    skipped_missing_data = 0

    for i, j in find_coasting_pairs(samples, args.stride):
        a, b = samples[i], samples[j]
        body_name = a.get("body")
        if body_name not in PLANET_CONSTANTS:
            skipped_wrong_body += 1
            continue

        body = PLANET_CONSTANTS[body_name]
        pred = predicted_acceleration(a, body)
        if pred is None:
            skipped_missing_data += 1
            continue

        dt = b["t"] - a["t"]
        if dt <= 0:
            continue
        measured = ((b["vx"] - a["vx"]) / dt, (b["vy"] - a["vy"]) / dt)

        pred_mag = math.hypot(*pred)
        meas_mag = math.hypot(*measured)
        # Denominator is PREDICTED magnitude, not measured. Gravity alone
        # keeps predicted magnitude substantial (~9-11 m/s^2 near Earth's
        # surface) so this never blows up the way dividing by a
        # near-zero MEASURED value can on a single noisy finite-difference
        # sample -- that was the original bug (mean/max exploded into the
        # billions of percent on a handful of pairs) even though the
        # underlying physics was fine.
        mag_error_pct = abs(pred_mag - meas_mag) / pred_mag * 100 if pred_mag > 1e-6 else float("nan")

        # Direction error via the angle between the two vectors.
        dot = pred[0] * measured[0] + pred[1] * measured[1]
        denom = pred_mag * meas_mag
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot / denom)))) if denom > 1e-9 else float("nan")

        results.append({
            "t": a["t"],
            "h": a.get("h"),
            "v_mag": math.hypot(a["vx"], a["vy"]),
            "drag_area": a.get("dragArea"),
            "pred_mag": pred_mag,
            "meas_mag": meas_mag,
            "mag_error_pct": mag_error_pct,
            "angle_error_deg": angle_deg,
        })

    if not results:
        print("No usable coasting pairs found in this file.", file=sys.stderr)
        print(f"({skipped_wrong_body} skipped: body not in PLANET_CONSTANTS, "
              f"{skipped_missing_data} skipped: missing/null telemetry fields)", file=sys.stderr)
        print("A coasting pair needs: mass flat across the whole span "
              "(engine off), inside the atmosphere, real dragArea reading "
              "each tick. Try a flight with a clear post-MECO coast phase, "
              "or a smaller --stride.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'t':>10} {'h(m)':>10} {'|v|(m/s)':>10} {'dragArea':>10} "
          f"{'pred(m/s2)':>11} {'meas(m/s2)':>11} {'mag err %':>10} {'angle err':>10}")
    for r in results[:args.max_report]:
        print(f"{r['t']:>10.2f} {r['h']:>10.1f} {r['v_mag']:>10.2f} {r['drag_area']:>10.4f} "
              f"{r['pred_mag']:>11.5f} {r['meas_mag']:>11.5f} {r['mag_error_pct']:>9.3f}% "
              f"{r['angle_error_deg']:>9.3f}deg")
    if len(results) > args.max_report:
        print(f"... ({len(results) - args.max_report} more not shown, see summary below)")

    mag_errors = [r["mag_error_pct"] for r in results if not math.isnan(r["mag_error_pct"])]
    angle_errors = [r["angle_error_deg"] for r in results if not math.isnan(r["angle_error_deg"])]

    # Anything still wildly off after the ground-proximity filter is worth
    # surfacing explicitly rather than letting it quietly drag the mean
    # around -- could be a real remaining edge case (e.g. a bounce that
    # traveled back above 5m) rather than assumed-fixed.
    suspect = [r for r in results if not math.isnan(r["mag_error_pct"]) and r["mag_error_pct"] > 20.0]

    print(f"\n--- Summary ({len(results)} coasting pairs, stride={args.stride}) ---")
    if mag_errors:
        mag_errors.sort()
        print(f"Magnitude error %:  mean={sum(mag_errors)/len(mag_errors):.4f}  "
              f"median={mag_errors[len(mag_errors)//2]:.4f}  max={max(mag_errors):.4f}")
    if angle_errors:
        angle_errors.sort()
        print(f"Direction error deg: mean={sum(angle_errors)/len(angle_errors):.4f}  "
              f"median={angle_errors[len(angle_errors)//2]:.4f}  max={max(angle_errors):.4f}")
    if skipped_wrong_body:
        print(f"({skipped_wrong_body} pairs skipped: body not yet in PLANET_CONSTANTS)")
    if skipped_missing_data:
        print(f"({skipped_missing_data} pairs skipped: missing/null telemetry fields)")
    if suspect:
        print(f"\n{len(suspect)} pair(s) still >20% error after filtering -- worth a look, not silently averaged away:")
        for r in suspect[:10]:
            print(f"  t={r['t']:.2f}  h={r['h']:.1f}m  pred={r['pred_mag']:.3f}  meas={r['meas_mag']:.3f}  err={r['mag_error_pct']:.1f}%")

    print("\nFor comparison, this project's other confirmed formulas validate "
          "to well under 0.1% (gravity 0.008-0.13%, thrust 0.4%, rotation "
          "0.0006%, staging 0.003-0.006%) against an empirical noise floor "
          "of roughly 0.006-0.03%. Use that as the bar for whether this "
          "counts as confirmed.")


if __name__ == "__main__":
    main()
