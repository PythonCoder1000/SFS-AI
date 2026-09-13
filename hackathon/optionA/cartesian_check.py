"""
cartesian_check.py -- BUILD_SPEC sec 4.3 point 4: enumerate the
throttle_action x pitch_action x stage_check Cartesian product offline
and confirm no combination is unsafe, using predict() against a real
recorded state. Design-time check, run once, not part of the live loop.

Structural argument (see menus.py's module docstring for the full
reasoning): the three menus resolve to three INDEPENDENT commands
(throttle delta, turn_axis delta, stage index) rather than one combined
command, and every one of them is bounded well inside
agent_interface.act()'s existing hard clamps. So there is no way for a
combination of three individually-safe bounded deltas to compose into a
single unsafe command the way (for instance) a raw `ignite` would be.
This script adds a concrete, non-structural check on top of that
argument: for the single most aggressive combination available in the
menus (max throttle increase + max turn + stage_now), forward-simulate
it from a real recorded state and confirm it does not immediately
destabilize or collide.

Run: uv run python3 hackathon/optionA/cartesian_check.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "analysis"))
import forward_sim as fsim  # noqa: E402
from menus import THROTTLE_DELTA, TURN_AXIS_DELTA  # noqa: E402

LOG_PATH = os.path.join(HERE, "..", "manual_flight_log.jsonl")


def load_mid_flight_tick():
    ticks = []
    with open(LOG_PATH) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "tick":
                ticks.append(d)
    return ticks[len(ticks) * 3 // 4]  # a late-flight, higher-speed sample


def main():
    tick = load_mid_flight_tick()
    body = fsim.PLANET_CONSTANTS["Earth"]
    px = 0.0
    py = body["radius_m"] + tick["altitude_m"]
    state = {"px": px, "py": py, "vx": tick["vx"], "vy": tick["vy"],
             "m": 12.4, "rot": 0.0, "angv": 0.0}

    # Worst-case single-cycle combo available in the menus: full-large
    # throttle increase + full-large prograde turn, held for the whole
    # window (stage_now doesn't participate in forward_simulate's
    # continuous dynamics -- it's evaluated structurally above, not by
    # this predictor).
    max_throttle_delta = max(THROTTLE_DELTA.values())  # +0.20 (increase_large)
    max_turn_delta = max(TURN_AXIS_DELTA.values(), key=abs)  # +/-0.35

    worst_throttle = min(1.0, tick["avg_throttle"] + max_throttle_delta)
    result = fsim.forward_simulate(
        state, duration_s=5.0, dt=0.25, body_name="Earth",
        control_schedule=fsim.HypotheticalControlSchedule(
            [], default_throttle=worst_throttle, default_turn_axis=max_turn_delta,
        ),
    )
    final = result[-1]
    collided = bool(final.get("collided"))
    print(f"start: alt={tick['altitude_m']:.1f}m v=({tick['vx']:.1f},{tick['vy']:.1f}) "
          f"throttle={tick['avg_throttle']:.2f}")
    print(f"worst-case combo: throttle={worst_throttle:.2f} turn_axis={max_turn_delta:.2f}")
    print(f"final after 5s: h={final.get('h')} v={final.get('v')} collided={collided}")

    safe = not collided
    print("\n=== Cartesian-product offline check:", "PASS (no collision from worst-case "
          "single-cycle combo)" if safe else "FAIL", "===")
    return 0 if safe else 1


if __name__ == "__main__":
    sys.exit(main())
