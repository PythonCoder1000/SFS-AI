"""IPC latency measurement -- Checkpoint B open item.

Measures real observe()<->act() round-trip latency against the live
game (file-polling IPC under the hood, see agent_interface.py's own
docstring -- real, non-trivial latency, not a direct socket).

Run standalone with the game running and a rocket loaded:
    uv run python3 hackathon/measure_latency.py
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

from agent_interface import observe, act  # noqa: E402


def _timed(fn, *args, **kwargs) -> float:
    start = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - start) * 1000.0  # ms


def measure(n: int = 30) -> dict:
    """Runs n observe() calls and n act() no-op throttle-hold calls,
    reporting median/p95 for each separately -- they go through the
    same file-protocol round trip but are different commands, so
    latency isn't assumed identical without measuring both."""
    observe_ms = []
    act_ms = []

    print(f"Measuring observe() latency over {n} calls...")
    for _ in range(n):
        observe_ms.append(_timed(observe))

    print(f"Measuring act() latency over {n} calls (throttle hold)...")
    # Read current throttle first so this doesn't actually change thrust.
    snap = observe()
    current_throttle = snap.get("thr", 0.0)
    for _ in range(n):
        act_ms.append(_timed(act, f"throttle {current_throttle}"))

    def summarize(samples: list) -> dict:
        sorted_samples = sorted(samples)
        median = statistics.median(sorted_samples)
        p95_idx = min(len(sorted_samples) - 1, int(round(0.95 * (len(sorted_samples) - 1))))
        p95 = sorted_samples[p95_idx]
        return {"median_ms": round(median, 2), "p95_ms": round(p95, 2),
                "min_ms": round(sorted_samples[0], 2), "max_ms": round(sorted_samples[-1], 2)}

    results = {"observe": summarize(observe_ms), "act": summarize(act_ms), "n": n}
    return results


if __name__ == "__main__":
    results = measure()
    print("\nresults:")
    for key in ("observe", "act"):
        r = results[key]
        print(f"  {key}(): median={r['median_ms']}ms p95={r['p95_ms']}ms "
              f"min={r['min_ms']}ms max={r['max_ms']}ms")
