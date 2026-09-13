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
        "otherwise-clear decisions. "
        "UNIT/CONVENTION WARNING, specific to THIS game's physics engine "
        "(2026-09-13, Christian's explicit request -- tsAI self-reported "
        "80% combined likelihood of exactly this class of confusion): "
        "do NOT apply real-world aerospace formulas or intuition to the "
        "numbers below without adjusting for how THIS game actually "
        "defines them. Specifically -- "
        "(1) `delta_v_remaining_mps`/`delta_v_required_for_target_mps` "
        "already use this game's own convention: isp is applied DIRECTLY "
        "with NO g0=9.8 multiplier (isp*ln(mass_ratio), not the standard "
        "isp*g0*ln(mass_ratio)). These numbers are already correct AS "
        "GIVEN -- do not mentally rescale them by ~9.8x using the "
        "standard rocket equation, and do not treat a delta-v figure that "
        "looks 'too small' by real-world standards as evidence something "
        "is wrong with the state. "
        "(2) `thrust_to_weight_current`/`thrust_to_weight_max` are plain "
        "force/weight ratios in THIS game's own physics, which permits "
        "meaningfully higher values than real rockets -- a value of 3-4+ "
        "is a strong, valid, unremarkable craft here, not an implausible "
        "or suspicious one by real-world TWR intuition (~1.2-2.0).")


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


def build_physics_block(mass_t: float, g_local_mps2: Optional[float],
                         total_thrust_t: float, throttle: float) -> dict:
    """2026-09-13 addition (Christian's explicit request, after tsAI
    self-reported only 52%/47% confidence on 'are you good at physics'/
    'spaceflight physics' -- see bookkeeping/active_state.md). Where
    coast_apoapsis_m hands tsAI one precomputed ANSWER, this hands it the
    INTERMEDIATE terms of the same confirmed thrust/gravity formulas
    already used everywhere else in this project
    (sfs_physics_reference.md sec 1.3/2.1), each labeled with the literal
    formula that produced it -- the closest equivalent to an inspectable
    scratchpad the systemone API's schema allows, since none of its three
    question types (choice/noul/score, BUILD_SPEC sec 3) return free text
    tsAI could 'show work' in. The goal is forcing explicit, ordered use
    of the real formulas as INPUT, in place of letting tsAI implicitly
    pattern-match over a single derived number.

    Ignores drag and off-vertical thrust components -- same documented
    simplification as compute_coast_apoapsis_m, deliberately, for the
    same reason (a closed-form estimate tsAI can actually reason about
    each cycle, not a full integrator run). Returns a null block (all
    None) if g_local isn't usable, same fail-safe convention as
    compute_coast_apoapsis_m -- never fabricates a physics number from
    bad inputs.

    2026-09-13 LATER SAME DAY: unwired from the live pipeline
    (pilot_loop.py no longer calls this or attaches its output to
    state). A real live flight test showed confidence on throttle_score
    collapsing over cycles 15-29 (0.48 down to 0.09) despite this block
    being present every cycle -- it didn't hurt, but it didn't prevent
    the actual failure mode either (see bookkeeping/active_state.md).
    Christian's call: leave this function intact for a reshape rather
    than deleting it, but stop sending it until there's a better shape.
    Do not re-wire into build_state/build_cycle_state without an
    explicit decision to do so."""
    if g_local_mps2 is None or g_local_mps2 <= 0 or mass_t <= 0:
        return {
            "thrust_accel_mps2": None, "gravity_accel_mps2": None,
            "net_accel_mps2": None,
            "formulas": {
                "thrust_accel_mps2": "total_thrust_t * 9.8 * throttle / mass_t",
                "gravity_accel_mps2": "mu / r^2 (confirmed gravity law)",
                "net_accel_mps2": "thrust_accel_mps2 - gravity_accel_mps2",
            },
        }
    thrust_accel_mps2 = total_thrust_t * 9.8 * throttle / mass_t
    net_accel_mps2 = thrust_accel_mps2 - g_local_mps2
    return {
        "thrust_accel_mps2": thrust_accel_mps2,
        "gravity_accel_mps2": g_local_mps2,
        "net_accel_mps2": net_accel_mps2,
        "formulas": {
            "thrust_accel_mps2": "total_thrust_t * 9.8 * throttle / mass_t",
            "gravity_accel_mps2": "mu / r^2 (confirmed gravity law)",
            "net_accel_mps2": "thrust_accel_mps2 - gravity_accel_mps2 "
                "(positive = still climbing/accelerating upward, "
                "negative = decelerating/falling)",
        },
    }


