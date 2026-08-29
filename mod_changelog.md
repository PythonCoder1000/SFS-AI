# sfsprobe — Mod Changelog

Tracks changes to `sfsprobe/SFSProbe.cs`, the C# probe mod. One entry per
build that ships a real behavior change. Target build stays pinned to
Spaceflight Simulator **1.6.00.16** (Steam, macOS) — see README.md.

Format: newest first. `[reconstructed]` marks entries written after the
fact from session notes rather than logged at the time.

---

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
