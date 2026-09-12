"""Checkpoint D -- guardrail gateway + arbitration/disablement latch
(spec sec 9). Sits between a supervisor.Correction and act() -- nothing
in this project calls act() directly on a Correction before it has
passed through GuardrailGateway.evaluate().

Gateway, in order, per spec:
    1. Schema validation (already done once in supervisor.py -- this
       layer re-checks structurally, deliberate defense in depth, not
       redundant waste: a gateway that trusts its caller's validation
       isn't really a gateway).
    2. Staging finite-state machine: reject any stage_request that
       isn't exactly the current expected_stage. There is no `ignite`
       anywhere in this schema at all (see supervisor.py's tool
       definition) -- the known catastrophic failure mode from
       sfsprobe/mod_changelog.md's ignite finding is structurally
       impossible here, not just discouraged.
    3. Clamp: relies on agent_interface.act()'s existing
       MAX_THROTTLE_STEP rate limit -- this gateway doesn't duplicate
       that, just documents the reliance.
    4. Mandatory multi-step predict-based sanity check for ANY
       correction with a real effect (not just stage/ignite-affecting
       ones, per this project's own choice to apply it more broadly --
       predict() costs ~0.5ms, so the extra caution is nearly free).
       Checks every intermediate point of a real forward_sim.py
       trajectory, not just the terminal one -- a single-endpoint check
       is the documented chattering failure mode the spec cites
       (16.3cm->3.6cm oscillation reduction measured on a real
       quadrotor from widening exactly this kind of filter).

On rejection: typed cause, one of RejectionCause. Retry-once-with-
cause-fed-back is the CALLER's responsibility (needs to re-invoke
call_supervisor with the cause in the prompt) -- this module only
classifies and decides accept/reject, it doesn't retry anything itself.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RejectionCause(str, Enum):
    SCHEMA_INVALID = "schema_invalid"
    STATE_INVARIANT_VIOLATION = "state_invariant_violation"
    PREDICTION_RISK = "prediction_risk"
    GATEWAY_UNCERTAIN = "gateway_uncertain"
    GATEWAY_INTERNAL_ERROR = "gateway_internal_error"


@dataclass
class GatewayDecision:
    accepted: bool
    cause: Optional[RejectionCause] = None
    detail: str = ""


# ---------------------------------------------------------------------------
# Individual gate checks -- each returns None (pass) or a RejectionCause
# ---------------------------------------------------------------------------

def check_schema(correction) -> Optional[RejectionCause]:
    """Defense in depth: re-validate structurally even though
    supervisor._validate_and_build() already did this once. A gateway
    that assumes its input is clean because "it must have passed
    validation already" is not actually a gate."""
    if correction is None:
        return RejectionCause.SCHEMA_INVALID
    if not correction.no_change:
        if correction.target_throttle is None:
            return RejectionCause.SCHEMA_INVALID
        if not (0.0 <= correction.target_throttle <= 1.0):
            return RejectionCause.SCHEMA_INVALID
    if correction.stage_request is not None and correction.stage_request < 0:
        return RejectionCause.SCHEMA_INVALID
    return None


class StagingGate:
    """expected_stage FSM + debounce. Reject any stage_request that
    isn't exactly the current expected stage -- no skipping ahead, no
    re-requesting a stage that's already been armed this "session"
    (debounced), matching sfsprobe's own confirmed non-idempotent
    `stage` behavior (mod_changelog.md, 2026-09-12): a duplicate stage
    request reaching the game can silently toggle engines back off,
    so this gate is the reason a duplicate never gets that far."""

    def __init__(self, debounce_s: float = 2.0):
        self.debounce_s = debounce_s
        self._last_accepted_stage: Optional[int] = None
        self._last_accepted_t: float = float("-inf")

    def check(self, stage_request: Optional[int], expected_stage: int, now_s: float) -> Optional[RejectionCause]:
        if stage_request is None:
            return None  # no staging action requested -- nothing to check

        if stage_request != expected_stage:
            return RejectionCause.STATE_INVARIANT_VIOLATION

        if (self._last_accepted_stage == stage_request
                and (now_s - self._last_accepted_t) < self.debounce_s):
            return RejectionCause.STATE_INVARIANT_VIOLATION  # debounced duplicate

        return None

    def record_accepted(self, stage_request: int, now_s: float) -> None:
        self._last_accepted_stage = stage_request
        self._last_accepted_t = now_s


