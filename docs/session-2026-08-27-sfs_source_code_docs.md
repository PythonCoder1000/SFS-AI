# SFS source code docs — 2026-08-27

## Where the project stands

The project is building an LLM agent that designs rockets in Spaceflight
Simulator, flies them, and adapts mid-flight. It is still in Tier 1
(research/architecture); no agent code exists. This session produced
**`docs/sfs_source_reference.md`** — a consolidated, IL-verified code
reference (~6,250 lines / 274 KB, 25 sections). It was written as
`sfs_full_reference.md` and, once complete, **overwrote
`docs/sfs_source_reference.md` in place**; that is now the single
canonical file and `sfs_full_reference.md` no longer exists. **All planned sections are
written**: A1 (reflection toolkit), A2 (methodology), A3 (`SFS.Variables`
wrappers), A4 (mod loader + Harmony), B1–B7 (Rocket, Location/Double2,
Part, PartHolder, Physics/Trajectory/Orbit/Kepler, Mass_Calculator,
Staging), C1 (drag/aero), D1 (heat), D2 (engines), D3 (RCS), D4
(planets/SOI/terrain), D5 (save/load), E1 (resources/fuel), E2
(control/input), E3 (joints/docking), E4 (parametric expressions), E5
(world/scene/timewarp), E6 (parachutes/wheels/toggles), E7
(stats/challenges/logging). **Four of the five items listed as "still
open, no path yet" in `high_level_checklist.md` now have confirmed
formulas read from IL.** `sfs_source_reference.md` and
`sfs_physics_reference.md` were deliberately left untouched pending
review of the new file; the merge-or-replace decision is still open.

## Supersedes

Corrections found today. Each contradicts something currently stated as
settled in the repo docs or in Mnemoverse (`project:sfs-agent`).

- **"SFS's own built-in mod loader already loads the old Harmony/MonoMod
  into the process before any individual mod's `Load()` runs"** — stated
  as the *final, confirmed root cause* in `sfs_source_reference.md`, in
  `high_level_checklist.md`'s "Abandoned" section, and in memory
  `176d2827`. → **The mechanism is not supported by the IL.**
  `Assembly-CSharp.dll` contains **zero** occurrences of `HarmonyLib` or
  `MonoMod`, has no extern assembly reference to either, and **no DLL in
  the game's `Managed/` folder references `0Harmony` at all** (checked
  individually with `monodis --assemblyref`). `ModLoader.Loader` loads
  exactly one assembly per mod folder (`<Folder>/<Folder>.dll` via
  `Assembly.LoadFrom`) and never touches Harmony. The MVID evidence
  recorded earlier is still valid — it proves the *old* DLL is what
  loaded — but it identified the symptom, not the cause. The supported
  explanation is **assembly-name resolution**: both copies are
  weak-named (zero-sized public key, confirmed on the game's 2.10.1.0
  and the bundled 2.16.0.0), so only one `0Harmony` can exist per
  process, and Mono probes the **application base** (`Managed/`) before
  the directory beside the mod DLL. `build.sh` asserts the opposite in a
  comment. **This does not reopen the decision** — dragArea is solved
  without Harmony, and the ceiling may still be low (MonoMod issue #230,
  `ILHookOnMonoShouldSucceed`, was still failing CI on macOS 14 arm64
  sysmono as of 2025-09-30). But the specific claim that *no
  non-invasive fix exists* is unsupported: an
  `AppDomain.AssemblyResolve` handler or strong-naming the bundle were
  never tried, and neither requires modifying the game's `Managed/`
  folder. Both are **untested**. Full detail in `sfs_source_reference.md`
  §A4.2–A4.3.

- **`sfs_source_reference.md`: "`SFS.World.Drag.AeroModule` — drag/aero,
  per-part-module level" / "per-module version (single part)"** → Wrong.
  `AeroModule` is an **abstract base class**; its
  `GetDragSurfaces(Matrix2x2)` is `protected abstract` with no body.
  `Aero_Rocket` and `Aero_Astronaut` are the subclasses. There is no
  per-part drag module — drag is computed for a whole `PartHolder` at
  once. (§C1.0)

