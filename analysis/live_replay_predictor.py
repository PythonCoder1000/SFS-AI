"""
live_replay_predictor.py -- visually replays forward_sim.py's PREDICTED
rotation (and the real recorded throttle input) onto the live rocket in
SFS, tick by tick, via repeated 'setrot' + 'throttle' commands sent
straight over sfsprobe's own file-based command protocol (same
command.txt/result.txt pair sfsprobe_mcp uses -- see that module's own
top-of-file docstring). Built so Christian can WATCH what the predictor
thinks is happening, rather than only reading rotation_error_deg numbers
out of test_against_run_trajectory.

Why this exists: test_against_run_trajectory (2026-09-07 curving-flight
validation) found the predictor oscillating between ~0 deg and ~180 deg
error repeatedly over a real 10s active-turning window -- a genuinely
different failure signature from the smooth divergence seen on the
earlier straight-up validation. Staring at a table of numbers doesn't
make it obvious WHY the model swings that way; watching the predicted
rotation play out on the actual craft might.

--------------------------------------------------------------------
IMPORTANT REAL CONSTRAINT -- read before picking --visual_dt
--------------------------------------------------------------------
The mod's own PollCommands() only checks command.txt every 0.5s real
time (ProbeRunner.Update() in SFSProbe.cs -- see sfsprobe_mcp/server.py's
own comment on STALE_LOG_THRESHOLD_S for the same fact). command.txt is
OVERWRITTEN on each write, not queued -- so sending updates faster than
~0.5s apart just means some writes get silently clobbered before the mod
ever reads them, not a smoother replay. Default --visual_dt is 0.5s for
exactly this reason; going lower doesn't buy you anything without a mod
change, and going lower is NOT flagged as an error here (a caller may
still want to try), but a warning is printed once if --visual_dt < 0.4.

--------------------------------------------------------------------
WHAT THIS DOES AND DOES NOT DO
--------------------------------------------------------------------
- DOES send 'setrot <predicted_theta_deg>' every --visual_dt real
  seconds (scaled by --realtime_scale), snapping the live rocket's
  rb2d.rotation to match forward_sim.py's prediction for that instant.
  'setrot' is a hard instant snap (confirmed via light_search) and
  ZEROES rb2d.angularVelocity every time it's called -- so the visual
  result is a series of discrete snaps, not smooth motion. This is a
  deliberate, accepted characteristic of this tool (a debug
  visualization), not a bug to fix.
- DOES send 'throttle <value>' alongside each setrot, from the SAME
  real recorded control input (--throttle_field, e.g. 'throttleOut')
  the analysis run used -- so the engine/gimbal visuals look like the
  real flight while rotation shows what the MODEL predicted, letting
  you compare "what really happened, throttle-wise" against "what the
  model thinks rotation was doing" side by side.
- Does NOT touch position -- the rocket is not teleported. This is a
  rotation/throttle-only visualization, on whatever rocket is currently
  loaded (per Christian's session: keep the rocket on the pad or
  wherever you want to watch it spin).
- Does NOT send 'master on' or 'ignite' unless --master_on / --ignite
  are explicitly passed -- this tool never assumes it's safe to start
  an engine on your behalf.

Usage (dry run first, always -- prints the full command plan without
touching the game):
    python3 live_replay_predictor.py --flight ... --craft_config ...
        --aoa_table ... --start_t 46.0543401115 --duration 10.0040437263
        --dry_run

Then for real:
    python3 live_replay_predictor.py --flight ... --craft_config ...
        --aoa_table ... --start_t 46.0543401115 --duration 10.0040437263
        --live
"""

import argparse
import bisect
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import forward_sim as fsim  # noqa: E402
import sfs_telemetry as st  # noqa: E402

DEFAULT_MOD_DIR = (
    "~/Library/Application Support/Steam/steamapps/common/"
    "Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe"
)


class ProbeConn:
    """Minimal standalone reimplementation of sfsprobe_mcp/server.py's
    send_command/send_command_batch primitives -- deliberately NOT
    importing server.py itself (that module boots a full FastMCP server
    as an import-time side effect via `mcp = FastMCP(...)`, wrong for a
    plain repeatable CLI script). Same protocol, same file paths, same
    env var (SFSPROBE_MOD_DIR) for consistency with every other tool in
    this project."""

    def __init__(self, mod_dir: Path):
        self.mod_dir = mod_dir
        self.cmd_file = mod_dir / "command.txt"
        self.result_file = mod_dir / "result.txt"
        if not self.mod_dir.is_dir():
            raise FileNotFoundError(f"sfsprobe mod folder not found at: {mod_dir}")

    def send_batch(self, commands: list[str], timeout_s: float = 2.0,
                    poll_interval_s: float = 0.05) -> tuple[str, float, bool]:
        """Writes all commands as one command.txt (one game tick, per
        the mod's own multi-line PollCommands support), waits up to
        timeout_s for result.txt to grow. Non-fatal on timeout (returns
        completed=False) -- a single missed visual tick during playback
        shouldn't abort the whole replay, unlike a one-shot analysis
        command where a timeout really does mean something's wrong."""
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


