# sfsprobe — Mod Changelog

Tracks changes to `sfsprobe/SFSProbe.cs`, the C# probe mod. One entry per
build that ships a real behavior change. Target build stays pinned to
Spaceflight Simulator **1.6.00.16** (Steam, macOS) — see README.md.

Format: newest first. `[reconstructed]` marks entries written after the
fact from session notes rather than logged at the time.

---

## v0.41.0 — 2026-08-30 (later same day)

**Root-caused the ~50% heat overprediction from the per-part validation—
by reading the actual IL, not guessing.** `scratch/full_il.txt` (the
project's own decompiled-assembly dump) was on disk the whole time;
directly confirmed `AeroModule.FixedUpdate_Reentry_And_Heating`,
`RemoveHighSlopeSurfaces`, and `ApplyProtectionZone`'s real bodies.

- **Finding:** `HeatManager.ApplyHeat` never sees the raw drag-path
  exposed-surfaces list. It's filtered through two heating-only
  functions first: `RemoveHighSlopeSurfaces(list, 5.0)` (keeps only
  `\|dy/dx\|<5.0` and `dx>0.1` — 10x stricter than drag's `dx>0.01`
  cull) and `ApplyProtectionZone(list)` (a real geometric
  shadow-occlusion pass — a `>0.1`-unit y-step in the outline shields
  nearby segments within a `≤0.4`-wide zone, modeling a protruding part
  shadowing recessed geometry). `heatParts`' `ExposedSurface` tally had
  been using the unfiltered list this whole time, systematically
  inflating the `surfaceFactor` term and over-absorbing heat.
- **`temperature` itself was ruled out** — confirmed passed to
  `ApplyHeat` completely unmodified, no scaling or offset. The air-temp
  formula was never the problem.
- **Fixed:** `heatParts` now calls the REAL `RemoveHighSlopeSurfaces`
  and `ApplyProtectionZone` via reflection (both `private static`,
  directly reachable) before tallying per-owner `ExposedSurface`,
  instead of reimplementing this geometry independently —
  `ApplyProtectionZone` especially is involved enough that a
  reimplementation risked a new bug.
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load. Next real flight should show the ~50% overprediction closed.

---

## v0.40.0 — 2026-08-30 (later same day)

- **New `script` command — conditional multi-step flight plans, checked
  every physics tick, zero round-trip latency per step.** Syntax:
  `script <cond1>:<cmd1>; <cond2>:<cmd2>; ...`, e.g.
  `script h>=1000:setrot 5; h>=5000:setrot 10; h>=25000:setrot 70`.
  Conditions are `<field><op><value>` (`>=`/`<=`/`==`/`!=`/`>`/`<`);
  fields are the short telemetry names (`h`, `vv`, `t`, `m`, `v`, `rot`,
  `angv`, `partCount`) with a fallback to `ResolvePath`'s existing
  dot-path walker for anything else. Multiple commands per step via
  `&&`. Every step's condition is checked independently, every tick, in
  `FixedUpdate` right alongside `Sample()` — not sequential/ordered, so
  out-of-order or simultaneous triggers are both handled correctly.
  Built specifically to remove Claude's own polling round-trip (seconds
  of real latency per checkpoint) from a scripted altitude-based flight
  plan. No JSON parser — deliberately kept to this codebase's existing
  plain-text comma/semicolon command style.
- **New `scriptstatus`/`scriptclear` commands** for visibility (which
  steps have fired) and control (abort a bad plan mid-flight).
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load.

---

## v0.39.0 — 2026-08-30 (later same day)

- **New `turn <value>` command.** Writes `arrowkeys.turnAxis` directly
  — the real state `Rocket.ApplyTorque` reads to drive rotation. No
  clamp applied, matching the game's own confirmed direct-write
  behavior. **Note:** the current test rocket (Capsule/Parachute/Fuel
  Tank/Nose Cone/Hawk Engine) has no RCS or reaction wheel, so it
  almost certainly has no `TorqueModule` — on this specific rocket the
  command only matters via gimbal, and only while an engine's
  `throttle_Out > 0`.
- **New `setrot <degrees>` command.** Instant orientation snap — writes
  `rb2d.rotation` directly and zeroes `rb2d.angularVelocity` in the same
  call, so a scripted multi-checkpoint flight plan can start each leg
  clean instead of carrying over spin from whatever happened before.
  This teleports orientation in one frame; it does not simulate getting
  there.
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load.

---

## v0.38.0 — 2026-08-30 (later same day)

Closes the heat gaps identified from the first accumulation-model
validation (~27% peak-magnitude error, main suspect: the whole-rocket
`dragArea` stand-in for the real per-part `ExposedSurface`).

