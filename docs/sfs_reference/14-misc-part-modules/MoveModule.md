# `SFS.Parts.Modules.MoveModule` and `ToggleModule`

**Group file.** `ToggleModule` is trivially small and delegates all
behaviour to `MoveModule`, so they are documented together.

**Migrated** from `docs/sfs_source_reference.md` §E6.3 (2026-08-28).

---

## ToggleModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @275143 · 3 methods / 2 fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `label` | `TranslationVariable` | public | no | | [CONFIRMED] |
| `state` | `MoveModule` | public | no | **all behaviour lives here** | [CONFIRMED] |

---

## MoveModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `I_InitializePartModule` (with an explicit `Priority`)
**Status:** [CONFIRMED] API · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @273975 · 11 methods / 6 fields

**The generic animation/state driver.** Used for toggles, for engine
gimbals ([`../04-engines/EngineModule.md`](../04-engines/EngineModule.md)),
for RCS thruster visuals
([`../05-rcs/RcsModule.md`](../05-rcs/RcsModule.md)), and for the
control-pad animations in `ArrowkeysDrawer`
([`../10-control-input/control-input.md`](../10-control-input/control-input.md)).

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `time` | `Float_Reference` | public | no | current animation position | [CONFIRMED] |
| `targetTime` | `Float_Reference` | public | no | commanded position | [CONFIRMED] |
| `animationTime` | `float` | public | no | duration | [CONFIRMED] |
| `unscaledTime` | `bool` | public | no | **animates on real time, not world time** — see the gotcha | [CONFIRMED] |
| `animationElements` | `MoveData[]` | public | no | | [CONFIRMED] |

> **`time` and `targetTime` being `Float_Reference` means a toggle's
> position is part of the variable system** — and therefore **serialised
> and parametric-capable**, not transient UI state. It lands in
> `PartSave.NUMBER_VARIABLES` like any other part variable.

> **`unscaledTime` is worth flagging:** a `MoveModule` with it set
> animates on **real time rather than world time**, so **its behaviour
> under timewarp differs from the rest of the simulation.** Which parts
> set it is **[OPEN]** — it is serialized data.

### Methods

**The programmatic route for every toggleable part**, all public:

| Signature | IL | Status |
|---|---|---|
| `void Toggle()` | @274442 | [CONFIRMED] signature |
| `void Activate()` | @274466 | [CONFIRMED] signature |
| `void SetTargetTime(float newTargetTime)` | @274480 | [CONFIRMED] signature |
| `void SetTime(float newTime)` | @274494 | [CONFIRMED] signature |

`Update` @274049 and `ApplyAnimation` @274111 **not read — [PARTIAL]**.

`SFS.Parts.Modules.MoveData` and its nested `Type` enum are separate
types — own entries [OPEN], Step 2.

## Status summary

| Item | Status |
|---|---|
| `ToggleModule` delegates entirely to `MoveModule` | [CONFIRMED] |
| `MoveModule` field layout | [CONFIRMED] |
| Public API (`Toggle` / `Activate` / `SetTime` / `SetTargetTime`) | [CONFIRMED] |
| Toggle state lives in the variable system | [CONFIRMED] |
| `MoveModule.Update` / `ApplyAnimation` | [PARTIAL] |
| Which parts set `unscaledTime` | [OPEN] |
| `MoveData` and `MoveData/Type` own entries | [OPEN] — Step 2 |
