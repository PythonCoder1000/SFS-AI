# `SFS.World.Drag.Aero_Rocket` — the rocket's drag geometry source

**Migrated** from `docs/sfs_source_reference.md` §C1.2 (2026-08-28).

Base class and pipeline: [`AeroModule.md`](AeroModule.md).

---

## Aero_Rocket

**Namespace:** SFS.World.Drag
**Kind:** class
**Extends:** SFS.World.Drag.AeroModule
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @220145 · 9 methods / 1 field

The `AeroModule` subclass for rockets. Supplies the five protected
abstract members and, crucially, the geometry source.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `rocket` | `SFS.World.Rocket` | public | no | **the only instance field on this class** | [CONFIRMED] |

> It has no `output` field. See the closure-artifact note in
> [`AeroModule.md`](AeroModule.md).

### Methods

#### GetDragSurfaces(Matrix2x2 rotate) -> List&lt;Surface&gt;

- **Access:** `protected override` instance · IL @220181, **18 bytes**
- **Parameters:** `rotate` — the velocity-aligned matrix,
  `Matrix2x2.Angle(-a)`, **not** identity
- **Returns:** the rocket's drag surfaces in velocity-aligned world space
- **Behavior:** a **pure forwarder**. The entire body is
  `return GetDragSurfaces(this.rocket.partHolder, rotate);`
- **Gotchas:** one of two same-named overloads — the confirmed
  `AmbiguousMatchException` case. Needs
  `NonPublic | Instance` **and** explicit parameter types.
- **Status:** [CONFIRMED]

#### GetDragSurfaces(PartHolder partsHolder, Matrix2x2 rotate) -> List&lt;Surface&gt;

- **Access:** **public static** · IL @220196, 355 bytes
- **Parameters:** `partsHolder` — **any** `PartHolder`, not necessarily
  one attached to a flying rocket; `rotate` — the velocity-aligned matrix
- **Returns:** a **freshly allocated** `List<Surface>` per call
- **Behavior:**
  ```csharp
  var output = new List<Surface>();                     // fresh list every call
  foreach (SurfaceData sd in partsHolder.GetModules<SurfaceData>())
  {
      if (!sd.Drag) continue;                           // per-part opt-out
      Vector3 scale = sd.transform.lossyScale;
      bool flip = (scale.x > 0f) != (scale.y > 0f);     // mirrored part
      HeatModuleBase heatModule = sd.heatModule;
      foreach (Surfaces s in sd.surfacesFast)
      {
          var pts = new Vector2[s.points.Length];
          for (int i = 0; i < s.points.Length; i++)
              pts[i] = (Vector2)s.owner.TransformPoint((Vector3)s.points[i]) * rotate;
          // ... AddLine over consecutive points (local fn <GetDragSurfaces>g__AddLine|5_0) ...
      }
  }
  return output;
  ```
- **Side effects:** none beyond allocation.
- **Gotchas:**
  - **The returned list is freshly allocated per call.** Safe to hold and
    inspect; it is not a reused buffer.
  - **Output is in velocity-aligned world space**, not part-local space.
    Points go through `Transform.TransformPoint` (local → world) and are
    then multiplied by `rotate`. Do not expect part-local outlines back.
  - **`SurfaceData.Drag` gates participation per part.** Backed by the
    private `dragSurfaces` field via `get_Drag()` @268796. A part with it
    false contributes nothing.
  - **`flip` is derived from `lossyScale` sign mismatch** — mirrored
    parts need their winding reversed.
  - **Reflection gotcha: `PartHolder.GetModules<T>()` is generic**
    (@238644, `instance !!T[] GetModules<T>()`). Reaching it needs
    `MakeGenericMethod(surfaceDataType)`, not a plain `GetMethod`. This
    only matters if reimplementing the walk — calling `GetDragSurfaces`
    itself avoids the problem entirely.
- **Why this matters more than it looks:** because the instance overload
  only supplies `rocket.partHolder`, the static overload works on **any**
  `PartHolder` — including one not attached to a flying rocket. The game
  itself relies on this: `BurnManager` (top-level, no namespace) calls
  the static overload directly at @26301. **So drag area is computable
  for a design before it flies**, which is directly relevant to the
  design-agent side of this project.
- **Status:** [CONFIRMED] from IL · **[UNTESTED-LIVE]** for a non-flying
  `PartHolder`

#### GetLocation() -> Location

- **Access:** `protected override` instance · IL @220167
- **Returns:** `SFS.World.Location`
- **Behavior:** reads through `rocket.location`, which is declared on
  `SFS.World.Player` as a `WorldLocation` whose `get_Value()` returns
  `Location`. This body is what confirms the wrapper depth used by the
  probe's `Unwrap(Get(r, "location"))`.
- **Status:** [CONFIRMED]

#### ApplyParachuteDrag(ref float force, ref Vector2 centerOfDrag_World) -> void

- **Access:** instance · IL @220367
- **Parameters:** both **by reference** — the method mutates the caller's
  force magnitude *and* application point
- **Behavior:** **[OPEN]** — body not yet read.
- **Gotchas:** called from `AeroModule.ApplyForce` **after** the
  `Lerp(CoM, CoP, 0.2)` damping, so parachute drag bypasses that damping
  entirely. From `docs/sfs_source_reference.md` §E6.1: it is a separate
  rotation-aware path using per-chute `rb2d.GetPointVelocity` and an
  `AnimationCurve`.
- **Status:** [OPEN] — needed before any parachute-carrying descent can
  be predicted. See
  [`../14-misc-part-modules/ParachuteModule.md`](../14-misc-part-modules/ParachuteModule.md).

#### The remaining overrides

`PhysicsMode { get; }`, `AddForceAtPosition(Vector2, Vector2)` and
`GetMass()` are supplied here as `protected override`.
**[PARTIAL]** — signatures confirmed via the abstract declarations on
`AeroModule`; bodies not read.

## Status summary

| Item | Status |
|---|---|
| Exactly one field, `public Rocket rocket` | [CONFIRMED] |
| Instance `GetDragSurfaces` is an 18-byte pure forwarder | [CONFIRMED] |
| Static `GetDragSurfaces(PartHolder, Matrix2x2)` body | [CONFIRMED] |
| Output is velocity-aligned **world** space, freshly allocated | [CONFIRMED] |
| `SurfaceData.Drag` per-part opt-out, `flip` from `lossyScale` | [CONFIRMED] |
| Static overload usable on a non-flying `PartHolder` | [CONFIRMED] in IL · [UNTESTED-LIVE] |
| `GetLocation()` body | [CONFIRMED] |
| `ApplyParachuteDrag` body | [OPEN] |
| `PhysicsMode` / `AddForceAtPosition` / `GetMass` bodies | [PARTIAL] |