def build_plan(flight_jsonl_path: str, craft_config_path: str, aoa_table_path: str,
                start_t: float, duration_s: float, dt: float, visual_dt: float,
                throttle_field: str, body_name: str, integrator: str) -> list[dict]:
    """Runs the SAME _prepare_replay() forward_sim.py's own
    test_against_run_trajectory uses (so this visualization is
    guaranteed to match whatever number Christian already saw from that
    tool, not a second, subtly-different reimplementation), then
    resamples the resulting predicted trajectory down to one entry per
    --visual_dt, pairing each with the REAL recorded throttle input at
    that same instant (separately built via load_control_schedule, same
    t0_abs convention _prepare_replay uses internally).

    Returns a list of {"visual_t", "theta_deg", "throttle"} dicts, one
    per real command that will be sent during playback."""
    rows = st.load_samples(Path(flight_jsonl_path))
    if not rows:
        raise ValueError(f"no samples found in {flight_jsonl_path}")
    t0 = rows[0]["t"]

    aoa_table = json.loads(Path(aoa_table_path).read_text())
    craft_config = fsim.load_craft_config_from_getforwardstartinfo(craft_config_path)
    aoa_table = fsim.build_position_independent_aoa_table(
        aoa_table, craft_config["com_local"], craft_config["rotation_deg"])

    # Same starting-state construction _prepare_replay does internally
    # (central-difference velocity around start_t) -- duplicated here
    # rather than calling the private _prepare_replay directly, so this
    # script doesn't silently break if that function's internal
    # signature changes; the actual math is copied verbatim.
    def to_state(r):
        return {"px": r["location.position.x"], "py": r["location.position.y"],
                "m": r["rb2d.mass"], "rot": r["rb2d.rotation"], "angv": r["rb2d.angularVelocity"]}

    start_idx = min(range(len(rows)), key=lambda i: abs(rows[i]["t"] - t0 - start_t))
    if start_idx == 0 or start_idx == len(rows) - 1:
        raise ValueError(f"start_t={start_t} too close to the flight's own start/end")
    r0, r1 = rows[start_idx - 1], rows[start_idx + 1]
    dt_v = r1["t"] - r0["t"]
    if dt_v <= 0:
        raise ValueError("degenerate dt around start_idx -- check for a revert/discontinuity here")
    start_state = to_state(rows[start_idx])
    start_state["vx"] = (r1["location.position.x"] - r0["location.position.x"]) / dt_v
    start_state["vy"] = (r1["location.position.y"] - r0["location.position.y"]) / dt_v

    control_schedule = fsim.load_control_schedule(
        flight_jsonl_path, t0_abs=t0 + start_t, throttle_field=throttle_field)

    sim = fsim.forward_simulate(
        start_state, duration_s, dt=dt, body_name=body_name, aoa_table=aoa_table,
        inertia=craft_config["inertia"], com_local=craft_config["com_local"],
        torque_effective=craft_config["torque_effective"], craft_config=craft_config,
        control_schedule=control_schedule, integrator=integrator)

    sim_times = [p["t"] for p in sim]
    plan = []
    n_visual = int(duration_s / visual_dt) + 1
    last_throttle = 0.0
    for i in range(n_visual):
        visual_t = round(i * visual_dt, 4)
        idx = bisect.bisect_left(sim_times, visual_t)
        idx = min(idx, len(sim) - 1)
        theta_deg = sim[idx]["theta_deg"]
        throttle = control_schedule.throttle(visual_t)
        if throttle is None:
            throttle = last_throttle  # hold last known real value, not a silent 0.0
        else:
            last_throttle = throttle
        plan.append({"visual_t": visual_t, "theta_deg": theta_deg, "throttle": throttle})
    return plan


