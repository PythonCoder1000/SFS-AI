"""Checkpoint C -- residual detector, causal classifier, and the LLM
replan trigger (the event gate).

Everything in this file is deterministic. No LLM call happens here --
this is the layer that decides WHETHER to ask the LLM anything at all,
and (separately) pre-classifies WHY a residual exists before the LLM
ever sees the state. Per the hackathon spec sec 5: localization stays
deterministic because the project's own research finding is that LLMs
are measurably bad at localizing their own error even when they can
act on a located one.

Nothing here touches sfsprobe/agent_interface -- it's pure math over
(predicted, actual) state pairs, so it's fully testable offline. See
the __main__ block for a synthetic smoke test.
"""

import math
from collections import deque
from typing import Optional

import weave


# ---------------------------------------------------------------------------
# Residual detector
# ---------------------------------------------------------------------------

@weave.op()
def compute_residual(predicted_final: dict, actual_state: dict) -> dict:
    """Compare a predict() call's predicted final state against what
    observe() actually shows at that same point in time.

    predicted_final: the {"px","py","vx","vy",...} dict from a
    predict() call's result["final"].
    actual_state: the same shape, from observe_to_state().

    Returns {"position_error_m": float, "speed_error_mps": float}.
    """
    dx = actual_state["px"] - predicted_final["px"]
    dy = actual_state["py"] - predicted_final["py"]
    position_error_m = math.hypot(dx, dy)

    pred_speed = math.hypot(predicted_final.get("vx", 0.0), predicted_final.get("vy", 0.0))
    actual_speed = math.hypot(actual_state.get("vx", 0.0), actual_state.get("vy", 0.0))
    speed_error_mps = actual_speed - pred_speed

    return {"position_error_m": position_error_m, "speed_error_mps": speed_error_mps}


class ResidualTrend:
    """Tracks residual magnitude over a short rolling window and reports
    whether it's growing, shrinking, or stable, plus a slope estimate
    (units/sec). Used both by the trigger (is this getting worse?) and
    by the state summary shown to the LLM (sec 5's prediction_residual
    schema fields)."""

    def __init__(self, window: int = 5, stable_band: float = 2.0):
        self.window = window
        self.stable_band = stable_band  # slope magnitude below this reads as "stable"
        self._samples = deque(maxlen=window)  # (t, magnitude)

    def update(self, t: float, magnitude: float) -> dict:
        self._samples.append((t, magnitude))
        if len(self._samples) < 2:
            return {"trend": "stable", "residual_slope": 0.0}

        t0, m0 = self._samples[0]
        t1, m1 = self._samples[-1]
        dt = t1 - t0
        slope = (m1 - m0) / dt if dt > 0 else 0.0

        if slope > self.stable_band:
            trend = "growing"
        elif slope < -self.stable_band:
            trend = "shrinking"
        else:
            trend = "stable"

        return {"trend": trend, "residual_slope": slope}


# ---------------------------------------------------------------------------
# Causal classifier -- deterministic, computed BEFORE the LLM sees anything
# ---------------------------------------------------------------------------

CausalCategory = str  # one of the enum values below, kept as plain str
CAUSAL_CATEGORIES = (
    "underperformance", "overshoot", "turn_model_mismatch",
    "actuator_saturation", "stage_transition", "unknown",
)


@weave.op()
def classify_cause(
    position_error_m: float,
    speed_error_mps: float,
    prediction_confidence: str,
    actuator_saturated: bool,
    just_staged: bool,
) -> CausalCategory:
    """Deterministic, rule-based -- no LLM. Order matters: check the
    unambiguous structural causes first (staging, saturation) before
    falling back to residual-sign-based guesses."""
    if just_staged:
        return "stage_transition"
    if actuator_saturated:
        return "actuator_saturation"
    if prediction_confidence == "low":
        # predict() itself flagged this regime as unreliable (atmospheric
        # turning) -- the residual is expected here, not a control failure.
        return "turn_model_mismatch"
    if speed_error_mps > 0 and position_error_m > 0:
        return "overshoot"
    if speed_error_mps < 0 and position_error_m > 0:
        return "underperformance"
    return "unknown"


# ---------------------------------------------------------------------------
# Replan trigger -- the LLM event gate (spec sec 6)
# ---------------------------------------------------------------------------

class TriggerDecision:
    def __init__(self, should_replan: bool, reason: str):
        self.should_replan = should_replan
        self.reason = reason

    def __repr__(self):
        return f"TriggerDecision(should_replan={self.should_replan}, reason={self.reason!r})"


