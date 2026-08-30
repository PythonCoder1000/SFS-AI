"""
sfs_telemetry.py -- shared telemetry analysis primitives for the SFS AI
project. Used by both the sfsprobe_mcp server (as importable functions,
no subprocess) and any standalone script that wants the same logic.

This module replaces the analysis logic that used to live only inside
analyze_dragarea.py -- that script's loading/segment-finding/validation
logic is now here, generalized, and analyze_dragarea.py can be thought
of as one specific use of validate_gravity_drag() below.

Design principle carried over from the rest of this project: report
honestly when data is missing or a heuristic is uncertain, rather than
silently returning a plausible-looking but ungrounded number.
"""

import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterator, Optional

# ---------------------------------------------------------------------------
# Confirmed planetary constants (sfs_physics_reference.md section 1.1).
# Only Earth is populated -- extend as other bodies get confirmed live.
# ---------------------------------------------------------------------------
PLANET_CONSTANTS = {
    "Earth": {
        "radius_m": 314970.0,
        "mu": 972219788820.0,
        "atmosphere_height_m": 30000.0,
        "rho0": 0.005,
        "curve": 10.0,
    },
}

MASS_FLAT_THRESHOLD = 0.0005
# Heat tolerance constants (sfs_physics_reference.md / D1 finding):
# Low=400, Mid=1000, High=6000 C; destruction fires at tolerance*1.03.
# Used only as a heuristic hint in find_events' part_count_drop
# annotation -- we don't know a given part's actual tolerance tier from
# telemetry alone, so this is a plausibility flag, not a certainty.
LOW_TOLERANCE_DESTRUCTION_C = 400.0 * 1.03


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_samples(path: Path) -> list[dict]:
    samples = []
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # malformed lines are silently skipped here; callers
                      # doing strict validation should use load_samples
                      # directly and check counts themselves
    return samples


# ---------------------------------------------------------------------------
# Physics primitives (confirmed formulas)
# ---------------------------------------------------------------------------

def atmospheric_density(h: float, body: dict) -> float:
    """rho(h) = (e^(-curve*h/H) - e^(-curve)) * rho0, 0<=h<=H else 0.
    Confirmed via IL, sfs_physics_reference.md section 2.3."""
    H = body["atmosphere_height_m"]
    if h < 0 or h > H:
        return 0.0
    curve = body["curve"]
    return (math.exp(-curve * h / H) - math.exp(-curve)) * body["rho0"]


def predicted_gravity_drag_accel(sample: dict, body: dict) -> Optional[tuple[float, float]]:
    """Gravity + drag, world-frame (x,y) m/s^2. None if required fields
    are missing. Gravity: mu/r^2 (section 2.1). Drag: confirmed
    ApplyForce formula (sfs_source_reference.md C1.5), mass-normalized,
    no extra unit constant needed (unlike thrust's explicit 9.8 factor)."""
    px, py = sample.get("px"), sample.get("py")
    vx, vy = sample.get("vx"), sample.get("vy")
    m = sample.get("m")
    drag_area = sample.get("dragArea")
    if None in (px, py, vx, vy, m) or drag_area is None or m <= 0:
        return None
    r = math.hypot(px, py)
    if r == 0:
        return None
    g_mag = body["mu"] / (r * r)
    gx, gy = -g_mag * (px / r), -g_mag * (py / r)
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


# ---------------------------------------------------------------------------
# Reentry temperature (AeroFormula.GetTemperature, confirmed 2026-08-30)
# ---------------------------------------------------------------------------

# The 4 serialized AeroFormula coefficients -- confirmed live via the
# 'aeroformula' probe command (sfsprobe v0.36.0), NOT IL literals, so
# these cannot be sourced any other way. See
# docs/sfs_reference/02-drag-aero/AeroFormula.md.
AEROFORMULA_COEFFICIENTS = {
    "velPow": 1.85,
    "densityPow": 2.2,
    "tempOffset": -500.0,
    "m": 1.47,
}

# Per-planet, confirmed live via 'atmophysics' (sfsprobe v0.36.1). Only
# Earth populated so far -- extend as other bodies get read live. The
# ctor default of 1.0f happened to match Earth's real value here, but
# per the project's data-trust rule this was read, not assumed.
ATMOSPHERE_PHYSICS = {
    "Earth": {"minHeatingVelocityMultiplier": 1.0, "shockwaveIntensity": 1.0},
}

