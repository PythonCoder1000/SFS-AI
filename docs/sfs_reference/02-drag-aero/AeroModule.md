# `SFS.World.Drag.AeroModule` — the drag and heating pipeline

**Migrated** from `docs/sfs_source_reference.md` §C1.0–C1.9 (2026-08-28).

The highest-priority system in this project: it produces `dragArea` and
centre of pressure, which gate aerodynamic torque magnitude and
atmospheric ascent prediction. **Every method body in the drag path has
been read.** Subclass: [`Aero_Rocket.md`](Aero_Rocket.md). Geometry
inputs: [`geometry-types.md`](geometry-types.md).

---

## AeroModule

**Namespace:** SFS.World.Drag
**Kind:** abstract class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @215749 · 25 methods / 9 fields

### CORRECTION — this is an abstract base, not a per-part module

An earlier `sfs_source_reference.md` described `AeroModule` and
`Aero_Rocket` as two levels of the same idea:

> `SFS.World.Drag.Aero_Rocket` — drag/aero, rocket level
> `SFS.World.Drag.AeroModule` — drag/aero, per-part-module level
> `instance List<Surface> GetDragSurfaces(Matrix2x2 rotate)` — per-module version (single part)

**That is wrong.** `AeroModule` is an **abstract base class**, not a
per-part module. `AeroModule.GetDragSurfaces(Matrix2x2)` is
`family virtual newslot abstract` — i.e. `protected abstract` — with no
body at all. `Aero_Rocket` is a **subclass** that overrides it. There is
no per-part drag module; **drag is computed for a whole `PartHolder` at
once.**

```
abstract AeroModule                       @215749
  ├── Aero_Rocket    : AeroModule         @220145   (rockets)
  ├── Aero_Astronaut : AeroModule         @219863   (EVA astronauts)
  └── Water_Rocket                        @218623   (separate hierarchy, not a subclass)
```

### Fields

Nine instance fields; all non-physics except `heatManager`.

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `heatManager` | `HeatManager` | public | no | the heat accumulator — see [`../03-heat-destruction/HeatManager.md`](../03-heat-destruction/HeatManager.md) | [CONFIRMED] |
| `burnManager` | `BurnManager` | public | no | burn-mark visuals | [CONFIRMED] |
| `shockEdge` | `AeroMesh` | public | no | shockwave visual | [CONFIRMED] |
| `shockOuter` | `AeroMesh` | public | no | shockwave visual | [CONFIRMED] |
| `reentryEdge` | `AeroMesh` | public | no | reentry visual | [CONFIRMED] |
| `reentryOuter` | `AeroMesh` | public | no | reentry visual | [CONFIRMED] |
| `airflowSound` | `AudioModule` | public | no | airflow audio | [CONFIRMED] |
| `burnSound` | `AudioModule` | public | no | burn audio | [CONFIRMED] |
| `frameIndex` | `int` | private | no | incremented per `FixedUpdate`; passed to `heatManager.DissipateHeat` | [CONFIRMED] |

> **Neither `AeroModule` nor `Aero_Rocket` has an `output` field.** An
> earlier pass of the old document listed one on both. It is a
> compiler-generated closure field on a nested `<>c__DisplayClass` — see
> [`../METHODOLOGY.md`](../METHODOLOGY.md). Corrected before publication;
> noted here because the same artifact recurs on any class with closures.

### The five abstract members

All `protected`, so reflection **must** include `BindingFlags.NonPublic`.

| Member | IL | Status |
|---|---|---|
| `protected abstract bool PhysicsMode { get; }` | @217512 | [CONFIRMED] |
| `protected abstract Location GetLocation()` | @217519 | [CONFIRMED] |
| `protected abstract List<Surface> GetDragSurfaces(Matrix2x2)` | @217526 | [CONFIRMED] |
| `protected abstract void AddForceAtPosition(Vector2 force, Vector2 position)` | @217533 | [CONFIRMED] |
| `protected abstract float GetMass()` | @217540 | [CONFIRMED] |

### Methods

#### FixedUpdate() -> void

