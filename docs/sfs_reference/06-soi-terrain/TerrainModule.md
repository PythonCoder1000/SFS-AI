# TerrainModule — `SFS.World.PlanetModules`

`TerrainModule` and its three nested data classes, plus `HeightMap`.
Grouped because `TerrainTexture`, `FlatZone` and `RockData` are pure
serialized-data holders reachable only as `TerrainModule` fields, and
`HeightMap` is the interpolation primitive the terrain formulas evaluate.

This is the **authoritative source of terrain geometry** for both the
visual and the collider systems documented in
[`terrain-chunks.md`](terrain-chunks.md). Neither of those computes a
height itself — both call `TerrainModule.GetTerrainPoints`, which calls
`SFS.World.TerrainSampler`.

> **Data trust:** every field on `TerrainModule`, `TerrainTexture`,
> `FlatZone` and `RockData` is **serialized planet data**, loaded from the
> planet `.txt` files by `PlanetLoader`. Per the project's standing rule,
> none of these values may be quoted from a wiki or an asset dump — read
> them live off `planet.data.terrain`.

---

## TerrainModule

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Extends:** `System.Object`
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@201039`

Reached as `planet.data.terrain` (`SFS.WorldBase.PlanetData::terrain`).

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `TERRAIN_TEXTURE_DATA` | `TerrainTexture` | public | no | Rendering-only texture settings. | CONFIRMED |
| `terrainFormula` | `string[]` | public | no | The default terrain-height expression, as source text. Compiled by `SetupSamplers`. | CONFIRMED |
| `terrainFormulaDifficulties` | `Dictionary<Difficulty/DifficultyType, string[]>` | public | no | Per-difficulty overrides of `terrainFormula`. **Terrain shape itself is difficulty-dependent.** | CONFIRMED |
| `textureFormula` | `string[]` | public | no | A second expression producing the per-vertex texture blend value. | CONFIRMED |
| `verticeSize` | `float32` | public | no | Base mesh resolution in metres at max LOD. Also feeds the *collider* grid via `TerrainColliderManager.GetAngularChunkSize`. | CONFIRMED |
| `collider` | `bool` | public | no | If false, collider chunks are still created and reference-counted but carry **no `PolygonCollider2D`**. | CONFIRMED |
| `flatZones` | `FlatZone[]` | public | no | Flattened launch/landing regions. | CONFIRMED |
| `flatZonesDifficulties` | `Dictionary<Difficulty/DifficultyType, FlatZone[]>` | public | no | Per-difficulty overrides. | CONFIRMED |
| `rocks` | `RockData` | public | no | Surface scatter settings. Cosmetic. | CONFIRMED |
| `terrainSampler` | `TerrainSampler/Executor` | public | no | The **compiled** terrain formula. Null until `SetupSamplers` has run, or if compilation threw. | CONFIRMED |
| `textureSampler` | `TerrainSampler/Executor` | public | no | The compiled texture formula. Same caveat. | CONFIRMED |

### Methods

#### SetupSamplers(string codeName, SFS.I_MsgLogger log) -> void

- **Access:** public instance
- **Parameters:** `codeName` is used only in error messages; `log` receives
  compilation failures (see [`I_MsgLogger.md`](../13-challenges-logging/I_MsgLogger.md)).
- **Preconditions:** **A loaded world.** The difficulty fallback chain reads
  `SFS.Base.worldBase.settings.difficulty.difficulty`, so calling this
  outside a loaded world NREs. **Ordering requirement: this must succeed
  before any call to `GetTerrainPoints` or `GetMaxTerrainHeight` on the same
  `TerrainModule`** — those dereference `terrainSampler`, which stays null
  if compilation threw.
- **Behavior:** resolves the terrain formula through a four-step fallback chain:
  1. `terrainFormulaDifficulties[Base.worldBase.settings.difficulty.difficulty]`
  2. else `terrainFormulaDifficulties[(DifficultyType)0]`
  3. else `terrainFormula`
  4. else `new string[0]`

  Lookups go through `Assets.Scripts.Utility.DictionaryUtils.At<K,V>`, which
  returns `default` rather than throwing on a missing key, and each step is
  guarded by a null check on the dictionary itself.
  The result is compiled by `TerrainSampler/Compiler.Compile(string[], I_MsgLogger)`
  into `terrainSampler`. `textureFormula` is then compiled into `textureSampler`
  with **no** fallback chain at all.
- **Gotchas:**
  - Both compilations are wrapped in `try`/`catch`. On failure the sampler
    field is **left null** and the only trace is
    `log.Log("ERROR: terrain formula: " + codeName)` (or
    `"ERROR: texture formula: "`). A planet with a broken formula loads
    silently and then throws later, at the first `GetTerrainPoints`.
  - Step 2's fallback key is the literal `0`, i.e. the first
    `DifficultyType` — it is a hardcoded default, not "the current difficulty".
  - The whole method reads `SFS.Base.worldBase.settings.difficulty`, so
    calling it outside a loaded world will NRE.
- **Status:** CONFIRMED

#### GetTerrainPoints(float64 from_Angle_01, float64 size_Angle_01, int32 pointCount, bool offset, bool forCollider, Planet planet, [out] Double2 offsetAmount, [out] float64[] angles, [out] float64[] height) -> Chunk/TerrainPoints

- **Access:** public instance
- **Parameters:**
  - `from_Angle_01`, `size_Angle_01` — **normalised revolutions**, not radians.
    `1.0` is one full turn. `from` is wrapped with `(from + 1.0) % 1.0`, so
    a single negative turn is tolerated but `-1.5` is not.
  - `pointCount` — number of terrain vertices. Both `out` arrays are sized
    `pointCount + 1`.
  - `offset` — if true, geometry is emitted relative to a floating-origin
    offset instead of planet-centred coordinates.
  - `forCollider` — changes the *end caps* only (see below).
- **Returns:** a `TerrainPoints` whose `points` array has
  `pointCount + (forCollider ? 2 : 1)` entries.
- **Preconditions:** `terrainSampler` and `textureSampler` must both be non-
  null — i.e. `SetupSamplers` must already have completed **without**
  throwing. `planet` must be non-null with `data` populated. `pointCount >=
  1`. **No scene or singleton requirement**, including when `offset` is
  true: `WorldView.GetOffset(Double2, double)` is a `public static` pure
  function and does not touch `WorldView.main` (confirmed from its IL body,
  `@199953`).
- **Behavior:**
  ```
  from01   = (from_Angle_01 + 1.0) % 1.0;
  fromRad  = from01 * 2π;
  toRad    = (from01 + size_Angle_01) * 2π;
  step     = Chunk.GetAngleBetweenPoints(size_Angle_01, pointCount);
  uvScale  = (float)(planet.Radius * step) * 8f;

  offsetAmount = offset
      ? WorldView.GetOffset(Double2.CosSin(fromRad, planet.Radius), 1000.0)
      : Double2.zero;

  angles = new double[pointCount + 1];
  for (i) angles[i] = fromRad + step * i;

  height  = TerrainSampler.GetTerrainSamples(planet, angles, fromRad, toRad);
  texture = TerrainSampler.GetTextureSamples(planet.data, angles);

  tp = new TerrainPoints(pointCount + (forCollider ? 2 : 1));
  for (i = 0; i < pointCount; i++) {
      r = planet.Radius + height[i];
      tp.points[i + 1]    = (Double2.CosSin(angles[i], r) - offsetAmount).ToVector3;
      tp.otherData[i + 1] = new Vector2((float)((height[i] - height[i+1]) / uvScale),
                                        (float)texture[i]);
  }

  if (forCollider) {
      tp.points[0]     = (Double2.CosSin(fromRad, Max(1.0, planet.Radius + height[0]              - 1000.0)) - offsetAmount).ToVector3;
      tp.points[last]  = (Double2.CosSin(toRad,   Max(1.0, planet.Radius + height[height.Length-2] - 1000.0)) - offsetAmount).ToVector3;
  } else {
      tp.points[0]     = -offsetAmount.ToVector3;      // the planet centre
  }
  return tp;
  ```
- **Notes:**
  - **Slot 0 is not a terrain vertex.** For a visual chunk it is the planet
    *centre*, which is exactly what `Chunk.GetIndices`' triangle fan
    (`0, i+2, i+1`) needs. For a collider chunk, slot 0 and the last slot are
    a **skirt** dropped 1000 m below the terrain at each end, so the polygon
    closes without the craft falling through the seam.
  - The skirt is clamped by `Math.Max(1.0, …)`, so on a body whose radius is
    under 1000 m the skirt collapses to 1 m from the centre rather than
    inverting.
  - `otherData.x` is the **slope** between consecutive samples, normalised by
    `uvScale`; `otherData.y` is the texture-formula output.
  - `otherData[0]` and `otherData[last]` are never written and stay
    `Vector2.zero`.
  - The last loop iteration reads `height[pointCount]`, which is why both
    arrays are `pointCount + 1` long.
- **Gotchas:**
  - Throws `NullReferenceException` if `SetupSamplers` failed — see above.
  - `angles` and `height` are `out` parameters and are freshly allocated on
    every call. This is on the chunk-creation path, not a per-frame path,
    but `LoadFully` can trigger hundreds of calls synchronously.
- **Status:** CONFIRMED

#### GetMaxTerrainHeight(Planet planet) -> float64

- **Access:** public instance
- **Returns:** the maximum terrain height anywhere on the planet, sampled at
  1001 evenly spaced angles.
- **Preconditions:** Same sampler requirement as `GetTerrainPoints` —
  `SetupSamplers` must have succeeded. No scene or singleton requirement.
  Note this is an expensive call: 1001 samples, allocating two arrays.
- **Behavior:**
  ```
  double[] angles = new double[1001];
  for (i) angles[i] = 0.0062831853071795866 * i;      // 2π / 1000
  return TerrainSampler.GetTerrainSamples(planet, angles, 0.0, 2π).Max();
  ```
- **Gotchas:**
  - This is where `Planet.maxTerrainHeight` comes from, and it is a
    **1000-sample approximation**, not an analytic maximum. A terrain formula
    with features narrower than 0.36° can exceed it. `maxTerrainHeight` is
    used as the collider altitude cut-off in `TerrainColliderModule.UpdateChunks`
    and as a fast-reject bound elsewhere — it is a bound in practice, not by
    construction.
  - Index 1000 evaluates to exactly `2π`, duplicating index 0.
- **Status:** CONFIRMED

#### GetVerticeSize(int32 LOD, int32 LOD_Max) -> float64

- **Preconditions:** None beyond valid arguments. Reads only the
  `verticeSize` field; no sampler, scene or singleton.
- **Behavior:** `return Math.Pow(2.55, LOD_Max - LOD) * verticeSize;`
- **Note:** the LOD ratio is **2.55**, not 2 — mesh resolution coarsens faster
  than the chunk subdivision (which is exactly 2 per level).
- **Status:** CONFIRMED

#### GetLoadDistance(int32 LOD, int32 LOD_Max) -> float64

- **Preconditions:** None beyond valid arguments. It reads no field at all —
  both constants are inlined — so it is callable on a default-constructed
  `TerrainModule`.
- **Behavior:** `return Math.Pow(2.05, LOD_Max - LOD) * 250.0;`
- **Note:** `250.0` is a hardcoded literal, not a field — the base load
  distance is not tunable per planet. Both `2.05` and `250.0` are inlined
  constants, so reflection cannot change them.
- **Status:** CONFIRMED

#### GetChunkSize_Angular(int32 baseChunkCount, int32 LOD) -> float64

- **Preconditions:** None beyond valid arguments, plus `baseChunkCount != 0`
  and `LOD < 31`. Reads no field.
- **Behavior:** `return 1.0 / ((int)Math.Pow(2, LOD) * baseChunkCount);`
- **Returns:** chunk width in normalised revolutions.
- **Gotcha:** `Math.Pow(2, LOD)` is computed in `double` and then cast to
  `int`. Past `LOD == 31` the cast is undefined-ish (in practice `int.MinValue`
  on x86), producing a negative or zero divisor. `GetMaxLOD` keeps real
  planets far below this.
- **Status:** CONFIRMED

---

## TerrainModule/TerrainTexture

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class (nested)
**Status:** CONFIRMED
**Depth:** LIGHT
**IL:** `@201530`

Pure rendering data — planet-map and surface-texture names, sizes, fade and
shadow parameters. No simulation relevance; recorded for completeness.

### Fields

| Name | Type | Access | Description |
|---|---|---|---|
| `planetTexture` | `string` | public | Texture asset name for the map view. |
| `planetTextureCutout` | `float32` | public | |
| `planetTextureRotation` | `float32` | public | |
| `planetTextureDontDistort` | `bool` | public | |
| `surfaceTexture_A` / `surfaceTextureSize_A` | `string` / `Vector2` | public | First surface layer. |
| `surfaceTexture_B` / `surfaceTextureSize_B` | `string` / `Vector2` | public | Second surface layer, blended by the texture formula. |
| `terrainTexture_C` / `terrainTextureSize_C` | `string` / `Vector2` | public | Third layer. |
| `surfaceLayerSize` | `float32` | public | |
| `minFade`, `maxFade` | `float32` | public | |
| `shadowIntensity`, `shadowHeight` | `float32` | public | |

**Status:** CONFIRMED (field layout). No methods beyond `.ctor()`.

---

## TerrainModule/FlatZone

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class (nested)
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@201634`