# Difficulty.HeatVelocityMultiplier / MinHeatVelocityMultiplier, by
# difficulty tier (sfs_physics_reference.md section 5.1). This project's
# empirical checks (e.g. ispMultiplier=1.0000) are all consistent with
# Normal difficulty, so that's assumed here unless told otherwise --
# flag if a flight was actually run on Hard/Realistic.
HEAT_VELOCITY_MULTIPLIER = {"Normal": 1.0, "Hard": 1.3, "Realistic": 4.5}
MIN_HEAT_VELOCITY_MULTIPLIER = {"Normal": 1.0, "Hard": 1.3, "Realistic": 3.0}


def predicted_reentry_temperature(velocity: float, velocity_y: float, density: float,
                                   body_name: str = "Earth", difficulty: str = "Normal") -> float:
    """Port of AeroFormula.GetTemperature, confirmed via IL
    (docs/sfs_reference/02-drag-aero/AeroFormula.md) with all 4
    coefficients now confirmed live (2026-08-30) rather than guessed.

    velocity: speed magnitude (m/s). velocity_y: SIGNED vertical
    component (positive = ascending). density: atmospheric density at
    the sample's altitude (use atmospheric_density(h, body) above).

    This is the GLOBAL air temperature the rocket sees -- NOT a
    per-part value. Per-part temperature is a separate accumulation
    (HeatManager.ApplyHeat, not implemented here) that integrates this
    value over time, weighted by each part's exposed surface. This
    function gives you the instantaneous forcing input to that
    accumulation, not the part's own temperature.
    """
    coef = AEROFORMULA_COEFFICIENTS
    atmo = ATMOSPHERE_PHYSICS.get(body_name)
    if atmo is None:
        raise ValueError(f"no confirmed atmospherePhysics for body {body_name!r} -- "
                          f"read it live via the 'atmophysics' probe command first")
    hvm = HEAT_VELOCITY_MULTIPLIER[difficulty]
    mhvm = MIN_HEAT_VELOCITY_MULTIPLIER[difficulty]

    min_heat_velocity = atmo["minHeatingVelocityMultiplier"] * mhvm * 250.0

    v = velocity / hvm
    v_y = velocity_y / hvm
    min_hv = min_heat_velocity / hvm

    # Ascending? discount some speed -- climbing out heats less than falling in.
    if v_y > 0.0:
        v -= min(v_y * 2.5, v * 0.5)

    if v < 0 or density <= 0:
        return 0.0

    t = (v ** coef["velPow"]) * (density ** (1.0 / coef["densityPow"])) / coef["m"]

    ascent_term = min(v_y / v * 2.0, 0.4) if (v_y > 0.0 and v > 0) else 0.0
    t += t * (coef["tempOffset"] * ascent_term + 0.2)

    # Hard cap tied to how far above the heating-onset speed you are.
    cap = (v - min_hv) * 6.0
    if t > cap:
        t = cap

    # Soft knee above 2000.
    if t > 2000.0:
        t = 2000.0 + (t - 2000.0) / 1.5

    return t if t > 0.0 else 0.0


def predicted_reentry_temperature_for_sample(sample: dict, body: dict, body_name: str = "Earth",
                                              difficulty: str = "Normal") -> Optional[float]:
    """Convenience wrapper: pulls velocity/velocity_y/density straight
    from a telemetry sample dict, the way validate_gravity_drag's sibling
    functions do. velocity_y is 'vv' (VerticalVelocity) in this
    project's telemetry schema."""
    vx, vy = sample.get("vx"), sample.get("vy")
    vv, h = sample.get("vv"), sample.get("h")
    if None in (vx, vy, vv, h):
        return None
    velocity = math.hypot(vx, vy)
    density = atmospheric_density(h, body)
    return predicted_reentry_temperature(velocity, vv, density, body_name, difficulty)