- **Access:** private instance (Unity message) · IL @215769–215950
- **Behavior:** the whole per-tick pipeline.
  ```csharp
  frameIndex++;
  Location location = GetLocation();
  if (IsInsideAtmosphereAndIsMoving(location)) {
      GetTemperatureAndShockwave(location, out float Q, out float shockOpacity, out float temperature);

      bool applyDrag = PhysicsMode && !SandboxSettings.main.settings.noAtmosphericDrag;
      bool applyHeat = temperature > 0f;

      if (applyDrag || applyHeat) {
          float a = (float)location.velocity.AngleRadians - 1.5707964f;   // - PI/2
          Matrix2x2 toVelocity   = Matrix2x2.Angle(-a);                   // -> GetDragSurfaces
          Matrix2x2 localToWorld = Matrix2x2.Angle(a);                    // -> ApplyForce / heating

          List<Surface> exposed = GetExposedSurfaces(GetDragSurfaces(toVelocity));

          if (applyDrag) ApplyForce(exposed, location, localToWorld, out float g_ForSound);
          if (applyHeat) FixedUpdate_Reentry_And_Heating(temperature, exposed, a, localToWorld, out drewReentryMesh);
      }
      // ... airflow/burn audio ...
  } else {
      airflowSound.volume.Value = 0f;  burnSound.volume.Value = 0f;
  }
  heatManager.DissipateHeat(frameIndex);
  ```
- **Side effects:** applies force to the rigidbody, accumulates heat,
  drives audio and meshes.
- **Gotchas:** four, all load-bearing.
  1. **`IsInsideAtmosphereAndIsMoving(location)` is a hard gate.**
     Outside it, drag *and* heating are both entirely skipped. Call it
     before trusting any drag number.
  2. **`SandboxSettings.main.settings.noAtmosphericDrag` disables drag
     while leaving heating active.** A sandbox world with this set
     produces zero drag with no other symptom — check it before
     concluding a measurement is wrong.
  3. **There are two rotation matrices, negations of each other.**
     `Matrix2x2.Angle(-a)` goes into `GetDragSurfaces`;
     `Matrix2x2.Angle(a)` is the `localToWorld` that maps the resulting
     centre of drag back to world space. Using one where the other
     belongs **mirrors the result**.
  4. **`GetExposedSurfaces` output is shared** between the drag and
     heating paths — computed once per `FixedUpdate`.
- **Precision note on `a`:** the game computes
  `(float)location.velocity.AngleRadians - 1.5707964f` — the cast to
  `float32` happens **before** the subtraction (`conv.r4` at IL_0071,
  `ldc.r4` at IL_0072). The probe computes
  `(float)(-(velocityAngle - Math.PI / 2.0))` in `double` and casts at
  the end. These differ in the last ulp. Irrelevant for a magnitude
  check; relevant if ever bit-matching the game's own output.
- **Status:** [CONFIRMED]

#### CalculateDragForce(List&lt;Surface&gt; surfaces) -> (float drag, Vector2 centerOfDrag)

**This method IS `dragArea`.**

- **Access:** **private static** · IL @216054–216155, full body read
- **Parameters:** `surfaces` — the *exposed* surfaces, in
  velocity-aligned world space
- **Returns:** a `ValueTuple<float, Vector2>`. **Tuple element names are
  not inferred** — the method carries a `TupleElementNamesAttribute`
  whose blob decodes to `drag` and `centerOfDrag`, so `Item1` is drag
  area and `Item2` is centre of drag. Read directly from the attribute;
  see [`../METHODOLOGY.md`](../METHODOLOGY.md).
- **Behavior:**
  ```csharp
  float drag = 0f;
  Vector2 centerOfDrag = Vector2.zero;
  for (int i = 0; i < surfaces.Count; i++)
  {
      Surface s = surfaces[i];
      Vector2 d = s.line.end - s.line.start;
      if (d.x < 0.01f) continue;                            // cull
      float weight = d.x / (d.x + Mathf.Abs(d.y));
      float w      = d.x * weight;                          // == dx^2 / (dx + |dy|)
      drag         += w;
      centerOfDrag += (s.line.start + s.line.end) * w;
  }
  if (drag > 0f)
      centerOfDrag /= drag * 2f;
  return (drag, centerOfDrag);
  ```
- **Side effects:** none — pure.
- **Gotchas:** **the `d.x < 0.01f` cull threshold.** Segments whose
  x-extent in velocity-aligned space is below 0.01 are skipped entirely.
  Because the comparison is `<` on a *signed* value, this culls **both**
  leeward-facing segments (negative `dx`) **and** near-edge-on ones — it
  is the windward-face selection *and* a small-segment filter in one
  test. Any reimplementation must reproduce the 0.01 threshold, not just
  the sign test; the two differ for finely-tessellated outlines. A
  nonzero surface count can therefore still yield `drag == 0`.