def check_prediction_risk(
    correction, current_state: dict, craft_config: dict, aoa_table: dict,
    predict_fn, duration_s: float = 3.0,
) -> Optional[RejectionCause]:
    """Mandatory multi-step sanity check: forward-simulate the proposed
    correction and inspect EVERY intermediate trajectory point, not
    just the final one. predict_fn is injected (not imported directly)
    so this module stays testable offline with a fake -- see the
    __main__ block."""
    if correction.no_change:
        return None  # nothing to check -- current plan continues unchanged

    throttle = correction.target_throttle if correction.target_throttle is not None else 0.0
    try:
        result = predict_fn(
            current_state, waypoints=[], duration_s=duration_s,
            craft_config=craft_config, aoa_table=aoa_table, default_throttle=throttle,
        )
    except Exception:  # noqa: BLE001 -- a predict() failure itself is a risk signal,
        # not something to propagate and crash the gateway.
        return RejectionCause.GATEWAY_INTERNAL_ERROR

    trajectory = result.get("trajectory", [])
    if not trajectory:
        return RejectionCause.GATEWAY_UNCERTAIN

    for point in trajectory:  # multi-step -- every intermediate point, not just the last
        if point.get("collided"):
            return RejectionCause.PREDICTION_RISK
        if point.get("would_destroy"):
            return RejectionCause.PREDICTION_RISK

    return None


class GuardrailGateway:
    """Combines all four checks in order, per spec sec 9. Stops at the
    first rejection -- cheaper checks (schema, staging) run before the
    expensive one (prediction risk, ~0.5ms but still last)."""

    def __init__(self, staging_gate: Optional[StagingGate] = None):
        self.staging_gate = staging_gate or StagingGate()

    def evaluate(
        self, correction, expected_stage: int, now_s: float,
        current_state: dict, craft_config: dict, aoa_table: dict, predict_fn,
    ) -> GatewayDecision:
        cause = check_schema(correction)
        if cause:
            return GatewayDecision(False, cause, "schema check failed")

        cause = self.staging_gate.check(correction.stage_request, expected_stage, now_s)
        if cause:
            return GatewayDecision(False, cause, "staging FSM rejected stage_request")

        cause = check_prediction_risk(correction, current_state, craft_config, aoa_table, predict_fn)
        if cause:
            return GatewayDecision(False, cause, "multi-step predict sanity check failed")

        if correction.stage_request is not None:
            self.staging_gate.record_accepted(correction.stage_request, now_s)
        return GatewayDecision(True)


# ---------------------------------------------------------------------------
# Arbitration / disablement latch (spec sec 9)
# ---------------------------------------------------------------------------