def validate_multi_engine(samples: list[dict], inputs: list[dict], single_engine_thrust: float,
                           start: int = 0, end: Optional[int] = None) -> dict:
    """LIVE-VALIDATED 2026-08-30 (median 0.14% error, 1,576 clean pairs,
    3-engine symmetric rocket). Confirms the 'no summation, N
    independent forces' multi-engine model by summing each engine's OWN
    thrust contribution (from inputs.jsonl's per-sample 'engines' array
    -- requires sfsprobe v0.37.0+, the AmbiguousMatchException fix)
    against gravity+drag, compared to measured (finite-difference)
    acceleration.

    Thrust direction is approximated as RADIAL (px,py)/r -- valid for a
    symmetric multi-engine cluster with no steering input, where thrust
    direction closely tracks 'straight up from the planet'; confirmed on
    the validation flight (velocity/radial dot product = 1.0000
    throughout). A rocket with active steering or asymmetric engines
    would need real per-engine world-frame thrust vectors instead --
    not implemented here, since inputs.jsonl only carries LOCAL
    thrustDirX/Y (see EngineModule.md), not a world-frame transform.

    samples and inputs must be the SAME flight's truth.jsonl/inputs.jsonl,
    same length, index-aligned (as sfsprobe writes them).
    """
    if len(samples) != len(inputs):
        raise ValueError("samples and inputs must be the same length (same flight, index-aligned)")
    end = len(samples) - 1 if end is None else end
    results = []
    for i in range(max(1, start), min(end, len(samples) - 1)):
        a, b = samples[i - 1], samples[i + 1]
        dt = b["t"] - a["t"]
        if dt <= 0:
            continue
        dt1, dt2 = samples[i]["t"] - a["t"], b["t"] - samples[i]["t"]
        irregular_timestep = abs(dt1 - dt2) > 0.001
        measured = ((b["vx"] - a["vx"]) / dt, (b["vy"] - a["vy"]) / dt)
        body = PLANET_CONSTANTS.get(samples[i].get("body"))
        if not body:
            continue
        grav_drag = predicted_gravity_drag_accel(samples[i], body)
        if grav_drag is None:
            continue
        m = samples[i]["m"]
        px, py = samples[i]["px"], samples[i]["py"]
        r = math.hypot(px, py)
        if r == 0 or m <= 0:
            continue
        thrust_accel_mag = sum(
            single_engine_thrust * 9.8 * e.get("throttleOut", 0.0) / m
            for e in inputs[i].get("engines", [])
            if e.get("type") == "engine" and e.get("engineOn")
        )
        rx, ry = px / r, py / r
        pred = (grav_drag[0] + thrust_accel_mag * rx, grav_drag[1] + thrust_accel_mag * ry)
        pred_mag, meas_mag = math.hypot(*pred), math.hypot(*measured)
        if pred_mag < 1e-6:
            continue
        err_pct = abs(pred_mag - meas_mag) / pred_mag * 100
        results.append({
            "t": samples[i]["t"], "h": samples[i].get("h"), "thrust_accel": thrust_accel_mag,
            "pred_mag": pred_mag, "meas_mag": meas_mag, "err_pct": err_pct,
            "irregular_timestep": irregular_timestep,
        })
    clean = [r for r in results if not r["irregular_timestep"]]
    errs = [r["err_pct"] for r in clean]
    suspect = [r for r in clean if r["err_pct"] > 5.0]
    return {
        "summary": {
            "total_pairs": len(results),
            "clean_pairs": len(clean),
            "excluded_irregular_timestep": len(results) - len(clean),
            "magnitude_error_pct": {
                "median": statistics.median(errs), "mean": statistics.mean(errs), "max": max(errs),
            } if errs else None,
            "suspect_count": len(suspect),
            "suspect_samples": suspect[:10],
        },
        "sample_results": results[:20],
    }


# ---------------------------------------------------------------------------
# Stage 1 -- core stats & search
# ---------------------------------------------------------------------------

def field_stats(samples: list[dict], fields: list[str], start: int = 0, end: Optional[int] = None) -> dict:
    end = len(samples) if end is None else end
    out = {}
    for field in fields:
        vals = [s[field] for s in samples[start:end] if field in s and s[field] is not None
                and isinstance(s[field], (int, float))]
        if not vals:
            out[field] = {"count": 0, "warning_code": "NO_DATA_IN_RANGE",
                          "note": "no numeric values found for this field in range"}
            continue
        out[field] = {
            "count": len(vals),
            "min": min(vals),
            "max": max(vals),
            "mean": statistics.mean(vals),
            "median": statistics.median(vals),
            "stddev": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
        }
    return out


_OPS = {
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}


def search_field(samples: list[dict], field: str, op: str, value: float,
                  start: int = 0, end: Optional[int] = None, limit: Optional[int] = None) -> list[dict]:
    if op not in _OPS:
        raise ValueError(f"unknown op {op!r}, must be one of {list(_OPS)}")
    end = len(samples) if end is None else end
    fn = _OPS[op]
    out = []
    for idx in range(start, end):
        s = samples[idx]
        v = s.get(field)
        if v is None or not isinstance(v, (int, float)):
            continue
        if fn(v, value):
            out.append({"idx": idx, "t": s.get("t"), "value": v})
            if limit and len(out) >= limit:
                break
    return out


def downsample(samples: list[dict], n: int, start: int = 0, end: Optional[int] = None) -> list[dict]:
    end = len(samples) if end is None else end
    window = samples[start:end]
    if n >= len(window) or n <= 0:
        return window
    step = len(window) / n
    return [window[int(i * step)] for i in range(n)]


