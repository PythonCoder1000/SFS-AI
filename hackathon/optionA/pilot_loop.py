"""
pilot_loop.py -- Checkpoint 4: the full loop, observe() -> enriched
state -> tsAI call -> guardrail -> act()/stage().

Two modes:
- live: drives the real game through analysis/agent_interface.py.
- replay: drives the same loop end-to-end against a recorded
  manual_flight_log.jsonl tick sequence instead (sec 7 Checkpoint 4's
  explicit documented fallback when a live session can't be reached).

Safety note (logged in BUILD_LOG.md Checkpoint 4 entry): in LIVE mode,
stage_check answers are still computed, confidence-gated, and
feasibility-checked exactly like the other two questions -- but the
resulting choice is only LOGGED, never sent to the game as a real
`stage <index>` command. This run's actual craft's stage-index mapping
was not independently re-verified before this unattended session, and
sec 1's own catalogued failure mode (misapplied staging destroys the
craft) is exactly the risk this project has no tolerance for running
unsupervised. throttle_action and pitch_action ARE sent live -- both
are continuous, reversible, and already hard-clamped by
agent_interface.act() independent of anything here.
"""
import argparse
import json
import os
import sys
import time
import math

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "analysis"))

import forward_sim as fsim  # noqa: E402
from tsai_client import SystemOneClient  # noqa: E402
from menus import MENUS, THROTTLE_DELTA, TURN_AXIS_DELTA  # noqa: E402
from guardrail import evaluate  # noqa: E402
from watchdog import Watchdog, StagingTracker  # noqa: E402
from state_builder import build_state, build_feasibility, build_prediction_block  # noqa: E402

SAFE_HOLD_THROTTLE_CHOICE = "hold"
SAFE_HOLD_PITCH_CHOICE = "hold"


def log(msg: str) -> None:
    print(f"[pilot_loop] {msg}", flush=True)


