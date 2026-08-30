# `SFS.World.RocketManager` and `SFS.Parts.PartsLoader` — spawning

**Group file.** The two static entry points that turn save records into
live objects. Filed under `07-saveload/` rather than `01-core-flight/`
because the finding that matters here is about **constructing a rocket
without the editor**, which is a save-format question.

**Migrated** from `docs/sfs_source_reference.md` §D5.4–D5.5
(2026-08-28).

**CORRECTION / LIVE CONFIRMATION (2026-08-29):** `SpawnBlueprint`'s
body was partially read (not full-line-by-line, but enough to explain a
real crash) and the whole no-editor spawn route was live-tested
successfully. See the updated sections below — this is not a silent
overwrite of the original `[OPEN]`/`[UNTESTED-LIVE]` marks, both are
kept below with what's now known.

Schemas: [`save-records.md`](save-records.md).

---

## RocketManager

**Namespace:** SFS.World
**Kind:** class (all members static)
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] signatures · [OPEN] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @190305 · 13 methods / 3 fields

### Methods

| Signature | IL | Access | Status |
|---|---|---|---|
| `static void SpawnBlueprint(Blueprint blueprint)` | @190336 | **public static** | [CONFIRMED] signature · **[PARTIAL] body** — first 5 instructions read (2026-08-29), rest still [OPEN] |
| `static List<PartJoint> GenerateJoints(Part[] parts)` | @190532 | **public static** | [CONFIRMED] signature |
| `static void LoadRocket(RocketSave rocketSave, out bool hasNonOwnedParts)` | @191085 | public static | [CONFIRMED] signature |
| `static Rocket CreateRocket_Child(JointGroup, Rocket parent, Vector2 offset)` | @191198 | public static | [CONFIRMED] signature |
| `static void MergeRockets(Rocket a, Part partA, Rocket b, Part partB, Vector2 anchor)` | @191330 | public static | [CONFIRMED] signature |
| `static void DestroyRocket(Rocket rocket, DestructionReason reason)` | @191488 | public static | [CONFIRMED] signature |
| `static Rocket[] SpawnRockets(List<JointGroup> groups)` | @190939 | private static | [CONFIRMED] signature |
| `static Location GetSpawnLocation(JointGroup group)` | @191007 | private static | [CONFIRMED] signature |
| `static Rocket CreateRocket(JointGroup, string name, bool throttleOn, float throttlePercent, bool RCS, float rotation, float angularVelocity, Func<Rocket,Location> location, bool physicsMode)` | @191274 | private static | [CONFIRMED] signature |

#### SpawnBlueprint(Blueprint blueprint) -> void

- **Access:** public static · IL @190336
- **Preconditions:** **`World_PC` scene — `WorldView.main` must be non-
  null.** The first five instructions call
  `WorldView.main.SetViewLocation(...)`, before any part is touched, so
  calling this from `Build_PC` throws `NullReferenceException` immediately.
  This was established by reading the IL **after a live crash**
  (2026-08-29); the original guess was the opposite. `blueprint` must be
  non-null with a non-null `parts` array. **The rest of the body is
  `[OPEN]`, so further preconditions may exist** — in particular whatever
  `PartsLoader.CreateParts` requires. Flagged, not yet resolved. Contrast
  `SFS.Builds.BuildState.LoadBlueprint`, which requires `Build_PC` and no
  `WorldView` at all ([`BuildState.md`](../16-builds/BuildState.md)).
- **Behavior (partial, confirmed 2026-08-29):** the FIRST FIVE
  instructions call `WorldView.main.SetViewLocation(SpaceCenterData.
  LaunchPadLocation)` — moving the camera to the launch pad, before
  touching a single part. `WorldView.main` is a static singleton
  populated only in the `World_PC` scene (a loaded flight/world), not
  `Build_PC` (the editor). Calling this from `Build_PC` throws
  `NullReferenceException` immediately. **This was found by reading the
  IL after a real crash**, not by inspection alone — the original
  scene-gate guess ("should be in the design screen") was wrong, and
  the correct requirement is the opposite.
- **Rest of the body (blueprint rotation normalization, the
  `PartsLoader.CreateParts` call and its `Transform`/sorting-layer
  arguments, `GenerateJoints`, rocket construction) is still [OPEN]** —
  read only far enough to explain the scene requirement, not
  line-by-line.
