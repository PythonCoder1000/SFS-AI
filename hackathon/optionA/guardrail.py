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

from menus import TURN_AXIS_DELTA, QUESTION_CLASS, throttle_score_to_delta

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
    isn't there).

    2026-09-13: previously had a temporary workaround here deriving
    score's confidence from `probabilities` (max-probability proxy),
    added after early samples all happened to show native confidence at
    or near 0. Removed after further testing: deliberately extreme,
    unambiguous situations showed native confidence tracking real
    situation clarity correctly (0.94/0.70 when genuinely obvious, low
    only when the situation was itself genuinely ambiguous) -- it was
    never broken, just an honest signal. Trust it directly, same as
    choice."""
    if "noul" in answer:
        return abs(answer["noul"] - 0.5) * 2.0
    return float(answer.get("confidence", 0.0))


# 2026-09-13 LATER SAME DAY fix (Christian's explicit request, following
# vendor doc confirmation -- console.typesafe.ai/docs/confidence and
# .../primitives/score, read directly, not assumed): vendor's own docs
# state plainly that `confidence` is "derived from the probabilities
# distribution" as a general FLATNESS statistic ("a flatter distribution
# means lower confidence"), and explicitly invite a domain-specific
# derived measure instead when the native one doesn't fit ("you are never
# locked into our definition ... which is exactly why we give you the
# full probabilities in the response"). throttle_score's six levels are
# NOT all decision-distinct for this project's purposes -- 0/1/2 all mean
# "decrease by some amount", 4/5 both mean "increase by some amount" --
# so probability legitimately spreads across 2-3 adjacent levels even
# when the DIRECTION is completely unambiguous, which native confidence
# (a flatness measure over all 6 levels) reads as "uncertain" regardless.
# CONFIRMED EMPIRICALLY across three real live flights this same day:
# combined decrease-side probability was consistently 67-84% on cycles
# where native confidence sat at 0.1-0.5 and the guardrail rejected every
# one -- see bookkeeping/active_state.md for the full cycle-by-cycle data
# pulled from Weave. Pooling into three decision-relevant groups (below)
# is the direct fix.
THROTTLE_SCORE_DECREASE_KEYS = ("0", "1", "2")
THROTTLE_SCORE_HOLD_KEY = "3"
THROTTLE_SCORE_INCREASE_KEYS = ("4", "5")


def throttle_score_directional_confidence(probabilities: dict) -> float:
    """Pools throttle_score's per-level probabilities into
    {decrease: 0+1+2, hold: 3, increase: 4+5} and returns the max pooled
    mass -- the "is the DIRECTION clear" analog of vendor confidence
    (which measures "is any SINGLE level clear" instead, per its own
    docs). Returns 0.0 defensively if probabilities is missing/empty --
    never fabricates confidence from nothing, same fail-safe convention
    as the rest of this project's physics/state functions."""
    if not probabilities:
        return 0.0
    decrease = sum(probabilities.get(k, 0.0) for k in THROTTLE_SCORE_DECREASE_KEYS)
    hold = probabilities.get(THROTTLE_SCORE_HOLD_KEY, 0.0)
    increase = sum(probabilities.get(k, 0.0) for k in THROTTLE_SCORE_INCREASE_KEYS)
    return max(decrease, hold, increase)


def effective_confidence(question_name: str, answer: dict) -> float:
    """The confidence value actually used for the guardrail gate --
    native vendor confidence (confidence_of()) for every question type
    EXCEPT throttle_score, which uses throttle_score_directional_
    confidence() instead. Centralized here (rather than duplicated in
    confidence_gate() and pilot_loop.py's per-cycle logging) so the
    gate and the log line displaying "why" can never silently drift onto
    different numbers for the same answer."""
    if question_name == "throttle_score" and answer.get("probabilities"):
        return throttle_score_directional_confidence(answer["probabilities"])
    return confidence_of(answer)


