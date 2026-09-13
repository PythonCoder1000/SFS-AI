"""
test_checkpoint2.py -- Checkpoint 2 exit condition: feed the gate a
deliberately low-confidence AND a deliberately infeasible synthetic
answer, confirm both are rejected with a logged, typed reason (not
silently passed).

Run: uv run python3 hackathon/optionA/test_checkpoint2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guardrail import evaluate, confidence_gate

BASE_STATE = {
    "vehicle": {"angular_rate_dps": 0.0, "fuel_remaining_pct": 60.0},
    "feasibility": {
        "delta_v_remaining_mps": 1800.0,
        "delta_v_required_for_target_mps": 1550.0,
        "max_angular_accel_dps2": 12.4,
    },
}


def case_low_confidence():
    """throttle_action, choice clears the menu but confidence is well
    below the 0.5 reject_below floor for a routine question -- must be
    rejected on confidence alone, before feasibility is even consulted."""
    answer = {"choice": "increase_large", "confidence": 0.31,
              "probabilities": {"increase_large": 0.31}}
    result = evaluate("throttle_action", answer, BASE_STATE)
    ok = (not result.accepted) and result.band == "reject" and result.reason is not None
    print(f"[low confidence] accepted={result.accepted} band={result.band} "
          f"reason={result.reason!r}")
    print("  ->", "PASS" if ok else "FAIL")
    return ok


def case_infeasible_high_confidence():
    """stage_check, HIGH confidence (0.95, clears the 0.9 irreversible
    floor) but physically infeasible: current stage has plenty of fuel
    and delta-v margin, so stage_now is a mistake regardless of how
    confident tsAI is -- feasibility must catch it, not confidence."""
    infeasible_state = {
        "vehicle": {"angular_rate_dps": 0.0, "fuel_remaining_pct": 80.0},
        "feasibility": {
            "delta_v_remaining_mps": 3000.0,       # plenty remaining
            "delta_v_required_for_target_mps": 1550.0,
            "max_angular_accel_dps2": 12.4,
        },
    }
    answer = {"choice": "stage_now", "confidence": 0.95,
              "probabilities": {"stage_now": 0.95}}
    result = evaluate("stage_check", answer, infeasible_state)
    ok = (not result.accepted) and result.reason is not None and "stage_now" in result.reason
    print(f"\n[infeasible, high confidence] accepted={result.accepted} "
          f"band={result.band} reason={result.reason!r}")
    print("  ->", "PASS" if ok else "FAIL")
    return ok


def case_sanity_accept():
    """Control case: a reasonable, feasible, high-confidence answer
    should be accepted cleanly -- confirms the gate isn't just
    rejecting everything."""
    answer = {"choice": "hold", "confidence": 0.9,
              "probabilities": {"hold": 0.9}}
    result = evaluate("throttle_action", answer, BASE_STATE)
    ok = result.accepted and result.band == "normal"
    print(f"\n[sanity: feasible+confident] accepted={result.accepted} "
          f"band={result.band}")
    print("  ->", "PASS" if ok else "FAIL")
    return ok


def main():
    results = [case_low_confidence(), case_infeasible_high_confidence(), case_sanity_accept()]
    all_pass = all(results)
    print("\n=== Checkpoint 2 exit check:", "PASS" if all_pass else "FAIL", "===")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
