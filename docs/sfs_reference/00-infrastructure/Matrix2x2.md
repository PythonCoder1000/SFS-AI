# `Matrix2x2` — the 2×2 rotation matrix

**Migrated** from `docs/sfs_source_reference.md` §C1.3 (2026-08-28).
Signatures re-read from IL during migration.

---

## Matrix2x2

**Namespace:** *(none — top-level, global namespace)*
**Kind:** **class** — a reference type, *not* a struct
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] shape · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @2535 · 7 methods / 2 fields

The rotation matrix fed into and out of the drag pipeline. Two facts
about it are load-bearing and both are easy to get wrong: **it is a
class**, and **its multiplication is not commutative across overloads**.

**Reflection name:** `"Matrix2x2"` — no namespace prefix.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `x` | `UnityEngine.Vector2` | **private** | no | first basis vector | [CONFIRMED] |
| `y` | `UnityEngine.Vector2` | **private** | no | second basis vector | [CONFIRMED] |

Both private — reflective reads need `BindingFlags.NonPublic |
BindingFlags.Instance`.

### Methods

#### Angle(float angleRadians) -> Matrix2x2

- **Access:** **public static** · IL @2542
- **Parameters:** `angleRadians` — **radians**, not degrees
- **Returns:** a new rotation matrix
- **Behavior:** the only constructor in practice; the `.ctor` is
  parameterless.
- **Gotchas:** the drag pipeline builds **two** of these per tick,
  negations of each other — `Angle(-a)` for `GetDragSurfaces` and
  `Angle(+a)` for `localToWorld`. Swapping them mirrors the result. See
  [`../02-drag-aero/AeroModule.md`](../02-drag-aero/AeroModule.md).
- **Status:** [CONFIRMED] signature · [PARTIAL] body

#### op_Multiply — four overloads

| Signature | IL |
|---|---|
| `static Vector2 op_Multiply(Matrix2x2 matrix, Vector2 b)` | @2573 |
| `static Vector2 op_Multiply(Vector2 b, Matrix2x2 matrix)` | @2610 |
| `static Vector2 op_Multiply(Matrix2x2 matrix, Vector3 b)` | @2647 |
| `static Vector2 op_Multiply(Vector3 b, Matrix2x2 matrix)` | @2684 |

- **Access:** all public static
- **Returns:** always `Vector2`, including for the `Vector3` forms
- **Gotchas:** **argument order is not commutative here.**
  `Aero_Rocket.GetDragSurfaces` uses the `(Vector2, Matrix2x2)` order,
  while `AeroModule.ApplyForce` uses `(Matrix2x2, Vector2)`. They are
  **not** the same operation. Four overloads on one name means naive
  `GetMethod("op_Multiply", flags)` throws `AmbiguousMatchException` —
  always pass explicit parameter types. Catalogued in
  [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
- **Status:** [CONFIRMED] signatures · [OPEN] bodies

#### GetX(Vector2 b) -> float

- **Access:** public instance · IL @2721
- **Status:** [CONFIRMED] signature · [OPEN] body

#### .ctor() -> void

- **Access:** public instance, parameterless · IL @2744
- **Gotchas:** produces an all-zero matrix. Use `Angle` instead.
- **Status:** [CONFIRMED]

## Status summary

| Item | Status |
|---|---|
| Top-level, no namespace; **class**, not struct | [CONFIRMED] |
| Two private `Vector2` fields | [CONFIRMED] |
| `Angle(float radians)` is the real constructor | [CONFIRMED] |
| Four `op_Multiply` overloads, order-sensitive | [CONFIRMED] |
| All method bodies | [OPEN] |