- **`heatParts` now written every tick in `truth.jsonl`.** For every
  part (resolved to its real heat owner — the `HeatModule` if it has
  one, else the `Part` itself, same rule `GetHeatState` uses): real
  `Temperature` (via the property, `+Inf`/`-Inf` sentinels preserved as
  explicit strings rather than silently coerced to null or a crashing
  `Infinity` literal), `HeatTolerance`, `IsHeatShield`, and a real
  **per-owner `ExposedSurface`** tally — `Σ(line.end.x - line.start.x)`
  over that owner's exposed segments, computed the same way
  `HeatManager.ApplyHeat` computes it internally. This replaces the
  whole-rocket `dragArea` proxy that was the leading suspect for the
  27% peak-temperature error in the first validation pass, and also
  gives real per-part temperature/tolerance data instead of only ever
  seeing the rocket-wide max.
- **New `difficulty` command.** Reads the ACTUAL
  `HeatVelocityMultiplier`/`MinHeatVelocityMultiplier` off
  `Base.worldBase.settings.difficulty` instead of assuming Normal =
  1.0/1.0 (which broke this project's own data-trust rule for one
  session). Also checks `aeroData.testShock`/`testReentry` — the debug
  override that would silently fake reentry temperatures.
- **New `jointgraph` command.** Dumps the live joint connectivity graph
  (`Rocket.jointsGroup.joints` — confirmed a genuine index, not a lazy
  memo): every `{a, b, anchor}` edge currently on the rocket. Combined
  with `heatParts`, this is the input needed to eventually predict
  *which* joint breaks next and how many parts it takes with it, not
  just that `partCount` will drop.
- `heatParts` also added as a `computed:heatParts` field for scoped
  telemetry mode, for consistency with `computed:engines`/`dragArea`.
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load, same as every version today.

---

## v0.37.0 — 2026-08-30 (later same day)

**Root-caused a bug that had been open since before v0.34** — the
`AmbiguousMatchException` on `EngineModule` reads, previously seen only
once (deep in a 73k-sample flight, deferred by explicit instruction) but
today trivially reproduced on EVERY engine, first tick, right on the pad,
while prepping a multi-engine validation flight.

