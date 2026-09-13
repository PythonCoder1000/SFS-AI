"""
menus.py -- the fixed, safe-by-construction menus tsAI answers every
cycle (launch_decision, throttle_score, pitch_action, stage_check).

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
4. Cartesian-product joint-action safety (launch_decision x throttle_score
   x pitch_action x stage_check) is pre-vetted offline in
   cartesian_check.py using forward_simulate()/predict() against real
   recorded states, not assumed at call time (systemone's questions
   cannot see each other -- BUILD_SPEC sec 3/4.3). Conclusion (logged in
   BUILD_LOG.md): no combination of a bounded throttle delta with a
   bounded turn_axis delta can itself resolve to a catastrophic command,
   because each axis independently clamps to agent_interface.act()'s
   existing MAX_TURN_AXIS_MAGNITUDE (0.5) and MAX_THROTTLE_STEP (0.3)
   hard limits, and stage_now only ever resolves to `stage <index>` for
   the CURRENT active stage -- never a blanket fire. The commands
   (throttle, turn, stage) are sent as separate act() calls, so there is
   no single joint command for them to combine into.

   *** 2026-09-13, Christian's explicit request, NOT YET RE-VETTED: ***
   `launch_decision`'s `launch` no longer resolves to a +0.30 delta --
   pilot_loop.py now special-cases it to set throttle to 1.0 directly,
   sent with act()'s allow_full_authority (bypassing MAX_THROTTLE_STEP
   for that one call, by design, so the jump actually reaches 100% in
   the game). `launch` ALSO now sends `stage <active_stage_index>` in
   the same cycle (previously only stage_check's own accept could do
   that). The structural argument above -- "launch sits exactly at, not
   past, MAX_THROTTLE_STEP" -- NO LONGER HOLDS, and the dedicated
   PAD_IDLE forward-simulation case in cartesian_check.py was built
   against the OLD 0.30 magnitude, not 1.0 combined with a real stage
   arm. This needs a fresh cartesian_check.py pass before the safety
   conclusion above can be trusted for `launch` again -- treat it as
   unverified, not re-confirmed, until that's done.

   *** 2026-09-13, second change, ALSO NOT YET RE-VETTED: ***
   Ongoing throttle control (previously `throttle_action`'s
   increase/decrease choices) is now `throttle_score`, a CONTINUOUS
   `score`-type question instead of six fixed `choice` buckets -- see
   throttle_score_to_delta()'s docstring for the live finding that
   motivated this (a real correction need genuinely split 3 ways across
   adjacent discrete buckets, never clearing the confidence threshold).
   The resulting delta is still clamped through the same
   MAX_THROTTLE_STEP path as before (agent_interface.act(), not bypassed
   for this one), so the STRUCTURAL per-call magnitude bound is
   unchanged -- but `score`'s calibration/reliability has not been
   characterized in this project the way `choice` has (the build spec's
   "same input reliably produces the same top choice" note was stated
   specifically about `choice`). Treat as unverified until smoke-tested.
   `hold_on_pad` (pitch_action, +0.0), added in Checkpoint 6 for
   PAD_IDLE framing, is unaffected by either change -- still a
   zero-magnitude turn delta, still covered by the original argument.

   *** 2026-09-13, third change, does NOT need cartesian_check.py
   re-vetting: *** `THROTTLE_SCORE_MENU`'s instructions briefly pointed
   tsAI at a new `state.physics` block (thrust_accel_mps2/
   gravity_accel_mps2/net_accel_mps2 -- see state_builder.py's
   build_physics_block()) before scoring. REMOVED again the same day: a
   real live flight showed confidence on throttle_score collapsing over
   sustained cycles (0.48 -> 0.09) with this block present every cycle
   -- it didn't hurt, but didn't fix the actual failure either.
   build_physics_block() is kept in state_builder.py, unwired, for a
   future reshape -- not currently sent.

   *** 2026-09-13, fourth change, ALSO does NOT need cartesian_check.py
   re-vetting: *** `THROTTLE_SCORE_MENU`'s instructions now instead
   point tsAI at a new `state.history` list (last few cycles'
   throttle/score/confidence/coast_apoapsis_error_m -- see
   state_builder.py's build_state() `history` param and pilot_loop.py's
   PilotRun.cycle_history). Motivated by tsAI's own self-report (asked
   directly why its confidence collapsed over a sustained flight: 66%
   'repeated_near_identical_state', 27% 'no_memory_of_trend') --
   every call was previously fully stateless, so a genuinely ongoing
   correction and a brand-new situation looked identical. Same safety
   category as the physics-block change above: input/instructions only,
   no menu vocabulary, score->delta mapping, or clamp path touched.
"""