def compute_coast_apoapsis_trend(current_error_m: Optional[float], current_t: Optional[float],
                                  prev_history_entry: Optional[dict],
                                  current_phase: Optional[str] = None) -> dict:
    """2026-09-13 LATER SAME DAY addition (Christian's explicit request,
    following the real-flight finding that the remaining overshoot after
    the confidence-gate fix wasn't a reasoning bug -- score WAS tracking
    coast_apoapsis_error_m closing in, smoothly, cycles 1-13 -- it's a
    physics timing problem: on a high-T/W craft, coast_apoapsis_m grows
    with vy^2, so the error can go from -1077m to -368m in ONE cycle and
    strongly positive the cycle after. There are only ~2 cycles of real
    warning between 'clearly still short' and 'about to badly overshoot'.
    See bookkeeping/active_state.md for the full cycle-by-cycle numbers
    (cycles 0-13 of the 2026-09-13 directional-confidence live flight)
    this diagnosis is based on.

    Computes the closing RATE of coast_apoapsis_error_m (how fast the
    error is moving toward/through zero, in m/s) from the current value
    and the most recent entry in state.history, plus a linear
    extrapolation of how many seconds until it crosses zero AT THAT RATE
    -- the 'start backing off now, before the raw number says to' signal
    that was missing. This is deliberately a simple linear extrapolation
    over one cycle's delta, not a fitted trend over the whole history --
    matches this file's existing closed-form-over-full-integration
    philosophy (see compute_coast_apoapsis_m's docstring).

    2026-09-13 EVEN LATER SAME DAY -- three fixes after external review
    flagged real risks in how this gets USED, not how it's computed:

    (1) Renamed the crossover field to `linear_seconds_to_crossover`
        (was `seconds_to_crossover`) -- a bare `error / rate` from ONE
        step is a local linear extrapolation, not a forecast in the same
        sense as the real 15s forward-integrator (`terminal_error`). The
        old name invited treating a decimal-precision number as an event
        schedule. The name itself is now the caveat.
    (2) Returns `valid: bool` -- False whenever the trend shouldn't be
        trusted numerically: no prior point, non-positive/absurd dt
        (>2s -- spans a watchdog hold/degrade or a slow cycle, not a
        clean back-to-back sample), OR the prior entry's phase differs
        from `current_phase` (a PAD_IDLE->ASCENT_GRAVITY_TURN transition
        produces a meaningless 'closure rate' across the launch step).
        `closure_rate_mps`/`linear_seconds_to_crossover` are still
        returned even when invalid (never silently swapped for None) so
        a caller can still see the raw number if it wants to -- but the
        menu instructions tell tsAI to check `valid` before leaning on
        it numerically.
    (3) `current_phase` is optional and defaults to None (skips the
        phase check, same permissive behavior as before) so existing
        callers/tests that don't pass it keep working.

    Returns `closure_rate_mps`/`linear_seconds_to_crossover` as None
    (with `valid: False`) when there's no usable prior point at all --
    never fabricates a trend from one data point.
    `linear_seconds_to_crossover` is left None (not a negative or
    nonsensical number) when the extrapolation doesn't point at an
    upcoming crossover (error moving away from zero, or already past it
    and continuing to diverge) -- the caller should read a None here as
    'no crossover predicted at the current rate', not as missing data."""
    if current_error_m is None or current_t is None or not prev_history_entry:
        return {"closure_rate_mps": None, "linear_seconds_to_crossover": None, "valid": False}
    prev_error_m = prev_history_entry.get("coast_apoapsis_error_m")
    prev_t = prev_history_entry.get("t")
    if prev_error_m is None or prev_t is None:
        return {"closure_rate_mps": None, "linear_seconds_to_crossover": None, "valid": False}
    dt = current_t - prev_t
    if dt <= 0:
        return {"closure_rate_mps": None, "linear_seconds_to_crossover": None, "valid": False}
    closure_rate_mps = (current_error_m - prev_error_m) / dt
    linear_seconds_to_crossover = None
    if closure_rate_mps != 0:
        dt_future = -current_error_m / closure_rate_mps
        if dt_future > 0:
            linear_seconds_to_crossover = dt_future
    valid = dt <= 2.0
    prev_phase = prev_history_entry.get("phase")
    if current_phase is not None and prev_phase is not None and prev_phase != current_phase:
        valid = False
    return {"closure_rate_mps": closure_rate_mps,
            "linear_seconds_to_crossover": linear_seconds_to_crossover,
            "valid": valid}


