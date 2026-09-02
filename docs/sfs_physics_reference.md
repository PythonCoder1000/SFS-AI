# SFS Physics Reference

What's confirmed about SFS's actual physics, and what isn't. Companion
document: `sfs_source_reference.md` (how to reach any of this via code —
class names, method signatures, reflection patterns). Progress tracking
against the project's Tier 1 checklist lives in `high_level_checklist.md`.

Target build: **Spaceflight Simulator 1.6.00.16**, Steam, macOS, Unity
6000.1.17f1, Mono (not IL2CPP). Every value below is tied to this exact
build — pin it before relying on any of this.

**Confidence tags:**
- **[CONFIRMED]** — read from real IL disassembly and/or empirically
  validated against live telemetry, typically well under 0.1% error.
- **[PARTIAL]** — the law/mechanism is known; a specific value, edge case,
  or piece of the pipeline is not.
- **[OPEN]** — genuinely unknown, not yet investigated or blocked on
  something else.

---

## 1. Confirmed values

### 1.1 Planetary constants — [CONFIRMED], all 40 bodies

Earth, verified in detail:
```
Radius              314,970 m
mass (μ)            972,219,788,820  (μ/R² = 9.800 exactly)
SOI                 119,243,724 m
AtmosphereHeightPhysics   30,000 m
```
Atmosphere density inputs (Earth): `ρ0 = 0.005`, `curve = 10`. Only 9 of
the 40 bodies have an atmosphere at all; only Earth has oxygen. SOI is
computed at runtime, not stored in the planet JSON — only reachable live.

> **CORRECTION (source-doc pass, `session-2026-08-27-sfs_source_code_docs.md`):**
> every number in this block is **difficulty-scaled**, and the block does
> not record which difficulty it was measured on.
> `Difficulty.ScalePlanetData` mutates `PlanetData` **once at load**,
> scaling radius, gravity, SOI, semi-major axis, atmosphere height *and*
> atmosphere curve. Confirmed multipliers, indexed
> `Normal=0, Hard=1, Realistic=2`: `defaultPlanetScales [1, 2, 20]`,
> `defaultAtmosphereScales [1, 1.667, 3.333]`,
> `defaultAtmosphereCurveScales [1, 1.5, 3]`,
> `defaultDistanceScales [1, 2, 20]`.
> **Live reads are already scaled and correct; the JSON on disk is not.**
> Treat the values above as a Normal-difficulty snapshot unless
> re-measured. See `sfs_source_reference.md` §D4.2 and §D1.5.

### 1.2 Part constants — [CONFIRMED] for exactly one engine, everything
else [PARTIAL]

**Rule: never trust a part constant unless read live from the running
game.** Static extraction and community/wiki data have both been
repeatedly, specifically wrong — Titan mass, Hawk thrust and ISP, and
others all disagreed with live-game reads by 10–20%+.

Live-verified, Hawk Engine, placed and flown:
```
mass       3.5 t
thrust     120  (tonnes-force)
ISP        240
```
Part masses are **parametric expressions** (e.g. a nose cone's mass field
is literally the string `"size * 0.05"`), resolved only at runtime once a
part is placed and its variables are bound.

> **CORRECTION (source-doc pass):** the claim that "no Python-side
> evaluator exists for this" is superseded — **the game ships its own
> expression compiler, and it is public.** `Part.mass` is a
> `SFS.Variables.Composed_Float` holding the expression string in a
> public `input` field; reading `.Value` compiles it via the public
> static `SFS.Parsers.Constructed.Compute.Compile(string,
> VariablesModule, out List<string>)` and returns the number. **The probe
> has been getting correct parametric masses all along** — reading
> `.Value` was never the problem.
>
> This also *explains* the rule at the top of this section rather than
> just restating it: an expression is only meaningful against a bound
> `VariablesModule`, which does not exist for a part sitting in an asset
> file. That is precisely why static extraction gave the wrong Titan mass
> and wrong Hawk thrust/ISP. The rule stands unchanged; the reason is now
> known. See `sfs_source_reference.md` §E4.

### 1.3 Physics constants — [CONFIRMED]

```
Fuel-flow rate formula:    thrust · scale · throttle / (ISP · ispMultiplier)
ispMultiplier (Normal difficulty):  1.0000  (to 0.002%)
Adaptive timestep range:   clamp(real Δt, 1/60, 1/15) seconds
Physics-warp rates:        1x, 2x, 3x, 5x
Rails-warp rates:          1, 5, 25 × 100^n
CanTimewarp thresholds:    0.1 m/s on land, 3.0 m/s in water
Build-grid rounding:       0.5-unit increments
```