class ReplanTrigger:
    """Decides WHEN the LLM supervisor gets called. Every threshold here
    is a placeholder per the spec -- tune against real dry-run data, not
    these numbers. Chattering (firing every few seconds) is called out
    in the spec as the single most likely visible demo failure, same
    shape as the PD throttle chatter we already hit and fixed.

    - enter_threshold_m / clear_threshold_m: asymmetric hysteresis
      (clear < enter) so it doesn't immediately re-trigger at the
      boundary.
    - persistence_ticks: consecutive ticks above enter_threshold_m
      required before actually firing -- ignores single-tick noise
      spikes.
    - cooldown_s: minimum real time between fires, regardless of
      residual state.
    - max_replans_per_phase: hard cap; reset via reset_phase().
    - heartbeat_interval_s: fires independent of threshold state, to
      catch drift that never crosses enter_threshold_m.
    - confidence == "low": hard override, per spec sec 6 -- suppresses
      ALL LLM-driven replanning (including heartbeat) and hands full
      authority to the deterministic layer. This is the plan's answer
      to atmospheric-turn regime degradation.
    """

    def __init__(
        self,
        enter_threshold_m: float = 300.0,
        clear_threshold_m: float = 100.0,
        persistence_ticks: int = 3,
        cooldown_s: float = 5.0,
        max_replans_per_phase: int = 5,
        heartbeat_interval_s: float = 20.0,
    ):
        assert clear_threshold_m < enter_threshold_m, "hysteresis requires clear < enter"
        self.enter_threshold_m = enter_threshold_m
        self.clear_threshold_m = clear_threshold_m
        self.persistence_ticks = persistence_ticks
        self.cooldown_s = cooldown_s
        self.max_replans_per_phase = max_replans_per_phase
        self.heartbeat_interval_s = heartbeat_interval_s

        self._in_violation = False
        self._consecutive_above = 0
        self._last_replan_time = 0.0
        self._last_heartbeat_time = 0.0
        self._replans_this_phase = 0
        self._current_phase: Optional[str] = None
        self._seen_first_tick = False

    def reset_phase(self, phase: str) -> None:
        """Call whenever the flight phase changes -- resets the per-phase
        cap and clears any in-progress violation/persistence state, since
        a residual measured against the old phase's plan is meaningless
        in the new one."""
        self._current_phase = phase
        self._replans_this_phase = 0
        self._in_violation = False
        self._consecutive_above = 0

    @weave.op()
    def update(self, residual_m: float, now_s: float, confidence: str) -> TriggerDecision:
        if not self._seen_first_tick:
            # Seed the cooldown/heartbeat clocks from the first real
            # timestamp we see, rather than assuming now_s starts near 0
            # -- time.monotonic() in the real run loop is a large
            # absolute value, so seeding at construction time would
            # otherwise make the very first tick look "overdue" and
            # fire immediately, before the flight has really started.
            self._last_replan_time = now_s
            self._last_heartbeat_time = now_s
            self._seen_first_tick = True

        if confidence == "low":
            return TriggerDecision(False, "confidence_low_override")

        # Hysteresis state machine
        if not self._in_violation:
            if residual_m > self.enter_threshold_m:
                self._consecutive_above += 1
            else:
                self._consecutive_above = 0
        else:
            if residual_m < self.clear_threshold_m:
                self._in_violation = False
                self._consecutive_above = 0

        cooldown_ok = (now_s - self._last_replan_time) >= self.cooldown_s
        cap_ok = self._replans_this_phase < self.max_replans_per_phase

        # Threshold-driven fire: just crossed into violation with enough persistence
        if not self._in_violation and self._consecutive_above >= self.persistence_ticks:
            self._in_violation = True
            if cooldown_ok and cap_ok:
                self._fire(now_s)
                return TriggerDecision(True, "residual_threshold")
            return TriggerDecision(False, "cooldown" if not cooldown_ok else "phase_cap_reached")

        # Heartbeat: independent of threshold state, catches sub-threshold drift
        if (now_s - self._last_heartbeat_time) >= self.heartbeat_interval_s:
            if cooldown_ok and cap_ok:
                self._fire(now_s)
                return TriggerDecision(True, "heartbeat")
            # Don't reset the heartbeat clock on a blocked attempt -- try again next tick
            return TriggerDecision(False, "cooldown" if not cooldown_ok else "phase_cap_reached")

        return TriggerDecision(False, "below_threshold")

    def _fire(self, now_s: float) -> None:
        self._last_replan_time = now_s
        self._last_heartbeat_time = now_s  # a fire counts as a heartbeat too
        self._replans_this_phase += 1


# ---------------------------------------------------------------------------
# Synthetic smoke test -- no live game needed
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== ReplanTrigger synthetic test ===")
    trigger = ReplanTrigger(
        enter_threshold_m=300.0, clear_threshold_m=100.0,
        persistence_ticks=3, cooldown_s=5.0,
        max_replans_per_phase=5, heartbeat_interval_s=20.0,
    )
    trigger.reset_phase("ASCENT_GRAVITY_TURN")

    # Simulated residual profile over 40 ticks @ 1s cadence:
    # ramps up past threshold, stays, gets cleared, ramps again, low-confidence spike
    residuals = (
        [50] * 5 +               # nominal
        [200, 280, 320, 340, 350, 360] +   # climbing past enter=300
        [370] * 5 +               # sustained violation (should only fire once)
        [50] * 10 +               # cleared, back to nominal (heartbeat may fire)
        [500] * 4                 # sudden spike, but confidence will be "low" here
    )
    confidences = ["high"] * 26 + ["low"] * 4

    for i, (r, conf) in enumerate(zip(residuals, confidences)):
        t = float(i)
        decision = trigger.update(r, t, conf)
        marker = "  <-- FIRED" if decision.should_replan else ""
        print(f"t={t:5.1f}  residual={r:6.1f}  conf={conf:5}  "
              f"-> {decision.reason:<22}{marker}")

    print("\n=== ResidualTrend + classify_cause test ===")
    trend = ResidualTrend(window=4)
    predicted = {"px": 0.0, "py": 314970.0 + 18000, "vx": 0.0, "vy": 60.0}
    actual_growing = {"px": 5.0, "py": 314970.0 + 18000 + 150, "vx": 0.0, "vy": 75.0}
    for t in range(6):
        res = compute_residual(predicted, actual_growing)
        mag = res["position_error_m"]
        t_info = trend.update(float(t), mag)
        cause = classify_cause(
            res["position_error_m"], res["speed_error_mps"],
            prediction_confidence="high", actuator_saturated=False, just_staged=False,
        )
        print(f"t={t}  pos_err={mag:6.1f}m  spd_err={res['speed_error_mps']:5.1f}m/s  "
              f"trend={t_info['trend']:<9} slope={t_info['residual_slope']:6.2f}  cause={cause}")
        actual_growing["py"] += 20  # simulate a growing gap each tick
