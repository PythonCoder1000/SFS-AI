"""
agent_interface.py -- the predict/act/observe boundary between the
physics-validated foundation (forward_sim.py + sfsprobe) and the actual
reasoning/decision-making AI loop.

2026-09-11: built as hackathon PREP, deliberately NOT the AI itself.
No decision logic lives here -- no "if divergence > X then correct",
no goal-seeking, no self-correction judgment. That loop is meant to be
built fresh at the event (see the compliance discussion this session --
"you're only evaluated on hackathon work"); this file is the clean API
surface it will sit on, so none of that 48 hours goes to wiring plumbing
instead of the actual judged loop.

Three functions, each doing ONE thing:
    observe()  -- current real craft state, as a clean dict
    act(cmd)   -- send a safety-clamped command to the live game
    predict()  -- forward-simulate a hypothetical control sequence

Run standalone (python3 agent_interface.py) for a quick self-test against
whatever craft is currently loaded in the live game.
"""
import os
import sys
import time
import json
import math
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forward_sim as fsim
from sfsprobe_tcp_client import SfsProbeTcpClient

MOD_DIR = Path(os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/"
    "Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe"
))
CMD_FILE = MOD_DIR / "command.txt"
RESULT_FILE = MOD_DIR / "result.txt"
SNAPSHOT_FILE = MOD_DIR / "sfs_probe_telemetry_snapshot.json"


def _send_command(command: str, timeout_s: float = 5.0, poll_s: float = 0.01) -> str:
    """Low-level file-protocol send/receive -- same protocol
    sfsprobe/probe_cmd.py uses (command.txt/result.txt polling), just
    importable here instead of only callable as a subprocess, since a
    standalone AI loop needs this as a library call, not a CLI script.
    See that file's own docstring for why polling result.txt beats a
    fixed sleep.

    2026-09-13 LATER SAME DAY: poll_s lowered from 0.1 (Christian's
    explicit request, chasing the pilot loop's achieved-Hz bottleneck).
    Measured live: at poll_s=0.1, observe()/act() round-trips were a
    suspiciously uniform ~0.105s every time (10 calls, 0.103-0.106s) --
    too tight a spread to be real game/IPC jitter, and almost exactly
    poll_s itself. The mod's own PollCommands() checks command.txt every
    0.05s (ProbeRunner.Update(), sfsprobe/SFSProbe.cs), so our old 0.1s
    poll interval was the dominant term, not the mod or the game.
    Confirmed by direct A/B: poll_s=0.01 measured ~0.055s mean round-trip
    (8 calls, 0.046-0.063s) -- roughly half, and now in line with the
    mod's own ~0.025s average detection latency (half its 0.05s poll
    period) plus real overhead. Not pushed lower than 0.01 -- the mod's
    own poll cadence is now the likely floor without a C#-side change,
    and busy-waiting much tighter than that mostly burns CPU for no
    further real gain. A genuine floor below this needs a real socket
    protocol replacing this file-polling IPC entirely (see the separate
    tcp-rewrite branch/effort for that -- deliberately NOT attempted
    here, kept as a small, low-risk, easily-revertable change on its
    own)."""
    if not RESULT_FILE.exists():
        RESULT_FILE.touch()
    start_size = RESULT_FILE.stat().st_size
    if CMD_FILE.exists():
        CMD_FILE.unlink()
    CMD_FILE.write_text(command + "\n")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cur_size = RESULT_FILE.stat().st_size
        if cur_size > start_size:
            with open(RESULT_FILE, "r") as f:
                f.seek(start_size)
                return f.read().strip()
        time.sleep(poll_s)
    raise TimeoutError(
        f"no response to {command!r} after {timeout_s}s -- game may not be "
        "running, mod not loaded, or no active rocket for a rocket-scoped command"
    )


# 2026-09-13 tcp-rewrite checkpoint 4: TCP-backed transport, opt-in only.
# File-protocol (_send_command above) remains the default for every
# caller -- this exists so observe()/act() can be told to use the
# persistent-socket path instead, behind an explicit use_tcp=True, until
# Christian decides to flip the default (see TCP_REWRITE_LOG.md). One
# shared client instance, lazily connected on first use.
_tcp_client: Optional[SfsProbeTcpClient] = None


def _get_tcp_client() -> SfsProbeTcpClient:
    global _tcp_client
    if _tcp_client is None:
        _tcp_client = SfsProbeTcpClient()
    return _tcp_client


def _send_command_tcp(command: str) -> str:
    """TCP-path equivalent of _send_command() -- same return contract
    (a stripped result string), transport only. Checkpoint 2/3 already
    validated the client itself; this just routes through it."""
    return _get_tcp_client().send(command)


# ---------------------------------------------------------------------------
# observe()
# ---------------------------------------------------------------------------

