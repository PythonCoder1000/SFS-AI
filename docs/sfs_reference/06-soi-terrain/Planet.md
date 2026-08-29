# `SFS.WorldBase.Planet` — bodies, gravity, atmosphere, SOI, terrain

**Migrated** from `docs/sfs_source_reference.md` §D4 (2026-08-28).

Difficulty scaling: [`Difficulty.md`](Difficulty.md). The rails side of
SOI transitions:
[`../01-core-flight/Physics.md`](../01-core-flight/Physics.md) and
[`../01-core-flight/Trajectory.md`](../01-core-flight/Trajectory.md).

---

## Planet

**Namespace:** SFS.WorldBase
**Kind:** class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @146888 · 52 methods / 24 fields

### Fields

Physics-relevant public fields:

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `codeName` | `string` | public | no | the identity used in save files | [CONFIRMED] |
| `mass` | `double` | public | no | **this is μ, the gravitational parameter — NOT kilograms.** No `G` appears anywhere in the codebase | [CONFIRMED] |
| `SOI` | `double` | public | no | sphere of influence radius, metres — a plain public field | [CONFIRMED] |
| `maxTerrainHeight` | `double` | public | no | **a fast-reject bound only**, not the terrain shape | [CONFIRMED] |
| `parentBody` | `Planet` | public | no | | [CONFIRMED] |
| `satellites` | `Planet[]` | public | no | **direct children only** — the SOI scan is one level deep | [CONFIRMED] |
| `orbit` | `Orbit` | public | no | | [CONFIRMED] |
| `trajectory` | `Trajectory` | public | no | | [CONFIRMED] |
| `data` | `PlanetData` | public | no | the serialized record; **difficulty-scaled in place at load** | [CONFIRMED] |
| `orbitalDepth` | `int` | public | no | | [CONFIRMED] |
| `satelliteIndex` | `int` | public | no | | [CONFIRMED] |
| `commonDenominator` | `int` | public | no | | [CONFIRMED] |
| `surfaceWavesRepeat` | `int` | public | no | | [CONFIRMED] |
| `landmarks` | `Landmark[]` | public | no | | [CONFIRMED] |

### Computed properties

| Property | IL | Notes | Status |
|---|---|---|---|
| `double Radius` | @146919 | `data.basics.radius` | [CONFIRMED] |
| `double SurfaceArea` | @146933 | `Radius * 2π` — **a circumference**; this is a 2D game | [CONFIRMED] |
| `double AtmosphereHeightPhysics` | @146947 | `HasAtmospherePhysics ? data.atmospherePhysics.height : +∞` | [CONFIRMED] |
| `double TimewarpRadius_Ascend` | @146967 | see below | [CONFIRMED] |
| `double TimewarpRadius_Descend` | @146997 | see below | [CONFIRMED] |
| `double OrbitRadius`, `double RewardMultiplier` | | | [PARTIAL] |
| `bool HasParent`, `HasAtmospherePhysics`, `HasAtmosphereVisuals`, `HasFrontClouds`, `HasRings` | | | [PARTIAL] |

> **Gotcha [CONFIRMED]:** `AtmosphereHeightPhysics` returns **positive
> infinity** for an airless body (`ldc.r8 (00 00 00 00 00 00 f0 7f)`),
> not 0. Any comparison of the form
> `height < planet.AtmosphereHeightPhysics` is therefore **true
> everywhere** on the Moon. `GetAtmosphericDensity` guards separately and
> is safe; ad-hoc checks are not.

### Methods

#### GetGravity(double radius) -> double

#### GetGravity(Double2 position) -> Double2

- **Access:** public instance · IL @148021 / @148037, bodies read
- **Behavior:**
  ```csharp
  public double  GetGravity(double radius)    => mass / (radius * radius);
  public Double2 GetGravity(Double2 position) => -position.normalized * (mass / position.sqrMagnitude);
  ```
- **Gotchas:** **an ambiguous overload pair** — resolve with explicit
  parameter types. Confirms `sfs_physics_reference.md` §2.1 exactly, and
  confirms `Planet.mass` **is** μ rather than a true mass.
- **Status:** [CONFIRMED]

#### GetAtmosphericDensity(double height) -> double

