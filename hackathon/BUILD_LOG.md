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