- **Cross-check:** exact agreement with
  `sfs_physics_reference.md` §2.3 — `drag = Σ dx²/(dx+|dy|)`, and
  `centerOfDrag = Σ((start+end)·w) / (2·drag) = Σ(midpoint·w) / drag`.
- **Status:** [CONFIRMED]

#### ApplyForce(List&lt;Surface&gt; exposedSurfaces, Location location, Matrix2x2 localToWorld, out float g_ForSound) -> void

- **Access:** private instance · IL @215950–216054, full body read
- **Behavior:**
  ```csharp
  (float drag, Vector2 centerOfDrag) = CalculateDragForce(exposedSurfaces);

  float density = (float)location.planet.GetAtmosphericDensity(location.Height);
  float f       = drag * 1.5f * (float)location.velocity.sqrMagnitude;
  Vector2 cop   = localToWorld * centerOfDrag;

  g_ForSound = f * density / GetMass() / 9.8f;

  if (this is Aero_Rocket ar)
  {
      cop = Vector2.Lerp(ar.rocket.rb2d.worldCenterOfMass, cop, 0.2f);
      ar.ApplyParachuteDrag(ref f, ref cop);          // mutates BOTH
  }

  Vector2 force = -location.velocity.ToVector2.normalized * (f * density);

  if (!float.IsNaN(force.x + force.y + cop.x + cop.y))
      AddForceAtPosition(force, cop);
  ```
- **Side effects:** `AddForceAtPosition` on the subclass — i.e. the
  actual rigidbody force.
- **Gotchas:** four details not previously documented.
  1. **`ApplyParachuteDrag` runs *after* the 0.2 lerp** and mutates both
     the force magnitude and the application point by reference.
     Parachute drag is therefore **not** subject to the CoP damping that
     surface drag is. A parachute-carrying rocket does not follow the
     §2.3 model alone.
  2. **The 0.2 lerp is `Aero_Rocket`-only.** `Aero_Astronaut` applies
     drag at the raw CoP with no damping.
  3. **`g_ForSound` is `f·ρ/mass/9.8`** — a g-force figure computed
     *only* to drive audio. Not used in physics, but a free and correct
     g-load readout if ever wanted.
  4. **A NaN guard suppresses the force entirely** if any component is
     NaN. A rocket silently experiencing zero drag may be hitting this
     rather than a zero drag area.
- **Cross-check:** confirms `sfs_physics_reference.md` §2.3 precisely —
  the `1.5` constant, `|v|²` via `sqrMagnitude`, and the
  `Lerp(CoM, CoP, 0.2)` application point.
- **Status:** [CONFIRMED]

#### GetExposedSurfaces(List&lt;Surface&gt; surfacesList) -> List&lt;Surface&gt;

- **Access:** **public static** · IL @216431, 1,523 bytes. Control flow
  traced and constants confirmed; not every branch transcribed.
- **Returns:** the visible (windward) lower envelope. **Empty input
  returns a new empty list, not null.**
- **Behavior:**
  - Input first passes through `AeroModule.Sort(List<Surface>)` (public
    static @216974), which delegates to a **`RadixSort`** over `uint`
    keys (@217040) — a bucket sort on the x-coordinate, not a comparison
    sort.
  - Then a **sweep along the x axis**, maintaining an ordered list of
    exposed "sections", edited by four compiler-emitted local functions:
    `<GetExposedSurfaces>g__InsertSection|16_0` @217659,
    `g__RemoveSection|16_1` @217587,
    `g__SetSectionStart|16_2` @217603,
    `g__SetSectionEnd|16_3` @217631.
  - Overlaps are resolved by comparing `y` at shared `x`, splitting
    segments with `Line2.GetPositionAtX_Unclamped`, keeping the windward
    one.
  - **Epsilon is `0.001f` throughout** — for both x-ordering comparisons
    and for treating a `y` difference as zero before taking `Mathf.Sign`.
- **Gotchas:** this is the "lower envelope / visible surface" problem the
  Python solver in `python_changelog.md` was built to solve. The game's
  own implementation is public and callable, so the solver is not needed
  to obtain the value — though it remains useful as an independent
  cross-check.
- **Status:** [PARTIAL] · **[OPEN]** — exact tie-breaking when two
  segments share both `x` and `y`, and the handling of surfaces belonging
  to different `owner` parts at the same `x`, were not fully traced.

#### FixedUpdate_Reentry_And_Heating(float temperature, List&lt;Surface&gt; exposedSurfaces, float velocityAngleRad, Matrix2x2 localToWorld, out bool drewReentryMesh) -> void

