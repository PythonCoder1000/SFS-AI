"""
pilot_loop.py -- Checkpoint 4: the full loop, observe() -> enriched
state -> tsAI call -> guardrail -> act()/stage().

Two modes:
- live: drives the real game through analysis/agent_interface.py.
- replay: drives the same loop end-to-end against a recorded
  manual_flight_log.jsonl tick sequence instead (sec 7 Checkpoint 4's
  explicit documented fallback when a live session can't be reached).

Safety note -- UPDATED (Christian's explicit decision, 2026-09-12):
throttle_action/pitch_action are sent live as before (continuous,
reversible, hard-clamped by agent_interface.act()). Two more real
commands are now ALSO sent live, both previously log-only:
  (B) `master on` -- sent once, the first cycle an ACCEPTED
      (post-watchdog) throttle_choice resolves to `launch`. Idempotent
      via self.master_ignited. Safe/reversible -- rocket-wide
      throttleOn, independent of throttle amount and per-engine
      engineOn.
  (C) `stage <active_stage_index>` -- sent (i) when stage_check's answer
      is ACCEPTED as `stage_now`, or (ii) as part of the full liftoff
      sequence the first time `launch` fires (2026-09-13 addition --
      see below), gated in BOTH cases by StagingTracker's shared
      edge-triggered idempotency (fires at most once per stage index,
      regardless of which code path requests it).
      THIS REOPENS THE RISK THE ORIGINAL CHECKPOINT 4 CUT EXISTED TO
      AVOID: this craft's stage-index mapping was not independently
      re-verified, and sec 1's catalogued failure mode (misapplied
      staging destroys the craft) is real. `active_stage` is also still
      a hardcoded 0 in state_builder's vehicle snapshot -- multi-stage
      progression is not tracked, so this will only ever fire `stage 0`
      until that's built. Requires a human present and watching --
      do not run unattended. See git history for the prior (safer,
      log-only) version if this needs reverting.
"""
import argparse
import json
import os
import sys
import time
import math

import weave
from dotenv import load_dotenv

load_dotenv()  # picks up .env in the repo root (or CWD) if present

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "analysis"))

import forward_sim as fsim  # noqa: E402
import agent_interface as ai_predict  # noqa: E402  -- predict()/observe_to_state() are
# pure computation (forward_sim.py only), no game I/O -- safe to import
# unconditionally at module level, unlike observe()/act() which touch
# the live mod's file protocol and stay behind run_live()'s local import.
from tsai_client import SystemOneClient  # noqa: E402
from menus import build_menus, mission_profile, throttle_score_to_delta, TURN_AXIS_DELTA  # noqa: E402
from guardrail import evaluate, confidence_of, effective_confidence  # noqa: E402
from watchdog import Watchdog, StagingTracker  # noqa: E402
from state_builder import (  # noqa: E402
    build_state, build_feasibility, build_prediction_block,
    compute_delta_v_remaining_mps,
)
from overlay_state import write_overlay_state, write_overlay_status_only  # noqa: E402

SAFE_HOLD_THROTTLE_CHOICE = "hold"
SAFE_HOLD_PITCH_CHOICE = "hold"
# 2026-09-13 LATER SAME DAY: how many recent cycles' summaries ride along
# in state.history each call -- see PilotRun.cycle_history's docstring.
# 5 is a starting guess (covers roughly the last few seconds at whatever
# the current --cycle-period-s/achieved Hz is -- see main()'s
# --cycle-period-s default for why that's no longer a fixed 0.5s), not
# yet tuned against real flight data.
HISTORY_MAX_ENTRIES = 5