INSUFFICIENT_DATA_PHRASING = (
    "The supplied current state lacks, has stale, or has contradictory "
    "information required to distinguish the operational choices. Select "
    "this only when no operational choice is supported -- not merely "
    "because two supported choices are close."
)

# Bounded deltas applied on top of the CURRENT commanded turn_axis.
# Stays well inside agent_interface.act()'s hard clamp (turn axis
# +/-0.5/call) so a menu choice can never by itself demand more
# authority than act() already allows -- act()'s clamp is a second,
# independent backstop, not the only one.
TURN_AXIS_DELTA = {"retrograde_large": -0.35, "retrograde_small": -0.15, "hold": 0.0,
                    "prograde_small": 0.15, "prograde_large": 0.35,
                    "hold_on_pad": 0.0}

# 2026-09-13: named anchor points on throttle_score's continuous scale,
# in order (index 0 = criteria[0] = most negative). throttle_score_to_delta()
# interpolates BETWEEN these -- the whole point of switching to `score`
# is that a real correction no longer has to round to one of these,
# unlike the old six-bucket `choice` menu it replaces.
THROTTLE_SCORE_LEVELS = [
    ("cut", -1.0),
    ("decrease_large", -0.20),
    ("decrease_small", -0.08),
    ("hold", 0.0),
    ("increase_small", 0.08),
    ("increase_large", 0.20),
]


def throttle_score_to_delta(score: float) -> float:
    """Maps a continuous `score` answer to a throttle DELTA via
    piecewise-linear interpolation between THROTTLE_SCORE_LEVELS'
    named anchor points (score is expected in [0, len(levels)-1],
    clamped defensively either way).

    2026-09-13 fix this replaces: throttle_action used to be a `choice`
    menu with two fixed step sizes (+/-0.08 small, +/-0.20 large).
    Confirmed live: a genuine, real correction need (craft well past
    target altitude, still climbing hard) split tsAI's probability mass
    THREE WAYS across decrease_small/hold/decrease_large (0.39/0.34/0.18
    at one point), so no single bucket ever cleared the 0.5 confidence
    threshold, even though ~0.57 combined probability agreed on SOME
    decrease -- repeated across cycles 23-29 of that run. A continuous
    score has no adjacent buckets to split a real in-between correction
    across."""
    n = len(THROTTLE_SCORE_LEVELS)
    clamped = max(0.0, min(float(n - 1), score))
    lo = int(clamped)
    hi = min(lo + 1, n - 1)
    frac = clamped - lo
    lo_delta = THROTTLE_SCORE_LEVELS[lo][1]
    hi_delta = THROTTLE_SCORE_LEVELS[hi][1]
    return lo_delta + (hi_delta - lo_delta) * frac


# PAD_IDLE-only: the discrete liftoff decision. Kept as `choice` (a
# genuine binary event, not a continuous quantity) even though ongoing
# throttle control moved to `throttle_score` below -- a `score` question
# can't also represent a one-shot 0%->100% liftoff jump cleanly, so this
# stays a separate question from throttle_score, asked every cycle in
# parallel but only MEANINGFUL during PAD_IDLE (pilot_loop.py reads
# whichever of the two is phase-relevant; see its build_cycle_state()).
LAUNCH_DECISION_MENU = {
    "type": "choice",
    "instructions": (
        "You are piloting a rocket. This question only applies while "
        "`state.phase` is `PAD_IDLE` (vehicle stationary, unlaunched, "
        "throttle at or near zero) -- once phase is ASCENT_GRAVITY_TURN "
        "the vehicle has already launched and this question no longer "
        "applies (see throttle_score for ongoing throttle control "
        "instead). `launch` opens the throttle to 100% (full liftoff), "
        "not a small step -- before choosing it, check "
        "`state.vehicle.thrust_to_weight_max`: if it is at or below 1.0, "
        "full throttle still will not lift the vehicle off the pad, and "
        "`hold` is the correct choice instead."
    ),
    "criteria": {
        "launch": "PAD_IDLE ONLY: open the throttle to 100% to begin "
            "liftoff -- the vehicle is stationary and unlaunched (phase "
            "PAD_IDLE), `state.vehicle.thrust_to_weight_max` clearly "
            "exceeds 1.0 (full throttle can actually overcome gravity), "
            "and the mission target and feasibility budget support "
            "beginning flight now.",
        "hold": "PAD_IDLE ONLY: remain on the pad at zero throttle -- do "
            "not launch yet (e.g. mission target/feasibility budget do "
            "not yet clearly support beginning flight, or the evidence "
            "is ambiguous).",
        "insufficient_data": INSUFFICIENT_DATA_PHRASING,
    },
}

