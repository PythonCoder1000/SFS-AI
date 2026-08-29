# Drag geometry types — `SurfaceData`, `Surfaces`, `Surface`, `Valid`

**Group file.** The four types that carry drag geometry between the parts
and the aero pipeline. Two live in `SFS.Parts.Modules` (the source, on
the part) and two in `SFS.World.Drag` (the result, consumed by
[`AeroModule.md`](AeroModule.md)).

The math types they are built on — `Line2` and `Matrix2x2` — are in
[`../00-infrastructure/`](../00-infrastructure/).

**Migrated** from `docs/sfs_source_reference.md` §C1.3 (2026-08-28).

---

## SurfaceData

**Namespace:** SFS.Parts.Modules
**Kind:** abstract class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [PARTIAL]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @268763 · 8 methods / 6 fields

The per-part geometry provider. `Aero_Rocket.GetDragSurfaces` walks
`partHolder.GetModules<SurfaceData>()` and reads `surfacesFast` off each.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `attachmentSurfaces` | `bool` | private | no | backs `Attachment` | [CONFIRMED] |
| `dragSurfaces` | `bool` | private | no | backs `Drag` — the **per-part drag opt-out** | [CONFIRMED] |
| `surfaces` | `List<Surfaces>` | public | no | the full geometry | [CONFIRMED] |
| `surfacesFast` | `List<Surfaces>` | public | no | **the drag geometry** — what the aero path actually reads | [CONFIRMED] |
| `onChange` | `Event_Local` | public | no | `[NonSerialized]` | [CONFIRMED] |
| `heatModule` | `HeatModuleBase` | public | no | `[NonSerialized]`; becomes `Surface.owner` | [CONFIRMED] |

### Methods

#### get_Attachment() -> bool

- **Access:** public instance (`Attachment` property) · IL @268778
- **Status:** [CONFIRMED] signature · [PARTIAL] body (returns
  `attachmentSurfaces`)

#### get_Drag() -> bool

- **Access:** public instance (`Drag` property) · IL @268796
- **Returns:** whether this part contributes to drag at all
- **Gotchas:** a part with this false contributes **nothing** to
  `GetDragSurfaces` — checked before any geometry is read.
- **Status:** [CONFIRMED]

#### Output() -> void

- **Access:** `public abstract` instance · IL @268814
- **Status:** [CONFIRMED] signature · [OPEN] per-subclass bodies

#### SetData(List&lt;Surfaces&gt;) -> void

#### SetData(List&lt;Surfaces&gt;, List&lt;Surfaces&gt;) -> void

- **Access:** both `protected` (`family`) · IL @268821 / @268835
- **Gotchas:** **a confirmed ambiguous overload pair.** Both are
  protected, so reflection needs `NonPublic | Instance` *and* explicit
  parameter types. Catalogued in
  [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
- **Status:** [CONFIRMED] signatures · [OPEN] bodies

#### IsSurfaceCovered(SurfaceData) -> bool

- **Access:** **public static** · IL @268854
- **Status:** [CONFIRMED] signature · [OPEN] body

---

## Surfaces

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @268970 · 3 methods / 3 fields

One closed or open outline belonging to one transform. Note the plural
name — a `SurfaceData` holds a *list* of `Surfaces`, each of which is
itself a polyline.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `points` | `Vector2[]` | public **readonly** | no | outline vertices, in `owner`-local space | [CONFIRMED] |
| `owner` | `UnityEngine.Transform` | public **readonly** | no | the transform `points` are relative to; `TransformPoint` on it gives world space | [CONFIRMED] |
| `loop` | `bool` | public **readonly** | no | whether the outline closes | [CONFIRMED] |

### Methods

#### GetSurfacesWorld() -> Line2[]

- **Access:** public instance · IL @268999
- **Returns:** the outline as world-space line segments
- **Status:** [CONFIRMED] signature · [OPEN] body

---

## Surface

**Namespace:** SFS.World.Drag
**Kind:** struct
**Extends:** System.ValueType
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @217767 · 1 method / 3 fields

One drag segment. This is the element type of every list the aero
pipeline passes around.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `owner` | `HeatModuleBase` | public | no | which part the segment belongs to — used by the heating path | [CONFIRMED] |
| `valid` | `SFS.World.Drag.Valid` | public | no | a **shared invalidation token**, not a bool — see below | [CONFIRMED] |
| `line` | `Line2` | public | no | the segment itself, in **velocity-aligned world space** as produced by `GetDragSurfaces` | [CONFIRMED] |

**Gotcha:** `Surface.line.start/end` are velocity-aligned, not world.
To recover world coordinates multiply by `Matrix2x2.Angle(+a)` — the
non-negated matrix — or call `AeroModule.RotateSurfaces`.

---

## Valid

**Namespace:** SFS.World.Drag
**Kind:** **class** (reference type — *not* a struct)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @218601 · 1 method / 1 field

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `valid` | `bool` | public | no | the flag | [CONFIRMED] |

**Gotchas:** a reference type holding one `bool`, deliberately. It is a
**shared invalidation token, not a per-surface flag** — many `Surface`
structs point at the same `Valid` instance, so flipping it invalidates a
whole group at once. Reading `surface.valid` reflectively gives you the
token *object*; the bool is one level deeper:
`Get(Get(surface, "valid"), "valid")`.

## Status summary

| Item | Status |
|---|---|
| `SurfaceData` field layout; `surfacesFast` is the drag geometry | [CONFIRMED] |
| `SurfaceData.Drag` per-part opt-out | [CONFIRMED] |
| `SurfaceData.SetData` is an ambiguous protected pair | [CONFIRMED] |
| `SurfaceData.Output` / `IsSurfaceCovered` / `SetData` bodies | [OPEN] |
| `Surfaces` field layout, all three readonly | [CONFIRMED] |
| `Surfaces.GetSurfacesWorld` body | [OPEN] |
| `Surface` field layout | [CONFIRMED] |
| `Valid` is a class and a shared token | [CONFIRMED] |
| `SurfaceData` concrete subclasses | [OPEN] — Step 2, `14-misc-part-modules/` |
