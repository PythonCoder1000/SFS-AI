# Option A (tsAI-as-pilot) — Autonomous Build Log

Running unattended per `hackathon/OPTION_A_BUILD_SPEC.md`. This log
records decisions made without a human to ask, and any deviation from
the spec's literal text, with the reasoning behind each.

All code for this build lives under `hackathon/optionA/`, kept separate
from the existing hackathon submission (`controller.py`/`supervisor.py`/
`gateway.py` — the Claude-as-supervisor architecture). Option A is a
distinct, parallel architecture (tsAI directly as pilot); nothing in the
existing submission is modified.

## Environment / data setup (before Checkpoint 1)

- Working in a git worktree (`worktree-optionA-build`, based on
  `origin/optionA-autonomous-build`) per this session's isolation policy.
- `TYPESAFE_AI_API_KEY` and the other `.env` secrets are gitignored and
  therefore not present in a fresh worktree checkout — copied `.env`
  from the main working copy (`/Users/christianjin/Documents/VSCode/SFS AI/.env`)
  into the worktree. This is a local file copy only, never committed
  (`.env` stays gitignored).
- `hackathon/manual_flight_log.jsonl` and `analysis/telemetry_flat_*.jsonl`
  are also gitignored generated telemetry (`*.jsonl` in `.gitignore`), so
  they were likewise absent from the fresh worktree. Copied
  `manual_flight_log.jsonl` (and one `telemetry_flat_*` file) from the
  main working copy for Checkpoint 1's unit test and Checkpoint 4's
  offline-replay fallback. Not committed (still gitignored in the
  worktree too).
- Confirmed `requests` is available via `uv run` (transitive dependency),
  so all scripts in `hackathon/optionA/` are run as
  `uv run python3 hackathon/optionA/<script>.py` from repo root.

## Checkpoint 1 — tsAI client + menu library

**Built:**
- `hackathon/optionA/tsai_client.py` — `SystemOneClient.ask(state, questions)`,
  auth from `.env`/env (`TYPESAFE_AI_API_KEY`), timeout, and a
  response-freshness check (`stale` flag when round-trip latency exceeds
  `freshness_s`, default 3.0s — a placeholder pending real dry-run
  latency data, see Checkpoint 4 note below).
- `hackathon/optionA/menus.py` — `throttle_action`, `pitch_action`,
  `stage_check` menus. Each has an explicit `insufficient_data` option
  using the vendor-tested "none of the above supported" phrasing (never
  "I don't know"). `ignite`/blanket-fire never appears anywhere in this
  file's vocabulary — `stage_check`'s `stage_now` resolves (in
  `pilot_loop.py`, Checkpoint 4) to `stage <active_stage_index>` only,
  matching the mod's arm-in-order contract.
- `hackathon/optionA/state_builder.py` — builds the sec-5 enriched state
  schema. `compute_max_angular_accel_dps2` reuses
  `forward_sim.compute_turn_axis`'s exact mass-penalty law (torque /=
  (mass/200)^0.35 above 200t) instead of re-deriving it, so it can never
  drift from the validated physics. `compute_delta_v_remaining_mps` uses
  Tsiolkovsky **without a g0 multiplier** — confirmed by reading
  `forward_sim._engine_thrust`'s `mass_flow = thrust_ton * throttle / isp`,
  this codebase's `isp` already plays the role of effective exhaust
  velocity in-engine, not real-world seconds-of-ISP. Using the textbook
  `isp * 9.80665 * ln(...)` form would have overstated delta-v by ~9.8x
  against this project's own validated fuel-burn physics — a real trap,
  worth flagging clearly here.

**Deviation from spec's literal data sources:** `manual_flight_log.jsonl`
only contains `{t, altitude_m, vx, vy, avg_throttle}` — a straight
altitude-hold test log, not a fully-instrumented ascent with
angle/fuel/stage telemetry. For the Checkpoint 1 unit test
(`test_checkpoint1.py`), missing fields were filled as follows, each
clearly labeled in-code:
- `angle_deg`: derived from the REAL `atan2(vx, vy)` velocity heading
  (reasonable stand-in during gravity-turn ascent where attitude tracks
  the velocity vector) — not fabricated.
- `angular_rate_dps`, `fuel_remaining_pct`: not present in this log at
  all; filled with documented placeholder constants, not silently
  treated as real telemetry.
