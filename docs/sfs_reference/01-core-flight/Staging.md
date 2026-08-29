# `SFS.World.Staging` and `SFS.World.Stage`

**Group file.** Signatures confirmed; **most bodies not read** — this
entry is deliberately [PARTIAL] and says so per item.

**Migrated** from `docs/sfs_source_reference.md` §B7 (2026-08-28).

Save side: [`../07-saveload/save-records.md`](../07-saveload/save-records.md)
(`StageSave`).

---

## Staging

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @183261 · 13 methods / 5 fields

### Fields

All public.

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `rocket` | `Rocket` | public | no | | [CONFIRMED] |
| `editMode` | `Bool_Local` | public | no | | [CONFIRMED] |
| `stages` | `List<Stage>` | public | no | the ordered stage list | [CONFIRMED] |
| `onStageAdded` | `Action<Stage, int>` | public | no | | [CONFIRMED] |
| `onStageRemoved` | `Action<Stage>` | public | no | | [CONFIRMED] |

**[OPEN]** — whether `stages[0]` is the next to fire. Not verified.

### Methods

| Signature | Access | Status |
|---|---|---|
| `ClearStages(bool record)` | public | [CONFIRMED] signature |
| `InsertStage(Stage a, bool record, int index = …)` | public | [CONFIRMED] signature |
| `RemoveStage(Stage a, bool record)` | public | [CONFIRMED] signature |
| `ApplyReorder(Dictionary<Stage, int> order)` | public | [CONFIRMED] signature |
| `Load(StageSave[] stageSaves, Part[] parts, bool record)` | public | [CONFIRMED] signature |
| `CreateStages(StageSave[] stages, Part[] parts)` | **public static** | [CONFIRMED] signature |
| `OnSplit(Rocket parentRocket, Rocket childRocket)` | **public static** | [CONFIRMED] signature |
| `OnMerge(Rocket A, Rocket B)` | **public static** | [CONFIRMED] signature |
| `GetPartGridType(Part part, out int index)` | **public static** | [CONFIRMED] signature |
| `SetStages`, `RemoveEmptyStages`, `GetForUndo` | private | [CONFIRMED] signature |

**All bodies [PARTIAL] — not read.**

### The `record` parameter

The `bool record` parameter throughout is **undo-system bookkeeping**
(`SFS.Builds.Undo/GridType` appears in `GetForUndo`), **not
persistence**. An agent manipulating stages programmatically should pass
`false` unless it wants entries in the editor's undo stack.

> **[OPEN].** The parameter's effect is *inferred* from `GetForUndo`'s
> return type — exactly the kind of name-based inference this reference
> is meant to avoid. Marked OPEN until a body is read.

### Two members that matter for the agent

- **`OnSplit` / `OnMerge`** are the hooks that redistribute stages when a
  craft separates or docks — directly relevant to modelling what happens
  to the staging plan after separation. **Bodies not read — [PARTIAL].**
- **`Load(StageSave[], Part[], bool)` and the static
  `CreateStages(StageSave[], Part[])`** are the bridge from the save
  format to live `Stage` objects, and **both are public** — the route for
  building a staging plan programmatically alongside
  `RocketManager.SpawnBlueprint`. **Bodies not read — [PARTIAL].**

---

## Stage

**Namespace:** SFS.World
**Kind:** class (`[Serializable]`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @184226 · 9 methods / 6 fields

### Fields

All public.

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `stageId` | `int` | public | no | | [CONFIRMED] |
| `parts` | `List<Part>` | public | no | | [CONFIRMED] |
| `usedToHaveParts` | `bool` | public | no | semantics [OPEN] | [CONFIRMED] shape |
| `onPartInserted` | `Action<Part, int>` | public | no | | [CONFIRMED] |
| `onPartRemoved` | `Action<int>` | public | no | | [CONFIRMED] |
| `useStageIdentifier` | `int` | public | no | semantics [OPEN] | [CONFIRMED] shape |

`PartCount` is a property over `parts`; `Contains(Part)` is a list
search.

### Methods

Mutators — `ToggleSelected(Part, bool crateNewStep)` *(sic — the
misspelling is in the shipped IL)*, `AddPart(Part, bool record, bool
createNewStep)`, `InsertPart(Part, int index, bool record)`,
`RemovePart(Part, bool record)`, `SetPartAtIndex(int, Part)` — plus a
private `OnPartDestroyed(Part)`.

**All signatures only — [PARTIAL].**

## Status summary

| Item | Status |
|---|---|
| `Staging` and `Stage` field layouts | [CONFIRMED] |
| Full method signatures for both | [CONFIRMED] |
| `CreateStages` / `OnSplit` / `OnMerge` / `GetPartGridType` are public static | [CONFIRMED] |
| Every body in both classes | [PARTIAL] — not read |
| Meaning of the `record` parameter | [OPEN] — inferred only |
| Whether `stages[0]` is the next to fire | [OPEN] |
| `useStageIdentifier`, `usedToHaveParts` semantics | [OPEN] |