# Fixed, agent-useful field list -- deliberately small (every-loop-
# iteration read, not a full telemetry dump). Reach for a specific
# sfsprobe command directly (dragarea, rocket_summary, etc.) for
# anything not covered here.
OBSERVE_FIELDS = (
    "location.position.x,location.position.y,"
    "location.velocity.x,location.velocity.y,"
    "rb2d.rotation,rb2d.angularVelocity,rb2d.mass,"
    "h,thr,thrOn,computed:engines"
)


def observe(extra_fields: Optional[str] = None, *, use_tcp: bool = False) -> dict:
    """Current real craft state, as a clean dict -- wraps
    telemetrysnapshot with a fixed field list instead of every caller
    re-deriving one. Pass extra_fields (comma-separated, same syntax
    telemetrysnapshot itself takes) to add fields beyond
    OBSERVE_FIELDS' default set without losing them.

    use_tcp=True sends the telemetrysnapshot command over the
    tcp-rewrite persistent socket (see sfsprobe_tcp_client.py) instead
    of the file-protocol command.txt/result.txt round trip -- default
    stays False (file protocol) until Checkpoint 4's live validation
    passes and Christian decides to flip it. Either way, the snapshot
    itself is still written by the mod to SNAPSHOT_FILE and read from
    there -- only the command/result transport changes."""
    fields = OBSERVE_FIELDS if extra_fields is None else OBSERVE_FIELDS + "," + extra_fields
    sender = _send_command_tcp if use_tcp else _send_command
    sender(f"telemetrysnapshot {fields}")
    with open(SNAPSHOT_FILE, "r") as f:
        return json.load(f)


def observe_to_state(snapshot: dict) -> dict:
    """Converts an observe() snapshot into the {px,py,vx,vy,m,rot,angv}
    shape predict()/forward_simulate() need. A thin adapter, not a
    second source of truth -- keeps the field-name translation in ONE
    place instead of every caller having to know both shapes."""
    return {
        "px": snapshot.get("location.position.x", 0.0),
        "py": snapshot.get("location.position.y", 0.0),
        "vx": snapshot.get("location.velocity.x", 0.0),
        "vy": snapshot.get("location.velocity.y", 0.0),
        "m": snapshot.get("rb2d.mass", 0.0),
        "rot": snapshot.get("rb2d.rotation", 0.0),
        "angv": snapshot.get("rb2d.angularVelocity", 0.0),
    }


# ---------------------------------------------------------------------------
# act()
# ---------------------------------------------------------------------------

# 2026-09-11: today's live-testing crashed a real rocket TWICE -- once at
# throttle=1/turn=1 (full authority, no ramp), once at throttle=0.3 with
# the same full turn=1 (still enough to tip a 279t craft at low
# altitude/speed, where aero + gravity torque dominate and there's little
# margin to recover). These limits are a DIRECT response to that, not a
# guess -- see bookkeeping/active_state.md's "Live-verification incident"
# note for the full story.
MAX_TURN_AXIS_MAGNITUDE = 0.5
MAX_THROTTLE_STEP = 0.3  # max |change| in one act() call vs the last commanded value
_last_throttle = {"value": 0.0}


def act(command: str, *, allow_full_authority: bool = False, use_tcp: bool = False) -> str:
    """Sends ONE command to the live game -- by default through the same
    file protocol sfsprobe/probe_cmd.py uses, or over the tcp-rewrite
    persistent socket when use_tcp=True (default False; file protocol
    stays the default transport until Christian flips it, per
    TCP_REWRITE_LOG.md Checkpoint 4). Either transport applies the same
    safety clamps below to the two command types that actually crashed a
    real rocket today: 'turn <axis>' and 'throttle <amount>'. Every
    other command passes through unmodified -- this is not a
    general-purpose command validator, just a guard on the two specific
    failure modes already observed live.

    allow_full_authority=True bypasses both clamps for a single call --
    escape hatch for deliberate full-authority testing, not the
    default. Use it deliberately, not out of impatience -- see the
    incident note above for what happens without it."""
    parts = command.strip().split()
    if not allow_full_authority and len(parts) == 2:
        verb, arg = parts[0].lower(), parts[1]
        if verb == "turn":
            try:
                v = float(arg)
            except ValueError:
                v = None
            if v is not None:
                clamped = max(-MAX_TURN_AXIS_MAGNITUDE, min(MAX_TURN_AXIS_MAGNITUDE, v))
                if clamped != v:
                    command = f"turn {clamped}"
        elif verb == "throttle":
            try:
                v = float(arg)
            except ValueError:
                v = None
            if v is not None:
                prev = _last_throttle["value"]
                delta = max(-MAX_THROTTLE_STEP, min(MAX_THROTTLE_STEP, v - prev))
                clamped = prev + delta
                if clamped != v:
                    command = f"throttle {clamped}"
                _last_throttle["value"] = clamped
    return _send_command_tcp(command) if use_tcp else _send_command(command)


