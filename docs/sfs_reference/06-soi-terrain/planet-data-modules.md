# Planet data modules — `SFS.World.PlanetModules`

Six of the serialized data blocks hanging off `SFS.WorldBase.PlanetData`:
`BasicModule`, `OrbitModule`, `WaterModule` (+ its nested `WaterMask`),
`RingsModule` and `FrontCloudsModule`. Grouped because every one of them is
a **field-only class with no methods but a constructor** — all behaviour
lives in their consumers. What is worth documenting is therefore the field
layout, the real constructor defaults, and *who reads each field*, which is
what this file records.

`TerrainModule` and `Atmosphere_Physics` are the two members of this
namespace with enough weight to get their own files —
[`TerrainModule.md`](TerrainModule.md),
[`Atmosphere_Physics.md`](Atmosphere_Physics.md). The purely visual
`Atmosphere_Visuals` family and `PostProcessingModule` are not yet
documented.

> **Data trust:** every value here is serialized planet data, and several
> are **rewritten in place** by `Difficulty.ScalePlanetData` at load. Read
> them live off `planet.data.*`; never quote them from a wiki or an asset
> dump. See [`Difficulty.md`](Difficulty.md).

---

## BasicModule

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@200600`

The most-read data block in the game: planet radius and gravity. Reached as
`planet.data.basic`.

### Fields

| Name | Type | Access | Default from `.ctor()` | Description | Status |
|---|---|---|---|---|---|
| `radius` | `float64` | public | `-1.0` | Body radius in metres. **Difficulty-scaled in place.** | CONFIRMED |
| `radiusDifficultyScale` | `Dictionary<Difficulty/DifficultyType, float64>` | public | empty | Read only by `Difficulty.RadiusScale`. | CONFIRMED |
| `gravity` | `float64` | public | `-1.0` | The gravity constant. **Difficulty-scaled in place.** See the μ-vs-kg note below. | CONFIRMED |
| `gravityDifficultyScale` | `Dictionary<…, float64>` | public | empty | Read only by `Difficulty.GravityScale`. | CONFIRMED |
| `timewarpHeight` | `float64` | public | `-1.0` | Altitude above which rails timewarp is allowed. **Difficulty-scaled in place.** | CONFIRMED |
| `velocityArrowsHeight` | `float64` | public | **`NaN`** (`00 00 00 00 00 00 f8 ff`) | Altitude at which the velocity-arrow UI appears. | CONFIRMED |
| `mapColor` | `UnityEngine.Color` | public | field-initialised, value not decoded | Map-view colour. | PARTIAL |
| `significant` | `bool` | public | `true` | Whether the map draws a name and dot for this body. | CONFIRMED |
| `rotateCamera` | `bool` | public | `true` | Whether the world camera rolls with the surface. | CONFIRMED |

- **`velocityArrowsHeight` defaults to `NaN`, not to a number.** Every
  comparison against it is false, so a planet file that omits it gets
  "arrows never shown" rather than "arrows always shown". Anything reading
  this field must not assume it is finite.
- **`gravity` is not g and not kg.** `Orbit.TryCreateOrbit` reads it directly
  as the gravitational parameter; see the standing correction in
  `../CORRECTIONS.md` that `Planet.mass` is μ, and
  [`Planet.md`](Planet.md).

### Who reads it

| Field | Consumers |
|---|---|
| `radius` | `Difficulty.ScalePlanetData` (**writes**), `Difficulty.RadiusScale`, `Planet.get_Radius`, `Planet.IsInsideAtmosphere`, `TerrainSampler.GetTerrainSamples`, `TerrainSampler.GetTextureSamples`, `MapManager.DrawLandmarks`, `LegacyConverter` |
| `gravity` | `Difficulty.ScalePlanetData` (**writes**), `Planet.SetupData`, `Orbit.TryCreateOrbit`, `CrewModule.EVA_Exit`, `Astronaut_EVA.get_G` / `.OnFixedUpdate` / `.RCS`, `WheelModule.OnCollisionStay2D`, `LegacyConverter` |
| `timewarpHeight` | `Difficulty.ScalePlanetData` (**writes**), `Planet.get_TimewarpRadius_Ascend`, `Planet.get_TimewarpRadius_Descend`, `VelocityArrowDrawer.OnLocationChange` |
| `velocityArrowsHeight` | `VelocityArrowDrawer.OnLocationChange` — **only reader** |
| `mapColor` | `MapEnvironment.CreateEnvironment` / `.CreateTerrain`, `MapManager.DrawPlanetName` / `.DrawPlanetDots` / `<DrawTrajectories>b__4` |
| `significant` | `MapManager.DrawPlanetName` / `.DrawPlanetDots` / `<DrawTrajectories>b__4` — map only |
| `rotateCamera` | `GameCamerasManager.GetTargetCameraAngle` — **only reader** |

**Note:** `gravity` reaches wheel friction (`WheelModule.OnCollisionStay2D`)
and astronaut EVA directly, not only through the orbital path. Changing it
by reflection changes ground handling as well as trajectories.

---

## OrbitModule

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@200700`