**[CONFIRMED 2026-08-30]** — full body read, resolving the exact question
of what `HeatManager.ApplyHeat` actually receives.

- **Access:** private instance · IL @216155, full body read (332 bytes)
- **Behavior:**
  ```csharp
  if (temperature <= 0f) return;

  // burn-mark visuals (Aero_Rocket only, gated on !noBurnMarks) -- skipped

  exposedSurfaces = AeroModule.RemoveHighSlopeSurfaces(exposedSurfaces, 5f);
  AeroModule.ApplyProtectionZone(exposedSurfaces);

  heatManager.ApplyHeat(exposedSurfaces, temperature, frameIndex);

  // reentry glow mesh visuals (reentryEdge/reentryOuter) -- skipped
  ```
- **The critical finding:** `temperature` is passed to `ApplyHeat`
  **completely unmodified** (`ldarg.1`, straight through, IL_0052) — no
  scaling, no offset. The raw `AeroFormula.GetTemperature()` output IS
  what the accumulator sees. **But `exposedSurfaces` is NOT the raw
  drag-path list** — it is filtered through two heating-only functions
  first, and this filtering is what a heat-accumulation reimplementation
  must reproduce (see below). Confirms and closes the `[OPEN]` status
  this method previously had.
- **Everything else in this method is visual** (burn marks, reentry glow
  meshes) and irrelevant to the physics.
- **Status:** [CONFIRMED]

#### RemoveHighSlopeSurfaces(List&lt;Surface&gt; surfaces, float maxSlope) -> List&lt;Surface&gt;

**[CONFIRMED 2026-08-30]** — full body read, including the closure
predicate.

- **Access:** private static · IL @217196
- **Behavior:** `surfaces.Where(predicate).ToList()`, predicate:
  ```csharp
  float slope = Mathf.Abs(surface.line.SizeY() / surface.line.SizeX());
  if (slope >= maxSlope) return false;
  return surface.line.SizeX() > 0.1f;
  ```
- **Called with `maxSlope = 5f`** from `FixedUpdate_Reentry_And_Heating`.
  Keeps only segments with `|dy/dx| < 5.0` **and** `dx > 0.1` — **10x
  stricter than the drag path's `dx > 0.01` cull** in
  `CalculateDragForce`
  ([`AeroModule.md`](AeroModule.md) above), and it additionally excludes
  steep (near-vertical) segments that the drag path keeps. A segment
  drag counts as exposed can therefore be entirely absent from the heat
  tally.
- **Status:** [CONFIRMED]

#### ApplyProtectionZone(List&lt;Surface&gt; surfaces) -> void

**[CONFIRMED 2026-08-30]** — full body read (473 bytes). A real
geometric shadow-occlusion pass, mutating `surfaces` in place.

- **Access:** private static · IL @217219
- **Behavior, per adjacent pair in the (already x-sorted) list:**
  ```
  for i in 1 .. count-1:
      gapBack = surfaces[i].start.y - surfaces[i-1].end.y
      if gapBack > 0.1f:
          thresholdX = surfaces[i].start.x - min(gapBack * 0.2f, 0.4f)
          # walk BACKWARD from j = i-1:
          #   if surfaces[j].start.x > thresholdX: remove it entirely (fully shadowed)
          #   else: clip surfaces[j].end to x = thresholdX, then stop

      gapFwd = surfaces[i].end.y - surfaces[i+1].start.y
      if gapFwd > 0.1f:
          thresholdX = surfaces[i].end.x + min(gapFwd * 0.2f, 0.4f)
          # walk FORWARD from j = i+1, same remove-or-clip-and-stop logic

  # final cleanup pass: remove any remaining segment with SizeX() < 0.1f
  ```
- **Physical meaning:** wherever the outline has a vertical step
  (`>0.1` unit y-discontinuity between adjacent segments), nearby
  surface is shielded from airflow within a protection zone up to `0.4`
  units wide (scaling with step size below that cap) — a protruding
  part shadows recessed geometry behind it. Segments fully inside the
  zone are removed; segments straddling the boundary are clipped, not
  removed outright.
- **Status:** [CONFIRMED]

**Practical consequence for any Python/probe reimplementation:** do not
reimplement this geometry independently — both functions are `private
static` and directly reachable via reflection
(`BindingFlags.NonPublic | BindingFlags.Static`), so calling the game's
own real implementation is both simpler and safer than re-deriving the
shadow-occlusion math. `sfsprobe`'s `heatParts` telemetry field does
exactly this as of v0.41.0.

