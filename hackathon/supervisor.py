"""Checkpoint C -- LLM supervisor call (spec sec 5 + sec 7).

Builds the state summary schema, calls Claude with a typed/schema-
enforced tool (never a raw string or raw sfsprobe command), warm-
started with the current plan + why a replan was triggered, verify-
first (keeping the current plan is a normal, expected answer). Hard
timeout with a deterministic fallback on miss or malformed output --
the loop must survive a bad LLM response, not just a good one.

Nothing here calls act() directly -- this module only ever returns a
typed Correction (or None on timeout/failure/no-change). Wiring a
returned Correction into actual throttle/turn commands, and vetting it
first, is the guardrail gateway's job (Checkpoint D) -- deliberately
not built yet, so don't be tempted to have this module call act().
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

import anthropic

MODEL = "claude-sonnet-4-6"
DEFAULT_TIMEOUT_S = 1.2  # spec sec 7: ~0.8-1.5s starting value

# ---------------------------------------------------------------------------
# State summary (spec sec 5) -- trimmed to what this project's controller
# actually has. Cut order if ever short on fields to compute (spec's own
# priority): recent_decisions beyond 1 entry -> derived.* beyond
# actuator_saturation -> anomaly_flags. NEVER cut prediction_residual or
# causal_category -- those are the self-correction signal the demo rests on.
# ---------------------------------------------------------------------------

def build_state_summary(
    *,
    cycle_id: int,
    phase: str,
    altitude_m: float,
    vertical_speed_mps: float,
    throttle: float,
    active_stage: int,
    target_altitude_m: float,
    plan_issued_at_cycle: int,
    prediction_confidence: str,
    prediction_horizon_s: float,
    predicted_terminal_altitude_error_m: float,
    predicted_terminal_speed_error_mps: float,
    position_error_m: float,
    speed_error_mps: float,
    residual_trend: str,
    residual_slope: float,
    triggered_replan: bool,
    causal_category: str,
    time_in_phase_s: float,
    time_since_last_replan_s: float,
    actuator_saturated: bool,
    recent_decisions: Optional[list] = None,
) -> dict:
    """Assembles the sec-5 schema. Straight-up-ascent-specific
    simplification: no turn axis / waypoint concept yet (this
    controller only ever commands throttle), so angle fields read 0/
    None rather than being fabricated."""
    return {
        "cycle_id": cycle_id,
        "phase": phase,
        "vehicle": {
            "altitude_m": round(altitude_m, 1),
            "vertical_speed_mps": round(vertical_speed_mps, 1),
            "angle_deg": 0.0,  # straight-up ascent only, no turn axis modeled yet
            "throttle": round(throttle, 2),
            "active_stage": active_stage,
        },
        "current_plan": {
            "type": "altitude_target",
            "target_altitude_m": target_altitude_m,
            "issued_at_cycle": plan_issued_at_cycle,
        },
        "goal_error": {
            "altitude_error_m": round(target_altitude_m - altitude_m, 1),
        },
        "prediction": {
            "confidence": prediction_confidence,
            "horizon_s": prediction_horizon_s,
            "terminal_error": {
                "altitude_m": round(predicted_terminal_altitude_error_m, 1),
                "speed_mps": round(predicted_terminal_speed_error_mps, 1),
            },
        },
        "prediction_residual": {
            "position_error_m": round(position_error_m, 1),
            "speed_error_mps": round(speed_error_mps, 1),
            "trend": residual_trend,
            "residual_slope": round(residual_slope, 2),
            "triggered_replan": triggered_replan,
            "causal_category": causal_category,
        },
        "derived": {
            "time_in_phase_s": round(time_in_phase_s, 1),
            "time_since_last_replan_s": round(time_since_last_replan_s, 1),
            "actuator_saturation": actuator_saturated,
        },
        "anomaly_flags": [],
        "recent_decisions": (recent_decisions or [])[-1:],  # cut to 1 entry, per spec's own cut order
    }


# ---------------------------------------------------------------------------
# Typed output (spec sec 7) -- schema-enforced via a forced tool call,
# never a raw string. no_change is this project's own explicit addition
# to the spec's example schema: "keep current plan" needs an unambiguous
# signal, not "happened to propose the same numbers."
# ---------------------------------------------------------------------------

SUPERVISOR_TOOL = {
    "name": "propose_correction",
    "description": (
        "Propose a correction to the current flight plan, or explicitly "
        "keep the current plan unchanged. Keeping the current plan is a "
        "normal, expected response -- not a failure to act. Only propose "
        "a change when the residual and its causal_category genuinely "
        "call for one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "no_change": {
                "type": "boolean",
                "description": "true = keep the current plan exactly as-is. When true, the other fields are ignored.",
            },
            "target_throttle": {
                "type": "number", "minimum": 0.0, "maximum": 1.0,
                "description": "Desired throttle 0-1. Only meaningful when no_change is false.",
            },
            "reason_code": {
                "type": "string",
                "description": "Short machine-readable reason, e.g. 'predicted_underspeed', 'predicted_overspeed', 'keep_current_plan'.",
            },
            "commit_ms": {
                "type": "integer",
                "description": "How long (ms) this correction should be held before the next replan check is allowed to reconsider it.",
            },
        },
        "required": ["no_change", "reason_code"],
    },
}

SYSTEM_PROMPT = """You are the supervisor layer for a deterministic rocket flight controller in Spaceflight Simulator. You are called ONLY when a lower-level, deterministic gate has already decided a replan check is warranted -- you are not polling continuously, and being called does not itself mean something is wrong.

