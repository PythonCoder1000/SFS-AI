"""Prediction-accuracy logger -- issues a predict() call at every loop
tick while a human flies manually, and logs predicted-vs-actual
comparisons to a JSONL file once each prediction's horizon elapses.

Pure observer: never calls act(). Safe to run alongside manual flight.

Usage:
    uv run python3 hackathon/predict_watch.py
    uv run python3 hackathon/predict_watch.py --horizon 3.0 --hz 5.0
    uv run python3 hackathon/predict_watch.py --out my_flight.jsonl

Output is JSONL, two record types (filter on "type" when analyzing):
  "tick"       -- one per loop iteration: raw telemetry snapshot.
  "comparison" -- one per resolved prediction: predicted vs actual,
                  with position_error_m / speed_error_mps.

Every tick issues a NEW prediction hypothesizing "hold current average
throttle, no further turn input, for `horizon` seconds" -- so at
steady state there are roughly horizon_s/dt predictions in flight at
once, each resolving in turn. This gives dense accuracy-over-time data
(does error grow with altitude? with speed? near the atmosphere
boundary?) rather than one sparse rolling comparison.
"""

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_interface import observe, observe_to_state, predict  # noqa: E402
from controller import CFG, AOA, EARTH_RADIUS_M  # noqa: E402  (reuses real craft config)
from residual import compute_residual  # noqa: E402


def run(
    horizon_s: float = 5.0,
    poll_hz: float = 5.0,
    out_path: str = None,
    max_duration_s: float = 600.0,
) -> str:
    if out_path is None:
        out_path = f"hackathon/predict_log_{int(time.time())}.jsonl"

    dt = 1.0 / poll_hz
    t_start = time.monotonic()
    deadline = t_start + max_duration_s
    pending = deque()  # {"issued_t","due_t","predicted_final","confidence","default_throttle"}

    print(f"Logging to {out_path}  (horizon={horizon_s}s, poll_hz={poll_hz}, "
          f"observer only -- no commands sent). Ctrl+C to stop.")

    n_ticks = 0
    n_comparisons = 0
    with open(out_path, "a") as f:
        try:
            while time.monotonic() < deadline:
                t_now = time.monotonic() - t_start
                snapshot = observe()
                state_now = observe_to_state(snapshot)
                engines = snapshot.get("engines", [])
                avg_throttle = (
                    sum(e.get("throttleOut", 0.0) for e in engines) / len(engines)
                    if engines else 0.0
                )
                r = (state_now["px"] ** 2 + state_now["py"] ** 2) ** 0.5
                altitude_m = r - EARTH_RADIUS_M

                # Resolve every prediction whose horizon has now elapsed
                while pending and t_now >= pending[0]["due_t"]:
                    p = pending.popleft()
                    res = compute_residual(p["predicted_final"], state_now)
                    f.write(json.dumps({
                        "type": "comparison",
                        "issued_t": round(p["issued_t"], 3),
                        "due_t": round(p["due_t"], 3),
                        "resolved_t": round(t_now, 3),
                        "horizon_s": horizon_s,
                        "confidence": p["confidence"],
                        "default_throttle_used": p["default_throttle"],
                        "predicted_final": {k: p["predicted_final"].get(k)
                                             for k in ("px", "py", "vx", "vy")},
                        "actual": {k: state_now.get(k) for k in ("px", "py", "vx", "vy")},
                        "position_error_m": res["position_error_m"],
                        "speed_error_mps": res["speed_error_mps"],
                    }) + "\n")
                    n_comparisons += 1

                f.write(json.dumps({
                    "type": "tick", "t": round(t_now, 3),
                    "altitude_m": altitude_m,
                    "vx": state_now["vx"], "vy": state_now["vy"],
                    "avg_throttle": avg_throttle,
                }) + "\n")
                f.flush()
                n_ticks += 1

                # Issue the next prediction: "hold current avg throttle,
                # no turn input, for horizon_s seconds"
                result = predict(
                    state_now, waypoints=[], duration_s=horizon_s,
                    craft_config=CFG, aoa_table=AOA, default_throttle=avg_throttle,
                )
                pending.append({
                    "issued_t": t_now, "due_t": t_now + horizon_s,
                    "predicted_final": result["final"], "confidence": result["confidence"],
                    "default_throttle": avg_throttle,
                })

                time.sleep(dt)
        except KeyboardInterrupt:
            print(f"\nStopped by user. {n_ticks} ticks, {n_comparisons} comparisons logged.")

    print(f"Done -- wrote {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=float, default=5.0, help="prediction horizon, seconds")
    parser.add_argument("--hz", type=float, default=5.0, help="loop rate")
    parser.add_argument("--out", type=str, default=None, help="output JSONL path")
    parser.add_argument("--max-duration", type=float, default=600.0, help="safety cutoff, seconds")
    args = parser.parse_args()
    run(horizon_s=args.horizon, poll_hz=args.hz, out_path=args.out, max_duration_s=args.max_duration)