A flattened region of terrain — this is how launch pads and scripted landing
sites get level ground. Consumed by `SFS.World.TerrainSampler`, not by
`TerrainModule` itself.

### Fields

| Name | Type | Access | Description | Status |
|---|---|---|---|---|
| `height` | `float64` | public | The flat height, in the same units as terrain height. | CONFIRMED |
| `angle` | `float64` | public | Centre of the zone. **Units not confirmed from this type** — resolve against `TerrainSampler`. | PARTIAL |
| `width` | `float64` | public | Angular half-width or full width — not disambiguated here. | PARTIAL |
| `transition` | `float64` | public | Blend distance from flat zone back to formula terrain. | PARTIAL |

### Methods

#### .ctor()

- **Access:** public instance
- **Preconditions:** None beyond valid arguments.
- **Behavior:** the compiler-generated default constructor; all four fields
  are left at `0.0`.
- **Status:** CONFIRMED

No methods beyond `.ctor()`. **The semantics of `angle` / `width` /
`transition` are decided entirely inside `SFS.World.TerrainSampler`,
which is not yet documented.** [OPEN]

---

## TerrainModule/RockData

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class (nested)
**Status:** CONFIRMED
**Depth:** LIGHT
**IL:** `@201656`

Surface scatter settings, consumed only by `DynamicChunk.GenerateRocks`.
Cosmetic — rocks have no colliders and no physics.