def field_at_time(samples: list[dict], t: float) -> Optional[dict]:
    if not samples:
        return None
    best = min(samples, key=lambda s: abs(s.get("t", float("inf")) - t))
    return best


# ---------------------------------------------------------------------------
# Stage 2 -- flight structure & events
# ---------------------------------------------------------------------------

def flight_summary(samples: list[dict]) -> dict:
    if not samples:
        return {"error": "no samples"}
    h_vals = [s["h"] for s in samples if "h" in s]
    v_vals = [math.hypot(s["vx"], s["vy"]) for s in samples if "vx" in s and "vy" in s]
    m_vals = [s["m"] for s in samples if "m" in s]
    t_vals = [s["t"] for s in samples if "t" in s]
    t_first, t_last = samples[0].get("t"), samples[-1].get("t")
    duration = (t_last - t_first) if (t_first is not None and t_last is not None) else None
    time_anomaly = None
    if duration is not None and duration < 0:
        # 'location.time' has been observed to NOT be strictly monotonic
        # across a full archived flight -- seen first 2026-08-28 on a
        # flight that crashed (first/last sample gave a negative
        # duration). Not yet root-caused: possibly ActiveRocket() started
        # tracking a different Rocket object after a part-count event, or
        # a scene/object handoff reset the clock. Flagged rather than
        # silently returning a nonsensical negative duration -- use
        # max(t)-min(t) as a best-effort positive fallback instead.
        time_anomaly = ("t is not monotonic across this file (last < first) -- "
                         "duration_s below is max(t)-min(t) as a fallback, not "
                         "last-t minus first-t. Root cause not yet confirmed; "
                         "treat any cross-sample time math on this file with caution.")
        duration = (max(t_vals) - min(t_vals)) if t_vals else None
    return {
        "sample_count": len(samples),
        "duration_s": duration,
        "time_anomaly": time_anomaly,
        "altitude_m": {"min": min(h_vals), "max": max(h_vals)} if h_vals else None,
        "speed_ms": {"min": min(v_vals), "max": max(v_vals)} if v_vals else None,
        "mass_t": {"start": m_vals[0], "end": m_vals[-1]} if m_vals else None,
        "final_part_count": samples[-1].get("partCount"),
        "initial_part_count": samples[0].get("partCount"),
        "max_temp_c": max((s.get("maxTemp", 0) for s in samples), default=None),
        "body": samples[0].get("body"),
    }


def detect_phases(samples: list[dict]) -> list[dict]:
    """Heuristic phase segmentation from mass-trend + vertical-velocity
    sign -- NOT a read of the game's own internal phase/state concept
    (no such field is exposed in telemetry). Good enough for scoping
    analysis by phase; treat phase boundaries as approximate, not exact
    game-state transitions.
    """
    if len(samples) < 2:
        return []
    phases = []
    cur_label = None
    seg_start = 0
    h0 = samples[0].get("h", 0)

    def label_for(i):
        s = samples[i]
        h = s.get("h", 0)
        m = s.get("m")
        vv = s.get("vv")
        if m is None or vv is None:
            return "unknown"
        prev_m = samples[max(0, i - 1)].get("m", m)
        decreasing = (prev_m - m) > MASS_FLAT_THRESHOLD
        if abs(h - h0) < 2.0 and i < len(samples) * 0.1:
            return "prelaunch"
        if decreasing and vv >= 0:
            return "powered_ascent"
        if decreasing and vv < 0:
            return "powered_descent"
        if vv >= 0:
            return "coast_ascent"
        return "coast_descent"

    for i in range(len(samples)):
        lbl = label_for(i)
        if cur_label is None:
            cur_label = lbl
            seg_start = i
        elif lbl != cur_label:
            phases.append({
                "phase": cur_label, "start_idx": seg_start, "end_idx": i - 1,
                "start_t": samples[seg_start].get("t"), "end_t": samples[i - 1].get("t"),
            })
            cur_label = lbl
            seg_start = i
    phases.append({
        "phase": cur_label, "start_idx": seg_start, "end_idx": len(samples) - 1,
        "start_t": samples[seg_start].get("t"), "end_t": samples[-1].get("t"),
    })
    return phases