#### Neighbouring methods

**[PARTIAL]** — signatures confirmed; bodies not read except where noted.

| Signature | IL | Notes |
|---|---|---|
| `public static void GetTemperatureAndShockwave(Location, out float Q, out float shockOpacity, out float temperature)` | @216283 | `public static`, takes only a `Location` — a directly callable entry point for the heat model |
| `public static float GetIntensity(float value, float halfPoint)` | @216381 | |
| `public static float GetHeatTolerance(HeatTolerance a)` | @216396 | |
| `public static Surface[] Sort(List<Surface> list)` | @216974 | delegates to `RadixSort` @217040 |
| `public static Line2[] RotateSurfaces(List<Surface>, Matrix2x2)` | @217439 | maps velocity-aligned back to world |
| `public static bool IsInsideAtmosphereAndIsMoving(Location)` | @217489 | the hard gate |
| `private static List<Surface> RemoveHighSlopeSurfaces(List<Surface>, float maxSlope)` | @217195 | **heating only** |
| `private static void ApplyProtectionZone(List<Surface> surfaces)` | @217218 | **heating only** |
| `private void FixedUpdate_Reentry_And_Heating(float temperature, List<Surface>, float velocityAngleRad, Matrix2x2, out bool)` | @216155 | |

**Call-site finding [CONFIRMED]:** `RemoveHighSlopeSurfaces` and
`ApplyProtectionZone` each have exactly **one** caller, at @216191 and
@216194 — both inside `FixedUpdate_Reentry_And_Heating`. They are part of
the **heating** path only and play no role in drag. A reimplementation of
drag must not apply them; a reimplementation of heating must.

---

## Reflection recipe — computing `dragArea` live

**[UNTESTED-LIVE]** — applied to `SFSProbe.cs` as the `dragarea` command
in **v0.27.0** (2026-08-28), built, but not yet run against the running
game. The code below matches what shipped.

Two details of the shipped version verified against the IL:

- It reads the velocity as `GetWrapped(dloc, "velocity")` rather than
  plain `Get`. **This is safe.** `Double2` (@180) is a struct with only
  public `x`/`y` fields and computed properties — no `Value` property and
  no `value` field — so `GetWrapped2` finds neither and returns the
  `Double2` unchanged. `AngleRadians` (@341) then resolves as a property
  via `Get`.