- **Root cause found:** `Float_Reference : Double_Reference` redeclares
  its own `float Value` property, which **hides** (via `new`, not
  `override`) the inherited `double Value` from `ReferenceVariable<double>`
  further up the hierarchy — confirmed by cross-referencing
  `docs/sfs_reference/00-infrastructure/variables-wrapper-family.md`
  against the engine appendix's existing note. `GetWrapped2`'s old plain
  `t.GetProperty("Value", flags)` walks the WHOLE type hierarchy and
  throws the instant it finds two same-named, differently-typed
  properties that aren't a normal override pair. `EngineModule
  .throttle_Out` is a `Float_Reference`, so this fired on every single
  engine read, silently aborting the whole per-engine try block (which
  is why `thrustDirX`/`thrustDirY`/`gimbalOn`/`throttleOut` never
  populated — candidate 3 from the old three-way open question, now
  settled).
- **Fixed in both `GetWrapped2` and `SetWrapped`** (the write side had
  the identical latent bug, hadn't been hit yet, fixed preemptively): now
  walk from the most-derived runtime type upward, taking the first
  **`DeclaredOnly`** `Value` property found at each level. A single type
  can't declare the same property twice, so this can never be ambiguous
  — and the most-derived declaration is exactly what a real `.Value`
  call site binds to anyway, so this is a correct fix, not a workaround.
- **This is a foundational helper** used by nearly every command in the
  probe (throttle, torque, mass, RCS, engines, ...), so this fix's real
  reach is broader than just the engine array — anywhere a
  `Float_Reference` was silently failing before now works.
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load, same as the last two versions.

---

## v0.36.1 — 2026-08-30 (later same day)

- **New `atmophysics` command.** Reads `planet.data.atmospherePhysics`
  for the current rocket's planet — specifically
  `minHeatingVelocityMultiplier` and `shockwaveIntensity`, the two
  fields `AeroModule.GetTemperatureAndShockwave` actually consumes.
  Needed because `minHeatingVelocityMultiplier`'s `1.0f` in the docs is
  only the class's *constructor default*, not necessarily what Earth's
  real planet file specifies — per the project's data-trust rule this
  has to be read live, same reasoning as `aeroformula` in v0.36.0. Also
  dumps `height`/`density`/`curve` for reference. Writes
  `sfs_probe_atmophysics.json`.
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load, same as v0.36.0.

---

## v0.36.0 — 2026-08-30

First step in closing up the four "confirmed from code, untested live"
physics items (heat, multi-engine, RCS, terrain) — starting with heat's
single blocking read.

- **New `aeroformula` command.** Reads the 4 serialized `AeroFormula`
  coefficients (`velPow`, `densityPow`, `tempOffset`, `m`) live off
  `GameManager.main.aeroData` — these feed `AeroFormula.GetTemperature`,
  whose structure and literal constants were already confirmed from IL,
  but these 4 values are Unity-serialized data with no IL-literal
  equivalent, so they were the one thing standing between "formula read"
  and "formula usable." Tries `aeroData.Formula` first, falls back to
  `aeroData.formulaHolder.formula`, and reports which path actually
  resolved rather than assuming. Writes `sfs_probe_aeroformula.json`.
- **Fixed `GetHeatState`** — previously read `Part.temperature`
  unconditionally, which is a plain field that's never written for any
  part whose surfaces are actually owned by a `HeatModule` instead (both
  `Part` and `HeatModule` implement the abstract `HeatModuleBase`, and
  only one is the real owner per part). Now checks each part for an
  attached `HeatModule` first and reads its `Temperature` **property**
  instead of the raw field — this also fixes reading `Part`'s own
  temperature correctly, since `Get()` resolves `"Temperature"` to the
  property, not the differently-cased `"temperature"` field. Also now
  excludes `+Inf`/`-Inf` sentinel values (`DissipateHeat`'s "fully
  cooled" marker) from the max-temperature comparison, so a cooled part
  can no longer be misread as the hottest thing on the rocket.
- Compiled clean, installed. **Not yet run live** — needs a fresh game
  load (mod DLL is loaded once at startup) before `aeroformula` or a
  heat-validation flight can be tried.

---

## v0.35.4 — 2026-08-29 (later same day)

- **Fixed 6 of 8 real bugs found by the Step 1.5 Mod-Integration Safety
  Audit** (a separate Claude Code session, cross-referencing every
  SFSProbe.cs command against documented method bodies). Full audit
  table lives in that session's handoff; summary of what changed here:

  **`cheat` (findings 1, 3, 4):**
  - **Silent-failure bug, fixed.** Was resolving `SandboxSettings` via
    `Resources.FindObjectsOfTypeAll(t)[0]`, which can return an inactive
    object/prefab in unspecified order. If `[0]` wasn't the live
    component, the toggle flipped a detached `Data` object -- but
    `OnToggle()` saves the GLOBAL `Base.worldBase.settings`, not
    `this.settings`, so the command still printed `"toggled X"` and
    still wrote the settings file **while changing nothing**. Now uses
    the confirmed public static `SandboxSettings.main` directly.
  - **Crash-from-menu bug, fixed.** Had no scene gate; `OnToggle()`
    dereferences `Base.worldBase.paths` unchecked, so calling this from
    the main menu threw. Now checks `Base.worldBase` is non-null first,
    reported as `reason=no_world_loaded` instead of an uncaught
    exception.
  - **`InfiniteOxygen`, documented not fixed.** There's a UI button for
    it but no matching flag/method on `SandboxSettings` -- a real gap in
    the game's own naming consistency, not something a probe-side fix
    can paper over.
  - **`arg` case-sensitivity, documented as correct, not a bug.** `arg`
    becomes a real C# method name via reflection (`"Toggle" + arg`), and
    .NET reflection lookup is case-sensitive -- lowercasing it (as `cmd`
    is) would break every cheat name, not fewer.
  - All failure paths now report distinct `reason=` tokens (`no_arg`,
    `no_world_loaded`, `sandboxsettings_main_null`, `method_not_found`,
    `toggle_exception`) instead of either silent fake-success or an
    uncaught exception.

  **`loadblueprintbuild` (findings 5, 6):**
  - **Data-loss risk, mitigated.** `BuildState.LoadBlueprint`'s own body
    calls `Clear(applyUndo)` BEFORE any part-spawning/validation --
    meaning a failed load (most likely cause: a part name that doesn't
    match the real catalog) already destroyed the current design by the
    time `reason=load_exception` appeared, which read as "nothing
    happened." Can't change that ordering (it's inside the game's own
    method), but now pre-validates every part name against the live
    `PartsLoader.parts` catalog BEFORE calling `LoadBlueprint` at all --
    catches the single most likely cause (`reason=unknown_part_names`)
    while the current design is still intact.
  - The remaining `load_exception` message (for failure modes
    pre-validation can't catch -- DLC/ownership rejection, a malformed
    variable) now explicitly warns that the previous design may already
    be gone, rather than implying nothing happened.

  **Not fixed (2 of 8 findings, correctly out of scope):** `autostop`
  was flagged as state-mutating in the plan but the audit found it's
  actually read-only (only stops the mod's own recording) -- a plan
  correction, not a code bug. `achievements`'s `GetCompleteChallenges`
  has no doc entry yet but is read-only, so it's noted, not blocking.

  Built and installed clean. `sfsprobe_load_blueprint`'s error-code
  mapping updated to include `unknown_part_names` -> `INVALID_PARAM`.
  Not yet live-tested.

## v0.35.3 — 2026-08-29 (later same day)

- **`getparts` now also reads `MagnetModule.points`** -- real local
  attachment-point offsets (`x`, `y`, `occupied`). This is the actual
  mechanism behind SFS's snap system, confirmed via IL: `SFS.Builds.
  HoldGrid` + `MagnetModule.GetAllSnapOffsets`/`GetSnapPointsWorld` --
  **not a coordinate grid at all**. Parts snap to each other via real
  geometric attachment points that the game's own interactive placement
  UI matches through `GetAllSnapOffsets`; direct blueprint injection
  (`loadblueprint`/`loadblueprintbuild`) bypasses that step entirely,
  which is why hand-picked positions can land a part somewhere a human
  dragging with the mouse never could. `Point.position` is a simple
  field (not mesh geometry), hypothesized safe to read straight from
  the catalog like the variable data was. **Built, installed clean --
  NOT YET LIVE-TESTED.** A reload+test was requested but the session
  moved on to other work before it happened; do not treat this as
  confirmed until a real `getparts` run shows non-empty magnet data.

## v0.35.2 — 2026-08-29 (later same day)

- **Widened `DumpObjectFieldsGeneric`** (the shared generic reflection
  dumper used for `VariableSave`/`VariantRef`) to read non-public fields
  (Unity's common `[SerializeField] private` pattern, same reasoning the
  main `Get()` helper already applies) and public "simple" properties,
  not just public fields -- closes a real gap where meaningful data on
  an object like `VariantRef` could sit behind either and silently come
  back empty.

## v0.35.1 — 2026-08-29 (later same day)

- **Fixed `getparts` missing `PartsLoader.partVariants` entirely.**
  Christian manually counted 57+ parts in the build menu without even
  reaching halfway through the tabs — directly contradicting v0.35.0's
  reported total of 56. My first explanation (DLC/expansion ownership
  limiting the catalog) was wrong and got corrected by the headcount,
  not confirmed by it — real IL reading found the actual cause:
  `PartsLoader` has a SECOND, separate `Dictionary<string, VariantRef>`
  field (`partVariants`, confirmed via IL, distinct from the `parts`
  dictionary `getparts` already read), and the build menu very likely
  shows variants as their own selectable tiles alongside base parts.
  `getparts` now reads both and reports `partsTotal`/`variantsTotal`
  separately. `VariantRef`'s exact field schema wasn't independently
  confirmed via IL before this was written, so its fields are read
  generically (whatever they're actually called) via the same pattern
  already used for `VariableSave` — that shared helper is renamed
  `DumpObjectFieldsGeneric` since it's no longer variable-specific.

  Built and installed clean. Not yet live-tested — next reload settles
  whether `partsTotal + variantsTotal` actually accounts for the real
  in-game count.

## v0.35.0 — 2026-08-29 (later same day)

- **Added `dumpblueprint`** — reads the CURRENT editor design as a real
  `Blueprint` object via `BuildState.main.GetBlueprint(bool)` (confirmed
  via real IL call sites, the same file `LoadBlueprint`'s body was read
  from), serializes it with the same `JsonWrapper.ToJson` used
  elsewhere. This is the reverse of `loadblueprintbuild` — "what does
  the editor actually contain right now" as real data, not a guess.
  Read-only, no state mutation.

- **Added `getparts`** — full parts-catalog index: real name (from
  `orientation.name`) + mass + centerOfMass + REAL parametric variable
  names/values for every part in `PartsLoader.parts`. Fixes a real data
  loss: the generic `Dump()` reflection walker's depth-3 cutoff was
  rendering every parametric variable (`doubleVariables`/
  `boolVariables`/`stringVariables`, e.g. `Fuel Tank`'s 7 double
  variables) as just the bare string `"VariableSave"` — the type name,
  not the actual name/value data. New `DumpVariablesModule`/
  `DumpVariableSaveGeneric` helpers walk past that cutoff explicitly
  (same fix pattern already applied once for `surfaceGeometry`), reading
  each `VariableSave`-like object's fields generically (whatever they're
  actually called) rather than guessing specific field names.

  **Deliberately command-gated, not part of the automatic on-load `menu`
  dump** (`DumpMenu`, unchanged, still runs on every scene load) — this
  is heavier and was explicitly requested to stay opt-in so a normal
  game reload doesn't slow down. Only runs when `getparts` is sent.

  Motivated by a real failure: a hand-built 4-part test blueprint
  (`default_rocket` — Engine Hawk/Fuel Tank/Capsule/Parachute, positions
  estimated from `centerOfMass` since real geometry isn't safely
  readable from unplaced catalog prefabs) spawned with the Fuel Tank
  abnormally tiny and the Parachute overlapping the Capsule — because
  the blueprint never supplied real `NUMBER_VARIABLES` for parametric
  parts, and no tool existed yet to find out what those variables even
  are. `getparts` (names + real variables) plus `dumpblueprint` (real
  as-placed state of whatever's currently in the editor) together are
  meant to close that gap without needing IL research per part.

  Built and installed clean, first try. **Neither command live-tested
  yet.**

## v0.34.0 — 2026-08-29 (later same day)

- **Replaced `GetEngineDirection` (first-active-engine-only) with
  `GetEngineArray` (one entry per engine/booster module).** Two real bugs
  fixed, both flagged in `high_level_checklist.md`'s tooling-bugs section:

  1. **Structural**: there is no thrust summation anywhere in the game --
     each engine calls `AddForceAtPosition` independently, off-axis torque
     is emergent. "First active engine" was never a meaningful summary of
     a multi-engine rocket; a predictive model needs N independent forces,
     not one. `inputs.jsonl`'s `engines` field is now an array, one entry
     per module found (`{part, type, engineOn/boosterPrimed,
     thrustDirX/Y or thrustVectorX/Y, gimbalOn, throttleOut}`), regardless
     of on/off state -- state is data now, not a filter.
  2. **Coverage**: `BoosterModule` (`thrustVector`/`boosterPrimed`) was
     completely missed before -- only `EngineModule` (`thrustNormal`/
     `engineOn`) was ever checked.

  Also fixes the silent-failure half of the same checklist item:
  `GetEngineDirection` ended in a bare `catch { }`, so of its three
  candidate explanations for why `thrustDirX/Y`/`gimbalOn`/`throttleOut`
  never populated (no matching module / `engineOn` false outside a burn,
  which is correct / an exception thrown and swallowed), the third was
  unfalsifiable by inspection alone. Every read in `GetEngineArray` is now
  individually try/caught and **logged**, with the specific part name, so
  a real flight settles which explanation it actually was instead of
  staying a permanent mystery.

  Added `computed:engines` for scoped telemetry, reusing the same helper.

  Built and installed clean. **Not yet live-tested** -- next real flight
  will show whether engines were actually being missed, correctly
  reporting `engineOn=false` outside a burn, or throwing (now visible in
  `probe.log` either way).

## v0.33.0 — 2026-08-29 (later same day)

- **Added `loadblueprintbuild <path>`** — the real mechanism behind the
  game's own "Load Blueprint" button. Calls `BuildState.LoadBlueprint
  (Blueprint, I_MsgLogger, bool autoCenterParts, bool applyUndo, Vector2
  offset, Action onLoaded)`, a **public instance** method confirmed via
  reading its actual IL body (2026-08-29) — it calls `BuildState.Clear()`
  first (hence **replaces** the current design, not adds to it), centers
  parts/camera, sets orientation, loads staging, all within
  `BuildState`/`BuildMenus`/`BuildOrientation`/`BuildGrid` (editor-scoped
  types). **No `WorldView` dependency at all** — correctly requires
  `Build_PC`, the opposite of `loadblueprint` (v0.30–v0.32, which spawns
  an *additional* rocket into a live `World_PC` flight via
  `RocketManager.SpawnBlueprint`). Both commands now coexist — they do
  genuinely different things (replace the design being edited vs. add a
  rocket to a running flight), not a replacement of one by the other.

  Same distinct-failure-reason discipline as `loadblueprint`:
  `not_in_build`, `buildstate_not_found`, `load_method_not_found`,
  `load_exception`, plus the shared `no_path`/`file_not_found`/
  `read_error`/`type_resolution`/`fromjson_method_not_found`/
  `deserialize_error`/`deserialize_null`.

  Built and installed clean, first try. **Confirmed working live,
  2026-08-29** (same day): loaded `single_capsule` from `Build_PC`,
  correctly replaced the prior design (not added alongside it). One
  minor known gap, not investigated further -- `Part_Utility.CenterParts`/
  `GetOwnedGridSize`'s internals were never read, so the part didn't
  land at the editor viewport's visual center, just somewhere
  grid-valid. Not pursued: a real launch auto-centers the rocket
  regardless, so this has no practical effect on the loader's actual use.

  **IMPORTANT SAFETY NOTE, added after a live-test debrief (2026-08-29):**
  `loadblueprint` (this command, `RocketManager.SpawnBlueprint`) should
  **NOT** be used routinely during a live flight, even though it's been
  confirmed to work. Its first action moves the camera to the launch pad
  -- the signature of a one-time internal Build-to-World launch-
  transition primitive, not a general spawn tool. Calling it mid-flight
  materializes a fully-fueled part with none of a real launch's cost/
  sequence/achievement tracking -- functionally cheating. Use
  `loadblueprintbuild` (below) for any routine design-loading need
  instead — that one IS the real, repeatable "Load Blueprint" mechanism.

## v0.32.0 — 2026-08-29 (later same day)

- **Fixed the `loadblueprint` scene gate: World_PC, not Build_PC.**
  First live test (against `single_capsule`, from `Build_PC` as
  originally gated) threw `spawn_exception: Object reference not set
  to an instance of an object.` Read `RocketManager.SpawnBlueprint`'s
  actual IL body (never read before this — `[OPEN]` in the source
  reference) to find out why: its first five instructions call
  `WorldView.main.SetViewLocation(SpaceCenterData.LaunchPadLocation)`
  — dereferencing the static `WorldView.main` singleton before touching
  a single part. That singleton is populated in `World_PC` (a loaded
  flight/world), not `Build_PC` (the editor) — the exact opposite of
  the original untested assumption ("should be in the design screen").
  Confirmed live: the same call from `World_PC` no longer hits
  `not_in_world` and gets past the scene check (see
  `python_changelog.md`/`docs/sfs_source_reference.md` for the fuller
  spawn-result outcome).

  `reason=not_in_design` renamed to `reason=not_in_world` to match.
  This is a real example of the project's own "verify before building"
  rule catching an actual wrong assumption, not just a hypothetical one
  — the fix came from reading the IL after a real failure, not from
  guessing harder.

  **Retested and CONFIRMED WORKING from `World_PC`, same day:**
  `loadblueprint` against a single-part test blueprint returned OK,
  rocket count went 1->2, part count went 8->9, and the spawned capsule
  was visually confirmed in-game next to the existing rocket. The whole
  pipeline is real, not just theoretically documented — write a plain
  JSON file, no editor interaction, spawn through the game's own code.
  Multi-part blueprints (joint generation, connectivity) and the
  possible DLC/ownership gate remain untested.

## v0.31.0 — 2026-08-29

- **`ping` now reports `gameVersion` and `modVersion`** alongside
  `scene`/`rockets`/`fixedDelta` — e.g.
  `pong scene=Build_PC rockets=-1 fixedDelta=0.02 gameVersion=1.6.00.16
  modVersion=0.31.0`. Small addition, but closes a real gap: there was
  previously no way to check either version without eyeballing
  `probe.log`'s load-time message by hand.
- **De-duplicated the version string.** `ModVersion` and the load-time
  `Log()` message each hardcoded the version separately before — a
  real (if harmless) inconsistency risk. Now both read from one
  `ProbeMod.VersionString` const, the single source of truth, also used
  directly by the new `ping` response.
- On the `sfsprobe_mcp` side: `sfsprobe_ping` now returns `game_version`/
  `mod_version` fields, and `sfsprobe_status` pulls `mod_version` out of
  its own internal ping call and surfaces it too — matching the actual
  ask ("ping shows game version, status shows mod version") without a
  second round trip either tool didn't already need.

## v0.30.0 — 2026-08-29

- Added **`loadblueprint <path>`** — spawns a rocket design directly,
  bypassing the editor UI entirely. Reads `Blueprint.txt`-format JSON
  from an ARBITRARY file path (does NOT require the file to live inside
  the game's own `Saving/Blueprints/` folder — reads it directly with
  plain `File.ReadAllText`), deserializes via the game's own
  `JsonWrapper.FromJson<Blueprint>` (generic, resolved via
  `MakeGenericMethod`), then calls the confirmed public-static
  `RocketManager.SpawnBlueprint(Blueprint)`. Schema and call chain
  confirmed via IL reading during the SFS Documentation effort
  (`docs/sfs_source_reference.md` §D5.1/D5.4/D5.5), cross-checked
  against a real saved blueprint file found on disk
  (`Saving/Blueprints/AllParts/Blueprint.txt`) — the six-field schema
  matches exactly.

  Path parsing gotcha handled: this project's own folder is literally
  named "SFS AI" (contains a space), so the command splits into exactly
  2 pieces (command word + everything else) rather than using the
  shared single-word `arg` every other case relies on — same pattern
  already used by the `telemetry` case for field specs.

  Every failure path reports a **distinct `reason=` token** (`no_path`,
  `not_in_design`, `file_not_found`, `read_error`, `type_resolution`,
  `fromjson_method_not_found`, `deserialize_error`, `deserialize_null`,
  `spawn_method_not_found`, `spawn_exception`) so a caller can tell
  "wrong scene" from "bad file" from "the game itself rejected the
  design" — not just one generic failure.

  **GENUINELY UNTESTED-LIVE as of this build.** `SpawnBlueprint`'s own
  body was never read during the documentation effort (marked
  `[OPEN]`), and there's a documented possible DLC/ownership gate
  (`OnPartNotOwned`/`OwnershipState`) that could silently reject some
  parts. Built and installed clean, first try — but the actual spawn
  call has not yet been exercised against a running game. Treat the
  first real test as an experiment, not an assumed-working feature.

## v0.29.0 — 2026-08-28

- Added **scoped telemetry** (real "probe" behavior, not a rebuild-every-
  field system anymore). `telemetry on` keeps the old default full-schema
  behavior unchanged. `telemetry on <fieldspec>` (comma-separated) records
  ONLY the requested fields, one `truth.jsonl` row per tick, no
  `inputs.jsonl` in this mode. Two kinds of entries:
  - **Dot-path fields** (e.g. `rb2d.mass`, `location.velocity.x`) — walked
    via a new generic `ResolvePath(root, path)` helper, reusing the exact
    same `Get()`/`GetWrapped2()` mechanism already used everywhere else in
    this file. Adding a new plain field NEVER needs a rebuild — it's just
    a different string sent at runtime.
  - **`computed:NAME` fields** (e.g. `computed:dragArea`) — for fields
    that need real logic first, dispatched via a new `AppendComputedField`
    switch. `dragArea` is the first entry, expanding to `dragArea`/
    `dragCopX`/`dragCopY`/`dragSurfaces`/`dragExposed` (same keys as the
    always-on full-mode field added in v0.28.0). Adding a NEW computed
    field still needs a rebuild (one `case` + reusing an existing helper
    like `GetHeatState`/`FuelByStage`/`SumEnabledTorque`/
    `CountFiringThrusters`/`GetPredictedOrbit`/`GetEngineDirection`, all
    already available), but reusing an already-registered one never does.
  - Example: `telemetry on h,vv,computed:dragArea` mixes both freely.
  - `telemetryFields` resets to `null` (full mode) on `StopRecording()`,
    so the Enter/Backslash hotkeys always default back to full mode
    regardless of what a prior command-driven scoped run used.
  Built and installed clean, first try. **Not yet run live** — next step
  is a real scoped-mode flight to confirm the dot-path walker and the
  `computed:dragArea` dispatch both work end-to-end during an actual
  ascent/coast/reentry.

## v0.28.0 — 2026-08-28

- Every telemetry tick now samples `dragArea` automatically. Refactored
  the v0.27.0 `dragarea` command's call chain into a shared
  `TryComputeDragArea(rocket, out drag, out copX, out copY, out allCount,
  out exposedCount)` helper, reused by both the manual `dragarea` command
  (unchanged) and a new call inside `Sample()`. `truth.jsonl` gained five
  new keys every row: `dragArea`, `dragCopX`, `dragCopY`, `dragSurfaces`,
  `dragExposed` (`null` for the first three if the computation fails that
  tick, e.g. rocket not yet spawned). Motivation: a full launch-to-
  reentry flight now produces a complete matched dataset of drag +
  velocity + altitude + mass with no manual `dragarea` polling needed,
  enabling a real deceleration-vs-prediction validation across an entire
  trajectory instead of single-point manual pulls. Built and installed
  clean, first try.

## v0.27.0 — 2026-08-28

- Added `dragarea` command: dragArea and center-of-pressure are directly
  callable via plain reflection, no Harmony/geometry-capture needed at
  all (that path is fully abandoned — see v0.26.0 below and
  `sfs_physics_reference.md` §4). Calls `Aero_Rocket.GetDragSurfaces
  (Matrix2x2)` (1-arg instance overload, explicit-type-resolved to avoid
  `AmbiguousMatchException` against the 2-arg static overload) →
  `AeroModule.GetExposedSurfaces(List<Surface>)` → `AeroModule.
  CalculateDragForce(List<Surface>)`, which returns `(drag,
  centerOfDrag)` confirmed via the method's own `TupleElementNamesAttribute`.
  Rotation matrix uses the real velocity-derived formula from
  `AeroModule.FixedUpdate()`'s own IL (`-(velocity.AngleRadians - π/2)`),
  not identity. Writes `sfs_probe_dragarea.json` (surface counts, sample
  segments, final drag/CoP tuple). Added `InvokeStatic(Type, method,
  paramTypes, args)` helper for explicit-overload disambiguation,
  reusable for any future ambiguous static method. Built, **not yet run
  live** — next step is the actual game test.

**LIVE-TESTED 2026-08-28, same day:** ran `dragarea` against a real
launch-pad rocket in `World_PC` scene. Result: 36 total surfaces, 25
exposed, `CalculateDragForce` returned `drag=7.962407`,
`centerOfDrag=[-177.989471, -319.42807]` (world-space, consistent with
the sample segment coordinates). No errors, no `AmbiguousMatchException`,
full chain resolved cleanly on the first live run. One bug caught and
fixed before this test: a local variable named `line` inside the case
block collided with `Command(string line)`'s own parameter, causing a
`CS0136` compile error — renamed to `segLine`. **dragArea is now
confirmed working end-to-end.**

## v0.26.0 — 2026-08-27

- Bundled HarmonyX 2.16.0 + full MonoMod 25.x dependency chain into
  `sfsprobe/lib/harmonyx_2.16.0/`, replacing the game's own older/
  arm64-broken `0Harmony.dll` (2.10.1.0) at build/install time, to test
  whether a newer MonoMod (with the arm64 macOS fix merged 2025-08-15)
  would unblock the v0.25 Harmony geometry-capture patch. Built and
  installed clean. **Result: did not help.** SFS's own built-in mod
  loader already loads the old Harmony/MonoMod into the process before
  any mod's `Load()` runs, confirmed via identical MVID stack-trace
  fingerprints before/after the bundle swap — our new DLLs were never
  actually touched at runtime. This is the final, confirmed root cause;
  Harmony-based geometry capture is abandoned (see v0.27.0 above for the
  replacement approach). Bundled files left in place, harmless/unused.

## v0.25 / v0.25.x — 2026-08-27 `[reconstructed]`

- Added a Harmony postfix patch on `SFS.Parts.Part.InitializePart()` to
  passively capture `surfacesFast` geometry the instant the game's own
  code populates it. Confirmed via IL that `InitializePart()` takes
  **zero arguments** (not `InitializePart(bool)` as an earlier research
  pass claimed) and has no internal "already initialized" skip-gate.
  New `geometry` command dumps captured surfaces per part. Diagnostic
  scaffolding added (`GeometryPatches.TestTrivialPatch`, full exception-
  chain unwrapping, IL-instruction-index extraction from
  `HarmonyException`) after `harmony.Patch()` started failing with
  `IL Compile Error (unknown location)` — isolating test proved the
  failure was environment-wide (patching a trivial no-op in our own
  assembly failed identically), not specific to `Part.InitializePart()`.
  Root-caused to a MonoMod/arm64-macOS incompatibility in the game's
  bundled Harmony version — see v0.26.0 above for the (unsuccessful)
  attempted fix.

## v0.24 — 2026-08-26

- Added `achievements` command. Confirmed via IL that in-game
  "achievements" are internally `SFS.Logs.Challenge` — not Steamworks
  achievements (SFS has none registered). Reads the full catalog from
  the static `SFS.Base.worldBase.challengesArray`, and per-rocket
  completion from the real public method
  `Rocket.stats.challengeRecorder.GetCompleteChallenges()`. Writes
  `sfs_probe_achievements.json` (id, title, description, planet,
  difficulty, step count, completed flag per challenge). Built and
  installed clean; not yet run live against the game.

## v0.23 — 2026-08-26 `[reconstructed]`

- Separation-event capture now records **both** resulting rocket
  objects at the instant of a split (position, velocity, rotation,
  angular velocity, mass, part count) — not just whichever piece the
  game's camera happens to keep following.

## v0.14 → v0.23 — 2026-08-26, GPU Session #1 `[reconstructed]`

One overnight session, iterated live against the running game. Net
result: gravity, thrust, throttle response, fuel-flow rate,
player-commanded rotation, and staging momentum conservation all
empirically confirmed, most to well under 0.1% error. Aerodynamic
torque confirmed to exist as a real, isolated effect (magnitude still
open — see `sfs_physics_reference.md` §7.1).

Notable changes made along the way (not individually versioned at the
time):
- Split the old combined `throttle` command (which had a hidden
  side-effect of setting master ignition) into three independent,
  explicit steps: `throttle <0..1>` → `ignite` → `master on`.
- Switched command loop to a polled file pair (`command.txt`/
  `result.txt`), not a socket — avoids macOS firewall prompts.
- Fixed `Part.modules` walking to unwrap arrays and dedup by reference
  identity, not type name (was 6x-overcounting a single real engine).
- Split telemetry into `inputs.jsonl` (control signals) and
  `truth.jsonl` (actual outcomes), kept separate so a simulator built
  from one can be checked against the other without circularity.
- Added `forceInit` as an explicit opt-in reflection flag, applied only
  to already-placed flying parts, never bare catalog prefabs — calling
  it on a bare prefab was confirmed to hang the game
  (`EXC_BAD_ACCESS`, stack-guard/recursion signature).
- Confirmed (and left unfixed, tracked as open bugs) that
  `thrustDirX`/`thrustDirY`/`gimbalOn`/`throttleOut` never populate,
  and that `thrOn` doesn't reliably indicate actual thrust — use mass
  flatness instead.

## v0.14 — pre-2026-08-26 `[reconstructed]`

- Added `ignite` command: sets `EngineModule.engineOn` per engine.
  Needed because staging normally does this automatically, but
  `throttle` alone does not.
- Telemetry pipeline operational: per-tick `inputs.jsonl`/`truth.jsonl`
  streams, on-demand snapshots, remote command interface.
- Key physics formulas verified against the live assembly: drag force
  law, atmosphere density curve, gravity, thrust, rotational dynamics.

---

## Earlier history

Not individually logged — this file starts tracking from v0.14 onward.
Earlier versions (v0.1–v0.13) covered basic scaffolding: hooking the
update loop, reflection helpers for wrapped value types, initial
telemetry streaming. See `sfs_physics_reference.md` for what's
currently confirmed vs. open, regardless of which version confirmed it.