- Mass/ISP/torque constants for the feasibility block were pulled from
  the real `analysis/sfs_probe_forwardstartinfo_hackathon_firing.json`
  snapshot (this project's actual hackathon test craft), not invented.

**Exit check result:** `uv run python3 hackathon/optionA/test_checkpoint1.py`
— 4 real states sampled across the flight log, all 3 bundled questions
per state returned choices inside their menu vocabulary with bounded
[0,1] confidence. **PASS.** Notably, `throttle_action` confidence came
back low (0.22–0.33) on this altitude-hold log — expected, since the
menu's framing assumes an ascent-shaping context this log doesn't
provide, and it's exactly the kind of case the confidence gate (sec 4.1,
Checkpoint 2) exists to catch.

**Cartesian-product offline safety check (sec 4.3 point 4):**
`hackathon/optionA/cartesian_check.py` forward-simulates the single most
aggressive available combination (max throttle-increase + max turn,
held 5s) from a real recorded state. Result: no collision, and no
result far outside physically-sane bounds. Caveat worth recording
honestly: the simulated final altitude went slightly negative at this
particular (near-ground, near-zero-velocity) starting sample without the
simulator's own `collided` flag tripping — a low-altitude terrain-
resolution edge case in `forward_simulate`'s dt granularity, not
something this check should paper over. It doesn't change the
Cartesian-safety conclusion (the same slight-descent behavior happens at
zero throttle too — it's gravity, not the aggressive combo, causing it),
but it's flagged here rather than silently treated as a clean pass.
The primary safety argument for this check remains structural, not
simulation-based: the three menus resolve to three independent, already-
individually-bounded commands (throttle delta, turn delta, stage index),
each well inside `agent_interface.act()`'s existing hard clamps, so no
combination of them can compose into a single unsafe command the way a
raw `ignite` would.

**Commit:** `checkpoint 1: tsAI client + menus`

## Checkpoint 2 — Feasibility + confidence gate

**Built:**
- `hackathon/optionA/guardrail.py` — `confidence_gate()` (sec 4.1,
  class-specific bands: routine reject<0.5/caution<0.7, irreversible
  reject<0.7/caution<0.9; `noul` confidence analog `abs(noul-0.5)*2`
  used automatically, `.confidence` never read on a `noul` answer) and
  `evaluate()` which chains it into the feasibility check (sec 4.2) for
  the actual chosen option. `insufficient_data`/`hold_stage` skip
  feasibility entirely — they're always the safe no-op regardless of
  confidence band. Caution-band answers get a `CAUTION_MARGIN` (1.5x)
  applied to every feasibility threshold, per sec 4.1's "pass with
  margin, not just pass" requirement.
- Feasibility checks per question: `throttle_action` (increasing
  throttle requires delta-v margin above what the target still needs);
  `pitch_action` (projects the chosen turn's angular-rate effect one
  assumed second forward and rejects if it would exceed 2x the
  vehicle's max angular acceleration — a documented simplification, see
  the function's own docstring for the dps-vs-dps2 unit note);
  `stage_check` (`stage_now` only accepted when the current stage's
  fuel is near-exhausted or its remaining delta-v can't meet the
  target — staging a healthy stage away is itself an irreversible
  mistake this project has no way to undo).

**Exit check result:** `uv run python3 hackathon/optionA/test_checkpoint2.py`
— three cases: (1) low-confidence `throttle_action` answer (0.31, below
the 0.5 routine floor) rejected on confidence alone with a typed reason;
(2) high-confidence (0.95) but physically infeasible `stage_now` (plenty
of delta-v/fuel margin remaining) rejected by feasibility despite
clearing the irreversible-class confidence floor; (3) sanity control
(feasible + confident `hold`) accepted cleanly. **PASS**, all three.

**Commit:** `checkpoint 2: feasibility + confidence gate`

## Checkpoint 3 — Watchdog + staging idempotency

**Built:**
- `hackathon/optionA/watchdog.py` — `Watchdog` (miss-counting,
  hold-last-accepted-command for exactly 1 miss, degrade to a
  caller-supplied phase-default safe-hold at 2+ consecutive misses per
  sec 6; `DEGRADE_AFTER_MISSES = 2` kept as the spec's own placeholder,
  not tightened yet — no real dry-run miss data exists until Checkpoint
  4) and `StagingTracker` (edge-triggered staging: a stage index fires
  at most once, tracked by the index itself as the command ID — a
  duplicate/replayed response targeting an already-fired index is a
  no-op, never a second `stage <index>` send; a genuinely new index
  still fires normally).
- Kept staging idempotency deliberately STRICTER than the continuous-
  command hold logic: replaying a bounded throttle/pitch hold is safe
  (reversible), replaying a stage command is not (sec 1's known
  catastrophic-staging failure mode class).

**Exit check result:** `uv run python3 hackathon/optionA/test_checkpoint3.py`
— dropped-response case: 1st miss holds the last accepted
throttle/pitch command exactly once, 2nd consecutive miss degrades to
the safe-hold default, and a subsequent hit resets the streak; duplicate
-response case: three `stage 0` requests (one genuine + two
duplicate/stale replays) produce exactly one `stage 0` send, and a
genuinely new stage index (`1`) still fires. **PASS**, both cases.

**Commit:** `checkpoint 3: watchdog + staging idempotency`

## Checkpoint 4 — Wire into agent_interface.py/sfsprobe, live dry run

**Built:** `hackathon/optionA/pilot_loop.py` — the full loop:
`observe()`/replay tick -> `state_builder.build_state()` -> one bundled
`SystemOneClient.ask()` call -> `guardrail.evaluate()` per question ->
`Watchdog`/`StagingTracker` -> `agent_interface.act()`. Supports
`--mode live` (real game via `analysis/agent_interface.py`) and
`--mode replay` (drives the identical loop against
`manual_flight_log.jsonl` ticks, per the spec's own documented
fallback) from one shared `PilotRun` class, so the decision logic is
identical in both modes — only the state source and whether `act()` is
real differ.

**A live SFS session WAS reachable** (unattended, but a rocket was
already loaded on the pad from prior test sessions) — this checkpoint's
exit was met via an actual live run, not the offline fallback, though
`--mode replay` was also exercised and works end-to-end (see below).

**Live dry run result (`--mode live --max-cycles 15`):** tsAI genuinely
answered all three bundled questions from real telemetry every cycle
(15 cycles, real `getforwardstartinfo`-sourced mass/isp/torque, real
`observe()` position/velocity/rotation each cycle). The guardrail
visibly rejected **every** cycle's `throttle_action`/`pitch_action`
answer on confidence (`throttle_action` confidence 0.13–0.35;
`pitch_action` mostly `insufficient_data` at confidence 0.24–0.46 --
both below the 0.5 routine floor) and accepted `stage_check`'s
`stage_now` into the caution band each time but suppressed it via
`StagingTracker` idempotency after the first cycle (and never sent it
live at all, per this file's safety note below). Net result: the
vehicle stayed on the pad, throttle 0 for the entire run, ending in a
genuinely stable state -- confirmed after the run via a fresh
`observe()`: mass unchanged (116.0t), rotation ~0, angular velocity
~0 -- **no crash, no unintended motion.**

**Real finding, worth recording honestly (not covered up as a clean
pass):** the craft never left the pad because `throttle_action`
confidence never crossed 0.5 even after fixing the state's `phase`
field to correctly say `PAD_IDLE` (was hardcoded to
`ASCENT_GRAVITY_TURN` regardless of actual throttle/speed/altitude
before this run -- fixed in `pilot_loop.py` mid-Checkpoint-4, see the
inline comment). Confidence actually got LOWER after the phase fix
(0.13–0.22 vs. 0.18–0.35 before) -- plausible reason: the current menu
instructions frame `throttle_action` purely in terms of ascent-shaping
("running slightly hot/cold relative to target trajectory"), which has
no clean meaning for a stationary, unlaunched vehicle -- there's no
explicit "launch" framing distinct from "increase throttle for shaping
reasons" in the current menu text. This is a real menu-design gap for a
PAD_IDLE phase, not a bug in the gate -- and the resulting behavior
(never launching without confidence) is itself the guardrail correctly
doing its job: refusing to act on a plausible-but-uncertain choice with
no human to double-check it. Recorded here rather than tuned away
under time pressure -- fixing it properly would mean adding a
PAD_IDLE-specific `launch`/`hold_on_pad` framing to the menu and
re-validating the Cartesian-product safety argument for it, which is
follow-up work, not a Checkpoint 4 blocker (the exit condition is a
live loop with a visible guardrail rejection and no crash, both
present).

**Safety deviation, deliberate:** `stage_check` answers are computed,
confidence-gated, and feasibility-checked exactly per spec, but
`pilot_loop.py` never sends the resulting `stage <index>` command to
the live game -- only `throttle_action`/`pitch_action` are sent live.
This craft's real stage-index mapping (which index corresponds to
"jettison the currently-firing propulsion stage" vs. accidentally the
parachute stage further down the stack) was not independently
re-verified before this unattended run, and sec 1's own catalogued
catastrophic-staging failure mode is exactly the risk this project has
zero tolerance for running with no human watching. This is logged here
as a real, intentional scope reduction from the spec's literal "wire
into act()/stage()" wording, not a silent omission.

**Replay mode also exercised** (`--mode replay --max-cycles 6` against
`manual_flight_log.jsonl`): identical loop, same guardrail/watchdog
behavior confirmed (12 rejections across 6 cycles, degrade-to-safe-hold
engaged by cycle 1, ended in a controlled, logged safe-hold with no
real `act()` calls sent). Kept in the codebase as the documented
fallback path even though the live path is what actually satisfied this
checkpoint's exit condition.

**Commit:** `checkpoint 4: live loop wired, dry run complete`

## Checkpoint 5 — Wrap-up

### What got built

All under `hackathon/optionA/`, a self-contained architecture distinct
from the existing hackathon submission (`controller.py`/`supervisor.py`/
`gateway.py`, the Claude-as-supervisor-over-a-PD-loop design). This
build implements sec 2's alternative: tsAI (`jev-latest` via
`/v1/systemone`) as the direct pilot, answering a fixed safe-by-
construction menu every cycle.

| File | Role |
|---|---|
| `tsai_client.py` | `SystemOneClient` -- thin `/v1/systemone` wrapper, auth from `.env`, timeout, freshness check |
| `menus.py` | `throttle_action`/`pitch_action`/`stage_check` menus -- `insufficient_data` always present, `ignite`/blanket-fire never in vocabulary |
| `state_builder.py` | Builds the sec-5 enriched state; Tsiolkovsky delta-v (this codebase's isp convention, no g0) and `alpha_max` (reuses `forward_sim.compute_turn_axis`'s mass-penalty law) |
| `guardrail.py` | Confidence bands (sec 4.1, class-specific) + feasibility check (sec 4.2), chained in `evaluate()` |
| `watchdog.py` | `Watchdog` (miss-count, hold-1, degrade-at-2) + `StagingTracker` (edge-triggered staging idempotency) |
| `pilot_loop.py` | Full loop, live or replay mode, `PilotRun` |
| `cartesian_check.py` | Design-time offline Cartesian-product safety check (sec 4.3.4) |
| `test_checkpoint{1,2,3}.py` | Per-checkpoint exit-condition tests |

### What got tested

- Checkpoint 1: real `/v1/systemone` calls against 4 real states from
  `manual_flight_log.jsonl` -- bounded, in-menu answers. PASS.
- Checkpoint 1 (design-time): Cartesian-product worst-case combo
  forward-simulated via `predict()`/`forward_simulate()` -- no
  collision; structural argument (independent, individually-bounded
  commands) is the primary safety basis. PASS, with an honestly-flagged
  low-altitude terrain-resolution caveat (see that section above).
- Checkpoint 2: synthetic low-confidence and synthetic
  high-confidence-but-infeasible answers both correctly rejected with
  typed reasons; a feasible+confident control case correctly accepted.
  PASS, 3/3 cases.
- Checkpoint 3: mocked dropped-response (hold-then-degrade) and mocked
  duplicate stage response (no double-fire) both correct. PASS, 2/2
  cases.
- Checkpoint 4: **real live SFS session**, 15 real cycles, real
  telemetry, real `/v1/systemone` calls, guardrail rejected every
  throttle/pitch answer this run (30 rejections) and suppressed a
  repeated `stage_now` via idempotency; ended in a confirmed-stable,
  undamaged state (throttle 0, mass/rotation unchanged from start). No
  crash. `--mode replay` also exercised end-to-end as the documented
  fallback path (12 rejections/6 cycles, same guardrail/watchdog logic).

### What's still a placeholder / known gap (per sec 8, not re-researched)

- **`DEGRADE_AFTER_MISSES = 2`** is still the spec's own placeholder,
  not a computed FTTI -- the live dry run never actually got an
  ACCEPTED answer to establish a real "how often does a good answer
  land" baseline, so there was no data to tighten it against. Left as
  spec's own conservative default.
- **Confidence bands (sec 4.1: 0.5/0.7/0.9)** unchanged from the spec --
  no rigorous calibration set exists (per spec's own sec 8 disclosure).
  The live dry run's actual numbers (throttle_action never above 0.35,
  stage_check consistently 0.73-0.86) are a small additional data point
  suggesting these bands are doing real work (correctly gating out a
  genuinely ambiguous PAD_IDLE throttle decision), not evidence they're
  perfectly tuned.
- **`dry_mass_t` estimate (35% of current wet mass)** in `pilot_loop.py`
  live mode is a documented ballpark, not measured -- this craft has no
  independent dry-mass telemetry channel. Affects the delta-v
  feasibility check's precision, not its existence/correctness as a
  mechanism.
- **`stage_check` is never sent live** (see Checkpoint 4's safety-
  deviation note) -- computed and gated correctly, but a real
  `stage <index>` send was deliberately scoped out of this unattended
  run pending independent re-verification of this craft's stage-index
  mapping. Follow-up, not a blocker.
- **PAD_IDLE menu framing gap** (Checkpoint 4 finding): the current
  `throttle_action`/`pitch_action` instructions assume an in-progress
  ascent; a genuinely idle, unlaunched craft has no clean "launch now"
  framing distinct from "shape the ascent," which measurably lowered
  tsAI's confidence below the accept floor and kept the craft grounded
  for the whole live dry run. Not fixed here -- fixing it means adding
  PAD_IDLE-specific menu criteria AND re-running the sec 4.3 Cartesian-
  product safety argument for that new option, which is real follow-up
  work, not a quick patch to make under this session's time budget.
- `trust_prediction`-style calibration (sec 8) was not built at all --
  `state_builder.build_prediction_block()` passes through
  `predict()`'s own `confidence` label unchanged; no separate
  tsAI-facing weighting logic was added, consistent with sec 8's own
  guidance not to rely on tsAI perfectly discounting a bad forecast.

### Deviations from the spec's literal text, summarized

1. Missing example data files (`manual_flight_log.jsonl`,
   `telemetry_flat_*`) were absent from the isolated build worktree
   (gitignored, not tracked) -- copied in from the main working copy
   rather than treated as a blocker, since they clearly exist in the
   project and the spec explicitly names them.
2. `manual_flight_log.jsonl`'s actual schema (`t`/`altitude_m`/`vx`/`vy`/
   `avg_throttle` only) is thinner than sec 5's full vehicle schema --
   missing fields filled with clearly-labeled real-derived values
   (angle from velocity heading) or documented placeholders, never
   silently treated as real telemetry.