- **Access:** public instance · IL @148579, body read
- **Parameters:** `height` — altitude **above the surface**, not radius
- **Returns:** density, or exactly `0.0` outside the atmosphere
- **Behavior:**
  ```csharp
  if (!data.hasAtmospherePhysics)       return 0.0;
  if (height > AtmosphereHeightPhysics) return 0.0;
  double c = data.atmospherePhysics.curve;
  return (Math.Exp(height / AtmosphereHeightPhysics * -c) - Math.Exp(-c))
         * data.atmospherePhysics.density;
  ```
- **Gotchas:** exactly `sfs_physics_reference.md` §2.3's
  `ρ(h) = (e^(−curve·h/H) − e^(−curve)) · ρ0`, **with a hard cutoff**.
  Note it reads `curve`, `density` and `height` **directly** — it does
  *not* consult `curveScale` / `heightDifficultyScale` at call time. See
  the difficulty note below.
- **Status:** [CONFIRMED]

#### IsInsideAtmosphere(Double2 position) -> bool

- **Access:** public instance · IL @148547
- **Status:** [PARTIAL] — signature only

#### IsOutsideSOI(Double2 position) -> bool

#### IsInsideSOI(Double2 positionToParent) -> bool

- **Access:** public instance · IL @148626 / @148640, bodies read
- **Behavior:**
  ```csharp
  public bool IsOutsideSOI(Double2 position)          // position RELATIVE TO THIS PLANET
      => position.Mag_MoreThan(SOI);

  public bool IsInsideSOI(Double2 positionToParent)   // position in the PARENT's frame
      => (positionToParent - orbit.GetLocation(WorldTime.main.worldTime).position)
         .Mag_LessThan(SOI);
  ```
- **Gotchas:** **note the asymmetry.** `IsOutsideSOI` takes a
  planet-relative position; `IsInsideSOI` takes a **parent-relative** one
  and subtracts the satellite's own orbital position at the current world
  time. **Passing the wrong frame silently returns a wrong answer.**
- **Status:** [CONFIRMED]

#### Terrain queries

- **Access:** public instance · IL @148203–@148458
- **Behavior:**
  ```csharp
  public bool IsInsideTerrain(Double2 position, double threshold, bool clampToWater)   @148203
  {
      if (position.Mag_MoreThan(Radius + maxTerrainHeight)) return false;   // fast reject
      double surface = Radius + GetTerrainHeightAtAngle(position.AngleRadians, clampToWater) - threshold;
      return position.Mag_LessThan(surface);
  }

  public double GetTerrainHeightAtAngle(double angleRadians, bool clampToWater)        @148294
      => GetTerrainHeightAtAngles(new[] { angleRadians }, clampToWater)[0];
  ```
- **Gotchas:** **terrain is real per-angle geometry, not a single
  bound.** `maxTerrainHeight` is only a fast-reject radius; the actual
  surface comes from
  `GetTerrainHeightAtAngles(double[] angleRadians, bool clampToWater)`
  @148458, which is **batched by design** — the single-angle form
  allocates a one-element array and calls it. **For any sweep
  (landing-site search, terrain profile), call the array form once
  rather than looping the scalar one.**

  This corrects the impression in `sfs_physics_reference.md` §5 that
  "`maxTerrainHeight` is a single bound per body, not real terrain
  geometry". The *bound* is a single value, but real per-angle terrain
  **is** available and queryable.
- **Also available:**

  | Signature | IL | Status |
  |---|---|---|
  | `Double2 GetTerrainNormal(Double2 globalPosition)` | @148240 | [PARTIAL] |
  | `float[] GetTerrainNormals(double[] angles_Radians)` | @148315 | [PARTIAL] |
  | `Color GetTerrainColor(Double2 position)` | @149756 | [PARTIAL] |
  | `int GetMaxLOD()` | @148158 | [PARTIAL] |
- **Status:** [CONFIRMED] for `IsInsideTerrain` and the batching ·
  **[OPEN]** for `GetTerrainHeightAtAngles`' own body (noise, heightmap
  sampling, `FlatZone` handling)

#### TimewarpRadius_Ascend / _Descend

- **Access:** public instance properties · IL @146967 / @146997
- **Behavior:**
  ```csharp
  double TimewarpRadius_Ascend =>
      Radius + Math_Utility.Round(
          data.basics.timewarpHeight,
          Math.Pow(10, Math.Floor(Math.Log10(data.basics.timewarpHeight / 2))) / 2);
  ```
  i.e. the raw `timewarpHeight` rounded to a "nice" increment scaled to
  its own magnitude. `TimewarpRadius_Descend` starts from
  `Radius + maxTerrainHeight` instead.