def find_events(samples: list[dict]) -> list[dict]:
    """Locate named, indexable events. Types: engine_start, engine_cutoff,
    apoapsis, periapsis, max_velocity, max_dynamic_pressure,
    part_count_drop (annotated likely_cause: destruction/separation,
    heuristic only), impact. Each event has a stable 'type' + occurrence
    order, so callers can reference e.g. the 2nd 'part_count_drop'.
    """
    events = []
    if len(samples) < 2:
        return events

    prev_decreasing = None
    prev_vv_sign = None
    for i in range(1, len(samples)):
        a, b = samples[i - 1], samples[i]
        m_a, m_b = a.get("m"), b.get("m")
        if m_a is not None and m_b is not None:
            decreasing = (m_a - m_b) > MASS_FLAT_THRESHOLD
            if prev_decreasing is not None and decreasing != prev_decreasing:
                events.append({
                    "type": "engine_start" if decreasing else "engine_cutoff",
                    "idx": i, "t": b.get("t"),
                })
            prev_decreasing = decreasing

        vv = b.get("vv")
        if vv is not None:
            sign = 1 if vv > 0 else (-1 if vv < 0 else 0)
            if prev_vv_sign == 1 and sign == -1:
                events.append({"type": "apoapsis", "idx": i, "t": b.get("t"), "h": b.get("h")})
            elif prev_vv_sign == -1 and sign == 1:
                events.append({"type": "periapsis", "idx": i, "t": b.get("t"), "h": b.get("h")})
            if sign != 0:
                prev_vv_sign = sign

        pc_a, pc_b = a.get("partCount"), b.get("partCount")
        if pc_a is not None and pc_b is not None and pc_b < pc_a:
            temp = b.get("maxTemp", 0) or 0
            likely_cause = "destruction (heuristic: maxTemp near/above Low-tier threshold)" \
                if temp >= LOW_TOLERANCE_DESTRUCTION_C * 0.9 else \
                "separation (heuristic: no notable heat spike at this event)"
            events.append({
                "type": "part_count_drop", "idx": i, "t": b.get("t"),
                "from": pc_a, "to": pc_b, "max_temp_c": temp, "likely_cause": likely_cause,
            })

    # Global extrema (single events, not per-tick).
    speeds = [(i, math.hypot(s["vx"], s["vy"])) for i, s in enumerate(samples) if "vx" in s and "vy" in s]
    if speeds:
        i, v = max(speeds, key=lambda p: p[1])
        events.append({"type": "max_velocity", "idx": i, "t": samples[i].get("t"), "value_ms": v})

    qs = []
    for i, s in enumerate(samples):
        if "vx" not in s or "vy" not in s or "h" not in s or "body" not in s:
            continue
        body = PLANET_CONSTANTS.get(s["body"])
        if not body:
            continue
        v = math.hypot(s["vx"], s["vy"])
        q = 0.5 * atmospheric_density(s["h"], body) * v * v
        qs.append((i, q))
    if qs:
        i, q = max(qs, key=lambda p: p[1])
        events.append({"type": "max_dynamic_pressure", "idx": i, "t": samples[i].get("t"), "value": q})

    # Impact: last sample where h drops below 5m having previously been
    # meaningfully airborne (h > 20m at some earlier point).
    was_airborne = False
    for i, s in enumerate(samples):
        h = s.get("h")
        if h is None:
            continue
        if h > 20:
            was_airborne = True
        if was_airborne and h < 5 and i == len(samples) - 1:
            events.append({"type": "impact", "idx": i, "t": s.get("t"), "h": h})
        elif was_airborne and h < 5:
            # first crossing below 5m after being airborne
            events.append({"type": "impact", "idx": i, "t": s.get("t"), "h": h})
            was_airborne = False  # only report the first crossing, not every subsequent low sample

    events.sort(key=lambda e: e["idx"])
    return events