class PilotRun:
    def __init__(self, client: SystemOneClient, mission_target: dict,
                 craft_mass_t: float, craft_dry_mass_t: float, craft_isp: float,
                 max_cycles: int, cycle_period_s: float, live: bool):
        self.client = client
        self.mission_target = mission_target
        self.craft_mass_t = craft_mass_t
        self.craft_dry_mass_t = craft_dry_mass_t
        self.craft_isp = craft_isp
        self.max_cycles = max_cycles
        self.cycle_period_s = cycle_period_s
        self.live = live

        self.watchdog = Watchdog()
        self.staging_tracker = StagingTracker()
        self.current_throttle = 0.0
        self.rejections_logged = 0
        self.cycles_run = 0

    def _vehicle_from_snapshot(self, snapshot: dict, torque_effective_raw: float) -> dict:
        px = snapshot.get("location.position.x", 0.0)
        py = snapshot.get("location.position.y", 0.0)
        vx = snapshot.get("location.velocity.x", 0.0)
        vy = snapshot.get("location.velocity.y", 0.0)
        body = fsim.PLANET_CONSTANTS["Earth"]
        altitude_m = math.hypot(px, py) - body["radius_m"]
        rot_deg = math.degrees(snapshot.get("rb2d.rotation", 0.0))
        angv_dps = math.degrees(snapshot.get("rb2d.angularVelocity", 0.0))
        mass_t = snapshot.get("rb2d.mass", self.craft_mass_t)
        fuel_pct = max(0.0, min(100.0,
                                 100.0 * (mass_t - self.craft_dry_mass_t) /
                                 max(1e-6, self.craft_mass_t - self.craft_dry_mass_t)))
        return {
            "altitude_m": altitude_m,
            "vertical_speed_mps": vy,
            "horizontal_speed_mps": vx,
            "angle_deg": rot_deg,
            "angular_rate_dps": angv_dps,
            "throttle": self.current_throttle,
            "active_stage": 0,
            "fuel_remaining_pct": fuel_pct,
        }, mass_t

    def build_cycle_state(self, cycle_id: int, t: float, snapshot: dict,
                           torque_effective_raw: float) -> dict:
        vehicle, mass_t = self._vehicle_from_snapshot(snapshot, torque_effective_raw)
        feasibility = build_feasibility(
            current_mass_t=mass_t, dry_mass_t=self.craft_dry_mass_t, isp=self.craft_isp,
            torque_effective_raw=torque_effective_raw,
            delta_v_required_for_target_mps=self.mission_target.get(
                "delta_v_required_for_target_mps", 0.0),
        )
        prediction = build_prediction_block(None, horizon_s=15.0)
        # Phase must match the REAL state, not just always claim ascent --
        # a "PAD_IDLE" craft (throttle 0, negligible speed, low altitude)
        # mislabeled as mid-gravity-turn is exactly the kind of
        # note-sec-5-warns-about ambiguity that (correctly) drives tsAI's
        # confidence down and the guardrail rejects on. Found live during
        # this Checkpoint 4 run -- see BUILD_LOG.md.
        speed = math.hypot(vehicle["horizontal_speed_mps"], vehicle["vertical_speed_mps"])
        if vehicle["throttle"] <= 0.01 and speed < 5.0 and vehicle["altitude_m"] < 200.0:
            phase = "PAD_IDLE"
        else:
            phase = "ASCENT_GRAVITY_TURN"
        return build_state(cycle_id, t, phase, self.mission_target,
                            vehicle, feasibility, prediction)

    def run_cycle(self, cycle_id: int, snapshot: dict, torque_effective_raw: float,
                  act_fn) -> bool:
        """Returns True to keep flying, False to end the run (max cycles
        reached this call)."""
        t = snapshot.get("t", float(cycle_id))
        state = self.build_cycle_state(cycle_id, t, snapshot, torque_effective_raw)

        result = self.client.ask(state, MENUS)
        if not result["ok"] or result["stale"]:
            reason = result["error"] or f"stale response ({result['latency_s']:.2f}s)"
            log(f"cycle {cycle_id}: MISS ({reason})")
            self.watchdog.record_miss()
        else:
            answers = result["answers"].get("answers", {})
            gate_results = {}
            for qname in MENUS:
                ans = answers.get(qname)
                if ans is None:
                    gate_results[qname] = None
                    continue
                gate_results[qname] = evaluate(qname, ans, state)
                gr = gate_results[qname]
                log(f"cycle {cycle_id}: {qname} choice={ans.get('choice')!r} "
                    f"conf={ans.get('confidence')} -> "
                    f"{'ACCEPT' if gr.accepted else 'REJECT'} band={gr.band} "
                    f"reason={gr.reason}")
                if not gr.accepted:
                    self.rejections_logged += 1

            throttle_gate = gate_results.get("throttle_action")
            pitch_gate = gate_results.get("pitch_action")
            stage_gate = gate_results.get("stage_check")

            if throttle_gate and throttle_gate.accepted and pitch_gate and pitch_gate.accepted:
                throttle_choice = answers["throttle_action"]["choice"]
                pitch_choice = answers["pitch_action"]["choice"]
                self.watchdog.record_hit(throttle_choice, pitch_choice)
            else:
                # A rejection with no vetted substitute this cycle counts
                # as a miss (sec 6) -- there is no safe accepted answer
                # to act on, same as a dropped/stale response.
                log(f"cycle {cycle_id}: guardrail rejected the live answer -- treating as a miss")
                self.watchdog.record_miss()

            if stage_gate and stage_gate.accepted and answers.get("stage_check", {}).get("choice") == "stage_now":
                active_stage = state["vehicle"]["active_stage"]
                if self.staging_tracker.should_fire(active_stage):
                    log(f"cycle {cycle_id}: stage_now ACCEPTED for stage {active_stage} "
                        f"(NOT sent live -- see module docstring safety note)")
                else:
                    log(f"cycle {cycle_id}: stage_now for stage {active_stage} suppressed "
                        f"(already fired -- idempotency)")

        outcome = self.watchdog.resolve(SAFE_HOLD_THROTTLE_CHOICE, SAFE_HOLD_PITCH_CHOICE)
        throttle_choice = outcome.throttle_choice or SAFE_HOLD_THROTTLE_CHOICE
        pitch_choice = outcome.pitch_choice or SAFE_HOLD_PITCH_CHOICE

        throttle_delta = THROTTLE_DELTA.get(throttle_choice, 0.0)
        if throttle_choice == "cut":
            self.current_throttle = 0.0
        else:
            self.current_throttle = max(0.0, min(1.0, self.current_throttle + throttle_delta))
        turn_axis = TURN_AXIS_DELTA.get(pitch_choice, 0.0)

        tag = "DEGRADED-SAFE-HOLD" if outcome.degraded else (
            "HOLD-LAST" if outcome.held_from_last else "LIVE")
        log(f"cycle {cycle_id}: [{tag}] -> throttle={self.current_throttle:.2f} turn_axis={turn_axis:.2f}")

        act_fn(self.current_throttle, turn_axis)

        self.cycles_run += 1
        return self.cycles_run < self.max_cycles


