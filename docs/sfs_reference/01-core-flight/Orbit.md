# `SFS.World.Orbit` — orbital elements from a state vector

**Migrated** from `docs/sfs_source_reference.md` §B5.3 and §B5.3.1
(2026-08-28).

> **Correction made during migration.** The old file's §B5.5 status table
> still listed the encounter search (`FindEncounters` etc.) as
> **[PARTIAL]**, but §B5.3.1 was a later depth pass that read those
> bodies. **They are CONFIRMED apart from two explicitly-noted
> fragments**; the blanket [PARTIAL] row was stale.

The library it composes: [`Kepler.md`](Kepler.md). The chain it lives in:
[`Trajectory.md`](Trajectory.md).

---

## Orbit

**Namespace:** SFS.World
**Kind:** class
**Extends:** System.Object
**Implements:** `SFS.World.I_Path`
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @192745 · 34 methods / 21 fields

### Element derivation

The interesting constructor is
`Orbit(Location location, bool calculateTimeParameters, bool calculateEncounters)`
@192871; `TryCreateOrbit(location, …, out bool success)` @192777 is the
non-throwing wrapper. Body transcribed:

```csharp
orbitStartTime = location.time;
Double3 h = Double3.Cross(location.position, location.velocity);      // angular momentum
Double2 eVec = (Double2)(Double3.Cross((Double3)location.velocity, h)
                         / location.planet.mass)
             - location.position.normalized;                          // eccentricity vector
ecc = eVec.magnitude;
sma = location.planet.mass
    / -(2.0 * (Math.Pow(location.velocity.magnitude, 2.0) / 2.0
               - location.planet.mass / location.Radius));            // vis-viva
semiMinorAxis = Kepler.GetSemiMinorAxis(sma, ecc);
periapsis     = Kepler.GetPeriapsis(sma, ecc);
apoapsis      = Kepler.GetApoapsis(sma, ecc);
arg           = eVec.AngleRadians;
arg_Matrix    = Matrix2x2_Double.Angle(arg);
slr           = Kepler.GetSemiLatusRectum(periapsis, ecc);            // NB: from periapsis
direction     = Math.Sign(h.z);
bool escapes  = apoapsis >= location.planet.SOI;
trueAnomaly_Out = Kepler.NormalizeAngle(location.position.AngleRadians - arg);
location_Out    = location;
if (calculateTimeParameters) {
    period     = escapes ? 0.0 : Kepler.GetPeriod(sma, location.planet.mass);
    meanMotion = Kepler.GetMeanMotion(sma, location.planet.mass);
    ...
}
```

### Three traps in this body

> **1. `Planet.mass` is the standard gravitational parameter μ = GM, not
> a mass in kilograms.** Confirmed three independent ways: the vis-viva
> expression above divides it by radius to get a specific energy;
> `Kepler.GetPeriod(sma, mass) = τ·√(sma³/mass)`; and
> `Kepler.GetMass(g, r) = g·r²`. **Treating `Planet.mass` as kilograms —
> or multiplying it by G — is wrong by ~10¹⁰.**
>
> This is not a new finding: `sfs_physics_reference.md` §2.1 already
> states "μ is read directly from `Planet.mass`", validated to
> 0.008–0.13% against live gravity. The three IL derivations are
> independent confirmation from code rather than measurement, extended to
> the orbital-element path. The trap is restated only because the field's
> *name* invites the wrong reading.

> **2. `period` is `0.0` for any orbit whose apoapsis reaches the SOI**,
> including every hyperbolic and every escape trajectory. It is **not**
> `Infinity` and not a small number — **code that divides by `period`
> gets a division by zero.**

> **3. `slr` is computed from periapsis, not from `sma`**
> (`GetSemiLatusRectum(p, e) = p·(1 + e)`). **Passing `sma` there is a
> silent error.**

### Position and velocity sampling

All public:

```csharp
Double2 GetPositionAtAngle(double angleRadians);
Double2 GetPositionAtTrueAnomaly(double trueAnomaly);
Double2 GetVelocityAtAngle(double angleRadians);      // => GetVelocityAtTrueAnomaly(angle - arg)
Double2 GetVelocityAtTrueAnomaly(double trueAnomaly);
Double2 GetPositionFromEccentricAnomaly(double E);    // branches on ecc < 1: cos/sin vs cosh/sinh
Location GetLocation(double time);                    // I_Path
double   GetTrueAnomaly(double time);
double   GetNextAnglePassTime(double time, double angleRadians);
double   GetLastAnglePassTime(double time, double angleRadians);
double   GetNextTrueAnomalyPassTime(double time, double trueAnomaly);
double   GetLastTrueAnomalyPassTime(double time, double trueAnomaly);
```

