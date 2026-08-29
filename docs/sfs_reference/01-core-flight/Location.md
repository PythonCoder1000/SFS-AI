# `Location`, `WorldLocation`, `Double2` — the world coordinate system

**Group file.** Three types, easy to confuse, with different mutability
and different traps. `Double2` is a global-namespace math struct and
would otherwise belong in `00-infrastructure/`, but it is documented here
because every trap in it is a coordinate-system trap.

**Migrated** from `docs/sfs_source_reference.md` §B2 (2026-08-28).

---

## Location

**Namespace:** SFS.World
**Kind:** class (`serializable`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @160698 · 9 methods / 4 fields

An **immutable-by-convention snapshot**. Four public fields, no
properties backing them.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `time` | `double` | public | no | world time, from `WorldTime.main.worldTime` — **not** a Unity clock | [CONFIRMED] |
| `planet` | `SFS.WorldBase.Planet` | public | no | the frame these coordinates are relative to | [CONFIRMED] |
| `position` | `Double2` | public | no | **planet-relative**, metres, planet centre at origin | [CONFIRMED] |
| `velocity` | `Double2` | public | no | planet-relative, m/s | [CONFIRMED] |

`position` and `velocity` are **not** solar-system coordinates — see
`GetSolarSystemPosition`.

### Computed members

All bodies read.

```csharp
double Radius           => position.magnitude;
double Height           => Radius - planet.Radius;
double VerticalVelocity => velocity.Rotate(-(position.AngleRadians - π/2)).y;

double GetTerrainHeight(bool clampToWater)
    => Height - planet.GetTerrainHeightAtAngle(position.AngleRadians, clampToWater);

Double2 GetSolarSystemPosition(double time)
    => position + planet.GetSolarSystemPosition(time);
```

- **`Height` is altitude above the datum radius, not above terrain.**
  `GetTerrainHeight` is the above-ground-level figure, and its
  `clampToWater` flag passes straight through to
  `Planet.GetTerrainHeightAtAngle` — pass `true` to treat sea level as
  the floor over water. **Per-angle terrain is reachable from a plain
  `Location` with no extra plumbing.**
- **`VerticalVelocity` is the radial component**: rotating by `π/2 − θ`
  maps the outward radial direction onto `+y`, so `.y` is the climb rate.
  Signed, positive outward.

### Methods

#### .ctor(double time, Planet, Double2 position, Double2 velocity)

#### .ctor(Planet, Double2 position, Double2 velocity = default)

- **Access:** public instance
- **Gotchas:** two.
  1. **Both constructors run every component through `CheckNaN`**
     @160874, which is `double.IsNaN(a) ? 0.0 : a`. **NaN silently
     becomes zero** — a craft whose physics blew up reports a
     valid-looking position at the planet's centre rather than
     propagating NaN. **Do not treat a `Location` as evidence that the
     numbers upstream were sane.**
  2. **The two-argument constructor sets `time = -1.0`**, so a
     `Location` built that way is not usable for anything time-dependent
     (`GetSolarSystemPosition` would evaluate at t = −1).
  - The pair is an **ambiguous overload set** — catalogued in
    [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
- **Status:** [CONFIRMED]

#### op_Addition(Location a, Location b) -> Location

- **Access:** public static · IL @160891
- **Gotchas:** composes `b.time` / `b.planet` with summed positions —
  **not a symmetric operation.** Read the body before using it.
- **Status:** [OPEN] — body not read

---

## WorldLocation

**Namespace:** SFS.World
**Kind:** class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @160568 · 4 methods / 3 fields

The **live, observable** form — what `Player.location` holds.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `planet` | `SFS.Variables.Planet_Local` | public | no | an `Obs<Planet>` — subscribable | [CONFIRMED] |
| `position` | `SFS.Variables.Double2_Local` | public | no | `Obs<Double2>` | [CONFIRMED] |
| `velocity` | `SFS.Variables.Double2_Local` | public | no | `Obs<Double2>` | [CONFIRMED] |

**There is no `time` field.**

### Methods

#### get_Value() -> Location

- **Access:** public instance · IL @160599
- **Returns:** a **freshly constructed copy**
- **Behavior:**
  ```csharp
  Location get_Value() => new Location(
      WorldTime.main != null ? WorldTime.main.worldTime : 0.0,
      planet, position, velocity);          // via Obs<T>.op_Implicit
  ```
- **Gotchas:** the returned `Location` is **stamped with the current
  world time at the moment of the read**, and **is a copy** — mutating it
  does nothing to the craft.
- **Status:** [CONFIRMED]

#### set_Value(Location value) -> void

- **Access:** public instance · IL @160629
- **Behavior:**
  ```csharp
  if (value == null || value.planet == null) return;   // no-op, no throw
  planet.Value   = value.planet;
  position.Value = value.position;
  velocity.Value = value.velocity;
  ```
- **Side effects:** fires the three `Obs<T>` change chains.
- **Gotchas:** **a teleport with a null planet fails silently.** If an
  agent sets a craft's location and nothing moves, this guard is the
  first thing to check — **there is no exception and no log line.**
- **Status:** [CONFIRMED] · [UNTESTED-LIVE] as a teleport

#### get_Height() -> double

- **Access:** public instance · IL @160576
- **Behavior:** duplicates `Location.Height` against the live values, so
  altitude is readable **without allocating a `Location`**.
- **Status:** [CONFIRMED]

---

## Double2

**Namespace:** *(none — top-level, global namespace)*
**Kind:** struct (`sequential`, `sealed`, `serializable`)
**Extends:** System.ValueType
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @180 · 48 methods / 2 fields

**Global namespace — not under `SFS.`.** `FindType("Double2")` is the
correct lookup; `SFS.Double2` returns null.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `x` | `double` | public | no | | [CONFIRMED] |
| `y` | `double` | public | no | | [CONFIRMED] |

> **It is a struct**, so reflection `GetValue` boxes a **copy** — writing
> `x` on the boxed result changes nothing. **To move a craft you must
> construct a new `Double2` and assign the whole value.**

### Methods

Bodies read and confirmed:

```csharp
double AngleRadians => Math.Atan2(y, x);
double AngleDegrees => Math.Atan2(y, x) / 6.283185307179586 * 360.0;
double magnitude, sqrMagnitude          // the obvious ones
bool Mag_MoreThan(double a) => sqrMagnitude >  a * a;
bool Mag_LessThan(double a) => sqrMagnitude <  a * a;

Double2 Rotate(double angleRadians) {    // standard CCW rotation
    double c = Math.Cos(angleRadians), s = Math.Sin(angleRadians);
    return new Double2(x * c - y * s, x * s + y * c);
}
```

- **`Mag_MoreThan` / `Mag_LessThan` avoid the square root** — and both
  are **strict** (`cgt` / `clt`), so a speed exactly at the threshold
  *passes* the timewarp check in
  [`Rocket.md`](Rocket.md).
- **`AngleRadians` is `Atan2(y, x)`** — **0 is +x, increasing
  counter-clockwise**. This is the convention `AeroModule` subtracts π/2
  from to get "up-relative" angles.
- **`op_Equality` @783 is exact `double` comparison** on both components,
  **with no epsilon**. Two positions computed by different routes will
  essentially never compare equal; use `Mag_LessThan` on the difference.

**Statics worth knowing:** `Dot`, `Angle`, `SignedAngle`, `Reflect`,
`Lerp(a, b, t)`, `CosSin(angleRadians)` and `CosSin(angleRadians, radius)`
— the last is the direct **polar→cartesian constructor**, which is what
you want for "put the craft at angle θ, radius r".

**Conversions:** implicit `Double2 → Vector2` and `Double2 → Vector3`;
explicit `Vector2 → Double2` and `Double3 → Double2`; plus the properties
`ToVector2` / `ToVector3` and the statics `ToDouble2(Vector2)` /
`ToDouble2(Vector3)`. **Prefer the properties** — the two `op_Implicit`
overloads differ **only in return type** and are unresolvable through
`GetMethod(name, Type[])`. See
[`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1, which also
lists `op_Addition`, `op_Subtraction`, `op_Multiply`, `ToDouble2`,
`CosSin`, `Equals` and `op_Explicit` as ambiguous sets on this type.

#### ToParsableString() / Parse(string) — **do not round-trip**

**[CONFIRMED].**

```csharp
string ToParsableString() => string.Format("{0}:{1}", x, y);   // 2 fields

static Double2 Parse(string text) {                            // reads [1] and [2]
    var p = text.Split(':', StringSplitOptions.None);
    return new Double2(double.Parse(p[1]), double.Parse(p[2]));
}
```

`Parse` indexes elements **1 and 2**, so it needs a three-part string,
while `ToParsableString` emits two. **`Double2.Parse(v.ToParsableString())`
throws `IndexOutOfRangeException`.** Neither method is called anywhere in
`Assembly-CSharp` (`grep` finds only their own `end of method` lines), so
this is **dead code the game never exercises** — but do not reach for it
as a serialisation helper. The save format uses Newtonsoft on the fields
directly.

---

## Which one to read, in practice

| You want | Read |
|---|---|
| live altitude | `rocket.location.Height` (no allocation) |
| a consistent snapshot to compute against | `rocket.location.Value` — copies, stamps `time` |
| altitude above ground | `location.Value.GetTerrainHeight(clampToWater)` |
| climb rate | `location.Value.VerticalVelocity` |
| to move the craft | `rocket.location.Value = new Location(...)` — **planet must be non-null** |
| to react to a change | subscribe to `rocket.location.position` (`Obs<Double2>`) |
| centre-of-mass position in Unity space | `((I_Physics)rocket).LocalPosition` — a **different quantity** |

### Two frame/clock traps

- **`rb2d.linearVelocity` is not world velocity.** It is expressed in the
  floating *velocity* frame (see
  [`../12-world-scene-timewarp/WorldView.md`](../12-world-scene-timewarp/WorldView.md)),
  so comparing it to `location.velocity` without
  `WorldView.ToGlobalVelocity` is wrong. Use `location.Value.velocity`
  (a `Double2`) for anything world-frame.
- **`Location.time` and Unity's `Time.timeSinceLevelLoad` are different
  clocks.** `Location.time` comes from `WorldTime.main.worldTime`, which
  advances at the timewarp rate and persists across saves. **Never
  cross-reference the two.**

## Status summary

| Item | Status |
|---|---|
| `Location` field layout, planet-relative | [CONFIRMED] |
| `Radius` / `Height` / `VerticalVelocity` / `GetTerrainHeight` bodies | [CONFIRMED] |
| `Height` is above datum, not terrain | [CONFIRMED] |
| Constructors coerce NaN → 0 | [CONFIRMED] |
| 2-arg ctor sets `time = -1` | [CONFIRMED] |
| `WorldLocation` has no `time`; synthesises from `WorldTime.main` | [CONFIRMED] |
| `set_Value` silently no-ops on null planet | [CONFIRMED] |
| `Double2` is a global-namespace struct | [CONFIRMED] |
| `Rotate`, `Mag_MoreThan/LessThan` (strict) bodies | [CONFIRMED] |
| `AngleRadians` = `Atan2(y, x)`, 0 = +x, CCW | [CONFIRMED] |
| `op_Equality` is exact, no epsilon | [CONFIRMED] |
| `op_Implicit` unresolvable by parameter types | [CONFIRMED] |
| `ToParsableString` / `Parse` mismatch; both uncalled | [CONFIRMED] |
| `Location.op_Addition` semantics | [OPEN] — body not read |
| `GetSolarSystemPosition` / `Planet.GetSolarSystemPosition` bodies | [OPEN] |
| Teleport via `set_Value` | [UNTESTED-LIVE] |
| `Double3`, `Planet_Local`, `Double2_Local` own entries | [OPEN] — Step 2 |