- `Unwrap(Get(r, "location"))` is the correct peel. `Rocket.location` is
  declared on the base class `SFS.World.Player` as a **`WorldLocation`**,
  whose `get_Value()` returns `SFS.World.Location` (confirmed in
  `Aero_Rocket.GetLocation()`'s body @220167). `Unwrap` peels the wrapper
  and stops on its `t.Name == "Location"` guard — exactly one layer,
  landing on the right type.

Binding flags that are **not optional**:

| Target | Required flags | Why |
|---|---|---|
| `Aero_Rocket.GetDragSurfaces(Matrix2x2)` | `NonPublic \| Instance` | `protected override` |
| `AeroModule.GetExposedSurfaces` | `Public \| Static` | |
| `AeroModule.CalculateDragForce` | `NonPublic \| Static` | `private static` |
| `Aero_Rocket.GetDragSurfaces(PartHolder, Matrix2x2)` | `Public \| Static` | |

All four resolutions **must** use the explicit-parameter-types form.
`rocket.aero` is an `Aero_Rocket`; `Matrix2x2` resolves as a bare
`"Matrix2x2"`.

```csharp
case "dragarea":
{
    object r = ActiveRocket();
    if (r == null) { ProbeMod.Result("dragarea: no active rocket"); break; }
    object aero = Get(r, "aero");
    if (aero == null) { ProbeMod.Result("dragarea: rocket.aero is null"); break; }

    Type matrixType     = FindType("Matrix2x2");
    Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
    if (matrixType == null || aeroModuleType == null)
    { ProbeMod.Result("dragarea: FAILED to resolve Matrix2x2 or AeroModule"); break; }

    // Rotation input, confirmed from AeroModule.FixedUpdate()'s own IL.
    // NOT identity. Game computes this in float32; see the precision note above.
    object location = Unwrap(Get(r, "location"));
    object velocity = Get(location, "velocity");
    double velocityAngle = ToD(Get(velocity, "AngleRadians"));
    float rotationInput  = (float)(-(velocityAngle - Math.PI / 2.0));
    object matrix = InvokeStatic(matrixType, "Angle",
        new Type[] { typeof(float) }, new object[] { rotationInput });
    if (matrix == null) { ProbeMod.Result("dragarea: Matrix2x2.Angle FAILED"); break; }

    // protected override -> NonPublic|Instance, explicit param types (2 overloads)
    MethodInfo getDragSurfaces = aero.GetType().GetMethod("GetDragSurfaces",
        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
        null, new Type[] { matrixType }, null);
    if (getDragSurfaces == null)
    { ProbeMod.Result("dragarea: couldn't resolve 1-arg GetDragSurfaces"); break; }

    object allSurfaces;
    try { allSurfaces = getDragSurfaces.Invoke(aero, new object[] { matrix }); }
    catch (Exception e)
    {
        ProbeMod.Result("dragarea: GetDragSurfaces threw: " +
            (e.InnerException != null ? e.InnerException.Message : e.Message));
        break;
    }

    object exposed = allSurfaces == null ? null :
        InvokeStatic(aeroModuleType, "GetExposedSurfaces",
            new Type[] { allSurfaces.GetType() }, new object[] { allSurfaces });

    // private static -> NonPublic|Static
    MethodInfo calcDrag = aeroModuleType.GetMethod("CalculateDragForce",
        BindingFlags.NonPublic | BindingFlags.Static,
        null, new Type[] { exposed.GetType() }, null);
    var tuple = (System.ValueTuple<float, Vector2>)calcDrag.Invoke(null, new object[] { exposed });
    // tuple.Item1 = dragArea, tuple.Item2 = centerOfDrag (velocity-aligned space)
    break;
}
```

**Gotchas confirmed from the IL:**

- `GetDragSurfaces` returns a **fresh** `List<Surface>` — safe to retain.
- `Surface.line.start/end` are in **velocity-aligned world space**. To
  get world coordinates, multiply by `Matrix2x2.Angle(+a)` (the
  non-negated matrix), or use `AeroModule.RotateSurfaces`.
- `Surface.valid` is a `Valid` **object**; the bool is one level deeper.
- `CalculateDragForce` culls `dx < 0.01f`, so a nonzero surface count can
  still yield `drag == 0`.
- If the rocket is outside the atmosphere or stationary, the game skips
  this whole path — but these methods will still happily compute a
  number. Gate on `IsInsideAtmosphereAndIsMoving` to match the game.
- Sandbox `noAtmosphericDrag` does **not** affect these methods; it only
  gates whether `ApplyForce` runs.

## Status summary

| Item | Status |
|---|---|
| `AeroModule` is abstract; `GetDragSurfaces` is protected abstract | [CONFIRMED] — corrects earlier doc |
| Rotation input `-(velocityAngle - π/2)`, and its `+` twin | [CONFIRMED] from `FixedUpdate` body |
| `CalculateDragForce` returns `(drag, centerOfDrag)` | [CONFIRMED] from attribute blob |
| `dragArea = Σ dx²/(dx+\|dy\|)`, CoP formula | [CONFIRMED] — exact match to §2.3 |
| `dx < 0.01f` cull threshold | [CONFIRMED] — newly documented |
| Force law `1.5·drag·\|v\|²·ρ`, applied at `Lerp(CoM,CoP,0.2)` | [CONFIRMED] from `ApplyForce` body |
| Parachute drag bypasses the 0.2 damping | [CONFIRMED] — newly documented |
| `GetExposedSurfaces` sweep structure, eps `0.001f` | [PARTIAL] |
| `GetExposedSurfaces` tie-breaking | [OPEN] |
| `FixedUpdate_Reentry_And_Heating` full body | [CONFIRMED] — `temperature` passed to `ApplyHeat` unmodified; `exposedSurfaces` filtered first |
| `RemoveHighSlopeSurfaces` full body | [CONFIRMED] — `\|dy/dx\|<5.0` and `dx>0.1`, stricter than drag's `dx>0.01` |
| `ApplyProtectionZone` full body | [CONFIRMED] — geometric shadow-occlusion, `>0.1` y-step triggers a `≤0.4`-wide protection zone |
| Neighbouring method bodies (`GetTemperatureAndShockwave`, `Sort`, `RotateSurfaces`, `GetIntensity`, `GetHeatTolerance`) | [OPEN] |
| The probe `dragarea` command | [UNTESTED-LIVE] — applied in v0.27.0, built, not yet run live |
| `Aero_Astronaut`, `Water_Rocket` | [OPEN] — Step 2 |
