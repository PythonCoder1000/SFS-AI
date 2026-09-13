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


def build_prediction_block(predict_result: Optional[dict], horizon_s: float,
                            target_altitude_m: Optional[float] = None,
                            target_speed_mps: Optional[float] = None) -> dict:
    """Adapts agent_interface.predict()'s return shape into sec 5's
    compact `prediction` block. predict_result may be None (e.g. first
    cycle, no prior prediction to compare against) -- returns a
    conservative low-confidence stub in that case rather than fabricating
    a terminal_error of 0, which would look like a clean prediction to
    tsAI and the guardrail alike."""
    if predict_result is None:
        return {"confidence": "low", "horizon_s": horizon_s,
                "terminal_error": {"altitude_m": None, "speed_mps": None}}

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
