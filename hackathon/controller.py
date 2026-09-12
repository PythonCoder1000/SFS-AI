"""Deterministic inner controller -- Checkpoint B (Stage 0) + Checkpoint C
residual/replan-gate wiring.

Zero LLM in the loop still (the supervisor call itself is the next
piece, spec sec 7). This file now also issues rolling predict() calls,
compares them against reality via hackathon/residual.py, and logs what
the replan trigger WOULD do -- so the gate can be watched against a
real flight before an LLM is ever wired to act on its output.

Imports the real observe()/act()/predict() from
analysis/agent_interface.py -- that file is pre-existing hackathon-prep
plumbing (see its own docstring), not something we rebuild here.
"""

import json
import math
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))

import forward_sim as fsim  # noqa: E402  (path set above)
from agent_interface import observe, observe_to_state, act, predict  # noqa: E402
from residual import (  # noqa: E402
    ReplanTrigger, ResidualTrend, compute_residual, classify_cause,
)
from supervisor import build_state_summary, call_supervisor  # noqa: E402
from gateway import GuardrailGateway, DisablementLatch  # noqa: E402

EARTH_RADIUS_M = fsim.PLANET_CONSTANTS["Earth"]["radius_m"]

# Real craft config + AoA table -- captured live from THIS craft
# (2026-09-12, getforwardstartinfo hackathon_idle / hackathon_firing)
# after discovering the earlier borrowed config was a different, much
# lighter craft (28.8t vs this rocket's real 116t) and gave inflated,
# not-very-meaningful residuals. idle snapshot supplies mass/engine/
# geometry; firing snapshot supplies the load-bearing torque values
# (torqueEffectiveRaw jumps 5 -> 12.2 idle->firing on this craft).
CFG = fsim.load_craft_config_from_getforwardstartinfo(
    str(ROOT / "analysis/sfs_probe_forwardstartinfo_hackathon_idle.json"),
    firing_snapshot_path=str(ROOT / "analysis/sfs_probe_forwardstartinfo_hackathon_firing.json"))
CFG["dry_mass_t"] = 8.0  # not in the dump; keeps fuel finite, matches offline harness
AOA = json.load(open(ROOT / "analysis/aoa_dragarea_table_hackathon.json"))

PREDICT_HORIZON_S = 5.0  # how far ahead each rolling prediction looks

# --- staging state machine -------------------------------------------------
# Known safety-critical finding (see hackathon spec sec 1): firing all
# engines at once destroys the rocket. Stages must be armed one at a
# time, in order, via `stage <index>` -- never a blanket `ignite`.
#
# 2026-09-12 CONFIRMED, live-tested: `stage <index>` is NOT idempotent.
# Repeated calls with the same index TOGGLE engineOn every single call
# (True/False/True/False..., 100% reproducible over 7 calls). No parts
# lost/separated (part count and mass stayed constant) -- unlike
# `ignite`, this doesn't destroy anything -- but a duplicate or retried
# `stage` call reaching the game mid-flight can silently kill already-
# firing engines while the caller's own state still believes they're
# armed. force_stage() below is safe BECAUSE it only ever increments
# expected_stage and never re-sends the same index twice -- do not call
# it more than once per stage, and do not build any retry/resend logic
# around `stage` without accounting for this. See sfsprobe/mod_changelog.md
# for the full writeup.
_stage_state = {"expected_stage": 0}

# TODO(Checkpoint B, open item): the trigger condition for "this stage
# is spent, advance" still needs to be confirmed against live telemetry
# (fuel/thrOn semantics) before this is more than a manual/placeholder
# hook. The idempotency question above is now answered (it's NOT
# idempotent) -- what's still open is knowing WHEN to call force_stage()
# automatically, not whether repeat calls are safe (they aren't).
def maybe_stage(snapshot: dict) -> None:
    """Placeholder hook -- currently a no-op. Call manually via
    force_stage() during testing until the real trigger is confirmed."""
    pass