3. Tsiolkovsky delta-v implemented WITHOUT the standard g0 multiplier,
   because this codebase's own `isp` convention (confirmed by reading
   `forward_sim._engine_thrust`) already omits it -- a correctness fix
   relative to the textbook formula, not a deviation from validated
   physics.
4. `stage_check` is computed/gated live but never actually sent to the
   game this session (safety-motivated scope reduction, Checkpoint 4).
5. Checkpoint 4's exit was met via a genuine live run (the game was, in
   fact, reachable) rather than the replay fallback -- the replay path
   was still built and verified per spec, just not the one that ended
   up satisfying the exit condition.

### Bottom line

The tsAI-as-pilot architecture from sec 2 is fully wired end-to-end and
was proven live: every cycle's flight-control decision really did come
from `/v1/systemone`, and the guardrail (confidence bands + feasibility
+ pre-vetted menu vocabulary + watchdog + staging idempotency) really
did do the job of preventing an under-confident/infeasible answer from
reaching the game, without a human in the loop. The specific outcome
this run (craft stayed safely grounded) is less visually dramatic than
a full ascent, but it is the CORRECT and SAFE outcome given what tsAI
actually reported about its own confidence in a state genuinely ambiguous
for the current menu wording -- and this project's own explicit safety
priority is exactly a guardrail that will accept "no flight" over
guessing.