class DisablementLatch:
    """Replaces a naive "3 consecutive rejections -> disable". Only
    STATE_INVARIANT_VIOLATION and repeated PREDICTION_RISK rejections
    under materially similar state/phase count -- a schema hiccup or a
    transient freshness failure never counts. The counter decays on a
    meaningful state or phase change. Re-enabling requires SUSTAINED
    deterministic stability (several consecutive good ticks), not one
    -- a one-way latch within a disablement episode, not a toggle.

    "Materially similar state" is approximated here as: same phase,
    same rejection cause, altitude within similarity_band_m of the
    previous counted rejection. Good enough for this project's single-
    phase ascent; a multi-phase mission would need a richer notion.
    """

    def __init__(
        self,
        disable_after: int = 3,
        reenable_after_stable_ticks: int = 5,
        similarity_band_m: float = 500.0,
    ):
        self.disable_after = disable_after
        self.reenable_after_stable_ticks = reenable_after_stable_ticks
        self.similarity_band_m = similarity_band_m

        self._count = 0
        self._last_cause: Optional[RejectionCause] = None
        self._last_phase: Optional[str] = None
        self._last_altitude_m: Optional[float] = None
        self._disabled = False
        self._stable_ticks = 0

    @property
    def disabled(self) -> bool:
        return self._disabled

    def record_rejection(self, cause: RejectionCause, phase: str, altitude_m: float) -> bool:
        """Call on every gateway rejection. Returns True if this
        rejection just caused (or kept) the latch disabled."""
        counts = cause in (RejectionCause.STATE_INVARIANT_VIOLATION, RejectionCause.PREDICTION_RISK)
        materially_similar = (
            counts and self._last_cause == cause and self._last_phase == phase
            and self._last_altitude_m is not None
            and abs(altitude_m - self._last_altitude_m) <= self.similarity_band_m
        )

        if counts:
            self._count = self._count + 1 if materially_similar else 1
            self._last_cause, self._last_phase, self._last_altitude_m = cause, phase, altitude_m
            self._stable_ticks = 0  # any counted rejection resets stability progress
        # a non-counting rejection (schema hiccup, uncertain) doesn't touch the counter

        if self._count >= self.disable_after:
            self._disabled = True
        return self._disabled

    def record_stable_tick(self, phase: str, residual_within_tolerance: bool) -> None:
        """Call once per tick the deterministic layer is in control and
        residual is within tolerance -- the only path back from
        disablement. A phase change alone does NOT re-enable; sustained
        stability does."""
        if phase != self._last_phase:
            self._count = 0  # decay: meaningful phase change clears the counter
        if residual_within_tolerance:
            self._stable_ticks += 1
        else:
            self._stable_ticks = 0

        if self._disabled and self._stable_ticks >= self.reenable_after_stable_ticks:
            self._disabled = False
            self._count = 0
            self._stable_ticks = 0