def force_stage() -> str:
    """Advance to the next expected stage. Only ever `expected_stage`,
    never a blanket ignite -- matches the gateway's staging FSM design
    (hackathon plan sec 9), even though the full gateway isn't built
    yet at this checkpoint."""
    idx = _stage_state["expected_stage"]
    result = act(f"stage {idx}")
    _stage_state["expected_stage"] += 1
    return result


# --- altitude PD controller -------------------------------------------------

class AltitudePD:
    """PD controller on altitude error, damped by vertical speed.
    Straight-up ascent only: no turn axis input, rot/turn left at 0.

    2026-09-12 live-test finding: raw tick-to-tick vspeed noise (a
    few m/s) was getting amplified by kd into near-full-range throttle
    swings (0.84 -> 1.00 -> 0.01 across 3 ticks, from only a 3.4 m/s
    vspeed change) -- classic chattering, called out as the most likely
    visible demo failure in the hackathon plan itself. Fixed with an
    exponential moving average on vspeed (smooths the noise kd reacts
    to) plus a deadband on the final throttle (holds the last commanded
    value if the new computed value hasn't moved far enough to matter).
    """

    def __init__(
        self,
        target_altitude_m: float,
        kp: float = 0.002,
        kd: float = 0.1,
        deadband: float = 0.05,
        vspeed_smoothing: float = 0.3,
    ):
        """kp/kd retuned 2026-09-12 via hackathon/offline_pd_test.py's grid
        sweep against forward_sim.py -- the earlier kd/kp=250 (chosen to
        fix overshoot) turned out to overcorrect: it plateaued around
        14-18km and never reached 20km target in 300-600s. Sweeping
        kp x kd/kp ratio found kd/kp=50 reliably reaches the tolerance
        band (~235-255s, landing within ~150m of target, low smooth
        final throttle). This kp/kd pair was the sweep's best balance of
        speed and precision -- see offline_pd_test.py for the full grid.
        """
        self.target_altitude_m = target_altitude_m
        self.kp = kp
        self.kd = kd
        self.deadband = deadband
        self.vspeed_smoothing = vspeed_smoothing  # EMA alpha, 0-1: lower = smoother/laggier
        self._smoothed_vspeed = None
        self._last_throttle = 0.0

    def throttle_for(self, altitude_m: float, vertical_speed_mps: float) -> float:
        if self._smoothed_vspeed is None:
            self._smoothed_vspeed = vertical_speed_mps
        else:
            a = self.vspeed_smoothing
            self._smoothed_vspeed = a * vertical_speed_mps + (1 - a) * self._smoothed_vspeed

        alt_error = self.target_altitude_m - altitude_m
        raw = self.kp * alt_error - self.kd * self._smoothed_vspeed
        clamped = max(0.0, min(1.0, raw))

        if abs(clamped - self._last_throttle) < self.deadband:
            return self._last_throttle  # hold -- change too small to bother

        self._last_throttle = clamped
        return clamped


def _altitude_and_vspeed(snapshot: dict) -> tuple[float, float]:
    """Derive altitude (m above surface) and vertical speed (m/s,
    radially outward) from a raw observe() snapshot -- same
    px/py/vx/vy shape observe_to_state() already normalizes."""
    state = observe_to_state(snapshot)
    px, py, vx, vy = state["px"], state["py"], state["vx"], state["vy"]
    r = math.hypot(px, py)
    altitude_m = r - EARTH_RADIUS_M
    # radial (outward) component of velocity = altitude rate of change
    vertical_speed_mps = (px * vx + py * vy) / r if r else 0.0
    return altitude_m, vertical_speed_mps


# --- Stage 0 run loop --------------------------------------------------------