**Final commit:** `checkpoint 5: Option A build complete, see BUILD_LOG.md`

## Checkpoint 6 — PAD_IDLE menu framing fix (follow-up to Checkpoint 4/5)

Follow-up task, unattended, per the Checkpoint 4/5 finding: the
`throttle_action`/`pitch_action` menu instructions and criteria in
`hackathon/optionA/menus.py` assumed an in-progress ascent for every
choice, so a genuinely idle/unlaunched vehicle (`state.phase ==
"PAD_IDLE"`) had no clean way to be answered about -- tsAI was forced
to reinterpret "increase throttle for ascent-shaping reasons" as a
liftoff decision, which measurably lowered its confidence and kept the
craft grounded for the whole Checkpoint 4 live dry run (not wrongly --
the guardrail correctly refused to act on an under-confident answer --
but for the wrong underlying reason: a menu-design gap, not a real
absence of evidence).

**HARD CONSTRAINT observed this session:** no live launch was
attempted, and no `pilot_loop.py --mode live` run was made at any point
in this checkpoint. Everything below was validated via `--mode replay`,
the unit/synthetic checkpoint tests, the offline Cartesian-product
check, and direct (non-`act()`) calls to `SystemOneClient.ask()` for
real-telemetry confidence inspection only -- consistent with this
session's instructions.

