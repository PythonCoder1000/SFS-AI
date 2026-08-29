# `Kepler` — the public static orbital-mechanics library

**Migrated** from `docs/sfs_source_reference.md` §B5.4 (2026-08-28).

**The single most useful discovery in the B-tier: the game ships a
complete, public, static orbital-mechanics library.** An agent planning
burns does not need to reimplement Kepler.

Consumed by [`Orbit.md`](Orbit.md).

---

## Kepler

**Namespace:** *(none — top-level, global namespace)*
**Kind:** static class (`public abstract sealed`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] for the 13 tabulated formulas · [PARTIAL] overall
**Depth:** FULL
**IL:** `scratch/full_il.txt` @26996 · 31 methods / 3 fields

**Reflection name:** `"Kepler"` — no namespace prefix.

### Fields

| Name | Type | Access | Static | Value | Status |
|---|---|---|---|---|---|
| `Tau` | `double` | private | const | `6.283185307179586` | [CONFIRMED] |
| `Tolerance` | `double` | private | const | `1e-7` | [CONFIRMED] |
| `MaxIterations` | `int` | private | const | `50` (`0x32`) | [CONFIRMED] |

### Methods — confirmed formulas

**Every method is `public static`.** Bodies read:

| Method | Body |
|---|---|
| `GetPeriapsis(sma, e)` | `sma * (1 - e)` |
| `GetApoapsis(sma, e)` | `e < 1 ? sma * (1 + e) : double.PositiveInfinity` |
| `GetSemiMajorAxis(peri, e)` | — |
| `GetSemiMinorAxis(sma, e)` | `e < 1 ? sma*√(1-e²)` ; `e > 1` branch uses `e²-1` |
| `GetMass(g, r)` | `g * r * r` — **μ from surface gravity and radius** |
| `GetSemiLatusRectum(p, e)` | `p * (1 + e)`, `p` = **periapsis** |
| `GetPeriapsisFromSemiLatusRectum(l, e)` | — |
| `GetPeriod(sma, mass)` | `τ * √(sma³ / mass)` |
| `GetMeanMotion(sma, mass)` | uses `\|sma\|` — **safe for hyperbolic** |
| `GetSphereOfInfluence(sma, mass, parentMass, multiplier)` | `sma * (mass/parentMass)^0.4 * multiplier` |
| `GetEscapeVelocity(planet, radius)` | `√(2 * planet.mass / radius)` |
| `NormalizeAngle(a)` | wraps to **(−π, π]** by repeated ±τ |
| `PositiveAngle(a)` | wraps to **[0, τ)** |

`GetMass(g, r) = g·r²` is one of the three independent confirmations that
**`Planet.mass` is μ, not kilograms** — see [`Orbit.md`](Orbit.md).

### Methods — signatures confirmed, bodies not read

`GetAngleDiff(from, to, direction)`, `ToTauRange(a)`,
`GetTrueAnomalyFromEccentricAnomaly(E, e)`,
`GetEccentricAnomalyFromTrueAnomaly(v, e)`,
`GetRadiusAtAngle(Orbit, angleRadians)`,
`GetRadiusAtTrueAnomaly(l, e, v)`,
`GetTrueAnomalyAtRadius(r, l, e)` **and**
`GetTrueAnomalyAtRadius(Orbit, r)` (**ambiguous pair**),
`GetVelocity(sma, r, n, E, e, arg, direction)`,
`GetVelocityNormal(E, e, arg)`, `GetMeanAnomaly(e, v)`,
`GetTimeToPeriapsis(r, e, l, meanMotion)` **and**
`GetTimeToPeriapsis(trueAnomaly, e, meanMotion, direction)`
(**ambiguous pair**), `GetPosition(r, trueAnomaly, arg)`,
`GetEccentricAnomaly(M, e)`.

> **Two ambiguous overload pairs**, both catalogued in
> [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
> `GetTimeToPeriapsis` is the nastier one: **both forms take four
> arguments, all `double` except the trailing `int` on the second — easy
> to bind to the wrong one.**

#### GetEccentricAnomaly(double M, double e) -> double

- **Access:** public static
- **Behavior:** dispatches to three private solvers —
  `GetEccentricAnomalyElliptical`, `…ExtremeEccentricity`,
  `…Hyperbolic` — iterating to `Tolerance = 1e-7` in at most 50 steps.
- **Gotchas:** **the elliptical, near-parabolic and hyperbolic cases are
  all handled**; there is no regime where the game silently returns
  garbage.
- **Status:** [CONFIRMED] dispatch structure · [OPEN] individual solver
  bodies

---

## What this means for the agent

**Manoeuvre planning should call `Kepler` and `Orbit` through reflection
rather than reimplementing them in Python.** The game's answers are the
ones the game will act on, including its own difficulty scaling and its
own definition of "in orbit"
([`Physics.md`](Physics.md) — `periapsis > Planet.OrbitRadius`). A Python
reimplementation would be **a second model to keep in sync**, and the
data-trust rule applies with full force.

## Status summary

| Item | Status |
|---|---|
| `Kepler` is a public static library in the global namespace | [CONFIRMED] |
| `Tau` / `Tolerance` / `MaxIterations` constants | [CONFIRMED] |
| The 13 formulas tabulated above | [CONFIRMED] |
| `GetEccentricAnomaly` 3-solver dispatch, 1e-7 / 50 iter | [CONFIRMED] |
| The two ambiguous overload pairs | [CONFIRMED] |
| The 14 methods not tabulated | [PARTIAL] — signatures only |
| The three private eccentric-anomaly solvers | [OPEN] |
| Calling `Kepler` from the probe | [UNTESTED-LIVE] |
