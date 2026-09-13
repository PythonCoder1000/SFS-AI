"""
test_checkpoint1.py -- Checkpoint 1 exit condition: unit-test the tsAI
client + menus against a handful of REAL states pulled from
hackathon/manual_flight_log.jsonl, confirm sane, bounded output. No live
game needed (per spec).

manual_flight_log.jsonl only has {t, altitude_m, vx, vy, avg_throttle} --
no angle/fuel/stage telemetry (it's a straight-up altitude-hold test log,
not a full instrumented ascent). Missing fields are filled with
documented, clearly-labeled placeholders derived from real numbers where
possible (angle_deg from atan2(vx,vy)) and conservative constants where
not (fuel_remaining_pct, torque) -- this is a deliberate adaptation,
logged in BUILD_LOG.md, not silently assumed to be real telemetry.

Run: uv run python3 hackathon/optionA/test_checkpoint1.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsai_client import SystemOneClient
from menus import MENUS, THROTTLE_DELTA, TURN_AXIS_DELTA
from state_builder import build_state, build_feasibility, build_prediction_block, NOTE

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "manual_flight_log.jsonl")

# Representative mass/isp/torque, pulled from the real
# analysis/sfs_probe_forwardstartinfo_hackathon_firing.json snapshot
# (this project's actual hackathon test craft) -- not invented numbers.
CRAFT_MASS_T = 12.4
CRAFT_DRY_MASS_T = 6.0
CRAFT_ISP = 260.0
CRAFT_TORQUE_EFFECTIVE_RAW = 850.0

MISSION_TARGET = {"apoapsis_m": 100000, "periapsis_m": 90000}
VALID_CHOICES = {
    "throttle_action": set(THROTTLE_DELTA) | {"insufficient_data"},
    "pitch_action": set(TURN_AXIS_DELTA) | {"insufficient_data"},
    "stage_check": {"stage_now", "hold_stage", "insufficient_data"},
}


def load_sample_ticks(n=4):
    ticks = []
    with open(LOG_PATH) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "tick":
                ticks.append(d)
    # Spread samples across the recorded flight (early/low-speed through
    # late/high-speed) rather than clustering near t=0.
    if len(ticks) < n:
        return ticks
    step = len(ticks) // n
    return [ticks[i * step] for i in range(n)]


def tick_to_state(tick: dict, cycle_id: int) -> dict:
    vx, vy = tick["vx"], tick["vy"]
    speed = math.hypot(vx, vy)
    # angle_deg: real quantity derivable from real vx/vy (velocity heading);
    # this log has no independent attitude channel, so heading is used as
    # a stand-in for vehicle angle -- reasonable for a near-vertical/
    # gravity-turn ascent where attitude tracks the velocity vector.
    angle_deg = math.degrees(math.atan2(vx, vy)) if speed > 0.5 else 90.0

    vehicle = {
        "altitude_m": tick["altitude_m"],
        "vertical_speed_mps": vy,
        "horizontal_speed_mps": vx,
        "angle_deg": angle_deg,
        "angular_rate_dps": 0.0,  # not recorded in this log -- documented placeholder
        "throttle": tick["avg_throttle"],
        "active_stage": 0,
        "fuel_remaining_pct": 55.0,  # documented placeholder, not recorded in this log
    }
    feasibility = build_feasibility(
        current_mass_t=CRAFT_MASS_T, dry_mass_t=CRAFT_DRY_MASS_T, isp=CRAFT_ISP,
        torque_effective_raw=CRAFT_TORQUE_EFFECTIVE_RAW,
        delta_v_required_for_target_mps=1550.0,
    )
    prediction = build_prediction_block(None, horizon_s=15.0)
    return build_state(cycle_id, tick["t"], "ASCENT_GRAVITY_TURN", MISSION_TARGET,
                        vehicle, feasibility, prediction)


def main():
    client = SystemOneClient()
    ticks = load_sample_ticks(4)
    assert ticks, f"no ticks loaded from {LOG_PATH}"

    all_sane = True
    for i, tick in enumerate(ticks):
        state = tick_to_state(tick, cycle_id=i)
        result = client.ask(state, MENUS)
        print(f"\n--- sample {i} (t={tick['t']:.1f}s, alt={tick['altitude_m']:.1f}m) ---")
        if not result["ok"]:
            print(f"  CLIENT ERROR: {result['error']}")
            all_sane = False
            continue
        if result["stale"]:
            print(f"  WARNING: stale response (latency={result['latency_s']:.2f}s)")

        answers = result["answers"].get("answers", {})
        for qname in MENUS:
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

    print("\n=== Checkpoint 1 exit check:", "PASS" if all_sane else "FAIL", "===")
    return 0 if all_sane else 1


if __name__ == "__main__":
    sys.exit(main())