- **`sfs_physics_reference.md` §5: heat/destruction has "no formula read
  from code"** → The whole chain is now read. A default part breaks at
  **412 °C** (`HeatTolerance.Low` = 400, threshold is
  `Temperature > tolerance × 1.03`), which explains the single 410.8 °C
  data point exactly. (§D1)

- **`sfs_physics_reference.md` §1.3 fuel-flow formula
  `thrust · throttle / (ISP · ispMultiplier)`** → Incomplete. The real
  call multiplies by a **`scale` term**: the magnitude of `thrustNormal`
  after the part's world transform. It is 1.0 for an unscaled part
  (which is why the empirical check passed at 0.002%), and not 1.0 for a
  scaled one. (§D2.3)

- **`sfs_physics_reference.md` §1.1 Earth atmosphere constants
  (`ρ0 = 0.005`, `curve = 10`, height 30,000 m) stated
  unconditionally** → These are **difficulty-scaled**.
  `Difficulty.ScalePlanetData` mutates `PlanetData` once at load,
  scaling radius, gravity, SOI, semi-major axis, atmosphere height and
  atmosphere curve. Live reads are already scaled and correct; JSON on
  disk is not. §1.1's numbers are a difficulty-specific snapshot and the
  doc does not record which difficulty. (§D4.2)

- **`sfs_physics_reference.md` §1.2: "No Python-side evaluator exists"
  for parametric part values** → The game ships one.
  `SFS.Variables.Composed_Float` holds `public string input` (the
  expression, e.g. `"size * 0.05"`) and compiles it via the public static
  `SFS.Parsers.Constructed.Compute.Compile`. Reading `.Value` **already
  evaluates it** — the probe has been getting correct parametric masses
  all along. And the expression is only meaningful against a bound
  `VariablesModule`, which is precisely why static asset parsing gave
  the wrong Titan mass and wrong Hawk thrust/ISP. **The data-trust rule
  in `CLAUDE.md` is now explained, not just observed.** (§E4)

- **`sfs_physics_reference.md` §5: "`maxTerrainHeight` is a single bound
  per body, not real terrain geometry"** → The *bound* is a single
  value, but real per-angle terrain **is** queryable via
  `Planet.GetTerrainHeightAtAngles(double[], bool)`. `maxTerrainHeight`
  is only a fast-reject radius inside `IsInsideTerrain`. (§D4.4)

- **`high_level_checklist.md`: multi-engine listed as needing a summation
  model** → There is **no summation**. Each `EngineModule.FixedUpdate`
  calls `Rb2d.AddForceAtPosition` independently at its own
  `thrustPosition`; multi-engine behaviour is Unity accumulating N
  forces, and off-axis torque is emergent. (§D2.0)

- **Assumption that RCS responds proportionally to steering input** →
  It does not. `TorqueThrust` returns false unless
  `|TurnAxis| ≥ 0.95` **or** `|angularVelocity| ≥ 2` deg/s. The second
  clause is what makes RCS act as a rotation damper. (§D3.2)

- **`sfs_source_reference.md` and memory `6ccf5310`: the `dragarea`
  command is "drafted, not yet applied"** → **Corrected by Christian
  mid-session.** `SFSProbe.cs` is at **v0.27.0** with `dragarea`
  applied and built (see `mod_changelog.md`). Still not run live. The
  shipped version was checked against the IL and is sound.

- **`docs/startup_prompt.md` and memory `d98fd915` instruct reading
  "the most recent `session-*.md` handoff file"** → No `session-*.md`
  file existed in the repo before this one. Memory also references
  `session-2026-08-26-gpu-session-1.md`, which is not in the repo either.
  A fresh session following the startup prompt will find nothing there.

## Decided

- **Build the new reference as a separate file first, then replace** —
  the old `sfs_source_reference.md` stayed available for comparison
  while the new one was written, and the merge-or-replace decision was
  deliberately deferred. **Resolved 2026-08-27: straight replacement.**
  Before overwriting, the old file's content was diffed against the new
  one and four items that had not been absorbed were carried across
  (see "Supersedes"). A copy of the original is in the session
  scratchpad only — `docs/` is untracked in git, so there is no other
  backup.
