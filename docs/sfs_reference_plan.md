# SFS Documentation — the plan (persistent reference)

This file is the standing instructions for building "the SFS Documentation"
(`docs/sfs_reference/`). Any new session working on this should read this
file plus `docs/sfs_reference/INVENTORY.md` before doing anything else --
don't re-derive scope or re-decide settled questions from scratch.

## What this actually is

**This is "the SFS Documentation" -- a standalone, complete reference to
Spaceflight Simulator 1.6.00.16's own decompiled source code.** It is NOT
documentation of `sfsprobe` (our mod), and it isn't scoped to "what this
project currently needs" -- it documents the game itself, completely,
independent of anything built on top of it. The only relationship to our
mod is downstream: we use this documentation to verify our mod still
works correctly, especially whenever SFS itself updates versions.

**Full game coverage, including UI/Builds/ModGUI.** `SFS.UI`,
`SFS.Builds`, and `SFS.UI.ModGUI` are in scope, same as everything else.

**~26 vendored third-party types are excluded** (Firebase,
TranslucentImage, Unity IAP, the SDWebImage port, Steam/GPGS glue) --
recorded with the reason, not silently dropped. These aren't SFS's own
code and document nothing about game behavior.

## Structure -- no monolithic file

```
docs/sfs_reference/
  INDEX.md              -- master table of contents + coverage tracker
  manifest.json          -- machine-readable companion index
  INVENTORY.md            -- the full 969-type inventory (Phase 1 Step 0 output)
  inventory.json          -- machine-readable inventory
  00-infrastructure/
  01-core-flight/
  02-drag-aero/
  03-heat-destruction/
  04-engines/
  05-rcs/
  06-soi-terrain/
  07-saveload/
  08-parametric-expressions/
  09-resources-fuel/
  10-control-input/
  11-joints-docking/
  12-world-scene-timewarp/
  13-challenges-logging/
  14-misc-part-modules/
  15-ui/
  16-builds/
  17-modgui/
  18-maps-navigation/     -- SFS.World.Maps
  19-career-progression/  -- SFS.Career
  20-localization-audio/  -- SFS.Translations + SFS.Audio
  21-platform-rendering/
```

**One markdown file per class** (or a small tightly-coupled group) --
not one file per category.

**Strict per-class template, followed identically everywhere:**

```markdown
## ClassName

**Namespace:** SFS.Whatever
**Kind:** class | interface | struct | abstract class
**Extends:** BaseClass (if any)
**Implements:** IInterface1, IInterface2 (if any)
**Status:** [CONFIRMED] | [PARTIAL] | [OPEN]
**Depth:** FULL | LIGHT (see tiered depth bar below)

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|

### Methods

#### MethodName(ParamType paramName, ...) -> ReturnType

- **Access:** public/private/protected, static/instance
- **Parameters:** what each one means, valid range/units if known
- **Returns:** what it means, including null/default cases
- **Preconditions:** REQUIRED for every FULL-depth method, not optional
  prose. What must already be true/exist before calling this --
  required scene, a live singleton that must be populated (e.g.
  "requires World_PC -- WorldView.main must be non-null"), an object
  that must already be initialized, an ordering requirement relative to
  other calls. If nothing is required beyond a valid instance/args,
  write "None beyond valid arguments" explicitly -- don't leave the
  field out, since an absent field looks identical to "not checked yet."
  This is the field that would have caught the loadblueprint World_PC/
  Build_PC mixup (2026-08-29) before any mod code was written, instead
  of after a real crash.
- **Behavior:** what the IL body actually does (FULL depth only --
  LIGHT depth may skip this and note "not read, low-priority UI class")
- **Side effects:** state mutation, events fired, allocations
- **Gotchas:** known hangs, no-ops, ordering requirements, ambiguous overloads
- **Status:** [CONFIRMED] | [PARTIAL] | [OPEN]
```

**Tiered depth bar:** FULL depth (real IL-body behavior read) for
anything reflectable/callable -- simulation, gameplay logic, anything an
agent could plausibly call. LIGHT depth (signature + one-line purpose
only, explicitly marked, no full behavior narrative) for pure-view/
UI-only classes with no simulation relevance. Every class still gets an
entry either way -- LIGHT is not "skip," it's "less depth, explicitly
marked as such."

