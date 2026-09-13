"""
menus.py -- the fixed, safe-by-construction `choice` menus tsAI answers
every cycle (throttle_action, pitch_action, stage_check).

Design rules applied here (OPTION_A_BUILD_SPEC.md sec 4.3), non-negotiable:
1. Every menu has an explicit insufficient_data option, phrased as the
   vendor-tested "none of the above supported" framing, not "I don't know".
2. No catastrophic option ever appears in vocabulary here (no blanket
   `ignite` -- staging is index-based, armed one stage at a time, via
   stage_check's `stage_now` -> the caller resolves that to
   `stage <active_stage_index>`, never a blanket fire-everything command).
3. Menu completeness (checked informally at design time, see
   BUILD_LOG.md Checkpoint 1 entry): every menu keeps at least one
   throttle/attitude option reachable in any phase this project flies
   (ascent gravity turn) -- coasting (throttle=hold/cut) and holding
   attitude are always legal regardless of state, so the pilot is never
   trapped with zero supported options.
4. Cartesian-product joint-action safety (throttle_action x pitch_action
   x stage_check) is pre-vetted offline in test_checkpoint1.py using
   predict() against a real recorded state, not assumed at call time
   (systemone's questions cannot see each other -- BUILD_SPEC sec 3/4.3).
   Conclusion (logged in BUILD_LOG.md): no combination of a bounded
   throttle delta with a bounded turn_axis delta can itself resolve to a
   catastrophic command, because each axis independently clamps to
   agent_interface.act()'s existing MAX_TURN_AXIS_MAGNITUDE (0.5) and
   MAX_THROTTLE_STEP (0.3) hard limits, and stage_now only ever resolves
   to `stage <index>` for the CURRENT active stage -- never a blanket
   fire. The three axes are independent commands (throttle, turn, stage)
   sent as separate act() calls, so there is no single joint command for
   them to combine into.
"""

INSUFFICIENT_DATA_PHRASING = (
    "The supplied current state lacks, has stale, or has contradictory "
    "information required to distinguish the operational choices. Select "
    "this only when no operational choice is supported -- not merely "
    "because two supported choices are close."
)

# Bounded deltas applied on top of the CURRENT commanded throttle/turn_axis.
# Both stay well inside agent_interface.act()'s hard clamps (turn axis
# +/-0.5/call, throttle step +/-0.3/call) so a menu choice can never by
# itself demand more authority than act() already allows -- act()'s clamp
# is a second, independent backstop, not the only one.
THROTTLE_DELTA = {"decrease_large": -0.20, "decrease_small": -0.08, "hold": 0.0,
                   "increase_small": 0.08, "increase_large": 0.20, "cut": -1.0}
TURN_AXIS_DELTA = {"retrograde_large": -0.35, "retrograde_small": -0.15, "hold": 0.0,
                    "prograde_small": 0.15, "prograde_large": 0.35}

THROTTLE_ACTION_MENU = {
    "type": "choice",
    "instructions": (
        "You are piloting a rocket during ascent. Choose the single best "
        "throttle adjustment for this cycle, given the vehicle state, "
        "mission target (target apoapsis/periapsis), feasibility budget "
        "(delta-v remaining vs required), and the forward prediction "
        "supplied in `state`. Prefer smaller adjustments unless the "
        "terminal error or feasibility margin clearly calls for a larger "
        "one. `cut` is for an emergency/off-nominal situation only "
        "(e.g. imminent overspeed past target orbital velocity, or "
        "delta-v budget already exhausted) -- not a routine choice."
    ),
    "criteria": {
        "decrease_large": "Cut throttle by a large step (-0.20) -- vehicle is "
            "accelerating well past what the prediction/feasibility budget supports.",
        "decrease_small": "Reduce throttle by a small step (-0.08) -- vehicle is "
            "running slightly hot relative to the target trajectory.",
        "hold": "Keep the current throttle unchanged -- prediction and feasibility "
            "both indicate the current setting is on track.",
        "increase_small": "Raise throttle by a small step (+0.08) -- vehicle is "
            "running slightly cold relative to the target trajectory.",
        "increase_large": "Raise throttle by a large step (+0.20) -- vehicle is "
            "significantly underperforming the target trajectory and has ample "
            "delta-v/fuel margin to spend on catching up.",
        "cut": "Cut throttle to zero immediately -- an off-nominal condition "
            "(overspeed vs. target, or delta-v budget exhausted) requires "
            "stopping thrust now, not a graduated reduction.",
        "insufficient_data": INSUFFICIENT_DATA_PHRASING,
    },
}

