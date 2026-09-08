"""
poll_torque_during_burn.py -- ignites/throttles the loaded rocket and
polls computed:torque's torqueEffectiveLive at a fixed real-time
interval over a sustained burn, to test whether it holds constant once
firing starts or continues to drift (e.g. with time-since-ignition,
fuel remaining, or mass) -- the H1 follow-up this project's own
changelog flagged as untested (see analysis/python_changelog.md's
2026-09-07 H1 entry). Reuses the same raw command.txt/result.txt
protocol as live_replay_predictor.py's ProbeConn (not the MCP layer),
so this is a standalone, rerunnable diagnostic.

Usage:
    python3 poll_torque_during_burn.py [duration_s] [interval_s]
"""

import json
import sys
import time
from pathlib import Path

DEFAULT_MOD_DIR = (
    "~/Library/Application Support/Steam/steamapps/common/"
    "Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe"
)


class ProbeConn:
    def __init__(self, mod_dir: Path):
        self.mod_dir = mod_dir
        self.cmd_file = mod_dir / "command.txt"
        self.result_file = mod_dir / "result.txt"

    def send_batch(self, commands: list[str], timeout_s: float = 3.0,
                    poll_interval_s: float = 0.05) -> tuple[str, float, bool]:
        if not self.result_file.exists():
            self.result_file.touch()
        start_size = self.result_file.stat().st_size
        start = time.monotonic()
        try:
            self.cmd_file.unlink(missing_ok=True)
        except OSError:
            pass
        self.cmd_file.write_text("\n".join(commands) + "\n")
        deadline = start + timeout_s
        while time.monotonic() < deadline:
            cur_size = self.result_file.stat().st_size
            if cur_size > start_size:
                with self.result_file.open("r") as f:
                    f.seek(start_size)
                    text = f.read()
                return text.strip(), time.monotonic() - start, True
            time.sleep(poll_interval_s)
        return "", time.monotonic() - start, False


def main():
    duration_s = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    interval_s = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

    mod_dir = Path(DEFAULT_MOD_DIR).expanduser()
    snapshot_path = mod_dir / "sfs_probe_telemetry_snapshot.json"
    conn = ProbeConn(mod_dir)

    print("Igniting and setting full throttle...")
    resp, elapsed, ok = conn.send_batch(["throttle 1", "master on", "ignite"])
    print(f"  -> {resp!r} (ok={ok}, {elapsed:.3f}s)")

    print(f"\nPolling torqueEffectiveLive every {interval_s}s for {duration_s}s...")
    t_start = time.monotonic()
    results = []
    while time.monotonic() - t_start < duration_s:
        t_elapsed = time.monotonic() - t_start
        resp, elapsed, ok = conn.send_batch(
            ["telemetrysnapshot computed:torque,computed:engines,partCount"],
            timeout_s=2.0)
        if ok:
            data = json.loads(snapshot_path.read_text())
            torque = data.get("torqueEffectiveLive")
            engines = data.get("engines", [])
            throttle_out = engines[0].get("throttleOut") if engines else None
            part_count = data.get("partCount")
            results.append({
                "t_elapsed": round(t_elapsed, 2),
                "torqueEffectiveLive": torque,
                "throttleOut": throttle_out,
                "partCount": part_count,
            })
            print(f"  t={t_elapsed:5.2f}s  torqueEffectiveLive={torque}  "
                  f"throttleOut={throttle_out}  partCount={part_count}")
        else:
            print(f"  t={t_elapsed:5.2f}s  NO ACK, skipping this poll")
        # sleep the remainder of this interval, accounting for the poll's own time
        next_target = t_start + (len(results)) * interval_s
        remaining = next_target - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    print("\nSummary:")
    torques = [r["torqueEffectiveLive"] for r in results if r["torqueEffectiveLive"] is not None]
    if torques:
        print(f"  torqueEffectiveLive: min={min(torques)}  max={max(torques)}  "
              f"first={torques[0]}  last={torques[-1]}")
        if min(torques) == max(torques):
            print("  -> CONSTANT throughout the burn.")
        else:
            print("  -> VARIED during the burn -- not a fixed value.")
    else:
        print("  no successful polls")


if __name__ == "__main__":
    main()