def compute_action_conditioned_apoapsis(altitude_m: float, vertical_speed_mps: float,
                                         g_local_mps2: Optional[float], mass_t: Optional[float],
                                         total_thrust_t: Optional[float], current_throttle: float,
                                         target_altitude_m: Optional[float] = None,
                                         lookahead_s: float = 1.0) -> Optional[dict]:
    """2026-09-13 EVEN LATER SAME DAY addition (Christian's explicit
    request, following external review of the state shape): the single
    `coast_apoapsis_m` above answers ONE question -- 'where do I end up
    if I cut thrust THIS INSTANT' -- but throttle_score's real choices
    range from full cut to full increase, and the model was left to
    mentally interpolate between 'coast_apoapsis_m' (implicitly the cut
    case) and 'current trajectory continues' for everything in between.
    This computes the SAME closed-form coast-apoapsis answer for a small
    set of CANDIDATE ACTIONS instead of just the cut case, so the model
    is choosing between precomputed CONSEQUENCES rather than
    interpolating between two implicit anchors.

    Mechanism, per candidate throttle: project vertical velocity/altitude
    forward `lookahead_s` seconds under that throttle held constant
    (thrust_accel = total_thrust_t * 9.8 * throttle / mass_t, same
    confirmed formula as the retired build_physics_block() -- reused
    here, but its OUTPUT is exposed, not the formula terms themselves,
    same 'hand it answers, not a scratchpad' philosophy as
    compute_coast_apoapsis_m), then run the existing coast_apoapsis_m
    closed form from that projected point. Same documented
    simplifications as the rest of this file (ignores drag, horizontal
    motion, off-vertical thrust) -- a short, cheap, closed-form estimate
    per candidate, not a full integrator run per candidate.

    Candidates are the four THROTTLE_SCORE_LEVELS anchors that represent
    a genuinely distinct action (cut/decrease_large/hold/increase_large
    -- the two 'small' anchors are skipped to keep this a small,
    scannable set, per the external-review request to avoid an
    overwhelming number of near-duplicate fields). Each candidate's
    throttle is clamped to [0, 1] against the CURRENT throttle, matching
    how a real correction would actually be applied.

    Returns None (not a null dict) if g_local/mass_t aren't usable --
    same fail-safe convention as the rest of this file. Each candidate's
    value is itself an {'apoapsis_m', 'error_m'} pair, `error_m` being
    apoapsis_m minus target_altitude_m (omitted/None if no target is
    supplied) so the model doesn't have to subtract on its own."""
    if g_local_mps2 is None or g_local_mps2 <= 0 or mass_t is None or mass_t <= 0:
        return None
    thrust_t = total_thrust_t or 0.0
    candidate_throttles = {
        "if_cut": 0.0,
        "if_decrease_large": max(0.0, current_throttle - 0.20),
        "if_hold": current_throttle,
        "if_increase_large": min(1.0, current_throttle + 0.20),
    }
    result = {}
    for label, throttle in candidate_throttles.items():
        thrust_accel_mps2 = thrust_t * 9.8 * throttle / mass_t
        net_accel_mps2 = thrust_accel_mps2 - g_local_mps2
        vy_after = vertical_speed_mps + net_accel_mps2 * lookahead_s
        alt_after = (altitude_m + vertical_speed_mps * lookahead_s
                     + 0.5 * net_accel_mps2 * (lookahead_s ** 2))
        apo = compute_coast_apoapsis_m(alt_after, vy_after, g_local_mps2)
        entry = {"apoapsis_m": apo}
        if apo is not None and target_altitude_m is not None:
            entry["error_m"] = apo - target_altitude_m
        result[label] = entry
    return result