- **Relevance:** the open **"safe timewarp ceiling"** decision in
  `high_level_checklist.md` — the game's own ascend/descend thresholds
  are computed properties, **readable live per planet**, rather than
  something to be measured empirically.
  `Difficulty.MaxPhysicsTimewarpIndex` (2 / 2 / 3) bounds the
  physics-warp index separately.
- **Also:** `static double GetTimewarpRadius_AscendDescend(Location)`
  @148665 — [PARTIAL], signature only.
- **Status:** [CONFIRMED]

---

## Difficulty scaling — where it actually happens

**[CONFIRMED]** — `Difficulty.ScalePlanetData(PlanetData)` @146246. The
scale dictionaries are applied **once at load**, mutating the
`PlanetData` in place:

```csharp
basics.radius              *= RadiusScale(planet);
basics.gravity             *= GravityScale(planet);
basics.timewarpHeight      *= AtmosphereScale(planet);
atmospherePhysics.height   *= AtmosphereScale(planet);
atmospherePhysics.curve    *= AtmosphereCurveScale(planet);
orbitModule.semiMajorAxis  *= SmaScale(planet);
// + SOI via SoiScale, rings, clouds, gradients, post-processing …
```

Each `*Scale` method (@146485–@146654) looks the planet's own
per-difficulty dictionary up by
`Base.worldBase.settings.difficulty.difficulty`, falling back to
`DefaultRadiusScale` / `DefaultAtmoHeightScale` / `DefaultAtmoCurveScale`
or `1.0`.

**The practical rules:**

- **Values read live from `Planet`/`PlanetData` at runtime are already
  difficulty-scaled** and are correct as-is. No extra scaling to apply.
- **Values read from the planet JSON on disk are unscaled** and are only
  correct for the default difficulty.
- **Radius, gravity, SOI, and semi-major axis all scale too**, not just
  the atmosphere — so `sfs_physics_reference.md` §1.1's Earth numbers
  (radius 314,970, μ, SOI, atmosphere height 30,000) are a
  **difficulty-specific snapshot**, and that document does not record
  which difficulty they came from.

### Atmosphere_Physics

**[CONFIRMED]** field list — @200297. Own entry is [OPEN] (Step 2).

```
double height, density, curve
Dictionary<DifficultyType,double> curveScale, heightDifficultyScale
double parachuteMultiplier          <- previously undocumented
double upperAtmosphere              <- previously undocumented
float  shockwaveIntensity, minHeatingVelocityMultiplier
```

The last two feed the reentry temperature formula — see
[`../02-drag-aero/AeroFormula.md`](../02-drag-aero/AeroFormula.md).

---

## The SOI transition mechanism

**[CONFIRMED]** — `IsOutsideSOI` and `IsInsideSOI` have **exactly one
caller each**, both in `SFS.World.Physics.Update()` @159627:

```csharp
if (PhysicsObject.PhysicsMode)
{
    location.position.Value = WorldView.ToGlobalPosition(PhysicsObject.LocalPosition);
    location.velocity.Value = WorldView.ToGlobalVelocity(PhysicsObject.LocalVelocity);
    location.planet.Value   = WorldView.main.ViewLocation.planet;

    if (WorldView.main.ViewLocation.planet.IsOutsideSOI(location.position)
        || location.planet.Value.satellites.Any(s => s.IsInsideSOI(location.position)))
    {
        PhysicsMode = false;          // <-- drop off physics, onto rails
        trajectory.EnterNextPath();
        Update();                     // re-enter, now in the rails branch
        return;
    }
}
else
{
    trajectory.CheckEncounters();
    trajectory.CheckPathTransition(WorldTime.main.worldTime);
    location.Value = trajectory.GetLocation(WorldTime.main.worldTime);
    ...
}
```

