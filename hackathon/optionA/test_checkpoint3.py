"""
test_checkpoint3.py -- Checkpoint 3 exit condition: simulate a dropped
response and a duplicate response in isolation (mocked, no live game).
Confirm: dropped -> hold-then-degrade correctly; duplicate -> stage does
not double-fire.

Run: uv run python3 hackathon/optionA/test_checkpoint3.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from watchdog import Watchdog, StagingTracker


def case_dropped_response_hold_then_degrade():
    wd = Watchdog(degrade_after=2)
    wd.record_hit(throttle_choice="increase_small", pitch_choice="hold")

    # Cycle N+1: response dropped (simulated timeout).
    wd.record_miss()
    outcome1 = wd.resolve(safe_hold_throttle_choice="hold", safe_hold_pitch_choice="hold")
    check1 = (outcome1.held_from_last and not outcome1.degraded and
              outcome1.throttle_choice == "increase_small" and outcome1.pitch_choice == "hold")
    print(f"[miss 1] {outcome1} -> {'PASS' if check1 else 'FAIL'}")

    # Cycle N+2: STILL dropped -- second consecutive miss -> degrade.
    wd.record_miss()
    outcome2 = wd.resolve(safe_hold_throttle_choice="hold", safe_hold_pitch_choice="hold")
    check2 = (outcome2.degraded and not outcome2.held_from_last and
              outcome2.throttle_choice == "hold" and outcome2.pitch_choice == "hold")
    print(f"[miss 2] {outcome2} -> {'PASS' if check2 else 'FAIL'}")

    # Recovery: a hit resets the streak.
    wd.record_hit(throttle_choice="increase_small", pitch_choice="prograde_small")
    check3 = wd.miss_count == 0
    print(f"[recovery] miss_count={wd.miss_count} -> {'PASS' if check3 else 'FAIL'}")

    return check1 and check2 and check3


def case_duplicate_stage_no_double_fire():
    tracker = StagingTracker()
    commands_sent = []

    def maybe_send_stage(stage_index):
        if tracker.should_fire(stage_index):
            commands_sent.append(f"stage {stage_index}")

    # First, genuine stage_now response for stage 0.
    maybe_send_stage(0)
    # A retried/duplicate call, or a stale response replayed after the
    # real one already landed, targeting the SAME stage index.
    maybe_send_stage(0)
    maybe_send_stage(0)

    check1 = commands_sent == ["stage 0"]
    print(f"\n[duplicate same-stage] commands_sent={commands_sent} -> "
          f"{'PASS' if check1 else 'FAIL'}")

    # A genuinely NEW stage event (vehicle progressed to stage 1) must
    # still be allowed to fire once.
    maybe_send_stage(1)
    check2 = commands_sent == ["stage 0", "stage 1"]
    print(f"[new stage after old] commands_sent={commands_sent} -> "
          f"{'PASS' if check2 else 'FAIL'}")

    return check1 and check2


def main():
    r1 = case_dropped_response_hold_then_degrade()
    r2 = case_duplicate_stage_no_double_fire()
    all_pass = r1 and r2
    print("\n=== Checkpoint 3 exit check:", "PASS" if all_pass else "FAIL", "===")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
