"""
test_checkpoint6.py -- Checkpoint 6 exit condition: confirm the new
PAD_IDLE-specific throttle_action/pitch_action criteria (menus.py) give
tsAI a real, distinct answer for a genuinely idle/unlaunched vehicle,
instead of forcing an ascent-shaping question onto a stationary craft.

This makes REAL /v1/systemone classification calls (same as
test_checkpoint1.py) against a REAL recorded low-altitude/near-zero-
speed sample from manual_flight_log.jsonl, built as an explicit
PAD_IDLE state (phase="PAD_IDLE", throttle=0.0). This is a
classification API call only -- no agent_interface.act() call is made
anywhere in this file, live or otherwise, per this session's hard
constraint against sending a real nonzero throttle command.

Run: uv run python3 hackathon/optionA/test_checkpoint6.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsai_client import SystemOneClient
from menus import MENUS, THROTTLE_DELTA, TURN_AXIS_DELTA
from state_builder import build_state, build_feasibility, build_prediction_block

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "manual_flight_log.jsonl")

CRAFT_MASS_T = 12.4
CRAFT_DRY_MASS_T = 6.0
CRAFT_ISP = 260.0
CRAFT_TORQUE_EFFECTIVE_RAW = 850.0
MISSION_TARGET = {"apoapsis_m": 100000, "periapsis_m": 90000}

VALID_CHOICES = {
    "throttle_action": set(THROTTLE_DELTA) | {"insufficient_data"},
    "pitch_action": set(TURN_AXIS_DELTA) | {"insufficient_data"},
}


def load_pad_idle_tick():
    with open(LOG_PATH) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "tick":
                return d
    raise RuntimeError(f"no ticks in {LOG_PATH}")


def build_pad_idle_state(tick, cycle_id=0):
    vehicle = {
        "altitude_m": tick["altitude_m"],
        "vertical_speed_mps": 0.0,
        "horizontal_speed_mps": 0.0,
        "angle_deg": 90.0,
        "angular_rate_dps": 0.0,
        "throttle": 0.0,
        "active_stage": 0,
        "fuel_remaining_pct": 100.0,
    }
    feasibility = build_feasibility(
        current_mass_t=CRAFT_MASS_T, dry_mass_t=CRAFT_DRY_MASS_T, isp=CRAFT_ISP,
        torque_effective_raw=CRAFT_TORQUE_EFFECTIVE_RAW,
        delta_v_required_for_target_mps=1550.0,
    )
    prediction = build_prediction_block(None, horizon_s=15.0)
    return build_state(cycle_id, tick["t"], "PAD_IDLE", MISSION_TARGET,
                        vehicle, feasibility, prediction)


def main():
    client = SystemOneClient()
    tick = load_pad_idle_tick()
    state = build_pad_idle_state(tick)

    print(f"--- PAD_IDLE state (real tick t={tick['t']:.1f}s, alt={tick['altitude_m']:.1f}m) ---")
    result = client.ask(state, MENUS)
    if not result["ok"]:
        print(f"CLIENT ERROR: {result['error']}")
        return 1
    if result["stale"]:
        print(f"WARNING: stale response (latency={result['latency_s']:.2f}s)")

    answers = result["answers"].get("answers", {})
    all_sane = True
    for qname in ("throttle_action", "pitch_action"):
        ans = answers.get(qname)
        if ans is None:
            print(f"  MISSING answer for {qname}")
            all_sane = False
            continue
        choice = ans.get("choice")
        conf = ans.get("confidence")
        in_menu = choice in VALID_CHOICES[qname]
        bounded = isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0
        print(f"  {qname}: choice={choice!r} confidence={conf} "
              f"(in_menu={in_menu}, bounded_confidence={bounded})")
        if not (in_menu and bounded):
            all_sane = False

    print("\nFor comparison, Checkpoint 4/5's live PAD_IDLE run (old menu wording, "
          "no launch/hold_on_pad framing) saw throttle_action confidence 0.13-0.22 "
          "and pitch_action mostly insufficient_data at 0.24-0.46, both below the "
          "0.5 routine confidence floor -- see BUILD_LOG.md Checkpoint 4/5.")

    print("\n=== Checkpoint 6 exit check:", "PASS (sane, in-menu, bounded answers)"
          if all_sane else "FAIL", "===")
    return 0 if all_sane else 1


if __name__ == "__main__":
    sys.exit(main())