# ---------------------------------------------------------------------------
# predict()
# ---------------------------------------------------------------------------

def predict(state: dict, waypoints: Optional[list] = None, duration_s: float = 10.0,
            dt: float = 0.25, craft_config: Optional[dict] = None,
            aoa_table: Optional[dict] = None, body_name: str = "Earth",
            default_throttle: Optional[float] = None,
            default_turn_axis: float = 0.0,
            default_directional_axis: tuple = (0.0, 0.0),
            flags: Optional[dict] = None) -> dict:
    """Forward-simulates duration_s seconds from `state` under a
    HYPOTHETICAL control plan (waypoints), NOT a replay of a real
    flight -- see HypotheticalControlSchedule's own docstring in
    forward_sim.py. This is the "if I did X, what happens?" call the
    AI loop needs; test_against_run/test_against_run_trajectory remain
    the "did the physics match a REAL flight" validation tools,
    unchanged, not replaced by this.

    state: the same shape observe_to_state() produces -- px, py, vx,
    vy, m required; rot/angv default to 0.0 if absent.

    Regime-aware by default (2026-09-09/11 findings, see
    bookkeeping/active_state.md's "important correction" note): auto-
    ENABLES the AoA=0 torque gate whenever the starting height is
    inside the atmosphere (h < 30000m, matching this project's own
    "atmosphere ends ~30km" observation on this craft) -- the ungated
    behavior was confirmed to flip a real craft 175 degrees in the
    first simulated second. Pass flags={'aero_torque_aoa_gate_deg':
    None} explicitly to override.

    Returns {"trajectory": [...], "final": {...}, "confidence": str,
    "collided": bool, "in_atmosphere": bool}. confidence is a rough
    regime label ("high"/"low"), grounded in this project's own
    measured accuracy, NOT a calibrated per-call number (that
    calibration is its own separate TODO):
      - "high": vacuum (any maneuver -- turns confirmed ~0.001%), OR
        atmosphere with NO turning requested (confirmed ~0.05% at
        20-34s, gate on).
      - "low": atmosphere WITH turning requested anywhere in the plan
        -- this project's own 2026-09-09 decision deprioritized this
        regime as an inherent feedback-loop instability, not a solved
        problem. Don't trust a "low" prediction for planning; it's
        exactly the regime the AI's real-time correction loop exists
        to handle instead of prediction.
    """
    body = fsim.PLANET_CONSTANTS[body_name]
    h0 = math.hypot(state["px"], state["py"]) - body["radius_m"]
    in_atmosphere = h0 < 30000.0

    resolved_flags = dict(flags) if flags else {}
    if in_atmosphere and "aero_torque_aoa_gate_deg" not in resolved_flags:
        resolved_flags["aero_torque_aoa_gate_deg"] = 2.0

    schedule = fsim.HypotheticalControlSchedule(
        waypoints or [],
        default_throttle=default_throttle,
        default_turn_axis=default_turn_axis,
        default_directional_axis=default_directional_axis,
    )

    # 2026-09-12 fix: forward_simulate() takes inertia/com_local as
    # SEPARATE top-level kwargs -- it does not read them out of
    # craft_config itself. Omitting them silently zeroed all rotational
    # and aerodynamic-torque dynamics on every predict() call (the
    # aero_torque_aoa_gate_deg flag set above had nothing to gate).
    # load_craft_config_from_getforwardstartinfo() already puts both
    # keys in craft_config, so this is just wiring them through.
    inertia = (craft_config or {}).get("inertia")
    com_local = (craft_config or {}).get("com_local")

    trajectory = fsim.forward_simulate(
        state, duration_s, dt=dt, body_name=body_name,
        aoa_table=aoa_table, craft_config=craft_config,
        inertia=inertia, com_local=com_local,
        control_schedule=schedule, flags=resolved_flags,
    )

    final = trajectory[-1]
    collided = bool(final.get("collided"))

    has_turn = (default_turn_axis != 0.0) or any(
        w.get("turn_axis", 0.0) != 0.0 for w in (waypoints or [])
    )
    if not in_atmosphere:
        confidence = "high"
    elif has_turn:
        confidence = "low"
    else:
        confidence = "high"

    return {
        "trajectory": trajectory, "final": final, "confidence": confidence,
        "collided": collided, "in_atmosphere": in_atmosphere,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("observe() ->")
    snap = observe()
    print(json.dumps(snap, indent=2)[:800])
    state = observe_to_state(snap)
    print("\nobserve_to_state() ->", state)

    print("\npredict() -- 5s no-input coast from the observed state ->")
    result = predict(state, waypoints=[], duration_s=5.0)
    print(f"  confidence={result['confidence']} in_atmosphere={result['in_atmosphere']} "
          f"collided={result['collided']}")
    print(f"  final: h={result['final'].get('h')} v={result['final'].get('v')}")