`GetVelocityAtTrueAnomaly` @194559 composes the library directly:

```csharp
double r = Kepler.GetRadiusAtTrueAnomaly(slr, ecc, trueAnomaly);
double E = Kepler.GetEccentricAnomalyFromTrueAnomaly(trueAnomaly, ecc);
return Kepler.GetVelocity(sma, r, meanMotion, E, ecc, arg, direction);
```

`GetPositionFromEccentricAnomaly` @194453 **handles hyperbolic orbits** —
`ecc < 1` uses `(cos E − e)·sma, sin E·semiMinorAxis`; otherwise the
`cosh`/`sinh` branch with negated axes. **So escape trajectories are
first-class, not an error case.**

> **`GetNextAnglePassTime` / `GetLastAnglePassTime` are the direct answer
> to "when will I be at this point in the orbit"** — the primitive a
> manoeuvre planner needs, already written and already correct for the
> game's own model.

### Other fields

`orbitStartTime` / `orbitEndTime`, `pathType` (`SFS.World.PathType` —
`Eternal=0, Escape=1, Encounter=2`), `periapsisPassageTime`, and an
`encounterText` `Func<string>`.

`private static Dictionary<int, Vector3[]> ellipseCache` and the
`GetPoints*` family are **map rendering, not physics** — [OPEN].

---

## The encounter search

**[CONFIRMED]** — four methods, outermost first.

#### UpdateEncounters() -> bool

- **Access:** public instance · IL @194999, body read
- **Behavior:**
  ```csharp
  if (pathType != PathType.Eternal) return false;     // already resolved
  double start = Math.Max(orbitStartTime, WorldTime.main.worldTime);
  double end   = start + period * 0.9;
  return FindEncounters(start, end);
  ```
- **Gotchas:** **only `Eternal` orbits are searched** — one already
  carrying an `Escape` or `Encounter` is left alone. The window is **0.9
  of one period**, not a full period, so a search never wraps past its
  own start. Note `period` is `0.0` for SOI-escaping orbits, but those
  are never `Eternal`, so the degenerate zero-length window is
  unreachable — **the two facts are consistent, not a latent bug.**
- **Status:** [CONFIRMED]

#### FindEncounters(double window_Start, double window_End) -> bool

- **Access:** private instance · IL @195035, body read
- **Behavior:**
  ```csharp
  foreach (Planet sat in location_Out.planet.satellites) {
      if (apoapsis  > sat.orbit.periapsis - sat.SOI + 0.1 &&
          periapsis < sat.orbit.apoapsis  + sat.SOI - 0.1) {
          if (ProcessEncounters(sat, window_Start,
                                Math.Min(window_End, orbitEndTime))) return true;
      }
  }
  return false;
  ```
- **Gotchas:** a **radial-overlap pre-filter** — unless the craft's
  annulus (`periapsis`…`apoapsis`) overlaps the satellite's swept band
  (`sat.orbit.periapsis − SOI` … `sat.orbit.apoapsis + SOI`), the
  satellite is skipped without any iteration. The `± 0.1` is the class's
  `private const double Margin = 0.1` used as a **shrink**, i.e. a
  **conservative** filter that can reject a grazing case. **First hit
  wins** — satellites are tested in array order, and the search returns
  on the first success rather than picking the earliest encounter.
- **Status:** [CONFIRMED]

#### ProcessEncounters(Planet satellite, double window_Start, double window_End) -> bool

- **Access:** private instance · IL @195112, body read
- **Behavior:**
  ```csharp
  double maxAcceleration = 2.0 * location_Out.planet.GetGravity(
                                     satellite.orbit.periapsis - satellite.SOI);
  double time = window_Start;
  for (int i = 0; i < 100; i++) {
      if (time >= window_End) return false;
      if (GetFastestPossibleArrivalTime(ref time, satellite, maxAcceleration)) {
          SetEncounter(satellite, time, <>c.b__56_0);   // encounterText
          return true;
      }
  }
  return false;
  ```
- **Gotchas:** **a bounded iterative advance, capped at 100 steps**
  (`ldc.i4.s 0x64`). `maxAcceleration` is **twice** the parent's gravity
  at the satellite's closest approach radius — a deliberate
  over-estimate, which is what makes each step a **safe lower bound** on
  arrival time rather than a guess.

  **Two failure modes are silent and indistinguishable from "no
  encounter":** running past `window_End`, and exhausting the 100
  iterations. **An agent cannot tell "no encounter exists" from "the
  search gave up" from the return value alone.**