# ---------------------------------------------------------------------------
# Offline tests -- fake predict_fn, no live game needed
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dataclasses import dataclass as _dc

    @_dc
    class FakeCorrection:
        no_change: bool = False
        target_throttle: Optional[float] = 0.5
        stage_request: Optional[int] = None
        reason_code: str = "test"
        commit_ms: Optional[int] = None

    def fake_predict_safe(state, **kwargs):
        return {"trajectory": [{"collided": False, "would_destroy": False} for _ in range(5)]}

    def fake_predict_collision(state, **kwargs):
        return {"trajectory": [
            {"collided": False, "would_destroy": False},
            {"collided": False, "would_destroy": False},
            {"collided": True, "would_destroy": False},  # crashes mid-trajectory, not at the end
        ]}

    def fake_predict_heat(state, **kwargs):
        return {"trajectory": [{"collided": False, "would_destroy": True}]}

    print("=== check_schema ===")
    assert check_schema(None) == RejectionCause.SCHEMA_INVALID
    assert check_schema(FakeCorrection(target_throttle=None)) == RejectionCause.SCHEMA_INVALID
    assert check_schema(FakeCorrection(target_throttle=5.0)) == RejectionCause.SCHEMA_INVALID
    assert check_schema(FakeCorrection(target_throttle=0.5)) is None
    assert check_schema(FakeCorrection(no_change=True, target_throttle=None)) is None
    print("  OK -- all schema cases correct")

    print("\n=== StagingGate ===")
    sg = StagingGate(debounce_s=2.0)
    assert sg.check(stage_request=0, expected_stage=0, now_s=0.0) is None
    sg.record_accepted(0, 0.0)
    assert sg.check(stage_request=0, expected_stage=0, now_s=0.5) == RejectionCause.STATE_INVARIANT_VIOLATION  # debounced
    assert sg.check(stage_request=1, expected_stage=0, now_s=0.5) == RejectionCause.STATE_INVARIANT_VIOLATION  # skip-ahead
    assert sg.check(stage_request=None, expected_stage=0, now_s=0.5) is None  # no request = pass
    assert sg.check(stage_request=0, expected_stage=0, now_s=3.0) is None  # debounce window elapsed
    print("  OK -- staging FSM rejects skip-ahead and debounces duplicates")

    print("\n=== check_prediction_risk ===")
    state = {"px": 0.0, "py": 315000.0, "vx": 0.0, "vy": 100.0, "m": 116.0}
    assert check_prediction_risk(FakeCorrection(no_change=True), state, {}, {}, fake_predict_safe) is None
    assert check_prediction_risk(FakeCorrection(), state, {}, {}, fake_predict_safe) is None
    assert check_prediction_risk(FakeCorrection(), state, {}, {}, fake_predict_collision) == RejectionCause.PREDICTION_RISK
    assert check_prediction_risk(FakeCorrection(), state, {}, {}, fake_predict_heat) == RejectionCause.PREDICTION_RISK
    print("  OK -- catches mid-trajectory collision and heat-destroy, not just terminal point")

    print("\n=== GuardrailGateway end to end ===")
    gw = GuardrailGateway()
    d = gw.evaluate(FakeCorrection(), expected_stage=0, now_s=0.0,
                     current_state=state, craft_config={}, aoa_table={}, predict_fn=fake_predict_safe)
    assert d.accepted, d
    d = gw.evaluate(FakeCorrection(), expected_stage=0, now_s=0.1,
                     current_state=state, craft_config={}, aoa_table={}, predict_fn=fake_predict_collision)
    assert not d.accepted and d.cause == RejectionCause.PREDICTION_RISK, d
    d = gw.evaluate(FakeCorrection(stage_request=5), expected_stage=0, now_s=0.2,
                     current_state=state, craft_config={}, aoa_table={}, predict_fn=fake_predict_safe)
    assert not d.accepted and d.cause == RejectionCause.STATE_INVARIANT_VIOLATION, d
    print("  OK -- accepts good corrections, rejects bad ones with the right typed cause")

    print("\n=== DisablementLatch ===")
    latch = DisablementLatch(disable_after=3, reenable_after_stable_ticks=5, similarity_band_m=500.0)
    latch.record_rejection(RejectionCause.SCHEMA_INVALID, "ASCENT", 5000.0)
    assert not latch.disabled, "schema hiccups must never count toward disablement"
    latch.record_rejection(RejectionCause.STATE_INVARIANT_VIOLATION, "ASCENT", 5000.0)
    latch.record_rejection(RejectionCause.STATE_INVARIANT_VIOLATION, "ASCENT", 5100.0)  # within band -- counts
    assert not latch.disabled
    latch.record_rejection(RejectionCause.STATE_INVARIANT_VIOLATION, "ASCENT", 5150.0)  # 3rd -- disables
    assert latch.disabled
    for _ in range(4):
        latch.record_stable_tick("ASCENT", residual_within_tolerance=True)
    assert latch.disabled, "must stay disabled before reenable_after_stable_ticks is reached"
    latch.record_stable_tick("ASCENT", residual_within_tolerance=True)  # 5th consecutive
    assert not latch.disabled, "sustained stability should re-enable"
    print("  OK -- ignores schema hiccups, disables on sustained similar violations, "
          "requires sustained stability (not one tick) to re-enable")

    print("\n=== DisablementLatch: phase change decays counter ===")
    latch2 = DisablementLatch(disable_after=3)
    latch2.record_rejection(RejectionCause.PREDICTION_RISK, "ASCENT", 8000.0)
    latch2.record_rejection(RejectionCause.PREDICTION_RISK, "ASCENT", 8050.0)
    latch2.record_stable_tick("DESCENT", residual_within_tolerance=True)  # phase change decays
    latch2.record_rejection(RejectionCause.PREDICTION_RISK, "DESCENT", 100.0)
    assert not latch2.disabled, "counter should have decayed on phase change, not accumulated to 3"
    print("  OK -- phase change correctly decays the counter")
