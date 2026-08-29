# `Line2` — the 2D segment struct

**Migrated** from `docs/sfs_source_reference.md` §C1.3 (2026-08-28).
Signatures re-read from IL during migration.

---

## Line2

**Namespace:** *(none — top-level, global namespace)*
**Kind:** struct (`sealed`, `sequential`, `serializable`)
**Extends:** System.ValueType
**Implements:** —
**Status:** [CONFIRMED] shape · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @15536 · 21 methods / 2 fields

The segment type used throughout the drag/aero pipeline
([`../02-drag-aero/geometry-types.md`](../02-drag-aero/geometry-types.md)
— it is the `line` field of `Surface`). Much richer than its two fields
suggest: **21 methods, not 2 fields**, and three of them are ambiguous
overload pairs.

**Reflection name:** `"Line2"` — no namespace prefix.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `start` | `UnityEngine.Vector2` | public | no | segment start | [CONFIRMED] |
| `end` | `UnityEngine.Vector2` | public | no | segment end | [CONFIRMED] |

### Methods

All public. Bodies not traced except where the drag pipeline depends on
them, so the default status below is [PARTIAL] — shape confirmed,
behaviour inferred from the name and from call sites.

| Signature | IL | Notes | Status |
|---|---|---|---|
| `Vector2 Size { get; }` | @15543 | `end - start` | [PARTIAL] |
| `float SizeX { get; }` | @15558 | | [PARTIAL] |
| `float SizeY { get; }` | @15575 | | [PARTIAL] |
| `.ctor(Vector2 start, Vector2 end)` | @15592 | | [CONFIRMED] |
| `static Line2 StartSize(Vector2 start, Vector2 size)` | @15608 | construct from start + extent | [PARTIAL] |
| `Vector2 Lerp(float t)` | @15623 | **ambiguous pair** | [PARTIAL] |
| `Vector2 Lerp(float t_X, float t_Y)` | @15639 | **ambiguous pair** — independent t per axis | [PARTIAL] |
| `Vector2 LerpUnclamped(float t)` | @15666 | **ambiguous pair** | [PARTIAL] |
| `Vector2 LerpUnclamped(float t_X, float t_Y)` | @15693 | **ambiguous pair** | [PARTIAL] |
| `void Flip()` | @15720 | mutating | [PARTIAL] |
| `void FlipHorizontally()` | @15745 | mutating | [PARTIAL] |
| `void FlipVertically()` | @15779 | mutating | [PARTIAL] |
| `Vector2 GetPositionAtX(float x)` | @15813 | clamped | [PARTIAL] |
| `Vector2 GetPositionAtY(float y)` | @15858 | clamped | [PARTIAL] |
| `Vector2 GetPositionAtX_Unclamped(float x)` | @15908 | **used by `AeroModule.GetExposedSurfaces`** to split overlapping segments | [CONFIRMED] as a call site |
| `float GetHeightAtX(float x)` | @15923 | clamped | [PARTIAL] |
| `float GetHeightAtX_Unclamped(float x)` | @15978 | | [PARTIAL] |
| `float GetSlope()` | @16017 | instance — **ambiguous with the static one** | [PARTIAL] |
| `static float GetSlope_Abs(Vector2 start, Vector2 end)` | @16054 | | [PARTIAL] |
| `static float GetSlope(Vector2 start, Vector2 end)` | @16076 | static — **ambiguous with the instance one** | [PARTIAL] |
| `static bool FindIntersection_Unclamped(Line2 a, Line2 b, out Vector2 position)` | @16097 | | [PARTIAL] |

### Gotchas

- **Three ambiguous overload pairs**: `Lerp`, `LerpUnclamped`, and
  `GetSlope` (instance vs static — these differ in *binding* as well as
  parameters, so both the flags and the parameter types must be right).
  Catalogued in
  [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
- The `Flip*` methods are **mutating** on a struct — calling them through
  reflection on a boxed copy mutates the copy, not the original.
- The two-argument `Lerp` interpolates each axis independently; it is not
  a 2D parametric point.

## Status summary

| Item | Status |
|---|---|
| Top-level, no namespace; struct with two public `Vector2` fields | [CONFIRMED] |
| Full 21-method surface | [CONFIRMED] signatures |
| `Lerp` / `LerpUnclamped` / `GetSlope` ambiguity | [CONFIRMED] |
| `GetPositionAtX_Unclamped` used by `GetExposedSurfaces` | [CONFIRMED] |
| All other method bodies | [OPEN] |