- **Status:** [CONFIRMED] signature and scene requirement · [PARTIAL]
  body · **live-tested successfully** from `World_PC` (see "The
  finding" section below).

#### GenerateJoints(Part[] parts) -> List&lt;PartJoint&gt;

- **Access:** public static · IL @190532
- **Behavior:** **derives connectivity from geometry.** This is why
  `Blueprint` has no `joints` field — a generated design does not need
  to author joints at all.
- **Status:** [CONFIRMED] role from call sites · [OPEN] body

---

## PartsLoader

**Namespace:** SFS.Parts
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] signatures · [OPEN] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @230665 · 9 methods / 8 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `parts` | `Dictionary<string, Part>` | public | no | **the part catalog, keyed by name** — `PartSave.name` must match a key here | [CONFIRMED] |
| `partVariants` | `Dictionary<string, VariantRef>` | public | no | | [CONFIRMED] |

The other 6 fields are [OPEN].

### Methods

| Signature | IL | Status |
|---|---|---|
| `static Part[] CreateParts(PartSave[] partSaves, Transform holder, string sortingLayer, OnPartNotOwned onPartNotOwned, out OwnershipState[] ownershipState)` | @230936 | [CONFIRMED] signature · [OPEN] body |
| `static Dictionary<string,Part> LoadParts()` | @230809 | [CONFIRMED] signature |
| `static (Dictionary<string,Part>, Dictionary<string,VariantRef>) LoadPartVariants()` | @230712 | [CONFIRMED] signature |

---

## The finding: a rocket can be built without the editor

`RocketManager.SpawnBlueprint(Blueprint)` is **`public static`** and
takes a plain serializable object. `PartsLoader.CreateParts` turns
`PartSave[]` into real `Part[]`, and `RocketManager.GenerateJoints(Part[])`
**derives connectivity from geometry** — so a generated design does not
need to author joints at all.

This bears directly on the open **"editor automation vs. file-writing"**
decision in `high_level_checklist.md`. **Three viable construction
routes**, in increasing order of coupling to the UI:

1. **Write `Blueprint.txt` to disk** and load it through the game's own
   blueprint menu. Fully offline; the schema is the six fields in
   [`save-records.md`](save-records.md).
2. **Construct a `Blueprint` in memory** by reflection and call
   `RocketManager.SpawnBlueprint` — no file, no editor, no menu.
   **[CONFIRMED WORKING, 2026-08-29]** — live-tested via the
   `sfsprobe` mod's `loadblueprint` command: a single-part blueprint
   (`Capsule`) spawned successfully when called from `World_PC`
   (rocket count 1->2, part count 8->9, visually confirmed in-game).
   Must be called from `World_PC`, not `Build_PC` (see the method entry
   above). Multi-part blueprints (joint generation/connectivity via
   `GenerateJoints`) and the possible DLC/ownership gate below remain
   untested.
3. **Drive the editor UI** ([`../16-builds/`](../16-builds/)).

**Route 2 is confirmed working for the single-part case.** Remaining
risks, now narrower than originally scoped:

- The bulk of `SpawnBlueprint`'s body (past the scene-requiring opening)
  was **not** read — **[OPEN]**.
- Part `name` keys must match `PartsLoader.parts`.
- `OnPartNotOwned` / `OwnershipState` suggest a **DLC/ownership gate** on
  some parts that a generated design could trip — **[OPEN]**. Not ruled
  out by this test: `Capsule` is presumably a free/base part.

## Reflection recipe — dump the live rocket as a `RocketSave`

**[UNTESTED-LIVE]** — a complete, round-trippable snapshot in one call.

```csharp
Type rocketSaveType = FindType("SFS.World.RocketSave");
Type jsonWrapper    = FindType("SFS.Parsers.Json.JsonWrapper");
ConstructorInfo ctor = rocketSaveType.GetConstructor(
    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
    null, new Type[] { FindType("SFS.World.Rocket") }, null);
object save = ctor.Invoke(new object[] { ActiveRocket() });
string json = (string)InvokeStatic(jsonWrapper, "ToJson",
    new Type[] { typeof(object), typeof(bool) }, new object[] { save, true });
```

> This would be a genuinely useful probe command — a single call that
> captures parts, positions, orientations, **all part variables**,
> stages, joints, location and control state in the game's own schema.
> It also sidesteps the `Part.modules` walking problem entirely (see
> [`../01-core-flight/Part.md`](../01-core-flight/Part.md)).
> **[UNTESTED-LIVE]** — the `RocketSave(Rocket)` constructor body was not
> read, so it may have side effects or assume editor/flight context.

