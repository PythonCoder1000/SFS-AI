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
import os
import sys
import time
from collections import deque
from pathlib import Path

import weave
from dotenv import load_dotenv

load_dotenv()  # picks up .env in the repo root (or CWD) if present -- see .env.example

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))

import forward_sim as fsim  # noqa: E402  (path set above)
from agent_interface import observe, observe_to_state, act, predict  # noqa: E402
from residual import (  # noqa: E402
    ReplanTrigger, ResidualTrend, compute_residual, classify_cause,
)
from supervisor import build_state_summary, call_supervisor, Correction  # noqa: E402
from gateway import GuardrailGateway, DisablementLatch  # noqa: E402

# Eligibility requirement (spec sec 0) -- get this in on day one so a time
# crunch can never make the project ineligible. 2026-09-12 finding: calling
# weave.init() with no WANDB_API_KEY configured does NOT fail cleanly -- it
# blocks waiting on an interactive `wandb login` prompt for a key paste,
# which hangs forever in any non-interactive context (this exact script,
# any script that imports it, a live flight run). Guarded the same way as
# the Anthropic/AWS credentials in supervisor.py: skip cleanly with a clear
# message if the key isn't there yet, rather than silently hanging.
if os.environ.get("WANDB_API_KEY"):
    weave.init("sfs-ai-hackathon")
else:
    print("[weave] WANDB_API_KEY not set -- skipping weave.init(), "
          "@weave.op() calls will no-op (no tracing, but nothing hangs or breaks). "
          "Add WANDB_API_KEY to .env to enable real Weave logging.")

EARTH_RADIUS_M = fsim.PLANET_CONSTANTS["Earth"]["radius_m"]


# --- Weave-traced wrappers around agent_interface.py's observe/act/predict -
# Spec sec 10: "@weave.op() on: observe, predict, ... act()." agent_interface.py
# is pre-existing plumbing (see its own docstring) that this project
# deliberately doesn't modify -- these thin wrappers add tracing at the call
# site instead of touching that file. NOT applied to anything inside the
# fast-loop's own internal ticks (the while loop body itself, print
# statements, etc.) -- only these three named boundary calls, matching the
# spec's "not on the fast-loop's internal ticks" instruction.
@weave.op()
def traced_observe():
    return observe()


@weave.op()
def traced_act(command: str):
    return act(command)


@weave.op()
def traced_predict(state, **kwargs):
    return predict(state, **kwargs)