def log(msg: str) -> None:
    print(f"[pilot_loop] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Weave/W&B tracing -- same convention as hackathon/controller.py (that
# project's spec sec 10): thin @weave.op() wrappers at named boundary
# calls, one shared project ("sfs-ai-hackathon") so both architectures'
# traces land in the same place for judges/analysis. Guarded on
# WANDB_API_KEY exactly like controller.py -- that file's own 2026-09-12
# finding was that weave.init() with no key blocks forever on an
# interactive `wandb login` prompt instead of failing cleanly, which would
# hang this live flight loop, not just a script.
# ---------------------------------------------------------------------------
if os.environ.get("WANDB_API_KEY"):
    weave.init("sfs-ai-hackathon")
else:
    log("WANDB_API_KEY not set -- skipping weave.init(), @weave.op() calls "
        "will no-op (no tracing, but nothing hangs or breaks). Add "
        "WANDB_API_KEY to .env to enable real Weave logging.")


@weave.op()
def traced_tsai_ask(client: SystemOneClient, state: dict, menus: dict) -> dict:
    """Weave-traced wrapper around SystemOneClient.ask() -- the tsAI
    equivalent of controller.py's traced_observe/traced_act/traced_predict
    boundary-tracing convention. Captures the full per-cycle request
    (state + menus) and the raw systemone response, independent of
    anything the guardrail later decides to do with it."""
    return client.ask(state, menus)


@weave.op()
def log_pilot_cycle(
    cycle_id: int, phase: str, result_ok: bool, result_stale: bool,
    result_error: str, latency_s: float, raw_answers: dict, gate_summary: dict,
    accepted_throttle_choice: str, accepted_pitch_choice: str,
    commanded_throttle: float, commanded_turn_axis: float,
    extra_commands: list, watchdog_tag: str, watchdog_miss_count: int,
    rejections_logged_total: int,
) -> dict:
    """One traced call per pilot cycle -- the tsAI-pilot equivalent of
    controller.py's log_cycle_decision, bundling everything needed to
    analyze a flight after the fact without cross-referencing multiple
    traces: tsAI's raw per-menu choice+confidence, the guardrail's
    accept/reject+band+reason per menu, the post-watchdog choice that
    actually got acted on, and the real commands sent to the game this
    cycle (including (B)/(C)'s `master on`/`stage <index>`)."""
    return {
        "cycle_id": cycle_id, "phase": phase,
        "tsai_call": {"ok": result_ok, "stale": result_stale, "error": result_error,
                      "latency_s": round(latency_s, 3)},
        "raw_answers": raw_answers, "gate_summary": gate_summary,
        "accepted": {"throttle_choice": accepted_throttle_choice,
                     "pitch_choice": accepted_pitch_choice},
        "commanded": {"throttle": round(commanded_throttle, 3),
                      "turn_axis": round(commanded_turn_axis, 3),
                      "extra_commands": extra_commands},
        "watchdog": {"tag": watchdog_tag, "miss_count": watchdog_miss_count},
        "rejections_logged_total": rejections_logged_total,
    }


class PilotRun:
    def __init__(self, client: SystemOneClient, mission_target: dict,
                 craft_mass_t: float, craft_dry_mass_t: float, craft_isp: float,
                 craft_total_thrust_t: float,
                 max_cycles: int, cycle_period_s: float, live: bool):
        self.client = client
        self.mission_target = dict(mission_target)  # copy -- don't mutate caller's dict
        # 2026-09-13 fix: derive the flight profile from the mission
        # target itself and build the menus FROM it, instead of one
        # static, profile-blind module-level MENUS dict. See
        # menus.mission_profile()'s docstring for the live failure this
        # replaces. `profile` is also stored back onto mission_target so
        # it shows up in every cycle's state.mission_target -- visible
        # and auditable in the Weave trace, not just an internal
        # assumption.
        self.mission_target["profile"] = mission_profile(self.mission_target)
        self.menus = build_menus(self.mission_target)
        self.craft_mass_t = craft_mass_t
        self.craft_dry_mass_t = craft_dry_mass_t
        self.craft_isp = craft_isp
        self.craft_total_thrust_t = craft_total_thrust_t  # summed engine thrust
        # (tonnes-force @ throttle=1.0) -- used to expose thrust-to-weight
        # to tsAI (2026-09-13, Christian's explicit request), alongside
        # mass_t. Real finding that motivated this: the craft sat on the
        # pad at throttle 0.30 producing T/W < 1 (not enough to lift off)
        # for an entire run with no way for tsAI to know that -- it could
        # only see throttle and fuel_remaining_pct, neither of which says
        # whether the CURRENT thrust level can overcome gravity at all.
        self.max_cycles = max_cycles
        self.cycle_period_s = cycle_period_s
        self.live = live

        self.watchdog = Watchdog()
        self.staging_tracker = StagingTracker()
        self.current_throttle = 0.0
        self.rejections_logged = 0
        self.cycles_run = 0
        self.master_ignited = False  # tracks whether `master on` has been sent this run (B)
        self.last_turn_axis = 0.0  # last commanded turn_axis, fed to predict() as the
        # hypothetical continuation default ("if I keep doing what I'm
        # currently doing, where do I end up") -- see build_cycle_state.
        # 2026-09-13 LATER SAME DAY addition (Christian's explicit
        # request, replacing the now-unwired physics scratchpad): rolling
        # window of recent-cycle throttle/score/confidence summaries, fed
        # into state.history each cycle (see state_builder.build_state's
        # docstring). Targets tsAI's own self-reported explanation for
        # why its confidence collapsed over a real sustained flight --
        # every call was previously fully stateless, so a genuinely
        # ongoing correction and a brand-new situation looked identical.
        # Capped at HISTORY_MAX_ENTRIES, oldest dropped first.
        self.cycle_history = []
        # 2026-09-13 EVEN LATER SAME DAY addition (Christian's explicit
        # request): set True once task_status is ACCEPTED (>=0.9
        # confidence, guardrail.BANDS['task_completion']) with choice
        # 'task_complete'. Checked by run_cycle()'s return value -- once
        # True, the run ends on this cycle's return regardless of
        # max_cycles. Deliberately a one-way flag (never reset back to
        # False) -- a single confirmed-complete reading ends the run;
        # this is not re-checked or reversible by a later cycle.
        self.task_complete_confirmed = False

    def _vehicle_from_snapshot(self, snapshot: dict, torque_effective_raw: float) -> dict:
        px = snapshot.get("location.position.x", 0.0)
        py = snapshot.get("location.position.y", 0.0)
        vx = snapshot.get("location.velocity.x", 0.0)
        vy = snapshot.get("location.velocity.y", 0.0)
        body = fsim.PLANET_CONSTANTS["Earth"]
        r = math.hypot(px, py)
        altitude_m = r - body["radius_m"]
        # 2026-09-13 EVEN LATER SAME DAY fix (Christian's explicit
        # request, confirmed via a real setrot test + the exact unit
        # warning already documented in forward_sim.py's
        # test_against_run_trajectory docstring): rb2d.rotation and
        # rb2d.angularVelocity are ALREADY in degrees / deg-per-second
        # (Unity's Rigidbody2D convention), not radians -- this was
        # WRONGLY applying math.degrees() to an already-degree value,
        # producing a rotation ~57x too large (confirmed live: setrot 45
        # read back as raw rb2d.rotation=48.26, not 0.785 rad). This fed
        # a nonsensical angle_deg to tsAI's pitch_action every cycle,
        # which is almost certainly why it locked onto 'hold' at
        # confidence 1.000 regardless of the craft's real attitude.
        rot_deg = snapshot.get("rb2d.rotation", 0.0)
        angv_dps = snapshot.get("rb2d.angularVelocity", 0.0)
        mass_t = snapshot.get("rb2d.mass", self.craft_mass_t)
        fuel_pct = max(0.0, min(100.0,
                                 100.0 * (mass_t - self.craft_dry_mass_t) /
                                 max(1e-6, self.craft_mass_t - self.craft_dry_mass_t)))
        # 2026-09-13 addition (Christian's explicit request): mass_t and
        # thrust-to-weight, both current and at full throttle, now exposed
        # directly in state.vehicle. g_local uses the same confirmed
        # gravity formula as everywhere else in this project (g = mu/r^2)
        # rather than assuming a flat 9.8 -- the sim's own thrust formula
        # (F = thrust_t * 9.8 * throttle) bakes in a FIXED 9.8 conversion
        # constant unrelated to the actual body
        # (sfs_physics_reference.md sec 2.2), so weight must be computed
        # in the SAME units for the ratio to mean anything: weight_equiv =
        # mass_t * (g_local / 9.8).
        g_local = body["mu"] / (r * r) if r > 1.0 else 9.8
        weight_equiv_t = mass_t * (g_local / 9.8)
        thrust_to_weight_max = (self.craft_total_thrust_t / weight_equiv_t
                                 if weight_equiv_t > 1e-9 else 0.0)
        thrust_to_weight_current = thrust_to_weight_max * self.current_throttle
        return {
            "altitude_m": altitude_m,
            "vertical_speed_mps": vy,
            "horizontal_speed_mps": vx,
            "angle_deg": rot_deg,
            "angular_rate_dps": angv_dps,
            "throttle": self.current_throttle,
            "active_stage": 0,
            "fuel_remaining_pct": fuel_pct,
            "mass_t": mass_t,
            "thrust_to_weight_max": thrust_to_weight_max,
            "thrust_to_weight_current": thrust_to_weight_current,
        }, mass_t, g_local

    def build_cycle_state(self, cycle_id: int, t: float, snapshot: dict,
                           torque_effective_raw: float) -> dict:
        vehicle, mass_t, g_local = self._vehicle_from_snapshot(snapshot, torque_effective_raw)
        feasibility = build_feasibility(
            current_mass_t=mass_t, dry_mass_t=self.craft_dry_mass_t, isp=self.craft_isp,
            torque_effective_raw=torque_effective_raw,
            delta_v_required_for_target_mps=self.mission_target.get(
                "delta_v_required_for_target_mps", 0.0),
        )
        # Phase must match the REAL state, not just always claim ascent --
        # a "PAD_IDLE" craft (throttle 0, negligible speed, low altitude)
        # mislabeled as mid-gravity-turn is exactly the kind of
        # note-sec-5-warns-about ambiguity that (correctly) drives tsAI's
        # confidence down and the guardrail rejects on. Found live during
        # this Checkpoint 4 run -- see BUILD_LOG.md.
        # 2026-09-13 EVEN LATER SAME DAY: moved ABOVE the prediction-block
        # call (was below it) so compute_coast_apoapsis_trend() can use
        # the real current phase for its phase-consistency validity check
        # -- see state_builder.compute_coast_apoapsis_trend()'s docstring.
        speed = math.hypot(vehicle["horizontal_speed_mps"], vehicle["vertical_speed_mps"])
        if vehicle["throttle"] <= 0.01 and speed < 5.0 and vehicle["altitude_m"] < 200.0:
            phase = "PAD_IDLE"
        else:
            phase = "ASCENT_GRAVITY_TURN"
        # 2026-09-13 fix: this was ALWAYS build_prediction_block(None, ...)
        # -- a permanent null/low-confidence stub, every cycle, live
        # flight included. tsAI's own menu instructions explicitly tell it
        # to weigh "the forward prediction supplied in state" for ascent-
        # shaping decisions; with that always null, pitch_action had zero
        # real trajectory feedback during an actual ascent (confirmed:
        # confidence never exceeded ~0.35, rejected by the guardrail every
        # cycle, zero steering commanded for 13 straight cycles -- see
        # BUILD_LOG.md's 2026-09-13 crash entry). predict()/
        # observe_to_state() are pure forward-sim computation, no live
        # game I/O, so this is safe to call in replay mode too.
        predict_result = None
        try:
            predict_state = ai_predict.observe_to_state(snapshot)
            predict_result = ai_predict.predict(
                predict_state, waypoints=[], duration_s=15.0,
                default_throttle=self.current_throttle,
                default_turn_axis=self.last_turn_axis,
            )
        except Exception as e:  # noqa: BLE001 -- never let a predict() failure crash
            # the flight loop; falling back to the old null stub is a
            # regression to prior (safe, if uninformative) behavior, not
            # a new failure mode.
            log(f"cycle {cycle_id}: predict() failed ({e}) -- falling back to "
                f"low-confidence stub")
        prediction = build_prediction_block(
            predict_result, horizon_s=15.0,
            target_altitude_m=self.mission_target.get("apoapsis_m"),
            current_altitude_m=vehicle["altitude_m"],
            current_vertical_speed_mps=vehicle["vertical_speed_mps"],
            g_local_mps2=g_local,
            current_t=t,
            prev_history_entry=(self.cycle_history[-1] if self.cycle_history else None),
            current_phase=phase,
            mass_t=mass_t,
            total_thrust_t=self.craft_total_thrust_t,
            current_throttle=vehicle["throttle"])
        return build_state(cycle_id, t, phase, self.mission_target,
                            vehicle, feasibility, prediction,
                            history=list(self.cycle_history[-HISTORY_MAX_ENTRIES:]))

    def run_cycle(self, cycle_id: int, snapshot: dict, torque_effective_raw: float,
                  act_fn) -> bool:
        """Returns True to keep flying, False to end the run (max cycles
        reached this call)."""
        t = snapshot.get("t", float(cycle_id))
        state = self.build_cycle_state(cycle_id, t, snapshot, torque_effective_raw)
        phase = state["phase"]
        extra_commands = []  # real non-throttle/turn commands to send this cycle (B/C)
        answers = {}
        gate_results = {}

        result = traced_tsai_ask(self.client, state, self.menus)
        if not result["ok"] or result["stale"]:
            reason = result["error"] or f"stale response ({result['latency_s']:.2f}s)"
            log(f"cycle {cycle_id}: MISS ({reason})")
            self.watchdog.record_miss()
        else:
            answers = result["answers"].get("answers", {})
            for qname in self.menus:
                ans = answers.get(qname)
                if ans is None:
                    gate_results[qname] = None
                    continue
                gate_results[qname] = evaluate(qname, ans, state)
                gr = gate_results[qname]
                shown = ans.get("choice", ans.get("score"))
                native_conf = confidence_of(ans)
                gate_conf = effective_confidence(qname, ans)
                # 2026-09-13 LATER SAME DAY: throttle_score's gate now uses
                # a different number than its native confidence (see
                # guardrail.effective_confidence's docstring) -- show both
                # whenever they diverge so a log reader isn't misled into
                # thinking the printed number is what the gate decided on.
                conf_display = (f"{native_conf:.3f}" if abs(native_conf - gate_conf) < 1e-9
                                 else f"{native_conf:.3f} (gate used directional={gate_conf:.3f})")
                log(f"cycle {cycle_id}: {qname} answer={shown!r} "
                    f"conf={conf_display} -> "
                    f"{'ACCEPT' if gr.accepted else 'REJECT'} band={gr.band} "
                    f"reason={gr.reason}")
                if not gr.accepted:
                    self.rejections_logged += 1

            # 2026-09-13: throttle control is now phase-split across two
            # separate questions -- launch_decision (meaningful only
            # PAD_IDLE) and throttle_score (meaningful only
            # ASCENT_GRAVITY_TURN) -- both asked every cycle in parallel
            # like everything else, but only the phase-relevant one is
            # ever acted on below; the other's answer this cycle is
            # logged above and otherwise ignored (see menus.py's
            # LAUNCH_DECISION_MENU/THROTTLE_SCORE_MENU docstrings for why
            # a `score` question can't also carry the PAD_IDLE liftoff
            # decision in one question).
            throttle_gate = gate_results.get(
                "launch_decision" if phase == "PAD_IDLE" else "throttle_score")
            pitch_gate = gate_results.get("pitch_action")
            stage_gate = gate_results.get("stage_check")

            if throttle_gate and throttle_gate.accepted and pitch_gate and pitch_gate.accepted:
                pitch_choice_hit = answers["pitch_action"]["choice"]
                # Throttle marker is always a dummy "hold" here -- see the
                # HOLD-LAST handling below for why the real value is
                # never read back for throttle (persistent/cumulative
                # state; replaying any nonzero delta would double-apply
                # it, the same class of bug 'launch' had before this
                # rework, now closed for the whole throttle channel).
                self.watchdog.record_hit("hold", pitch_choice_hit)
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
                        f"-- SENDING `stage {active_stage}` LIVE this cycle (C)")
                    extra_commands.append(f"stage {active_stage}")
                else:
                    log(f"cycle {cycle_id}: stage_now for stage {active_stage} suppressed "
                        f"(already fired -- idempotency)")

            # 2026-09-13 EVEN LATER SAME DAY addition (Christian's
            # explicit request): only meaningful once actually flying
            # (PAD_IDLE has no ascent to be done with) -- same
            # phase-gating convention as launch_decision/throttle_score
            # above. task_status's own guardrail class
            # ('task_completion', reject_below=0.9 -- see guardrail.BANDS)
            # already did the confidence check inside evaluate() above;
            # this just acts on an ACCEPTED result.
            task_status_gate = gate_results.get("task_status")
            if (phase == "ASCENT_GRAVITY_TURN" and task_status_gate
                    and task_status_gate.accepted
                    and answers.get("task_status", {}).get("choice") == "task_complete"):
                self.task_complete_confirmed = True
                log(f"cycle {cycle_id}: task_status ACCEPTED as task_complete "
                    f"(confidence >= 0.9) -- ending the run after this cycle's "
                    f"safe-hold commands are sent.")

        outcome = self.watchdog.resolve(SAFE_HOLD_THROTTLE_CHOICE, SAFE_HOLD_PITCH_CHOICE)
        pitch_choice = outcome.pitch_choice or SAFE_HOLD_PITCH_CHOICE
        turn_axis = TURN_AXIS_DELTA.get(pitch_choice, 0.0)
        self.last_turn_axis = turn_axis  # fed to next cycle's predict() call

        # 2026-09-13 fix, generalizing the earlier 'launch'-specific fix
        # to the WHOLE throttle channel: throttle is persistent,
        # cumulative state (self.current_throttle carries across cycles),
        # unlike turn_axis (a fresh per-cycle rate command, safe to
        # replay as-is). HOLD-LAST replaying ANY throttle delta -- not
        # just 'launch's old +0.30 -- would double-apply it on top of
        # what's already set. So HOLD-LAST for throttle now ALWAYS means
        # "hold steady", same as DEGRADED-SAFE-HOLD, regardless of what
        # was last accepted. Only a genuinely fresh, THIS-cycle LIVE
        # accept ever changes self.current_throttle.
        fresh_accept = not outcome.held_from_last and not outcome.degraded
        throttle_label = "hold"

        if fresh_accept and phase == "PAD_IDLE":
            launch_choice = (answers.get("launch_decision") or {}).get("choice", "hold")
            if launch_choice == "launch" and not self.master_ignited:
                # 2026-09-13 (Christian's explicit request): 'launch' now
                # fires the FULL liftoff sequence -- master ignition +
                # stage arm + throttle -- instead of relying on
                # stage_check to separately decide to arm engines. Real
                # finding that led here: stage_check correctly says
                # 'hold_stage' on a fresh, full-fuel stage (there's no
                # fuel-exhaustion evidence yet), so on a previous run
                # 'launch' fired but the engines were NEVER armed
                # (engineOn stayed false) -- master on + throttle were
                # both sent for real but produced zero thrust. Routed
                # through the SAME staging_tracker idempotency
                # stage_check uses, so if stage_check later also tries to
                # fire this same index, it correctly sees it already
                # fired (no double-toggle -- `stage <index>` is NOT
                # idempotent, confirmed elsewhere in this project:
                # repeated calls on the same index TOGGLE engineOn, they
                # don't no-op).
                active_stage = state["vehicle"]["active_stage"]
                log(f"cycle {cycle_id}: launch accepted -- sending full liftoff "
                    f"sequence LIVE this cycle: `master on` (B) + `stage {active_stage}` "
                    f"(C) + throttle to 100%")
                extra_commands.insert(0, "master on")
                if self.staging_tracker.should_fire(active_stage):
                    extra_commands.append(f"stage {active_stage}")
                else:
                    log(f"cycle {cycle_id}: stage {active_stage} already fired earlier -- "
                        f"not re-arming (idempotency)")
                self.master_ignited = True
                self.current_throttle = 1.0
                throttle_label = "launch"
            # else: launch_choice == "hold"/"insufficient_data" -- stay put,
            # throttle_label/current_throttle already correctly "hold".
        elif fresh_accept:  # ASCENT_GRAVITY_TURN, fresh accept
            score = answers["throttle_score"]["score"]
            delta = throttle_score_to_delta(score)
            self.current_throttle = max(0.0, min(1.0, self.current_throttle + delta))
            throttle_label = f"score={score:.2f}(delta={delta:+.3f})"
        # else: HOLD-LAST or DEGRADED-SAFE-HOLD -- self.current_throttle
        # unchanged, throttle_label stays "hold".

        # 2026-09-13 LATER SAME DAY addition (Christian's explicit
        # request, replacing the now-unwired physics scratchpad): record
        # this cycle's throttle_score summary for state.history on the
        # NEXT cycle (see PilotRun.cycle_history's docstring and
        # state_builder.build_state's history param). Deliberately only
        # covers throttle_score, not launch_decision/pitch_action/
        # stage_check -- the confidence-collapse finding this targets was
        # specific to throttle_score's sustained-correction cycles.
        ts_answer = answers.get("throttle_score")
        self.cycle_history.append({
            "cycle_id": cycle_id,
            "t": round(t, 2),
            "phase": phase,
            "throttle": round(self.current_throttle, 3),
            "throttle_score": None if ts_answer is None else ts_answer.get("score"),
            "throttle_score_confidence": None if ts_answer is None else ts_answer.get("confidence"),
            "accepted_this_cycle": fresh_accept,
            "coast_apoapsis_error_m": state["prediction"].get("coast_apoapsis_error_m"),
        })
        if len(self.cycle_history) > HISTORY_MAX_ENTRIES:
            self.cycle_history.pop(0)

        tag = "DEGRADED-SAFE-HOLD" if outcome.degraded else (
            "HOLD-LAST" if outcome.held_from_last else "LIVE")
        log(f"cycle {cycle_id}: [{tag}] throttle_decision={throttle_label!r} -> "
            f"throttle={self.current_throttle:.2f} turn_axis={turn_axis:.2f}")

        gate_summary = {
            qname: (None if gr is None else
                    {"accepted": gr.accepted, "band": gr.band, "reason": gr.reason})
            for qname, gr in gate_results.items()
        }
        raw_answers = {
            qname: (None if ans is None else
                    {"choice": ans.get("choice"), "score": ans.get("score"),
                     "confidence": confidence_of(ans)})
            for qname, ans in answers.items()
        }
        log_pilot_cycle(
            cycle_id=cycle_id, phase=state["phase"],
            result_ok=result["ok"], result_stale=result["stale"], result_error=result["error"],
            latency_s=result["latency_s"], raw_answers=raw_answers, gate_summary=gate_summary,
            accepted_throttle_choice=throttle_label, accepted_pitch_choice=pitch_choice,
            commanded_throttle=self.current_throttle, commanded_turn_axis=turn_axis,
            extra_commands=list(extra_commands), watchdog_tag=tag,
            watchdog_miss_count=self.watchdog.miss_count,
            rejections_logged_total=self.rejections_logged,
        )

        # HUD overlay -- one write per cycle, for the fullscreen judge-facing
        # Swift overlay (hackathon/overlay/). Never allowed to affect flight
        # control: any failure here is swallowed and logged, not raised.
        try:
            write_overlay_state(
                status="active", cycle_id=cycle_id, t=t, phase=phase,
                mission_target=self.mission_target, answers=answers,
                gate_results=gate_results, menus=self.menus,
                commanded_throttle=self.current_throttle, commanded_turn_axis=turn_axis,
                watchdog_tag=tag,
            )
        except Exception as e:  # noqa: BLE001 -- cosmetic HUD write, never fatal
            log(f"cycle {cycle_id}: [WARN] overlay write failed: {e}")

        act_fn(self.current_throttle, turn_axis, extra_commands,
               full_authority_throttle=(throttle_label == "launch"))

        self.cycles_run += 1
        # 2026-09-13 EVEN LATER SAME DAY: max_cycles == -1 means
        # unlimited (Christian's explicit request) -- the run now ends
        # ONLY when task_complete_confirmed flips True (task_status
        # accepted at >=0.9 confidence) or, if a finite --max-cycles was
        # explicitly passed, that count is reached first (whichever
        # comes first still applies -- max_cycles remains a hard backstop
        # when set, not overridden by the infinite default).
        cycles_exhausted = self.max_cycles != -1 and self.cycles_run >= self.max_cycles
        return not self.task_complete_confirmed and not cycles_exhausted