# ASCENT_GRAVITY_TURN-only: continuous throttle control (see
# throttle_score_to_delta()'s docstring for why this is `score`, not
# `choice`). criteria[i] MUST stay index-aligned with
# THROTTLE_SCORE_LEVELS above -- both describe the same six anchor
# points, in the same order.
THROTTLE_SCORE_MENU = {
    "type": "score",
    "instructions": (
        "You are piloting a rocket during ASCENT_GRAVITY_TURN (this "
        "question does not apply while `state.phase` is `PAD_IDLE` -- see "
        "launch_decision instead for the liftoff decision). Score how the "
        "CURRENT throttle should change this cycle, on the continuous "
        "scale below from 0 (cut immediately) to 5 (a large increase). "
        "This is a CONTINUOUS scale, not a fixed set of buckets -- if the "
        "right correction sits between two anchor points (e.g. more than "
        "a small decrease but less than a large one), score accordingly "
        "in between them rather than rounding to the nearest anchor. "
        "`state.history` (when present) lists your last few cycles' "
        "throttle/score/confidence/coast_apoapsis_error_m, oldest first -- "
        "use it to tell whether this is a NEW situation or a CONTINUATION "
        "of a correction already underway: if coast_apoapsis_error_m has "
        "been shrinking toward zero cycle over cycle, that correction is "
        "WORKING and a similar or smaller score is likely still right; if "
        "it has been flat or growing despite recent corrections, the "
        "prior magnitude was insufficient and a LARGER score is likely "
        "needed, not a repeat of the same one. Do not let seeing several "
        "similar-looking recent cycles in `state.history` lower your "
        "confidence on its own -- similarity across cycles is expected "
        "during a sustained correction, not evidence of ambiguity; judge "
        "confidence from how clearly the CURRENT numbers support a "
        "choice, the same as if `state.history` were empty. "
        "`state.prediction.coast_apoapsis_m` is the altitude this "
        "trajectory would coast up to if thrust were cut THIS INSTANT "
        "(closed-form, ignores drag/horizontal motion) -- "
        "`coast_apoapsis_error_m` is that minus the mission's target "
        "apoapsis, so a large POSITIVE coast_apoapsis_error_m means even "
        "an immediate full cutoff still overshoots by that much, and a "
        "large NEGATIVE value means continuing to coast alone won't reach "
        "the target even without cutting. Use this as your PRIMARY signal "
        "for magnitude -- it directly answers 'how far off would doing "
        "nothing more leave me', which is a more concrete basis for the "
        "score than eyeballing raw altitude/speed/feasibility numbers. "
        "CRITICAL, on a powerful vehicle: coast_apoapsis_error_m can move "
        "by thousands of meters in a SINGLE cycle once vertical speed is "
        "high (it scales with speed squared), so waiting until it's "
        "already positive to start backing off is often already too "
        "late. `coast_apoapsis_closure_rate_mps` (how fast the error is "
        "moving toward/through zero, computed from this cycle vs the "
        "last) and `coast_apoapsis_seconds_to_crossover` (a linear "
        "extrapolation of how many seconds until it crosses zero AT THAT "
        "RATE, or null if no crossover is currently projected) exist "
        "specifically so you can start reducing throttle BEFORE "
        "coast_apoapsis_error_m itself goes positive, proportional to how "
        "soon and how fast it's closing -- a short seconds_to_crossover "
        "with still-negative coast_apoapsis_error_m calls for an early, "
        "partial decrease now, not waiting for confirmation. "
        "`terminal_error` (the 15s forward-simulated prediction assuming "
        "throttle/turn_axis HOLD UNCHANGED) is a secondary cross-check, "
        "not the primary signal, since it reflects a fixed future horizon "
        "rather than an immediate what-if. Also weigh `mass_t` and "
        "`thrust_to_weight_current`/`thrust_to_weight_max`, and the "
        "feasibility budget (delta-v remaining vs required)."
    ),
    "criteria": [
        "0 -- cut: stop thrust immediately -- an off-nominal condition "
            "(overspeed vs. target, or delta-v budget exhausted) requires "
            "stopping now, not a graduated reduction",
        "1 -- decrease_large: vehicle is accelerating well past what the "
            "prediction/feasibility budget supports",
        "2 -- decrease_small: vehicle is running slightly hot relative to "
            "the target trajectory",
        "3 -- hold: prediction and feasibility both indicate the current "
            "throttle is on track",
        "4 -- increase_small: vehicle is running slightly cold relative "
            "to the target trajectory",
        "5 -- increase_large: vehicle is significantly underperforming "
            "the target trajectory and has ample delta-v/fuel margin to "
            "spend catching up",
    ],
}

