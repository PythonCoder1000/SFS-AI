#!/usr/bin/env python3
"""
demo_flight_2026-09-11.py -- vertical, no-steering ascent test for
"lock a demo-safe craft + flight envelope" (hackathon prep item #4).

REVISED 2026-09-11 after two live failures: the first version used
blanket 'ignite' (arms EVERY engine across ALL stages at once). On
this STACKED multi-stage rocket that fires the upper-stage engine
(Titan/Valiant) directly into the still-attached lower-stage tanks
before any separation happens -- destroyed the craft both times
(partCount collapsing 27 -> 7 -> 6 -> 4 within ~1-2s of full throttle).
Root-caused by Christian watching a repeat live. See
sfsprobe/mod_changelog.md's v0.68.0 entry.

FIX: use 'stage <index>' to activate ONE stage's engines at a time,
in order, exactly like a real staged launch -- never blanket 'ignite'
on a craft with engines stacked above/below other engines.

Purpose unchanged: does this rocket reach vacuum on a straight up,
zero-turn ascent -- the exact envelope forward_sim.py has actually
validated (atmospheric coast with the AoA gate on, into vacuum coast).
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_interface as ai

TELEMETRY_FIELDS = (
    "t,location.position.x,location.position.y,"
    "location.velocity.x,location.velocity.y,"
    "rb2d.rotation,rb2d.angularVelocity,rb2d.mass,h,thr,thrOn,fdt,"
    "outputTurnAxisTorque,directionalAxisX,directionalAxisY,dragArea,"
    "aeroTorque,aeroAlphaDeg,comX,comY,copAppliedX,copAppliedY,"
    "partCount,hasControl,isOnSurface,engines"
)

TARGET_ALTITUDE_M = 35000.0
MAX_DURATION_S = 150.0
POLL_INTERVAL_S = 2.0
MASS_FLAT_EPS = 0.01
NUM_STAGES = 3  # from 'stages': index 0, 1, 2


def main():
    print(f"[{time.strftime('%H:%M:%S')}] Starting telemetry recording...")
    print(ai._send_command(f"telemetry on {TELEMETRY_FIELDS}"))

    time.sleep(0.5)
    print(f"[{time.strftime('%H:%M:%S')}] Ramping throttle to full BEFORE any stage fires "
          f"(engines not yet armed, so throttle_Out stays 0 until stage 0 activates them)...")
    for _ in range(4):
        result = ai.act("throttle 1")
        print(f"  {result}")
        time.sleep(0.3)

    print(f"[{time.strftime('%H:%M:%S')}] master on...")
    print(ai.act("master on", allow_full_authority=True))

    print(f"[{time.strftime('%H:%M:%S')}] Firing stage 0 (first-stage engines ONLY)...")
    print(ai.act("stage 0", allow_full_authority=True))

    print(f"[{time.strftime('%H:%M:%S')}] Ascending, monitoring (no turn input at any point)...")
    start = time.time()
    last_mass = None
    stage_idx = 0
    reached_target = False
    while time.time() - start < MAX_DURATION_S:
        snap = ai.observe()
        h = snap.get("h")
        m = snap.get("rb2d.mass")
        vy = snap.get("location.velocity.y")
        pc = snap.get("partCount")
        elapsed = time.time() - start
        print(f"  t={elapsed:5.1f}s  h={h}  m={m}  vy={vy}  partCount={pc}")

        if h is not None and h > TARGET_ALTITUDE_M:
            print(f"[{time.strftime('%H:%M:%S')}] Reached target altitude ({h:.0f}m).")
            reached_target = True
            break

        if m is not None and last_mass is not None and abs(m - last_mass) < MASS_FLAT_EPS:
            if stage_idx + 1 < NUM_STAGES:
                stage_idx += 1
                print(f"[{time.strftime('%H:%M:%S')}] Mass flat -- current stage exhausted, "
                      f"firing stage {stage_idx}...")
                print(ai.act(f"stage {stage_idx}", allow_full_authority=True))
                last_mass = None  # reset so the NEW stage's own burn isn't misread as flat immediately
                time.sleep(POLL_INTERVAL_S)
                continue
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Mass flat and no stages left -- stopping.")
                break
        last_mass = m

        time.sleep(POLL_INTERVAL_S)

    print(f"[{time.strftime('%H:%M:%S')}] Cutting throttle...")
    print(ai.act("throttle 0", allow_full_authority=True))

    print(f"[{time.strftime('%H:%M:%S')}] Stopping telemetry recording...")
    print(ai._send_command("telemetry off"))

    print(f"\n{'REACHED TARGET' if reached_target else 'DID NOT REACH TARGET (see log above for why)'}")


if __name__ == "__main__":
    main()