**HARD RULE, added 2026-08-29 after a real incident:** a method whose
body is marked `[OPEN]` (not read) must not be wired into a live
SFSProbe.cs command if that command mutates game state -- spawns or
destroys objects, writes save data, changes scene, or otherwise does
something irreversible or state-dependent. A read-only probe/dump
command built on an `[OPEN]`-body method is lower-risk and can proceed
with the risk noted; a command that DOES something to the live game
cannot. This is not a new documentation requirement so much as a
restatement of "live IL-body reads not signatures-only" (already a
standing rule below) with the enforcement point made explicit: the
body must be read BEFORE the mod command is written, not discovered to
be necessary after a live failure. (What actually happened 2026-08-29:
`RocketManager.SpawnBlueprint` was correctly marked `[OPEN]` body in
the docs -- the documentation was honest. A live mod command was built
and shipped around it anyway, which is the actual rule violation. The
first live call crashed; reading the body after the fact explained why
and revealed the method needed `World_PC`, not the `Build_PC` that had
been guessed. The new Preconditions field above is the structural fix
so this class of gap is visible before code is written, not just
after -- but the underlying discipline of reading bodies before
shipping state-mutating commands is what actually prevents it.)

**`INDEX.md`** -- one row per documented type: name, namespace, kind,
file path, one-line summary, status, depth, coverage count.

**`manifest.json`** -- same fields as INDEX.md rows, machine-readable,
kept in sync incrementally per class, not regenerated in one pass.

## Definition of done

Every class's documentation needs to answer: real signature, inputs,
outputs; what the code does and how (FULL depth: from IL bodies, not
names; LIGHT depth: at minimum an accurate signature and purpose);
how it's structured; when/how/where it's accessible (Preconditions,
above -- not optional); what can/cannot be safely run. AND it needs to
live in the right file, follow the template, and be reflected in
INDEX.md and manifest.json.

Standing rules throughout: live IL-body reads not signatures-only (for
FULL-depth classes), Confirmed/Partial/Open per member, document
corrections rather than silently overwrite, save incrementally (disk +
Mnemoverse) not batched at the end, checkpoint every 3-4 classes and wait.
Added 2026-08-29: a state-mutating SFSProbe.cs command must not be built
on a method whose body is still `[OPEN]` -- see the HARD RULE above.

## Phases

**Phase 1, Step 0 (inventory) -- DONE.** See `INVENTORY.md`. 969 real
types, 53 namespaces, 6,137 methods, 4,078 fields.

**Phase 1, Step 1 -- migrate existing content.** The old
`docs/sfs_source_reference.md` (~6,590 lines) gives named headings to
only 67 of 969 types (266 mentioned anywhere in prose). This is a real
but bounded job. Split into the new structure, one class per file,
reformatted into the strict template. `docs/` is untracked in git --
scratch-backup first, diff-check nothing gets silently dropped. Build
`INDEX.md` and `manifest.json` from this as you go.

**Phase 1, Step 1.5 -- Mod-Integration Safety Audit. NEW, added
2026-08-29, run once, high priority -- do this before continuing
general Step 2 coverage.** Prompted by a real incident: a live
SFSProbe.cs command (`loadblueprint`) was built around
`RocketManager.SpawnBlueprint`, a method correctly marked `[OPEN]` body
in the docs, and its first live call crashed for a reason (a `World_PC`
scene requirement) that reading the body up front would have caught.
This step finds any OTHER instance of the same gap already shipped.

Procedure: read `sfsprobe/SFSProbe.cs`'s `Command()` switch top to
bottom. For every `case`, list every SFS game method it calls via
reflection (`FindType`/`GetMethod`/`Invoke`, or a direct call on an
already-resolved type). Cross-reference each against
`docs/sfs_reference/`'s current coverage (or `sfs_source_reference.md`
for anything not yet migrated): is its body `[CONFIRMED]`,
`[PARTIAL]`, or `[OPEN]`? Classify each command:

- **Read-only** (dumps/snapshots/telemetry -- `snapshot`, `world`,
  `menu`, `ping`, `dragarea`, `achievements`, `geometry`, `diag`) --
  lower risk even if body is `[OPEN]`, since nothing is mutated. Note
  but don't block on these.