**Built / changed:**
- `hackathon/optionA/menus.py`:
  - Added a new PAD_IDLE-only `throttle_action` choice, `launch`
    (throttle delta +0.30 -- sits exactly at, not past,
    `agent_interface.act()`'s existing `MAX_THROTTLE_STEP` (0.3) hard
    clamp, so it needs no clamp change and no new bound to justify).
  - Added a new PAD_IDLE-only `pitch_action` choice, `hold_on_pad`
    (turn_axis delta +0.0 -- a zero-magnitude command, distinct in
    *label* from ascent's `hold` so tsAI is never asked to reuse an
    ascent-shaping label for a grounded vehicle, but identical in
    *effect*: no rotation command).
  - Rewrote both menus' `instructions` to explicitly branch on
    `state.phase`: PAD_IDLE vehicles are told to choose only between
    `launch`/`hold` (throttle) or `hold_on_pad` (pitch) using
    PAD_IDLE-specific criteria text; ASCENT_GRAVITY_TURN vehicles keep
    the original ascent-shaping criteria, now explicitly labeled
    "ASCENT_GRAVITY_TURN ONLY" so tsAI is told the existing options
    don't apply to a stationary craft rather than left to infer it.
  - `hold` (throttle) keeps working for both phases but now carries two
    distinct criteria sentences (PAD_IDLE: "stay on the pad, don't
    launch yet" vs. ASCENT_GRAVITY_TURN: "current setting is on
    track") -- deliberately kept as one shared choice rather than
    forked into `hold`/`hold_on_pad` like pitch_action, since "stay at
    the current throttle setting" is one coherent idea in both phases
    (0.0 throttle on the pad, whatever-it-is in ascent); pitch_action's
    `hold` genuinely means something different in each phase (attitude
    -tracking vs. no-rotation-applicable), which is why it got a
    separate label instead.
  - Updated the module docstring's Cartesian-product design-rule
    paragraph to describe the new choices and point at the two-case
    check below instead of the original single mid-flight case.
- `hackathon/optionA/cartesian_check.py` (sec 4.3 point 4 re-run,
  required before considering this done): restructured into two
  worst-case cases instead of one:
  - **Case 1** (unchanged): the original ASCENT_GRAVITY_TURN worst case
    (`increase_large` + `prograde_large`/`retrograde_large`, whichever
    the dict iteration picks first at tied magnitude) from a real
    mid-flight tick.
  - **Case 2** (new): a PAD_IDLE worst case -- `launch` (+0.30 throttle)
    paired *pessimistically* with the largest available turn_axis
    magnitude in the whole menu (not the menu's own recommended
    `launch` + `hold_on_pad` pairing, which is turn_axis=0.0 and
    therefore strictly less aggressive than what this check exercises),
    from a real near-zero-speed, low-altitude tick (the first recorded
    sample -- the closest real stand-in this log has for an actual pad
    state).
  - **Result:** `uv run python3 hackathon/optionA/cartesian_check.py`
    -- both cases report `collided=False`. **PASS.** Case 2's final
    altitude goes slightly negative (h=-58.9m) from this near-ground
    starting sample, same as Case 1 and same as the original
    Checkpoint 1 finding -- confirmed this is the same pre-existing
    low-altitude terrain-resolution/gravity artifact already flagged in
    Checkpoint 1 (it happens at zero throttle too), not something
    introduced by `launch`. The structural safety argument is unchanged
    and, if anything, strengthened: `launch` sits at the *same* hard
    clamp boundary the existing menu already relied on (+0.30 vs. the
    previous max of +0.20, both inside `MAX_THROTTLE_STEP=0.3`), and
    `hold_on_pad` is a zero-magnitude command, so neither choice
    required loosening any existing bound.
- `hackathon/optionA/test_checkpoint6.py` (new): makes a REAL
  `/v1/systemone` call (via `SystemOneClient.ask()`, no `act()` call
  anywhere in the file) against a real recorded low-altitude tick from
  `manual_flight_log.jsonl`, built as an explicit PAD_IDLE state
  (`phase="PAD_IDLE"`, `throttle=0.0`) using the same real-telemetry
  approach as `test_checkpoint1.py`. Confirms answers are sane, in the
  (now-expanded) menu vocabulary, and confidence-bounded.

**Real-telemetry confidence result (`test_checkpoint6.py`, a genuine
tsAI classification call, not simulated):**
```
throttle_action: choice='hold' confidence=0.6
pitch_action:    choice='hold_on_pad' confidence=1.0
```
Compare to Checkpoint 4/5's actual live PAD_IDLE run under the OLD menu
wording: `throttle_action` confidence 0.13-0.22 (well below the 0.5
routine floor) and `pitch_action` mostly `insufficient_data` at
confidence 0.24-0.46 (also below floor). The new PAD_IDLE-specific
framing took `throttle_action` from consistently-rejected to
consistently-accepted-band and `pitch_action` from
mostly-insufficient-data to fully confident -- a real, measured
improvement from the menu-wording fix, not an assumption.

**End-to-end confirmation (`--mode replay --max-cycles 6`, no live game
involved):** across the log's early, genuinely PAD_IDLE-phase cycles
(0-4: throttle 0, altitude 63.5m, negligible speed -- `build_cycle_state`'s
own phase-detection logic classifies these as PAD_IDLE), the loop now
gets `throttle_action='hold'` at confidence 0.63-0.79 (ACCEPT, caution
or normal band) and `pitch_action='hold_on_pad'` at confidence 1.0
(ACCEPT, normal band) every cycle -- both cleanly accepted rather than
rejected, and both correctly resolving to a zero-command hold (the
vehicle never received a `launch` answer from this particular log,
which is itself expected and correct: this log is an altitude-hold
test, not a real launch-readiness profile, so there is no real evidence
in it that should make tsAI choose `launch`). Cycle 5 (where the log's
phase shifts away from PAD_IDLE) reverts to the previously-documented
low-confidence ascent-framing rejections, unchanged from Checkpoint 4/5
behavior -- confirming the fix is scoped to PAD_IDLE and did not alter
ascent-phase behavior.

**Why a live re-run to see an actual `launch` accepted/sent was NOT
attempted (documented per this session's instructions, not silently
skipped):** confirming that the new `launch` choice would actually be
chosen, accepted by the confidence gate, and result in a real nonzero
throttle command reaching the game would require either (a) a live SFS
session with a craft in a genuine, evidence-rich PAD_IDLE state with a
real mission target that plausibly justifies immediate launch, run
through `--mode live`, or (b) accepting a lucky confidence roll on the
same ambiguous replay log used above. Both would risk -- or in case (a),
require as the very definition of success -- a real nonzero throttle
command reaching the live game, which this session's hard constraint
explicitly prohibits regardless of how confident tsAI's answer might
be. This is left as a documented follow-up: the NEXT attended
Checkpoint 4-style live dry run (with a human able to watch and abort)
is the right place to observe whether `launch` is actually selected and
correctly gated on a real PAD_IDLE craft, not this unattended session.

**Exit check result:** `uv run python3 hackathon/optionA/cartesian_check.py`
-- PASS, both cases (sec 4.3 point 4 re-run, as required before
considering this fix done). `uv run python3 hackathon/optionA/test_checkpoint6.py`
-- PASS. Pre-existing `test_checkpoint{1,2,3}.py` re-run to confirm no
regression from the menu changes -- all three still PASS unchanged.
`--mode replay --max-cycles 6` re-run end-to-end -- confirms the fix's
effect on real loop behavior (PAD_IDLE cycles now ACCEPT instead of
REJECT) without any live game involvement.

**Commit:** `checkpoint 6: PAD_IDLE menu framing fix + re-validated Cartesian check`

## Checkpoint 7 — First attended live launches, four real bugs found and fixed, throttle_score switch, coast_apoapsis physics hint

**Attended session, human watching throughout, multiple real `--mode
live` runs, several real crashes/overshoots and reverts along the way.**
This is the checkpoint Checkpoint 6 explicitly deferred to. Summarized
here rather than at the same per-run detail level as Checkpoints 1-6 --
see the Weave project `sfs-ai-hackathon` for full per-cycle traces of
every run this session.

**Four real bugs found live and fixed, in order:**
1. **HOLD-LAST double-applied throttle deltas.** `launch`'s old +0.30
   delta got replayed a second time by HOLD-LAST on the very next
   missed/rejected cycle (confirmed live: 0.30 -> 0.60 with no real
   tsAI decision behind the second jump). Generalized fix: throttle is
   persistent/cumulative state, unlike turn_axis (a fresh per-cycle
   rate command) -- HOLD-LAST for throttle now always means "hold
   steady," never replays a delta, regardless of what was last
   accepted.
2. **`prediction` was permanently a null stub.** `build_cycle_state()`
   always called `build_prediction_block(None, ...)` -- real
   `predict()`/`observe_to_state()` (pure forward-sim, no live game
   I/O) is now actually wired in every cycle, live and replay both.
3. **No loud signal when the script's own control ended mid-flight.**
   Added a best-effort final-state check in `run_live()`'s `finally`
   block -- logs `[ATTENTION]` with real altitude/vertical-speed if the
   craft is still meaningfully airborne when the run exits, since
   pilot_loop.py ending does not mean the game stops.
4. **`launch` fired master+throttle but never actually armed the
   engines.** `stage_check` correctly says `hold_stage` on a fresh
   full-fuel stage, so engines were never armed via that path --
   `launch` now bundles `master on` + `stage <active_stage_index>` +
   throttle together, routed through the same `StagingTracker`
   idempotency `stage_check` uses.

**Christian's explicit design changes, same session:**
- `launch` sets throttle to 100% directly (not a delta), sent with
  `allow_full_authority` to bypass the normal per-call clamp.
- `mass_t`/`thrust_to_weight_max`/`thrust_to_weight_current` added to
  `state.vehicle` (real finding: craft sat at throttle 0.30 producing
  T/W<1, unable to lift off, with no way for tsAI to know that).
- Mission-profile-aware pitch menu (`mission_profile()`/`build_menus()`
  in `menus.py`): `periapsis_m<=0` now derives a `vertical_hop` profile
  with pitch instructions that say `hold` is DEFAULT-correct and
  `prograde`/`retrograde` are NOT an altitude fix -- fixes a real live
  finding where the old generic "gravity-turn shaping" framing left
  pitch genuinely torn between prograde/retrograde for an entire flight
  that had no orbit to shape toward.
- **`throttle_action` (choice, 6 fixed buckets) replaced by two
  questions:** `launch_decision` (choice, PAD_IDLE-only binary) +
  `throttle_score` (score, continuous, ASCENT_GRAVITY_TURN-only).
  Motivated by a real live finding: a genuine correction need split
  3 ways across adjacent discrete buckets (0.39/0.34/0.18), never
  clearing the 0.5 confidence floor even though ~0.57 combined
  probability agreed on SOME decrease.
- **`score`-type native `confidence` investigated, NOT actually
  broken.** Read as always-0 in early samples; a temporary
  max-probability-derived workaround was built, then REMOVED after
  testing deliberately extreme/unambiguous situations showed native
  confidence tracks real situation clarity correctly (0.94/0.70 when
  genuinely obvious). The real issue was never the confidence field --
  it was genuine model uncertainty about magnitude in a moderate,
  three-way-ambiguous overshoot.
- **`coast_apoapsis_m`/`coast_apoapsis_error_m` added to
  `state.prediction`** (`state_builder.compute_coast_apoapsis_m`):
  closed-form energy-conservation estimate of where the craft would
  coast to if thrust were cut THIS INSTANT, told to tsAI as the
  PRIMARY magnitude signal for `throttle_score`. Directly motivated by
  Christian's framing that tsAI wasn't trained on spaceflight physics,
  so the fix is to hand it pre-computed physics answers instead of
  making it eyeball raw numbers. Re-tested against the exact real
  states that caused an earlier crash: max probability on the correct
  bucket went from 0.36 (3-way split, rejected) to 0.70 (decisively
  concentrated on `cut`, accepted) -- confirmed working on real crash
  data, not just synthetic cases.

**Live outcome, honestly: mixed, real progress, not fully solved.**
Multiple live launches this session, most ending in the craft still
airborne/overshooting at shutdown (`[ATTENTION]` firing as designed)
and Christian reverting. The LAST run of the session (40 cycles, all
four bugs fixed + `coast_apoapsis` hint in place) is the first run
where the pilot ever made a confident, correct, LIVE throttle
correction mid-flight (cycle 14: `score=2.10 conf=0.73 ACCEPT`,
throttle 1.00->0.93, then 0.74 by cycle 15) -- previously unprecedented
in this build. But the correction was insufficient in magnitude (0.74
throttle still T/W~2.3, well above 1.0) and confidence for a FURTHER
correction dropped back into reject territory for the rest of the
flight, so the craft still ended airborne (~14-27km, +500-700 m/s) and
was reverted. `stage_check` correctly recognized low fuel late in the
flight (confidence rose to 0.81) and wanted to stage -- correctly
suppressed by idempotency since stage 0 had already fired, no
double-toggle.

**Explicitly NOT done, carried to next session (Christian's stated
focus):** `cartesian_check.py` has NOT been re-run against `launch` at
100% throttle + bundled stage-arm -- the safety argument for that
combination is flagged unverified in both `menus.py`'s and
`pilot_loop.py`'s docstrings, not re-confirmed. Next session's explicit
focus is different from a re-verification pass, though: how to
communicate with tsAI more efficiently given it was never trained on
spaceflight physics specifically -- reducing how much it has to guess,
since guessing shows up as low confidence and gets correctly rejected.
`coast_apoapsis_m` is one instance of that pattern (hand it a computed
answer, not raw numbers to interpret) and it measurably worked on the
crash-case retest -- but the live run shows one such hint isn't enough
on its own to carry a full flight. See `bookkeeping/active_state.md`
for the concrete next step.

**Commit:** not yet made -- `guardrail.py`/`menus.py`/`pilot_loop.py`/
`state_builder.py` all modified, uncommitted at session end (see
`bookkeeping/active_state.md`).