> **CORRECTION (source-doc pass) — fuel flow has a fourth term.**
> `EngineModule.RecalculateMassFlow` computes
> `thrust · scale · throttle_Out / (ISP · IspMultiplier)`, where
> `scale = transform.TransformVector(thrustNormal.Value).magnitude`.
> It is **exactly 1.0 for an unscaled part**, which is why the empirical
> check still passed to 0.002% — but it is *not* 1.0 for a scaled one, so
> a Python reimplementation must include it. See
> `sfs_source_reference.md` §D2.3.
>
> Independent confirmation from the same pass: `ispMultipliers` is a
> literal `[1.0, 1.0, 1.5]` by difficulty in `Difficulty`'s constant
> table, matching the measured 1.0000 on Normal exactly.

> **CORRECTION (source-doc pass) — the two warp ladders are confirmed,
> but they scale different quantities.** Both rate tables above are
> exactly right (decoded from the `<PrivateImplementationDetails>` init
> blobs: physics `[1,2,3,5]`; rails `rails[i%3] · 100^(i/3)` from
> `[1,5,25]`). What the table does not say is that the two modes are
> mechanically different:
>
> - **Physics warp** (`WorldTime.realtimePhysics == true`) raises Unity's
>   `Time.timeScale`. Everything is still simulated, just faster in real
>   time. Step size is unchanged.
> - **Rails warp** (`realtimePhysics == false`) leaves `timeScale` at 1
>   and multiplies `WorldTime.FixedDeltaTime` instead — the world steps
>   analytically in large chunks, and drag, heating and mass
>   recalculation are all gated off.
>
> Consequence: **`WorldTime.FixedDeltaTime` and Unity's
> `Time.fixedDeltaTime` are not interchangeable.** They agree only at
> 1×. `HeatManager` uses the former; `Rocket.ApplyTorque` uses the
> latter. This is why "safe timewarp ceiling" is a **per-mode** question,
> not a single number — see `high_level_checklist.md`. Also note
> `WorldTime.SetState(speed, realtimePhysics, showMsg)` is public and
> validates nothing. See `sfs_source_reference.md` §E5.1.

---

## 2. Confirmed formulas

### 2.1 Gravity — [CONFIRMED], 0.008–0.13% error

```
g(r) = μ / r²
F(r) = -μ/r² · r̂ · m
```
`μ` is read directly from `Planet.mass`. For tangential velocity, apoapsis/
periapsis need the full 2D radial equation
(`d²r/dt² = -μ/r² + L²/r³`) — the naive 1D vertical free-fall equation
produced an apparent 43% "error" that vanished once corrected.

> **CORROBORATED (source-doc pass) — no change.** `Planet.mass` being μ
> rather than a mass in kilograms is now confirmed a second way, from
> code: `Orbit`'s constructor divides it by radius to get a specific
> energy, `Kepler.GetPeriod(sma, mass) = τ·√(sma³/mass)`, and
> `Kepler.GetMass(g, r) = g·r²`. Recorded because the field's *name*
> invites the wrong reading. See `sfs_source_reference.md` §B5.3.

### 2.2 Thrust — [CONFIRMED], 0.4% error

```
F = thrustNormal · thrust · 9.8 · throttle_Out
```
The `9.8` is a fixed tonnes-force conversion constant, unrelated to any
specific planet's surface gravity. Throttle response is instant, no ramp:
`throttle_Out = engineOn ? throttle_Input : 0`. Three independent control
layers: amount (`throttlePercent`), which engines (`engineOn`, per
engine), master start (`throttleOn`).

### 2.3 Drag — force law [CONFIRMED], `dragArea` [CONFIRMED, live-tested
2026-08-28 — see §4]

```
F_drag = -v̂ · 1.5 · dragArea · |v|² · ρ(h)
CoP    = Σ(midpoint · weight) / dragArea     (weight = dx²/(dx+|dy|))
```
Force applied at `Lerp(CoM, CoP, 0.2)` — only 20% of the way toward true
CoP, an artificial stability damping the game applies.

> **REFINEMENT (source-doc pass) — two qualifications on the formula
> above.**
>
> 1. **`CalculateDragForce` culls segments with `dx < 0.01f`** before
>    accumulating. A reimplementation needs that exact threshold, not
>    just a windward sign check. (Already noted in §4; repeated here
>    because this is where the formula lives.)
> 2. **The `Lerp(CoM, CoP, 0.2)` step does not survive a parachute.**
>    `Aero_Rocket.ApplyParachuteDrag(ref float force, ref Vector2 cop)`
>    runs *after* the lerp and mutates **both** by reference. Parachute
>    drag is a separate, rotation-aware path: per chute it uses
>    `rb2d.GetPointVelocity(chute.position)` (so a spinning craft gives
>    each chute a different airspeed) converted via
>    `WorldView.ToGlobalVelocity`, squared, times an **`AnimationCurve`
>    evaluated at the deployment state** — partial deployment is a curve
>    lookup, not a linear ramp, and the curve is serialized data that
>    must be read live. **So §2.3 as written holds only for a rocket with
>    no parachutes.** See `sfs_source_reference.md` §E6.1.