- **Scope: exclude `SFS.UI` (87 types), `SFS.Builds` (25), and
  `SFS.UI.ModGUI` (18)** — they only matter if the agent plays the
  in-game editor, which is an open design decision. Documenting them now
  would be speculative work that might be thrown away. Christian's call:
  answer that decision separately first. (The `Blueprint` *data type*
  from `SFS.Builds` is documented anyway, in §D5, because it is save
  format rather than UI.)
- **Promote E4 (parametric expressions) ahead of the B-tier** — recon
  showed the game has a real expression AST, which turned out to solve a
  problem `sfs_physics_reference.md` calls unsolvable. Paid off.
- **Deprioritise E6 (parachutes, wheels, toggles) to last** — agreed as
  completeness for its own sake.
- **Status tags are per-item, not per-section**:
  `[CONFIRMED]` / `[PARTIAL]` / `[OPEN]` / `[UNTESTED-LIVE]`, where
  `[UNTESTED-LIVE]` explicitly means "IL says so, never executed".

## What worked

All commands run from the repo root, `/Users/christianjin/Documents/VSCode/SFS AI`.

**Verify the pinned build before trusting any line number:**

```bash
DLL=~/Library/Application\ Support/Steam/steamapps/common/Spaceflight\ Simulator/SpaceflightSimulatorGame.app/Contents/Resources/Data/Managed/Assembly-CSharp.dll
md5 -q "$DLL"          # must be cbad19d24f73252e5a7acd6b88cfa9c1
monodis --output=scratch/full_il.txt "$DLL"
md5 -q scratch/full_il.txt   # dcf3f2dbfd670f9666d2de2fb6a5f2f0
```

The existing `scratch/full_il.txt` was re-generated and came back
**byte-identical**, so it is current. `monodis --assembly` reports
`Version: 0.0.0.0` (Unity never stamps it) — the **md5 is the only real
identity check**.

**The signature extractor.** `monodis` splits a method declaration across
two lines: the `.method` line has only attributes, and the return type,
name and parameters are on the *next* line beginning with `default`. A
naive `grep '\.method'` therefore returns a wall of `hidebysig instance`
with no names, which is how an earlier pass could conclude a class was
empty. Saved to the session scratchpad as `sig.sh`:

```bash
#!/bin/bash
# sig.sh <ClassName> -- fields + flattened method signatures for a top-level class.
# STOPS at the first nested .class so compiler-generated closure members are
# not misattributed to the outer type.
IL="scratch/full_il.txt"
start=$(grep -n "^  \.class .*[ .]$1$" "$IL" | head -1 | cut -d: -f1)
if [ -z "$start" ]; then echo "NOT FOUND: $1"; exit 1; fi
awk -v s="$start" '
NR<s {next}
{ lines[NR]=$0 }
NR>s && (/^  \} \/\/ end of class/ || /^  \.class nested/) { end=NR; stop=$0; exit }
END {
  for(i=s;i<=end;i++){
    l=lines[i]
    if (l ~ /^  \.class/ && i==s) { print "CLASS@"i": " l }
    else if (l ~ /^    \.field/)  { print "  FIELD: " l }
    else if (l ~ /^    \.method/) {
      sig=lines[i]
      for(j=i+1;j<=i+4;j++){ sig=sig" "lines[j]; if(lines[j] ~ /\)/) break }
      gsub(/[ \t]+/," ",sig); print "  METHOD@"i": " sig
    }
  }
  if (stop ~ /nested/) print "  [truncated at first nested type @"end"]"
}' "$IL"
```

`METHOD@<line>` gives the line to `sed -n` into for the body:

```bash
sed -n '216053,216152p' scratch/full_il.txt
```

**The `.class nested` stop is a correctness fix, not tidiness.** Without
it the extractor walks past the outer type's closing brace into the
compiler-generated `<>c__DisplayClassN_M` closure types and attributes
their fields to the outer class. This produced a real false positive
during the session: both `AeroModule` and `Aero_Rocket` appeared to have
a `public List<Surface> output` field. Neither does — it is a captured
local. Caught before publication; the tool and §A2 were both fixed.
Anything named `<>c`, `<>c__DisplayClassN_M`, or `<Method>d__N` is
scaffolding, not API.

**Finding call sites** — the same grep finds the declaration and every
caller, and lines with `IL_xxxx: call` are the callers:

