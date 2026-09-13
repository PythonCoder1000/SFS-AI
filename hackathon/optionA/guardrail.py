"""
guardrail.py -- Checkpoint 2: confidence-band gate (sec 4.1) + feasibility
check (sec 4.2). Pure functions, no network/game I/O, so they're cheap to
unit-test in isolation (test_checkpoint2.py) and to reuse unchanged from
the live loop (pilot_loop.py).

Every rejection returns a typed reason string (never a silent pass-through
or a silent override) -- BUILD_SPEC sec 4.2/6 both require this to be
loud, not swallowed.
"""
from dataclasses import dataclass
from typing import Optional

from menus import TURN_AXIS_DELTA, THROTTLE_DELTA, QUESTION_CLASS

# ---------------------------------------------------------------------------
# 4.1 -- confidence bands
# ---------------------------------------------------------------------------
# This project's adapted bands (BUILD_SPEC sec 4.1) -- NOT the vendor's
# flat 0.5 floor. Grounded in real testing showing good decisions across
# a 0.5-0.9 confidence range depending on situation clarity; stricter than
# vendor default because there is no human in the loop to catch a
# borderline-bad answer after the fact.
BANDS = {
    "routine": {"reject_below": 0.5, "caution_below": 0.7},
    "irreversible": {"reject_below": 0.7, "caution_below": 0.9},
}


def confidence_of(answer: dict) -> float:
    """Extracts a 0-1 confidence value from any of the three tsAI answer
    shapes (choice/score have a native `confidence`; noul does not --
    BUILD_SPEC sec 3 -- so we use the documented analog
    abs(noul - 0.5) * 2 for that case. Never reads `.confidence` on a
    noul answer -- see the spec's explicit warning; that field simply
    isn't there)."""
    if "noul" in answer:
        return abs(answer["noul"] - 0.5) * 2.0
    return float(answer.get("confidence", 0.0))


@dataclass
class GateResult:
    accepted: bool
    band: str            # "reject" | "caution" | "normal"
    reason: Optional[str]  # None if accepted cleanly; set on reject or caution-with-detail


def confidence_gate(question_name: str, answer: dict) -> GateResult:
    """4.1 confidence-band check only -- does not touch feasibility."""
    question_class = QUESTION_CLASS.get(question_name, "routine")
    band_cfg = BANDS[question_class]
    conf = confidence_of(answer)

    if conf < band_cfg["reject_below"]:
        return GateResult(False, "reject",
                           f"confidence {conf:.3f} < reject_below {band_cfg['reject_below']} "
                           f"for class={question_class}")
    if conf < band_cfg["caution_below"]:
        return GateResult(True, "caution",
                           f"confidence {conf:.3f} in caution band "
                           f"[{band_cfg['reject_below']}, {band_cfg['caution_below']}) "
                           f"for class={question_class} -- feasibility must pass WITH MARGIN")
    return GateResult(True, "normal", None)


# ---------------------------------------------------------------------------
# 4.2 -- feasibility check
# ---------------------------------------------------------------------------
# Margin multiplier applied to every feasibility threshold below when the
# confidence gate returned "caution" -- BUILD_SPEC sec 4.1: caution-band
# answers must pass feasibility "with margin, not just pass".
CAUTION_MARGIN = 1.5


def check_throttle_feasibility(choice: str, state: dict, band: str) -> GateResult:
    feas = state.get("feasibility", {})
    dv_remaining = feas.get("delta_v_remaining_mps", 0.0)
    dv_required = feas.get("delta_v_required_for_target_mps", 0.0)
    margin = CAUTION_MARGIN if band == "caution" else 1.0

    if choice in ("increase_small", "increase_large"):
        # Spending more delta-v requires it to actually exist, with margin
        # over what the remaining ascent still needs.
        needed_margin_mps = 25.0 * margin if choice == "increase_small" else 75.0 * margin
        if dv_remaining < dv_required + needed_margin_mps:
            return GateResult(False, "reject",
                               f"throttle {choice}: delta_v_remaining "
                               f"{dv_remaining:.1f} < required {dv_required:.1f} "
                               f"+ margin {needed_margin_mps:.1f}")
    # decrease_small/decrease_large/hold/cut never spend additional
    # delta-v budget -- always feasible from a budget standpoint.
    return GateResult(True, band, None)