def run_ascent(
    target_altitude_m: float,
    tolerance_m: float = 250.0,
    poll_hz: float = 5.0,
    max_duration_s: float = 300.0,
    induce_fault_at_t: float = None,
    induce_fault_duration_s: float = 3.0,
    induce_fault_throttle: float = 0.0,
) -> dict:
    """Fly straight up to target_altitude_m. Returns the last observed
    snapshot. Checkpoint C: when the replan gate fires, this now
    actually calls the LLM supervisor and applies its correction --
    previously it only logged what the gate would have done.

    induce_fault_at_t: if set, forces throttle to induce_fault_throttle
    (default 0.0, a hard cutout) for induce_fault_duration_s seconds
    starting at that many seconds into the flight -- simulates an
    actuator fault so the residual/gate/supervisor loop has something
    real to react to, for Checkpoint C's own exit test (spec sec 11:
    "On an induced perturbation, residual crosses tolerance, LLM fires,
    correction visibly shrinks the residual"). The fault overrides
    EVERYTHING during its window (PD and any LLM correction alike) --
    it's meant to model a real actuator that briefly can't respond, not
    something the loop is expected to fight in real time. Nothing
    special is needed for the recovery: by the time the prediction
    issued before/during the fault actually resolves (PREDICT_HORIZON_S
    later), the fault window has already closed on its own, so the
    supervisor's correction naturally applies to the AFTERMATH, not a
    fight against the fault itself.

    IMPORTANT, still true: there is NO guardrail gateway yet
    (Checkpoint D -- schema/staging-FSM/clamp/mandatory-predict-sanity-
    check). A Correction's target_throttle goes straight to act(),
    protected only by agent_interface.act()'s existing rate clamp
    (MAX_THROTTLE_STEP=0.3/call) -- nothing here vets whether the LLM's
    suggestion is actually a good idea. That's a deliberate, known gap
    at this checkpoint, not an oversight -- don't leave this running
    unsupervised.

    2026-09-12 live-test finding: `throttle <amount>` only sets
    throttlePercent -- it does NOT arm the rocket-wide master ignition
    switch (throttleOn). Without `master on`, engines report engineOn
    and accept throttle commands but produce zero real thrust
    (throttleOut stayed 0 through several throttle calls in testing).
    `master on` is idempotent and rocket-wide (independent of per-
    engine state and of staging), so it's safe to send unconditionally
    at the start of every run, not just once ever.
    """
    act("master on")

    controller = AltitudePD(target_altitude_m)
    dt = 1.0 / poll_hz
    t_start = time.monotonic()
    deadline = t_start + max_duration_s

    # Checkpoint C: rolling predict() -> compare -> classify -> gate -> LLM.
    # Checkpoint D: every non-no_change Correction is vetted by the
    # guardrail gateway before it can touch act() -- retry once with
    # the rejection cause fed back, then deterministic safe-hold.
    trigger = ReplanTrigger()
    trigger.reset_phase("ASCENT")
    trend = ResidualTrend()
    gateway = GuardrailGateway()
    latch = DisablementLatch()
    pending_prediction = None  # {"due_t", "predicted_final", "confidence"}
    throttle_history = deque(maxlen=5)  # for actuator-saturation detection
    cycle_id = 0
    last_gate_fire_t = 0.0
    recent_decisions = []  # cut to last 1 entry per state-summary schema's own cut order
    override_throttle = None  # LLM correction currently being held, if any
    override_until_t = 0.0

    last_snapshot = None
    try:
        while time.monotonic() < deadline:
            snapshot = observe()
            last_snapshot = snapshot
            altitude_m, vspeed = _altitude_and_vspeed(snapshot)
            t_now = time.monotonic() - t_start
            state_now = observe_to_state(snapshot)
            cycle_id += 1

            maybe_stage(snapshot)  # no-op placeholder, see TODO above

            actuator_saturated = (
                len(throttle_history) == throttle_history.maxlen
                and (all(t <= 0.0 for t in throttle_history)
                     or all(t >= 1.0 for t in throttle_history))
            )

            # Consume a due prediction: compare it against reality, classify,
            # check the gate, and call the LLM supervisor if it fires.
            if pending_prediction is not None and t_now >= pending_prediction["due_t"]:
                res = compute_residual(pending_prediction["predicted_final"], state_now)
                confidence = pending_prediction["confidence"]
                trend_info = trend.update(t_now, res["position_error_m"])
                cause = classify_cause(
                    res["position_error_m"], res["speed_error_mps"],
                    confidence, actuator_saturated, just_staged=False,
                )
                decision = trigger.update(res["position_error_m"], t_now, confidence)
                marker = "  <-- REPLAN" if decision.should_replan else ""
                print(f"  [residual] pos_err={res['position_error_m']:6.1f}m "
                      f"spd_err={res['speed_error_mps']:5.1f}m/s "
                      f"trend={trend_info['trend']:<8} conf={confidence:<5} "
                      f"cause={cause:<20} gate={decision.reason}{marker}")

                if decision.should_replan:
                    time_since_last_replan_s = t_now - last_gate_fire_t  # BEFORE updating it below
                    last_gate_fire_t = t_now
                    pred_alt = math.hypot(pending_prediction["predicted_final"]["px"],
                                           pending_prediction["predicted_final"]["py"]) - EARTH_RADIUS_M
                    summary = build_state_summary(
                        cycle_id=cycle_id, phase="ASCENT",
                        altitude_m=altitude_m, vertical_speed_mps=vspeed,
                        throttle=(override_throttle if override_throttle is not None
                                  else throttle_history[-1] if throttle_history else 0.0),
                        active_stage=_stage_state["expected_stage"],
                        target_altitude_m=target_altitude_m, plan_issued_at_cycle=0,
                        prediction_confidence=confidence, prediction_horizon_s=PREDICT_HORIZON_S,
                        predicted_terminal_altitude_error_m=target_altitude_m - pred_alt,
                        predicted_terminal_speed_error_mps=res["speed_error_mps"],
                        position_error_m=res["position_error_m"], speed_error_mps=res["speed_error_mps"],
                        residual_trend=trend_info["trend"], residual_slope=trend_info["residual_slope"],
                        triggered_replan=True, causal_category=cause,
                        time_in_phase_s=t_now, time_since_last_replan_s=time_since_last_replan_s,
                        actuator_saturated=actuator_saturated, recent_decisions=recent_decisions,
                    )

                    if latch.disabled:
                        print("  [gateway] LLM authority DISABLED for this phase "
                              "(sustained rejections) -- skipping supervisor call")
                        correction = None
                    else:
                        correction = call_supervisor(summary, decision.reason)
                        if correction is not None and not correction.no_change:
                            gdecision = gateway.evaluate(
                                correction, expected_stage=_stage_state["expected_stage"], now_s=t_now,
                                current_state=state_now, craft_config=CFG, aoa_table=AOA, predict_fn=predict,
                            )
                            if not gdecision.accepted:
                                print(f"  [gateway] REJECTED ({gdecision.cause.value}): {gdecision.detail} "
                                      f"-- retrying once with cause fed back")
                                latch.record_rejection(gdecision.cause, "ASCENT", altitude_m)
                                retry_reason = (
                                    f"{decision.reason}; PREVIOUS PROPOSAL REJECTED by the guardrail gateway: "
                                    f"{gdecision.cause.value} ({gdecision.detail}). Propose something "
                                    f"different, or keep the current plan."
                                )
                                correction2 = call_supervisor(summary, retry_reason)
                                if correction2 is not None and not correction2.no_change:
                                    gdecision2 = gateway.evaluate(
                                        correction2, expected_stage=_stage_state["expected_stage"], now_s=t_now,
                                        current_state=state_now, craft_config=CFG, aoa_table=AOA, predict_fn=predict,
                                    )
                                    if gdecision2.accepted:
                                        correction = correction2
                                    else:
                                        print(f"  [gateway] retry REJECTED again ({gdecision2.cause.value}) "
                                              f"-- deterministic safe-hold this cycle")
                                        latch.record_rejection(gdecision2.cause, "ASCENT", altitude_m)
                                        correction = None  # safe-hold: PD keeps flying, no LLM throttle applied
                                else:
                                    correction = correction2  # None or no_change both skip the gateway cleanly
                            elif correction.stage_request is not None:
                                force_stage()  # gateway-accepted staging action -- only ever expected_stage

                    if correction is None:
                        print("  [supervisor] no correction (no credentials, timeout, rejected twice, "
                              "or malformed response) -- deterministic layer continues unchanged")
                    elif correction.no_change:
                        print(f"  [supervisor] keep current plan ({correction.reason_code}, "
                              f"{correction.latency_ms:.0f}ms)")
                    else:
                        commit_s = (correction.commit_ms / 1000.0) if correction.commit_ms else 1.0
                        override_throttle = correction.target_throttle
                        override_until_t = t_now + commit_s
                        print(f"  [supervisor] CORRECTION: throttle -> {correction.target_throttle:.2f} "
                              f"({correction.reason_code}, hold {commit_s:.1f}s, "
                              f"{correction.latency_ms:.0f}ms)")
                    if correction is not None:
                        recent_decisions = [correction.to_dict()]

                    # Arbitration: this tick's residual is the freshest stability signal --
                    # feed it to the latch regardless of what the supervisor/gateway did.
                    residual_within_tolerance = res["position_error_m"] < trigger.clear_threshold_m
                    latch.record_stable_tick("ASCENT", residual_within_tolerance)

                pending_prediction = None

            if abs(target_altitude_m - altitude_m) <= tolerance_m:
                break

            if induce_fault_at_t is not None and induce_fault_at_t <= t_now < induce_fault_at_t + induce_fault_duration_s:
                throttle = induce_fault_throttle
                print(f"  [FAULT INJECTED] forcing throttle={throttle:.2f}  (t={t_now:.1f}s)")
            elif override_throttle is not None and t_now < override_until_t:
                throttle = override_throttle  # LLM correction still in its commit window
            else:
                override_throttle = None
                throttle = controller.throttle_for(altitude_m, vspeed)
            # Bumpless handoff (spec sec 9): keep the deterministic controller's
            # own internal state honest about what's ACTUALLY being commanded,
            # even on ticks where the fault injector or an LLM correction is the
            # one deciding. Without this, the PD's _last_throttle/deadband logic
            # would resume from a stale value and jump the moment it regains
            # authority, instead of continuing smoothly from reality.
            controller._last_throttle = throttle
            act(f"throttle {throttle}")
            throttle_history.append(throttle)
            print(f"alt={altitude_m:8.1f}m  vspeed={vspeed:7.1f}m/s  throttle={throttle:.2f}")

            # Issue the next rolling prediction: "if I hold this throttle for
            # PREDICT_HORIZON_S seconds with no further input, where do I end
            # up?" -- a hypothetical, not a real replay of the actual plan.
            if pending_prediction is None:
                result = predict(
                    state_now, waypoints=[], duration_s=PREDICT_HORIZON_S,
                    craft_config=CFG, aoa_table=AOA, default_throttle=throttle,
                )
                pending_prediction = {
                    "due_t": t_now + PREDICT_HORIZON_S,
                    "predicted_final": result["final"],
                    "confidence": result["confidence"],
                }

            time.sleep(dt)
    finally:
        # Always cut throttle on the way out -- tolerance reached, timeout
        # hit, or an exception/KeyboardInterrupt -- never leave the last
        # commanded throttle running unattended. Matches the plan's own
        # "never an indefinite freeze" rule (sec 7.1), applied here even
        # though the full expiry contract isn't built until Checkpoint D.
        act("throttle 0")

    return last_snapshot


if __name__ == "__main__":
    # Manual smoke test -- requires the game running with a rocket
    # loaded in the scene. Adjust target as needed.
    final_snapshot = run_ascent(target_altitude_m=20000.0)
    print("final snapshot:", final_snapshot)
