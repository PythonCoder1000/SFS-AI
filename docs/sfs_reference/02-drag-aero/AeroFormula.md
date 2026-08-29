# `AeroFormula` — the reentry temperature formula

**Migrated** from `docs/sfs_source_reference.md` §D1.2 (2026-08-28).
Signatures re-read from IL during migration.

Entry point is
[`AeroModule.GetTemperatureAndShockwave`](AeroModule.md); the temperature
this produces is consumed by
[`../03-heat-destruction/HeatManager.md`](../03-heat-destruction/HeatManager.md).

## The air temperature a rocket sees is global, not per-part

**[CONFIRMED].** Entry point:

```
public static void AeroModule.GetTemperatureAndShockwave(
    Location location, out float Q, out float shockOpacity, out float temperature)   @216283
```

Public, static, takes only a `Location` — directly callable.

```csharp
AeroData aeroData = GameManager.main.aeroData;

// Debug override path -- ignores physics entirely
if (aeroData.testShock || aeroData.testReentry) {
    Q = 0f;
    shockOpacity = aeroData.testShock ? aeroData.shockOpacity / 100f : 0f;
    temperature  = aeroData.testReentry
        ? aeroData.reentryPercent / (100f - aeroData.reentryPercent) * 3000f : 0f;
    return;
}

aeroData.Formula.GetEverything(
    location.velocity.magnitude,
    location.VerticalVelocity,
    location.planet.GetAtmosphericDensity(location.Height),
    location.planet.data.atmospherePhysics.minHeatingVelocityMultiplier,
    location.planet.data.atmospherePhysics.shockwaveIntensity,
    out Q, out shockOpacity, out temperature, out _);
```

**Gotcha:** the `testShock` / `testReentry` branch is a developer
override on `AeroData` that produces temperatures with **no relation to
flight state** — check it is false before trusting a reading.

---

## AeroFormula

**Namespace:** *(none — top-level, global namespace)*
**Kind:** struct (`sealed`, `sequential`, `serializable`)
**Extends:** System.ValueType
**Implements:** —
**Status:** [CONFIRMED] structure and `GetTemperature` body · **[OPEN] the four coefficient values**
**Depth:** FULL
**IL:** `scratch/full_il.txt` @23603 · 5 methods / 4 fields

Reached via `GameManager.main.aeroData.Formula` →
`AeroData.formulaHolder.formula` (`TemperatureTest.formula` @26477).

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `velPow` | `float` | public | no | velocity exponent | **[OPEN] value** |
| `densityPow` | `float` | public | no | density exponent (used as `1/densityPow`) | **[OPEN] value** |
| `tempOffset` | `float` | public | no | ascent-discount coefficient | **[OPEN] value** |
| `m` | `float` | public | no | overall divisor | **[OPEN] value** |

> The `public float drag` field a naive extractor reports here does not
> exist — it is a closure field on the nested `<>c__DisplayClass5_0`.

> **[OPEN] — these four coefficients are serialized Unity data, not IL
> literals.** They must be read live. Per the project's data-trust rule,
> do not assume values for them.
>
> **Where to read them:** `GameManager.main.aeroData` is a serialized
> `AeroData` field on the world-scene `GameManager` singleton, and it is
> what supplies these. So the read is `GameManager.main.aeroData` → the
> relevant `AeroFormula` → these four fields, all reachable from the
> probe with no new plumbing. The `AeroData` type's own layout is
> **[PARTIAL]** — not read — so the exact path from `aeroData` to an
> `AeroFormula` still needs one live introspection pass.

### Methods

#### GetEverything(double velocity, double velocity_Y, double density, float startHeatingVelocityMultiplier, float shockwaveM, out float Q, out float shockOpacity, out float temperature, out float pure) -> void