The planet's own orbit around its parent, and its sphere of influence.
Reached as `planet.data.orbit`.

### Fields

| Name | Type | Access | Default from `.ctor()` | Description | Status |
|---|---|---|---|---|---|
| `parent` | `string` | public | `null` | Parent body **code name**, not a reference. Resolved in `Planet.SetupInteractions`. A null/absent parent is how the star at the root is expressed. | CONFIRMED |
| `semiMajorAxis` | `float64` | public | `0.0` | **Difficulty-scaled in place.** | CONFIRMED |
| `smaDifficultyScale` | `Dictionary<…, float64>` | public | empty | Read only by `Difficulty.SmaScale`. | CONFIRMED |
| `eccentricity` | `float64` | public | `0.0` | | CONFIRMED |
| `argumentOfPeriapsis` | `float64` | public | `0.0` | | CONFIRMED |
| `direction` | `int32` | public | **`1`** | Orbit direction. An `int`, not a `bool` or an enum. | CONFIRMED |
| `multiplierSOI` | `float64` | public | **`1.0`** | Multiplies the computed sphere of influence. **Difficulty-scaled in place.** | CONFIRMED |
| `soiDifficultyScale` | `Dictionary<…, float64>` | public | empty | Read only by `Difficulty.SoiScale`. | CONFIRMED |

- **The solar-system graph is by string.** `parent` holds a code name and
  `Planet.SetupInteractions` looks it up in a
  `Dictionary<string, Planet>`. There is no direct `Planet` reference on the
  data object, which is why planet data is portable between saves — the same
  reason `LocationData` stores a planet code name (see
  [`save-records.md`](../07-saveload/save-records.md)).
- **`multiplierSOI` defaults to `1.0`, so SOI is always a computed quantity
  times this factor** — it is never authored directly.

### Who reads it

| Field | Consumers |
|---|---|
| `parent` | `Planet.SetupInteractions`, `Planet.<GetSatellites>b__84_0` |
| `semiMajorAxis` | `Difficulty.ScalePlanetData` (**writes**), `Planet.SetupInteractions`, `Planet.<GetSatellites>b__84_1` (satellite sort key) |
| `eccentricity`, `argumentOfPeriapsis`, `direction` | `Planet.SetupInteractions` — **only reader** |
| `multiplierSOI` | `Difficulty.ScalePlanetData` (**writes**), `Planet.SetupInteractions` |
| `smaDifficultyScale`, `soiDifficultyScale` | `Difficulty.SmaScale` / `Difficulty.SoiScale` |

**Everything except `parent` and `semiMajorAxis` is read exactly once, in
`Planet.SetupInteractions`.** After planet load, the live orbit lives on
`Planet`, not here — mutating `OrbitModule` afterwards changes nothing until
the world reloads.

---

