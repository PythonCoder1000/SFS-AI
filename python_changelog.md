# Python — Changelog

Tracks Python-side work for the SFS agent: physics models, solvers,
analysis scripts, and (later) the design/flight agent code itself.
Not version-numbered like the mod — dated entries, newest first.

---

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