@dataclass
class GateResult:
    accepted: bool
    band: str            # "reject" | "caution" | "normal"
    reason: Optional[str]  # None if accepted cleanly; set on reject or caution-with-detail


def confidence_gate(question_name: str, answer: dict) -> GateResult:
    """4.1 confidence-band check only -- does not touch feasibility.

    2026-09-13 LATER SAME DAY: uses effective_confidence() rather than
    confidence_of() directly -- see that function's docstring. Every
    question type except throttle_score is completely unaffected (they
    resolve to the exact same value confidence_of() would have given)."""
    question_class = QUESTION_CLASS.get(question_name, "routine")
    band_cfg = BANDS[question_class]
    conf = effective_confidence(question_name, answer)

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


def check_throttle_score_feasibility(score: float, state: dict, band: str) -> GateResult:
    """2026-09-13: generalizes check_throttle_feasibility (below, now
    unused/removed) to throttle_score's continuous scale -- same margin
    logic, continuous instead of two fixed buckets. Only an INCREASE
    (delta > 0) spends additional delta-v budget and needs a margin
    check; hold/decrease/cut are always feasible from a budget
    standpoint, same as before."""
    delta = throttle_score_to_delta(score)
    if delta <= 0.0:
        return GateResult(True, band, None)

    feas = state.get("feasibility", {})
    dv_remaining = feas.get("delta_v_remaining_mps", 0.0)
    dv_required = feas.get("delta_v_required_for_target_mps", 0.0)
    margin = CAUTION_MARGIN if band == "caution" else 1.0

    # Scale the needed margin continuously with the size of the increase
    # requested (25m/s at a token increase, up to 75m/s at the full
    # +0.20 increase_large anchor) instead of two fixed thresholds --
    # same spirit as the old 25/75 buckets, continuous instead of
    # stepped.
    needed_margin_mps = (25.0 + (delta / 0.20) * 50.0) * margin
    if dv_remaining < dv_required + needed_margin_mps:
        return GateResult(False, "reject",
                           f"throttle_score {score:.2f} (delta={delta:+.3f}): "
                           f"delta_v_remaining {dv_remaining:.1f} < required "
                           f"{dv_required:.1f} + margin {needed_margin_mps:.1f}")
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
    "throttle_score": check_throttle_score_feasibility,
    "pitch_action": check_pitch_feasibility,
    "stage_check": check_stage_feasibility,
}
# No entry for launch_decision -- same as before (the old code never had
# a feasibility function for the 'launch' choice either): the confidence
# gate plus tsAI's own thrust_to_weight_max/feasibility-aware criteria
# are the only checks on that one, and the preflight gate
# (_preflight_feasibility_gate in pilot_loop.py) already establishes the
# mission is achievable at full fuel before launch is ever offered.


def evaluate(question_name: str, answer: dict, state: dict) -> GateResult:
    """Full guardrail: confidence gate, then (if not already rejected)
    feasibility check. `insufficient_data`/`hold_stage` are never fed
    through feasibility -- they're always the safe no-op regardless of
    confidence band, so accepting them needs no physics check.

    2026-09-13: throttle_score answers carry `score`, not `choice` (no
    named no-op value to skip the way insufficient_data/hold_stage are
    for the choice-type questions) -- always run its feasibility check
    once the confidence gate passes."""
    conf_result = confidence_gate(question_name, answer)
    if not conf_result.accepted:
        return conf_result

    feasibility_fn = FEASIBILITY_CHECKS.get(question_name)
    if feasibility_fn is None:
        return conf_result

    if question_name == "throttle_score":
        feas_result = feasibility_fn(answer.get("score", 0.0), state, conf_result.band)
    else:
        choice = answer.get("choice")
        if choice in ("insufficient_data", "hold_stage", None):
            return conf_result
        feas_result = feasibility_fn(choice, state, conf_result.band)

    if not feas_result.accepted:
        return feas_result
    return conf_result