```bash
grep -n "CalculateDragForce" scratch/full_il.txt
```

This is how `RemoveHighSlopeSurfaces` and `ApplyProtectionZone` were
shown to belong to the **heating** path only, with one caller each
inside `FixedUpdate_Reentry_And_Heating` — so a drag reimplementation
must not apply them.

**Decoding static array constants.** `Difficulty`'s constant tables are
initialised via `RuntimeHelpers.InitializeArray` from
`<PrivateImplementationDetails>` blobs. Map blob hash → `.data` label →
bytes, then `struct.unpack`. Full decoded tables are in
`sfs_source_reference.md` §D1.5 (not duplicated here). The headline: it
independently confirms §1.3's empirically-measured
`ispMultiplier (Normal) = 1.0000` as a literal from code.

**Reading attribute blobs.** `monodis` renders `.custom` attribute data
as hex with an ASCII comment column, which is how
`CalculateDragForce`'s tuple element names (`drag`, `centerOfDrag`) were
recovered. A signature says it returns `ValueTuple<float, Vector2>`; the
body says which is which.

## Probe bugs found (not yet fixed)

Three concrete `sfsprobe/SFSProbe.cs` issues, all found by reading IL
rather than by running anything.

- **`GetHeatState` may under-report heat.** It reads
  `Get(part, "temperature")` — the plain `Part.temperature` field — for
  every part. But `SFS.Parts.Part` **extends
  `SFS.World.Drag.HeatModuleBase`**, and a part carrying a separate
  `HeatModule` has its real temperature in that module's
  `Float_Reference`, leaving `Part.temperature` never written. Fix: read
  `Surface.owner`'s **`Temperature` property** — the probe's `Get` reads
  properties, so the virtual resolves correctly on either subclass with
  no type test. Needs a live check.

- **`thrustDirX` / `thrustDirY` / `gimbalOn` / `throttleOut` "never
  populate" — narrowed, not solved.** The IL **rules out** the obvious
  causes: every field name and wrapper access in `GetEngineDirection` is
  correct (`Composed_Vector2` really does have public `Composed_Float
  x, y` fields; `Composed<T>`, `Bool_Reference` and `Float_Reference`
  all expose a public `Value`), and lazy init is not it either
  (`Composed<T>.get_Value()` calls `CheckInitialize()` first). All four
  keys are emitted inside a single `if (eng != null)` block
  (~`SFSProbe.cs:772`), so they fail *together* exactly when
  `GetEngineDirection` returns null. Three candidates remain: no module
  matches `GetType().Name == "EngineModule"`; every engine has
  `engineOn == false` at sample time (which is **correct** outside a
  burn, and is also what `CheckOutOfFuel` produces on fuel exhaustion);
  or an exception is thrown and swallowed.

- **Bare `catch { }` blocks hide diagnosis.** `GetEngineDirection` ends
  in one with no logging, which is what makes the above undiagnosable.
  Same pattern in `GetHeatState`, `InvokeReturn`, and `Get`. **Fix this
  first** — log the exception and which branch was taken, and the
  telemetry question becomes a one-run answer. The newer `InvokeStatic`
  helper already logs and is the better model.

Separately: `GetEngineDirection`'s single-engine limit is **by design**,
and given that there is no thrust summation (§D2.0), one engine's
direction is not a meaningful summary of a multi-engine rocket anyway —
emit a per-engine array instead. It also misses `BoosterModule`
entirely, which uses `thrustVector` / `boosterPrimed` rather than
`thrustNormal` / `engineOn`.

## Dead ends

- **Trying to root-cause the thrust-telemetry bug from IL alone.** Every
  plausible mechanical explanation (wrong field names, unwrapping the
  wrong layer, lazy initialisation) was checked and eliminated. The
  remaining causes are runtime-state questions that only a live run with
  logging can settle. Do not spend more IL-reading time on it.

- **`sig.sh` without the nested-class stop.** Produced a confident,
  wrong field list. See "What worked".

## Open

