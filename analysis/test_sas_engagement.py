"""
test_sas_engagement.py -- direct live test of H1 (SAS auto-engages once
manual turnAxis drops to 0, producing real torque our replay was
missing because it only ever recorded raw arrowkeys.turnAxis, not the
resolved output_TurnAxisTorque). See python_changelog.md's H1 entry and
the follow-up hypothesis-table discussion for full context.

Confirmed IL gate (sfs_source_reference.md B1.3, GetTurnAxis):
    if arrowkeys.turnAxis != 0: return arrowkeys.turnAxis   # manual wins
    if useStopRotation && hasControl && !IsOnSurface:
        return SAS's own computed value
    return 0

So this test: get the craft airborne (IsOnSurface must be false for SAS
to be even eligible), induce real spin with a turn burst, release, then
poll hasControl / IsOnSurface / output_TurnAxisTorque / rb2d.angularVelocity
directly (bypassing the wrong turnAxis-as-output_TurnAxisTorque mapping
entirely) to see whether the real game applies real correcting torque
once the stick is let go.
"""

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


def poll_state(conn: ProbeConn, snapshot_path: Path, label: str):
    resp, elapsed, ok = conn.send_batch(
        ["telemetrysnapshot hasControl,IsOnSurface,output_TurnAxisTorque,rb2d.angularVelocity"],
        timeout_s=2.0)
    if not ok:
        print(f"  [{label}] NO ACK")
        return None
    import json
    data = json.loads(snapshot_path.read_text())
    print(f"  [{label}] hasControl={data.get('hasControl')} IsOnSurface={data.get('IsOnSurface')} "
          f"output_TurnAxisTorque={data.get('output_TurnAxisTorque')} "
          f"angv={data.get('rb2d.angularVelocity'):.4f}")
    return data


def main():
    mod_dir = Path(DEFAULT_MOD_DIR).expanduser()
    snapshot_path = mod_dir / "sfs_probe_telemetry_snapshot.json"
    conn = ProbeConn(mod_dir)

    print("Igniting, full throttle, getting airborne...")
    conn.send_batch(["throttle 1", "master on", "ignite"])
    time.sleep(2.0)  # give it a couple seconds to clear the pad

    poll_state(conn, snapshot_path, "after liftoff, pre-turn")

    print("\nApplying turn burst (turn 1) for 0.5s to induce real spin...")
    conn.send_batch(["turn 1"])
    time.sleep(0.5)

    poll_state(conn, snapshot_path, "mid-turn-burst")

    print("\nReleasing (turn 0) -- watching for SAS engagement...")
    conn.send_batch(["turn 0"])

    for i in range(10):
        time.sleep(0.3)
        poll_state(conn, snapshot_path, f"t+{(i+1)*0.3:.1f}s after release")

    print("\nDone. If output_TurnAxisTorque goes nonzero (opposing the sign of angv) "
          "while IsOnSurface=0, that's real SAS engagement -- confirms H1.")


if __name__ == "__main__":
    main()