def check_pitch_feasibility(choice: str, state: dict, band: str) -> GateResult:
    vehicle = state.get("vehicle", {})
    feas = state.get("feasibility", {})
    max_alpha = feas.get("max_angular_accel_dps2", 0.0)
    current_rate = vehicle.get("angular_rate_dps", 0.0)
    margin = CAUTION_MARGIN if band == "caution" else 1.0

    if max_alpha <= 0.0:
        return GateResult(False, "reject",
                           "pitch feasibility: max_angular_accel_dps2 <= 0 "
                           "(no usable torque authority data) -- cannot verify")

    delta = TURN_AXIS_DELTA.get(choice, 0.0)
    if delta == 0.0:
        return GateResult(True, band, None)  # "hold" is always feasible

    # Assume this cycle's command is held for ~1s (conservative -- real
    # cycle period is shorter; overestimating dt overestimates the rate
    # change, which is the safe direction for a feasibility REJECT check).
    assumed_dt_s = 1.0
    projected_rate = current_rate + delta * max_alpha * assumed_dt_s

    # Safe bound: don't let a single cycle's command push the projected
    # angular rate past 2x the vehicle's own max angular acceleration
    # (dps2 used as a dps ceiling here is a deliberate, documented
    # simplification -- see BUILD_LOG.md Checkpoint 2 entry -- it keeps
    # the projected rate within "recoverable in about half a second at
    # full opposite authority" of this vehicle, which is the property
    # that actually matters for a gravity-turn ascent, not the specific
    # dps vs dps2 unit dimension).
    safe_bound_dps = max_alpha * 2.0 / margin
    if abs(projected_rate) > safe_bound_dps:
        return GateResult(False, "reject",
                           f"pitch {choice}: projected angular rate "
                           f"{projected_rate:.2f} dps exceeds safe bound "
                           f"{safe_bound_dps:.2f} dps (max_alpha={max_alpha:.2f})")
    return GateResult(True, band, None)


def check_stage_feasibility(choice: str, state: dict, band: str) -> GateResult:
    feas = state.get("feasibility", {})
    vehicle = state.get("vehicle", {})
    dv_remaining = feas.get("delta_v_remaining_mps", 0.0)
    dv_required = feas.get("delta_v_required_for_target_mps", 0.0)
    fuel_pct = vehicle.get("fuel_remaining_pct", 100.0)
    margin = CAUTION_MARGIN if band == "caution" else 1.0

    if choice == "stage_now":
        # Staging is only justified when the CURRENT stage is genuinely
        # spent or cannot meet the remaining requirement -- staging a
        # healthy stage away is itself an irreversible mistake.
        fuel_exhausted = fuel_pct <= (5.0 / margin)
        cannot_meet_target = dv_remaining < dv_required
        if not (fuel_exhausted or cannot_meet_target):
            return GateResult(False, "reject",
                               f"stage_now: current stage not exhausted "
                               f"(fuel_remaining_pct={fuel_pct:.1f}, "
                               f"delta_v_remaining={dv_remaining:.1f} >= "
                               f"required={dv_required:.1f}) -- staging now "
                               f"would discard a usable stage")
    return GateResult(True, band, None)


FEASIBILITY_CHECKS = {
    "throttle_action": check_throttle_feasibility,
    "pitch_action": check_pitch_feasibility,
    "stage_check": check_stage_feasibility,
}


def evaluate(question_name: str, answer: dict, state: dict) -> GateResult:
    """Full guardrail: confidence gate, then (if not already rejected)
    feasibility check for the chosen option. `insufficient_data`/
    `hold_stage` are never fed through feasibility -- they're always the
    safe no-op regardless of confidence band, so accepting them needs no
    physics check."""
    conf_result = confidence_gate(question_name, answer)
    if not conf_result.accepted:
        return conf_result

    choice = answer.get("choice")
    if choice in ("insufficient_data", "hold_stage", None):
        return conf_result

    feasibility_fn = FEASIBILITY_CHECKS.get(question_name)
    if feasibility_fn is None:
        return conf_result

    feas_result = feasibility_fn(choice, state, conf_result.band)
    if not feas_result.accepted:
        return feas_result
    return conf_result