def _call_with_retry(fn, *args, max_attempts: int = 3, retry_delay_s: float = 0.5,
                      label: str = "mod call", **kwargs):
    """2026-09-12 live finding: sfsprobe itself can go unresponsive for a
    few seconds -- not a supervisor/API issue, the mod's own file-
    protocol I/O -- which previously crashed run_ascent() entirely via
    an uncaught TimeoutError from observe()/act() (see
    bookkeeping/active_state.md's incident note). That's a real infra
    hiccup, not a reason to abandon the flight -- retry it a bounded
    number of times before giving up. Bounded on purpose: a genuinely
    dead mod should still surface as a real failure (and the caller's
    own finally-block throttle-cut still runs), not hang forever."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except TimeoutError as e:
            last_exc = e
            print(f"  [WARN] {label} timed out (attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                time.sleep(retry_delay_s)
    raise last_exc


@weave.op()
def log_cycle_decision(
    cycle_id: int, replan_trigger_reason: str, llm_latency_ms: float,
    proposed_action: dict, accepted_action: dict, rejection_cause,
    fallback_used: bool,
) -> dict:
    """One traced call per replan cycle bundling exactly the fields spec
    sec 10 asks for beyond the raw op traces -- proposed vs accepted
    action side by side is what makes a Weave decision-markers panel
    possible without cross-referencing multiple separate traces."""
    return {
        "cycle_id": cycle_id, "replan_trigger_reason": replan_trigger_reason,
        "llm_latency_ms": llm_latency_ms, "proposed_action": proposed_action,
        "accepted_action": accepted_action, "rejection_cause": rejection_cause,
        "fallback_used": fallback_used,
    }


@weave.op()
def log_correction_effectiveness(
    cycle_id: int, error_before_replan: float, error_after_replan: float,
    correction_effectiveness: float, correction_harm_rate: float,
) -> dict:
    """Headline metric (spec sec 10): correction_effectiveness =
    error_before_replan - error_after_replan, reported ALONGSIDE
    correction_harm_rate (how often a replan makes it worse), never
    just the effectiveness number alone -- a system that helps 90% of
    the time but catastrophically hurts the other 10% looks great on
    effectiveness alone and isn't."""
    return {
        "cycle_id": cycle_id, "error_before_replan": error_before_replan,
        "error_after_replan": error_after_replan,
        "correction_effectiveness": correction_effectiveness,
        "correction_harm_rate": correction_harm_rate,
    }

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
    result = _call_with_retry(traced_act, f"stage {idx}", label=f"act('stage {idx}')")
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
    inject_bad_stage_request_at_t: float = None,
    inject_bad_stage_request_at_ts: list = None,
    force_supervisor_timeout_at_t: float = None,
    simulate_midcall_stage_transition_at_t: float = None,
) -> dict:
    """Fly straight up to target_altitude_m. Returns the last observed
    snapshot. Checkpoint C: when the replan gate fires, this now
    actually calls the LLM supervisor and applies its correction --
    previously it only logged what the gate would have done.

    inject_bad_stage_request_at_t: Checkpoint D live exit test. At the
    first replan cycle at or after this many seconds into the flight, a
    DELIBERATELY ILLEGAL Correction is substituted for the real first
    supervisor call -- stage_request set to expected_stage+1 (guaranteed
    mismatch, per the staging FSM). Everything downstream is completely
    real: the gateway evaluates it for real, the retry-with-cause-fed-
    back call goes to the REAL LLM, and the disablement latch records
    the rejection for real. Only the first attempt is fabricated -- a
    well-behaved LLM proposing sensible throttle corrections during a
    normal ascent is very unlikely to spontaneously trigger a rejection
    on its own, so this is how we get a real, repeatable, on-camera
    "illegal command rejected, safe fallback engaged" moment instead of
    just trusting the offline gateway_corpus_test.py coverage.

    inject_bad_stage_request_at_ts: same mechanism, but a LIST of
    injection times instead of one -- the other half of Checkpoint D's
    live exit test: "a bad-but-not-illegal LLM streak does not
    incorrectly trip the disablement latch once state has moved on."
    Spaced widely apart in real flight time, each injection lands at a
    meaningfully different altitude, so DisablementLatch's own
    materially-similar-state check (same cause + phase + altitude within
    similarity_band_m, default 500m) should treat them as unrelated
    rejections rather than an accumulating streak -- proving the latch
    discriminates a real bad streak from a few unlucky, unrelated
    rejections scattered across a flight. Takes priority over the
    single-time parameter if both are given.

    force_supervisor_timeout_at_t: Checkpoint E fault-injection gate,
    category 1/4 ("forced API timeout ... must reach safe-hold without
    manual repair"). At the first replan cycle at or after this many
    seconds, the supervisor call is made with an impossibly short
    timeout_s (1ms) -- a REAL timeout against the REAL API, not a
    simulated stand-in for one. call_supervisor()'s own try/except
    catches it and returns None exactly like any other failure, so this
    exercises the actual code path a real network hiccup would hit, not
    a mock of it.

    simulate_midcall_stage_transition_at_t: Checkpoint E fault-injection
    gate, category 2 ("mid-call stage transition"). At the first replan
    cycle at or after this many seconds, right after the supervisor call
    returns but BEFORE the gateway evaluates it, _stage_state's
    expected_stage is bumped by 1 -- simulating some other process (or a
    real staging event) changing the world out from under this cycle
    while the LLM call was in flight. Proves the gateway reads
    expected_stage LIVE at evaluation time, not a value memoized when
    the state summary was built seconds earlier -- if a correction's
    stage_request happens to reference the now-STALE expected_stage, it
    must be rejected as a mismatch, not honored because "it was valid
    when the LLM was asked."

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

    2026-09-12 live-test finding: `throttle <amount>` only sets
    throttlePercent -- it does NOT arm the rocket-wide master ignition
    switch (throttleOn). Without `master on`, engines report engineOn
    and accept throttle commands but produce zero real thrust
    (throttleOut stayed 0 through several throttle calls in testing).
    `master on` is idempotent and rocket-wide (independent of per-
    engine state and of staging), so it's safe to send unconditionally
    at the start of every run, not just once ever.
    """
    _call_with_retry(traced_act, "master on", label="act('master on')")

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
    # Weave sec 10 headline metric tracking: measured one cycle after a
    # correction is actually applied, against THAT cycle's fresh residual.
    pending_effectiveness = None  # {"error_before", "fired_at_t"}
    total_corrections = 0
    harm_count = 0
    bad_stage_injected = False  # Checkpoint D live test: single-time hook fires at most once
    pending_injection_ts = sorted(inject_bad_stage_request_at_ts) if inject_bad_stage_request_at_ts else []
    timeout_forced = False  # Checkpoint E live test: fires at most once
    stage_transition_simulated = False  # Checkpoint E live test: fires at most once

    last_snapshot = None
    try:
        while time.monotonic() < deadline:
            snapshot = _call_with_retry(traced_observe, label="observe()")
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

                # Weave sec 10 headline metric: did the LAST correction we
                # applied actually help? Measured against THIS cycle's fresh
                # residual, one cycle after it fired.
                if pending_effectiveness is not None:
                    error_before = pending_effectiveness["error_before"]
                    error_after = res["position_error_m"]
                    effectiveness = error_before - error_after
                    total_corrections += 1
                    if effectiveness < 0:
                        harm_count += 1
                    harm_rate = harm_count / total_corrections
                    print(f"  [effectiveness] error_before={error_before:.1f}m "
                          f"error_after={error_after:.1f}m effectiveness={effectiveness:+.1f}m "
                          f"harm_rate={harm_rate:.2f} ({harm_count}/{total_corrections})")
                    log_correction_effectiveness(cycle_id, error_before, error_after,
                                                  effectiveness, harm_rate)
                    pending_effectiveness = None

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
                        proposed_action_dict = None
                        rejection_cause_value = None
                        llm_latency_total_ms = 0.0
                    else:
                        proposed_action_dict = None
                        rejection_cause_value = None
                        llm_latency_total_ms = 0.0
                        if (inject_bad_stage_request_at_ts is not None and pending_injection_ts
                                and t_now >= pending_injection_ts[0]):
                            pending_injection_ts.pop(0)
                            bad_stage = _stage_state["expected_stage"] + 1
                            correction = Correction(
                                no_change=False, reason_code="TEST_INJECTED_bad_stage_request",
                                target_throttle=(throttle_history[-1] if throttle_history else 0.5),
                                stage_request=bad_stage, commit_ms=1000, latency_ms=0.0,
                            )
                            print(f"  [TEST] injecting deliberately illegal correction "
                                  f"(streak test, alt={altitude_m:.0f}m): stage_request={bad_stage} "
                                  f"(expected_stage={_stage_state['expected_stage']}) -- should be "
                                  f"REJECTED by gateway, and NOT accumulate with unrelated rejections")
                        elif (inject_bad_stage_request_at_t is not None and not bad_stage_injected
                                and t_now >= inject_bad_stage_request_at_t):
                            bad_stage_injected = True
                            bad_stage = _stage_state["expected_stage"] + 1
                            correction = Correction(
                                no_change=False, reason_code="TEST_INJECTED_bad_stage_request",
                                target_throttle=(throttle_history[-1] if throttle_history else 0.5),
                                stage_request=bad_stage, commit_ms=1000, latency_ms=0.0,
                            )
                            print(f"  [TEST] injecting deliberately illegal correction: "
                                  f"stage_request={bad_stage} (expected_stage="
                                  f"{_stage_state['expected_stage']}) -- should be REJECTED by gateway")
                        else:
                            if (force_supervisor_timeout_at_t is not None and not timeout_forced
                                    and t_now >= force_supervisor_timeout_at_t):
                                timeout_forced = True
                                print(f"  [TEST] forcing a REAL supervisor timeout (timeout_s=0.001) "
                                      f"-- should fail safely to deterministic layer, no hang/crash")
                                correction = call_supervisor(summary, decision.reason, timeout_s=0.001)
                            else:
                                correction = call_supervisor(summary, decision.reason)

                        if (simulate_midcall_stage_transition_at_t is not None and not stage_transition_simulated
                                and t_now >= simulate_midcall_stage_transition_at_t):
                            stage_transition_simulated = True
                            old_expected = _stage_state["expected_stage"]
                            _stage_state["expected_stage"] += 1
                            print(f"  [TEST] simulating a mid-call stage transition: expected_stage "
                                  f"{old_expected} -> {_stage_state['expected_stage']} (right after the "
                                  f"supervisor call returned, before the gateway evaluates it)")

                        if correction is not None:
                            proposed_action_dict = correction.to_dict()
                            llm_latency_total_ms += correction.latency_ms
                        if correction is not None and not correction.no_change:
                            gdecision = gateway.evaluate(
                                correction, expected_stage=_stage_state["expected_stage"], now_s=t_now,
                                current_state=state_now, craft_config=CFG, aoa_table=AOA, predict_fn=predict,
                            )
                            if not gdecision.accepted:
                                print(f"  [gateway] REJECTED ({gdecision.cause.value}): {gdecision.detail} "
                                      f"-- retrying once with cause fed back")
                                rejection_cause_value = gdecision.cause.value
                                latch.record_rejection(gdecision.cause, "ASCENT", altitude_m)
                                print(f"  [latch] disabled={latch.disabled} (should stay False for "
                                      f"unrelated/well-separated rejections)")
                                retry_reason = (
                                    f"{decision.reason}; PREVIOUS PROPOSAL REJECTED by the guardrail gateway: "
                                    f"{gdecision.cause.value} ({gdecision.detail}). Propose something "
                                    f"different, or keep the current plan."
                                )
                                correction2 = call_supervisor(summary, retry_reason)
                                if correction2 is not None:
                                    llm_latency_total_ms += correction2.latency_ms
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
                                        rejection_cause_value = gdecision2.cause.value
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
                        pending_effectiveness = {"error_before": res["position_error_m"], "fired_at_t": t_now}
                        print(f"  [supervisor] CORRECTION: throttle -> {correction.target_throttle:.2f} "
                              f"({correction.reason_code}, hold {commit_s:.1f}s, "
                              f"{correction.latency_ms:.0f}ms)")
                    if correction is not None:
                        recent_decisions = [correction.to_dict()]

                    log_cycle_decision(
                        cycle_id=cycle_id, replan_trigger_reason=decision.reason,
                        llm_latency_ms=llm_latency_total_ms, proposed_action=proposed_action_dict,
                        accepted_action=(correction.to_dict() if correction is not None else None),
                        rejection_cause=rejection_cause_value,
                        fallback_used=(correction is None),
                    )

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
            _call_with_retry(traced_act, f"throttle {throttle}", label=f"act('throttle {throttle}')")
            throttle_history.append(throttle)
            print(f"alt={altitude_m:8.1f}m  vspeed={vspeed:7.1f}m/s  throttle={throttle:.2f}")

            # Issue the next rolling prediction: "if I hold this throttle for
            # PREDICT_HORIZON_S seconds with no further input, where do I end
            # up?" -- a hypothetical, not a real replay of the actual plan.
            if pending_prediction is None:
                result = traced_predict(
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
        # "never an indefinite freeze" rule (sec 7.1). Retried too (same
        # 2026-09-12 mod-unresponsive finding) -- but this is the LAST
        # line of defense, so failure here must never crash silently or
        # mask whatever exception got us into finally in the first
        # place: catch broadly, warn loudly, never re-raise.
        try:
            _call_with_retry(act, "throttle 0", label="final throttle-cut act('throttle 0')")
        except Exception as e:  # noqa: BLE001 -- deliberately broad: this is the safety net,
            # nothing here should ever propagate and hide the real error.
            print(f"  [CRITICAL] failed to cut throttle after retries: {e} -- "
                  f"MANUAL INTERVENTION MAY BE NEEDED, check the game directly")

    return last_snapshot


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def _vertical_theta_deg(px: float, py: float) -> float:
    """Craft rotation (rb2d.rotation convention) that points 'straight
    up' (radially away from the planet) at this position. Confirmed
    empirically 2026-09-12: a stationary craft on the pad read
    theta=-0.04 deg against this formula's own -0.07 deg prediction at
    that same position -- 0.03 deg off, i.e. no real calibration offset
    needed. Derived from forward_sim.py's own confirmed AoA convention
    (aoa = wrap180((theta+90) - heading_deg)): a craft with zero AoA
    flying straight up has heading == atan2(py,px) (straight out from
    the planet), so theta == heading - 90."""
    return math.degrees(math.atan2(py, px)) - 90.0


class AttitudePD:
    """PD controller on rotation error -> turn_axis command. Separate
    from AltitudePD (throttle) -- this is the piece run_ascent() never
    needed, since it always held rot/turn_axis at 0 (straight-up only).
    A gravity turn needs BOTH loops running simultaneously: throttle
    still drives when we get there, attitude now drives WHERE we point.

    Deliberately conservative gains: agent_interface.py's act() clamps
    any 'turn <v>' command to +-0.5 no matter what this computes (see
    MAX_TURN_AXIS_MAGNITUDE, added after two real crashes from turn=1
    full authority at low altitude/speed) -- this controller is tuned
    to rarely need that clamp, not to lean on it. kd damps on the
    craft's own angular velocity (omega, deg/s) to avoid overshoot/
    oscillation chasing a moving pitch-program target, the same
    chattering risk AltitudePD's own kd/vspeed-smoothing was built to
    avoid on the throttle side.
    """

    def __init__(self, kp: float = 0.012, kd: float = 0.06):
        self.kp = kp
        self.kd = kd

    def turn_axis_for(self, current_theta_deg: float, desired_theta_deg: float,
                       omega_degs: float) -> float:
        """SIGN FIX (2026-09-12, post-incident): confirmed via
        forward_sim.py's apply_rotation_update -- the actual physics is
        `omega -= torque_effective * turn_axis * RAD2DEG/mass * dt`
        with torque_effective POSITIVE, so a POSITIVE turn_axis
        DECREASES omega and a NEGATIVE turn_axis INCREASES it (SAS's
        own compute_turn_axis, turn_axis=omega/delta with delta>0,
        commands turn_axis with the SAME sign as omega specifically
        because that's what cancels it under this formula). The
        original version here had raw = kp*error - kd*omega -- backwards
        on BOTH terms: to increase theta (positive error) you need to
        BUILD positive omega, which requires a NEGATIVE turn_axis, not
        positive; and to damp an existing positive omega back to zero
        you need a POSITIVE turn_axis (matching SAS's own law), not
        negative. That inversion is exactly what pegged turn at the
        -0.5 clamp for 40+ consecutive ticks on the first live attempt
        while theta raced through 2000+ degrees and altitude started
        dropping -- a real positive-feedback runaway, caught and killed
        via SIGINT before any damage, not a close call worth repeating.
        """
        error = _wrap180(desired_theta_deg - current_theta_deg)
        raw = -self.kp * error + self.kd * omega_degs
        return max(-0.5, min(0.5, raw))


# Hard safety ceiling for run_gravity_turn_to_orbit's attitude loop --
# independent of AttitudePD's own gains being right. If |omega| ever
# exceeds this, something is badly wrong (a real gravity-turn pitch
# program never needs anywhere near this much angular rate) and the
# run aborts immediately -- zero turn, zero throttle -- rather than
# trusting the controller to self-correct. Direct response to the
# 2026-09-12 sign-bug incident: a watchdog independent of the
# controller's own correctness is the actual fix for "a bug like that
# should never be able to run away again", not just fixing this one bug.
SPIN_ABORT_THRESHOLD_DEGS = 45.0


def _pitch_program_deg(altitude_m: float, pitch_start_alt_m: float,
                        pitch_end_alt_m: float, max_pitch_deg: float) -> float:
    """How far off local-vertical to pitch, as a function of altitude --
    a classic gravity-turn profile: stay vertical until pitch_start_alt_m
    (let speed build in the thickest air first, avoid turning at low
    speed/high density where torque authority is weakest and risk is
    highest -- directly the regime the two real turn-related crashes
    this project already logged happened in), then ramp linearly to
    max_pitch_deg by pitch_end_alt_m, then hold there. Linear, not eased
    -- simplest profile that's still a real gravity turn; an S-curve or
    similar refinement is a natural next iteration once this baseline
    is confirmed to fly at all."""
    if altitude_m <= pitch_start_alt_m:
        return 0.0
    if altitude_m >= pitch_end_alt_m:
        return max_pitch_deg
    frac = (altitude_m - pitch_start_alt_m) / (pitch_end_alt_m - pitch_start_alt_m)
    return max_pitch_deg * frac


def _orbital_apoapsis_periapsis_alt(px: float, py: float, vx: float, vy: float,
                                     mu: float, body_radius_m: float) -> tuple:
    """Apoapsis/periapsis ALTITUDE (above body_radius_m), computed from
    the current state via standard two-body orbital mechanics (vis-viva
    energy + specific angular momentum) -- NOT via the game's own
    predApo/predPeri telemetry fields. Confirmed live 2026-09-12 via
    sfsprobe's field registry (light_search): those fields are
    namespace='truth', requestAs='telemetry on (full mode, no field
    list) -- truth.jsonl' -- i.e. ONLY populated by the continuous
    full-mode RECORDING pipeline, not retrievable via the per-tick
    telemetrysnapshot query this fast control loop uses for everything
    else. Confirmed the hard way first: predApo/predPeri came back None
    on every single telemetrysnapshot call across an entire real flight
    (63m to 81,209m altitude) before this was traced to the field
    registry entry above. Hand-computing here avoids depending on a
    second, asynchronous recording pipeline inside a tight real-time
    loop -- one self-contained state->orbital-elements calc instead.

    epsilon = v^2/2 - mu/r (specific orbital energy), a = -mu/(2*epsilon)
    (semi-major axis, valid for epsilon<0 -- a closed ellipse), h_ang =
    px*vy - py*vx (z-component of the specific angular momentum in this
    module's 2D world frame), e = sqrt(1 - h_ang^2/(mu*a)) (eccentricity).
    r_apo/r_peri = a*(1+-e). Returns (None, None) for a degenerate
    state (r<1m) or a hyperbolic/parabolic trajectory (epsilon>=0 --
    no apoapsis/periapsis pair exists, matching a real fast/steep
    powered-ascent trajectory before it settles into a bound orbit)."""
    r = math.hypot(px, py)
    if r < 1.0:
        return None, None
    v2 = vx * vx + vy * vy
    epsilon = v2 / 2.0 - mu / r
    if epsilon >= 0:
        return None, None
    a = -mu / (2.0 * epsilon)
    h_ang = px * vy - py * vx
    e_sq = 1.0 - (h_ang * h_ang) / (mu * a)
    e = math.sqrt(max(0.0, e_sq))
    r_apo = a * (1.0 + e)
    r_peri = a * (1.0 - e)
    return r_apo - body_radius_m, r_peri - body_radius_m


def run_gravity_turn_to_orbit(
    target_orbit_altitude_m: float,
    pitch_start_alt_m: float = 1500.0,
    pitch_end_alt_m: float = 25000.0,
    max_pitch_deg: float = 80.0,
    poll_hz: float = 5.0,
    max_duration_s: float = 900.0,
    circularize_tolerance_m: float = 1500.0,
) -> dict:
    """First orbit attempt: vertical liftoff -> gravity-turn ascent
    (pitch program + AttitudePD, throttle held near-full during the
    burn since the goal here is 'reach target apoapsis', not 'hover at
    an altitude' the way run_ascent()'s AltitudePD is built for) ->
    cut throttle once predicted apoapsis (the game's OWN live 'predApo'
    telemetry field, not a hand-rolled orbital-mechanics calc) reaches
    target -> coast to apoapsis -> circularization burn (point
    prograde, burn until the game's own 'predPeri' also reaches target,
    i.e. periapsis raised to match apoapsis).

    predApo/predPeri: the game's own telemetry fields exist but are
    ONLY populated by the continuous full-mode recording pipeline
    ('telemetry on'), not the per-tick 'telemetrysnapshot' query this
    loop uses (confirmed live, see _orbital_apoapsis_periapsis_alt's
    own docstring for the full story) -- apoapsis/periapsis here are
    computed directly from state instead (vis-viva + angular momentum),
    not read from the game.

    No LLM supervisor in this loop -- this is the deterministic flight-
    mechanics piece (attitude + throttle + phase sequencing), the same
    scope run_ascent() covers for straight-up flight. A first real
    attempt, not a tuned/proven controller -- gains and the pitch
    program are conservative starting points, expect to iterate after
    watching how it actually flies.
    """
    _call_with_retry(traced_act, "master on", label="act('master on')")

    attitude_ctrl = AttitudePD()
    dt = 1.0 / poll_hz
    t_start = time.monotonic()
    deadline = t_start + max_duration_s
    phase = "ascent"
    last_snapshot = None
    mu = fsim.PLANET_CONSTANTS["Earth"]["mu"]

    try:
        while time.monotonic() < deadline:
            snapshot = _call_with_retry(traced_observe, label="observe()")
            last_snapshot = snapshot
            state_now = observe_to_state(snapshot)
            px, py, vx, vy = state_now["px"], state_now["py"], state_now["vx"], state_now["vy"]
            r = math.hypot(px, py)
            altitude_m = r - EARTH_RADIUS_M
            theta = state_now["rot"]
            omega = state_now["angv"]
            t_now = time.monotonic() - t_start

            pred_apo_alt, pred_peri_alt = _orbital_apoapsis_periapsis_alt(
                px, py, vx, vy, mu, EARTH_RADIUS_M)

            # Spin watchdog (2026-09-12, post-incident) -- checked BEFORE
            # any phase logic runs, independent of AttitudePD's own
            # correctness, so a bug in the controller (like the sign
            # inversion that caused the first live attempt's runaway)
            # can never spin the craft past this point unnoticed. A real
            # gravity-turn pitch program never needs anywhere near this
            # much angular rate -- if omega gets here, something is
            # already wrong and the safest move is to stop commanding
            # turn/throttle entirely and hand control back, not to keep
            # trusting the loop to self-correct.
            if abs(omega) > SPIN_ABORT_THRESHOLD_DEGS:
                print(f"  [ABORT] |omega|={abs(omega):.1f}deg/s exceeds "
                      f"{SPIN_ABORT_THRESHOLD_DEGS:.0f}deg/s safety ceiling -- "
                      f"cutting turn and throttle, stopping the run")
                _call_with_retry(traced_act, "turn 0.0", label="act('turn 0.0')")
                _call_with_retry(traced_act, "throttle 0", label="act('throttle 0')")
                phase = "aborted_spin"
                break

            if phase == "ascent":
                pitch = _pitch_program_deg(altitude_m, pitch_start_alt_m,
                                            pitch_end_alt_m, max_pitch_deg)
                desired_theta = _vertical_theta_deg(px, py) - pitch
                turn_axis = attitude_ctrl.turn_axis_for(theta, desired_theta, omega)
                _call_with_retry(traced_act, f"turn {turn_axis}", label=f"act('turn {turn_axis}')")
                throttle = 1.0
                _call_with_retry(traced_act, f"throttle {throttle}", label=f"act('throttle {throttle}')")
                print(f"[ascent] alt={altitude_m:8.1f}m pitch={pitch:5.1f}deg theta={theta:7.2f} "
                      f"turn={turn_axis:+.2f} apo={pred_apo_alt} peri={pred_peri_alt}")
                if pred_apo_alt is not None and pred_apo_alt >= target_orbit_altitude_m:
                    phase = "coast_to_apo"
                    _call_with_retry(traced_act, "throttle 0", label="act('throttle 0')")
                    print(f"  [phase] apoapsis target reached (predApo={pred_apo_alt:.0f}m) "
                          f"-- cutting throttle, coasting to apoapsis")

            elif phase == "coast_to_apo":
                _call_with_retry(traced_act, "turn 0.0", label="act('turn 0.0')")
                _call_with_retry(traced_act, "throttle 0", label="act('throttle 0')")
                radial_v = (px * vx + py * vy) / r if r else 0.0
                print(f"[coast]  alt={altitude_m:8.1f}m radial_v={radial_v:6.1f}m/s "
                      f"apo={pred_apo_alt} peri={pred_peri_alt}")
                if abs(radial_v) < 3.0 and altitude_m > pitch_end_alt_m * 0.5:
                    phase = "circularize"
                    print(f"  [phase] near apoapsis (radial_v={radial_v:.1f}m/s) -- circularizing")

            elif phase == "circularize":
                heading_deg = math.degrees(math.atan2(vy, vx)) if math.hypot(vx, vy) > 1e-6 else theta + 90
                desired_theta = heading_deg - 90.0  # zero-AoA prograde pointing
                turn_axis = attitude_ctrl.turn_axis_for(theta, desired_theta, omega)
                _call_with_retry(traced_act, f"turn {turn_axis}", label=f"act('turn {turn_axis}')")
                throttle = 1.0
                _call_with_retry(traced_act, f"throttle {throttle}", label=f"act('throttle {throttle}')")
                print(f"[circ]   alt={altitude_m:8.1f}m theta={theta:7.2f} turn={turn_axis:+.2f} "
                      f"apo={pred_apo_alt} peri={pred_peri_alt}")
                if pred_peri_alt is not None and pred_peri_alt >= target_orbit_altitude_m - circularize_tolerance_m:
                    _call_with_retry(traced_act, "throttle 0", label="act('throttle 0')")
                    phase = "done"
                    print(f"  [phase] periapsis raised to {pred_peri_alt:.0f}m (target "
                          f"{target_orbit_altitude_m:.0f}m) -- ORBIT ACHIEVED, cutting throttle")
                    break

            time.sleep(dt)
    finally:
        try:
            _call_with_retry(act, "throttle 0", label="final throttle-cut act('throttle 0')")
        except Exception as e:  # noqa: BLE001 -- safety net, never mask the real error
            print(f"  [CRITICAL] failed to cut throttle after retries: {e} -- "
                  f"MANUAL INTERVENTION MAY BE NEEDED, check the game directly")

    return {"final_snapshot": last_snapshot, "phase_reached": phase}


if __name__ == "__main__":
    # Manual smoke test -- requires the game running with a rocket
    # loaded in the scene. Adjust target as needed.
    final_snapshot = run_ascent(target_altitude_m=20000.0)
    print("final snapshot:", final_snapshot)