def resolve_scope(samples: list[dict], scope: Optional[dict],
                   phases: Optional[list[dict]] = None,
                   events: Optional[list[dict]] = None) -> tuple[int, int, Optional[dict]]:
    """Resolve a scope dict into a (start_idx, end_idx, warning) tuple.
    end_idx is INCLUSIVE (use samples[start:end_idx+1]). Scope forms:
      {"phase": "ascent"}  -- matches any phase whose name contains this
      {"time_range": [t1, t2]}
      {"before_event": "impact", "window_s": 10, "index": -1}
      {"after_event": "engine_cutoff", "window_s": None, "index": 0}
      {"around_event": "apoapsis", "window_s": 5, "index": 0}
    'index' selects which occurrence (0-based) when an event type
    appears more than once; default 0 (first occurrence), -1 for last.

    warning is None on a clean resolution (including scope=None, which
    is a deliberate "whole flight" request, not a fallback). When a
    phase/event/time-range genuinely can't be matched, this returns the
    full-flight range as a fallback AND a non-None warning dict
    ({'code': 'SCOPE_NO_MATCH', 'message': ...}) so callers can surface
    that the returned data is NOT actually scoped the way it was asked
    to be -- silently falling back used to hide this.
    """
    if not samples:
        return (0, 0, None)
    default = (0, len(samples) - 1)
    if not scope:
        return (*default, None)

    def _no_match(reason: str) -> tuple[int, int, dict]:
        return (*default, {
            "code": "SCOPE_NO_MATCH",
            "message": f"No matching {reason} found for the given scope -- "
                       "falling back to the full flight range.",
        })

    if "phase" in scope:
        phases = phases if phases is not None else detect_phases(samples)
        matches = [p for p in phases if scope["phase"] in p["phase"]]
        if not matches:
            return _no_match(f"phase containing {scope['phase']!r}")
        return (matches[0]["start_idx"], matches[-1]["end_idx"], None)

    if "time_range" in scope:
        t1, t2 = scope["time_range"]
        idxs = [i for i, s in enumerate(samples) if t1 <= s.get("t", -1) <= t2]
        if not idxs:
            return _no_match(f"samples in time_range {scope['time_range']}")
        return (idxs[0], idxs[-1], None)

    for key, sign in (("before_event", -1), ("after_event", 1), ("around_event", 0)):
        if key in scope:
            events = events if events is not None else find_events(samples)
            etype = scope[key]
            matches = [e for e in events if e["type"] == etype]
            if not matches:
                return _no_match(f"event of type {etype!r}")
            idx_sel = scope.get("index", 0)
            try:
                ev = matches[idx_sel]
            except IndexError:
                return _no_match(f"event of type {etype!r} at index {idx_sel}")
            center = ev["idx"]
            window_s = scope.get("window_s")
            if window_s is None:
                if sign < 0:
                    return (0, center, None)
                elif sign > 0:
                    return (center, len(samples) - 1, None)
                return (*default, None)
            center_t = ev["t"]
            lo_t = center_t - window_s if sign <= 0 else center_t
            hi_t = center_t + window_s if sign >= 0 else center_t
            idxs = [i for i, s in enumerate(samples) if lo_t <= s.get("t", -1) <= hi_t]
            if not idxs:
                return _no_match(f"samples within the window around event {etype!r}")
            return (idxs[0], idxs[-1], None)

    return _no_match("recognizable scope key (expected phase/time_range/before_event/after_event/around_event)")


# ---------------------------------------------------------------------------
# Stage 4 -- physics validation, generalized
# ---------------------------------------------------------------------------

def find_clean_segments(samples: list[dict], kind: str = "coast", stride: int = 1) -> Iterator[tuple[int, int]]:
    """kind='coast': mass flat + partCount stable + h>5 across the whole
    span (excludes crash/bounce artifacts). kind='burn': mass strictly
    decreasing across the whole span, partCount stable."""
    n = len(samples)
    for i in range(0, n - stride):
        j = i + stride
        a = samples[i]
        if "m" not in a or "m" not in samples[j]:
            continue
        if kind == "coast":
            ok = all(abs(samples[k].get("m", a["m"]) - a["m"]) < MASS_FLAT_THRESHOLD for k in range(i, j + 1))
        elif kind == "burn":
            ok = all(samples[k].get("m", a["m"]) <= samples[max(i, k - 1)].get("m", a["m"]) + 1e-9
                     for k in range(i + 1, j + 1)) and (a["m"] - samples[j]["m"]) > MASS_FLAT_THRESHOLD
        else:
            raise ValueError(f"unknown kind {kind!r}")
        if not ok:
            continue
        base_parts = a.get("partCount")
        if base_parts is not None:
            if not all(samples[k].get("partCount", base_parts) == base_parts for k in range(i, j + 1)):
                continue
        if kind == "coast":
            h_a, h_b = a.get("h"), samples[j].get("h")
            if h_a is None or h_b is None or h_a < 5.0 or h_b < 5.0:
                continue
        yield i, j