- **State-mutating** (`throttle`, `master`, `ignite`, `revert`,
  `autostop`, `cheat`, `loadblueprint`, `loadblueprintbuild`, and any
  future one) -- if the underlying method's body is still `[OPEN]`,
  **read it now**, out of normal coverage order, and add a
  Preconditions entry per the template above. If reading it reveals a
  wrong assumption already shipped in `SFSProbe.cs` (like the
  Build_PC/World_PC case), flag it clearly as a finding -- don't fix
  the mod code in this session (that's Python/C# work, a different
  session's job), just document the gap precisely enough that fixing
  it is a five-minute follow-up, and note it in the handoff.

Output: a short table in the handoff (command name, methods called,
body status, risk classification, any concrete findings) plus updated
Preconditions fields for every method now read. This step is NOT about
achieving full coverage of these classes -- it's specifically about
closing the "body unread, already shipped" gap. Move on to Step 2 once
every state-mutating command's underlying methods have a real
Preconditions entry (even if that entry is "requires further reading,
flagged, not yet resolved" -- honesty beats silence, but it must be a
deliberate, visible flag, not an absent field).

**Phase 1, Step 2 -- cover everything else.** ~90% of the total work.
Includes all of UI/Builds/ModGUI now. Same template, tiered depth bar
above.

**Phase 1, Step 3 -- retire the old file.** Once migration + new
coverage are done and confirmed, delete `docs/sfs_source_reference.md`,
repoint every reference to it (`docs/startup_prompt.md`, `README.md`,
`CLAUDE.md`, `mod_changelog.md`, `python_changelog.md`) at
`docs/sfs_reference/INDEX.md`. Grep the whole project first.

**Phase 2 -- confirmed empirical values** (only after Phase 1 is fully
done). Lives in `docs/sfs_reference/CONFIRMED_VALUES.md`. Pull every
genuinely CONFIRMED value from `sfs_physics_reference.md` section 1.
**Explicitly exclude anything drag-related** -- the dragArea mechanism
is confirmed live (2026-08-28), but the values aren't empirically
validated against measured flight deceleration yet
(`python/analyze_dragarea.py` exists for that, hasn't been run against a
real flight). One master table, cross-referenced from elsewhere rather
than duplicated.

**Phase 3 -- final verification pass** (only after Phases 1 and 2).
Full re-audit of every file against fresh IL, not just new material.
Corrections documented, not silently overwritten. Confirm INDEX.md/
manifest.json accuracy and that the old file's retirement was complete.
Close with an honest check against the Definition of Done above.

## Session boundaries -- stop and hand off explicitly

This task is too large for one continuous session. At each of these
points: run `/session-save`, summarize progress and what's next, and
tell Christian to start a new session before continuing.

- After Step 1 (migration) -- before starting Step 1.5
- After Step 1.5 (mod-integration safety audit) -- before starting Step 2
- Roughly every 15-20 classes within Step 2
- After Step 2, before Step 3
- Between Phase 1 and Phase 2
- Between Phase 2 and Phase 3
- Within Phase 3's audit, roughly every 20-30 files

A fresh session starts by reading this file plus
`docs/sfs_reference/INDEX.md` (once it exists) to see exactly where the
last one left off.

---

## Operation: Tidal Wave -- system-level reconstruction documentation

**This is a separate, parallel track, not Phase 4.** It does not block
on, and is not blocked by, Phases 1-3 above. It can start any time --
ideally once Step 1.5 is done and a meaningful chunk of per-class
coverage exists to draw from, but it doesn't have to wait for that.
Sessions on this track pull from whatever's currently confirmed in
`docs/sfs_reference/` (and `sfs_source_reference.md` for anything not
yet migrated), and flag/cross-link rather than block when they hit an
under-documented class.

**What this actually is.** The per-class reference (Phases 1-3) answers
"what does this method do." Operation: Tidal Wave answers "how does the
game actually work, end to end, well enough that someone could rebuild
it -- or correctly extend it -- without ever touching the source or the
IL." It is the kind of documentation an engineer on the original team
would maintain for onboarding, not what a fan-made wiki produces: it
covers how to use a system, how it works internally, what must be true
before you touch it, and exactly where people get it wrong.

**No code.** Prose, sequences, data-flow descriptions, cross-references
-- not reproduced C#/IL. Consistent with how the rest of this project
already documents behavior (describing what a method does, not pasting
its body) -- the difference here is scope (a whole system, not one
method) and audience (someone building a new feature, not someone
looking up a signature).

**Why this exists, concretely.** The `loadblueprint` incident
(2026-08-29) was a SCENE-LIFECYCLE problem -- `RocketManager.
SpawnBlueprint` needing `World_PC` isn't a fact about that one method,
it's a fact about how the game's Hub_PC/Build_PC/World_PC/Home_PC scene
lifecycle populates and tears down singletons like `WorldView.main`.
No per-class doc, however good, tells you that on its own -- you'd need
to already know to go look. A system-level doc titled "Scene Lifecycle"
would have stated it as a fact about the system, found once and never
relearned the hard way again.

**Definition of done, per system** (this is what keeps "reconstruct the
entire game" from being unbounded): a developer with zero access to the
source or the IL could build a NEW feature that correctly integrates
with that system, using ONLY this doc plus the per-class reference it
links to -- no guessing, no re-deriving a precondition by crashing into
it first. If a system's doc can't clear that bar, it isn't done.

**Format.** `docs/sfs_reference/tidal_wave/`, one file per system.
Template:

```markdown
## System Name

**Status:** [CONFIRMED] | [PARTIAL] | [OPEN]
**Key participants:** classes/methods involved, each linking to its
  per-class entry (this doc doesn't re-derive signatures, it connects them)

### Overview
What this system does and why it exists.

### How it works, end to end
The actual sequence/flow -- real call chains, real ordering, what
runs when, on rails vs live, what's gated and by what.

### How to use / integrate
If you're building a feature that touches this system, here's the
real entry points and the correct way to call them.

### Prerequisites
What must already be true before this system can be used --
scene, populated singletons, initialization order.

### Pitfalls
Known gotchas, wrong assumptions already made and corrected (e.g. the
Build_PC/World_PC case belongs here, in "Scene Lifecycle" and/or
"Rocket Construction & Spawning").
```

**Starting system list** (not exhaustive, not rigid -- refine as work
proceeds; prioritize systems SFSProbe.cs's existing commands already
touch, since those are live risk, before expanding outward):

- Scene lifecycle (Hub_PC/Build_PC/World_PC/Home_PC transitions; what's
  populated/torn down at each; `WorldView.main`'s lifecycle -- this one
  directly would have prevented the loadblueprint incident)
- Rocket construction & spawning (`Blueprint` -> `PartSave` -> `Part` ->
  `Rocket`, both routes: `BuildState.LoadBlueprint` (editor) and
  `RocketManager.SpawnBlueprint` (world) -- including WHY they differ
  and when each is actually appropriate, not just that they exist)
- Physics tick loop (`FixedUpdate` order of operations: gravity, drag,
  thrust, RCS, heat, staging checks -- what runs when, live vs on rails)
- Timewarp system (physics warp vs rails warp, what's gated off in each)
- Save/load pipeline (`WorldSave`, `RocketSave`, `Blueprint`, the
  `JsonWrapper` layer, on-disk file layout)
- Parametric part variable system (`Composed_Float` expression
  evaluation, `VariablesModule`, how part configuration actually resolves)
- Staging system (`Staging.Load`, stage IDs, part-to-stage mapping,
  separation events)
- Drag/aerodynamics system (`GetDragSurfaces` -> `GetExposedSurfaces` ->
  `CalculateDragForce`, rotation-matrix derivation)
- Heat/destruction system (temperature accumulation, tolerance
  thresholds, destruction triggers)
- Control input system (`Arrowkeys`, `hasControl` gating in the UI
  layer, direct-write bypass implications)
- Engine/thrust system (`EngineModule`, gimbal, throttle resolution
  chain, the multi-engine independent-force model)
- RCS system (thruster selection logic, on/off thresholds)
- Editor/build system (`BuildState`, `BuildMenus`, `BuildGrid`,
  `BuildOrientation`, part placement/undo)
- Mod loading system (`ModLoader.Mod` contract, the Harmony/MonoMod
  situation)
- Achievement/challenge system (`Challenge` catalog, completion tracking)
- SOI/orbital mechanics system (`Kepler` library, trajectory prediction,
  SOI-crossing physics-mode transitions)
- Resource/fuel system (`ResourceModule`, per-stage fuel aggregation)

**Session boundaries for this track:** checkpoint after every 1-2
complete system docs (these are much larger than a single class entry),
run `/session-save`, hand off. This track's checkpoints are independent
of Phases 1-3's -- interleave however makes sense; they don't block
each other.
