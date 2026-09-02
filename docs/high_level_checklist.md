# High-Level Checklist — SFS AI

Progress tracker for Tier 1 (high-level research/architecture) completion.
Nothing below Tier 1 (mid-level schema, design, implementation) starts
until this is materially answered. See `sfs_physics_reference.md` for the
physics detail and `sfs_source_reference.md` for the code-level detail
behind any confirmed item.

---

## Current focus (2026-08-31 evening): forward integrator, closing physics for good

Goal: a genuine forward integrator that can answer "where will this
rocket be in N seconds" — then move on to the rest of the to-do (design
decisions, blueprint tooling) with physics no longer an open question.

**Fixed-thrust-direction trajectory prediction is fully unblocked right
now** — translation (gravity + drag + thrust) and body rotation
(player/SAS-commanded + aero torque, both confirmed) cover every
physics input a fixed-thrust integrator needs.

**Two specific gaps are what's left before physics is closed for
good — both are IL reads, not open-ended research:**

- [x] **Gimbal timing — fully closed 2026-08-31/09-01.** IL read
      complete: `EngineModule.RecalculateGimbal` sets the target from
      steering input every tick; `MoveModule.Update` chases it
      **linearly** (`Mathf.MoveTowards`, no easing) at rate
      `1/animationTime`; `MoveModule.ApplyAnimation` turns that into the
      real angle via `X.Evaluate(time - offset)` on a Unity
      `AnimationCurve`. **Both live-only pieces now confirmed too:** a
      real engine's curve is genuinely linear (keyframe tangents exactly
      equal the chord slope — confirmed via `gimbalinfo`), and
      `turnAxis_Input` is a bare passthrough of
      `Rocket.output_TurnAxisTorque` — confirmed both via IL
      (`Inject_TurnAxisTorque` broadcasts one value to every
      `INJ_TurnAxisTorque` module) and live (**0.0000% error, 6,513
      samples**, spanning manual-hold saturation and SAS's full settling
      curve). This is also why gimbaling engines visibly counter-steer
      the instant SAS engages — gimbal target and body rotation share
      one upstream signal, not two correlated systems. See
      `sfs_source_reference.md` §B1.10.