def run_live(max_cycles: int, cycle_period_s: float, mission_target: dict) -> PilotRun:
    import agent_interface as ai

    resp = ai._send_command("getforwardstartinfo")
    log(f"getforwardstartinfo -> {resp}")
    with open(str(ai.MOD_DIR / "sfs_probe_forwardstartinfo.json")) as f:
        craft_raw = json.load(f)
    mass_t = craft_raw.get("mass", 100.0)
    total_thrust = sum(e.get("thrustTon", 0.0) for e in craft_raw.get("engines", []))
    isp = craft_raw.get("engines", [{}])[0].get("isp", 240.0) if craft_raw.get("engines") else 240.0
    torque_idle = craft_raw.get("torqueEffectiveRaw", 5.0)
    # Documented estimate, not measured: no independent dry-mass telemetry
    # channel exists for this craft. 65% of current (pre-ignition, full
    # tanks) mass as propellant is a generic-rocket ballpark, used ONLY to
    # give the delta-v feasibility check (sec 4.2) a non-zero budget to
    # reason about during this short dry run -- not a claim of measured
    # accuracy. See BUILD_LOG.md Checkpoint 4 entry.
    dry_mass_t = mass_t * 0.35
    log(f"live craft: mass={mass_t:.1f}t dry_est={dry_mass_t:.1f}t isp={isp:.0f} "
        f"total_thrust={total_thrust:.0f}t torque_idle={torque_idle}")

    run = PilotRun(SystemOneClient(), mission_target, mass_t, dry_mass_t, isp,
                   max_cycles, cycle_period_s, live=True)

    def act_fn(throttle, turn_axis):
        ai.act(f"throttle {throttle:.3f}")
        ai.act(f"turn {turn_axis:.3f}")

    cycle_id = 0
    try:
        while True:
            snapshot = ai.observe()
            angv_dps = abs(math.degrees(snapshot.get("rb2d.angularVelocity", 0.0)))
            if angv_dps > 500.0 or any(
                math.isnan(snapshot.get(k, 0.0)) for k in
                ("location.position.x", "location.position.y",
                 "location.velocity.x", "location.velocity.y", "rb2d.rotation")
            ):
                log(f"cycle {cycle_id}: SANITY ABORT (angv={angv_dps:.1f}dps or NaN telemetry) "
                    f"-- ending run immediately")
                break
            keep_going = run.run_cycle(cycle_id, snapshot, torque_idle, act_fn)
            cycle_id += 1
            if not keep_going:
                break
            time.sleep(cycle_period_s)
    finally:
        log("run ending -- commanding safe throttle-down/attitude-hold")
        ai.act("throttle 0.0", allow_full_authority=True)
        ai.act("turn 0.0", allow_full_authority=True)

    return run


def run_replay(log_path: str, max_cycles: int, mission_target: dict) -> PilotRun:
    ticks = []
    with open(log_path) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "tick":
                ticks.append(d)

    mass_t, dry_mass_t, isp, torque_idle = 12.4, 6.0, 260.0, 850.0
    run = PilotRun(SystemOneClient(), mission_target, mass_t, dry_mass_t, isp,
                   min(max_cycles, len(ticks)), cycle_period_s=0.0, live=False)

    body = fsim.PLANET_CONSTANTS["Earth"]

    def act_fn(throttle, turn_axis):
        log(f"  (replay -- would send: throttle {throttle:.3f}, turn {turn_axis:.3f})")

    step = max(1, len(ticks) // max_cycles)
    selected = ticks[::step][:max_cycles]
    for cycle_id, tick in enumerate(selected):
        snapshot = {
            "t": tick["t"],
            "location.position.x": 0.0,
            "location.position.y": body["radius_m"] + tick["altitude_m"],
            "location.velocity.x": tick["vx"],
            "location.velocity.y": tick["vy"],
            "rb2d.rotation": 0.0,
            "rb2d.angularVelocity": 0.0,
            "rb2d.mass": mass_t,
        }
        keep_going = run.run_cycle(cycle_id, snapshot, torque_idle, act_fn)
        if not keep_going:
            break

    log("replay ending -- final state was a controlled, logged safe-hold (no real act() sent)")
    return run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "replay"], default="live")
    parser.add_argument("--max-cycles", type=int, default=20)
    parser.add_argument("--cycle-period-s", type=float, default=1.0)
    parser.add_argument("--replay-log", default=os.path.join(HERE, "..", "manual_flight_log.jsonl"))
    args = parser.parse_args()

    mission_target = {"apoapsis_m": 5000, "periapsis_m": 0,
                       "delta_v_required_for_target_mps": 400.0}

    if args.mode == "live":
        run = run_live(args.max_cycles, args.cycle_period_s, mission_target)
    else:
        run = run_replay(args.replay_log, args.max_cycles, mission_target)

    log(f"DONE: cycles_run={run.cycles_run} guardrail_rejections={run.rejections_logged} "
        f"final_watchdog_miss_count={run.watchdog.miss_count}")
    if run.rejections_logged == 0:
        log("WARNING: no guardrail rejection occurred during this run -- "
            "spec Checkpoint 4 exit condition wants at least one to be visible.")


if __name__ == "__main__":
    main()