## Related: `SFS.Builds.BuildState.LoadBlueprint` -- the actual "Load Blueprint" button

**Found 2026-08-29**, prompted by a direct question about why
`RocketManager.SpawnBlueprint` needs `World_PC` when the game's editor
clearly has its own "Load" UI that doesn't. It does — and it's a
different method on a different class, not documented here in full
(that's `BuildState`'s own future entry, not yet written), but the
signature and the part relevant to spawning are confirmed:

```csharp
// SFS.Builds.BuildState, public instance method, IL @94166
instance void LoadBlueprint(Blueprint blueprint, I_MsgLogger logger,
    bool autoCenterParts, bool applyUndo,
    [opt] Vector2 offset, [opt] Action onLoaded)
```

**Behavior (confirmed from the real IL body):** calls `BuildState.Clear
(applyUndo)` **first** — this is what makes it "replace" rather than
"add". Then calls the private `BuildState.SpawnBlueprint(Blueprint,
bool, I_MsgLogger)` to create the parts, centers them (either via
`GridSize.GetOwnedGridSize`/`Part_Utility.CenterParts`, or an explicit
offset against `blueprint.center`), calls `BuildState`'s **own**
`CenterCameraOnParts` (not `WorldView.main` — no world dependency at
all), sets `BuildOrientation.main.SetOrientation`, and loads staging via
`BuildMenus.staging.Load`. Optionally invokes an `onLoaded` callback.

**This is the better fit for a design-iteration workflow** than
`RocketManager.SpawnBlueprint` above: it's the real editor mechanism,
requires `Build_PC` (not `World_PC`), and replaces rather than adds.
Implemented as the mod's `loadblueprintbuild` command (v0.33.0) — built,
installed, and **confirmed working live, 2026-08-29**: loading a
single-part blueprint (`single_capsule`) correctly replaced the design
already open in the editor. One minor known gap, not pursued further:
the spawned part didn't land at the editor viewport's visual center
(the internals of `Part_Utility.CenterParts`/`GridSize.
GetOwnedGridSize` were never read) — low priority, since a real launch
auto-centers the rocket regardless, so it has no practical effect.
`RocketManager.SpawnBlueprint` (above) remains useful for a different
case: adding an *additional* rocket to an already-running flight, which
`BuildState.LoadBlueprint` cannot do (it's editor-only) -- but per
`mod_changelog.md`'s safety note, that route should not be used as
routine operation, only one-off research.

---

## Status summary

| Item | Status |
|---|---|
| `RocketManager.SpawnBlueprint` is public static, takes a plain object | [CONFIRMED] — enables the no-editor route |
| `SpawnBlueprint` requires `World_PC` scene (`WorldView.main` dependency) | [CONFIRMED] 2026-08-29 — found via a real crash + IL read |
| `GenerateJoints` derives connectivity from geometry | [CONFIRMED] — blueprints need no joints |
| `PartsLoader.parts` is the catalog, keyed by name | [CONFIRMED] |
| `CreateParts` signature, including the ownership out-parameter | [CONFIRMED] |
| Single-part blueprint spawns successfully via `RocketManager.SpawnBlueprint` | [CONFIRMED WORKING] 2026-08-29, live-tested |
| Single-part blueprint spawns successfully via `BuildState.LoadBlueprint` (replaces current editor design) | [CONFIRMED WORKING] 2026-08-29, live-tested |
| `SpawnBlueprint` body past the scene-check opening | [OPEN] |
| `CreateParts` / `GenerateJoints` bodies | [OPEN] |
| `Part_Utility.CenterParts` / `GridSize.GetOwnedGridSize` bodies | [OPEN] -- known effect: spawned part isn't at the editor viewport's visual center; not pursued, no practical impact |
| Ownership / DLC gating (`OnPartNotOwned`, `OwnershipState`) | [OPEN] — not exercised by the free-part test |
| `MergeRockets` / `DestroyRocket` / `CreateRocket_Child` bodies | [OPEN] |
| Multi-part blueprint spawning (joint generation/connectivity) | [UNTESTED-LIVE] |
| Round-tripping a generated blueprint in the live game | [UNTESTED-LIVE] |