- **Side effects:** on success calls the public `SetEncounter`, which
  sets `pathType`, `orbitEndTime` and `encounterText`.
- **Status:** [CONFIRMED]

#### GetFastestPossibleArrivalTime(ref double time, Planet satellite, double maxAcceleration) -> bool

- **Access:** private instance · IL @195183
- **Behavior:**
  ```csharp
  Double2 craftPos = GetLocation(time).position;

  // (a) inside the satellite's inner exclusion radius -> skip ahead by orbit geometry
  if (craftPos.Mag_LessThan(satellite.orbit.periapsis - satellite.SOI + 0.1)) {
      double t = GetNextTrueAnomalyPassTime(time,
          Kepler.GetTrueAnomalyAtRadius(this, satellite.orbit.periapsis - satellite.SOI)
          * direction);
      if (t == time) t += 1.0;                    // guard against a stuck step
      time = t; return false;
  }
  // (b) outside the outer radius -> symmetric skip (same shape, apoapsis + SOI)
  ...
  // (c) in the band: measure the real approach
  Double2 rel      = satellite.GetLocation(time).position - craftPos;
  Double2 relVel   = satellite.GetLocation(time).velocity - GetLocation(time).velocity;
  double  closing  = relVel.Rotate(-rel.AngleRadians).x;   // component along the line
  double  gap      = rel.magnitude - satellite.SOI;

  if (gap < 0.1 && closing < 0.0) return true;             // arrived, and approaching
  time += GetFallTime(closing, gap, maxAcceleration);
  ...
  return false;
  ```
- **Gotchas:** `closing` is obtained by rotating the relative velocity by
  minus the relative-position angle and taking `.x` — the component
  **along the line joining the two bodies**. Negative means closing.
- **Status:** [CONFIRMED] for branches (a) and (c) · **[PARTIAL]** — the
  fragments marked `...` (branch (b), and the tail after the
  `GetFallTime` advance) were not transcribed instruction-by-instruction;
  structure and constants confirmed, exact bounds arithmetic on the
  outer-radius branch is unread

#### GetFallTime(double verticalVelocity, double startHeight, double gravity) -> double

- **Access:** private instance · IL @195410, body read
- **Behavior:**
  ```csharp
  => Math.Sqrt((startHeight + verticalVelocity * verticalVelocity / (2.0 * gravity))
               * 2.0 / gravity)
   + verticalVelocity / gravity;
  ```
- **Gotchas:** constant-acceleration time-to-close from `startHeight`
  with initial separation rate `verticalVelocity`. With `gravity`
  deliberately **over**-estimated in `ProcessEncounters`, this returns a
  time **no later than** the true arrival — so advancing by it can never
  step past an encounter. **That is the invariant the whole search rests
  on.**
- **Status:** [CONFIRMED]

> **For an agent:** the search is a conservative forward stepper over one
> 0.9-period window per `Eternal` orbit, per satellite, capped at 100
> steps, returning the **first** satellite that works. It is cheap enough
> to call, but it answers **"is there an encounter on this conic"** —
> **not** "what is the best transfer". **Do not mistake
> `UpdateEncounters` for a manoeuvre planner.**

## Status summary

| Item | Status |
|---|---|
| `Orbit(Location, …)` element derivation | [CONFIRMED] |
| **`Planet.mass` is μ = GM, not kilograms** | [CONFIRMED] — three ways |
| `period == 0.0` for SOI-escaping orbits | [CONFIRMED] |
| `slr` derives from periapsis, not sma | [CONFIRMED] |
| Hyperbolic orbits handled (`cosh`/`sinh` branch) | [CONFIRMED] |
| `GetVelocityAtTrueAnomaly` composes `Kepler` directly | [CONFIRMED] |
| `UpdateEncounters` / `FindEncounters` / `ProcessEncounters` bodies | [CONFIRMED] |
| `GetFallTime` and the over-estimated-gravity invariant | [CONFIRMED] |
| `GetFastestPossibleArrivalTime` outer-radius branch and tail | [PARTIAL] |
| `GetNextAnglePassTime` / `GetLastAnglePassTime` bodies | [OPEN] — signatures confirmed |
| `GetPoints*` / `ellipseCache` (map rendering) | [OPEN] |
| Calling `Orbit` from the probe | [UNTESTED-LIVE] |