def mission_profile(mission_target: dict) -> str:
    """2026-09-13 fix: derives the flight profile FROM the mission target
    itself (periapsis_m <= 0 -> a vertical hop, no orbit to shape toward)
    instead of letting the pitch menu's text silently assume every
    mission is an orbital launch. See _pitch_action_menu's docstring for
    the live failure this fixes (2026-09-13: pitch_action confidence
    never exceeded ~0.34 for an entire flight, genuinely split between
    prograde/retrograde, because the instructions pointed toward
    orbital gravity-turn shaping for a mission that had none)."""
    return "vertical_hop" if mission_target.get("periapsis_m", 0) <= 0 else "orbital_ascent"


def _pitch_action_menu(profile: str) -> dict:
    """Builds pitch_action's ASCENT_GRAVITY_TURN guidance for the given
    flight profile. This used to be ONE static, profile-blind dict --
    see mission_profile()'s docstring for the live failure that caused.
    PAD_IDLE guidance (hold_on_pad) is identical either way and is not
    branched."""
    if profile == "vertical_hop":
        ascent_guidance = (
            "This mission's target has `periapsis_m` at or below 0 -- a "
            "vertical hop to a target altitude, not an orbital insertion. "
            "There is no periapsis to raise, so trading vertical velocity "
            "for horizontal velocity (a gravity turn) does NOT help reach "
            "the target altitude -- it costs altitude for no orbital "
            "benefit. `hold` near vertical is the correct DEFAULT choice "
            "for this profile, including when the prediction shows an "
            "altitude shortfall or overshoot -- that is a throttle/timing "
            "problem, not a pitch problem, when there is no periapsis "
            "target. Only choose `prograde`/`retrograde` to correct real, "
            "evidenced UNWANTED drift away from vertical (e.g. actual "
            "tipping from wind or torque), never as deliberate "
            "ascent-shaping."
        )
        prograde_small = ("ASCENT_GRAVITY_TURN, vertical-hop mission "
            "(periapsis_m <= 0): NOT a fix for an altitude shortfall or "
            "overshoot -- there is no periapsis to raise. Only choose this "
            "to correct small, evidenced unwanted drift away from vertical.")
        prograde_large = ("ASCENT_GRAVITY_TURN, vertical-hop mission "
            "(periapsis_m <= 0): NOT a fix for an altitude shortfall or "
            "overshoot -- there is no periapsis to raise. Only choose this "
            "to correct large, evidenced unwanted drift away from vertical.")
        hold_text = ("ASCENT_GRAVITY_TURN, vertical-hop mission "
            "(periapsis_m <= 0): DEFAULT correct choice -- hold near "
            "vertical, which maximizes altitude for the fuel spent, even "
            "if the prediction shows a shortfall or overshoot (fix that "
            "with throttle, not pitch, for this profile). (For a "
            "stationary, unlaunched vehicle use `hold_on_pad` instead.)")
        retrograde_small = ("ASCENT_GRAVITY_TURN, vertical-hop mission "
            "(periapsis_m <= 0): rotate back toward vertical by a small "
            "step -- use to correct real, evidenced drift away from "
            "vertical.")
        retrograde_large = ("ASCENT_GRAVITY_TURN, vertical-hop mission "
            "(periapsis_m <= 0): rotate back toward vertical by a large "
            "step -- use to correct real, evidenced drift away from "
            "vertical.")
    else:  # "orbital_ascent"
        ascent_guidance = (
            "Choose the single best attitude (pitch) adjustment for this "
            "cycle using the ascent-shaping criteria below, given the "
            "current angle, angular rate, the mission target, and the "
            "forward prediction supplied in `state`. `prograde` narrows "
            "the pitch-over angle toward the velocity vector (standard "
            "gravity-turn shaping); `retrograde` widens it back toward "
            "vertical. Prefer smaller adjustments unless the terminal "
            "error or turn-rate bound clearly calls for a larger one."
        )
        prograde_small = ("ASCENT_GRAVITY_TURN ONLY: rotate toward "
            "prograde by a small step (turn_axis +0.15) -- the vehicle is "
            "pitching over slightly too slowly.")
        prograde_large = ("ASCENT_GRAVITY_TURN ONLY: rotate toward "
            "prograde by a large step (turn_axis +0.35) -- the vehicle is "
            "well behind the target gravity-turn shape and has turn-rate "
            "margin to spend catching up.")
        hold_text = ("ASCENT_GRAVITY_TURN ONLY: hold the current "
            "attitude/rate -- prediction indicates the current "
            "gravity-turn shape is on track. (For a stationary, unlaunched "
            "vehicle use `hold_on_pad` instead.)")
        retrograde_small = ("ASCENT_GRAVITY_TURN ONLY: rotate toward "
            "vertical by a small step (turn_axis -0.15) -- the vehicle is "
            "pitching over slightly too fast.")
        retrograde_large = ("ASCENT_GRAVITY_TURN ONLY: rotate toward "
            "vertical by a large step (turn_axis -0.35) -- the vehicle is "
            "pitching over too aggressively relative to the target "
            "trajectory.")

    return {
        "type": "choice",
        "instructions": (
            "You are piloting a rocket. `state.phase` tells you which "
            "framing applies this cycle. If `state.phase` is `PAD_IDLE` "
            "(vehicle stationary, unlaunched), choose `hold_on_pad` using "
            "its criteria below -- the `retrograde`/`prograde`/`hold` "
            "options describe shaping an ALREADY-underway ascent and have "
            "no clean meaning for a grounded vehicle with no meaningful "
            "airspeed or velocity vector to shape toward. If "
            "`state.phase` is `ASCENT_GRAVITY_TURN`: " + ascent_guidance
        ),
        "criteria": {
            "hold_on_pad": "PAD_IDLE ONLY: maintain the vehicle's current "
                "pre-launch orientation on the pad -- no attitude shaping "
                "is applicable while the vehicle is stationary and "
                "unlaunched. Not applicable once phase is "
                "ASCENT_GRAVITY_TURN.",
            "retrograde_large": retrograde_large,
            "retrograde_small": retrograde_small,
            "hold": hold_text,
            "prograde_small": prograde_small,
            "prograde_large": prograde_large,
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

def build_menus(mission_target: dict) -> dict:
    """Builds the per-run menu set FROM the actual mission target,
    instead of a single static module-level dict that can silently go
    stale relative to whatever mission is actually being flown (see
    mission_profile()/_pitch_action_menu()'s docstrings for the live
    2026-09-13 failure this replaces). Call once per PilotRun -- the
    mission target doesn't change mid-flight -- and reuse the result;
    see pilot_loop.py's PilotRun.__init__."""
    profile = mission_profile(mission_target)
    return {
        "launch_decision": LAUNCH_DECISION_MENU,
        "throttle_score": THROTTLE_SCORE_MENU,
        "pitch_action": _pitch_action_menu(profile),
        "stage_check": STAGE_CHECK_MENU,
    }

# Confidence-band question class, used by guardrail.py (BUILD_SPEC sec 4.1).
QUESTION_CLASS = {
    "launch_decision": "routine",
    "throttle_score": "routine",
    "pitch_action": "routine",
    "stage_check": "irreversible",
}