PITCH_ACTION_MENU = {
    "type": "choice",
    "instructions": (
        "You are piloting a rocket during a gravity-turn ascent. Choose "
        "the single best attitude (pitch) adjustment for this cycle, "
        "given the current angle, angular rate, the mission target, and "
        "the forward prediction supplied in `state`. `prograde` narrows "
        "the pitch-over angle toward the velocity vector (standard "
        "gravity-turn shaping); `retrograde` widens it back toward "
        "vertical. Prefer smaller adjustments unless the terminal error "
        "or turn-rate bound clearly calls for a larger one."
    ),
    "criteria": {
        "retrograde_large": "Rotate toward vertical by a large step (turn_axis "
            "-0.35) -- the vehicle is pitching over too aggressively relative to "
            "the target trajectory.",
        "retrograde_small": "Rotate toward vertical by a small step (turn_axis "
            "-0.15) -- the vehicle is pitching over slightly too fast.",
        "hold": "Hold the current attitude/rate -- prediction indicates the "
            "current gravity-turn shape is on track.",
        "prograde_small": "Rotate toward prograde by a small step (turn_axis "
            "+0.15) -- the vehicle is pitching over slightly too slowly.",
        "prograde_large": "Rotate toward prograde by a large step (turn_axis "
            "+0.35) -- the vehicle is well behind the target gravity-turn shape "
            "and has turn-rate margin to spend catching up.",
        "insufficient_data": INSUFFICIENT_DATA_PHRASING,
    },
}

# stage_check is the ONLY irreversible-action menu here. It never contains
# a blanket `ignite`-equivalent -- `stage_now` resolves (in pilot_loop.py)
# to `stage <active_stage_index>` for the CURRENT stage only, matching the
# mod's documented arm-in-order staging contract (BUILD_SPEC sec 1).
STAGE_CHECK_MENU = {
    "type": "choice",
    "instructions": (
        "You are piloting a rocket during ascent. The current stage's "
        "fuel_remaining_pct and feasibility budget are supplied in "
        "`state`. Decide whether the CURRENT active stage should be "
        "staged (jettisoned/next stage armed) THIS cycle. This is an "
        "irreversible action -- only choose stage_now when the evidence "
        "clearly supports it (e.g. current stage fuel effectively "
        "exhausted, or delta-v remaining in this stage cannot meet the "
        "feasibility budget for the target)."
    ),
    "criteria": {
        "stage_now": "Stage the current active stage now -- its fuel is "
            "effectively exhausted or its remaining delta-v cannot support "
            "reaching the mission target, and the evidence for this is clear.",
        "hold_stage": "Do not stage this cycle -- the current stage still has "
            "usable fuel/delta-v margin toward the mission target.",
        "insufficient_data": INSUFFICIENT_DATA_PHRASING,
    },
}

MENUS = {
    "throttle_action": THROTTLE_ACTION_MENU,
    "pitch_action": PITCH_ACTION_MENU,
    "stage_check": STAGE_CHECK_MENU,
}

# Confidence-band question class, used by guardrail.py (BUILD_SPEC sec 4.1).
QUESTION_CLASS = {
    "throttle_action": "routine",
    "pitch_action": "routine",
    "stage_check": "irreversible",
}