Density:
```
ρ(h) = ( e^(-curve·h/H) - e^(-curve) ) · ρ0     for 0 ≤ h ≤ H
ρ(h) = 0                                         otherwise (hard cutoff)
```
Confirmed via IL and matches all 40 bodies' JSON inputs.

### 2.4 Rotation (player-commanded) — [CONFIRMED], 0.0006% error

```
angularVelocity -= turnAxis · (180/π) · torque_effective · Δt / mass
torque_effective = Σ(enabled TorqueModule.torque)
                    / (mass/200)^0.35    [only when mass > 200t]
```
Mass-based, not true moment-of-inertia — confirmed and validated in
vacuum (isolated from aero effects), only small (~0.1–0.5 deg/s)
mid-window noise consistent with ordinary integration noise.

> **CORROBORATED (source-doc pass) — formula unchanged.**
> `Rocket.ApplyTorque` writes `rb2d.angularVelocity` **directly** and
> never calls `AddTorque`, so the rigidbody's moment of inertia is never
> consulted — the empirical "mass-based, not true MoI" finding is exactly
> what the code does. The `(mass/200)^0.35` divisor and the rad→deg
> `57.29578` are both literals in the IL.
>
> One open detail: the IL compares `rb2d.mass > 200f` with **no unit
> conversion**, so the "200 t" reading above rests on this section's
> empirical validation, not on anything visible in the code. Worth
> re-checking if craft mass units ever matter elsewhere.
>
> Also newly known and *not* in the formula above: when `turnAxis` is
> zero the game substitutes SAS, which is **deadbeat, not PID** —
> `clamp(ω / one-tick-authority, ±1)`. It is disabled entirely while a
> turn key is held, while `hasControl` is false, or while `IsOnSurface`,
> and damped to 10% in water. See `sfs_source_reference.md` §B1.3.

### 2.5 Aerodynamic torque — [CONFIRMED], live-validated 2026-08-31

```
τ = (cop_applied − worldCenterOfMass) × F_drag        (2D cross product)
cop_applied = Lerp(worldCenterOfMass, cop_world, 0.2)  (same 20% damping as §2.3)
```
Where `cop_world` is `centerOfDrag` (§4/§2.3) rotated out of
velocity-aligned space into real world/scene coordinates via the
non-negated `Matrix2x2.Angle(velocityAngle − π/2)` — a rotation that was
confirmed via IL early in this project but never actually applied
anywhere in the probe until this validation (`dragCopX`/`Y` in
`truth.jsonl` are still raw velocity-frame values, not world space).
Unlike player-commanded rotation (§2.4), aero torque goes through
Unity's real `AddForceAtPosition`, so predicting the resulting angular
acceleration needs `rb2d.inertia` — Unity's own computed moment of
inertia, a stock property never read by this project before now.

**Live-validated 2026-08-31** on a real capsule+heat-shield reentry
(post-separation, hands off all manual controls). Across 12,174 clean
ticks (`inertia` stable, `output_TurnAxisTorque == 0` on both
endpoints): **correlation 0.9986** between predicted and real
finite-differenced angular acceleration. On the 117 ticks with
meaningful torque (|real α| > 5°/s²): **100% sign agreement**, magnitude
ratio (predicted/real) **0.985–1.011** at the largest swings, **median
error 4.66%**. Not quite this project's sub-1%-error gold standard, but a
real, solid confirmation — direction and magnitude both track.