- **Access:** public instance · IL @23612
- **Behavior:**
  ```csharp
  Q = GetQ(velocity, density);                              // = (float)(v*v*density)
  temperature = GetTemperature(velocity, velocity_Y, density,
      startHeatingVelocityMultiplier
        * Base.worldBase.settings.difficulty.MinHeatVelocityMultiplier
        * 250f);
  shockOpacity = GetShockOpacity(Q, (float)velocity, (float)density, shockwaveM, temperature, out pure);
  ```
- **Status:** [CONFIRMED]

#### GetTemperature(double velocity, double velocity_Y, double density, float minHeatVelocity) -> float

**The core formula.**

- **Access:** **private** instance · IL @23756, full body read
- **Parameters:** `velocity` — speed magnitude; `velocity_Y` — vertical
  component, **signed** (positive = ascending); `density` — atmospheric
  density at height; `minHeatVelocity` — the heating-onset speed, already
  multiplied by the difficulty factor and 250
- **Returns:** temperature, clamped at zero from below
- **Behavior:**
  ```csharp
  float hvm = Base.worldBase.settings.difficulty.HeatVelocityMultiplier;
  velocity        /= hvm;
  velocity_Y      /= hvm;
  minHeatVelocity /= hvm;

  // Ascending? discount some speed -- climbing out heats less than falling in.
  if (velocity_Y > 0.0)
      velocity -= Math.Min(velocity_Y * 2.5, velocity * 0.5);

  float t = (float)(Math.Pow(velocity, velPow) * Math.Pow(density, 1f / densityPow)) / m;

  t += t * (float)(tempOffset * (velocity_Y > 0.0
                                  ? Math.Min(velocity_Y / velocity * 2.0, 0.4)
                                  : 0.0)
                   + 0.2);

  // Hard cap tied to how far above the heating-onset speed you are
  float cap = ((float)velocity - minHeatVelocity) * 6f;
  if (t > cap) t = cap;

  // Soft knee above 2000
  if (t > 2000f) t = 2000f + (t - 2000f) / 1.5f;

  return t > 0f ? t : 0f;
  ```
- **Gotchas:** ascent and descent are **not symmetric** — an ascending
  craft gets a speed discount of up to 50%, and a separate `tempOffset`
  bonus term capped at 0.4. Both branches key off the sign of
  `velocity_Y`.
- **Constants confirmed as IL literals:** `2.5`, `0.5`, `0.2`, `0.4`,
  `2.0`, `6f`, `2000f`, `1.5f`, and the `250f` in `GetEverything`.
- **Status:** [CONFIRMED] — modulo the four serialized coefficients

#### GetQ(double velocity, double density) -> float

- **Access:** private instance · IL @23876
- **Behavior:** `(float)(velocity * velocity * density)` — dynamic
  pressure, up to a constant.
- **Status:** [CONFIRMED]

#### GetShockOpacity(float Q, float velocity, float density, float shockwaveM, float temperature, out float pure) -> float

- **Access:** private instance · IL @23657
- **Behavior:** visuals only. Uses a compiler-emitted local function
  `<GetShockOpacity>g__Apply|5_0` @23892, which computes
  `AeroModule.GetIntensity(drag, 3f) * 2f`.
- **Status:** [PARTIAL] — structure only, main body [OPEN]

### Related

`AeroModule.GetIntensity(value, halfPoint) = value / (value + halfPoint)`
@216381 — a saturating curve, used for visuals.

## Status summary

| Item | Status |
|---|---|
| Temperature is **global**, not per-part | [CONFIRMED] |
| `GetTemperatureAndShockwave` is `public static`, takes only a `Location` | [CONFIRMED] |
| `testShock` / `testReentry` developer override branch | [CONFIRMED] |
| `AeroFormula` is a 4-field struct reached via `GameManager.main.aeroData` | [CONFIRMED] |
| `GetTemperature` formula and its literal constants | [CONFIRMED] |
| `GetQ` body | [CONFIRMED] |
| `velPow` / `densityPow` / `tempOffset` / `m` **values** | **[OPEN]** — serialized data, must be read live |
| `AeroData` type layout | [PARTIAL] — not read |
| `GetShockOpacity` body | [OPEN] — visuals only |