def _safe_shutdown_act(ai_module, command: str, max_attempts: int = 3,
                        retry_delay_s: float = 0.5) -> None:
    """Retries a shutdown command a bounded number of times before giving
    up -- the same 2026-09-12 mod-unresponsive finding controller.py's
    _call_with_retry exists for (sfsprobe can go unresponsive for a few
    seconds, independent of anything wrong with the flight itself; this
    live dry run hit it for real, right on this exact shutdown call).
    This is the LAST line of defense (the run is already ending, in a
    `finally` block) -- failure here must never crash silently or mask
    whatever exception got us into `finally` in the first place: catch
    broadly, warn loudly, never re-raise."""
    for attempt in range(1, max_attempts + 1):
        try:
            ai_module.act(command, allow_full_authority=True, use_tcp=True)
            return
        except TimeoutError as e:
            log(f"  [WARN] shutdown command {command!r} timed out "
                f"(attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                time.sleep(retry_delay_s)
        except Exception as e:  # noqa: BLE001 -- deliberately broad: this is the
            # safety net, nothing here should ever propagate and hide the
            # real error or leave a later shutdown command unsent.
            log(f"  [CRITICAL] shutdown command {command!r} failed unexpectedly: {e}")
            return
    log(f"  [CRITICAL] shutdown command {command!r} failed after {max_attempts} attempts -- "
        f"MANUAL INTERVENTION MAY BE NEEDED, check the game directly")


def _preflight_feasibility_gate(mass_t: float, dry_mass_t: float, isp: float,
                                 mission_target: dict) -> bool:
    """ONE-TIME check, run once before the first cycle -- separate from
    the per-cycle `feasibility` block in state_builder.py, which tracks
    MARGIN as fuel burns DURING flight and is correctly recomputed every
    cycle. This answers a different question, asked at a different time:
    can this craft, at full fuel, ever reach this mission target at all?

    2026-09-13 finding this exists to fix: without this, an infeasible
    mission (this run's actual case -- see BUILD_LOG.md) never surfaced
    as a clear, loud, one-time stop. It just looked like tsAI quietly
    hesitating on the pad forever (cycle after cycle of ambiguous
    low-confidence 'hold'), indistinguishable from ordinary caution
    without pulling the Weave traces. Same underlying dry-mass-estimate
    ballpark as the per-cycle check -- this doesn't fix that estimate's
    accuracy, it just stops silently retrying an infeasible mission.

    Returns True if feasible, False (after logging loudly) if not."""
    available = compute_delta_v_remaining_mps(mass_t, dry_mass_t, isp)
    required = mission_target.get("delta_v_required_for_target_mps", 0.0)
    log(f"PREFLIGHT: available delta-v ~{available:.0f}m/s (isp={isp:.0f}, "
        f"mass={mass_t:.1f}t, dry_est={dry_mass_t:.1f}t) vs required "
        f"{required:.0f}m/s for mission target {mission_target}")
    if available < required:
        log(f"PREFLIGHT FAILED: MISSION INFEASIBLE -- need {required:.0f}m/s, "
            f"craft has ~{available:.0f}m/s at full fuel. Not starting the "
            f"pilot loop -- lower the mission target, or improve the "
            f"dry-mass estimate, before trying again.")
        return False
    log("PREFLIGHT OK -- proceeding.")
    return True


def run_live(max_cycles: int, cycle_period_s: float, mission_target: dict) -> PilotRun:
    import agent_interface as ai

    # 2026-09-13 EVEN LATER SAME DAY (Christian's explicit request,
    # following the mod-timeout crash mid-flight that ended tonight's
    # task_status live test): switched every real live call in this
    # function over to the TCP path (tcp-rewrite, now merged in) --
    # file-protocol (command.txt/result.txt polling) is what actually
    # timed out. TCP checkpoint 4 measured ~22 Hz vs. the file-protocol's
    # 2.48 Hz baseline (~9x) with no observed timeouts across its own
    # live-validated dry run -- see TCP_REWRITE_LOG.md. use_tcp=True is
    # now threaded through every observe()/act() call below, including
    # the safety-critical shutdown path in the `finally` block
    # (_safe_shutdown_act, above) -- that shutdown call was the EXACT
    # one that timed out tonight, so it's not left on the slower/less
    # reliable path just because it's "only cleanup". File-protocol
    # remains agent_interface.py's default (use_tcp defaults False) --
    # this is pilot_loop.py opting in explicitly, not a global flip.
    resp = ai._send_command_tcp("getforwardstartinfo")
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

    run = PilotRun(SystemOneClient(), mission_target, mass_t, dry_mass_t, isp, total_thrust,
                   max_cycles, cycle_period_s, live=True)

    if not _preflight_feasibility_gate(mass_t, dry_mass_t, isp, mission_target):
        return run  # 0 cycles run -- nothing was ever commanded, nothing to shut down

    try:
        write_overlay_status_only("active")
    except Exception as e:  # noqa: BLE001 -- cosmetic HUD write, never fatal
        log(f"  [WARN] overlay status write failed: {e}")

    def act_fn(throttle, turn_axis, extra_commands=None, full_authority_throttle=False):
        for cmd in extra_commands or []:
            log(f"  -> sending live: {cmd!r}")
            ai.act(cmd, use_tcp=True)
        ai.act(f"throttle {throttle:.3f}", allow_full_authority=full_authority_throttle, use_tcp=True)
        ai.act(f"turn {turn_axis:.3f}", use_tcp=True)

    cycle_id = 0
    loop_start_t = time.time()  # 2026-09-13 LATER SAME DAY: real achieved
    # Hz measurement, not just the --cycle-period-s setting -- the real
    # floor is tsAI latency + game IPC round-trip, so the setting alone
    # doesn't tell you what rate was actually achieved.
    try:
        while True:
            snapshot = ai.observe(use_tcp=True)
            # rb2d.angularVelocity is already deg/s (see the unit note in
            # _vehicle_from_snapshot above) -- no math.degrees() here either.
            angv_dps = abs(snapshot.get("rb2d.angularVelocity", 0.0))
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
        elapsed_s = time.time() - loop_start_t
        if cycle_id > 0 and elapsed_s > 0:
            log(f"achieved rate: {cycle_id} cycles in {elapsed_s:.1f}s "
                f"= {cycle_id / elapsed_s:.2f} Hz (--cycle-period-s was {cycle_period_s})")
        log("run ending -- commanding safe throttle-down/attitude-hold")
        try:
            write_overlay_status_only("ended")
        except Exception as e:  # noqa: BLE001 -- cosmetic HUD write, never fatal
            log(f"  [WARN] overlay status write failed: {e}")
        _safe_shutdown_act(ai, "throttle 0.0")
        _safe_shutdown_act(ai, "turn 0.0")
        if run.master_ignited:
            log("run ending -- master ignition was sent this run, sending `master off` cleanup")
            _safe_shutdown_act(ai, "master off")
        # 2026-09-13 fix (#3): the script's own control ends here, but the
        # game keeps running -- if the craft is still meaningfully
        # airborne and moving, that's not obvious unless someone is
        # watching closely (this is exactly what got missed before the
        # 2026-09-13 crash: the run ended mid-climb at 170m/s with no
        # loud signal that manual attention was now needed). Best-effort,
        # read-only, never allowed to raise past this point.
        try:
            final_snapshot = ai.observe(use_tcp=True)
            final_alt = math.hypot(
                final_snapshot.get("location.position.x", 0.0),
                final_snapshot.get("location.position.y", 0.0),
            ) - fsim.PLANET_CONSTANTS["Earth"]["radius_m"]
            final_vy = final_snapshot.get("location.velocity.y", 0.0)
            if final_alt > 200.0 and abs(final_vy) > 10.0:
                log(f"  [ATTENTION] craft is still airborne at shutdown: "
                    f"altitude~{final_alt:.0f}m, vertical_speed~{final_vy:+.0f}m/s -- "
                    f"pilot_loop control has ended, this needs YOUR attention now "
                    f"(throttle/attitude/parachute) -- it will NOT auto-recover.")
            else:
                log(f"  final state: altitude~{final_alt:.0f}m, "
                    f"vertical_speed~{final_vy:+.0f}m/s")
        except Exception as e:  # noqa: BLE001 -- best-effort reporting only,
            # never let this final check mask whatever got us into finally.
            log(f"  [WARN] could not read final state for the airborne check: {e}")

    return run


def run_replay(log_path: str, max_cycles: int, mission_target: dict) -> PilotRun:
    ticks = []
    with open(log_path) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "tick":
                ticks.append(d)

    mass_t, dry_mass_t, isp, torque_idle = 12.4, 6.0, 260.0, 850.0
    total_thrust = 20.0  # placeholder, same spirit as the other hardcoded
    # replay-craft numbers above -- a rough single-small-engine figure,
    # not measured. Only affects the new thrust_to_weight fields' realism
    # in replay mode, not the guardrail/watchdog plumbing this harness
    # actually tests.
    # 2026-09-13 EVEN LATER SAME DAY: max_cycles == -1 (the new infinite
    # default) has no meaning against a FIXED recorded tick sequence --
    # replay is bounded by len(ticks) regardless, so -1 here just means
    # "use every tick", same as passing len(ticks) explicitly.
    effective_max_cycles = len(ticks) if max_cycles == -1 else min(max_cycles, len(ticks))
    run = PilotRun(SystemOneClient(), mission_target, mass_t, dry_mass_t, isp, total_thrust,
                   effective_max_cycles, cycle_period_s=0.0, live=False)

    if not _preflight_feasibility_gate(mass_t, dry_mass_t, isp, mission_target):
        return run  # 0 cycles run

    body = fsim.PLANET_CONSTANTS["Earth"]

    def act_fn(throttle, turn_axis, extra_commands=None, full_authority_throttle=False):
        for cmd in extra_commands or []:
            log(f"  (replay -- would also send: {cmd!r})")
        log(f"  (replay -- would send: throttle {throttle:.3f}, turn {turn_axis:.3f})")

    step = max(1, len(ticks) // effective_max_cycles)
    selected = ticks[::step][:effective_max_cycles]
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
    # 2026-09-13 EVEN LATER SAME DAY: -1 means unlimited (Christian's
    # explicit request) -- the run now ends when tsAI's own task_status
    # answer is ACCEPTED as task_complete (>=0.9 confidence, see
    # guardrail.BANDS['task_completion'] and menus.TASK_STATUS_MENU's
    # docstring for the calibration behind that floor), not a fixed
    # cycle count. A positive value still works as a hard backstop cap
    # (whichever -- task_complete or the cycle count -- comes first ends
    # the run; see PilotRun.run_cycle()'s return logic).
    parser.add_argument("--max-cycles", type=int, default=-1)
    # 2026-09-13 LATER SAME DAY: lowered from 0.5 (Christian's explicit
    # request -- 1Hz effective loop rate was too slow to catch a
    # fast-closing coast_apoapsis_error_m in time, confirmed live: 14
    # cycles of continuous, correctly-directed graduated braking still
    # weren't enough on a T/W~3+ craft). 0.0 removes the artificial sleep
    # entirely -- the real floor becomes tsAI's own round-trip latency
    # (~0.2-0.3s per call, confirmed from real traces) plus the game's
    # file-polling IPC, not this constant. Real achieved Hz is now logged
    # at DONE so this can be tuned from measured data, not guessed.
    parser.add_argument("--cycle-period-s", type=float, default=0.0)
    parser.add_argument("--replay-log", default=os.path.join(HERE, "..", "manual_flight_log.jsonl"))
    # 2026-09-13 STILL LATER SAME DAY addition (Christian's explicit
    # request -- "test a real turn signal, see if it can do any orbital
    # stuff"): mission_target was previously hardcoded to a fixed
    # vertical-hop mission (periapsis_m=0) every run, so pitch_action's
    # ORBITAL_ASCENT gravity-turn framing (see menus._pitch_action_menu's
    # profile branch) had never actually been exercised live -- every
    # flight tonight held vertical the whole way by design (profile ==
    # 'vertical_hop'). Exposed as real CLI flags instead of editing the
    # hardcoded dict, so this is a reusable knob, not a one-off hack.
    # Defaults preserve tonight's exact vertical-hop mission unchanged.
    parser.add_argument("--apoapsis-m", type=float, default=5000.0)
    parser.add_argument("--periapsis-m", type=float, default=0.0,
                         help="> 0 switches menus.mission_profile() to "
                              "'orbital_ascent' (real gravity-turn pitch "
                              "shaping) instead of 'vertical_hop' (hold "
                              "vertical). NOTE: this craft's real delta-v "
                              "budget (~200m/s) is nowhere near what a "
                              "real circular orbit needs at low altitude "
                              "on this body (~1743 m/s at ~5000m, mu/r^2 "
                              "physics) -- a positive periapsis_m tests "
                              "the gravity-turn PITCH LOGIC, not an "
                              "actually-achievable orbital insertion.")
    parser.add_argument("--delta-v-required-mps", type=float, default=150.0)
    args = parser.parse_args()

    mission_target = {"apoapsis_m": args.apoapsis_m, "periapsis_m": args.periapsis_m,
                       "delta_v_required_for_target_mps": args.delta_v_required_mps}

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
