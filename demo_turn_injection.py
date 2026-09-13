"""
demo_turn_injection.py -- automated "disable AI, knock it off course,
re-enable" demo. Launches pilot_loop.py as a real child process, watches
altitude itself (agent_interface.observe(), same as pilot_loop.py's own
telemetry path), and at the target injection altitude:
  1. SIGSTOPs the pilot_loop.py process (freezes tsAI control -- the
     game keeps running, craft keeps flying under whatever was last
     commanded).
  2. Sends 'setrot <deg>' directly to the game, bypassing pilot_loop.py
     entirely -- an INSTANT attitude snap (writes rb2d.rotation and
     zeroes rb2d.angularVelocity in one call), so the resulting
     deviation is exact and deterministic, unlike a 'turn' rate burst
     whose final angle depends on timing/latency.
  3. SIGCONTs pilot_loop.py -- it resumes, observes the real (now
     perturbed) state on its next cycle, and (if it's working) corrects
     it back via pitch_action, same as any other real deviation. tsAI
     is never told an injection happened -- it just sees real telemetry.

Usage: uv run python3 demo_turn_injection.py [--apoapsis-m 10000]
       [--inject-at-m 2000] [--set-rot-deg 45]
"""
import argparse
import math
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "analysis"))
import agent_interface as ai  # noqa: E402
import forward_sim as fsim  # noqa: E402


def log(msg: str) -> None:
    print(f"[demo] {msg}", flush=True)


def get_altitude() -> float:
    snap = ai.observe(use_tcp=True)
    px = snap.get("location.position.x", 0.0)
    py = snap.get("location.position.y", 0.0)
    r = math.hypot(px, py)
    body = fsim.PLANET_CONSTANTS["Earth"]
    return r - body["radius_m"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apoapsis-m", type=float, default=7000.0)
    parser.add_argument("--inject-at-m", type=float, default=2000.0)
    parser.add_argument("--set-rot-deg", type=float, default=45.0,
                         help="Absolute rotation (degrees) to snap the craft to via "
                              "the 'setrot' command -- an instant, precise attitude "
                              "set (zeroes angular velocity too), unlike a 'turn' "
                              "burst which is a rate command with an unpredictable "
                              "final angle.")
    parser.add_argument("--pilot-log", default=os.path.join(HERE, "demo_flight.log"))
    args = parser.parse_args()

    # Launch the venv's real python3 directly (not `uv run`, which
    # wraps it in an extra process -- SIGSTOP/SIGCONT need to target
    # the actual pilot_loop.py interpreter, not a wrapper).
    venv_python = os.path.join(HERE, ".venv", "bin", "python3")
    pilot_script = os.path.join(HERE, "hackathon", "optionA", "pilot_loop.py")
    log_f = open(args.pilot_log, "w")
    child = subprocess.Popen(
        [venv_python, pilot_script, "--mode", "live",
         "--apoapsis-m", str(args.apoapsis_m)],
        stdout=log_f, stderr=subprocess.STDOUT, cwd=HERE,
    )
    log(f"launched pilot_loop.py (pid={child.pid}), target apoapsis={args.apoapsis_m}m, "
        f"log -> {args.pilot_log}")

    injected = False
    last_print = 0.0
    while not injected:
        if child.poll() is not None:
            log(f"pilot_loop.py exited early (code={child.returncode}) before injection -- aborting")
            return
        try:
            alt = get_altitude()
        except Exception as e:  # noqa: BLE001 -- transient telemetry read failure, keep polling
            time.sleep(0.2)
            continue
        now = time.time()
        if now - last_print > 1.0:
            log(f"altitude={alt:.0f}m (waiting for {args.inject_at_m:.0f}m)")
            last_print = now
        if alt >= args.inject_at_m:
            log(f"altitude={alt:.0f}m >= inject threshold -- PAUSING tsAI (SIGSTOP pid={child.pid})")
            os.kill(child.pid, signal.SIGSTOP)
            log(f"sending raw 'setrot {args.set_rot_deg}' directly to the game "
                f"(instant snap, tsAI is frozen, doesn't see this)")
            ai.act(f"setrot {args.set_rot_deg}", use_tcp=True)
            # rb2d.rotation is already degrees (Unity Rigidbody2D convention,
            # confirmed live) -- no math.degrees() here.
            rot_after = ai.observe(use_tcp=True).get("rb2d.rotation", 0.0)
            log(f"injection done, rotation now ~{rot_after:.1f}deg -- RESUMING tsAI (SIGCONT pid={child.pid})")
            os.kill(child.pid, signal.SIGCONT)
            injected = True
        time.sleep(0.15)

    log("waiting for pilot_loop.py to finish the flight...")
    child.wait()
    log(f"pilot_loop.py exited (code={child.returncode}) -- see {args.pilot_log} for the full cycle log")


if __name__ == "__main__":
    main()