- [x] **Parachute drag — IL read complete 2026-09-01, live validation
      attempted, inconclusive.**
      `Aero_Rocket.ApplyParachuteDrag` runs AFTER the normal
      `Lerp(CoM, CoP, 0.2)` (corrects the 2026-08-27 note that it
      bypasses it — it doesn't, it blends further on top). For each
      deployed chute (`targetState` 1=partial/2=full, 0=stowed skipped):
      `chuteDrag = GetPointVelocity(chute.position).sqrMagnitude *
      chute.drag.Evaluate(chute.state)` (rotation-aware, unlike
      everywhere else in the aero chain), then `cop` and `force` update
      via a force-weighted average — multiple chutes compound
      sequentially, not independently. `chuteDrag` has no density term
      of its own; density applies once, uniformly, to the combined
      total afterward. Probe support built (`parachutedrag` command +
      `computed:parachuteDrag` field, v0.52.0/0.52.1, includes
      `parachuteForceX/Y`). **Four real flights attempted, all
      inconclusive, four different genuine causes** — not a formula
      problem, a data-quality problem each time: (1) chute-active window
      had almost no rotation signal (craft stabilizes, as expected);
      (2) chute-active window was already near-zero speed, nothing to
      measure; (3) a `+1220 m/s²` single-tick jump strongly suggests
      `ActiveRocket()` briefly tracked a different physical object
      (debris from a nearby separation), same artifact class seen
      elsewhere in this project; (4) a genuinely clean single-object
      flight (debris explicitly destroyed first) revealed the real gap —
      predicted was drag-only, real included gravity, and near terminal
      velocity under a chute the two roughly cancel, so real net accel
      goes small while drag-only predicted stays large. Calibrating
      local gravity from a same-flight "freefall" stretch didn't work
      either — that stretch still had real aero drag on it (fast,
      pre-chute), not gravity alone. **Fix identified, not yet done:**
      record `location.position.x/y` (+planet) alongside everything
      else so the already-confirmed gravity formula can be subtracted
      from real acceleration before comparing to predicted drag-only
      acceleration. See `sfs_source_reference.md` §C1.11,
      `sfs_physics_reference.md` §2.8.

With both gaps now IL-confirmed, Tier 1 physics has nothing left
unread. Parachute drag remains open purely on the live-validation side
(gimbal's core chain has this closed; parachute drag doesn't yet, see
above for exactly why four attempts didn't land it) — see revised
"What done looks like" at the bottom of this file.

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
- [x] **Drag FORCE formula (predicted gravity+drag vs. measured
      acceleration) — LIVE-VALIDATED 2026-08-29, the strongest result
      to date.** Distinct from the item above: `dragArea` confirmed the
      *computation mechanism* works; this confirms the *physics model*
      itself predicts real measured acceleration. One continuous
      73,108-sample flight (Engine Hawk/Fuel Tank/Capsule/Parachute) —
      powered ascent, vacuum coast to `predApo≈685,164` (~370km
      altitude), apoapsis, vacuum descent, real atmospheric reentry
      through 30km, stopped at `h≈97m` (before impact, avoiding the
      crash-telemetry corruption seen in the original test flight).
      **70,858 comparison pairs, median magnitude error 0.098%** —
      matches this project's other confirmed formulas (gravity
      0.008–0.13%) and is far above the sample size of any prior test.
      **One real, specific, deferred caveat:** 419 outlier pairs
      (>20% error), ALL clustered at `h≈26,000–29,600m` during
      high-speed ascent (`v≈1670–1690 m/s`), right at the edge of the
      30,000m atmosphere-height cutoff — not scattered noise, a
      specific reproducible zone. Hypothesized (not confirmed) to be a
      finite-difference artifact from the density formula's hard cutoff
      at the atmosphere boundary, similar in character to the earlier
      apoapsis zero-crossing noise pattern. Root cause deferred by
      explicit instruction — see `flights_log.jsonl`
      (`drag_validation_full_ascent_reentry`) for full notes.

## Physics — confirmed live 2026-08-31

- [x] **Aerodynamic torque (magnitude)** — CONFIRMED and live-validated.
      `τ = (cop_applied − worldCenterOfMass) × F_drag`, using the
      already-confirmed drag force law and CoP, correctly rotated into
      world space (a real bug fix — `dragCopX/Y` in telemetry was still
      velocity-frame, never actually converted before now) and Unity's
      own `rb2d.inertia` (read for the first time this session). Real
      capsule+heat-shield reentry, 12,174 clean ticks: correlation
      0.9986; on meaningful-torque ticks, 100% sign agreement, magnitude
      within 1.5% at the largest swings, median error 4.66%. **The real
      finding was that SAS auto-engages whenever hands are off controls**
      (`hasControl && !IsOnSurface && no manual input`) and writes
      `angularVelocity` directly, swamping the much subtler aero signal
      — three earlier attempts were invalidated by this before it was
      caught. Filtering on `Rocket.output_TurnAxisTorque == 0` (not raw
      `arrowkeys.turnAxis`) is required to isolate pure aero torque. New
      `aerotorque` probe command + `computed:aeroTorque` telemetry field,
      v0.49.0. See `sfs_physics_reference.md` §2.5,
      `sfs_source_reference.md` §C1.10.

## Physics — was "still open, no path yet"; now read from code, awaiting live validation

**STATUS (updated 2026-08-31):** all four items below previously read
"no formula read from code" / "untouched". Reading the IL bodies
produced confirmed formulas for all four, and as of this date **all
four are also validated live** against real flight data — heat,
multi-engine, terrain, and RCS. Detail in `sfs_physics_reference.md` §5.

- [x] **Heat/destruction formula** — chain read end to end, all 4
      coefficients confirmed live, AND live-validated against the
      game's own real computation. `velPow=1.85`, `densityPow=2.2`,
      `tempOffset=-500`, `m=1.47`. Default part breaks at **412.0 °C**.
      **A real transcription bug was found and fixed 2026-08-30**: the
      ascent-correction term is additive (`t + tempOffset·(X+0.2)`),
      not multiplicative as an earlier pass recorded — caught by
      comparing the Python formula directly against the game's live
      `AeroModule.GetTemperatureAndShockwave` output (2,989 samples,
      median error 0.0000% after the fix). The full per-part heat
      accumulation model (`ApplyHeat`/`DissipateHeat`, implemented in
      `python/sfs_telemetry.py`) is now validated against a real
      destruction event: **mean peak-temperature error 0.18%** across
      7 heated parts — tighter than or matching every other confirmed
      formula in this project. **Heat is fully closed.**
- [x] **Heat: the four `AeroFormula` coefficients** — **CONFIRMED LIVE
      2026-08-30**: `velPow=1.85`, `densityPow=2.2`, `tempOffset=-500`,
      `m=1.47`, via the `aeroformula` probe command. Formula structure
      independently confirmed correct via direct live-vs-real-game
      comparison (see above) — fully closed, not just read.
- [x] **Multi-engine rockets** — resolved by discovering there is
      **nothing to model**: no summation exists. Each engine calls
      `AddForceAtPosition` independently; off-axis torque is emergent.
      A predictive model applies N forces, not one resultant. (The
      "only grabs the first active engine" half of the old item was a
      *tooling* bug — moved to the tooling section below.)
      **LIVE-VALIDATED 2026-08-30.** Real hand-built symmetric 3-engine
      rocket (three parallel Fuel Tank+Engine Hawk columns), full
      throttle, ~26s burn, 1,594 samples. Summed 3 independent
      per-engine thrust contributions (confirmed formula, no shared
      resultant) against gravity+drag, compared to measured
      acceleration: **1,576 clean pairs, median error 0.14%, mean
      0.21%** — as tight as the 0.098% drag validation. 18 outlier
      pairs found and explained, not silently dropped: 16 were a
      finite-difference artifact from one irregular (half-length) tick
      spacing; the remaining 2 were a genuine one-tick `engineOn`
      flicker on a single engine (likely an asynchronous fuel-draw
      transient across the 3 separate tanks), not investigated further.
      `partCount` held at 10 the entire burn, confirming the hand-built
      rocket was genuinely one connected craft. This flight is also what
      surfaced and got the `AmbiguousMatchException` fixed (v0.37.0,
      see tooling section) — engine array reads were unusable before
      that fix.
- [x] **RCS** — both selection methods read, and force
      magnitude/direction fully live-validated — see the comprehensive
      entry below ("Live validation of RCS — fully closed 2026-08-31").
      Not proportional to input: `TorqueThrust` returns false unless
      `|TurnAxis| ≥ 0.95` **or** `|angularVelocity| ≥ 2 °/s`; the second
      clause is the auto-stabilisation. Thrusters are effectively on/off.
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
- [x] **Terrain height live-validated 2026-08-30** (new `terrain` probe
      command, v0.45.0). 13-point angular sweep on Earth showed genuine
      per-angle variation — real land ~45-52m right at the craft's
      position, dropping to deep underwater terrain (down to -3557m
      unclamped, correctly clamped to 0 with `clampToWater=true`) a few
      degrees either side, while `maxTerrainHeight` reported 261.4m for
      the same body — well above the real local surface. Cross-check
      (`Location.Height` − `Location.GetTerrainHeight(true)` = swept
      value at offset 0) matched to full precision.
- [x] **Terrain surface queries live-validated 2026-08-30** (new
      `terraingeo` probe command, v0.46.0). `IsInsideTerrain` exercised
      at three points: real craft position (`false`), a synthetic point
      5m below the local surface (`true` — confirms the real
      surface-comparison branch), and a synthetic point 1000m above
      `maxTerrainHeight` (`false` — confirms the fast-reject branch).
      `GetTerrainColor` returned a plausible grass green matching the
      landmass under the craft; `GetMaxLOD()` returned 12.
- [x] **Terrain research fully closed 2026-08-30** — read the IL body
      for the two remaining open pieces:
      - `GetTerrainNormal` is **misnamed**: it's actually a
        central-difference **tangent** vector along the surface, in
        **global XY** (not a local frame as first guessed) — matches
        the live reading to 5+ significant figures once decoded.
      - `GetTerrainHeightAtAngles`' wrapper body: normalizes angles,
        returns an all-zero array for bodies with no solid surface
        (`hasTerrain==false`, e.g. gas giants — don't mistake that `0`
        for sea level), delegates the actual noise to
        `TerrainSampler.GetTerrainSamples`, which itself (1) calls a
        per-planet `SampleCommand` pipeline for the raw heightmap
        (**[OPEN, deprioritized]** — genuinely deep procedural noise,
        not needed since the wrapper API is fully validated), (2)
        actively **lowers** underwater terrain further via a
        water-color-driven depth adjustment (explains the -3557m deep
        readings from the live sweep), and (3) blends toward `FlatZone`
        targets near guaranteed-flat landing sites.
      - `SFS.World.Terrain` namespace (`DynamicTerrain`,
        `TerrainColliderModule`) confirmed to be Unity mesh-LOD and
        physics-collider plumbing — real collision is handled
        automatically by the engine, out of scope for the agent.
      Terrain is now closed end-to-end: height querying, surface
      queries (inside/color/normal/LOD), and the underlying mechanism
      are all understood to the confirmed standard.
- [x] **Live validation of RCS — fully closed 2026-08-31.** Heat and
      multi-engine are both validated live (heat: 0.18% mean peak error,
      formula independently confirmed against the game's own real
      computation; multi-engine: 0.14% median error). RCS: the
      `TorqueThrust` selection gate matches real flight data at 99.63%
      (4081/4096 samples, 2026-08-30) — the two per-part thresholds are
      read live too (`rcsinfo`). **Force magnitude/direction validated
      live 2026-08-31** on an engines-off coast flight: predicted force
      (per-module `sumNormal·thrust·count·9.8`, `rcsforce` command
      v0.47.0) matched real finite-differenced force to 0.06%
      (29.38 real vs 29.4 predicted for `turnAxis<0`; the `turnAxis>0`
      case, predicted exactly zero by geometric cancellation, landed
      close to the measurement noise floor). Median per-tick direction
      error 6.1°. See `docs/sfs_source_reference.md` §D3.8 — including
      an honest note on a Python re-derivation bug (wrongly pooling all
      6 RCS modules' `count` together instead of scoping per-module)
      caught and corrected during the analysis; the probe tooling and
      the original IL reading were both right all along. This closes
      the last open Tier 1 physics item — heat, multi-engine, terrain,
      and RCS are now all fully closed.

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
- [x] **Live-tested 2026-08-29** (a real 73,108-sample flight) — and
      the new logging immediately paid off: `GetEngineArray` threw a
      real, previously-invisible error repeatedly, `EngineModule read
      error on part "Hawk_Engine_Name": Ambiguous match found` (a
      genuine .NET `AmbiguousMatchException`, most likely a
      property/field name collision across `EngineModule`'s inheritance
      hierarchy). The OLD pre-v0.34 code's bare `catch { }` was almost
      certainly swallowing this exact exception the whole time — this
      is the fix working exactly as designed, surfacing a bug that was
      always there rather than hiding it.
- [x] **ROOT-CAUSED AND FIXED 2026-08-30 (v0.37.0).** `Float_Reference
      : Double_Reference` hides its base's `Value` property via `new`
      (redeclares its own `float Value`, different return type, same
      name as the inherited `double Value`); `GetWrapped2`'s old plain
      whole-hierarchy `GetProperty("Value")` lookup throws the instant
      it sees two same-named properties that aren't a normal override
      pair. `EngineModule.throttle_Out` is a `Float_Reference`, so this
      fired on every engine read, aborting the whole per-engine block —
      this was candidate 3 of the old three-way open question for why
      `thrustDirX`/etc. never populated, now settled as the real cause.
      Fixed by walking the type hierarchy taking the first
      `DeclaredOnly` `Value` property at each level (can never be
      ambiguous). Same fix applied to `SetWrapped` preemptively. This is
      a foundational helper used by nearly every command in the probe,
      so the real reach is broader than just engines. **Not yet
      re-tested live** — needs a fresh game load.

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

## Blueprint construction — magnet-based stacking confirmed, surface-mount deferred

**Real findings, 2026-08-29**, from live IL research + hands-on testing
against a genuine, hand-built, correctly-connected 4-part rocket
(Engine Hawk / Fuel Tank / Capsule / Parachute) plus reference
separators and side parachutes.

**CORRECTION (2026-08-29):** `sfs_physics_reference.md` §1.3 and
`sfs_source_reference.md` both currently state "Build-grid rounding:
0.5-unit increments" as `[CONFIRMED]`. That's wrong — or at minimum,
not the real mechanism. Confirmed via IL this same session: SFS's real
part-connection system is `SFS.Builds.HoldGrid` + `MagnetModule`,
geometric attachment-point matching, not coordinate-snap rounding. Not
yet corrected in those two reference docs directly (out of scope for
this session — that tree belongs to the parallel documentation pass);
flagged here so whoever next touches that claim knows it's stale.

- [x] **SFS's part-connection system is `SFS.Builds.HoldGrid` +
      `MagnetModule`, NOT a coordinate-snap grid.** Confirmed via IL:
      `MagnetModule.GetAllSnapOffsets`/`GetSnapPointsWorld`,
      `HoldGrid.CollectSurfaceSnaps`/`CollectInterstageSnaps`. A part's
      own position ("pivot") in a blueprint is NOT its geometric center
      — `MagnetModule.points` are local-space offsets FROM that pivot,
      and for a part like `Fuel Tank` the pivot sits at its bottom
      connector, not its middle. This is why hand-picked positions in a
      raw blueprint can land a part somewhere a human dragging with the
      mouse never could — direct injection bypasses the snap step
      entirely.
- [x] **Magnet-chain stacking formula confirmed with real numbers, not
      guessed.** For any part with a `MagnetModule`: next part's pivot
      = previous part's pivot + previous part's local offset to its
      "next" connector − next part's local offset to its "entry"
      connector. Verified exactly against a real connected rocket’s
      `dumpblueprint` output (Engine Hawk y=−3.0, Fuel Tank y=−3.0
      [pivot = bottom connector], Fuel Tank top connector at
      −3.0+4.0=1.0, Capsule y=1.0 — exact match). Also confirmed:
      `Fuel Tank`'s `height` parametric variable (`N.height`) maps
      1:1 to real magnet-to-magnet world-space spacing — no hidden
      scale factor.
- [x] **A genuinely distinct "surface-mount" attachment category
      exists, confirmed across 3 part types.** `Parachute`,
      `Parachute Side`, and `Side Separator` ALL return `magnetPoints:
      null` (no `MagnetModule` at all) — not a `Parachute`-specific
      quirk. Real placed positions for these don't follow the magnet-
      chain formula (e.g. `Parachute` landed 2.0 units above the
      `Capsule` it was attached to, with no connector data to explain
      why). Most likely mechanism: `HoldGrid.CollectSurfaceSnaps`,
      which matches actual geometric edges (`Line2`/`ProcessSurfaceSnap`)
      rather than discrete points — genuinely harder to solve, needs
      real part geometry (`surfacesFast`), which is itself gated behind
      `Part.InitializePart()` (safe on placed instances only, per the
      existing geometry-capture gotcha).
- [ ] **Surface-mount positioning formula — NOT solved, deliberately
      deferred.** Real separator positions from the reference build
      (`x=11/8.5, y=0.5/-2.5` around a tank centered at x=10) don't fit
      a simple offset rule from the data gathered so far. Needs either
      (a) real geometry data from placed instances (`surfacesFast` via
      `InitializePart()`, same pattern already proven safe for placed
      parts elsewhere in this project), or (b) calling the game's own
      `HoldGrid.CollectSurfaceSnaps`/`ProcessSurfaceSnap` directly via
      reflection rather than reimplementing edge-matching in Python.
      Scoped out of the v1 magnet-based stacking tool (see
      `python/blueprint_builder.py`) — v1 covers stack/structural parts
      (tanks, capsules, engines, adapters) correctly; surface-mount
      parts (parachutes, separators, RCS, solar panels) are a known,
      documented v2 gap, not silently wrong.
- [ ] **Minor, low-priority tooling bug (not yet fixed):**
      `sfsprobe`'s `getplacedmagnets` command reads part names via
      `displayName.TranslatableName`, which returns a shared
      localization KEY (e.g. `"Parachute_Name"`) rather than the
      distinct catalog name — `Parachute` and `Parachute Side` are
      indistinguishable in its output. `getparts`/`dumpblueprint`
      already use the correct field (`orientation.name`); apply the
      same fix to `getplacedmagnets` next time it's touched.
- [ ] **`sfsprobe_build_stack_blueprint` (the MCP tool wrapping all of
      the above) is built and compiles clean, but has NEVER BEEN RUN
      end to end.** Every individual primitive it calls
      (`loadblueprintbuild`, `getplacedmagnets`) is separately
      confirmed working live; the orchestration itself (scout → read
      real magnets → compute → load final → verify connectivity) is
      not. First concrete next step: call it with a real part list
      (e.g. `['Engine Hawk', 'Fuel Tank', 'Capsule']`) and check whether
      the final loaded blueprint actually matches the confirmed manual
      chaining math, and whether the post-load connectivity check
      (`occupied` flags) reports clean.

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
- [x] **`ApplyParachuteDrag`'s force/CoP mutation** — mutates force *and*
      application point by reference, so the §2.3 drag formula does not
      hold as-is for a parachute-carrying rocket. It is also the one
      rotation-aware path (per-chute `GetPointVelocity`) and uses an
      `AnimationCurve`, so partial deployment is a curve lookup.
      **CORRECTION (2026-09-01):** the "bypasses the `Lerp(CoM, CoP,
      0.2)` damping" half of this entry was wrong — confirmed via the
      real call site that the Lerp runs FIRST and this method blends
      further on top of it, not around it. See §2.8/§C1.11 for the full
      corrected read.
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
      **Further confirmed live 2026-08-30, and found worse than
      previously known:** even via the confirmed `GetTrajectory()` call
      (not the stale raw field), `predApo` gave a wildly wrong number
      during a real flight — reported ~369km while the craft's actual
      ballistic apex, independently confirmed via live telemetry AND the
      confirmed gravity formula (agreement to 0.01%), was only ~54km.
      The reading barely moved across a 34-second window where the
      craft's real velocity swung by 250 m/s — looks like a genuine
      non-refresh in live-physics mode, not just a one-off. Christian
      separately reports a related class of bug in normal play: SFS's
      own predicted paths sometimes intersect other planets incorrectly,
      a known cause of his timewarp crashes — same underlying system,
      different failure mode. **Practical rule for this project: never
      trust `predApo`/`predPeri`/`predEcc` telemetry as ground truth.**
      Compute apex/trajectory from real position/velocity with the
      confirmed gravity formula instead — it's more accurate than the
      game's own live prediction.
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

**REVISED (2026-09-01).** Materially: gimbal timing is now fully closed
(IL + live), parachute drag is IL-confirmed with probe support built
and four live-validation flights attempted (all inconclusive, real
causes documented above — not a formula problem), plus a decision (not
necessarily research) on each item in "Design decisions owed."
Everything else is done. The only remaining research-shaped work in
all of Tier 1 is landing one clean parachute-drag validation flight
with position recorded (for gravity subtraction) — no more IL reads
needed anywhere.

All five items the old framing called out as deferrable-but-unknown —
heat, multi-engine, terrain, RCS, and now aerodynamic torque — are
**fully closed**: confirmed from IL *and* live-validated against real
flight data (heat 0.18% mean peak error; multi-engine 0.14% median
error; terrain height/surface queries + `GetTerrainNormal`/
`GetTerrainHeightAtAngles` bodies all confirmed and live-checked; RCS
selection gate 99.63% live match plus force magnitude 0.06% live match;
aero torque correlation 0.9986, 100% sign agreement on meaningful
ticks, 4.66% median error). None of them are research items anymore,
deferred or otherwise — there's nothing left to look up. The earlier note that "picking any of them up
is a flight-test, not a research project" turned out to be exactly
right, and all five flight-tests are now done.

Two things did get *added* to Tier 1 by this pass, both decisions rather
than research:

1. **The control-input path** (bypass the UI-layer gates or replicate
   them) — a real fork, because the direct-write path can turn an
   uncontrolled craft and has no clamp.
2. **The timewarp ceiling is now two decisions, not one** — physics warp
   and rails warp scale different quantities and gate different physics.

**Updated 2026-08-31**: the caveat that used to live here — that the
four confirmed formulas were code readings only, not validated physics —
no longer applies. All four now have real flight-test validation
(heat 0.18% mean peak error; multi-engine 0.14% median error; terrain
height/surface queries live-confirmed; RCS force magnitude 0.06% error).
A demo relying on any of the four is now relying on something that has
actually been measured against reality, not just read from decompiled
code.