> **The real finding of this validation wasn't the formula — it was what
> was fighting it.** Three earlier attempts (rows of chaotic, seemingly
> uncorrelated data) all had the same root cause: **SAS auto-engages
> the instant `hasControl && !IsOnSurface` and there's no manual turn
> input** (§2.4's deadbeat damping), which writes `angularVelocity`
> **directly**, completely bypassing inertia and the aero-torque model.
> "Hands off controls" is exactly the trigger condition for SAS, not the
> absence of it — releasing Q/E to get a clean aero-only test walks
> straight into the one condition that turns the game's own
> auto-stabilizer on. Filtering on raw `arrowkeys.turnAxis == 0` (what
> the player touched) is not sufficient; the correct filter is
> `Rocket.output_TurnAxisTorque == 0` — the actual applied value each
> tick, whichever source (player or SAS) produced it. On the validation
> flight, `output_TurnAxisTorque` was nonzero on 12,532 of 25,491 ticks;
> of those, 11,575 had zero manual input — i.e. SAS alone accounted for
> the overwhelming majority of non-aero angular acceleration in the
> data. This is not visible or labeled in-game (no SAS toggle exists in
> SFS the way it does in KSP-likes) — it's silent unless you're reading
> the field directly.

Probe support: `aerotorque` command (on-demand) and
`computed:aeroTorque` scoped-telemetry field, both added v0.49.0. See
`sfs_source_reference.md` §C1.10 for the reflection chain and
`TryComputeAeroTorque`.

**Known caveat, not yet handled:** invalid mid-parachute-deployment,
since `ApplyParachuteDrag` mutates force/cop by reference (§2.3) and
that mutation isn't replicated.

### 2.6 Mass model — [CONFIRMED], sub-gram precision

Total rocket mass is the plain sum of part masses, verified against
`rb2d.mass` to 5 decimal places on two different rockets.

> **MECHANISM (source-doc pass) — why it tracks, and one caveat.**
> `Rocket.UpdateMass()` runs **every** `FixedUpdate` and writes
> `rb2d.mass = mass.GetMass()` plus `rb2d.centerOfMass`, so `rb2d.mass`
> is always current as of the last physics tick and needs no
> recomputation. `Mass_Calculator.Calculate` is the plain mass-weighted
> centroid this section measured — with the detail that each part's local
> CoM is transformed by its `OrientationModule` first, so mirrored and
> rotated parts are handled.
>
> Mass follows fuel burn through an event chain, now confirmed end to
> end: `resourcePercent` write → `ResourceModule.RecalculateMass` →
> `Part.mass` (a `Composed_Float`) recompute → `Composed.onChange` →
> `Mass_Calculator.MarkDirty` → `rb2d.mass`. Nothing polls.
>
> **Caveat:** `MarkDirty` returns early while
> `WorldTime.realtimePhysics` is false, so **mass changes are ignored
> during rails timewarp**. Leaving timewarp re-marks dirty and repairs
> it, but a `GetMass()` read taken *during* warp can predate a mass
> change made while warping. Fuel is also stored as a **fraction**
> (`resourcePercent`), never an absolute quantity, and tank capacity is
> difficulty-scaled by `dryMassMultipliers [1.0, 1.0, 0.25]`. See
> `sfs_source_reference.md` §B6 and §E1.
>
> **Infinite fuel invalidates this section's premise.**
> `Flow.FlowNegative` opens with
> `if (SandboxSettings.main.settings.infiniteFuel) return;` — the cheat
> **skips consumption entirely** rather than refilling tanks, so
> `resourcePercent` never moves and **craft mass never drops**. That
> changes the trajectory, not just the endurance. Any validation run
> taken with infinite fuel on is a constant-mass vehicle and cannot be
> compared against a real burn.

### 2.7 Staging separation — [CONFIRMED], 0.003–0.006% error

The separator applies an internal impulse between the two resulting
pieces. Because it's internal, **total system momentum is conserved
regardless of the separator's force setting**, confirmed across two real
separation events. Angular velocity carries over unchanged to both pieces
at the instant of the split.

> **ADDITION (source-doc pass):** `DetachModule.separationForce` is a
> `Composed_Vector2`, i.e. a **parametric expression**, so separation
> impulse scales with part size the way mass does. Momentum conservation
> is unaffected (the impulse is internal either way), but a predictive
> model of the *velocities* after separation cannot treat the force as a
> constant. Splitting itself is pure graph work — `JointGroup` runs a
> stack-based flood fill over its adjacency index and counts connected
> components; no physics, geometry or distance test is involved. See
> `sfs_source_reference.md` §E3.2 and §E3.4.

### 2.8 Parachute drag — [CONFIRMED]

```
Aero_Rocket.ApplyParachuteDrag(ref float force, ref Vector2 cop):
  // force/cop arrive already computed by the normal path:
  //   force = dragArea * 1.5f * speedSq        (pre-direction, pre-density)
  //   cop   = Lerp(worldCenterOfMass, cop_world, 0.2f)   -- normal §2.3 Lerp,
  //           ALREADY applied before this runs (does NOT bypass it)
  foreach chute in rocket.GetModules<ParachuteModule>():
    if chute.targetState.Value not in {1, 2}: continue   // 0=stowed, no contribution
    chuteVel = ToGlobalVelocity(rb2d.GetPointVelocity(chute.parachute.position))
    chuteDrag = chuteVel.sqrMagnitude * chute.drag.Evaluate(chute.state.Value)
    cop = (cop * force + chute.parachute.position * chuteDrag) / (force + chuteDrag)
    force = force + chuteDrag
```

**One real correction to an earlier note:** the 2026-08-27 source-doc
pass said this "bypasses the §2.3 `Lerp(CoM, CoP, 0.2)` damping." That
was wrong — confirmed via the actual call site: the normal Lerp runs
FIRST, and this method further blends on top of that already-Lerp'd cop,
it doesn't skip it.

**Two things easy to get wrong in a reimplementation:**
1. **Rotation-aware, unlike everything else in the aero model.**
   `rb2d.GetPointVelocity` gives the true local velocity at the chute's
   own position (bulk velocity + ω×r), the one place in the whole
   confirmed aero chain that accounts for the craft's spin. The main
   body force/torque (§2.3/§2.5) never does — confirmed to have zero
   ω-dependence anywhere else.
2. **No density term of its own.** `chuteDrag` never gets multiplied by
   atmospheric density directly — it's added straight into the shared
   pre-density `force` scalar, which then gets density applied ONCE,
   uniformly, to the combined total back in `ApplyForce`. So the
   chute's contribution does end up density-scaled, just indirectly.

**Multiple deployed chutes compound sequentially** — each iteration's
weighted-average cop blend uses the *already-updated* `force` from the
previous chute in the loop, not the original pre-parachute value.
`targetState` values (1=partial/"safe", 2=full) inferred from the
adjacent `deploySound_Partial`/`deploySound_Fully` fields, not from a
named enum — `state`/`targetState` are both plain `Float_Reference`s.

Not yet live-validated — see `sfs_source_reference.md` §C1.11 for the
full IL and status.

---

## 3. Empirical noise floor

Roughly **0.006–0.03%** error across the clean single-force validation
tests, and **~0.008%** divergence between two nominally identical full
flights (mostly accumulating during unpowered coasting, not powered
flight — the burn phase itself reproduced to 0.5m/1.5ms out of a 23km/36s
burn). Any divergence threshold chosen for the observer/gate should clear
this floor by a comfortable margin, or it fires on noise, not real
problems.

---

## 4. `dragArea` — CONFIRMED, live-tested 2026-08-28

**Old plan (abandoned):** capture geometry via a Harmony patch on
`Part.InitializePart()`. Fully root-caused and abandoned — see
`docs/session-2026-08-27-*.md` for the chain. (Note: the specific
mechanism originally given for *why* Harmony failed — "the mod loader
preloads an old Harmony/MonoMod before any mod runs" — was itself found
to be unsupported on 2026-08-28: `Assembly-CSharp.dll` has zero
references to HarmonyLib/MonoMod. The real mechanism is almost certainly
weak-named-assembly path-probing order. Doesn't matter for dragArea,
which no longer needs Harmony at all — flagged here only so "no
non-invasive fix exists" isn't treated as settled if Harmony's ever
revisited for something else.)

**New path — confirmed live:** `dragArea` and center-of-pressure are
**directly callable**, no capture needed. `Aero_Rocket.GetDragSurfaces
(Matrix2x2)` → `AeroModule.GetExposedSurfaces(List<Surface>)` →
`AeroModule.CalculateDragForce(List<Surface>)` returns exactly
`(drag, centerOfDrag)` — confirmed via the method's own
`TupleElementNamesAttribute` metadata and by tracing the IL accumulation
logic against the formula in §2.3 above (`Σ dx²/(dx+|dy|)`, exact match).
Full call chain and exact reflection code: see `sfs_source_reference.md`
§C1, shipped as the `dragarea` probe command in v0.27.0.

> **CORRECTION (source-doc pass) — `AeroModule` is an abstract base
> class**, not the "per-part-module level" of drag as an earlier pass
> described it. Its `GetDragSurfaces(Matrix2x2)` is `protected abstract`
> with **no body**; `Aero_Rocket` and `Aero_Astronaut` are the
> subclasses. There is no per-part drag module — **drag is computed for a
> whole `PartHolder` at once.** Two further reflection traps on this
> chain: `GetDragSurfaces` has **two overloads** (protected instance
> `(Matrix2x2)` and public static `(PartHolder, Matrix2x2)`) and throws
> `AmbiguousMatchException` under a plain name lookup; and the rotation
> matrix passed in is **not identity** — it is derived from the velocity
> angle, and there are **two** of them
> (`a = (float)location.velocity.AngleRadians − π/2`, with
> `Matrix2x2.Angle(−a)` going into `GetDragSurfaces` and
> `Matrix2x2.Angle(+a)` into `ApplyForce`/heating). Getting the sign
> wrong silently produces a plausible, wrong drag area.

**`GetExposedSurfaces` — what the occlusion filter actually does**
(source-doc pass, `[PARTIAL]`: control flow traced and constants
confirmed, not every branch transcribed). It is `public static`, ~1.5 KB
of IL, and:

- returns a **new empty list** for empty input, not null;
- first sorts via `AeroModule.Sort` → a **`RadixSort` over `uint` keys**
  — a bucket sort on the x-coordinate, not a comparison sort;
- then **sweeps along x**, maintaining an ordered list of exposed
  sections through four compiler-emitted local functions
  (`InsertSection`, `RemoveSection`, `SetSectionStart`, `SetSectionEnd`);
- resolves overlaps by comparing `y` at shared `x`, splitting with
  `Line2.GetPositionAtX_Unclamped` and keeping the windward segment;
- uses **`0.001f` as epsilon throughout**, for both x-ordering and for
  treating a `y` difference as zero before `Mathf.Sign`.

**This is the same lower-envelope / visible-surface problem the Python
solver in `python_changelog.md` was written to solve.** The game's own
implementation is public and callable, so the solver is not needed to
*obtain* the number — it remains useful only as an independent
cross-check, and if used that way it should match these constants
(`0.001f` epsilon, radix ordering) rather than its own.

One more caution on this chain: `RemoveHighSlopeSurfaces` and
`ApplyProtectionZone` belong to the **heating** path only — one caller
each, inside `FixedUpdate_Reentry_And_Heating`. A drag reimplementation
must **not** apply them.

**Live test result (2026-08-28, real launch-pad rocket, `World_PC`
scene):** 36 total surfaces, 25 exposed after occlusion filtering,
`drag=7.962407`, `centerOfDrag=[-177.989471, -319.42807]` (world-space).
No errors, clean overload resolution on the first live run.

**Known refinement not yet folded in:** `CalculateDragForce` culls
segments with `dx < 0.01f` before accumulating — a Python
reimplementation of this formula needs that exact threshold, not just a
windward sign check. Also: `ApplyParachuteDrag` runs *after* the
`Lerp(CoM, CoP, 0.2)` step in §2.3 and mutates force/application-point by
reference, so the §2.3 formula does not hold as-is for a
parachute-carrying rocket — found during a separate documentation pass,
not yet independently live-verified here.

**What this unblocked:** aerodynamic torque magnitude (§2.5, now confirmed and live-validated), realistic atmospheric ascent prediction, and validation of the already-built Python lower-envelope solver against the game's own numbers directly (rather than only synthetic test cases).

---

## 5. Was "still open, no known path" — four of five now have formulas

> **STATUS CHANGE (source-doc pass,
> `session-2026-08-27-sfs_source_code_docs.md`).** This section
> previously listed four items as having no known path. Reading the IL
> bodies produced confirmed formulas for all four. **None has been
> validated live**, so they are `[CONFIRMED]` as *code readings* and
> `[UNTESTED-LIVE]` as *physics* — that distinction is the whole point of
> the tag and should not be collapsed. Full derivations in
> `sfs_source_reference.md`; only the results are here.

### 5.1 Heat / destruction — was [OPEN], now [CONFIRMED from code],
[PARTIALLY LIVE-VALIDATED 2026-08-30]

The whole chain is read. A **default part breaks at 412.0 °C**:
`Part.HeatTolerance` is hardcoded to `HeatTolerance.Low`
(`AeroModule.GetHeatTolerance`: `Low=>400, Mid=>1000, High=>6000`), and
destruction fires on `Temperature > tolerance · 1.03`. **This explains
the single 410.8 °C data point exactly** — it was 1.2 °C below the
threshold at the moment parts began dropping.

```
HeatManager.ApplyHeat:
  absorb        = 0.02 · WorldTime.FixedDeltaTime
  surfaceFactor = 1 + log10(ExposedSurface + 1)
  d             = (delta < 1000) ? delta : delta² / 1000
  gated on !noHeatDamage && WorldTime.main.realtimePhysics

HeatManager.DissipateHeat:  rate = 0.01·dt,  floor = 10·dt

AeroFormula.GetTemperature(velocity, velocity_Y, density, minHeatVelocity):
  v /= hvm; vY /= hvm; minHV /= hvm          (hvm = HeatVelocityMultiplier)
  if (vY > 0) v -= min(vY·2.5, v·0.5)
  t  = (v^velPow · density^(1/densityPow)) / m
  t += tempOffset · ((vY > 0 ? min(vY/v·2, 0.4) : 0) + 0.2)   [ADDITIVE -- see correction below]
  cap = (v − minHeatVelocity)·6;  if (t > cap) t = cap
  if (t > 2000) t = 2000 + (t − 2000)/1.5
  return max(t, 0)
```

`heatVelocityMultiplier` by difficulty is `[1.0, 1.3, 4.5]`;
`minHeatVelocityMultiplier` is `[1.0, 1.3, 3.0]`.

> **CORRECTION (2026-08-30, direct IL re-read) — the ascent-correction
> term is ADDITIVE, not multiplicative.** An earlier documentation pass
> transcribed this step as `t += t * (tempOffset·X + 0.2)` — the whole
> correction scaled by `t` itself. The real IL (confirmed by directly
> re-reading `AeroFormula.GetTemperature`'s bytecode, triggered by a
> live-vs-Python comparison that caught the formula returning exactly
> 0 during real ascent-phase heating) is:
> ```
> t = t + tempOffset · (ascent_term + 0.2)
> ```
> an ADDITIVE correction, with `0.2` grouped inside the `tempOffset`
> multiplication rather than outside it. With `tempOffset=-500`
> confirmed live, the old (wrong) multiplicative version drove `t`
> deeply negative whenever the ascent term neared its `0.4` cap,
> collapsing to `0` after the final clamp — exactly the bug that
> exposed this. The correct additive version was verified against the
> game's own live `AeroModule.GetTemperatureAndShockwave` output across
> 2,989 real samples spanning a full ascent-to-reentry flight:
> **median error 0.0000%, mean 0.0001%, max 0.0047%** — effectively
> exact agreement. `python/sfs_telemetry.py`'s
> `predicted_reentry_temperature` has been corrected accordingly. This
> also fully explains the ~50% heat-accumulation overprediction chased
> earlier the same session: the old multiplicative version added a
> spurious ~20% bonus every tick during descent, which compounds over
> a long integration far more than a one-off formula error would
> suggest.

**RESOLVED 2026-08-30 — the four `AeroFormula` coefficients are now
CONFIRMED, not open.** Read live via the new `aeroformula` probe command
(sfsprobe v0.36.0): `velPow=1.85`, `densityPow=2.2`, `tempOffset=-500`,
`m=1.47`. Earth's `atmospherePhysics.minHeatingVelocityMultiplier=1.0`
and `shockwaveIntensity=1.0` also confirmed live (`atmophysics` command,
v0.36.1). Full formula now implemented in `python/sfs_telemetry.py` as
`predicted_reentry_temperature`. **Sanity-checked** (not yet a full
validation) against the real 73,108-sample reentry flight: predicted air
temperature is ~0 above 30km, ramps sharply during the real high-speed
low-altitude descent, peaking ~5900°C as *air* temperature right around
when that flight's actual parts started breaking off (~410°C part
temperature, via the slow `ApplyHeat` absorption this doesn't yet model).
Physically consistent, good sign, **not proof** — see the two remaining
gaps below.

**Still [OPEN]:**
1. **The part-level accumulation** (`HeatManager.ApplyHeat`/
   `DissipateHeat`'s absorb/dissipate integration over time) is not yet
   implemented in Python — `predicted_reentry_temperature` gives the
   instantaneous *air* temperature (the forcing input), not a part's own
   accumulated temperature. This is the real remaining engineering work,
   not a data gap.
2. **A genuinely fresh validation flight is needed.** The existing
   archived reentry flight predates the `GetHeatState` fix (also
   v0.36.0) — its `maxTemp` telemetry reads `Part.temperature`
   unconditionally, which is confirmed wrong for any `HeatModule`-
   carrying part. A flight recorded with the CURRENT probe is needed
   before real per-part temperature data can be trusted for validation.

Also resolved: **per-part temperature is reachable.** Read the
`Temperature` property virtually off the `HeatModuleBase` (e.g.
`Surface.owner`), not `Part.temperature` — for a part whose heat is owned
by a separate `HeatModule` the plain field is never written, so the probe
may currently under-report. And `Part.OnOverheat` does **not** always
destroy: a part with joints is spared, its `joints[0]` destroyed and the
module cooled 20% instead.

### 5.2 Multi-engine — was [OPEN], now [CONFIRMED]

**There is no summation model, because there is no summation.** Each
`EngineModule.FixedUpdate` calls `Rb2d.AddForceAtPosition` independently
at its own `thrustPosition`. Multi-engine behaviour is Unity accumulating
N separate forces, and off-axis torque is emergent, not computed. A
predictive model should apply N forces, not one resultant.

The probe limitation noted here previously (`GetEngineDirection` returns
only the first active engine) is a **tooling** bug, not a physics gap —
it has moved to the checklist's tooling section. Given the above, one
engine's direction is not a meaningful summary of a multi-engine rocket
anyway; the probe should emit a per-engine array.

### 5.3 RCS — was [OPEN, deliberately unmodeled], now [CONFIRMED-LIVE]

Both selection methods are read. The gate that makes RCS behave as a
rotation damper:

```
RcsModule.TorqueThrust:
  if (|TurnAxis| < 0.95 && |rb2d.angularVelocity| < 2) return false;

RcsModule.FixedUpdate:
  AddForceAtPosition(sumNormal · (thrust · count · 9.8), ...)
  mass flow = thrust · count / ISP
```

**RCS is not proportional to steering input** — thrusters are effectively
on/off, firing only at near-full deflection **or** whenever the craft is
rotating faster than 2 °/s. The second clause is the auto-stabilisation.

**Live-validated 2026-08-31** on an engines-off coast flight (see
`sfs_source_reference.md` §D3.8 for the full derivation): `sumNormal` and
`count` are scoped **per RCS module** (`FixedUpdate` is an instance
method, so each module only sums over its own thrusters), which does
make force quadratic in a single module's own firing-thruster count —
confirmed both in the arithmetic and now in real flight data, matching
to 0.06% (29.38 measured vs 29.4 predicted for one steering direction;
the other direction predicts exact cancellation to zero and measured
close to the noise floor). Median per-tick direction error 6.1°. An
earlier hand re-derivation during this validation mistakenly pooled all
modules into one shared count, which would have overstated the force by
~6x — caught and corrected before it reached this doc; the per-module
scoping above is what's confirmed.

### 5.4 SOI transitions and terrain — was [OPEN], now [CONFIRMED
mechanism], [UNTESTED-LIVE]

**SOI crossing forces the craft onto rails.** In `Physics.Update`:

```csharp
if (planet.IsOutsideSOI(location.position) ||
    planet.satellites.Any(s => s.IsInsideSOI(location.position))) {
    PhysicsMode = false; trajectory.EnterNextPath(); Update(); return;
}
```

Setting `PhysicsMode = false` **disables every collider on the craft and
zeroes its angular velocity**, and any burn or drag integration in
progress simply stops being simulated. Re-entering physics mode rebases
the craft onto the analytic path, so there is a small position
discontinuity across the transition. Never observed in flight — watch
`rocket.physics.PhysicsMode` flip at the boundary.

> **CORRECTION — "`maxTerrainHeight` is a single bound per body, not real
> terrain geometry."** Half right. The *bound* is a single value, but
> **real per-angle terrain is queryable**:
> `Location.GetTerrainHeight(bool clampToWater)` →
> `Planet.GetTerrainHeightAtAngle(double angleRadians, bool)`, plus a
> batch `Planet.GetTerrainHeightAtAngles(double[], bool)`.
> `maxTerrainHeight` is only a fast-reject radius inside
> `IsInsideTerrain`. Terrain-relative altitude has been available all
> along. Note this is a different quantity from `Location.Height`, which
> is altitude above the **datum radius**, not above ground.
>
> **Fully closed 2026-08-30** — both live-validated (new `terrain` and
> `terraingeo` probe commands, v0.45.0/v0.46.0) and IL-confirmed for
> every piece: height querying, `IsInsideTerrain`, `GetTerrainColor`,
> `GetMaxLOD`, and `GetTerrainNormal` (which turned out to be misnamed —
> it returns a **tangent** vector along the surface in global XY, not a
> perpendicular normal; see `docs/sfs_source_reference.md` §D4.4 for the
> full IL derivation and live cross-checks). The underlying noise
> generator (`TerrainSampler.Executor.Calculate`) is a per-planet command
> pipeline, deliberately left unread since the wrapper API above is
> already fully validated. `SFS.World.Terrain` (mesh/collider generation)
> confirmed out of scope — real collision is handled by the engine.

Also newly available and directly relevant to trajectory work: the game
ships a complete public static orbital-mechanics library (`Kepler`, ~30
methods, with elliptical / near-parabolic / hyperbolic eccentric-anomaly
solvers) plus `Orbit.GetNextAnglePassTime`. Prefer calling it over
reimplementing Kepler in Python — the game's answers are the ones the
game will act on, including its own difficulty scaling. Traps:
`Orbit.period` is **0.0**, not infinity, for any orbit reaching the SOI;
`Orbit.slr` derives from periapsis, not `sma`; and `Physics.InOrbit()`
means `periapsis > Planet.OrbitRadius`, not `ecc < 1`. See
`sfs_source_reference.md` §B5.

---

## 6. Still genuinely open

- **`AeroFormula` coefficients** (§5.1) — location known, values not read.
- **The heat sentinel sign mismatch** — `DissipateHeat` writes **+∞** when
  a module finishes cooling, but `ApplyHeat` and `HeatPart` both test
  `IsNegativeInfinity`. `PartSave.temperature` initialises to `+∞`, which
  suggests `+∞` is the intended "not heated" sentinel and the two readers
  are the bug. Taken literally, a fully cooled part never re-heats. Not
  verified that modules actually reach `Temperature ≤ 0` in practice.