### Fields

| Name | Type | Access | Description |
|---|---|---|---|
| `rockType` | `string` | public | Prefab selector. |
| `rockDensity` | `float32` | public | |
| `minSize`, `maxSize` | `float32` | public | |
| `powerCurve` | `float32` | public | Biases the size distribution between min and max. |
| `maxAngle` | `float32` | public | Slope cut-off above which rocks are not placed. |

**Status:** CONFIRMED (field layout). No methods beyond `.ctor()`.

---

## HeightMap

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@201685`

A 1-D float lookup table with linear interpolation. Used by terrain formulas
as a hand-authored height curve. Not a `Planet` field — instances are created
by the formula compiler.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `points` | `float32[]` | public | no | The samples. Default is `{ 0f, 1f }` — a plain ramp. | CONFIRMED |

### Methods

#### .ctor() / .ctor(float32[] points)

- **Preconditions:** None beyond valid arguments. A null `points` argument
  is stored as null and will NRE on the first `Evaluate`, not here.
- **Behavior:** the field initialiser sets `points = new float[2] { 0f, 1f }`
  in **both** constructors; the array overload then overwrites it.
- **Status:** CONFIRMED

#### .ctor(UnityEngine.Texture2D image)

- **Preconditions:** `image` must be non-null and **CPU-readable** —
  `GetPixels32()` throws on a texture imported without Read/Write enabled.
  `image.width >= 1`, or `points` is empty and every `Evaluate` then throws.
- **Behavior:** `points = new float[image.width]`, then for each column
  `i` in `0 … width-1`:
  `points[points.Length - i - 1] = GetHeightAtX(i)`.

  `GetHeightAtX(x)` scans rows `y = 0 … height-1`:
  ```
  a = colors[y * width + x].a / 255f;
  if (a < 1f) return (y + a) / height;
  ```
  returning `1f` if no row was found.
- **Gotchas:**
  - **The columns are reversed.** Column 0 of the image becomes the *last*
    entry of `points`. A texture-authored height map reads right-to-left.
  - Height is read from the **alpha** channel, not luminance, and the first
    non-opaque row from the top wins. Sub-pixel precision comes from the
    alpha value itself.
  - `GetPixels32()` requires the texture to be readable; a non-readable
    import setting throws here.
- **Status:** CONFIRMED

#### Evaluate(float32 a) -> float32

- **Preconditions:** `points.Length >= 2` (a length of 1 makes the index `%`
  a division by zero) and `a >= 0` (a negative argument yields a negative
  index and throws `IndexOutOfRangeException`, because C#'s `%` keeps the
  sign). No upper bound — the function wraps.
- **Behavior:**
  ```
  a *= points.Length - 1;
  int   i = (int)a % (points.Length - 1);
  float t = a % 1f;
  return points[i] * (1f - t) + points[i + 1] * t;
  ```
- **Gotchas:**
  - **This wraps, it does not clamp.** The `%` on the index makes the curve
    periodic — `Evaluate(1f)` returns `points[0]`, **not** the last sample.
    That is deliberate for an angle-indexed map and a trap for anything else.
  - A **negative** `a` yields a negative index and throws
    `IndexOutOfRangeException` — C#'s `%` keeps the sign.
  - `points.Length == 1` divides by zero in the `%`.
- **Status:** CONFIRMED

#### EvaluateDoubleOut(float64 a) -> float64

- **Preconditions:** Identical to `Evaluate`: `points.Length >= 2` and `a >=
  0`. The `double` signature buys no extra safety and no extra precision.
- **Behavior:** identical to `Evaluate`, but the input scaling and index are
  computed in `double` and the result is widened to `double` on return.
- **Gotcha:** **this is not a double-precision evaluate.** `t` is narrowed to
  `float32` and the lerp itself runs entirely in `float32`; only the argument
  and the return type are `double`. Do not reach for it expecting extra
  precision in the interpolation.
- **Status:** CONFIRMED

#### EvaluateClamped(float32 a) -> float32

- **Preconditions:** `points.Length >= 2`. **No constraint on `a`** — this
  is the variant that is safe for arbitrary input, including negatives and
  `NaN` (which returns the last sample).
- **Behavior:**
  ```
  if (!(a < 1f)) return points[points.Length - 1];
  if (!(a > 0f)) return points[0];
  a *= points.Length - 1;
  int   i = (int)a;
  float t = a % 1f;
  return points[i] * (1f - t) + points[i + 1] * t;
  ```
- **Notes:**
  - No modulo on the index — this is the non-periodic variant.
  - The comparisons are the unordered forms (`blt.un` / `bgt.un`), so
    **`NaN` returns `points[points.Length - 1]`** rather than throwing or
    propagating `NaN`.
- **Status:** CONFIRMED

---

## Reflection notes

- `planet.data.terrain` is a plain public field chain — no properties, no
  ambiguity: `Planet.data` → `PlanetData.terrain` → `TerrainModule`.
- All five `TerrainModule` LOD/geometry methods are public instance methods
  with unique names; none is overloaded.
- `GetTerrainPoints` has three `out` parameters, so a reflection call needs a
  `object[]` args array and must read the mutated slots back out.
- `HeightMap.Evaluate` / `EvaluateDoubleOut` / `EvaluateClamped` have
  distinct names — no `AmbiguousMatchException` risk (contrast the
  overload traps catalogued in [`REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md)).
- **For a terrain height at a given angle, do not call any of these.** Use
  `Location.GetTerrainHeight(bool)` → `Planet.GetTerrainHeightAtAngle`
  (see [`Planet.md`](Planet.md)); `GetTerrainPoints` allocates three arrays
  and builds a mesh-ready vertex list as a side effect.

## Open

- `SFS.World.TerrainSampler` (`Compiler`, `Executor`, `GetTerrainSamples`,
  `GetTextureSamples`) is not yet documented. It is the actual evaluator, and
  the semantics of `FlatZone.angle` / `width` / `transition` live there. [OPEN]
- `Planet.GetMaxLOD()` and `Planet.GetVerticeCount(double, double)` are
  referenced throughout this file but are documented (or not) under
  [`Planet.md`](Planet.md). [OPEN]
- Every numeric field here is serialized planet data and must be read live.
  [OPEN by rule — see `../METHODOLOGY.md`]
