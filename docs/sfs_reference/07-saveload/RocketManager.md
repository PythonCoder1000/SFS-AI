# `SFS.World.RocketManager` and `SFS.Parts.PartsLoader` — spawning

**Group file.** The two static entry points that turn save records into
live objects. Filed under `07-saveload/` rather than `01-core-flight/`
because the finding that matters here is about **constructing a rocket
without the editor**, which is a save-format question.

**Migrated** from `docs/sfs_source_reference.md` §D5.4–D5.5
(2026-08-28).

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
| `static void SpawnBlueprint(Blueprint blueprint)` | @190336 | **public static** | [CONFIRMED] signature · **[OPEN] body** |
| `static List<PartJoint> GenerateJoints(Part[] parts)` | @190532 | **public static** | [CONFIRMED] signature |
| `static void LoadRocket(RocketSave rocketSave, out bool hasNonOwnedParts)` | @191085 | public static | [CONFIRMED] signature |
| `static Rocket CreateRocket_Child(JointGroup, Rocket parent, Vector2 offset)` | @191198 | public static | [CONFIRMED] signature |
| `static void MergeRockets(Rocket a, Part partA, Rocket b, Part partB, Vector2 anchor)` | @191330 | public static | [CONFIRMED] signature |
| `static void DestroyRocket(Rocket rocket, DestructionReason reason)` | @191488 | public static | [CONFIRMED] signature |
| `static Rocket[] SpawnRockets(List<JointGroup> groups)` | @190939 | private static | [CONFIRMED] signature |
| `static Location GetSpawnLocation(JointGroup group)` | @191007 | private static | [CONFIRMED] signature |
| `static Rocket CreateRocket(JointGroup, string name, bool throttleOn, float throttlePercent, bool RCS, float rotation, float angularVelocity, Func<Rocket,Location> location, bool physicsMode)` | @191274 | private static | [CONFIRMED] signature |

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
   **[UNTESTED-LIVE]**.
3. **Drive the editor UI** ([`../16-builds/`](../16-builds/)).

**Route 2 is the one the IL most directly supports**, and it is worth a
live test before the design decision is made. Its risks are real but
narrow:

- `SpawnBlueprint`'s body was **not** read — **[OPEN]**.
- Part `name` keys must match `PartsLoader.parts`.
- `OnPartNotOwned` / `OwnershipState` suggest a **DLC/ownership gate** on
  some parts that a generated design could trip — **[OPEN]**.

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

## Status summary

| Item | Status |
|---|---|
| `RocketManager.SpawnBlueprint` is public static, takes a plain object | [CONFIRMED] — enables the no-editor route |
| `GenerateJoints` derives connectivity from geometry | [CONFIRMED] — blueprints need no joints |
| `PartsLoader.parts` is the catalog, keyed by name | [CONFIRMED] |
| `CreateParts` signature, including the ownership out-parameter | [CONFIRMED] |
| `SpawnBlueprint` / `CreateParts` / `GenerateJoints` bodies | [OPEN] |
| Ownership / DLC gating (`OnPartNotOwned`, `OwnershipState`) | [OPEN] |
| `MergeRockets` / `DestroyRocket` / `CreateRocket_Child` bodies | [OPEN] |
| Round-tripping a generated blueprint in the live game | [UNTESTED-LIVE] |