def build_prediction_block(predict_result: Optional[dict], horizon_s: float,
                            target_altitude_m: Optional[float] = None,
                            target_speed_mps: Optional[float] = None,
                            current_altitude_m: Optional[float] = None,
                            current_vertical_speed_mps: Optional[float] = None,
                            g_local_mps2: Optional[float] = None,
                            current_t: Optional[float] = None,
                            prev_history_entry: Optional[dict] = None,
                            current_phase: Optional[str] = None,
                            mass_t: Optional[float] = None,
                            total_thrust_t: Optional[float] = None,
                            current_throttle: Optional[float] = None) -> dict:
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
    compute_coast_apoapsis_m's docstring for what it answers and why).

    2026-09-13 LATER SAME DAY: also computes the coast_apoapsis_error_m
    CLOSING RATE (see compute_coast_apoapsis_trend()'s docstring) when
    `current_t` and `prev_history_entry` (the most recent entry from
    PilotRun.cycle_history, i.e. state.history[-1] before this cycle's
    entry is appended) are supplied. Both optional and default None so
    existing callers/tests that don't pass them keep working -- the trend
    fields come back as None in that case, same fail-safe convention as
    the rest of this function. `current_phase` (also optional) enables
    compute_coast_apoapsis_trend()'s phase-consistency validity check.

    2026-09-13 EVEN LATER SAME DAY: also computes
    `action_conditioned_apoapsis` (see
    compute_action_conditioned_apoapsis()'s docstring) when `mass_t`,
    `total_thrust_t`, and `current_throttle` are all supplied -- omitted
    entirely (key absent, not a null dict) when any is missing, same
    convention as `physics`/`history` in build_state()."""
    coast_apoapsis_m = None
    coast_apoapsis_error_m = None
    if current_altitude_m is not None and current_vertical_speed_mps is not None:
        coast_apoapsis_m = compute_coast_apoapsis_m(
            current_altitude_m, current_vertical_speed_mps, g_local_mps2)
        if coast_apoapsis_m is not None and target_altitude_m is not None:
            coast_apoapsis_error_m = coast_apoapsis_m - target_altitude_m

    trend = compute_coast_apoapsis_trend(coast_apoapsis_error_m, current_t, prev_history_entry,
                                          current_phase=current_phase)

    action_conditioned = None
    if (mass_t is not None and total_thrust_t is not None and current_throttle is not None
            and current_altitude_m is not None and current_vertical_speed_mps is not None):
        action_conditioned = compute_action_conditioned_apoapsis(
            current_altitude_m, current_vertical_speed_mps, g_local_mps2,
            mass_t, total_thrust_t, current_throttle, target_altitude_m=target_altitude_m)

    if predict_result is None:
        block = {"confidence": "low", "horizon_s": horizon_s,
                 "terminal_error": {"altitude_m": None, "speed_mps": None},
                 "coast_apoapsis_m": coast_apoapsis_m,
                 "coast_apoapsis_error_m": coast_apoapsis_error_m,
                 "coast_apoapsis_closure_rate_mps": trend["closure_rate_mps"],
                 "coast_apoapsis_linear_seconds_to_crossover": trend["linear_seconds_to_crossover"],
                 "coast_apoapsis_trend_valid": trend["valid"]}
        if action_conditioned is not None:
            block["action_conditioned_apoapsis"] = action_conditioned
        return block

    final = predict_result.get("final", {}) or {}
    alt_err = None
    speed_err = None
    if target_altitude_m is not None and "h" in final:
        alt_err = final["h"] - target_altitude_m
    if target_speed_mps is not None and "v" in final:
        speed_err = final["v"] - target_speed_mps

    block = {
        "confidence": predict_result.get("confidence", "low"),
        "horizon_s": horizon_s,
        "terminal_error": {"altitude_m": alt_err, "speed_mps": speed_err},
        "coast_apoapsis_m": coast_apoapsis_m,
        "coast_apoapsis_error_m": coast_apoapsis_error_m,
        "coast_apoapsis_closure_rate_mps": trend["closure_rate_mps"],
        "coast_apoapsis_linear_seconds_to_crossover": trend["linear_seconds_to_crossover"],
        "coast_apoapsis_trend_valid": trend["valid"],
    }
    if action_conditioned is not None:
        block["action_conditioned_apoapsis"] = action_conditioned
    return block


def build_state(cycle_id: int, t: float, phase: str, mission_target: dict,
                 vehicle: dict, feasibility: dict, prediction: dict,
                 physics: Optional[dict] = None,
                 history: Optional[list] = None) -> dict:
    """Assembles the exact sec 5 schema. `vehicle` must already contain
    altitude_m, vertical_speed_mps, horizontal_speed_mps, angle_deg,
    angular_rate_dps, throttle, active_stage, fuel_remaining_pct.

    `physics` (2026-09-13 addition, see build_physics_block()'s
    docstring): optional so existing callers/tests that don't pass it
    keep working -- omitted entirely from the schema when None, rather
    than sent as a confusing null block. Currently unwired from the live
    pipeline (see build_physics_block()'s docstring) -- still accepted
    here so a caller can pass it again once it's reshaped.

    `history` (2026-09-13 LATER SAME DAY addition, Christian's explicit
    request): optional list of recent-cycle summaries (see
    pilot_loop.py's PilotRun.cycle_history for the exact shape) --
    directly targets tsAI's own 66%/27% self-reported explanation
    (repeated_near_identical_state / no_memory_of_trend) for why its
    confidence on throttle_score collapsed over a sustained real flight
    (0.48 -> 0.09 across cycles 15-29, see bookkeeping/active_state.md)
    -- every prior cycle's call was fully stateless, so a genuinely
    ongoing correction and a fresh unrelated situation looked identical.
    Omitted entirely (not sent as an empty list) when None or empty, same
    convention as `physics`."""
    state = {
        "cycle_id": cycle_id,
        "t": t,
        "phase": phase,
        "mission_target": mission_target,
        "vehicle": vehicle,
        "feasibility": feasibility,
        "prediction": prediction,
        "note": NOTE,
    }
    if physics is not None:
        state["physics"] = physics
    if history:
        state["history"] = history
    return state