> ### The finding: crossing an SOI boundary in physics mode forces the craft onto rails
>
> It is **not** a smooth reference-frame handover — the game sets
> `PhysicsMode = false`, calls `Trajectory.EnterNextPath()`, and re-enters
> `Update()` on the rails branch **in the same frame**.
>
> For this project that matters directly: any powered burn, drag force,
> or per-tick integration in progress **stops being simulated** at the
> instant of an SOI crossing. A flight agent burning through an SOI
> boundary is not doing what it thinks it is doing, and telemetry sampled
> across that boundary changes meaning mid-stream. Also note that
> destruction is gated on `realtimePhysics`
> ([`../03-heat-destruction/HeatManager.md`](../03-heat-destruction/HeatManager.md)),
> so a craft dropped onto rails at an SOI crossing also **stops being
> destroyable**.
>
> **[UNTESTED-LIVE]** — read from IL; never observed in flight, which is
> exactly the gap `sfs_physics_reference.md` §5 records. It is now a
> *specific* thing to look for: **watch `Physics.PhysicsMode` flip at the
> boundary.**

The satellite test scans **only `location.planet.Value.satellites`** —
direct children of the current body, one level down. Combined with
`IsOutsideSOI` for the way out, this is the patched-conic model the
physics doc already infers, now confirmed at the code level.

---

## Reflection recipe

**[UNTESTED-LIVE]**

```csharp
object pl      = FindComponent("SFS.WorldBase.PlanetLoader");
object planets = Get(pl, "planets");                 // Dictionary<string, Planet>

object loc    = Unwrap(Get(ActiveRocket(), "location"));
object planet = Get(loc, "planet");                  // may be Planet_Local -> Unwrap
planet = Unwrap(planet);                             // Unwrap stops on name "Planet"

double mu     = ToD(Get(planet, "mass"));            // μ, not kg
double soi    = ToD(Get(planet, "SOI"));
double radius = ToD(Get(planet, "Radius"));          // property
double maxTer = ToD(Get(planet, "maxTerrainHeight"));

double h   = ToD(Get(loc, "Height"));
double rho = ToD(InvokeReturn(planet, "GetAtmosphericDensity", new object[] { h }));

// GetGravity is AMBIGUOUS -- two overloads. Resolve explicitly:
MethodInfo g = planet.GetType().GetMethod("GetGravity",
    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
    null, new Type[] { typeof(double) }, null);
double gAtR = (double)g.Invoke(planet, new object[] { radius + h });

// Are we on rails or under physics?  (the SOI-crossing tell)
object physics    = Get(ActiveRocket(), "physics");
bool   physicsMode = ToB(Get(physics, "PhysicsMode"));    // non-public property
```

**Gotchas:**

- `Planet.mass` is **μ**; never treat it as kilograms.
- `AtmosphereHeightPhysics` is **+∞** on airless bodies.
- `GetGravity` needs explicit overload resolution.
- `Orbit.apoapsis`/`periapsis` are **radii from planet centre**, not
  altitudes — subtract `Planet.Radius` before comparing to
  `location.Height`.
- `IsInsideSOI` wants a **parent-frame** position; `IsOutsideSOI` wants a
  **planet-relative** one.
- Live planet values are already difficulty-scaled; JSON values are not.

## Status summary

| Item | Status |
|---|---|
| `Planet` field/property layout | [CONFIRMED] |
| `mass` is μ; `g = μ/r²` both overloads | [CONFIRMED] |
| `ρ(h)` formula and hard cutoff | [CONFIRMED] — matches §2.3 exactly |
| Difficulty scaling applied once at load via `ScalePlanetData` | [CONFIRMED] — live reads are pre-scaled |
| Radius / gravity / SOI / SMA also difficulty-scaled | [CONFIRMED] — newly documented |
| `AtmosphereHeightPhysics` = +∞ when airless | [CONFIRMED] — trap |
| `IsOutsideSOI` / `IsInsideSOI` semantics and frames | [CONFIRMED] |
| **SOI crossing in physics mode forces rails** | [CONFIRMED] in IL, [UNTESTED-LIVE] |
| Satellite scan is one level deep (patched conic) | [CONFIRMED] |
| Real per-angle terrain height is queryable, batched | [CONFIRMED] — corrects "single bound" impression |
| Timewarp radius formula | [CONFIRMED] — feeds the open ceiling decision |
| `GetTerrainHeightAtAngles` body | [OPEN] |
| `IsInsideAtmosphere`, terrain normal/colour/LOD bodies | [OPEN] |
| The other ~40 `Planet` methods | [OPEN] — Step 2 |
| `SFS.World.Terrain` namespace — `DynamicTerrain`, `TerrainColliderModule`, `TerrainPoints`, `Chunk` (mesh/collider generation, **not** the height query above) | [OPEN] — Step 2 |