def validate_gravity_drag(samples: list[dict], start: int = 0, end: Optional[int] = None, stride: int = 1) -> dict:
    """The generalized version of analyze_dragarea.py's core check.
    Predicted (gravity+drag) vs measured (finite-difference) acceleration
    over clean coasting pairs within [start, end]."""
    end = len(samples) - 1 if end is None else end
    window = samples[start:end + 1]
    results = []
    for i, j in find_clean_segments(window, kind="coast", stride=stride):
        a, b = window[i], window[j]
        body_name = a.get("body")
        body = PLANET_CONSTANTS.get(body_name)
        if not body:
            continue
        pred = predicted_gravity_drag_accel(a, body)
        if pred is None:
            continue
        dt = b["t"] - a["t"]
        if dt <= 0:
            continue
        measured = ((b["vx"] - a["vx"]) / dt, (b["vy"] - a["vy"]) / dt)
        pred_mag, meas_mag = math.hypot(*pred), math.hypot(*measured)
        mag_error_pct = abs(pred_mag - meas_mag) / pred_mag * 100 if pred_mag > 1e-6 else None
        dot = pred[0] * measured[0] + pred[1] * measured[1]
        denom = pred_mag * meas_mag
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot / denom)))) if denom > 1e-9 else None
        results.append({
            "t": a["t"], "h": a.get("h"), "v_mag": math.hypot(a["vx"], a["vy"]),
            "drag_area": a.get("dragArea"), "pred_mag": pred_mag, "meas_mag": meas_mag,
            "mag_error_pct": mag_error_pct, "angle_error_deg": angle_deg,
        })
    mag_errors = [r["mag_error_pct"] for r in results if r["mag_error_pct"] is not None]
    angle_errors = [r["angle_error_deg"] for r in results if r["angle_error_deg"] is not None]
    suspect = [r for r in results if r["mag_error_pct"] is not None and r["mag_error_pct"] > 20.0]
    summary = {
        "pair_count": len(results),
        "magnitude_error_pct": {
            "mean": statistics.mean(mag_errors), "median": statistics.median(mag_errors),
            "max": max(mag_errors),
        } if mag_errors else None,
        "direction_error_deg": {
            "mean": statistics.mean(angle_errors), "median": statistics.median(angle_errors),
            "max": max(angle_errors),
        } if angle_errors else None,
        "suspect_count": len(suspect),
        "suspect_samples": suspect[:10],
        "comparison_bar": "Other confirmed formulas in this project validate well under "
                           "0.1% (gravity 0.008-0.13%, thrust 0.4%, rotation 0.0006%, "
                           "staging 0.003-0.006%) against an empirical noise floor of "
                           "roughly 0.006-0.03%.",
    }
    return {"summary": summary, "sample_results": results[:20]}


def noise_floor(samples_a: list[dict], samples_b: list[dict], fields: list[str] = None) -> dict:
    """Compare two nominally-identical flights (same rocket, same
    commanded inputs) sample-index-aligned, reporting divergence per
    field. This is the determinism check from the original architecture
    doc -- run it on two flights meant to be reproductions of each other."""
    fields = fields or ["h", "vx", "vy", "m"]
    n = min(len(samples_a), len(samples_b))
    if n == 0:
        return {"error": "one or both flights have no samples"}
    diffs = {f: [] for f in fields}
    for i in range(n):
        for f in fields:
            va, vb = samples_a[i].get(f), samples_b[i].get(f)
            if va is not None and vb is not None:
                diffs[f].append(abs(va - vb))
    out = {}
    for f in fields:
        d = diffs[f]
        out[f] = {
            "count": len(d),
            "mean_abs_diff": statistics.mean(d) if d else None,
            "max_abs_diff": max(d) if d else None,
        }
    return {"aligned_sample_count": n, "per_field_divergence": out}


# ---------------------------------------------------------------------------
# Stage 5 -- derived flight metrics
# ---------------------------------------------------------------------------

def compute_apoapsis_periapsis(samples: list[dict]) -> dict:
    """Observed apo/peri from real telemetry (distance-from-center
    extrema), compared against the game's own live predApo/predPeri if
    present in the sample."""
    body_name = samples[0].get("body") if samples else None
    body = PLANET_CONSTANTS.get(body_name)
    radii = [(i, math.hypot(s["px"], s["py"])) for i, s in enumerate(samples) if "px" in s and "py" in s]
    if not radii:
        return {"error": "no position data"}
    max_r_idx, max_r = max(radii, key=lambda p: p[1])
    min_r_idx, min_r = min(radii, key=lambda p: p[1])
    out = {
        "observed_apoapsis_altitude_m": max_r - body["radius_m"] if body else None,
        "observed_periapsis_altitude_m": min_r - body["radius_m"] if body else None,
        "observed_apoapsis_idx": max_r_idx,
        "observed_periapsis_idx": min_r_idx,
    }
    pred_apo = samples[max_r_idx].get("predApo")
    pred_peri = samples[min_r_idx].get("predPeri")
    if pred_apo is not None and body:
        out["predicted_apoapsis_altitude_m"] = pred_apo - body["radius_m"]
    if pred_peri is not None and body:
        out["predicted_periapsis_altitude_m"] = pred_peri - body["radius_m"]
    return out


