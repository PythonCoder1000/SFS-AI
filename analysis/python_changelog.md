# Python — Changelog

Tracks Python-side work for the SFS agent: physics models, solvers,
analysis scripts, and (later) the design/flight agent code itself.
Not version-numbered like the mod — dated entries, newest first.

---

## 2026-09-06 (continuation, later same session) — aero_torque root-cause dig: one wrong "fix" reverted with real data, one real bug fixed, debug tooling added, regression narrowed but not closed

**Context:** continuing the same day's aero_torque regression (42° median rotation error with aero_torque ON vs 0.48° OFF, on the validated 9-second run). Four real findings, one of which is a self-correction.

**1. Wrong "fix" made and reverted, real evidence not more code-reading.** Earlier the same day, `_derivative()`'s aero-torque `alpha = (torque_z / inertia) * RAD2DEG` was changed to drop RAD2DEG, reasoning Unity's Rigidbody2D is degree-native throughout. Recorded a real flight with `computed:aeroTorque` telemetry (engine off, clean coast): `aeroAlphaDeg / (aeroTorque / rbInertia) = 57.29577735756871` at every sample checked — exact RAD2DEG. Reverted; `torque_z/inertia` is genuinely radians/s² (Unity's real `AddForceAtPosition`/`rb2d.inertia` path, standard physics — NOT the degree-native `ApplyTorque` SAS/manual-turn path, a separate mechanism).

**2. Real fix: gimbal no longer redirects thrust in `_engine_thrust()`.** The code still rotated thrust direction by `gimbal_deg` despite `active_state.md` claiming this was removed. Confirmed via IL (two independent reads): `MoveModule.ApplyAnimation()` writes `localEulerAngles` on `MoveData`'s own `transform` field, a SEPARATE Transform from `EngineModule`'s own — and `EngineModule.FixedUpdate()`'s real force direction uses `EngineModule`'s own transform, never touched by gimbal's animation. Fixed. Empirically tested head-to-head on a real hard-turn (`turn 1` saturated) + active-burn flight: rotation error barely moved (74.3° vs 71.5° median) — real fix, but not the dominant error source.

**3. New capability: `forward_simulate`/`test_against_run_trajectory` gained `debug=True`.** Exposes per-step `force_x/y`, `cop_x/y`, `inertia`, `torque_z`, and alpha under both unit conventions; auto-attaches real `aeroTorque`/`aeroAlphaDeg`/`rbInertia` from telemetry when available for direct per-tick diffing. This is what caught finding #1.

**4. Aero-torque formula validated directly; the real problem is closed-loop state drift, not the formula.** Feeding real recorded theta/velocity/omega into the torque calc (bypassing this module's own integrated state) reproduces real `aeroTorque` within a few percent, tightening over time. But the FULL replay (using this module's own predicted state each step) shows `torque_z` diverging from -0.12 to +78 within 6 seconds on the same clean window, while real torque stays smooth and bounded. Shrinking dt from 0.25 to 0.002 shrinks but does not fix this (converges to a wrong, still ~200x-too-large answer) — ruling out simple numerical/RK4 stiffness as the primary cause. Root cause NOT YET FOUND. Leading candidate, not yet tested: `inertia` is a single static pre-ignition value held constant for the whole sim; real `rbInertia` measured dropping ~20% over just 14s of burn in tonight's own data. See `bookkeeping/active_state.md` for full detail and next steps.

---

## 2026-09-06 (latest) — forward_sim.py: control-schedule timing bug fixed, phantom gimbal torque removed, live torque replay added

**Context:** a gimbal-torque divergence investigation (three separate real
flights, one-engine and six-engine craft) that started by suspecting a
`rotation_direction` sign bug and ended somewhere completely different --
three real, independent bugs found and fixed in one session, plus one real
open question still unresolved.

**1. Real bug, high impact: `_prepare_replay`'s `control_schedule` was built
with the wrong time origin.** `load_control_schedule(..., t0_abs=t0, ...)`
used the flight's ABSOLUTE start time as the schedule's zero-point, but
`forward_simulate`'s step loop queries it with `t_before`/`t_after` that are
ZERO-INDEXED FROM `start_t`. For any `start_t != 0` (every real use of this
replay, since `start_t=0` is rejected by the velocity-estimate check), every
real throttle/turn-axis/RCS lookup during the sim was reading from
`start_t` seconds too early in the real recording -- for a replay starting
right at ignition, this meant reading pre-ignition (all-zero) control state
for the ENTIRE predicted window, regardless of what the real craft was
actually doing. Root-caused by noticing `gimbal_times` stayed frozen at
exactly `0.0` through an entire real full-throttle hard turn. Fixed:
`t0_abs=t0 + start_t`. This single bug explains the apparent
"catastrophic rotation-direction sign error" theory chased across three
flights earlier the same session -- once fixed, sign was confirmed correct
on every craft tested; that theory is walked back, not confirmed.

**2. Real, IL-confirmed finding: gimbal deflection contributes ZERO real
torque, ever.** `EngineModule.thrustNormal` is initialized to `Vector2.up`
in the constructor and is NEVER written anywhere else in the entire
assembly (grepped every reference) -- `RecalculateGimbal()` only ever
touches `gimbal.targetTime` (the purely visual nozzle-animation target).
The force applied in `FixedUpdate()` (`rb2d.AddForceAtPosition(thrustNormal
* thrust * 9.8 * throttle_Out, ...)`) therefore never reflects real gimbal
deflection -- gimbal is cosmetic. Confirmed independently two ways: (a) the
IL read above, and (b) live data -- real angular acceleration stayed
constant across a full 17%->100% gimbal deflection ramp instead of scaling
with deflection angle, on two separate flights. Removed the entire
engine-lever torque contribution from `_derivative()` (`torque_z +=
lx*fy - ly*fx` over `engine_levers`) -- it was modeling a physically
nonexistent mechanism and, combined with bug #3 below, was causing genuine
double-counting once the timing bug (#1) was fixed and real torque started
flowing through correctly.

**3. Real finding: `TorqueModule.torque` (the source of `torque_effective`,
via `Rocket.GetTorque()`) is LIVE-STATE-DEPENDENT, not a fixed per-part
constant -- `getforwardstartinfo`'s pre-ignition snapshot (`throttle=0` at
capture time) was silently missing this entirely for at least one real
engine.** Measured directly on a real craft: `torqueEffectiveLive` (new
probe field, see `mod_changelog.md` v0.61.0) read a flat `5` (capsule only)
pre-ignition, but scaled LINEARLY with real throttle up to `13` at full
throttle during an actual burn (`5 + 8*throttle`) -- confirmed by directly
watching it track a real throttle ramp down to 0 and back up. Added
`torque_field` support end to end: `ControlSchedule.torque_effective(t)`,
`load_control_schedule(..., torque_field=...)`, and a new per-step
`torque_effective_now` in `forward_simulate`'s loop that prefers the LIVE
recorded value over the static `torque_effective` parameter whenever a
`torque_field` is supplied (falls back to the old static behavior
unchanged if not, so no existing caller breaks). `test_against_run` and
`test_against_run_trajectory` both gained a `torque_field` parameter
threaded through to `_prepare_replay`.

**Validated result, all three fixes combined:** on a real, continuously
throttle-varying, actively-tumbling one-engine flight, single-tick formula
validation (live torque against real finite-differenced angular
acceleration) gave **2.31% median error on cleanly-spaced samples** (most
of an earlier 6% figure turned out to be finite-differencing noise from
irregular tick spacing, not a real formula gap) -- and the FULL RK4
integrator, run end to end over a real 9-second window with `drag: True,
aero_torque: False`, tracked real rotation to **0.48 deg median error** and
position to **~13m median error**. This is the first real multi-second
trajectory validation this project has had -- everything before tonight was
either a single-tick check or run against a stale/mismatched craft config.

**Open, unresolved, flagged not solved:** enabling `aero_torque` (drag-
induced torque from the CoP/CoM lever arm) makes the SAME run dramatically
WORSE (42 deg median rotation error, up from 0.48 deg) despite
`aero_torque`'s underlying mechanism being IL-confirmed as a real,
structurally independent force application
(`AeroModule.ApplyForce`->`AddForceAtPosition` at the real CoP, nothing to
do with `torque_effective`/`ApplyTorque`) and previously live-validated on
a DIFFERENT craft (0.9986 correlation, 4.66% median error, capsule
reentry). Root cause not found. Leading unconfirmed suspicion, not yet
checked: a possible frame mismatch between the new real `dragCopX/Y`
(velocity-aligned frame, from the new `AoA_drag_table_*.json` -- see
`mod_changelog.md` v0.62.0) and `worldCenterOfMass` when computing the
lever arm -- both showed coincidentally similar magnitudes (~365) for this
craft, which is exactly the kind of thing that would produce a badly wrong
torque if one is subtly in the wrong frame relative to the other. Needs a
direct numeric check (pull real CoM and a few real CoP values, verify the
DIFFERENCE comes out as a physically sane few-meter lever arm) before doing
anything else with `aero_torque` -- not attempted yet.

---

## 2026-09-05 (latest) — telemetry archive lifecycle refactor: Python side (MCP capability audit + implementation)

**Context:** `SFSProbe.cs` v0.60.0 unified the telemetry archive lifecycle
(single merged flat file, gzip-then-delete-raw on stop, delete-previous-
.gz on next start of the same mode -- see `mod_changelog.md` v0.60.0). This
entry is the Python-side follow-through: an MCP capability audit
(loosely following a generic tool-improvement framework Christian
provided, applied to `sfsprobe_mcp`'s real codebase after actually
reading it, not assumed) that found every one of the 16 flight-file
analysis tools was now silently broken against real archived flights,
plus three genuine capability gaps worth closing in the same pass.

**1. Gzip transparency -- the single highest-leverage fix.**
`analysis/sfs_telemetry.py`'s `load_samples(path)` is the one chokepoint
every flight-file tool routes through (`field_stats`, `field_search`,
`downsample`, `field_at_time`, `flight_summary`, `phase_detect`,
`find_events`, `clean_segments`, `apoapsis_periapsis`, `delta_v`,
`compare_flights`, `noise_floor`, `validate_gravity_drag`,
`regression_check`, `flight_to_csv`, `tag_flight` -- 16 tools). It did a
plain `open()` with zero gzip awareness; since v0.60.0 archives every
flight is a `.gz`, this one function being broken meant all 16 tools
were broken, not just theoretically at-risk. New `_open_samples_file()`
helper detects real gzip magic bytes (`1f 8b`), not just the `.gz`
suffix, and decompresses straight into memory via `gzip.open(path,
"rt")` -- never writes an unzipped copy to disk, per the project's
storage rule of thumb (2026-09-05). One function fixed, sixteen tools
unblocked.

**Same bug, found independently in THREE more places while auditing,
all fixed the same way** (reusing `st.load_samples` instead of
duplicating the fix): `analysis/forward_sim.py`'s `test_against_run()`
(its own raw `open()`), its control-input loader (a second raw `open()`
in the same file), and `prep_demo_data()` (a third, for the interactive
prediction-demo artifact's self-test). None of these were caught by
the original MCP-side audit since they live outside `sfsprobe_mcp/` --
found only because the audit extended into `analysis/` too.

**2. Stale `TRUTH_FILE`/`INPUTS_FILE` constants -- a currently-live bug,
not just future risk.** `sfsprobe_mcp/server.py` still pointed
`_resolve_flight_path(None)` (the "use the live recording" fallback),
`_wait_until` (the `run_flight_script`/`run_and_analyze` live-condition
poller), and `tail_file`'s `truth`/`inputs` targets at `truth.jsonl`/
`inputs.jsonl`, which v0.60.0 merged away in favor of `sample.jsonl`.
Concretely: **any `wait_until` step in a scripted flight was silently
non-functional the moment the mod shipped v0.60.0**, not a hypothetical.
Repointed to new `SAMPLE_FILE`/`ROCKETSTATE_FILE` constants; `tail_file`
gained a `parts` target (tailing the live `rocketstate.jsonl` had no
path at all before this).

**3. `sfsprobe_tag_flight` didn't survive the new auto-delete policy.**
Tagging only ever logged a path string -- under v0.60.0's "new runs
overwrite previous results" policy, that path could get deleted by the
next same-mode recording, silently orphaning the tag. New
`_copy_to_kept(path)` copies the `.gz` into `archive/kept/` (a no-op if
it's already there) before logging; `sfsprobe_tag_flight` now logs the
durable `kept/` path, not the transient archive one. `sfsprobe_list_flights`'
untagged-file glob (`*_truth_*.jsonl`, the old naming) was also stale --
fixed to `telemetry_*_*.jsonl.gz`.

**4. New `sfsprobe_parts_timeline` -- the 'parts' mode (`telemetry
json`) recording had ZERO analysis tooling before this**, despite being
the literal feature built to answer "which fuel tank lost fuel, when
did something break." Rather than forking a parallel tool family
(`get_fuel_drain`/`find_broken_part`/...), one generalized capability:
`st.parts_timeline(samples, name_substring=None)` tracks every part id
(confirmed against `BuildRocketJsonSnapshot`'s real schema in
`SFSProbe.cs`, not assumed) across a recording's snapshots, reporting
first/last resourcePercent and mass per part, which parts vanished
before the recording's final sample (the schema has no explicit
'broken' flag -- disappearance from a later snapshot IS the signal),
and the top 10 by resourcePercent drop. **First real run against this
session's own earlier parts-mode test recording caught something
genuine**: 37 of 38 parts vanished (`partCount` 38->1) -- something
destroyed almost the whole rocket during that live test, previously
unnoticed.

**5. New `sfsprobe_test_against_run` -- the forward integrator's own
end-to-end validation had no MCP wrapper**, despite every OTHER
validation step (`validate_gravity_drag`, `regression_check`,
`noise_floor`) already having one. Straight wrap of
`forward_sim.test_against_run()` (itself fixed under item 1 above).

**6. New `sfsprobe_test_against_run_trajectory` -- the deeper fix.**
Originally scoped as "generalize `divergence_check` into a trajectory
curve"; course-corrected after actually reading `divergence_check`'s
code, since it compares one sample against FIXED SCALAR targets
(`{"h": 5000}`) -- a genuinely different operation from comparing a
PREDICTED trajectory against the ACTUAL one over time, and forcing them
together would have blurred a real semantic boundary rather than
generalized one. The right fix: `forward_simulate()` already returns
the FULL predicted trajectory (`list[dict]`, one entry per RK4 step) --
`test_against_run()` itself only ever looked at `sim[-1]`, discarding
every intermediate step. Refactored the shared setup (real-flight load,
starting-state construction, control-schedule replay) into a new
`_prepare_replay()` helper used by both functions (zero behavior change
for the existing `test_against_run` -- verified by running it against
two real flight files post-refactor and confirming identical validation
behavior), then added `test_against_run_trajectory()`, which walks every
predicted step and compares against the real flight at that timestamp,
reporting position error and rotation error as SEPARATE curves --
directly answering `docs/high_level_checklist.md`'s open item
("characterize forward integrator compounding error separately for
position vs. rotation") that this project had no real per-step data for
before now. Even `test_against_run`'s own single-endpoint check never
reported rotation error at all until this pass.

**Units caught before they became a silent bug:** confirmed against
`docs/sfs_source_reference.md` (not assumed) that `rb2d.rotation` is
degrees and `rb2d.angularVelocity` is deg/s -- Unity's `Rigidbody2D`
convention, NOT radians -- meaning both already match
`forward_simulate`'s own `theta_deg`/`omega_degs` directly. Applying
`math.degrees()` to an already-degree value (the natural first guess)
would have silently produced a rotation error ~57x too large without
ever raising an exception.

**Verification:** `python3 -m py_compile` on all three touched files,
plus a real import + tool-registration smoke test via the project's own
venv (`PYTHONPATH=` cleared to avoid an unrelated `mcp` package shadow
from `mac-terminal-mcp`'s bundled deps) -- confirms all 40 tools
register cleanly (37 original + 3 new). Beyond that, real functional
tests against actual files from this session: `load_samples` against
both a new `.gz` archive AND an old pre-refactor uncompressed `kept/`
file (backward compatible), `flight_summary` end-to-end through the
gzip path, `parts_timeline` against a real parts-mode recording (the
38->1 finding above), and `test_against_run_trajectory` against two
real flight files (both correctly hit the same pre-existing, unmodified
validation error for missing control-input fields -- confirming the
refactor preserved behavior rather than silently changing it). None of
this touched the live game -- pure static analysis against files
already on disk.

**Not done, explicitly deferred (noted per the audit framework's own
"remaining opportunities" step, not silently dropped):** per-engine ISP
for `delta_v` (needs either a new computed telemetry field or an
IL-sourced catalog lookup -- real mod-side work, insufficiently
justified to bundle into a Python-side pass). The `output_TurnAxisTorque`/
`output_DirectionalAxis.x` field-naming mismatch surfaced during
verification (neither of today's real flat-mode recordings had those
exact field names, even in full-telemetry mode) is flagged as a finding
for the NEXT session, not fixed here -- touching it without fully
understanding why the naming differs risked a worse, silent bug.

---

## 2026-09-04 (latest) — `sfsprobe_registry_audit` drift auditor (MCP overhaul Checkpoint 7, part 1)

**Context:** `docs/mcp_overhaul_checkpoint_prompt.md`, Checkpoint 7 /
architecture decision A. Checkpoint 1's `CommandRegistry`/`FieldRegistry`
is now the primary source of truth for `light_search`, but nothing
stops a future command or field from being added to `SFSProbe.cs`
without a matching registry entry -- exactly the "comments as the only
documentation" failure mode the whole overhaul exists to fix. This
closes the loop: a static diff between the registry array literals and
the real case-block/switch parsers that already exist as `light_search`'s
`static_fallback` path.

- **Added `sfsprobe_registry_audit()`** (`sfsprobe_mcp/server.py`, no
  params) -- new `_parse_registry_commands`/`_parse_registry_fields`
  regex-parse `CommandRegistry`/`FieldRegistry`'s array literals straight
  out of `SFSProbe.cs` (scoped to just those two array bodies via
  `_extract_named_array_block`, so a stray unrelated `ProbeCommandInfo`/
  `ProbeFieldInfo` literal elsewhere in the file, if one is ever added,
  can't get silently swept into the diff). Compares against
  `_parse_probe_commands`/`_parse_computed_groups`/`_parse_script_fields`/
  `_parse_literal_telemetry_fields` -- the exact same fallback-parser
  functions `light_search` already uses, not reimplemented. Reports, per
  section (commands / computed field groups / computed output keys /
  script-condition fields / literal telemetry fields): entries present
  in code but missing a registry entry, and entries present in the
  registry with no matching code (stale). Pure source-file parsing, no
  live game or `describe` round-trip needed -- catches drift the moment
  new code is written, before it's ever rebuilt or reloaded.
- **`literal_telemetry_fields` section is deliberately looser than the
  others:** there's no dedicated `FieldRegistry` namespace for "valid
  directly in a scoped `telemetry on <fields>` list" (currently just
  `partCount`) -- by design, per `mod_changelog.md` v0.55.0, its dual
  validity (both a `script-condition` field AND a scoped-telemetry
  literal) is explained via cross-referencing prose in each of its two
  registry entries' `Description`/`RequestAs` text, not a fourth
  namespace tag. This section only flags a literal field with **zero**
  registry entries under any namespace -- a true blind spot, not a
  namespace-shape mismatch. Confirmed against the real registry:
  `partCount` has entries under both `script-condition` and `truth`,
  each explicitly cross-referencing the other -- correctly not flagged.
- **Result, run against the real `SFSProbe.cs` (v0.58.0) via the actual
  `server.py` module (not a fresh reimplementation)**: `"clean": true`
  across every section -- 44/44 commands, 6/6 computed-field groups,
  21/21 computed output keys, 10/10 script-condition fields, 1/1 literal
  telemetry field all present in both the registry and the real code.
  **No drift found** — Checkpoint 1's registry has stayed in sync
  through Checkpoints 2-6 despite the one real code change since it was
  written (`telemetry`'s v0.58.0 mode-validation fix, which touched
  dispatch logic, not the registry or any case/switch label the
  registry describes).
- Implemented as a tool (not a one-off script) specifically so future
  sessions can re-run it after adding a command/field, per the standing
  convention Checkpoint 7 documents in `docs/high_level_checklist.md`.
- Verified: `python -m py_compile`/ast check clean; called directly
  through the real `server.py` module (game not required -- pure static
  analysis) and confirmed the `clean: true` result by hand against the
  actual `CommandRegistry`/`FieldRegistry` source.

**Addendum, same day — Checkpoint 7's live regression pass.** With SFS
launched fresh (v0.58.0, scene `World_PC`, 1 rocket loaded), ran
`sfsprobe_status`/`sfsprobe_ping` directly through `server.py` (both
responded correctly, mod version confirmed live), started a real scoped
telemetry recording (`fields=["partCount", "computed:gimbal"]`), let it
run ~5s (488 samples), stopped it, and read the archived
`flight01_truth_*.jsonl` directly: `partCount` was a clean int (`38`)
on every one of 488 samples, zero nulls; `gimbalOn` was `true`
consistently. Confirms neither the v0.55.0 `partCount` fix nor the
v0.56.1 gimbal engine-selection fix regressed across Checkpoints 1-6's
changes to the surrounding file. Also re-ran a fast-fail check
(`zzznotarealcommand123` -> `UNKNOWN_COMMAND` in 0.31s, `source:
"live_registry"`) and `light_search("parachuteAlphaDeg", domain="field")`
(still correctly resolves the angular-acceleration unit) live through
the actual mod, not a fresh throwaway process -- the exact distinction
Checkpoint 3's false-pass lesson said to keep checking. Full detail and
the corresponding `docs/high_level_checklist.md` bug-status corrections
in that file directly (the `partCount`/gimbal checklist entries were
found stale during this pass -- still listed as open bugs despite being
fixed in v0.55.0/v0.56.1 -- and moved to a "fixed" section as part of
this audit).

---

## 2026-09-04 — MCP overhaul complete (Checkpoints 1-8)

**Checkpoint 8 (cleanup) done same day, after Christian's explicit
confirmation the overhaul was complete and working:**
`docs/mcp_overhaul_checkpoint_prompt.md` deleted -- it was a temporary
implementation prompt, not a permanent project doc, fully superseded by
this entry, the per-checkpoint entries above, `sfsprobe/mod_changelog.md`,
and the real shipped code. `docs/high_level_checklist.md`'s tracking
item moved out of "Tooling bugs — confirmed broken, unfixed" (it was
never actually a bug) into a new "Tooling — MCP overhaul complete"
section and marked done.

Closing summary tying together the deleted checkpoint prompt's
full checkpoint sequence, each already individually changelogged above
and in `sfsprobe/mod_changelog.md`. In one session's work: command/field/
doc discovery moved from regex-parsed source comments to a live,
structured, self-describing C# registry (`CommandRegistry`/
`FieldRegistry`, Checkpoint 1); a unified `light_search` tool superseding
the old `sfsprobe_command_search`/`sfsprobe_telemetry_field_search`
(Checkpoint 2), covering commands, fields, and now
`docs/sfs_physics_reference.md`/`docs/sfs_source_reference.md` prose too
(Checkpoint 4); fast-fail command validation catching a bad leading word
in milliseconds instead of a multi-second timeout (Checkpoint 3, which
also surfaced and fixed a real, separate mod bug --
`telemetry`'s silent-stop-on-typo behavior, v0.58.0); a second tool,
`deep_search`, for real decompiled-IL ground truth when doc prose isn't
trustworthy or doesn't cover something (Checkpoint 5); a zero-context
`sfsprobe_onboarding` orientation tool (Checkpoint 6); and a static
drift auditor plus a full live regression pass confirming none of the
above regressed two known-fixed bugs (`partCount` nulls, wrong-engine
gimbal selection) (Checkpoint 7, this entry's own predecessor).
**Deferred, explicitly out of scope for this overhaul:** replacing the
file-polling `command.txt`/`result.txt` IPC with a real socket protocol
-- tracked as standing future work in `docs/high_level_checklist.md`,
not attempted here. **Honest scope notes carried forward, not silently
dropped:** fast-fail validation is leading-word-only (a bad SECOND word
on an otherwise-valid command, like the original `telemetry snapshot`
mistake, is only caught for `telemetry` specifically, via its own
v0.58.0 fix -- not as a general mechanism); `deep_search` can only ever
match real identifiers, never paraphrased concepts (that's
`light_search`'s doc domain's job); the drift auditor's coverage is
exactly as good as its regex parsers, not fuzzed against hypothetical
registry-literal reformatting.

---

## 2026-09-04 — `sfsprobe_onboarding` orientation tool (MCP overhaul Checkpoint 6)

**Addendum, same day, post-independent-verification:** a `grep` audit
of every quoted error-code-shaped string in `server.py` found the
onboarding text's 10-code list omitted `WAIT_TIMEOUT`. Most of the
other omissions (`FILE_ERROR`/`NOT_IN_BUILD`/`NOT_IN_WORLD`/
`SPAWN_FAILED`/`TYPE_RESOLUTION_FAILED` on `sfsprobe_load_blueprint`,
`NO_NEW_ARCHIVE`/`NO_SAMPLES` on flight-analysis tools) are reasonably
left to each tool's own docstring. `WAIT_TIMEOUT` was worth fixing
specifically: it's similar enough to the already-listed `TIMEOUT` that
a fresh reader could easily assume it's a duplicate or synonym, when
it's actually unrelated — a `warning_code` (not `error_code`) from a
flight-script wait-for-condition step timing out, not a mod
communication failure. Added a clarifying entry distinguishing the two
plus a one-line pointer to the tool-specific codes intentionally left
out. `py_compile`/ast check clean after the edit.

**Context:** `docs/mcp_overhaul_checkpoint_prompt.md`, Checkpoint 6.
The rest of the overhaul (Checkpoints 1–5) makes commands/fields/docs/IL
all discoverable through tools, but a brand-new AI session with zero
project context still had no single place telling it those tools exist,
what order to reach for them in, or what the server's own error codes
mean. This closes that gap.

- **Added `sfsprobe_onboarding()`** (`sfsprobe_mcp/server.py`, no
  params) — returns a short plain-text orientation: what the mod/MCP
  relationship is conceptually (command.txt/result.txt, without
  requiring the caller to touch those files), the standing instruction
  to call `light_search` before guessing any command/field/unit, the
  concrete distinction between `light_search` (fast, live-registry/doc
  backed, handles open-ended conceptual queries) and `deep_search`
  (slower, real decompiled IL, identifier-only), every real error code
  in current use (`TIMEOUT`, `FILE_NOT_FOUND`, `INVALID_PARAM`,
  `UNKNOWN_COMMAND`, `UNKNOWN_ERROR`, `ASSEMBLY_NOT_FOUND`,
  `MONODIS_FAILED`, `NO_ACTIVE_ROCKET`, `PARSE_ERROR`, `MISSING_FIELD`
  — cross-checked against every literal `"error_code"` in the file, not
  guessed), and the four telemetry field namespaces
  (`computed_group`/`computed_output_key`/`script_condition_field`/
  `literal_telemetry_field` from `_build_field_index`) explicitly called
  out as distinct from the live registry's separate `truth`/`inputs`
  namespace tags — an early draft of this text conflated the two, caught
  before shipping by cross-referencing `_build_field_index`'s four
  `kind` values against `SFSProbe.cs`'s `Namespace = "truth"/"inputs"`
  entries directly.
- **Implemented as a `@mcp.tool`, not an `@mcp.resource`.** The plan
  left this an open choice; went with a tool because every other
  capability on this server already is one, tools are guaranteed to
  appear in a caller's tool list and be called proactively, and
  resources buy nothing here since there are no parameters to template.
- Verified: `python -m py_compile` clean; ran the tool function directly
  (no game required, since it's pure static text) and read the output
  cold as a zero-context AI — it correctly leads with "search before
  you guess" and correctly routes to `light_search` first for open-ended
  questions, `deep_search` only for identifier lookups doc prose
  doesn't cover.

---

## 2026-09-04 — `light_search`/`deep_search` split, corrected to a two-level type+member index (MCP overhaul Checkpoint 5)

**Context:** `docs/mcp_overhaul_checkpoint_prompt.md`, Checkpoint 5.
`sfsprobe_search`'s `domain="doc"` (Checkpoint 4) is only as good as
hand-written prose that can drift from ground truth — this project has
already found a doc chunk carrying its own `> **CORRECTION**`
annotation. This checkpoint adds a second tool that goes straight to
the real decompiled game IL instead.

**Mid-checkpoint course-correction, found discussing the design with
Christian:** the first implementation matched query terms against type
names only (via a `monodis --typedef` listing). That's wrong on its own
merits, not just incomplete — IL has **zero comments and zero tags**
(decompilation strips them entirely), so unlike `light_search`'s doc
domain (human prose plus `[CONFIRMED]`/`[PARTIAL]`/`[OPEN]` tags),
`deep_search` can only ever match identifiers: type/method/field names.
A query like `"gimbal"` needs to hit `EngineModule`'s `gimbal` FIELD or
its `RecalculateGimbal` METHOD — not the type name `EngineModule`,
which doesn't contain "gimbal" at all. A type-name-only index would
have silently returned nothing for exactly the queries this tool most
needs to answer. Revised to a genuine two-level index before this
checkpoint's gate was called done:

- **Renamed `sfsprobe_search` → `light_search`** everywhere in
  `server.py` (tool name, function name, comments) — a pure rename,
  behavior identical. `SearchInput` (the Pydantic input class) was
  never named after the tool, so it keeps its name unchanged.
- **New: `ASSEMBLY_PATH`** (env-var-overridable via
  `SFSPROBE_ASSEMBLY_PATH`, same pattern as `SFSPROBE_MOD_DIR`) —
  defaults to the confirmed real Steam install path for
  `Assembly-CSharp.dll`. **New: `MONODIS_BIN`** (env-var-overridable
  via `SFSPROBE_MONODIS`, defaults to `"monodis"` — confirmed present
  at `/opt/homebrew/bin/monodis`).
- **`analysis/il_inventory.py` refactored, not reimplemented.** This
  script already existed (built for the `docs/sfs_reference/` migration)
  and already parsed every `.class` declaration out of a `monodis` IL
  dump into name/namespace/kind/extends/nesting/line-number records —
  exactly the type-level index `deep_search` needs. Its gap: it only
  *counted* `.method`/`.field` declarations per type, never captured
  their names. Fix, per Christian's explicit direction ("a small
  addition to existing logic, not a new architecture"):
  - Its whole top-level parsing block (previously bare module-level
    code that ran and **wrote `docs/sfs_reference/inventory.json` on
    bare import** — a real hazard once another module started
    importing it) is now `parse_il(il_path, capture_members=False)`,
    an importable function. The write-to-`docs/sfs_reference/` side
    effect now only happens under `if __name__ == "__main__":`, so
    importing this module has zero side effects — required for
    `server.py` to import it safely at all.
  - New `capture_members=True` flag: when a `.method`/`.field` line
    matches, also recovers the real name via `_parse_member_name`
    (concatenates the declaration's continuation line(s) — a `.method`
    decl splits its attributes from the return-type/name/params onto a
    `default ...` line, per `sfs_source_reference.md` §A2's gotcha #1 —
    until a `(` appears, then takes the last token before it) and
    appends into new `method_names`/`field_names` lists on that type's
    record. Default `False`, so a plain call is byte-for-byte identical
    to the module's original behavior.
  - **Regression check:** ran the script's own CLI path
    (`capture_members=False`) against the real
    `docs/sfs_reference/inventory.json` and diffed against a pre-change
    backup — identical for all 969 real types except one
    `mentioned_in_old_doc` flag for `Line`, which changed only because
    `docs/sfs_source_reference.md` itself has been edited since that
    file was last generated (expected content drift, not a parsing
    regression). **Restored the WIP file to its original state
    afterward** — this checkpoint doesn't touch `docs/sfs_reference/`,
    per Christian's explicit "don't act on it without asking."
- **`deep_search(query, top_k)` rebuilt as a two-level identifier
  search:**
  1. `_get_member_inventory()` calls `il_inventory.parse_il(path,
     capture_members=True)` against `deep_search`'s own cached full IL
     dump (never `scratch/full_il.txt` — see below), filtered through
     `il_inventory.is_compiler_generated` (also reused, not
     reimplemented), cached in memory keyed on that cache file's mtime.
  2. `_score_deep_matches` tries each type's own name first
     (exact/prefix/substring, then — single-term queries only — a
     tightened `difflib.SequenceMatcher` fuzzy fallback, ratio >0.7),
     then falls through to every method/field name across all types.
     Returns `matched_via` (`"type name"` or `"member name"`) plus the
     specific `matched_members` list, so a caller can see *why* a type
     came back — unlike a doc chunk, an IL class summary doesn't
     explain itself.
  3. **Multi-word queries use AND, not OR, per term against one
     candidate name.** Found during verification: an OR/max-score
     scheme let a genuinely conceptual sentence query — `"why does
     thrust ramp up slowly"` — return several unrelated types, because
     common short words like `"up"` exact-matched a real field named
     `up` (`ArrowkeysDrawer`) and `"thrust"` substring-matched several
     unrelated `thrust` fields, producing noise that made `deep_search`
     look like it (partially) answers conceptual questions when it
     fundamentally cannot. Requiring every term to match within the
     *same* name fixes this: no single real identifier contains all of
     an unrelated sentence's words, so AND naturally yields zero
     matches for that whole query class while still correctly matching
     legitimate multi-word identifier lookups (e.g. `"Recalculate
     Gimbal"` still resolves to `EngineModule.RecalculateGimbal`).
  4. For each matched type, `_extract_class_summary` (unchanged from
     the first pass) ports this project's manual `sig.sh` convention
     (`docs/sfs_source_reference.md` §A2) to Python: finds the type's
     top-level `.class` line in the cached IL dump, then walks forward
     collecting field declarations and flattened method signatures
     until either the class's own closing brace or the first NESTED
     type — whichever comes first. The nested-type stop isn't
     cosmetic: without it the extractor walks into compiler-generated
     closure/nested-interface types and misattributes their members to
     the outer class, a real false positive `sig.sh` itself hit twice
     during manual research (`AeroModule`/`Aero_Rocket`'s phantom
     `output` field; `Rocket`'s phantom abstract `set_Rocket`).
  5. IL dump caching unchanged from the first pass: a full `monodis
     --output=` dump (~0.3s for the real ~290k-line assembly), cached
     at `scratch/.deep_search_cache/assembly_full_il.txt` with a JSON
     sidecar recording the assembly's mtime, re-dumped only when that
     mtime changes. **Deliberately not `scratch/full_il.txt`** —
     Christian's own manual-research scratch file — so a repeatable
     tool call can never clobber work he's mid-way through.
- Response caps each matched type's returned lines at
  `DEEP_SEARCH_MAX_LINES` (250) with a `note` giving the real line
  range in the cache file when a class summary runs longer.
- **Verification (fresh import of the real `server.py`, not through a
  live MCP client connection — no game dependency for either tool path,
  so a fresh-process test is equally valid for correctness; same caveat
  as Checkpoint 4 about the live subprocess not yet having this code):**
  `light_search` re-run against all of Checkpoints 2/4's original
  queries under the new name — all still correct, confirming the rename
  didn't regress anything. `deep_search("gimbal")` (a query that only
  ever existed as a *field*, never a type name) correctly resolves to
  `EngineModule` via `matched_via: "member name"`, listing
  `gimbal`/`gimbalOn`/`RecalculateGimbal`.
  `deep_search("RecalculateGimbal")` resolves the same type via its
  real method name. `deep_search("EngineModule")`'s extracted IL
  contains `hasGimbal`, `engineOn`, and `throttle_Out` (cross-checked
  against `sfs_source_reference.md` §D2.1 — exact match, both
  ultimately read the same real assembly), ~0.08s per call once the IL
  dump/inventory are cached (~0.45s on a fully cold cache).
  `deep_search("parachute")` resolves `ParachuteModule` as the clear top
  hit. `deep_search("why does thrust ramp up slowly")` — the exact
  conceptual-query regression case — now correctly returns zero
  matches with a note pointing at `light_search`'s doc domain instead.
  Confirmed `scratch/full_il.txt`'s mtime unchanged before/after
  every `deep_search` call and every `il_inventory.parse_il` test run.
- **Honest scope note, now documented in the tool's own docstring/input
  schema too (per Christian's explicit ask), not just here:**
  `deep_search` can only ever match real identifiers (type/method/field
  names) — it has no access to comments, prose, or intent, because none
  of that survives decompilation. A query like `"why does thrust ramp
  up slowly"` will always return nothing here, even though
  `light_search`'s `domain="doc"` answers it fine from hand-written
  prose. `deep_search` is for "I roughly know the type/method/field
  name and want ground truth over a doc's summary of it," never for
  open-ended "explain this concept" questions.

---

## 2026-09-04 — Documentation indexing in `sfsprobe_search` (MCP overhaul Checkpoint 4)

**Context:** `docs/mcp_overhaul_checkpoint_prompt.md`, Checkpoint 4.

- **New: `_chunk_doc_file(path)`** — splits one Markdown doc into flat
  chunks, one per `##`/`###`/`####` heading (a chunk runs from its
  heading to the next heading of ANY level, not a nested tree, per the
  checkpoint's spec). Each chunk carries `heading`/`level`/`body`/
  `source_file`/`tags`, with `tags` pulling any
  `[CONFIRMED]`/`[PARTIAL]`/`[OPEN]` markers found in the heading line
  or the first 500 chars of the body (where this project's docs
  actually put them).
- **New: `_resolve_docs()`** — chunks every file in the new `DOC_PATHS`
  constant (`docs/sfs_physics_reference.md`,
  `docs/sfs_source_reference.md`), cached in-memory for
  `DOC_CACHE_TTL_S` (5s, same pattern as `REGISTRY_CACHE_TTL_S`) so
  repeated searches don't re-read+re-chunk the 7,193-line source-
  reference file every call, but an edit to either doc still shows up
  within a few seconds without restarting the server. A missing file is
  skipped, not fatal.
- **`sfsprobe_search`'s `doc` domain** now returns real chunks (`docs`/
  `total_docs`) instead of the Checkpoint-2-era empty stub with a
  `docs_note` explaining it wasn't built yet. Reuses the existing
  `_score_items` term-overlap scorer with `primary_key="heading"` — no
  new scoring logic needed, same as commands (`"name"`) and fields
  (`"key"`).
- 214 total chunks across both files (chunk body sizes: min 0, median
  ~1.3KB, max ~7.3KB — no runaway giant chunks that would blow out a
  tool response).
- **Verification (fresh import of the real `server.py`, not through a
  live MCP client connection — see caveat below):**
  `sfsprobe_search("three layer engine control", domain="doc")` returns
  physics-reference §2.2 Thrust as the top hit, which is genuinely the
  section containing the throttle/master/engineOn three-layer control
  model (confirmed by reading the actual text at that heading, not just
  trusting the heading title). `sfsprobe_search("SOI crossing physics
  mode", domain="doc")` returns both physics-reference §5.4 SOI
  transitions and terrain and source-reference §D4.3 SOI — the
  transition mechanism among its top hits. `domain="all"` on
  `"parachute"` returns 44 commands / 67 fields / 214 docs as three
  separate lists (each independently scored/truncated to `top_k`), so
  the much larger doc corpus can't crowd out commands or fields the way
  a single flat merged ranking might.
- **Honest gap, same shape as Checkpoint 3's lesson:** this was verified
  by importing `server.py` fresh in a throwaway process, not through
  the actual long-lived `sfsprobe_mcp` subprocess a real MCP client
  stays connected to (two such processes were already running from
  before this checkpoint's edits — `ps aux` showed them predating this
  session's changes). Unlike Checkpoint 3's fast-fail validation, this
  domain has zero game-state dependency (pure file parsing, no
  `command.txt`/`probe.log` round-trip), so a fresh-process test is
  equally valid for correctness — but the live client connection still
  won't see any of this code until it's restarted. Flagging so this
  doesn't get silently assumed to already be live.

---

## 2026-09-04 — Fast-fail command validation (MCP overhaul Checkpoint 3)

**Context:** `docs/mcp_overhaul_checkpoint_prompt.md`, Checkpoint 3.

- **New: `_resolve_commands()`**, factored out of `sfsprobe_search`'s
  command domain so it's shared, not duplicated, between search and
  validation (both now agree on exactly what counts as a known
  command). `sfsprobe_search`'s command-domain block now just calls it.
- **New: `_validate_command_line()`** — checks a command's leading word
  against the known set before `sfsprobe_send_command` ever writes to
  `command.txt`. On a miss: immediate `UNKNOWN_COMMAND` error with
  `difflib.get_close_matches` suggestions, zero game round-trip. Fails
  OPEN (skips the check entirely) if the command set can't be resolved
  at all (game unreachable AND `SFSProbe.cs` unreadable) — never blocks
  a real command over an infra hiccup.
- **`sfsprobe_send_batch`** gets the same check applied to every command
  in the batch up front: if ANY leading word is unknown, the WHOLE batch
  is rejected (listing every bad entry + its suggestions) and NOTHING is
  sent — not even the valid entries — since a typo mid-launch-sequence
  is exactly the kind of mistake worth stopping before anything fires.
- **Honest gap found during live verification, not papered over:** the
  checkpoint plan's own worked example — send `'telemetry snapshot'`
  and confirm a fast-fail pointing at `telemetrysnapshot` — does NOT
  actually fast-fail. `telemetry` (the leading word) IS a real command;
  the mistake is the second word/argument, which leading-word-only
  validation is structurally unable to catch. Confirmed live: `'telemetry
  snapshot'` still times out after 5s exactly as before this checkpoint.
  What DOES work, confirmed live: a genuine leading-word typo
  (`'telemetrysnapsho'`) fast-fails in 0.46s with suggestions
  `telemetrysnapshot, telemetry, snapshot`; a bad word inside a batch
  (`'ignit'`) correctly blocks the whole batch with suggestion `ignite`;
  real commands (`ping`, `gimbalinfo`, `achievements`) still round-trip
  normally, unaffected. **This is a scope limitation of leading-word
  validation as specified, not a bug in this implementation** — a full
  fix would need per-command argument-shape validation (e.g. knowing
  `telemetry`'s only valid second words are `on`/`off`), which is a
  materially bigger feature than what Checkpoint 3 scoped. Flagging
  here rather than silently claiming the plan's literal example works.

**Correction, 2026-09-04, found by Christian independently testing
Checkpoint 3 from a separate live MCP session:** the paragraph above
was written from a fresh, short-lived `python3 -c` process that
re-imports `server.py` on every run. The MCP server Christian's client
actually talks to is a long-lived subprocess spawned once by Claude
Desktop -- two of them, both started 19:32:35, well before this
checkpoint's code existed. Python doesn't hot-reload a running
process, so those two processes were still serving the PRE-Checkpoint-3
`server.py` the whole time my own tests "confirmed" it working --
proven by Christian sending `telemetyr on partCount` / `asdfqwerty`
through his session and finding BOTH commands really reached the game
(matching `unknown command: ...` lines in `probe.log` at the exact
timestamps), when a working fast-fail should never touch
`command.txt`/`probe.log` at all.

**Re-verified with the log-based method Christian specified** (send a
bad command, confirm NO matching line appears in `probe.log`, not just
trust the JSON response) after he restarted both his SFS session and
his MCP client connections: `reverifybadcmd777` produced zero trace in
`probe.log` (only the expected `describe` cache-refresh line), 0.42ms
once the registry cache was warm. The validation logic itself was
correct the whole time (case (c) from the original diagnosis: present
in the file, not live in the already-running process) -- the lesson is
that verifying against a fresh throwaway process is not equivalent to
verifying against the actual long-lived server process a real client
connects to. **Going forward, Checkpoint verification should include
checking for and accounting for already-running `sfsprobe_mcp` server
processes** (`ps aux | grep sfsprobe_mcp`), not just testing fresh
imports.

**Context:** `docs/mcp_overhaul_checkpoint_prompt.md`, Checkpoint 2 of the
MCP overhaul (Checkpoint 1 — `SFSProbe.cs`'s `CommandRegistry`/
`FieldRegistry` + `describe` command — already done and live-verified,
see `sfsprobe/mod_changelog.md` v0.57.0).

- **New tool: `sfsprobe_search(query, domain, top_k)`** in
  `sfsprobe_mcp/server.py`, `domain` ∈ `command`/`field`/`doc`/`all`.
  Replaces `sfsprobe_command_search` and `sfsprobe_telemetry_field_search`
  (both removed outright — this project has no external consumers to
  keep a deprecated wrapper for).
- **Resolution order:** tries the mod's `describe` command first (via
  `_get_registry()`, new helper) — the live `CommandRegistry`/
  `FieldRegistry` dump, cached in-memory for `REGISTRY_CACHE_TTL_S`
  (5s) so a rapid sequence of searches doesn't each pay a real game
  round-trip, but never serves data from a previous game session past
  that TTL. Falls back to the existing regex parsers
  (`_parse_probe_commands`, `_build_field_index` — kept, not deleted)
  only when the game/mod isn't reachable (not running, mod too old to
  have `describe`, or a timeout). Every response's `"source"` field
  says which path served it: `"live_registry"` or `"static_fallback"`.
- **New: `_score_items()`**, a single shape-agnostic term-overlap
  scorer shared by both the `command` and `field` domains regardless of
  which source (live registry vs. fallback parser) produced the items
  — replaces the two old per-shape scorers (`_search_probe_commands`,
  `_search_field_index`, both removed) that each had to special-case
  every entry "kind." `_normalize_fallback_field()` gives fallback
  field entries (which have no single shared identity field across
  their five different kinds) a synthetic `key` so the same scorer
  works on them too.
- **`domain="doc"` is part of the schema now but not yet implemented**
  — returns an empty, clearly-labeled result (`docs_note` explains
  why) rather than an error, so this is Checkpoint 4's job and callers
  built against the final four-domain shape won't need to change.
- Verified offline (game not running): `domain="field"` query
  `"parachute"` correctly falls back (`"source": "static_fallback"`)
  and surfaces `parachuteAlphaDeg`/etc. with their real
  `computed:parachuteDrag` request path; `domain="command"` and
  `domain="all"` also verified.
- **Live-verified 2026-09-04** (game running, mod v0.57.0, real
  `describe` round-trip): all four queries that caused real mistakes
  this session now return correct, actionable answers, every one
  tagged `"source": "live_registry"` — `parachuteAlphaDeg` carries the
  "ANGULAR ACCELERATION, NOT an angle" unit warning; `gimbalThrottleOut`
  correctly resolves to `computed:gimbal` instead of being requestable
  bare; `partCount` correctly shows both its real namespaces
  (script-condition vs. truth/scoped-with-special-case); and
  `telemetrysnapshot` resolves correctly under `domain="command"` (the
  exact `telemetry snapshot`-vs-`telemetrysnapshot` confusion this tool
  exists to prevent). `domain="command"` returned 44 entries,
  `domain="field"` returned 67 — matching Checkpoint 1's counts exactly.
  `domain="all"` correctly bundles commands + fields + the doc stub.
  **Checkpoint 2's verification gate is now fully satisfied**, both
  fallback and live-registry paths.

---

## 2026-09-02 — `--test_against_run`: control-input replay, real per-thruster RCS, mass-penalty fix

- **New: `getforwardstartinfo`-driven craft_config.** Added
  `load_craft_config_from_getforwardstartinfo()`, translating the
  probe's new `getforwardstartinfo` command (mod v0.54.0) into
  `forward_simulate`'s `craft_config` -- real per-part thrust/ISP/
  geometry/thresholds read live from the actual rocket, not empirical
  fits or hand-entered guesses. This is what "finishes" the forward
  integrator: it was previously always missing a real data source for
  this input.
- **New: `ControlSchedule` / `load_control_schedule()`.** Replays a
  real flight's REAL recorded control INPUTS
  (`output_TurnAxisTorque`, `output_DirectionalAxis.x/y`, optionally a
  throttle field) as t->value step functions (deliberately NOT
  interpolated -- a real control input is discontinuous between ticks).
  `forward_simulate` gained a `control_schedule` parameter: when
  supplied, turn_axis/directional_axis/throttle come from the real
  recording instead of being predicted (SAS, zero-RCS-input, constant
  throttle). Separates "does the confirmed physics predict correctly"
  from "can this module guess pilot behavior."
- **New: `test_against_run()` + `--test_against_run` CLI flag.** Runs
  the above end-to-end against a real flight and reports predicted vs
  actual height/speed/position error, same methodology as
  `prediction_demo.html`.
- **Real bug found and fixed during this pass (caught by a smoke test
  against tonight's actual flight, not by inspection):** the first
  version of the control_schedule wiring skipped `apply_sas` entirely
  when a schedule was active (reasoning: turn_axis is already resolved,
  don't re-predict it via SAS) -- but `apply_sas` was ALSO the only
  place the confirmed rotation formula's omega UPDATE happened, so
  skipping it silently stopped integrating rotation at all. Caught via
  a real-flight smoke test: predicted theta diverged ~39° over 5s.
  Fixed by splitting `apply_sas` into `compute_turn_axis` (SAS's OWN
  turn_axis prediction) + a new `apply_rotation_update()` (the actual
  physics integration step, given ANY turn_axis regardless of source).
  Re-tested after the fix: predicted theta within **0.029°** of the
  real recorded value over a 5s control-replay window (wrapped mod
  360°) -- aero torque was deliberately zeroed in the smoke test's
  minimal craft_config, which explains the remaining omega-endpoint
  mismatch, not a code issue.
- **`_rcs_force` fully rewritten** to replicate REAL per-thruster
  `TorqueThrust`/`DirectionThrust` selection (confirmed IL, D3.1-D3.3)
  each call, given real per-thruster geometry + thresholds from
  `getforwardstartinfo`, instead of a precomputed static
  `sum_normal_local` direction that could only ever represent rotation,
  never real translational RCS firing (a genuine gap, confirmed missing
  during today's earlier RCS validation session, not a known
  simplification until this rewrite).
- **`compute_turn_axis`/`apply_sas` mass>200t penalty fix:**
  previously expected an already-penalized `torque_effective` constant
  from the caller; now correctly re-derives the penalty from the LIVE
  (possibly integrated, changing) mass every call. Wrong before for any
  sim whose mass crosses 200t mid-burn -- moot for any flight logged so
  far (max mass this project has seen is ~115t), but a real correctness
  fix for future heavier craft.
- **`_engine_thrust` gained `throttle_override`** for the same replay
  mechanism, applied uniformly across all engines (documented
  approximation -- no flight logged so far captured genuine per-engine
  throttle, only `gimbalThrottleOut`'s single-representative-engine
  scoping).
- Everything above is ADDITIVE and backward-compatible: no
  `control_schedule` supplied means identical behavior to before this
  pass (verified via a blind-mode regression check in the same smoke
  test).

---

## 2026-09-02 (later) — `forward_sim.py` parachute drag + rotation VALIDATED

- **Updated `forward_sim.py`'s top-of-file disclaimer** (previously
  "NONE of it has been validated") to reflect the real result of a
  flight this same day: `parachute_drag`'s exact formula as wired into
  this module (confirmed gravity + `parachuteForceX/Y` / real per-tick
  mass) checked against real telemetry — correlation 1.000, 100% sign
  agreement, median error 0.015%. No formula change was needed; the
  IL-confirmed formula was already implemented correctly, this pass
  only updates validation status. Also independently reconfirmed the
  body-fixed rotation formula (theta/omega integration) across 3 real
  staging events on a different flight — resolves the "rotation sign
  convention assumed-not-confirmed" item from the 7 documented
  Bucket-A simplifying assumptions (now 6). See
  `bookkeeping/active_state.md` and `docs/high_level_checklist.md` for
  the full 6-attempt parachute-drag story and the staging-event
  rotation fit. Everything else NEW in the 2026-09-02 Bucket-A
  integration pass (thrust, fuel_burn, gimbal discrete timing as wired
  into this module, RCS force+torque, heat, terrain, staging) remains
  explicitly unvalidated end-to-end in this module.

---

## 2026-09-02 — AoA -> dragArea empirical lookup table (`aoa_dragarea.py`)

- **Built `analysis/aoa_dragarea.py`**, replacing `forward_sim.py`'s
  frozen-starting-value `dragArea` with a per-craft angle-of-attack
  lookup, per the plan recorded in `active_state.md`'s "Immediate next
  experiment". `dragArea` is a deterministic function of AoA alone for
  a fixed rigid craft design — this builds an empirical table straight
  from real telemetry rather than porting live per-part geometry
  (still blocked on the surface-mount-part gap).
- **AoA convention**: `heading = rot + 90` (matches
  `sfs_source_reference.md` §B1.4's `GetRotation()` `ControlModule`
  fallback path, same `atan2(y,x)` frame as velocity heading); `AoA =
  wrap(heading - velocity_heading)` to `[-180, 180]`.
- **No fresh calibration flight needed** — checked the existing
  2026-08-31 aero-torque validation flight
  (`flight01_truth_2026-08-31_19-57-17.jsonl`, 4,969 samples,
  `partCount` stable at 19 throughout) first, per the plan, and it
  already sweeps the full `-180..+180` deg range with a physically
  sensible pattern (`dragArea` minimal `~3.5` near 0 deg AoA, rising to
  `~9-10` i.e. `~2.5-2.8x` at high AoA).
- **Table**: 2-degree bins (180 total), median `dragArea` per bin, 0
  empty bins, 13/180 low-confidence (<5 samples). Saved to
  `analysis/aoa_dragarea_table_capsule_reentry.json`.
- **Held-out validation** (train on even-indexed samples, test on
  odd-indexed, 2,484 test pairs, genuinely unseen during table
  construction): **median error 0.25%, mean 0.31%, p90 0.67%, max
  2.01%** — tight, in the same range as several of this project's other
  confirmed physics formulas.
- **Table is per-craft-design specific**, not general — encodes one
  part list/geometry via a `craft_signature` fingerprint (`heatParts`
  names + `partCount`). Reusing it for a different rocket is invalid; a
  different design needs its own table built the same way.
- **Not yet done**: wiring `lookup_dragarea()` into `forward_sim.py`'s
  `accel()`. That also requires adding rotation state (`theta`,
  angular velocity) to the integrator, plus the confirmed rotation
  formula and aero-torque formula — `dragArea` alone isn't enough
  without the integrator tracking its own evolving orientation.

---

## 2026-09-02 (continued) — wired AoA→dragArea into forward_sim.py; rotation state added; coordinate-frame gotcha found

- **`forward_sim.py` rewritten** with a rotating-state integrator:
  state now includes `theta` (orientation, deg) and `omega` (angular
  velocity, deg/s) alongside the original `px,py,vx,vy,m`. `dragArea`
  is looked up from the AoA table at every RK4 sub-step instead of
  staying frozen at the starting sample's value — the translational
  wiring asked for is fully working and requires no extra live data
  (dragArea is pure geometry, zero altitude/density dependency,
  confirmed via IL).
- **Old frozen-dragArea/no-rotation behavior preserved** as a fallback
  when no `aoa_table` is passed (`forward_simulate(..., aoa_table=None)`)
  — verified byte-for-byte equivalent to the pre-rewrite version on a
  synthetic test case.
- **Aero-torque model implemented** (`compute_aero_torque()`), following
  `sfs_source_reference.md` §C1.10's confirmed formula exactly:
  `torqueZ = (cop_applied - com_local) × F_drag`,
  `alpha_deg = (torqueZ / inertia) * 57.29578`. **Verified numerically**
  against the real live-read snapshot in `sfs_probe_aerotorque.json`:
  reproduced `torqueZ=11.018437336` against the probe's own
  `11.018437386` (float32 rounding only), and
  `alpha_deg=1.5770399538` against `1.5770399570`. The `*57.29578`
  rad→deg factor is **not explicit in the doc's pseudocode but is
  required** — confirmed here for the first time; `sfs_source_reference.md`
  §C1.10 should get a one-line addition noting this.
- **Coordinate-frame gotcha found and documented, not previously
  flagged anywhere:** `dragCopX`/`dragCopY` and `worldCenterOfMass`
  (needed for the torque formula) live in Unity's small-scale LOCAL
  physics frame (floating-origin-relative, order ~10^2–10^3) — **not**
  the same frame as `Location.position` (`px,py`, order ~10^5–10^6,
  used everywhere else in this project for gravity/translation).
  Mixing them (e.g. treating `px,py` as `worldCenterOfMass`) silently
  produces a nonsense torque — caught only because a first attempt at
  computing torque from archived flight data returned exactly 0.0 for
  every single tick, which traced back to this, not (as first
  suspected) to the flight being in vacuum (see below — that was also
  true, but a separate issue).
- **`inertia` and `com_local` are required parameters, deliberately
  not fabricated or defaulted.** A `sfs_probe_aerotorque.json` snapshot
  existed with a real `inertia` value (400.313232421875), but its
  `craft_signature` does NOT match the AoA table's craft (verified via
  `aoa_dragarea.craft_signature` on both flights' first samples) —
  reusing a different craft's inertia would be worse than not modeling
  torque at all, so it was not used. If `inertia`/`com_local` aren't
  supplied, `theta` still advances kinematically from the starting
  `angv`, but `omega` stays frozen (zero-torque assumption) rather than
  silently guessing.
- **Found the AoA table's source flight is entirely above the
  atmosphere** (h=81,510–91,078m, ceiling is 30,000m) — confirmed by
  checking every sample's `h`. The wide AoA sweep used to build the
  table is the craft freely tumbling in vacuum from momentum
  conservation after stage separation, not atmosphere-driven
  weathercocking. Doesn't affect `dragArea`/`centerOfDrag` validity
  (pure geometry, no altitude dependency) but means this flight cannot
  be used to derive or validate real aero-torque magnitude or a
  craft's `rb2d.inertia` — a genuinely different flight (real
  atmospheric descent, h<30,000m) or a fresh live `aerotorque` read is
  needed for that.
- **`aoa_dragarea.py` extended** to bin `dragCopX`/`dragCopY` alongside
  `dragArea` (generalized `build_table`/`lookup_field`, kept
  `lookup_dragarea` as a backward-compatible wrapper). Table rebuilt;
  held-out validation unchanged (median 0.25%, mean 0.31%, p90 0.67%).
- **End-to-end validation against real flight data:**
  - Translational (position/altitude) prediction: mean **0.001% error**
    over four 10s forward-sims from different points in the flight —
    matches the project's established noise floor, confirms the new
    integrator introduces no regressions.
  - Rotation (`theta`) prediction, zero-torque fallback: **works
    exactly where the assumption holds, fails informatively where it
    doesn't.** Real `angv` is nonzero (active tumbling/SAS correction)
    for samples 215–2230, then drops to exactly 0 and stays there
    (SAS-locked steady state) for the rest of the flight. Forward-sims
    started inside the locked window matched real `theta` exactly
    (0.00° error); forward-sims started inside the active window
    diverged substantially (49.7°, 178.5° error at 10s) — expected and
    correct behavior, since the zero-torque model doesn't (and isn't
    meant to) capture SAS's active correction or real time-varying
    torque. Not a bug; documents exactly what this fallback does and
    doesn't cover.
- **Not yet done:** a live `aerotorque` read (`inertia` + `worldCenterOfMass`)
  for the AoA table's actual craft, taken while it's in real atmosphere,
  to activate and validate the full torque model end to end. Also not
  done: modeling SAS itself (fully confirmed, §B1.3/§2.4 — deadbeat
  controller nulling `angularVelocity` within one tick's authority
  whenever `hasControl && !IsOnSurface` and no manual input), which
  would be needed to match real hands-off flight behavior beyond pure
  aero torque.

---

## 2026-09-02 (continued) — SAS added to forward_sim.py; found and documented the RCS torque-damping gap

- **`apply_sas()` added** to `forward_sim.py`, implementing the
  confirmed deadbeat SAS formula
  (`sfs_source_reference.md` §B1.3 / `sfs_physics_reference.md` §2.4)
  exactly: `omega -= torque_effective*57.29578/mass*clamp(omega/delta,-1,1)*dt`.
  Applied once per RK4 outer step (not a fine-grained inner tick loop) --
  **proved mathematically, then confirmed empirically, that a single
  big-step application is EXACT for the pure-SAS mechanism** (chaining
  the real per-tick formula many times over the same window gives an
  identical result, differing only in the 17th decimal place).
- **Validated against this exact craft's own real flight data**
  (same flight the AoA table was built from -- entirely vacuum, so no
  aero-torque confound): using the craft's own real `torque=5` field
  (`SumEnabledTorque`, confirmed via `SFSProbe.cs`) and real per-tick
  mass, single-tick predictions across all 4,168 real hands-off
  (`turnAxis==0`) ticks: **median error exactly 0.0 deg/s**, mean 0.15,
  p90 0.61, max 0.75.
- **Found and documented a real, honest gap, not swept under the rug:**
  the near-zero aggregate error hides that it's concentrated almost
  entirely in low-`|omega|` ticks. Digging into where the larger errors
  cluster: stretches with `|omega| >= 2 deg/s` show a consistent
  ~0.45-0.61 deg/s UNDER-prediction of real deceleration PER TICK,
  compounding to ~30+ deg/s of error over a 1-second window. Root cause
  identified and confirmed, not just suspected: `RcsModule.TorqueThrust`
  (`sfs_source_reference.md` §D3.2) fires RCS thrusters for rotational
  damping whenever `|angularVelocity| >= 2` deg/s -- exactly the regime
  where the gap appears -- and this craft's own recorded `rcsFiring`
  field confirms 5 of 6 RCS thrusters were actively firing throughout
  the high-omega stretches checked. RCS's torque contribution is a
  SEPARATE mechanism (real `AddForceAtPosition` physics, needing
  per-thruster position + `rb2d.inertia` -- same class of missing
  ingredient as the aero-torque model) and is **not modeled**. Net:
  `apply_sas()` is accurate under ~2 deg/s or on any RCS-disabled craft;
  under-predicts real hands-off damping on a spinning RCS-equipped craft.
- **`torque_effective` required as an explicit parameter**, same
  treatment as `inertia`/`com_local` -- never fabricated. For this
  specific craft it's legitimately available from the same flight's own
  `inputs.jsonl` (`torque=5`), not borrowed from a different craft.
- **Also found in passing, while investigating an initial apparent
  discrepancy that turned out not to be a bug:** a low-`|omega|` window
  (angv~0.3 deg/s) where SAS's confirmed formula predicts an immediate
  null but the real craft's angv stayed completely flat for a full
  second. Most likely explanation: `hasControl` was false during that
  window (e.g. camera/focus elsewhere) -- SAS's gate
  (`hasControl && !IsOnSurface`) requires it, and we have no
  per-tick `hasControl` telemetry to confirm either way. Documented as
  an open unknown, not resolved.
- **Regression-checked:** translational (position/altitude) accuracy
  unchanged (0.001% mean error, same four-point test as the dragArea
  wiring); backward-compatible frozen-dragArea path still works
  unmodified.

---

## 2026-09-02 (continued) — isolation flags added to forward_sim.py

- **`flags` parameter added** to `forward_simulate()`/`accel()`/`_rk4_step()`:
  `{"gravity", "drag", "aero_torque", "sas"}`, each defaulting to `True`.
  Lets a divergence between predicted and real be narrowed to ONE
  physics component (e.g. `flags={"drag": False}`) instead of guessed
  at, without needing to strip out the corresponding data
  (`aoa_table`/`inertia`/`com_local`/`torque_effective`) to test it --
  "I have the data but want this off for a test" is now separate from
  "I don't have this data" (the pre-existing `None`-means-off
  behavior); both work independently.
- Unknown flag names raise `ValueError` immediately (fails loud, not
  silently ignored).
- **Verified**: all-flags-off reduces to exact constant-velocity
  straight-line motion (analytic check, not just "looks plausible").
  `flags={"sas": False}` on a real validated case correctly freezes
  omega at its starting value instead of nulling to 0, isolating
  exactly what the flag claims to isolate. Default flags (all `True`)
  reproduce byte-identical results to the pre-flags code on every
  existing regression check (0.001% mean h error, 0.0 deg/s SAS median
  error) -- adding the flag layer introduced no behavior change when
  left at defaults.

---

## 2026-09-02 (continued) — Bucket A fully integrated into forward_sim.py (INTEGRATION-ONLY PASS, no flight validation)

**Scope: every remaining Bucket A item from active_state.md's physics
status list wired into the predictor** -- thrust, fuel burn, gimbal,
RCS (force + torque), parachute drag, staging separation, heat
accumulation, terrain collision. Explicitly NOT validated against any
real flight in this pass -- that was out of scope for the task this was
written under. Backup of the pre-integration file saved as
`forward_sim.py.bak-pre-bucketA`.

**State model expanded**: continuous RK4-integrated state grew from
(px,py,vx,vy,m,theta,omega) to (px,py,vx,vy,m,theta,omega,heat_temp) --
mass is now a real integrated state (was frozen), heat_temp is new.
Discrete post-step state added: gimbal_times (one per gimbaled engine).
SAS/gimbal/RCS/staging/terrain are all DISCRETE post-step corrections
(operator splitting), not blended into the continuous derivative --
matches how SAS was already handled, extended to the new mechanisms for
the same reason (all are genuinely discrete/gated/rate-limited, not
smooth ODEs).

**Formulas used, all pulled directly from sfs_physics_reference.md /
sfs_source_reference.md, re-read this session rather than assumed from
memory:**
- Thrust (section 2.2), fuel-flow rate incl. the `scale` term
  (section 1.3), multi-engine as N independent forces not a resultant
  (section 5.2)
- Gimbal (section B1.10): target = turnAxis_Input * rotation_direction
  = the SAME signal SAS uses (compute_turn_axis() extracted so both
  reuse one implementation); MoveTowards rate-limited chase, confirmed
  linear on the one real engine read live
- RCS (section 5.3): gate is `|turn_axis| >= 0.95 OR |omega| >= 2` --
  **caught and fixed during design, not left in**: an earlier draft
  used `|omega| >= 2` alone and would have MISSED the common case where
  SAS saturates turn_axis to +-1 well before omega reaches 2 deg/s on a
  weak-torque craft. Force per-module (not pooled -- the ~6x
  overstatement mistake already caught once in this project, guarded
  against again here).
- Parachute drag (section 2.8): refactored `_aero_force_and_cop()` to
  match the confirmed pseudocode's pre-density/pre-direction
  intermediate `force` scalar exactly, so base drag and parachute
  blending share ONE implementation (previously would have been
  duplicated between the translation and torque call sites).
- Staging (section 2.7): momentum conservation; angular velocity
  confirmed to carry over unchanged, not touched by a staging event here
- Heat (section 5.1): reused sfs_telemetry.py's ALREADY-VALIDATED
  (0.18% mean peak error) absorb/dissipate rates verbatim rather than
  re-deriving from the formula text, specifically to avoid re-risking
  the additive-vs-multiplicative bug already found and fixed once in
  this project's air-temperature formula
- Terrain (section 5.4): flat-datum fallback when no live
  `terrain_lookup` supplied

**Integration-only validation performed (NOT flight validation)**: syntax
check, then 15 targeted crash/edge-case checks (all-flags-off reduces to
an exact analytic straight line; inertia=0, isp=0, mass->0 without a dry
mass floor, gimbal animation_time=0, r->0 degenerate case, empty
engines/rcs/parachutes lists, unknown flag names, staging ejecting more
mass than exists, terrain collision early-stop, backward-compat frozen
path) plus 40 randomized-parameter trials checking every output field
stays finite (no NaN/Inf) across random combinations of engines/RCS/
parachutes/staging/inertia-presence/terrain. All passed. Built and
syntax/crash-tested in an isolated sandbox first, transferred only after
passing, to avoid leaving a broken file on a real machine mid-session.

**Known deviations/assumptions, honestly flagged, not silently
buried -- see the integration report for the full writeup:**
1. Body-fixed vector rotation convention (CCW-positive, standard Unity
   default) is ASSUMED, not independently IL-confirmed for arbitrary
   part positions specifically.
2. RCS/SAS/gimbal execution order within one step is a REASONED,
   defensible choice (matches the confirmed pseudocode's described
   order), not proven to exactly match Unity's actual per-tick script
   execution order (which this project's own docs note is NOT a
   guaranteed call chain elsewhere).
3. Heat is a single representative "hottest part" scalar, not full
   per-part tracking (a real scope limit, not an approximation
   presented as complete).
4. Parachute drag_curve uses linear interpolation, not the real Hermite
   AnimationCurve (no real chute keyframes have been read live, unlike
   the one gimbal curve that was).
5. Gimbal's discrete big-step timing has NOT been proven exact under
   RK4 operator splitting the way SAS's deadbeat law was (SAS's
   telescoping proof doesn't extend to gimbal's different, rate-limited-
   toward-a-moving-target mechanism).
6. Staging's velocity-kick term (`eject_delta_v_local`) has no source of
   real values -- `separationForce` is an unread parametric expression
   for any specific craft; defaults to zero (pure mass drop) unless the
   caller supplies real data.
7. `position_local` for engines/RCS/parachutes is defined here as
   CoM-relative by this module's own convention, not something
   IL-confirmed to be suppliable directly in that frame -- caller's job
   to get this right.

---

## 2026-08-30 (later same day) — heat formula bug found and fixed via direct live comparison; HEAT FULLY CLOSED

- **Root-caused and fixed a real transcription bug** in
  `predicted_reentry_temperature`'s ascent-correction term. An earlier
  documentation pass recorded it as multiplicative
  (`t += t * (tempOffset·X + 0.2)`); the real IL (re-read directly from
  `scratch/full_il.txt`, not re-derived from the old doc) is additive:
  `t += tempOffset · (X + 0.2)`. With `tempOffset=-500` confirmed live,
  the wrong multiplicative version drove `t` deeply negative whenever
  the ascent term neared its `0.4` cap, silently collapsing the whole
  formula to `0` during real ascent-phase heating — which is exactly
  the symptom that led to catching this: a live-vs-Python comparison
  (`realAirTemp`, a new sfsprobe v0.43.0 telemetry field calling
  `AeroModule.GetTemperatureAndShockwave` directly) showed the real
  game reporting up to 1439°C air temperature during ascent while the
  Python formula returned exactly 0.00 at the same instants.
- **Verified against the game's own live computation, not just
  self-consistency:** 2,989 real samples across a full ascent-to-
  reentry flight, comparing `predicted_reentry_temperature`'s output
  directly against `AeroModule.GetTemperatureAndShockwave`'s real
  return value at the same tick. **Median error 0.0000%, mean 0.0001%,
  max 0.0047%** — effectively exact, floating-point-level agreement.
- **This also fully explains the ~50% heat-accumulation overprediction**
  chased earlier the same session (which the `ExposedSurface`-filtering
  fix, v0.41.0, only partially closed to ~46.6%): the wrong
  multiplicative version added a spurious ~20% bonus to `t` every
  single tick during descent, and that error compounds across the
  ~1000+ ticks of a real reentry integration far more than a one-off
  formula error would suggest.
- **Re-ran the full per-part `ApplyHeat`/`DissipateHeat` accumulation
  model** (same one built earlier this session, now using both the
  corrected formula and the correctly-filtered `ExposedSurface`) against
  a real destruction event (3 Hawk Engines, symmetric, all crossing the
  confirmed 412°C threshold together): **mean peak-temperature error
  0.18%** across all 7 heated parts (0.09–0.30% individually) — tighter
  than or matching every other confirmed formula in this project
  (drag: 0.098%, gravity: 0.008–0.13%, multi-engine: 0.14%).
- **Heat is now fully closed**: formula confirmed exact against the
  game's own live output, full accumulation model validated against a
  real destruction event, coefficients read live, `ExposedSurface`
  correctly filtered through the real `RemoveHighSlopeSurfaces`/
  `ApplyProtectionZone`. No remaining open items in the heat model
  itself — only RCS and terrain remain unvalidated among the original
  four "confirmed from code, untested live" physics items.

---

## 2026-08-30 (later same day) — multi-engine LIVE-VALIDATED

- **Real flight test of the "no summation, N independent forces" model**
  (confirmed via IL in an earlier session, never flight-tested until
  now). Christian hand-built a real symmetric 3-engine rocket in the
  editor (three parallel Fuel Tank+Engine Hawk columns at x=8/10/12,
  shared capsule+parachute+nose cones) after magnet-based stacking
  turned out unable to place two engines in series (an engine is a
  single-connector "cap" part — real, useful negative finding, logged
  in `blueprint_builder.py`'s docstring context).
- Flew it full-throttle for ~26s (1,594 samples). Validation method:
  sum 3 independent per-engine thrust contributions (each
  `thrustNormal · thrust · 9.8 · throttle_Out`, no shared resultant —
  this IS the "no summation" model, not a simplification of it) plus
  the confirmed gravity+drag formula, compare against measured
  (finite-difference) acceleration.
- **Result: 1,576 clean pairs, median error 0.14%, mean 0.21%** —
  tighter than the 0.098%-median drag validation, this project's
  previous best. Strong, direct confirmation the multi-engine model is
  correct, not just plausible.
- **18 outlier pairs found and explained, not silently dropped:** 16
  were a finite-difference artifact — one tick in the recording had
  irregular (half-length) spacing, which distorts a central-difference
  "measured" acceleration that assumes even spacing. The remaining 2
  were a genuine one-tick `engineOn` flicker on a single engine (all 3
  on at one sample, one dropped to off+throttle 0 the very next sample,
  then presumably back on), most likely an asynchronous fuel-draw
  transient across the rocket's 3 separate tanks — not investigated
  further, flagged rather than hidden.
- `partCount` held at 10 for the entire burn, confirming the hand-built
  rocket was genuinely one rigid connected craft, not three separate
  physics bodies that happened to look adjacent.
- **This flight is also what surfaced sfsprobe's long-standing
  `AmbiguousMatchException`** on engine reads clearly enough to finally
  root-cause and fix it (v0.37.0, see `mod_changelog.md`) — a pad-idle
  sanity check before this flight showed EVERY engine read failing, not
  the rare one-off it had previously looked like.

---

## 2026-08-30 — `predicted_reentry_temperature` (AeroFormula.GetTemperature port)

- **Added to `sfs_telemetry.py`: `predicted_reentry_temperature` +
  `predicted_reentry_temperature_for_sample`.** Full port of
  `AeroFormula.GetTemperature`, confirmed via IL
  (`docs/sfs_reference/02-drag-aero/AeroFormula.md`), now runnable end
  to end because the last two unknowns got read live today:
  - The 4 `AeroFormula` coefficients (`velPow=1.85`, `densityPow=2.2`,
    `tempOffset=-500`, `m=1.47`) via the new `aeroformula` probe command
    (sfsprobe v0.36.0).
  - Earth's `atmospherePhysics.minHeatingVelocityMultiplier=1.0` and
    `shockwaveIntensity=1.0` via the new `atmophysics` probe command
    (sfsprobe v0.36.1) — the ctor default happened to match, but per the
    project's data-trust rule this was read, not assumed.
  Difficulty multipliers (`HeatVelocityMultiplier`/
  `MinHeatVelocityMultiplier`) are assumed **Normal** (1.0/1.0), matching
  every other empirical check this project has run (e.g. `ispMultiplier
  = 1.0000`) — flag if a flight was ever actually run on Hard/Realistic.
- **This is the GLOBAL instantaneous air temperature (the forcing
  input), not a per-part accumulated temperature.** `HeatManager
  .ApplyHeat`'s absorption/dissipation integration over time is a
  separate step, **not yet implemented in Python** — this function
  answers "how hot is the air right now", not "how hot has this part
  gotten."
- **Sanity-checked against the real 73,108-sample reentry flight**
  (`flight01_2026-08-29`, the same one behind the 0.098%-error drag
  validation): predicted air temperature is essentially zero for the
  whole vacuum-coast portion above 30km (atmosphere cutoff engaging
  correctly), then ramps sharply exactly during the real high-speed
  low-altitude descent (~t=1089–1100s, h≈20,000m→10,000m, v≈1700m/s),
  peaking near 5900°C as *air* temperature — physically consistent with
  why the actual PART temperature (subject to slow absorption) crossed
  the 412°C break threshold and started shedding parts right around
  that same window. Not a full validation (that needs the part-level
  integration plus a fresh flight recorded with the fixed `GetHeatState`
  — see below), but strong corroborating evidence the formula's right
  before investing in that integration layer.
- **Next step:** implement `HeatManager.ApplyHeat`/`DissipateHeat`'s
  per-part accumulation in Python, then fly a fresh reentry (the
  existing archived flight predates the `GetHeatState` fix in sfsprobe
  v0.36.0, so its `maxTemp` telemetry may be silently wrong for any
  `HeatModule`-carrying part) to get real per-part temperature data to
  validate the full accumulation model against, not just this
  instantaneous forcing-function sanity check.

---

## 2026-08-29 (later same day) — forward_sim.py + interactive trajectory-prediction demo

- **Added `python/forward_sim.py`.** Forward-integrates (RK4, not Euler)
  the CONFIRMED gravity+drag formula — a verbatim port of
  `sfs_telemetry.py`'s `predicted_gravity_drag_accel`/
  `atmospheric_density`, not reimplemented from scratch — starting from
  any real telemetry sample, for a chosen duration. Built to power an
  interactive predicted-vs-actual trajectory demo using the exact
  physics validated that same day at 0.098% median error across 70,858
  pairs (see `docs/high_level_checklist.md`, "Drag FORCE formula").

  `dragArea` is deliberately held constant at the starting sample's
  real value for the whole prediction window — a documented
  simplification (valid for an unpowered coast, where orientation stays
  roughly fixed), not an oversight; noted in the module docstring as
  something that would need revisiting for a window including active
  thrust/rotation/staging.

  `prep_demo_data()` loads a real archived flight, downsamples it for
  embedding in a UI, and runs a **self-test** before shipping any
  numbers into a demo: a 10s forward-simulation from a real mid-flight
  sample, compared against the ACTUAL recorded trajectory at the
  matching later timestamp. Against the real 73,108-sample drag-
  validation flight: **0.0001% altitude error** — confirms the RK4 port
  matches the validated formula before any UI gets built on top of it,
  rather than assuming the port is correct.

- **Built an interactive React artifact** (`TrajectoryPredictor.jsx`,
  delivered directly, not committed to this repo) on top of
  `forward_sim.py`'s output: pick a real sample (slider) and a
  prediction duration (slider), see the live-computed predicted
  trajectory (JS port of the same RK4 physics) overlaid on the real
  recorded one, with a numeric predicted-vs-actual comparison at the
  end of the window. Deliberately surfaces the real, still-unexplained
  divergence zone found during validation (26–30km altitude,
  high-speed ascent) as a shaded region when a chosen window crosses
  it, rather than hiding a known limitation behind a clean-looking demo.

## 2026-08-29 (later same day) — blueprint_builder.py + sfsprobe_build_stack_blueprint

- **Added `python/blueprint_builder.py`** — builds SFS blueprints from a
  part list using REAL, empirically-confirmed magnet-point data instead
  of guessed positions. Confirmed 2026-08-29 against a real hand-built,
  connected 4-part rocket (see `docs/high_level_checklist.md`,
  "Blueprint construction"): SFS's part-connection system is
  `SFS.Builds.HoldGrid` + `MagnetModule`, not a coordinate-snap grid. A
  part's own position ("pivot") is NOT its geometric center —
  `MagnetModule.points` are local offsets FROM that pivot. The
  magnet-chain formula (`next_pivot = prev_pivot + prev_exit_offset -
  next_entry_offset`) is exact against real data, not derived from the
  centerOfMass/height heuristics tried first (which produced a
  too-narrow tank and an overlapping parachute).

  Pure, testable functions, no game interaction: `scout_blueprint`
  (rough far-apart placement, just to turn parts into placed instances
  so their real magnet points become readable), `build_stack_from_scout`
  (the actual chaining math + centering — also the fix for the
  "blueprints end up off to the side" bug), `write_blueprint`,
  `check_connectivity` (uses the game's own live `occupied` flag rather
  than reimplementing collision geometry). Sanity-tested directly
  against today's real confirmed numbers — relative spacing matched
  exactly.

  **Explicit, deliberate limitation:** parts with no `MagnetModule`
  (`magnetPoints: null`, confirmed for `Parachute`, `Parachute Side`,
  `Side Separator` — likely all "surface-mount" parts) raise
  `SurfaceMountPartError` rather than silently guessing a position. Real
  geometry/edge-matching (`HoldGrid.CollectSurfaceSnaps`) is a separate,
  harder, deliberately-deferred problem — see the checklist.

- **Added `sfsprobe_build_stack_blueprint`** to `sfsprobe_mcp` — the live
  orchestration on top of the pure module: scout-place → read real
  magnet points via the mod's `getplacedmagnets` (v0.35.5) → compute the
  correct stack → write and load the final blueprint → re-verify real
  connectivity via the `occupied` flag rather than assuming success from
  a successful load call alone. Compiles and imports clean. **Not yet
  live-tested end to end** — the underlying primitives
  (`loadblueprintbuild`, `getplacedmagnets`) are each individually
  confirmed working; this specific new orchestration hasn't been run.

## 2026-08-29 — reference_audit.py (template compliance checker)

- **New `python/reference_audit.py`.** Mechanically enforces the
  `Preconditions` rule added to `docs/sfs_reference_plan.md` the same day:
  every `#### ` method entry under a **FULL**-depth type must carry a
  `- **Preconditions:**` bullet. An absent field looks identical to "not
  checked yet", which is precisely the gap behind the `loadblueprint`
  `World_PC`/`Build_PC` incident, so it is checked by a script rather than
  by discipline.
- Also reports FULL-depth types that document **no** method entries at all.
  Not a failure — many types genuinely have none beyond a
  compiler-generated constructor — but a FULL-depth type with no methods
  written up is worth eyeballing.
- Two modes, matching `reference_index.py`'s convention:

  ```bash
  python3 python/reference_audit.py            # full report
  python3 python/reference_audit.py --check    # silent on pass, exit 1 on fail
  ```

- **First run found 166 of 216 FULL-depth method entries missing the
  field** — every one of them in the 43 files produced by Phase 1 Step 1
  (migration), which predates the rule. The four Step 2 files written on
  2026-08-29 pass. Backfilling the migrated corpus is tracked in the
  session handoff, not done here.
- Skips the five standalone files (`INVENTORY.md`, `INDEX.md`,
  `METHODOLOGY.md`, `REFLECTION_TOOLKIT.md`, `CORRECTIONS.md`), which
  deliberately do not follow the per-class template.

---

## 2026-08-29 — blueprints/ folder + sfsprobe_load_blueprint tool

- **Created `blueprints/`** at the project root, split into `research/`
  (usable now — hand-crafted/exploratory designs, including the first
  test blueprint `single_capsule`) and `live/` (not used yet — reserved
  for once the design agent is built and connected, kept separate so
  it's always clear which designs came from a human/manual process vs.
  the agent itself).
- **`sfsprobe_load_blueprint`** added to `sfsprobe_mcp` (Stage 12) —
  wraps the new mod command (`loadblueprint`, v0.30.0). Resolves a
  blueprint by `name` (looked up in `blueprints/research/`) or an
  explicit `path`, sends the command, and maps the mod's distinct
  `reason=` failure tokens to proper `error_code` values
  (`NOT_IN_DESIGN`, `FILE_NOT_FOUND`, `FILE_ERROR`,
  `TYPE_RESOLUTION_FAILED`, `PARSE_ERROR`, `SPAWN_FAILED`) — exactly the
  distinguishable-failure-reasons behavior asked for, not one generic
  error.
- Path-resolution logic (name lookup, missing-blueprint case,
  missing-both-name-and-path case) smoke-tested directly — all correct.
  **The actual spawn call itself has not been tested live yet** —
  needs a game reload (to pick up mod v0.30.0) and a Claude Desktop
  restart (to pick up the new MCP tool). Genuinely untested-live territory
  per the mod changelog's own caveat — treat the first real call as an
  experiment.

---

## 2026-08-28 (later same day) — sfs_telemetry.py + 24 new sfsprobe_mcp tools

- **Created `python/sfs_telemetry.py`** — pulls `analyze_dragarea.py`'s
  analysis logic (sample loading, planet constants, atmospheric density,
  clean-segment detection, predicted-vs-measured validation) out into a
  real importable module, generalized rather than drag-specific.
  `analyze_dragarea.py` still works standalone as a thin CLI.
  New capabilities beyond what the script had: `field_stats`,
  `search_field`, `downsample`, `field_at_time` (Stage 1 -- generic
  stats/search, not built ad-hoc per question anymore); `flight_summary`,
  `detect_phases`, `find_events` (Stage 2 -- heuristic phase segmentation
  and named/indexable event detection: engine_start/cutoff, apoapsis,
  periapsis, max_velocity, max_dynamic_pressure, part_count_drop with a
  heuristic destruction-vs-separation guess, impact); `resolve_scope`
  (Stage 3 -- lets other tools restrict analysis to a phase or a window
  around/before/after a named event); `validate_gravity_drag` (Stage 4,
  generalized from the script, now scope-aware), `noise_floor` (the
  determinism check from the original architecture doc), `find_clean_segments`
  (coast or burn, exposed standalone); `compute_apoapsis_periapsis`,
  `estimate_delta_v` (Stage 5 -- ISP not reliably in telemetry, honestly
  returns a note rather than a fabricated number if not supplied),
  `compare_flights` (Stage 6); `rocket_summary`, `part_lookup` (Stage 8 --
  from a live `snapshot` dump, real mass values, best-effort thrust/ISP).

- **Fixed a real bug found while building `flight_summary`**: `location.time`
  ('t' in telemetry) is NOT guaranteed monotonic across an archived flight
  — found on flight01 (crashed), which gave a negative duration when
  naively computed as last-t minus first-t. `flight_summary` now detects
  this and returns a `time_anomaly` note plus a max(t)-min(t) fallback
  instead of a silently wrong negative number. Root cause not yet
  confirmed (candidates: `ActiveRocket()` switching tracked object after
  a part-count event, or a scene/object handoff resetting the clock).

- **Added 24 new tools to `sfsprobe_mcp`** across Stages 1–11 (data
  analysis breadth, flight orchestration) — see `sfsprobe_mcp/README.md`
  for the full list and `mod_changelog.md`... actually there is no mod
  change here, this is Python/MCP-only, no `SFSProbe.cs` touched. New
  tool categories: generic stats/search/downsample; flight summary/phase/
  event detection; scoped analysis (phase- or event-relative, e.g. "drag
  error during the last 10s before impact"); generalized formula
  validation + noise-floor determinism check; apoapsis/periapsis/delta-v/
  divergence-check derived metrics; flight comparison + regression check
  ("does our mod still work" after an SFS update); bookkeeping
  (`list_flights`/`tag_flight`/`flight_to_csv` writing to a new
  `flights_log.jsonl` at the project root, so results stop evaporating
  between sessions); live rocket/part summary from a `snapshot` dump;
  `checklist_status` parsing `high_level_checklist.md`; and scripted
  flight orchestration (`run_flight_script` — ordered command batches,
  fixed delays, and **live-telemetry-condition waits**, e.g. cut engine
  once altitude exceeds X, repeatable across rocket designs unlike a
  fixed-time script; `run_and_analyze` closes the test-analyze loop into
  one call).

- **Verified**: `sfs_telemetry.py` compiles and sanity-tested directly
  against a real archived flight (flight01) — `load_samples`,
  `flight_summary`, `detect_phases`, `find_events`, and
  `validate_gravity_drag` all reproduced expected/consistent results.
  `sfsprobe_mcp/server.py` compiles clean, starts without error, and a
  smoke test calling ~12 of the 24 new tools directly (bypassing the MCP
  transport, which needs a Claude Desktop restart to pick up) ran with no
  exceptions and sensible output, including a genuine edge case correctly
  handled: `{'before_event':'impact', ...}` scoping fell back to the full
  flight range because flight01's telemetry never actually recorded a
  sample below 5m altitude (recording stopped just before real impact) —
  not a bug, `resolve_scope` correctly found no matching event. **Not yet
  tested through an actual live MCP connection** — needs a Claude Desktop
  restart, same as every previous `sfsprobe_mcp` change.

---

## 2026-08-28

- **`reference_index.py` / `reference_add.py`** — the bookkeeping pair for
  the `docs/sfs_reference/` split (Phase 1 Step 1).

  `reference_add.py` merges entries into
  `docs/sfs_reference/manifest.json` from stdin JSON, one or many at a
  time, then reruns the index build — so the manifest grows *as classes
  land* rather than in one pass at the end. Callers supply only
  `fq` / `file` / `summary` / `status` / `depth`; **namespace, kind, IL
  line number and method/field counts are filled from `inventory.json`,
  never from the caller**, so those can't drift from the assembly. Also
  accepts `{"section_map": [[old, new], ...]}` to extend the old-file
  §-section → new-file map. `status` is validated against
  CONFIRMED/PARTIAL/OPEN and `depth` against FULL/LIGHT.

  `reference_index.py` regenerates `docs/sfs_reference/INDEX.md` wholly
  from `manifest.json` + `inventory.json` — coverage table, standalone
  files, per-folder type tables, and the old-file section map. **INDEX.md
  is generated, never hand-edited**; drift between it and the manifest is
  prevented by construction. `--check` verifies every manifest `file`
  path exists on disk and every `fq` is a real inventory type.

- **`il_inventory.py`** — parses the `monodis` IL dump
  (`scratch/full_il.txt`, 13.3 MB, gitignored) into
  `docs/sfs_reference/inventory.json`: one record per `.class` declaration
  with namespace, kind, `extends`, nesting/parent, generic arity, line
  number in the dump, and `.method`/`.field` declaration counts. Filters
  compiler-generated types (closures, `<>c__DisplayClass*`, iterator state
  machines, `<PrivateImplementationDetails>` and its
  `__StaticArrayInitTypeSize=*` structs) — 1,509 `.class` declarations →
  **969 real types**. Also annotates each type with whether the
  pre-split `docs/sfs_source_reference.md` gives it a named heading
  (67 types) or merely mentions it (266). Written for Phase 1 Step 0 of
  the SFS Documentation restructure; output drives
  `docs/sfs_reference/INVENTORY.md`.

  Two parsing gotchas worth keeping: type names must be read as the first
  token *after* the flag keywords, not the last token on the line —
  generic declarations end in the type-parameter list
  (`.class ... Singleton\`1<(class ...Component) T>`), so a
  last-token heuristic yields `T>`. And quoted names (`'<>c__10\`1'`) have
  to be unquoted before splitting on `` ` `` or `<`, or they parse to the
  empty string.

- **Created `python/` folder** — didn't exist before this entry, despite
  being referenced by the 2026-08-26 changelog entries below. The
  two-body orbit solver and lower-envelope drag solver mentioned there
  were never actually found on disk when checked — likely only ever
  existed in a past chat session and were never saved. **Lesson: verify
  code mentioned in this changelog is actually on disk, don't assume
  because it's logged here that it's retrievable.** If those solvers are
  needed again, they'll need to be rebuilt from scratch or recovered from
  chat history.
- **`analyze_dragarea.py`** — validates the live-tested dragArea
  reflection path (mod_changelog.md v0.27.0) against real measured
  deceleration, the same rigor already applied to gravity/thrust/
  rotation/staging. Reads a truth.jsonl recorded with v0.28.0+ (which
  samples dragArea automatically every tick), finds coasting segments
  (mass flat across the whole span — same proxy `CheckAutoStop()` uses),
  and for each sample pair compares: measured acceleration (finite
  difference of `vx`/`vy` over real elapsed time) against predicted
  acceleration (gravity via confirmed `mu/r^2`, plus drag via the real
  `ApplyForce` force-application formula found during the doc-writing
  pass — `1.5 * dragArea * |v|^2 * density(h) / mass`, no extra unit
  constant needed since `AddForceAtPosition` is mass-normalized). Reports
  per-pair and aggregate magnitude/direction error, with the project's
  existing confirmed-formula error bars (gravity 0.008–0.13%, thrust
  0.4%, rotation 0.0006%, staging 0.003–0.006%, empirical noise floor
  ~0.006–0.03%) printed as the comparison bar. Only Earth's atmosphere
  constants are populated in `PLANET_CONSTANTS`; other bodies are
  skipped with a count, not silently mispredicted. Known gap: doesn't
  detect/filter parachute-deployed flight, where `ApplyParachuteDrag`
  bypasses this formula entirely (found same session, not yet handled
  here). Smoke-tested with fabricated data to confirm the pipeline runs
  end-to-end (parses, computes, reports) — **not yet run against a real
  flight**, which is the actual validation step.

---

## 2026-08-26

- **Two-body orbit solver**, built from scratch. Matches the game's own
  `Physics.GetTrajectory()` output to two decimal places at every
  sampled tick of a real coast, and matched the real eventual outcome
  of a 370km climb to 6.6m (0.0018%) — predicted *before* the rocket
  got there.
- **Lower-envelope / visible-surface solver**, built to eventually
  compute `dragArea` once real part geometry is available (see
  `sfs_physics_reference.md` §7.1 — geometry capture is still blocked
  on a Harmony patch, not yet written). Validated against synthetic
  test cases: 5/5 passed, including exact full-shielding and
  partial-shielding numbers, with the "pointed shape has lower drag"
  physical intuition falling out naturally from the formula. Not yet
  fed real geometry.

---

## Earlier history

No Python code existed before this date — the project was
research/planning only until the 2026-08-26 session (see
`SFS_Starting_point_Context` and `session-2026-08-26-gpu-session-1.md`
for the full narrative).
