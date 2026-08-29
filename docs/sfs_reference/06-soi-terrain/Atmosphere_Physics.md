# Atmosphere_Physics — `SFS.World.PlanetModules`

## Atmosphere_Physics

**Namespace:** `SFS.World.PlanetModules`
**Kind:** class
**Extends:** `System.Object`
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@200297`

The nine numbers that define a planet's atmosphere for **physics** purposes
— drag, heating, parachutes and the atmosphere/space state classifier.
Reached as `planet.data.atmospherePhysics`. Its visual counterpart is
`Atmosphere_Visuals`, which shares nothing with it.

The class has **no methods** beyond its constructor: it is pure serialized
data, and every consumer reads the fields directly. That makes the consumer
map below the useful part of this entry.

> **Data trust:** these are per-planet serialized values, and `height` and
> `curve` are additionally **rewritten in place** by
> `Difficulty.ScalePlanetData`. Never quote a number for them — read it live
> off the running game, after the world has loaded. See
> [`Difficulty.md`](Difficulty.md) and `../CORRECTIONS.md` (the Earth
> `ρ0 = 0.005`, `curve = 10`, `height = 30000` correction).

### Fields

| Name | Type | Access | Static | Default from `.ctor()` | Description | Status |
|---|---|---|---|---|---|---|
| `height` | `float64` | public | no | `-1.0` | Atmosphere top, in metres above sea level. **Mutated by `Difficulty.ScalePlanetData`.** | CONFIRMED |
| `density` | `float64` | public | no | `-1.0` | Sea-level density ρ₀. | CONFIRMED |
| `curve` | `float64` | public | no | `-1.0` | Falloff exponent of the density profile. **Mutated by `Difficulty.ScalePlanetData`.** | CONFIRMED |
| `curveScale` | `Dictionary<Difficulty/DifficultyType, float64>` | public | no | empty dictionary | Per-difficulty multiplier applied to `curve`, read by `Difficulty.AtmosphereCurveScale`. | CONFIRMED |
| `parachuteMultiplier` | `float64` | public | no | `1.0` | Scales parachute effectiveness on this planet. | CONFIRMED |
| `upperAtmosphere` | `float64` | public | no | `0.5` | Fraction of `height` above which `StatsRecorder` classifies the craft as "upper atmosphere". | CONFIRMED |
| `heightDifficultyScale` | `Dictionary<Difficulty/DifficultyType, float64>` | public | no | empty dictionary | Per-difficulty multiplier applied to `height`, read by `Difficulty.AtmosphereScale`. | CONFIRMED |
| `shockwaveIntensity` | `float32` | public | no | `0.5f` | Reentry shockwave opacity multiplier. | CONFIRMED |
| `minHeatingVelocityMultiplier` | `float32` | public | no | `1.0f` | Scales the velocity threshold below which reentry heating does not start. | CONFIRMED |

**The three `-1.0` defaults are sentinels, not physical values.** A planet
whose data omits `height` / `density` / `curve` gets `-1.0`, which makes
`IsInsideAtmosphere` false everywhere and `GetAtmosphericDensity` meaningless
— it is how a vacuum body is expressed, and also how a malformed planet file
fails.

### Methods

#### .ctor()

- **Access:** public instance
- **Behavior:** assigns the nine defaults tabulated above. Note both
  dictionaries are constructed non-null, so a consumer can index them without
  a null check — but they are **empty**, so every lookup must still tolerate
  a miss.
- **Status:** CONFIRMED

---

## Who reads these fields

Confirmed by IL cross-reference over the whole assembly — this is the
complete list of consumers in `Assembly-CSharp.dll` 1.6.00.16.

| Field | Read by | What it does there |
|---|---|---|
| `height` | `Difficulty.ScalePlanetData` `@146297` | **read *and written*** — scaled by `AtmosphereScale(planet)` |
| | `Planet.get_AtmosphereHeightPhysics` `@146962` | the public accessor |
| | `Planet.IsInsideAtmosphere(Double2)` `@148569` | the atmosphere test |
| | `LocationDrawer.GetIdealAngle` `@166069` | UI: the ideal-ascent-angle readout |
| `density` | `Planet.GetAtmosphericDensity(double)` `@148620` | ρ₀ in the density formula |
| | `LegacyConverter.Convert_Atmosphere_Physics` `@221261` | old-format planet import |
| `curve` | `Difficulty.ScalePlanetData` `@146303` | **read *and written*** — scaled by `AtmosphereCurveScale(planet)` |
| | `Planet.GetAtmosphericDensity(double)` `@148606`, `@148613` | read **twice** in the one formula |
| | `LegacyConverter.Convert_Atmosphere_Physics` `@221256` | old-format planet import |
| `curveScale` | `Difficulty.AtmosphereCurveScale(PlanetData)` `@146589` | the only reader |
| `heightDifficultyScale` | `Difficulty.AtmosphereScale(PlanetData)` `@146524` | the only reader |
| `parachuteMultiplier` | `ParachuteModule.DeployParachute(UsePartData)` `@262568` | deploy gate |
| | `ParachuteModule.LateUpdate` `@262941` | per-frame drag scaling |
| | `BalloonModule.DeployBalloon(UsePartData)` `@39948` | balloons reuse the parachute multiplier |
| `upperAtmosphere` | `StatsRecorder.GetState(Location)` `@72147` | the only reader — atmosphere-state classification |
| `shockwaveIntensity` | `AeroModule.GetTemperatureAndShockwave` `@216371` | shockwave opacity out-parameter |
| `minHeatingVelocityMultiplier` | `AeroModule.GetTemperatureAndShockwave` `@216366` | heating onset velocity |

### Consequences worth stating plainly

- **`height` and `curve` are difficulty-mutated in place**, so the values on
  a live `Atmosphere_Physics` are the *already-scaled* ones. Reading them and
  then applying a difficulty scale yourself double-counts. `density` is
  **not** scaled.
- **`parachuteMultiplier` is not parachute-only** — `BalloonModule` reads the
  same field. Changing it affects both part types.
- **`upperAtmosphere` has exactly one consumer** and it is a statistics
  classifier, not physics. It does not affect drag, heating, or density.
- **`shockwaveIntensity` and `minHeatingVelocityMultiplier` are `float32`**
  while everything else on this class is `float64` — a reflection helper that
  assumes a uniform field type will throw on these two.
- Nothing here is consulted by `AeroModule.CalculateDragForce`. Drag *area*
  comes from geometry (see [`AeroModule.md`](../02-drag-aero/AeroModule.md));
  this class supplies only the density the force is multiplied by, via
  `Planet.GetAtmosphericDensity`.

---

## Reflection notes

- Access path: `planet.data.atmospherePhysics` — public fields all the way,
  no properties, no ambiguity.
- The class has a single public parameterless constructor, so a fresh
  instance is trivially constructible — but assigning one to
  `planet.data.atmospherePhysics` bypasses `Difficulty.ScalePlanetData`,
  which normally runs once at planet load. The result is an unscaled
  atmosphere that will not match anything else in the world.
- Both dictionaries are keyed by `SFS.WorldBase.Difficulty/DifficultyType`,
  a nested enum — reach it with
  `typeof(SFS.WorldBase.Difficulty).GetNestedType("DifficultyType")`.

## Open

- Whether `Difficulty.ScalePlanetData` is idempotent — i.e. whether calling
  it twice scales `height`/`curve` twice — is not established here. Relevant
  to any mod that reloads planet data. [OPEN]
- The exact form of `Planet.GetAtmosphericDensity(double)` belongs in
  [`Planet.md`](Planet.md); this entry only records which fields it reads.
  [OPEN]