def estimate_delta_v(samples: list[dict], start: int, end: int, isp: Optional[float] = None) -> dict:
    """Tsiolkovsky rocket equation from mass loss over [start,end]. ISP
    is NOT reliably present in telemetry (fuelByStage has been observed
    empty in real flights) -- caller must supply it (e.g. from a
    snapshot's per-engine data via rocket_summary) or this returns a
    note rather than a fabricated number."""
    m0 = samples[start].get("m")
    m1 = samples[end].get("m")
    if m0 is None or m1 is None or m1 >= m0:
        return {"error": "no mass loss in this range, or missing mass data"}
    if isp is None:
        return {
            "mass_start_t": m0, "mass_end_t": m1,
            "delta_v": None,
            "note": "ISP not provided and not reliably available in telemetry "
                    "(fuelByStage has been observed empty in real flights) -- "
                    "pass isp= explicitly (e.g. from sfsprobe_rocket_summary's "
                    "per-engine data) to get a real delta-v number.",
        }
    g0 = 9.8  # tonnes-force convention used throughout this project's confirmed formulas
    dv = isp * g0 * math.log(m0 / m1)
    return {"mass_start_t": m0, "mass_end_t": m1, "isp_used": isp, "delta_v_ms": dv}


# ---------------------------------------------------------------------------
# Stage 6 -- comparison
# ---------------------------------------------------------------------------

def compare_flights(samples_a: list[dict], samples_b: list[dict], fields: list[str]) -> dict:
    stats_a = field_stats(samples_a, fields)
    stats_b = field_stats(samples_b, fields)
    out = {}
    for f in fields:
        a, b = stats_a.get(f, {}), stats_b.get(f, {})
        out[f] = {"flight_a": a, "flight_b": b}
        if a.get("mean") is not None and b.get("mean") is not None:
            out[f]["mean_diff"] = b["mean"] - a["mean"]
    return out


# ---------------------------------------------------------------------------
# Stage 8 -- pre-flight/design-time, from a snapshot (not flight telemetry)
# ---------------------------------------------------------------------------

def rocket_summary(snapshot: dict) -> dict:
    """From a 'snapshot' command's JSON dump (sfs_probe_flight.json).
    Total mass and per-part list always available (mass.Value is real
    live-evaluated data, not the parametric expression string -- see
    sfs_physics_reference.md section 1.2's data-trust rule). Thrust/ISP/
    TWR are best-effort: only populated if an engine module's fields are
    recognizable in this dump's structure; otherwise honestly reported
    as not found rather than guessed.
    """
    rockets = snapshot.get("rockets", [])
    if not rockets:
        return {"error": "no rockets in this snapshot"}
    r = rockets[0]
    parts = r.get("parts", [])
    total_mass = 0.0
    part_list = []
    engines_found = []
    for p in parts:
        mass_val = (p.get("mass") or {}).get("Value")
        name = ((p.get("orientation") or {}).get("name")) or p.get("Name") or "unknown"
        if mass_val is not None:
            total_mass += mass_val
        part_list.append({"name": name, "mass_t": mass_val})
        # Best-effort engine detection: look for thrust-like keys
        # anywhere in this part's own top-level dict (module contents
        # vary too much structurally to walk generically here).
        for key in p.keys():
            if "thrust" in key.lower() or "isp" in key.lower():
                engines_found.append({"part_name": name, "field": key, "raw": p[key]})
    out = {
        "part_count": len(parts),
        "total_mass_t": total_mass,
        "parts": part_list,
        "engine_fields_found": engines_found,
    }
    if not engines_found:
        out["note"] = ("No recognizable thrust/ISP fields found in this snapshot's part "
                        "data structure -- TWR/delta-v need those read directly via "
                        "reflection (e.g. extend the probe's snapshot command), not "
                        "reliably extractable from this dump alone yet.")
    return out


def part_lookup(snapshot: dict, name_substring: str) -> list[dict]:
    """Find parts by (case-insensitive) name substring in a snapshot dump."""
    rockets = snapshot.get("rockets", [])
    if not rockets:
        return []
    out = []
    needle = name_substring.lower()
    for p in rockets[0].get("parts", []):
        name = ((p.get("orientation") or {}).get("name")) or p.get("Name") or ""
        if needle in name.lower():
            out.append({
                "name": name,
                "mass_t": (p.get("mass") or {}).get("Value"),
                "temperature_c": p.get("Temperature") or p.get("temperature"),
                "heat_tolerance": p.get("HeatTolerance"),
            })
    return out