- **`docs/sfs_source_reference.md` is structurally complete** — every
  planned section is written. What remains is depth, not coverage: many
  sections carry explicit `[PARTIAL]` items where a signature is
  confirmed but the body was not transcribed. The per-section Status
  tables are the authoritative list; the largest gaps are
  `Trajectory`'s path-transition machinery, `Orbit`'s encounter search,
  `DockingPortModule.Dock`, `FuelPipeModule`'s bodies, `Staging`/`Stage`
  (signatures only), and `AeroData`'s layout.
- **Whether to merge or replace `sfs_source_reference.md`** once the new
  file is reviewed. Not decided.
- **`sfs_physics_reference.md` and `high_level_checklist.md` have not
  been updated** with any of today's corrections. The Supersedes section
  above is currently the only record of them inside the repo.
- **Heat sentinel sign question.** `DissipateHeat` writes **positive**
  infinity when a module finishes cooling, but `ApplyHeat` and
  `HeatPart` both test `IsNegativeInfinity`. `PartSave.temperature`'s
  field initialiser is also `+∞`, which suggests `+∞` is the intended
  "not heated" sentinel and the two readers are the bug. Taken literally
  a fully-cooled part never re-heats. **Not verified that modules
  actually reach `Temperature ≤ 0` in practice** — testable by reading
  `Surface.owner.Temperature` across a heat-then-cool cycle.
- **SOI crossing forces rails.** Confirmed in IL: in physics mode,
  leaving the planet's SOI or entering a satellite's sets
  `PhysicsMode = false`, calls `Trajectory.EnterNextPath()`, and
  re-enters `Update()` on the rails branch in the same frame. Any burn
  or drag integration in progress stops being simulated. Never observed
  in flight — watch `Physics.PhysicsMode` flip at the boundary.
- **RCS force appears quadratic in firing-thruster count.** `sumNormal`
  is an unnormalised vector sum and is then multiplied by `count` again,
  while mass flow stays linear. Arithmetic confirmed (both `mul`
  opcodes); flight consequence **not measured**, and non-parallel
  normals partially cancel. Do not treat the `N²` as established.
- **`dragarea` (v0.27.0) has still never been run live.** This remains
  the single highest-priority next step in `high_level_checklist.md`.
- **Route 2 for rocket construction is untested.**
  `RocketManager.SpawnBlueprint(Blueprint)` is public static and
  `GenerateJoints(Part[])` derives connectivity from geometry, so an
  agent could spawn a design with no editor and no file. `SpawnBlueprint`'s
  body was not read, and `OnPartNotOwned` / `OwnershipState` suggest a
  DLC gate a generated design could trip. This bears on the open
  "editor automation vs. file-writing" decision but does not settle it.
- **A `RocketSave(Rocket)` → `ToJson` probe command** would capture
  parts, positions, orientations, all part variables, stages, joints,
  location and control state in one call, in the game's own schema — and
  sidestep the `Part.modules` walking problem. Constructor body not read.
- **`AeroFormula` coefficients (`velPow`, `densityPow`, `tempOffset`,
  `m`)** are serialized Unity data, not IL literals. The heat formula is
  otherwise fully confirmed but cannot be evaluated offline until these
  are read live.
- **Direct control writes bypass the game's own gates.** `Arrowkeys` is
  pure state; the `hasControl` and timewarp checks live in
  `ArrowkeysDrawer` (UI). `turnAxis` is unclamped on the manual branch.
  The agent must decide whether to replicate the guards or deliberately
  bypass them. Never tested live. (§E2.3)
- **`WorldTime.SetState` is public and validates nothing** — arbitrary
  timewarp speed/mode with no `CanTimewarp` check and no `timewarpIndex`
  update. Untested. (§E5.1)
- **`I_MsgLogger` is an unused diagnosis channel.** Passing a custom
  one-method implementation into `CanTimewarp` / `CanFlow` / `LoadSave`
  returns the game's own localised refusal reason instead of a bare
  `false`. Requires no Harmony. Not yet wired into the probe. (§E7.1)
- **`GameManager.main.aeroData` closes the `AeroFormula` gap**, but the
  `AeroData` layout is unread, so one live introspection pass is still
  needed to reach `velPow`/`densityPow`/`tempOffset`/`m`. (§E5.3)
- **No `session-*.md` files existed before this one**, despite
  `docs/startup_prompt.md` and memory instructing a fresh session to
  read them. Either write the missing earlier handoffs or amend the
  startup prompt.
