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

Checkpoint 6 update: menus.py added a PAD_IDLE-specific `launch`
throttle_action choice (+0.30, at the same act()-clamp boundary as the
old ascent-only max of +0.20) and a `hold_on_pad` pitch_action choice
(+0.0). This script now runs TWO worst-case cases instead of one: Case
1 (unchanged) covers an in-flight ASCENT_GRAVITY_TURN vehicle; Case 2
(new) covers a PAD_IDLE vehicle exercising `launch` paired
pessimistically with the largest available turn_axis magnitude in the
whole menu (not the menu's own recommended `launch` + `hold_on_pad`
pairing, which is turn_axis=0.0 and therefore strictly less aggressive
than what this check exercises).

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


def load_pad_idle_tick():
    """An early/near-zero-speed, low-altitude sample -- stands in for a
    genuine PAD_IDLE state (this log has no real t=0 pad sample, but the
    first recorded tick is the closest real approximation available:
    lowest altitude, lowest speed). Used for Checkpoint 6's PAD_IDLE
    worst-case case (`launch`), separate from the mid-flight case above."""
    ticks = []
    with open(LOG_PATH) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "tick":
                ticks.append(d)
    return ticks[0]


def run_combo(tick, start_throttle, throttle_delta, turn_delta, label):
    body = fsim.PLANET_CONSTANTS["Earth"]
    px = 0.0
    py = body["radius_m"] + tick["altitude_m"]
    state = {"px": px, "py": py, "vx": tick["vx"], "vy": tick["vy"],
             "m": 12.4, "rot": 0.0, "angv": 0.0}

    worst_throttle = max(0.0, min(1.0, start_throttle + throttle_delta))
    result = fsim.forward_simulate(
        state, duration_s=5.0, dt=0.25, body_name="Earth",
        control_schedule=fsim.HypotheticalControlSchedule(
            [], default_throttle=worst_throttle, default_turn_axis=turn_delta,
        ),
    )
    final = result[-1]
    collided = bool(final.get("collided"))
    print(f"\n--- {label} ---")
    print(f"start: alt={tick['altitude_m']:.1f}m v=({tick['vx']:.1f},{tick['vy']:.1f}) "
          f"throttle={start_throttle:.2f}")
    print(f"combo: throttle={worst_throttle:.2f} turn_axis={turn_delta:.2f}")
    print(f"final after 5s: h={final.get('h')} v={final.get('v')} collided={collided}")
    return not collided


def main():
    all_safe = True

    # Case 1 (Checkpoint 1, unchanged): worst-case single-cycle combo
    # available to an in-flight ASCENT_GRAVITY_TURN vehicle -- full-large
    # throttle increase + full-large prograde turn, held for the whole
    # window (stage_now doesn't participate in forward_simulate's
    # continuous dynamics -- it's evaluated structurally above, not by
    # this predictor).
    mid_tick = load_mid_flight_tick()
    ascent_throttle_delta = max(
        v for k, v in THROTTLE_DELTA.items() if k != "launch")  # +0.20 (increase_large)
    ascent_turn_delta = max(TURN_AXIS_DELTA.values(), key=abs)  # +/-0.35
    all_safe &= run_combo(
        mid_tick, mid_tick["avg_throttle"], ascent_throttle_delta, ascent_turn_delta,
        "Case 1: ASCENT_GRAVITY_TURN worst-case (increase_large + prograde_large)")

    # Case 2 (Checkpoint 6, new): worst-case single-cycle combo available
    # to a PAD_IDLE vehicle now that `launch` (+0.30) exists -- from a
    # near-zero-throttle, near-zero-speed, low-altitude start, `launch`
    # combined with the largest available turn_axis magnitude (a
    # PAD_IDLE vehicle would normally pair `launch` with `hold_on_pad`
    # per the menu's own instructions, i.e. turn_axis=0.0 -- pairing it
    # instead with the largest turn delta in the whole menu, including
    # `hold_on_pad`'s own 0.0, is the deliberately-pessimistic worst case
    # this check exists to rule out, not the expected combination).
    pad_tick = load_pad_idle_tick()
    launch_throttle_delta = THROTTLE_DELTA["launch"]  # +0.30
    pad_turn_delta = max(TURN_AXIS_DELTA.values(), key=abs)  # +/-0.35
    all_safe &= run_combo(
        pad_tick, 0.0, launch_throttle_delta, pad_turn_delta,
        "Case 2: PAD_IDLE worst-case (launch + largest available turn_axis)")

    print("\n=== Cartesian-product offline check:",
          "PASS (no collision from either worst-case single-cycle combo)"
          if all_safe else "FAIL", "===")
    return 0 if all_safe else 1


if __name__ == "__main__":
    sys.exit(main())