## WaterModule

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@202059`

Twenty-two fields, of which **exactly three matter to simulation** and the
rest are rendering. Reached as `planet.data.water`.

### Fields — the three that affect physics

| Name | Type | Access | Default | Description | Status |
|---|---|---|---|---|---|
| `lowerTerrain` | `bool` | public | `false` | Read by `TerrainSampler.GetTerrainSamples` — whether the terrain formula is pushed down to carve the ocean basin. **Changes the terrain geometry itself.** | CONFIRMED |
| `oceanDepth` | `float32` | public | `0.0f` | Read by `TerrainSampler.GetTerrainSamples`. How far down. | CONFIRMED |
| `wavesSize` | `Vector2` | public | `(0,0)` | Read by `Planet.SetupData`, `Planet.CreateWaterMaterial`, and — the physics one — `Water_Rocket.<FixedUpdate>g__GetWaveHeight|2_0`. **Wave height feeds buoyancy, not just the shader.** | CONFIRMED |

### Fields — rendering only

`oceanMaskTexture`, `sand`, `floor`, `shallow`, `deep`,
`maskGradient_Water`, `waterGradientWidthMultiplier` (default `1.0f`),
`maskGradient_Terrain`, `sandGradientWidthMultiplier` (`1.0f`),
`floorGradientWidthMultiplier` (`1.0f`), `shoreNoiseSize`, `sandNoiseSize`,
`opacity_Surface` (`0.75f`), `opacity_Far` (`1.0f`),
`opacity_FullDarkness` (`0.95f`), `surfaceVisibilityDistance` (`1200f`),
`fullDarknessDepth` (`500f`), `fullDarknessVisibilityDistance` (`300f`),
`mapColor`.

All are consumed by `Planet.CreateWaterMaterial`, `WorldEnvironment.UpdateViewPosition`,
or `MapEnvironment.CreateTerrain`. **Status:** CONFIRMED (layout + defaults);
**Depth:** LIGHT for these nineteen.

- **`lowerTerrain` and `oceanDepth` are the only water fields that change
  where the ground is.** A craft's terrain collision on an ocean world is
  decided by `TerrainSampler`, which consults these two, not by anything on
  the water surface.
- **`wavesSize` crosses the render/physics line** — it is read by both
  `CreateWaterMaterial` and `Water_Rocket`'s wave-height helper. It is the
  one field here where a visual tweak is also a physics change. Note
  `Rocket.floating` means *in water* (see `../CORRECTIONS.md`).

---

## WaterModule/WaterMask

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class (nested in `WaterModule`)
**Status:** CONFIRMED
**Depth:** LIGHT
**IL:** `@202130`

Three floats, both instances constructed non-null by `WaterModule..ctor()`.

| Name | Type | Access | Description |
|---|---|---|---|
| `must` | `float32` | public | Mask threshold above which water is forced. |
| `cannot` | `float32` | public | Threshold below which water is forbidden. |
| `global` | `float32` | public | Uniform bias applied everywhere. |

Read only by `Planet.CreateWaterMaterial`. Rendering-only. The field *names*
are unambiguous; the exact blend semantics live in the shader, which is not
in this assembly. **[OPEN]**

---

## RingsModule

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Status:** CONFIRMED
**Depth:** LIGHT
**IL:** `@201013`

| Name | Type | Access | Description | Status |
|---|---|---|---|---|
| `ringsTexture` | `string` | public | Read by `Planet.CreateRingsMaterial`. | CONFIRMED |
| `startRadius` | `float64` | public | Inner edge. **Difficulty-scaled in place.** Read by `Rings.CreateMesh`. | CONFIRMED |
| `endRadius` | `float64` | public | Outer edge. **Difficulty-scaled in place.** Read by `Rings.CreateMesh`. | CONFIRMED |
| `positionZ` | `float32` | public | Render depth. **Difficulty-scaled in place.** Read by `Rings.Create`. | CONFIRMED |
| `mapColor` | `UnityEngine.Color` | public | Read by `MapEnvironment.CreateEnvironment`. | CONFIRMED |

**Rings are purely visual — no collider, no drag, no gravity contribution.**
Nothing outside `Rings`, `Planet.CreateRingsMaterial`, `MapEnvironment` and
`Difficulty.ScalePlanetData` reads any of these fields. Note that
`positionZ`, a render-depth value, is nonetheless difficulty-scaled along
with the two radii.

---

## FrontCloudsModule

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Status:** CONFIRMED
**Depth:** LIGHT
**IL:** `@200661`

The cloud layer drawn *in front of* the craft.

| Name | Type | Access | Default from `.ctor()` | Description | Status |
|---|---|---|---|---|---|
| `cloudsTexture` | `string` | public | `null` | | CONFIRMED |
| `cloudTextureCutout` | `float32` | public | `1.0f` | | CONFIRMED |
| `fadeZoneHeight` | `float32` | public | `10000f` | **Difficulty-scaled in place.** | CONFIRMED |
| `height` | `float32` | public | `10000f` | **Difficulty-scaled in place.** | CONFIRMED |
| `positionZ` | `float32` | public | `-5000f` | Negative — clouds sit in front of the craft plane. **Difficulty-scaled in place.** | CONFIRMED |
| `sharpenAlpha` | `bool` | public | `false` | | CONFIRMED |

Consumers: `Difficulty.ScalePlanetData`, `Planet.CreateFrontCloudsMaterial`,
`FrontClouds.Create` / `.CreateMesh`, `WorldEnvironment.UpdateFog`.
**Purely visual** — no physics consumer. Note that `positionZ` is negative by
default and is still passed through the difficulty scale, so a negative
scale factor would put the clouds behind the craft.

---

## Reflection notes

- All six are plain public-field classes on `planet.data`:
  `basic`, `orbit`, `water`, `rings`, `frontClouds` (exact `PlanetData` field
  names to be confirmed against [`Planet.md`](Planet.md)). No properties, no
  overloads, no ambiguity.
- Every one has a single public parameterless constructor, so instances are
  trivially constructible — but see the `Atmosphere_Physics` caveat: an
  instance you build yourself has **not** been through
  `Difficulty.ScalePlanetData`, so its `radius` / `gravity` /
  `semiMajorAxis` / `multiplierSOI` will be raw authored values while the
  rest of the world is scaled.
- The `*DifficultyScale` dictionaries are keyed by the nested enum
  `SFS.WorldBase.Difficulty/DifficultyType`; reach it with
  `typeof(SFS.WorldBase.Difficulty).GetNestedType("DifficultyType")`.
- **`OrbitModule` is read-once.** After `Planet.SetupInteractions` has run,
  writing to it does nothing to the live solar system.

## Open

- `BasicModule.mapColor`'s constructor default is a `Color` field
  initialisation whose component values were not decoded from the IL.
  Cosmetic. [OPEN]
- The exact `PlanetData` field names that expose these six modules are
  asserted from usage, not read off `PlanetData` itself — confirm against
  `SFS.WorldBase.PlanetData` (`@150017`) when that type is documented. [OPEN]
- `WaterMask.must` / `cannot` / `global` semantics live in a shader outside
  this assembly. [OPEN]
- `Atmosphere_Visuals` (+ `Gradient`, `Clouds`, `ColorGradient`,
  `ColorGradient/Key`) and `PostProcessingModule` (+ `Key`) are the remaining
  undocumented members of this namespace. [OPEN]
