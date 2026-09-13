"""
state_builder.py -- builds the per-cycle enriched state schema (sec 5)
fed to tsAI. This is the "deterministic layer computes information ...
it does not decide anything" piece from sec 2's architecture diagram:
pure computation from observe()/predict() output plus mission constants,
no menu choice logic lives here (that's tsai_client.py + menus.py) and
no accept/reject logic lives here (that's guardrail.py).
"""
import math
import sys
import os
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "analysis"))
import forward_sim as fsim  # noqa: E402


NOTE = ("Include phase and mission_target on every call -- omitting them "
        "measurably increases ambiguity and lowers confidence on "
        "otherwise-clear decisions.")


def compute_max_angular_accel_dps2(mass_t: float, torque_effective_raw: Optional[float]) -> float:
    """alpha_max = torque_effective / I, sec 4.2 -- reuses the EXACT
    mass-penalty law already confirmed live in forward_sim.compute_turn_axis
    (torque /= (mass/200)^0.35 above 200t) rather than re-deriving it, so
    this never drifts from the validated physics. Returns the angular
    accel deliverable at turn_axis=1.0 (full commanded authority)."""
    if torque_effective_raw is None or mass_t <= 0:
        return 0.0
    torque = torque_effective_raw
    if mass_t > 200.0:
        torque = torque_effective_raw / ((mass_t / 200.0) ** 0.35)
    return torque * fsim.RAD2DEG / mass_t


def compute_delta_v_remaining_mps(current_mass_t: float, dry_mass_t: float,
                                   isp: float) -> float:
    """Tsiolkovsky delta-v, in THIS codebase's isp convention: no g0
    multiplier. forward_sim._engine_thrust computes
    mass_flow = thrust_ton * throttle / isp directly, i.e. isp already
    plays the role of effective exhaust velocity in this game's internal
    units -- confirmed by reading that formula, not assumed. Using the
    standard isp*g0*ln(...) form here would silently overstate delta-v by
    ~9.8x against this project's own validated fuel-burn physics."""
    if isp <= 0 or dry_mass_t <= 0 or current_mass_t <= dry_mass_t:
        return 0.0
    return isp * math.log(current_mass_t / dry_mass_t)


def build_feasibility(current_mass_t: float, dry_mass_t: float, isp: float,
                       torque_effective_raw: Optional[float],
                       delta_v_required_for_target_mps: float) -> dict:
    return {
        "delta_v_remaining_mps": compute_delta_v_remaining_mps(current_mass_t, dry_mass_t, isp),
        "delta_v_required_for_target_mps": delta_v_required_for_target_mps,
        "max_angular_accel_dps2": compute_max_angular_accel_dps2(current_mass_t, torque_effective_raw),
    }


def compute_coast_apoapsis_m(altitude_m: float, vertical_speed_mps: float,
                              g_local_mps2: float) -> Optional[float]:
    """2026-09-13 addition (Christian's explicit request, after finding
    tsAI's own magnitude judgment genuinely uncertain in a moderate
    overshoot -- see BUILD_LOG.md): closed-form energy-conservation
    estimate of the altitude this trajectory would coast up to if thrust
    were cut THIS INSTANT (h + v^2/2g, ignoring drag and horizontal
    motion -- a documented simplification, same spirit as this file's
    other physics estimates). This answers, directly and numerically,
    "even if I stop adding thrust right now, how far past/short of the
    target will I still end up" -- the exact question tsAI was having to
    eyeball from raw altitude/speed/feasibility numbers before. Distinct
    from `prediction.terminal_error`, which assumes throttle/turn_axis
    HOLD UNCHANGED for a fixed 15s horizon; this assumes an immediate
    full cutoff, the relevant comparison for "should I be backing off
    right now, and by how much." Returns the current altitude (no
    further ballistic gain) when vertical_speed_mps <= 0 -- already
    falling, coasting adds nothing more upward. Returns None if g_local
    isn't usable (<=0) -- never fabricates a number from bad physics."""
    if g_local_mps2 is None or g_local_mps2 <= 0:
        return None
    if vertical_speed_mps <= 0:
        return altitude_m
    return altitude_m + (vertical_speed_mps ** 2) / (2.0 * g_local_mps2)


def build_prediction_block(predict_result: Optional[dict], horizon_s: float,
                            target_altitude_m: Optional[float] = None,
                            target_speed_mps: Optional[float] = None,
                            current_altitude_m: Optional[float] = None,
                            current_vertical_speed_mps: Optional[float] = None,
                            g_local_mps2: Optional[float] = None) -> dict:
    """Adapts agent_interface.predict()'s return shape into sec 5's
    compact `prediction` block. predict_result may be None (e.g. first
    cycle, no prior prediction to compare against) -- returns a
    conservative low-confidence stub in that case rather than fabricating
    a terminal_error of 0, which would look like a clean prediction to
    tsAI and the guardrail alike.

    2026-09-13: also computes `coast_apoapsis_m` (and its error vs
    target) whenever the current altitude/vertical-speed/g_local inputs
    are supplied -- independent of predict_result, so it's available
    even on a cycle where predict() itself failed or returned None (see
    compute_coast_apoapsis_m's docstring for what it answers and why)."""
    coast_apoapsis_m = None
    coast_apoapsis_error_m = None
    if current_altitude_m is not None and current_vertical_speed_mps is not None:
        coast_apoapsis_m = compute_coast_apoapsis_m(
            current_altitude_m, current_vertical_speed_mps, g_local_mps2)
        if coast_apoapsis_m is not None and target_altitude_m is not None:
            coast_apoapsis_error_m = coast_apoapsis_m - target_altitude_m

    if predict_result is None:
        return {"confidence": "low", "horizon_s": horizon_s,
                "terminal_error": {"altitude_m": None, "speed_mps": None},
                "coast_apoapsis_m": coast_apoapsis_m,
                "coast_apoapsis_error_m": coast_apoapsis_error_m}

    final = predict_result.get("final", {}) or {}
    alt_err = None
    speed_err = None
    if target_altitude_m is not None and "h" in final:
        alt_err = final["h"] - target_altitude_m
    if target_speed_mps is not None and "v" in final:
        speed_err = final["v"] - target_speed_mps

    return {
        "confidence": predict_result.get("confidence", "low"),
        "horizon_s": horizon_s,
        "terminal_error": {"altitude_m": alt_err, "speed_mps": speed_err},
        "coast_apoapsis_m": coast_apoapsis_m,
        "coast_apoapsis_error_m": coast_apoapsis_error_m,
    }


def build_state(cycle_id: int, t: float, phase: str, mission_target: dict,
                 vehicle: dict, feasibility: dict, prediction: dict) -> dict:
    """Assembles the exact sec 5 schema. `vehicle` must already contain
    altitude_m, vertical_speed_mps, horizontal_speed_mps, angle_deg,
    angular_rate_dps, throttle, active_stage, fuel_remaining_pct."""
    return {
        "cycle_id": cycle_id,
        "t": t,
        "phase": phase,
        "mission_target": mission_target,
        "vehicle": vehicle,
        "feasibility": feasibility,
        "prediction": prediction,
        "note": NOTE,
    }
