# High-Level Checklist — SFS AI

Progress tracker for Tier 1 (high-level research/architecture) completion.
Nothing below Tier 1 (mid-level schema, design, implementation) starts
until this is materially answered. See `sfs_physics_reference.md` for the
physics detail and `sfs_source_reference.md` for the code-level detail
behind any confirmed item.

---

## Physics — confirmed

- [x] **Gravity** — 0.008–0.13% error, both radial and tangential cases
- [x] **Thrust** — 0.4% error against measured acceleration
- [x] **Throttle response** — instant, no ramp; three-layer control model confirmed
- [x] **Fuel-flow rate** — 0.002% error
- [x] **Rotation (player-commanded)** — 0.0006% error, mass-based not true MoI
- [x] **Staging separation** — momentum conservation, 0.003–0.006% error
- [x] **Mass model** — sub-gram precision
- [x] **Aerodynamic torque — existence** — weathercock stability confirmed live
- [x] **Drag force law** — confirmed via IL, matches all 40 bodies' density inputs
- [x] **`dragArea` (magnitude)** — **LIVE-TESTED 2026-08-28.** Directly
      callable via `Aero_Rocket.GetDragSurfaces` →
      `AeroModule.GetExposedSurfaces` → `AeroModule.CalculateDragForce`,
      no Harmony needed. Confirmed live against a real launch-pad rocket:
      36 surfaces total, 25 exposed, `drag=7.962407`,
      `centerOfDrag=[-177.99, -319.43]`. `dragarea` probe command shipped
      in v0.27.0. **This was the single highest-priority Tier 1 blocker
      — now closed.**

## Physics — was blocked, now has a path

- [ ] **Aerodynamic torque (magnitude)** — geometry access is now
      unblocked (dragArea confirmed live, above), but the actual torque
      computation (`force × (CoP − CoM) offset`) hasn't been done yet.
      Next concrete step once picked back up.

## Physics — was "still open, no path yet"; now read from code, awaiting live validation

**STATUS CHANGE (source-doc pass, `session-2026-08-27-sfs_source_code_docs.md`):**
all four items below previously read "no formula read from code" /
"untouched". Reading the IL bodies produced confirmed formulas for all
four. **None is validated live**, so each is checked as a *research*
item and re-opened as a *validation* item — a confirmed code reading is
not a validated physics model. Detail in `sfs_physics_reference.md` §5.

- [x] **Heat/destruction formula** — chain read end to end. Default part
      breaks at **412.0 °C** (`HeatTolerance.Low` = 400, threshold
      `× 1.03`), which explains the lone 410.8 °C data point exactly.
      `ApplyHeat`/`DissipateHeat`/`GetTemperature` all transcribed.
      Per-part temperature **is** reachable — read `Temperature`
      virtually off `HeatModuleBase`, not the `Part.temperature` field.
- [ ] **Heat: the four `AeroFormula` coefficients** (`velPow`,
      `densityPow`, `tempOffset`, `m`) — serialized Unity data, not IL
      literals, so the formula can't be evaluated offline yet.
      **Location now known: `GameManager.main.aeroData`.** `AeroData`'s
      own layout is unread; one live introspection pass closes this.
- [x] **Multi-engine rockets** — resolved by discovering there is
      **nothing to model**: no summation exists. Each engine calls
      `AddForceAtPosition` independently; off-axis torque is emergent.
      A predictive model applies N forces, not one resultant. (The
      "only grabs the first active engine" half of the old item was a
      *tooling* bug — moved to the tooling section below.)
- [x] **RCS** — both selection methods read. Not proportional to input:
      `TorqueThrust` returns false unless `|TurnAxis| ≥ 0.95` **or**
      `|angularVelocity| ≥ 2 °/s`; the second clause is the
      auto-stabilisation. Thrusters are effectively on/off.
- [ ] **RCS force scaling in firing-thruster count** — `sumNormal` is an
      unnormalised sum then multiplied by `count` again, so force looks
      quadratic while mass flow stays linear. Both `mul` opcodes
      confirmed, **flight effect unmeasured** — do not treat N² as
      established.
- [x] **SOI transitions** — mechanism read. Crossing an SOI boundary in
      physics mode sets `PhysicsMode = false`, which **disables every
      collider and zeroes angular velocity**, calls
      `Trajectory.EnterNextPath()`, and re-enters on the rails branch in
      the same frame. Any burn in progress stops being simulated.
