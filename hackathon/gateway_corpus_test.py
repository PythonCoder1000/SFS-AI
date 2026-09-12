"""Checkpoint D -- valid-but-unusual action corpus (spec sec 9).

"Pre-demo: build a small corpus of valid-but-unusual actions the
gateway must correctly admit -- catches over-refusal (a guardrail that
blocks legitimate maneuvers costs the mission, not safety, but it'll
cost the demo too)."

Every case here is something a real supervisor might legitimately
propose, that a naively-strict gateway could plausibly reject by
accident. Uses the REAL predict()/CFG/AOA from controller.py, not
fakes -- the whole point is testing against the actual physics model
this gateway will run against live, not a mock that can't produce a
false rejection even if the real check logic has a bug.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from controller import CFG, AOA, EARTH_RADIUS_M  # noqa: E402
from agent_interface import predict  # noqa: E402
from gateway import GuardrailGateway, StagingGate  # noqa: E402
from supervisor import Correction  # noqa: E402


def _state(altitude_m: float, vspeed_mps: float, mass_t: float = 90.0) -> dict:
    return {"px": 0.0, "py": EARTH_RADIUS_M + altitude_m, "vx": 0.0, "vy": vspeed_mps,
            "m": mass_t, "rot": 0.0, "angv": 0.0}


CASES = [
    # (label, correction, expected_stage, state, should_accept)
    (
        "full throttle boundary value (1.0) during genuine underperformance",
        Correction(no_change=False, reason_code="predicted_underspeed", target_throttle=1.0, commit_ms=2000),
        0, _state(3000.0, 80.0),
        True,
    ),
    (
        "zero throttle boundary value (0.0) -- legitimate cutback near target",
        Correction(no_change=False, reason_code="predicted_overspeed", target_throttle=0.0, commit_ms=2000),
        0, _state(19500.0, 30.0),
        True,
    ),
    (
        "large throttle swing (0.2 -> 0.9) responding to a genuine sharp underperformance",
        Correction(no_change=False, reason_code="predicted_underspeed", target_throttle=0.9, commit_ms=3000),
        0, _state(8000.0, 50.0),
        True,
    ),
    (
        "very short commit_ms (aggressive, fast-reconsider correction)",
        Correction(no_change=False, reason_code="predicted_overspeed", target_throttle=0.4, commit_ms=200),
        0, _state(10000.0, 200.0),
        True,
    ),
    (
        "very long commit_ms (deliberately patient correction)",
        Correction(no_change=False, reason_code="predicted_underspeed", target_throttle=0.6, commit_ms=15000),
        0, _state(5000.0, 100.0),
        True,
    ),
    (
        "legitimate stage_request exactly matching expected_stage, alone",
        Correction(no_change=False, reason_code="stage_ready", target_throttle=0.5,
                    stage_request=1, commit_ms=1000),
        1, _state(12000.0, 150.0),
        True,
    ),
    (
        "combined action: throttle change AND legitimate stage_request in one correction",
        Correction(no_change=False, reason_code="stage_and_throttle_adjust", target_throttle=0.7,
                    stage_request=2, commit_ms=1000),
        2, _state(15000.0, 180.0),
        True,
    ),
    (
        "no_change with an unusual/verbose reason_code string",
        Correction(no_change=True, reason_code="residual_within_normal_bounds_for_this_flight_phase"),
        0, _state(6000.0, 90.0),
        True,
    ),
    (
        "throttle held at current value (no real change, but not flagged no_change)",
        Correction(no_change=False, reason_code="confirm_hold", target_throttle=0.5, commit_ms=1000),
        0, _state(9000.0, 100.0),
        True,
    ),
    (
        "high altitude, near-target, small conservative correction",
        Correction(no_change=False, reason_code="fine_tune_approach", target_throttle=0.15, commit_ms=1000),
        0, _state(19800.0, 10.0),
        True,
    ),
]


if __name__ == "__main__":
    print(f"=== Valid-but-unusual action corpus -- {len(CASES)} cases ===\n")
    gateway = GuardrailGateway(staging_gate=StagingGate(debounce_s=0.0))  # debounce off -- each case is independent
    failures = []

    for i, (label, correction, expected_stage, state, should_accept) in enumerate(CASES):
        decision = gateway.evaluate(
            correction, expected_stage=expected_stage, now_s=float(i) * 100.0,  # spread out, avoid debounce coupling
            current_state=state, craft_config=CFG, aoa_table=AOA, predict_fn=predict,
        )
        ok = decision.accepted == should_accept
        marker = "OK" if ok else "FAIL"
        print(f"[{marker}] {label}")
        print(f"       -> accepted={decision.accepted} cause={decision.cause} detail={decision.detail!r}")
        if not ok:
            failures.append(label)

    print()
    if failures:
        print(f"{len(failures)}/{len(CASES)} FAILED (over-refusal on legitimate actions):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"All {len(CASES)} valid-but-unusual actions correctly admitted -- no over-refusal.")
