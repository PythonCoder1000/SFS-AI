"""Deterministic inner controller -- Checkpoint B (Stage 0).

Zero LLM in the loop. Flies straight up to a target altitude using a
PD throttle controller, plus a minimal staging state machine.

Imports the real observe()/act() from analysis/agent_interface.py --
that file is pre-existing hackathon-prep plumbing (see its own
docstring), not something we rebuild here.
"""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

import forward_sim as fsim  # noqa: E402  (path set above)
from agent_interface import observe, observe_to_state, act  # noqa: E402

EARTH_RADIUS_M = fsim.PLANET_CONSTANTS["Earth"]["radius_m"]

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
) -> dict:
    """Fly straight up to target_altitude_m, zero LLM. Returns the last
    observed snapshot. This is the Checkpoint B / Stage 0 fallback
    demo -- must work standalone, no supervisor, no guardrail gateway.

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
    deadline = time.monotonic() + max_duration_s

    last_snapshot = None
    try:
        while time.monotonic() < deadline:
            snapshot = observe()
            last_snapshot = snapshot
            altitude_m, vspeed = _altitude_and_vspeed(snapshot)

            maybe_stage(snapshot)  # no-op placeholder, see TODO above

            if abs(target_altitude_m - altitude_m) <= tolerance_m:
                break

            throttle = controller.throttle_for(altitude_m, vspeed)
            act(f"throttle {throttle}")
            print(f"alt={altitude_m:8.1f}m  vspeed={vspeed:7.1f}m/s  throttle={throttle:.2f}")

            time.sleep(dt)
    finally:
        # Always cut throttle on the way out -- tolerance reached, timeout
        # hit, or an exception/KeyboardInterrupt -- never leave the last
        # commanded throttle running unattended. Matches the plan's own
        # "never an indefinite freeze" rule (sec 7.1), applied here even
        # though the full expiry contract isn't built until Checkpoint C.
        act("throttle 0")

    return last_snapshot


if __name__ == "__main__":
    # Manual smoke test -- requires the game running with a rocket
    # loaded in the scene. Adjust target as needed.
    final_snapshot = run_ascent(target_altitude_m=20000.0)
    print("final snapshot:", final_snapshot)