- [x] **Real terrain shape** — the old claim ("`maxTerrainHeight` is a
      single bound, not real terrain geometry") was half wrong.
      Per-angle terrain **is** queryable via
      `Location.GetTerrainHeight(bool)` →
      `Planet.GetTerrainHeightAtAngle`, plus a batch
      `GetTerrainHeightAtAngles`. `maxTerrainHeight` is only a
      fast-reject radius. Available all along.
- [ ] **Live validation of all four** — no flight has confirmed any of
      the above. This is now the blocking item for this group, and it
      replaces "no path yet".

## Tooling bugs — fixed 2026-08-29 (v0.34.0)

- [x] `thrustDirX`/`thrustDirY`/`gimbalOn`/`throttleOut` never populate --
      **root cause no longer a mystery, fixed at the source.** The bare
      `catch { }` that made the third candidate explanation
      unfalsifiable is gone -- `GetEngineArray` (replacing
      `GetEngineDirection`) logs every read failure individually, by
      part name, instead of swallowing it. Whichever of the three
      candidates was actually happening will show up in `probe.log` on
      the next real flight instead of staying an open question forever.
- [x] `GetEngineDirection()` only returns the first active engine --
      **fixed by design change, not a better single-engine heuristic.**
      Since there is no thrust summation anywhere in the game (each
      engine calls `AddForceAtPosition` independently), a single
      engine's direction was never a meaningful summary. Replaced with
      `GetEngineArray()`, emitting one entry per engine/booster module
      found, on or off. Also now covers `BoosterModule`
      (`thrustVector`/`boosterPrimed`), which the old getter missed
      entirely.
- [ ] **Not yet live-tested.** Built and installed (v0.34.0), but no
      flight has run against it yet -- next flight settles whether
      engines were genuinely missing before, correctly reporting
      `engineOn=false` outside a burn, or throwing.

## Tooling bugs — confirmed broken, unfixed

- [ ] `thrOn` — unreliable as a thrust indicator (workaround exists: check
      mass flatness instead)
- [ ] `GetHeatState` may under-report — it reads the `Part.temperature`
      field, but for a part whose heat is owned by a separate
      `HeatModule` that field is never written. Read the `Temperature`
      property virtually off `HeatModuleBase` instead. Needs a live check.
      Same bare-`catch{}`-hides-failures pattern as the now-fixed engine
      getter (see above) -- worth the same treatment when this is picked
      up, not just the temperature-source fix alone.

## Design decisions owed — not blocked on research, pure decisions

- [ ] **Divergence threshold** — what numerically triggers the observer/gate.
      Noise floor now known (~0.006–0.03%), anchor point exists, decision
      still not made.
- [ ] **Mission spec schema** — designer → flight-agent handoff format
- [ ] **Editor automation vs. file-writing** — does the agent play the
      in-game editor, or write blueprint files directly. **Substantially
      de-risked, 2026-08-29** (not yet fully decided, since multi-part is
      untested): the file-writing route now has TWO confirmed-working
      mechanisms depending on intent -- `BuildState.LoadBlueprint`
      (requires `Build_PC`, replaces the design currently open in the
      editor, the real "Load Blueprint" button, SAFE for routine use) and
      `RocketManager.SpawnBlueprint` (requires `World_PC`, adds a rocket
      to an already-running flight -- but per the mod changelog's safety
      note, likely a one-time internal launch-transition primitive, NOT
      for routine use). Both spawn a real part with zero editor
      interaction, called via reflection from a plain JSON file. Finding
      the `Build_PC`/`World_PC` split required a real crash first -- see
      `docs/sfs_reference/07-saveload/RocketManager.md`. Still open:
      whether `GenerateJoints` actually connects a multi-part design into
      something flyable, and whether the documented
      `OnPartNotOwned`/`OwnershipState` DLC gate blocks any non-free
      parts (untested by the free-part `Capsule` case).
- [ ] **Exact state-message contents** — what the flight agent actually
      sees each tick
- [ ] **Phase detection ownership** — probably Python (cheap, easy to
      change), not formally decided
- [ ] **Failure taxonomy** — categories for the observation prototype's
      log review
- [ ] **Safe timewarp ceiling** — **RESHAPED (source-doc pass): this is a
      per-mode question, not a single number.** The two warp modes are
      mechanically different. *Physics warp*
      (`WorldTime.realtimePhysics == true`, rates `[1,2,3,5]`) raises
      Unity's `Time.timeScale` — everything is still simulated, just
      faster, so the ceiling is an integration-accuracy question.
      *Rails warp* (`realtimePhysics == false`, rates
      `[1,5,25] · 100^n`) leaves `timeScale` at 1 and multiplies
      `WorldTime.FixedDeltaTime` instead — drag, heating and mass
      recalculation are all **gated off**, so the ceiling there is a
      "what am I willing to stop simulating" question, not an accuracy
      one. `maxPhysicsTimewarpIndex` is `[2, 2, 3]` by difficulty.
      Decide a ceiling for each mode separately. Note also
      `WorldTime.SetState(speed, realtimePhysics, showMsg)` is public and
      **validates nothing** — no `CanTimewarp` check, no clamp, and it
      does not update `timewarpIndex`.
- [ ] **Control-input path: bypass the game's gates, or replicate them?**
      **NEW DECISION OWED (source-doc pass).** `Arrowkeys` is pure state;
      the `hasControl` and timewarp guards live in `ArrowkeysDrawer`
      (UI). Writing `arrowkeys.turnAxis.Value` directly therefore turns
      an uncontrolled craft and turns during timewarp, and **nothing
      clamps `turnAxis` to ±1** on the manual branch. The agent must
      either re-check `hasControl` / `realtimePhysics` itself or bypass
      deliberately. Throttle has no such asymmetry — it is event-driven
      and ungated, identical via UI or direct write.

## Zero game dependency — could start any time, untouched

- [ ] Can a Haiku-class model reliably do goal-downgrade reasoning
      (recognizing a target orbit is unreachable, retargeting a lower one)?
- [ ] Structured-output reliability under repeated calls, same model class

## Answered this session

- [x] **Achievements: Steam-only?** No — `SFS.Logs.Challenge`, in-game
      state, fully reflectable, not gated behind Steamworks at all.
      `achievements` probe command built (v0.24), correct, not yet run live.
      (Source-doc pass: `Challenge.CollectChallenges()` is also public
      static and reaches the same catalogue. The
      `Base.worldBase.challengesArray` path the probe uses was **not**
      re-verified against IL in that pass — marked `[PARTIAL]`.)
- [x] **`Part.InitializePart()` signature** — corrected: zero arguments,
      not `InitializePart(bool)` as an earlier pass claimed.

## Answered by the source-doc pass (`session-2026-08-27-sfs_source_code_docs.md`)

Corrections that changed a previously-"confirmed" claim. Each is expanded
in the corrections table at the top of `sfs_source_reference.md` and in
the relevant section of `sfs_physics_reference.md`.

- [x] **Parametric part values — "no Python-side evaluator exists"** was
      wrong. The game ships one: `Composed_Float` holds the expression
      string and `Compute.Compile` is public static. Reading `.Value`
      already evaluates it, so **live reads were always correct**. This
      also explains *why* static asset parsing kept producing wrong
      constants — an expression needs a bound `VariablesModule`, which an
      asset file has none of. The data-trust rule is unchanged; its
      reason is now known.
- [x] **`AeroModule` is an abstract base class**, not "per-part-module
      level" drag. Drag is computed for a whole `PartHolder` at once.
      `GetDragSurfaces` has two overloads (`AmbiguousMatchException`
      under plain lookup) and its rotation matrix is derived from the
      velocity angle, not identity — and there are **two** matrices with
      opposite sign.
- [x] **Fuel-flow formula was missing a term** — `thrust · scale ·
      throttle / (ISP · ispMultiplier)`, where `scale` is the
      world-transformed `thrustNormal` magnitude. 1.0 for unscaled parts,
      which is why the 0.002% empirical check still passed.
- [x] **Earth atmosphere constants are difficulty-scaled** —
      `Difficulty.ScalePlanetData` mutates radius, gravity, SOI, SMA,
      atmosphere height *and* curve once at load. The recorded values are
      a single-difficulty snapshot and the doc did not say which.
- [x] **`CalculateDragForce` culls `dx < 0.01f` segments** — a
      reimplementation needs that exact threshold.
- [x] **`ApplyParachuteDrag` bypasses the `Lerp(CoM, CoP, 0.2)` damping**
      and mutates force *and* application point by reference, so the §2.3
      drag formula does not hold for a parachute-carrying rocket. It is
      also the one rotation-aware path (per-chute `GetPointVelocity`) and
      uses an `AnimationCurve`, so partial deployment is a curve lookup.
- [x] **Control gates live in the UI layer, not the model** — see the new
      decision item above.
- [x] **The two timewarp modes scale different quantities** — see the
      reshaped ceiling item above. `WorldTime.FixedDeltaTime` and Unity's
      `Time.fixedDeltaTime` are not interchangeable.
- [x] **Infinite fuel skips consumption entirely** rather than refilling
      tanks, so mass never drops. Anything learned under that cheat is
      learned on a different vehicle.
- [x] **Walking `Part.modules` under-reports** — it is a lazy memo of
      queries already made, keyed by short type name, never cleared; not
      an inventory. (It is `Dictionary<string, object>`, not
      `Dictionary<Type, object>` as previously recorded, though the
      empirical multi-count and dedupe advice were both right.) Use
      `PartHolder.GetModules<T>()`.
- [x] **`Physics.trajectory` is maintained on rails only** — in physics
      mode the live value is a private `lastTrajectory`, and
      `SetLocationAndState` nulls the public field outright. Always call
      `GetTrajectory()`. (Confirms an earlier empirical note, from IL.)
- [x] **`Rocket.floating` means "in water"**, not "off the ground".
- [x] **`maxTerrainHeight`** — see the terrain item above.
- [x] **Harmony root cause** — see "Abandoned" below; corrected there.
- [x] **The game ships a public orbital-mechanics library** (`Kepler`,
      ~30 static methods incl. hyperbolic solvers; plus `Orbit`'s
      angle-pass-time helpers). Prefer calling it over reimplementing
      Kepler in Python.
- [x] **`I_MsgLogger` is a one-method interface** threaded through every
      refusal gate (`CanTimewarp`, `CanFlow`, `LoadSave`). Passing a
      custom implementation yields the game's own localised *reason* for
      a refusal instead of a bare `false`. No Harmony needed; not yet
      wired into the probe.

## Abandoned — do not revisit without explicit reason

- [x] ~~Harmony-based geometry capture~~ — root-caused (see caveat below),
      superseded entirely by the directly-callable `dragArea` approach,
      now live-confirmed. Not needed for this goal regardless of the
      correction below.
      **CORRECTION (2026-08-28):** the original root-cause claim below
      ("mod loader preloads old Harmony before any mod's Load() runs")
      is NOT actually supported — `Assembly-CSharp.dll` has zero
      references to HarmonyLib/MonoMod at all. Real mechanism is almost
      certainly weak-named-assembly path-probing order, not preloading.
      An `AssemblyResolve` handler or strong-naming were never tried. The
      original paragraph is kept below for the historical record, but
      "no non-invasive fix exists" should not be treated as settled if
      Harmony is ever revisited for something else.

  Original (2026-08-27, now partly superseded by the above): SFS's own
  built-in mod loader (baked into `Assembly-CSharp.dll`) already loads
  an incompatible, arm64-macOS-broken Harmony/MonoMod version before
  any mod's code runs. Bundling a fixed version doesn't help — the old
  one is already claimed process-wide by the time a mod's `Load()`
  fires. The only remaining fix (replacing the game's own
  `Managed/0Harmony.dll`) was explicitly declined to keep the base
  game stock.

---

## What "done" with Tier 1 actually looks like

Materially: aero torque magnitude computed from the now-confirmed
dragArea geometry, plus a decision (not necessarily research) on each of
the items in "Design decisions owed."

**REVISED (source-doc pass).** The old framing said heat, multi-engine,
RCS and SOI/terrain "matter more once flying complex rockets in Tier 2+
than for a first working demo — worth flagging as deferrable rather than
blocking." That is still the right *priority* call, but the reason has
changed: they are no longer deferred because they are unknown. **All four
now have confirmed formulas read from IL**; what they lack is live
validation. So the deferral is cheap now — picking any of them up is a
flight-test, not a research project.

Two things did get *added* to Tier 1 by this pass, both decisions rather
than research:

1. **The control-input path** (bypass the UI-layer gates or replicate
   them) — a real fork, because the direct-write path can turn an
   uncontrolled craft and has no clamp.
2. **The timewarp ceiling is now two decisions, not one** — physics warp
   and rails warp scale different quantities and gate different physics.

One item to keep honest: the four confirmed formulas are `[CONFIRMED]` as
*code readings* and `[UNTESTED-LIVE]` as *physics*. Do not let the
checkboxes above collapse that distinction — a demo that relies on the
heat model without a flight test is relying on something never executed.
