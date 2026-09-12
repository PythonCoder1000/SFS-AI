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
_stage_state = {"expected_stage": 0}

# TODO(Checkpoint B, open item): the real trigger condition for "this
# stage is spent, advance" needs to be confirmed against live telemetry
# (fuel/thrOn semantics per sfsprobe's actual field set) before this is
# more than a manual/placeholder hook. Don't wire this to auto-fire
# until that's verified -- see hackathon plan sec 9 on stage command
# idempotency being an open, unverified gap.
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
    """

    def __init__(self, target_altitude_m: float, kp: float = 0.0006, kd: float = 0.05):
        self.target_altitude_m = target_altitude_m
        self.kp = kp
        self.kd = kd

    def throttle_for(self, altitude_m: float, vertical_speed_mps: float) -> float:
        alt_error = self.target_altitude_m - altitude_m
        raw = self.kp * alt_error - self.kd * vertical_speed_mps
        return max(0.0, min(1.0, raw))


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
    demo -- must work standalone, no supervisor, no guardrail gateway."""
    controller = AltitudePD(target_altitude_m)
    dt = 1.0 / poll_hz
    deadline = time.monotonic() + max_duration_s

    last_snapshot = None
    while time.monotonic() < deadline:
        snapshot = observe()
        last_snapshot = snapshot
        altitude_m, vspeed = _altitude_and_vspeed(snapshot)

        maybe_stage(snapshot)  # no-op placeholder, see TODO above

        if abs(target_altitude_m - altitude_m) <= tolerance_m:
            act("throttle 0")
            break

        throttle = controller.throttle_for(altitude_m, vspeed)
        act(f"throttle {throttle}")

        time.sleep(dt)

    return last_snapshot


if __name__ == "__main__":
    # Manual smoke test -- requires the game running with a rocket
    # loaded in the scene. Adjust target as needed.
    final_snapshot = run_ascent(target_altitude_m=20000.0)
    print("final snapshot:", final_snapshot)