def run_plan(plan: list[dict], conn: "ProbeConn | None", realtime_scale: float,
             visual_dt: float, master_on: bool, ignite: bool, dry_run: bool) -> None:
    if dry_run or conn is None:
        print("DRY RUN -- no commands sent. Plan:")
        for step in plan:
            print(f"  t={step['visual_t']:6.2f}s  setrot {step['theta_deg']:8.3f}   "
                  f"throttle {step['throttle']:.3f}")
        print(f"\n{len(plan)} ticks, {visual_dt}s apart "
              f"({visual_dt / max(realtime_scale, 1e-9):.3f}s real time apart at "
              f"realtime_scale={realtime_scale}).")
        return

    if master_on:
        resp, _, ok = conn.send_batch(["master on"])
        print(f"master on -> {resp!r} (ok={ok})")
    if ignite:
        resp, _, ok = conn.send_batch(["ignite"])
        print(f"ignite -> {resp!r} (ok={ok})")

    sleep_s = visual_dt / max(realtime_scale, 1e-9)
    print(f"Playing back {len(plan)} ticks, {sleep_s:.3f}s real time apart "
          f"(visual_dt={visual_dt}s, realtime_scale={realtime_scale})...")
    t_wall_start = time.monotonic()
    for i, step in enumerate(plan):
        commands = [f"setrot {step['theta_deg']:.4f}", f"throttle {step['throttle']:.4f}"]
        resp, elapsed, ok = conn.send_batch(commands, timeout_s=min(sleep_s * 0.9, 2.0))
        status = "ok" if ok else "NO ACK (mod busy/behind? continuing anyway)"
        print(f"[{i+1}/{len(plan)}] t={step['visual_t']:6.2f}s  "
              f"rot={step['theta_deg']:8.3f}deg  throttle={step['throttle']:.3f}  "
              f"({status}, {elapsed:.3f}s)")
        # Sleep the REMAINDER of this tick's real-time budget, accounting
        # for however long send_batch's own wait already took -- keeps
        # playback close to real-time-scaled instead of drifting slower
        # by accumulating every tick's ack-wait on top of a full sleep.
        target_wall = t_wall_start + (i + 1) * sleep_s
        remaining = target_wall - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
    print("Playback complete.")


def main():
    p = argparse.ArgumentParser(
        description="Visually replay forward_sim.py's predicted rotation + real "
                    "recorded throttle onto the live rocket via repeated setrot/throttle.")
    p.add_argument("--flight", required=True, metavar="PATH",
                    help="compat-renamed flight jsonl (must have output_TurnAxisTorque / "
                         "output_DirectionalAxis.x/y / location.position.x/y / rb2d.* keys)")
    p.add_argument("--craft_config", required=True, metavar="PATH",
                    help="sfs_probe_forwardstartinfo.json")
    p.add_argument("--aoa_table", required=True, metavar="PATH",
                    help="converted bins-format AoA table (aoa_dragarea.py format)")
    p.add_argument("--start_t", type=float, required=True)
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--dt", type=float, default=1.0 / 60.0,
                    help="underlying RK4 sim step, seconds (default matches game tick rate)")
    p.add_argument("--visual_dt", type=float, default=0.5,
                    help="real-world seconds between setrot sends (default 0.5s -- see "
                         "module docstring: the mod only polls command.txt every 0.5s, "
                         "so lower values mostly get clobbered before being read)")
    p.add_argument("--realtime_scale", type=float, default=1.0,
                    help="1.0 = real time, 0.25 = 4x slower (easier to watch), "
                         "2.0 = 2x faster")
    p.add_argument("--throttle_field", default="throttleOut",
                    help="flat telemetry key for real recorded throttle (see "
                         "convert_flight_compat_keys.py -- default matches its output)")
    p.add_argument("--body", default="Earth")
    p.add_argument("--integrator", default="rk4", choices=["rk4", "symplectic_euler"])
    p.add_argument("--mod_dir", default=DEFAULT_MOD_DIR)
    p.add_argument("--master_on", action="store_true",
                    help="send 'master on' once before playback starts")
    p.add_argument("--ignite", action="store_true",
                    help="send 'ignite' once before playback starts")
    p.add_argument("--live", action="store_true",
                    help="actually send commands to the game. Without this (or with "
                         "--dry_run), only prints the plan.")
    p.add_argument("--dry_run", action="store_true", help="explicit alias for the default "
                    "(no --live) behavior -- prints the plan, sends nothing")
    args = p.parse_args()

    if args.visual_dt < 0.4:
        print(f"WARNING: --visual_dt={args.visual_dt}s is below the mod's own ~0.5s "
              "command.txt poll interval -- many ticks will likely be silently "
              "clobbered before the mod ever reads them. Proceeding anyway.",
              file=sys.stderr)

    plan = build_plan(args.flight, args.craft_config, args.aoa_table, args.start_t,
                       args.duration, args.dt, args.visual_dt, args.throttle_field,
                       args.body, args.integrator)

    conn = None
    if args.live and not args.dry_run:
        conn = ProbeConn(Path(args.mod_dir).expanduser())

    run_plan(plan, conn, args.realtime_scale, args.visual_dt, args.master_on,
              args.ignite, dry_run=not (args.live and not args.dry_run))


if __name__ == "__main__":
    main()