You will be shown the current flight state, the current plan, and a causal_category that was computed deterministically BEFORE this call -- localization of the error is not your job, it has already been done. Your job is to decide whether the current plan still makes sense given that residual and its cause, and either confirm it (no_change: true) or propose a specific new target_throttle.

Keeping the current plan is a normal, common, and often CORRECT answer -- treat it as the default unless the residual and causal_category genuinely justify a change. Do not propose a change just because you were called.

You MUST respond by calling the propose_correction tool. Never respond with plain text."""


@dataclass
class Correction:
    no_change: bool
    reason_code: str
    target_throttle: Optional[float] = None
    commit_ms: Optional[int] = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _build_prompt(state_summary: dict, warm_start_reason: str) -> str:
    """Warm-started: includes the current plan + WHY this call is
    happening, not just raw state (spec sec 7 -- non-warm-started
    replanning was found to collapse in several test conditions in the
    literature this project's plan cites)."""
    return (
        f"Replan check triggered. Reason: {warm_start_reason}\n\n"
        f"Current plan: {json.dumps(state_summary['current_plan'])}\n\n"
        f"Full state summary:\n{json.dumps(state_summary, indent=2)}"
    )


def call_supervisor(
    state_summary: dict,
    warm_start_reason: str,
    api_key: Optional[str] = None,
    model: str = MODEL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Optional[Correction]:
    """Returns a Correction, or None on timeout/error/malformed output --
    None means "fall back to the deterministic layer", never raises out
    to the caller. This function's whole job is to make sure a bad LLM
    response can never break the flight loop."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None  # no key configured -- fail safe to deterministic layer

    client = anthropic.Anthropic(api_key=key, timeout=timeout_s)
    t0 = time.monotonic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(state_summary, warm_start_reason)}],
            tools=[SUPERVISOR_TOOL],
            tool_choice={"type": "tool", "name": "propose_correction"},
        )
    except Exception as e:  # noqa: BLE001 -- deliberately broad: timeout, network,
        # rate limit, API error, whatever -- ALL of them mean "fall back",
        # none of them should propagate and break the flight loop.
        latency_ms = (time.monotonic() - t0) * 1000
        print(f"  [supervisor] call failed ({type(e).__name__}: {e}) after {latency_ms:.0f}ms -- falling back")
        return None

    latency_ms = (time.monotonic() - t0) * 1000

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        print(f"  [supervisor] no tool_use block in response after {latency_ms:.0f}ms -- falling back")
        return None

    try:
        return _validate_and_build(tool_use.input, latency_ms)
    except (KeyError, TypeError, ValueError) as e:
        print(f"  [supervisor] malformed tool input ({e}) after {latency_ms:.0f}ms -- falling back")
        return None


def _validate_and_build(raw: dict, latency_ms: float) -> Correction:
    """Strict validation -- anything out of range or the wrong type
    raises, which call_supervisor() catches and turns into a safe
    fallback. This is deliberately paranoid: a malformed or
    wrong-direction LLM response must never reach act()."""
    if not isinstance(raw, dict):
        raise TypeError(f"tool input is not a dict: {type(raw)}")

    no_change = raw["no_change"]
    if not isinstance(no_change, bool):
        raise TypeError(f"no_change must be bool, got {type(no_change)}")

    reason_code = raw.get("reason_code", "")
    if not isinstance(reason_code, str) or not reason_code:
        raise ValueError("reason_code must be a non-empty string")

    if no_change:
        return Correction(no_change=True, reason_code=reason_code, latency_ms=latency_ms)

    throttle = raw.get("target_throttle")
    if throttle is None:
        raise ValueError("target_throttle required when no_change is false")
    throttle = float(throttle)
    if not (0.0 <= throttle <= 1.0):
        raise ValueError(f"target_throttle out of range: {throttle}")

    commit_ms = raw.get("commit_ms")
    if commit_ms is not None:
        commit_ms = int(commit_ms)
        if commit_ms < 0:
            raise ValueError(f"commit_ms negative: {commit_ms}")

    return Correction(
        no_change=False, reason_code=reason_code,
        target_throttle=throttle, commit_ms=commit_ms, latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Offline tests -- no API key or live game needed for the validation path
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== _validate_and_build survives malformed input ===")
    bad_inputs = [
        {},  # missing required fields
        {"no_change": "yes"},  # wrong type
        {"no_change": False},  # missing target_throttle
        {"no_change": False, "target_throttle": 5.0, "reason_code": "x"},  # out of range
        {"no_change": False, "target_throttle": -0.5, "reason_code": "x"},  # out of range
        {"no_change": False, "target_throttle": 0.5, "reason_code": ""},  # empty reason
        {"no_change": False, "target_throttle": "half", "reason_code": "x"},  # wrong type
        "not even a dict",
        None,
    ]
    for bad in bad_inputs:
        try:
            _validate_and_build(bad, latency_ms=0.0)
            print(f"  FAIL -- should have raised for {bad!r}")
        except (KeyError, TypeError, ValueError) as e:
            print(f"  OK -- correctly rejected {bad!r} ({type(e).__name__}: {e})")

    print("\n=== _validate_and_build accepts good input ===")
    good_inputs = [
        {"no_change": True, "reason_code": "keep_current_plan"},
        {"no_change": False, "target_throttle": 0.85, "reason_code": "predicted_underspeed", "commit_ms": 700},
    ]
    for good in good_inputs:
        c = _validate_and_build(good, latency_ms=123.4)
        print(f"  OK -- {c}")

    print("\n=== call_supervisor with no API key (should fail safe to None) ===")
    dummy_summary = build_state_summary(
        cycle_id=1, phase="ASCENT", altitude_m=5000.0, vertical_speed_mps=200.0,
        throttle=0.5, active_stage=0, target_altitude_m=20000.0, plan_issued_at_cycle=0,
        prediction_confidence="high", prediction_horizon_s=5.0,
        predicted_terminal_altitude_error_m=300.0, predicted_terminal_speed_error_mps=50.0,
        position_error_m=300.0, speed_error_mps=50.0, residual_trend="growing",
        residual_slope=10.0, triggered_replan=True, causal_category="underperformance",
        time_in_phase_s=20.0, time_since_last_replan_s=999.0, actuator_saturated=False,
    )
    result = call_supervisor(dummy_summary, "residual_threshold", api_key="")
    print(f"  result: {result}  (expected None -- no key)")
    assert result is None, "expected None with no API key"
    print("  OK")
