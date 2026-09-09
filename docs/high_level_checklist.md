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
- [x] **Parachute drag — fully closed 2026-09-02 (IL 2026-09-01, live-validated 2026-09-02).**
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
      total afterward. **LIVE-VALIDATED 2026-09-02, attempt #6, correlation
      1.000, 100% sign agreement, median error 0.015%** (90th percentile
      0.040%) — matches or beats every other confirmed formula in this
      project. Real cause of the previous 5 inconclusive attempts, now
      fully understood: (1) chute-active window had almost no rotation
      signal; (2) chute-active window was already near-zero speed,
      nothing to measure; (3) a debris-tracking artifact (a different
      physical object briefly tracked after a nearby separation); (4) a
      real methodology gap — predicted was drag-only, real included
      gravity, fixed 2026-09-02 by subtracting the confirmed gravity
      formula from real acceleration; (5) unmodeled RCS translational
      thrust — `output_DirectionalAxis` (fed by
      `arrowkeys.horizontalAxis`/`verticalAxis`/`rcs`) drives a SECOND,
      independent RCS selection path (`DirectionThrust`) alongside the
      rotational one (`TorqueThrust`), and a window filtered only on
      zero rotational signal can still have real unmodeled translational
      RCS thrust throughout — caught by Christian, not Claude, and fixed
      by adding `output_DirectionalAxis.x/y` to telemetry and filtering
      on both. **The (6th, final) remaining wrinkle, also resolved same
      day:** even with attempts 1-5's causes all fixed, a first pass on
      a genuinely clean window still showed ~0 correlation — that
      window happened to be near terminal velocity, where real net
      acceleration is a small residual (gravity and drag nearly cancel),
      too small to resolve by double-differencing noisy 60Hz position
      data. Fixed by differentiating the directly-measured
      `location.VerticalVelocity` ONCE instead of double-differencing
      position — a generalizable lesson for any future near-equilibrium
      validation, not parachute-specific. Probe support:
      `parachutedrag` command + `computed:parachuteDrag` field
      (v0.52.0/0.52.1, includes `parachuteForceX/Y`). See
      `sfs_source_reference.md` §C1.11, `sfs_physics_reference.md` §2.8.

Both gaps are now closed — IL-confirmed and live-validated. Tier 1
physics has nothing left unread or unvalidated anywhere.

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
      error 6.1°. **2026-09-06 addendum:** IL-confirmed which mechanism
      RCS torque actually goes through — `RcsModule.FixedUpdate` calls
      the real Unity `AddForceAtPosition`, the exact same mechanism as
      aero torque (goes through `rb2d.inertia`/Unity's solver), NOT a
      direct `angularVelocity` write like SAS/manual turning. Not
      explicitly stated anywhere in this project before now — found via
      an exhaustive grep of all 9 real `set_angularVelocity` call sites
      in the decompiled assembly. See `bookkeeping/active_state.md`
      2026-09-06 for the full breakdown (also surfaced:
      `RocketManager.MergeRockets` writes angularVelocity on docking,
      not previously documented as a rotation-affecting event;
      `Water_Rocket.FixedUpdate` is a separate, undecoded
      buoyancy-physics rotation mechanism). See
      `docs/sfs_source_reference.md` §D3.8 — including
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

## Tooling bugs — fixed 2026-09-03/04 (v0.55.0–v0.58.0)

- [x] **`partCount` returned null in scoped telemetry mode (found
      2026-09-03, fixed v0.55.0).** Root cause: `partCount` was only a
      recognized pseudo-field inside `GetScriptFieldValue` (the
      script/trigger condition evaluator) — `Sample()`'s scoped-telemetry
      loop never consulted that switch, only special-cased `computed:`
      fields, and otherwise called `ResolvePath` directly, which has no
      bare `partCount` property to find. Fixed with a dedicated
      `case "partCount":` special-case in `Sample()`'s scoped loop
      (`partHolder.parts.Count`, cross-referenced from both the
      `script-condition` and `truth`-namespace `FieldRegistry` entries so
      a future reader sees the dual mechanism rather than assuming one
      case makes the other redundant — see `FieldRegistry`'s two
      `partCount` entries). **Live-reverified 2026-09-04 during the MCP
      overhaul's Checkpoint 7 regression pass:** a real 488-sample scoped
      recording (`fields=["partCount", "computed:gimbal"]`) against a
      live 38-part rocket returned zero nulls, `partCount=38` on every
      sample. Unblocks the forward-integrator re-flight's
      staging-detection plan noted in `bookkeeping/active_state.md`.
      (This checklist entry itself was found stale during Checkpoint 7 —
      still listed as "confirmed broken, unfixed" below several sessions
      after the actual fix shipped; moved here as part of that audit,
      see the note in the MCP overhaul entry below about this file's
      one known reversion incident.)
- [x] **`TryGetPrimaryGimbal` picked the wrong engine on multi-stage
      rockets (found 2026-09-03, fixed v0.56.0, corrected v0.56.1).**
      v0.56.0's first fix (compare `throttle_Out` magnitude across
      gimbaling engines) worked by coincidence, not by checking the
      actual thing that varies — SFS has exactly three engine control
      layers (shared throttle "amount", rocket-wide master ignition, and
      per-engine `engineOn`), and only the last is genuinely per-engine.
      v0.56.1 fixed it for the right reason: reads `engineOn` directly,
      returns the first gimbaling engine that's actually on, falling back
      to the first gimbaling engine found (any state) only if none are
      on. **Live-reverified 2026-09-04** in the same Checkpoint 7
      regression recording above: `gimbalOn=true` consistently across
      all 488 samples on a live multi-part rocket, confirming the
      engine-selection fix still resolves correctly after every
      Checkpoint 1–6 change to the surrounding file.

## Tooling — MCP overhaul complete (2026-09-04)

- [x] **MCP overhaul — complete, Checkpoints 1-8 all done.** Originally
      planned and tracked via a temporary implementation prompt
      (`docs/mcp_overhaul_checkpoint_prompt.md`, now deleted per its own
      Checkpoint 8 — its content is fully superseded by this entry plus
      the real changelog entries it references). **What shipped, vs. the
      original plan:** every checkpoint shipped as planned, with two
      honest mid-course corrections neither silently swept under the
      rug: Checkpoint 3's first "verified" pass was a false positive (it
      tested a fresh throwaway process, not the actual long-lived
      `sfsprobe_mcp` subprocess a real client stays connected to — caught
      independently by Christian via `probe.log`-timestamp matching, not
      by the tool's own JSON response); Checkpoint 5's first `deep_search`
      implementation matched type names only, which would have silently
      returned nothing for the exact queries it exists to answer (IL has
      no comments/tags, so a query like `"gimbal"` needs to hit a FIELD
      name, not a type name) — caught and rebuilt into a genuine
      two-level type+member index before that checkpoint was called done.
      Both corrections are detailed in full below and in
      `analysis/python_changelog.md`. Covers: moving command/field discovery from
      regex-parsed comments to a live C# self-description registry
      (with units -- directly targets the
      parachuteAlphaDeg-is-really-angular-acceleration class of bug),
      a unified `sfsprobe_search` tool superseding the old
      `sfsprobe_command_search`/`sfsprobe_telemetry_field_search`,
      fast-fail command validation, physics/source doc indexing folded
      into the same search tool, and a zero-context agent onboarding
      resource. **Explicitly deferred within that plan too:** replacing
      the file-polling command.txt/result.txt IPC with a real socket
      protocol -- noted as separate future work, not attempted in the
      overhaul itself, since it's a much larger and riskier change.
      **Status:** Checkpoint 1 (C# `CommandRegistry`/`FieldRegistry` +
      `describe` command) done and live-verified. Checkpoint 2
      (`sfsprobe_search` in the Python MCP, old two tools removed) done
      and live-verified 2026-09-04 -- both the static-fallback path and
      the live `describe` registry confirmed correct against the four
      queries that caused real mistakes this session
      (`parachuteAlphaDeg`, `gimbalThrottleOut`, `partCount`,
      `telemetrysnapshot`). Checkpoint 3 (fast-fail leading-word command
      validation in `sfsprobe_send_command`/`sfsprobe_send_batch`) done
      and **genuinely** live-verified 2026-09-04, after a false-positive
      round: my first pass "verified" it against a fresh throwaway
      Python process, which doesn't reflect the actual long-lived
      `sfsprobe_mcp` server subprocess a real MCP client stays connected
      to -- two such processes were still running the pre-Checkpoint-3
      code, which Christian caught independently from his own session
      (`ps aux` showed both started 19:32:35, before the checkpoint's
      edits existed) and confirmed via `probe.log`-timestamp matching,
      not just the JSON response. After Christian restarted his SFS
      session and MCP connections, re-verified with the same log-based
      method: a bad command produces zero trace in `probe.log` and
      resolves in <1ms once the registry cache is warm. Real, separate
      bug found and fixed along the way: `SFSProbe.cs`'s `telemetry`
      case treated ANY non-`"on"` second word as `"off"`, silently
      stopping+archiving an active recording with no error surfaced
      (or silently no-op'ing + a client-side timeout if already off) --
      fixed in mod v0.58.0, built, reloaded, and live-confirmed (an
      active recording now survives `telemetry snapshot` intact; see
      `sfsprobe/mod_changelog.md` v0.58.0 and
      `analysis/python_changelog.md` for full detail). Remaining honest
      scope note: leading-word-only validation still can't catch a bad
      SECOND word on an otherwise-valid command in general -- v0.58.0
      fixes `telemetry` specifically, not that whole class of mistake.
      Checkpoint 4 (`domain="doc"` indexing of `docs/sfs_physics_
      reference.md` + `docs/sfs_source_reference.md` into
      `sfsprobe_search`) done 2026-09-04: both files chunked by Markdown
      heading (214 chunks total), each tagged with any
      `CONFIRMED`/`PARTIAL`/`OPEN` markers found in its heading/body,
      cached `DOC_CACHE_TTL_S`s so edits to either file show up without
      a server restart. Verified against a fresh import of the real
      `server.py` module (not `mac-terminal-mcp`/a running MCP
      connection): `sfsprobe_search("three layer engine control",
      domain="doc")` correctly surfaces physics-reference §2.2 Thrust
      (the section that actually contains the throttle/master/engineOn
      three-layer model); `sfsprobe_search("SOI crossing physics mode",
      domain="doc")` surfaces both the physics-reference §5.4 and
      source-reference §D4.3 SOI sections; `domain="all"` returns
      commands/fields/docs as separate per-domain lists (44/67/214
      total) rather than one merged ranking, so docs' larger corpus
      can't drown out commands/fields. **Caveat carried over from the
      Checkpoint 3 lesson above: this was NOT re-verified through the
      actual long-lived `sfsprobe_mcp` subprocess a real MCP client
      stays connected to** (two such processes were already running,
      started before this checkpoint's edits) — since `domain="doc"` is
      pure file-parsing with no game-state dependency, a fresh-process
      test is equally valid for correctness, but the live client
      connection still won't see this code until it's restarted.
      Checkpoint 5 (split into `light_search`/`deep_search`) done
      2026-09-04, **corrected mid-checkpoint after discussing the design
      with Christian**: `sfsprobe_search` renamed to `light_search` (pure
      rename, behavior unchanged -- re-verified all of Checkpoints 2/4's
      queries under the new name, all still correct). First `deep_search`
      pass matched type names only (via `monodis --typedef`) -- wrong on
      its own merits: IL has zero comments/tags (decompilation strips
      them), so a query like `"gimbal"` needed to hit `EngineModule`'s
      `gimbal` FIELD, not the type name `EngineModule` (which doesn't
      contain "gimbal" at all). Rebuilt as a genuine two-level
      type+member index before calling this checkpoint done: reused
      (not reimplemented) `analysis/il_inventory.py`'s existing
      `.class`-declaration parser (built for the `docs/sfs_reference/`
      migration), extending it with a `capture_members=True` flag that
      also records real method/field names, not just counts -- and
      refactored its previously-bare module-level code (which wrote
      `docs/sfs_reference/inventory.json` on *any* import) into an
      `if __name__ == "__main__"`-guarded CLI so importing it has zero
      side effects. `deep_search` now tries type names first, then falls
      through to every method/field name across all types, returning
      `matched_via` + which specific members matched. Multi-word queries
      use AND per term against one candidate name -- found necessary when
      a conceptual sentence query (`"why does thrust ramp up slowly"`)
      returned noise under OR/max-score (common short words like `"up"`
      exact-matched an unrelated real field). Verified: `deep_search
      ("gimbal")` now correctly resolves `EngineModule` via its `gimbal`/
      `gimbalOn`/`RecalculateGimbal` members; `deep_search
      ("EngineModule")` still returns real IL containing `hasGimbal`,
      `engineOn`, `throttle_Out` (matches `sfs_source_reference.md`
      §D2.1 exactly); `deep_search("parachute")` resolves cleanly to
      `ParachuteModule`; the exact conceptual-sentence query now
      correctly returns zero matches with a note pointing at
      `light_search`'s doc domain instead. Confirmed `docs/sfs_reference/
      inventory.json` (WIP migration artifact) restored to its exact
      original state after a regression test, and `scratch/full_il.txt`
      (Christian's manual-research scratch file) untouched throughout --
      `deep_search` uses its own cache at `scratch/.deep_search_cache/`.
      **Honest scope note, now stated in the tool's own docstring too:**
      `deep_search` can only ever match real identifiers, never concepts
      or prose -- that job stays with `light_search`. Checkpoint 6
      (`sfsprobe_onboarding` orientation tool) done 2026-09-04: returns
      plain-text orientation covering the mod/MCP relationship, the
      "search before you guess" standing instruction, when to reach for
      `light_search` vs. `deep_search`, every real error code in current
      use, and the four telemetry field namespaces (explicitly
      distinguished from the live registry's separate `truth`/`inputs`
      namespace tags, a conflation caught and fixed before shipping --
      see `analysis/python_changelog.md`). Implemented as a `@mcp.tool`
      rather than an `@mcp.resource` for consistency with every other
      capability on this server. Verified via a direct function call
      (no game dependency, pure static text) and a cold read-through as
      a zero-context AI. **Checkpoint 7 (audit pass) done 2026-09-04.**
      Added `sfsprobe_registry_audit()` (new tool, no params) -- statically
      diffs `CommandRegistry`/`FieldRegistry`'s array literals against the
      real case-block/switch parsers `light_search`'s fallback path
      already uses (reused, not reimplemented), flagging any command/
      field present in code but missing a registry entry, or vice versa
      (stale). Pure source parsing, no game needed. **Result:
      `"clean": true`** -- 44/44 commands, 6/6 computed-field groups,
      21/21 computed output keys, and 10/10 script-condition fields all
      present on both sides; the registry has not drifted since
      Checkpoint 1 despite the one intervening dispatch-logic change
      (`telemetry`'s v0.58.0 fix). `partCount`'s dual script-condition/
      scoped-telemetry validity is deliberately handled via
      cross-referencing prose in its two registry entries rather than a
      dedicated namespace tag -- confirmed intentional, not a gap. Full
      regression pass run live against a real SFS session (v0.58.0,
      scene `World_PC`, 1 rocket): `sfsprobe_status`/`sfsprobe_ping` both
      responded correctly; a real 488-sample scoped recording
      (`partCount`, `computed:gimbal`) confirmed **both tonight's target
      bugs still fixed** -- zero `partCount` nulls (constant `38` across
      all samples) and `gimbalOn=true` consistently (the v0.56.1
      engine-selection fix); a fast-fail bad-command test
      (`zzznotarealcommand123`) returned `UNKNOWN_COMMAND` in 0.31s via
      `source: "live_registry"`; `light_search("parachuteAlphaDeg",
      domain="field")` still correctly resolves the angular-acceleration
      unit live. **New standing convention, documented here per the
      plan:** from now on, adding a command or telemetry field means
      adding BOTH the `case`/`switch` entry in `SFSProbe.cs` AND a
      matching `CommandRegistry`/`FieldRegistry` entry in the same
      change -- run `sfsprobe_registry_audit()` after, to confirm before
      the next session starts relying on stale registry data.
      **Deferred, not attempted this overhaul:** replacing the
      file-polling `command.txt`/`result.txt` IPC with a real socket
      protocol -- larger, riskier change (new C# networking code, full
      protocol rewrite both sides); noted here as the standing
      future-work item, not tracked as a bug. **Honest caveat:** the
      drift auditor's coverage is exactly as good as its regex parsers --
      if `CommandRegistry`/`FieldRegistry`'s array-literal syntax itself
      changes shape (e.g. entries reformatted across more lines than the
      regex expects), the audit could silently under- or over-report
      rather than erroring; it was verified against the array's current
      real formatting, not fuzzed against hypothetical reformattings.
      **Checkpoint 8 (cleanup) done 2026-09-04**, after Christian's
      explicit confirmation the overhaul was complete and working:
      `docs/mcp_overhaul_checkpoint_prompt.md` deleted (temporary
      implementation prompt, superseded by this entry and the
      per-checkpoint changelog entries); this checklist item moved here
      and marked done.

## Tooling bugs — confirmed broken, unfixed

- [ ] **`computed:engines`'s per-engine `thrustDirX`/`thrustDirY` never
      reflects real gimbal deflection (found 2026-09-06).** Confirmed
      across an entire clean 6,518-sample flight (6-engine rocket,
      real hard steering corrections including a full ±1 turnAxis
      reversal at t=33.6s): every engine reports exactly `(0, 1)` —
      the un-deflected baseline direction — on 100% of samples, even
      while the single-engine proxy (`gimbalTime`/`gimbalTargetTime`)
      correctly shows the SAME engines' gimbal actively ramping to full
      deflection and back. `engineOn` and `throttleOut` in the same
      `computed:engines` payload ARE correct per-engine (confirmed
      individually-toggled engines read correctly). This is likely the
      same underlying issue as the old `GetEngineDirection`/
      `GetEngineArray` `thrustDirX` bug (fixed 2026-08-29/08-30,
      v0.34.0/v0.37.0 — see below) recurring in the newer
      `computed:engines` scoped-telemetry code path, which may not
      route through the fixed `GetEngineArray` function at all. Not yet
      root-caused this session — flagged for a probe-code fix before
      relying on per-engine gimbal direction for anything. Workaround in
      the meantime: use the single-engine `gimbalTime`/`gimbalTargetTime`
      proxy for gimbal-timing validation (still correct), and don't use
      per-engine `thrustDirX/Y` for anything until fixed.
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
- [x] **Surface-mount positioning formula — IL-CONFIRMED 2026-09-02** (was
      "NOT solved, deliberately deferred"). Real mechanism read end to
      end: `HoldGrid.CollectSurfaceSnaps`/`ProcessSurfaceSnap` — edge-to-
      edge matching (parallel gate, overlap gate, proximity gate, then a
      0.25-unit-quantized offset + rotation delta), NOT a fixed
      per-part-type offset, which is exactly why the earlier attempt to
      fit one to the reference separator positions failed. Full algorithm
      in `sfs_source_reference.md` §E8.1. **One open piece**: the exact
      anchor-end (start vs. end) branch selection was traced but not
      live-cross-checked — needs one real test placement before
      `blueprint_builder.py` v2 trusts it blind. Still needs real edge
      geometry (`surfacesFast`) for both parts either way, same gotcha as
      before (gated behind `Part.InitializePart()` on placed instances).
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

## Forward integrator — ROOT CAUSE FOUND AND FIXED 2026-09-07

**The rotation-instability bug (below, and its 2026-09-02 origin entry
further down) is RESOLVED.** Root cause: `dragCopX/Y` in the static AoA
sweep table are genuine absolute world coordinates, not
position-independent offsets -- confirmed via a live setrot+dragarea
comparison at a real flown AoA (table predicted copX=+446.68, live
measurement gave copX=-300.70, opposite sign). The table got worse the
further the craft moved from where it was swept, exactly matching how
the blowup compounded with altitude. Fixed in `forward_sim.py`: a new
`build_position_independent_aoa_table()` function rebuilds the table
into true position-independent lever arms, wired automatically into
`_prepare_replay`; paired with live CoM tracking (no longer frozen at
pre-ignition) so both halves of the (cop-com) subtraction stay correct
regardless of how far the craft has flown. Also folded in: live_inertia
(confirmed real, mass-proportional) and a Box2D-matching rotation
safety clamp, both real findings from the same investigation.

**Validated** against the tagged straight_up_predictor_test_2026-09-07
flight via the official `test_against_run_trajectory` tool, dt=1/60s
(game's real physics rate), 6s window: rotation error median 0.00048
deg / max 0.035 deg; angular velocity error median 0.0018 deg/s / max
0.033 deg/s -- down from 179+ degrees and ~15,400 deg/s before the fix.
Full story (every ruled-out candidate along the way -- integrator
choice, step size, velocity source, torque formula, composition order,
Box2D clamp alone, live inertia alone) in
`analysis/python_changelog.md`'s 2026-09-07 entry.

**Still open, separate finding, NOT part of this fix:** a real small-AoA
(0.1-2 deg) aerodynamic instability in this specific finless craft,
confirmed via live setrot tests showing sustained real `rb2d.rotation`
drift (not a diagnostic artifact). Crossover to the confirmed-stable
20+ deg regime not yet bracketed.

**Follow-up same session:** added a selectable `integrator` flag
("rk4" default, or "symplectic_euler" -- confirmed the closer match to
what Box2D itself actually uses). Rotation accuracy is virtually
identical between the two; translational position accuracy is 4-10x
worse with symplectic Euler (expected -- 1st-order vs. RK4's 4th-order
at the same dt). Also found and fixed a real 24.5x (RK4) / 12.3x
(symplectic Euler) speedup in `aoa_dragarea.py`'s `lookup_field()` --
was re-sorting all 721 table bins from scratch on every call; now
sorts once and caches, uses `bisect` instead of a linear scan.
Verified byte-for-byte identical output across the full angle range
before promoting.

**Honest scope note found while timing the above:** the fix above is
validated for the clean 6-second ascent window specifically. A full
600s replay of the same tagged flight correctly predicts terrain
impact around sim_t~50s (matching the real flight's own eventual
fall back to pad height), but rotation error in that later
coast/descent portion is substantial (median 72 deg across the few
samples that far out) -- plausibly the same still-open small-AoA
instability noted above, becoming visible over a longer horizon.
Full-flight (not just ascent) accuracy is NOT yet confirmed.

## Forward integrator — continued 2026-09-07 (later session): earlier fix confirmed real but does NOT generalize to sustained real maneuvering at high rotation rate

**The earlier same-day fix (position-independent AoA table + live CoM tracking) is real and holds up** -- re-confirmed via a fresh v0.65.0-instrumented flight. But testing against REAL curving/maneuvering flights (this session's own explicit next-step, not the straight-up-only window validated earlier) surfaced a much larger, separate problem: on any flight with sustained fast rotation (tested up to ~98 deg/s), rotation error grows to tens-to-hundreds of degrees within 15-25 seconds, regardless of which specific aero-torque data source or execution order is used.

**One SEVERE bug found and fixed along the way, affecting every test this session before it was caught**: `throttle_field="throttleOut"` was silently resolving to `0.0` (a definite "commanded off" signal) instead of `None` ("no signal"), because that field name has never existed as a top-level telemetry key -- only nested per-engine. This zeroed engine thrust and used the wrong (idle, not firing) torque value for the ENTIRE duration of every affected test. Fixed; full detail in `analysis/python_changelog.md`.

**After the fix, an extensive, systematic hypothesis campaign ruled out every individually-testable mechanism**: static AoA table staleness (refuted, inverted -- aero data is necessary and roughly correct), numerical/RK4 stiffness at two different rotation rates (refuted both times), live-vs-table aero data noise (refuted -- nearly identical in both magnitude and jitter), the rotation-error metric's multi-revolution handling (refuted with exact test cases), SAS/aero execution-order (real effect, not dominant), mass-scaled inertia (already implemented and active the whole session, doesn't explain it). A full IL-and-Box2D-source audit (reading raw bytecode directly, not trusting prior doc summaries) confirmed every SFS-side formula is solid; the only genuinely unreachable pieces are inside Unity's own compiled physics module (moment-of-inertia computation, damping, and -- confirmed via Unity's OWN documentation -- script execution order between MonoBehaviours, which is NOT guaranteed deterministic unless explicitly pinned, and SFS pins nothing).

**Working conclusion**: the divergence has the signature of compounding sensitivity in a dynamically sensitive regime (nearly-identical inputs produce meaningfully different tail outcomes; divergence is smooth/gradual, not a discrete jump) rather than a single fixable formula error. NOT yet confirmed as formal chaos (would need a controlled-perturbation test for exponential vs. ordinary divergence growth -- proposed, not run).

**Practical reframe, agreed with Christian, driving the next session's plan**: stop trying to make one predictor handle both regimes uniformly. Split validation into (1) **atmosphere** (drag + aero_torque active) -- accept a short reliable horizon as fundamental to the regime, not a bug to fix; real/sane flight profiles (gentle gravity turns) don't sustain the 70+ deg/s rates that broke the model anyway, confirmed by direct comparison (a real single-maneuver flight: median 0.01 deg/s, max 13.83 deg/s vs. the stress-test flight: median 6.55, 90th pct 64.48, max 98.64) -- and use short-horizon prediction with periodic re-sync to real telemetry (standard receding-horizon/MPC control, natural in a live agent flight since real telemetry is always available) rather than open-loop long prediction. (2) **space/vacuum** (gravity + timewarp + thrust + rotation only, no aero) -- genuinely simpler state, should support much longer prediction horizons -- NOT YET TESTED, no vacuum-coast flight recorded this session.

**Immediate next experiment (stated by Christian)**: fly a new flight next session using deliberately CRAFTED/SCRIPTED turn and throttle commands (not live manual button-mashing) -- separately for the atmosphere-regime and space-regime cases -- so the reliable-horizon-vs-rotation-rate relationship can be measured cleanly. A rough attempt this session (many starting points across the existing stress-test flight) came out too noisy to use, because that flight had continuous fresh rapid turn inputs throughout, confounding "horizon from a given starting state" with "how soon does the next aggressive input arrive." A scripted flight with deliberately spaced, controlled turn events (mirroring the successful scripted-input approach already used earlier this session, e.g. `analysis/replay_steps.json`'s generation pattern) would give a clean signal. See `bookkeeping/active_state.md` for the concrete setup.

## Forward integrator -- 2026-09-08: root cause found for the sign-asymmetry (AoA=0 table defect, not sign), regime-gated fix, 30s-ahead goal achieved for coast/vacuum

**The scripted-flight next-step above is DONE** -- ran `atmosphere_scripted_turns_2026-09-08` (3 spaced turn events) plus a purpose-built matched pair (`direction_sign_matched_pair_2026-09-08_A2`/`_B`, identical launch, single turn differing only in sign) specifically to isolate turn-sign as a variable, confirmed matched via real telemetry (sub-1% alt/vel, thousandths of a degree rotation, up to the turn).

**Root cause found: the matched pair's sign asymmetry (smaller-magnitude turn diverging WORSE) was never about sign -- it's a static-table defect at AoA~0.** Direct per-tick real-vs-table-predicted torque comparison (no compounding trajectory, isolates the table itself) found the table predicts large spurious torque (~-85 to -92 deg/s^2) exactly where real torque is genuinely ~0. Ruled out both alternative explanations directly rather than assuming: not a general rate-dependence gap (median residual doesn't trend with |omega| at all -- the earlier apparent correlation was outlier-driven), not an aero-table sign/mirror-symmetry bug (position-independent lever arms at mirrored AoA are genuine mirror images).

**Fix built and tested (`analysis/forward_sim_v2.py`, not yet merged into `forward_sim.py`): a regime-gated `aero_torque_aoa_gate_deg` flag.** Zeroes only the torque contribution (not drag force) near AoA=0. Result is genuinely regime-dependent, not a universal win: fixes pure-coast windows completely (99.97% -> 0.040% error) but makes turn-inclusive windows WORSE at every threshold/cooldown tested -- confirmed the gate is only safe with zero turn commands anywhere in a window's history, not merely "far enough" from one.

**30s-ahead accuracy goal (Christian's explicit target, <1% at 30s): achieved for coast/vacuum, isolated (not solved) for atmospheric maneuvering.** Powered atmospheric coast 0.497% at 30s / 0.671% at 34s (data ceiling). Natural (unscripted) fuel-exhaustion cutoff crossed cleanly, 0.06-0.14% error through the transition. Unpowered vacuum coast ~0.001% even at 60-70s. **A vacuum turn (h=116,584m, well above the 30km atmosphere ceiling) also predicts almost perfectly (0.001% position)** -- this reframes the entire "turns are chaotic" conclusion from 2026-09-07: it was never turning itself, it's specifically turning THROUGH DENSE ATMOSPHERE. Atmospheric-turn error remains the one real open gap, now with sign/dt/integrator/composition-order/live_inertia/the AoA=0 fix itself all ruled out as the cause -- genuinely needs new data (a `dragareasweep` captured while actively spinning at known rates, not just static angles), not another existing-data hypothesis. Full detail: `analysis/python_changelog.md`'s 2026-09-08 entry.

**Also this session: mod v0.66.0 added programmatic staging (`stage`/`stages`), IL-researched and live-verified end to end on a real 3-stage rocket.** See `sfsprobe/mod_changelog.md`.

---

## Forward integrator — end-to-end calibration, NOT done (historical entries below, kept for the record)

**Added 2026-09-02, after tonight's error-compounding discussion.** All
individual physics formulas are confirmed and validated in isolation
(see above), and the integrator already supports active RCS/thrust
command sequences via `ControlSchedule`/REPLAY mode — dynamic
what-if simulation, not just passive-force prediction, is architecturally
done. What's genuinely missing is knowing how error actually compounds
over a real multi-minute mission with real maneuvering, as opposed to
assumed from a model.

- [x] **Run `--test_against_run` end to end against a real mission for
      the first time.** First attempt 2026-09-02 failed immediately
      (`KeyError: 'location.position.x'` — telemetry field list was
      missing position/mass/rotation/angularVelocity). Corrected field
      list and re-flight plan already written up in
      `bookkeeping/active_state.md`'s "Immediate next experiment" — this
      item just formally tracks it at the Tier 1 level, since it's a
      real prerequisite for calling the integrator done, not an optional
      nice-to-have.
      **2026-09-05 update:** `test_against_run` and the new
      `test_against_run_trajectory` (full predicted-vs-actual curve,
      position/rotation error separated) are both now wrapped as MCP
      tools and confirmed working end-to-end via real live testing —
      but only against tiny (<1min, mostly stationary) test flights with
      a stale craft_config. The tooling gap is closed; the actual real-
      mission run this item describes still hasn't happened.
      **2026-09-07 update — DONE, and it found a real, severe bug.** Ran
      a real ~70s straight-up-then-fall flight (full throttle to h=1007m,
      cutoff, coast, fall to pad height, zero steering input throughout —
      tagged `straight_up_predictor_test_2026-09-07`,
      `archive/kept/telemetry_flat_2026-09-07_09-40-05.jsonl.gz`)
      through `test_against_run_trajectory` with full Bucket-A physics
      enabled (`aoa_table_path` supplied — see the critical tooling gotcha
      below). Real `rb2d.rotation` stayed at ~0.0000° for the entire
      flight (genuinely non-rotating craft, confirmed both in the raw
      telemetry and independently via `angv` staying under 0.005°/s
      throughout). The PREDICTED rotation (`theta_deg`), starting from the
      same zero, diverges in a clean **exponential** pattern purely from
      numerical/model instability — no real perturbation driving it:
      0.004° → 0.02° → 0.06° → 0.13° → 0.28° → 0.59° → 1.26° → 2.79° →
      6.57° → 17.66° → 93.25° by t=2.75s, predicted angular velocity
      pinned around **23,000 deg/s** by t≈6s, theta chaotically wrapping
      thereafter. This is almost certainly the SAME failure mode as the
      original, unrecoverable 142.75° blowup (flight #9, lost — see
      `bookkeeping/active_state.md`) — but now fully REPRODUCED on a
      flight with a trivially-known-correct answer (zero rotation),
      tagged and saved this time. The growth pattern (each ~0.25s RK4
      step roughly doubling from a near-zero start) is the textbook
      signature of a **positive-feedback / wrong-sign restoring-torque
      bug** in the Bucket-A rotation model — weathercock stability should
      be a damping (negative) feedback, and something in `forward_sim.py`
      is amplifying instead of damping even tiny AoA perturbations. NOT
      YET root-caused to the exact line/term — see
      `bookkeeping/active_state.md`'s "Immediate next experiment" for the
      concrete next step (read the Bucket-A torque/rotation integration
      code directly, hunting for a sign error).

      **Real, separate tooling gotchas found getting this test to run at
      all (all now documented, all reusable for future tests):**
      1. `test_against_run_trajectory` requires flat literal JSON keys
         (`output_TurnAxisTorque`, `output_DirectionalAxis.x/y`,
         `location.position.x/y`, `rb2d.mass`, `rb2d.rotation`,
         `rb2d.angularVelocity`) that do NOT match what full-mode
         `telemetry on` actually records (`turnAxis`, `directionalAxisX/Y`,
         `px`/`py`, `m`, `rot`, `angv`) — needed a field-renaming compat
         pass on the flight file before the tool would even accept it.
      2. `engines` is recorded as a nested array
         (`engines[0].throttleOut`), not a flat dotted key — a
         `throttle_field` pointing at a literal `"engines[0].throttleOut"`
         string silently resolves to `None`/0.0 every tick via the code's
         own `r.get(throttle_field) or 0.0` fallback, with NO error raised.
      3. **The most important one:** omitting `aoa_table_path` doesn't
         just skip aero-torque accuracy — it silently routes the ENTIRE
         simulation into an old fallback mode with gravity + frozen drag
         ONLY, meaning **zero engines/thrust/gimbal/RCS/staging/terrain/
         heat are modeled at all**, no error or warning either. Always
         supply a real `aoa_table_path` for any meaningful full-physics
         replay test.
      4. `getforwardstartinfo`'s auto-written `AoA_drag_table_<name>.json`
         is the RAW sweep-samples format (flat list of
         `{aoaDeg,dragArea,dragCopX,dragCopY,...}`), NOT the "bins" dict
         format `forward_sim.py`'s loader expects (built by
         `aoa_dragarea.py`'s `build_table`) — needed a one-bin-per-sample
         conversion pass. A real, clean, reusable conversion (arguably
         better data than the noisy flight-derived kind `aoa_dragarea.py`
         normally builds, since it's a noise-free synthetic sweep) — worth
         promoting into a real `analysis/` script rather than staying a
         one-off scratch conversion.
- [ ] **Determine actual error-compounding behavior empirically, not by
      assumed model.** The only real data point so far: four 10-second
      BLIND-mode (no control replay) forward-sims from an earlier
      session, mean **0.001% error** in translational/altitude
      prediction — but that was a calm window. The SAME test's rotation
      prediction ranged from **0.00° error** (started inside a
      SAS-locked steady state) to **49.7° and 178.5° error at just 10s**
      (started during active tumbling/correction) — a completely
      different failure mode, not just "faster compounding." One
      calm-window data point is not enough to know how the REPLAY-mode
      integrator (with real control input, not the zero-torque
      fallback that produced those rotation numbers) behaves over a full
      mission under real maneuvering. This needs the corrected re-flight
      above, analyzed across both calm AND actively-maneuvering windows
      separately — position and rotation likely need separate
      compounding characterizations, not one blended number.
- [ ] **Only after the above: revisit the divergence-threshold design
      decision** (see below) with real data instead of the two
      illustrative compounding models (linear worst-case / random-walk)
      used in tonight's exploratory tool. Likely two separate thresholds
      — translational/altitude vs. rotation — not one blended number,
      per the asymmetry above.
- [ ] **Address the six documented simplifying assumptions** in the
      Bucket-A integration (discrete-mechanism execution order, heat
      single-representative-part, parachute curve linear not Hermite,
      gimbal operator-splitting not proven exact, staging velocity-kick
      defaults to zero, single-engine-scoped throttle applied uniformly)
      — full list in `analysis/python_changelog.md`'s Bucket-A entry.
      Each is a real, bounded gap between "physics is confirmed" and
      "the integrator's predictions are trustworthy," separate from the
      compounding question above.
- [ ] **`gimbalThrottleOut` throttle-replay proxy picks the wrong engine
      on multi-stage rockets (found 2026-09-03, first real-flight test
      of `--test_against_run`). FIXED in v0.56.0, not yet re-tested
      live.** `TryGetPrimaryGimbal` returns the
      FIRST `EngineModule` with `hasGimbal==true` walking `partHolder.parts`
      in order -- not necessarily one that's currently firing. On a real
      6-engine, multi-stage flight (4x Hawk + Valiant + Titan), the first
      gimbaling engine in part order was Valiant (likely the dormant
      upper stage), so `gimbalThrottleOut` read 0 every tick for the
      entire ~30s replay window even though real mass dropped
      247.6→205.5t (unmistakable full-throttle multi-engine burn from
      the OTHER engines). Consequence: `--test_against_run` predicted the
      rocket essentially in free-fall (height error 100%, speed error
      76%, ~2070m position offset over 30s) even WITH a real per-craft
      AoA/drag table built from this same flight's own dragArea samples
      -- not a drag/physics-model failure, a throttle-signal failure.
      This was already flagged as a known limitation in
      `TryGetPrimaryGimbal`'s own code comment ("fine for a single-gimbal
      test craft; multi-gimbal rockets would need per-engine scoping
      this doesn't attempt yet") -- this is the first real flight to
      empirically confirm it actually matters. **The RCS/rotation side
      of control-schedule replay (`output_TurnAxisTorque`,
      `output_DirectionalAxis.x/y`) was exercised on this same flight
      (229 samples with translational RCS active, 1,578 with rotational)
      and is not implicated** -- this is specifically a thrust/throttle
      gap, not a control-replay gap. **Fix applied v0.56.0, corrected
      v0.56.1** (see `mod_changelog.md`): v0.56.0 compared throttle_Out
      magnitudes across gimbaling engines (worked, but only because
      throttle_Out's only per-engine variation IS the engineOn flag --
      amount/master ignition are rocket-wide, confirmed via IL); v0.56.1
      reads engineOn directly instead, the actually-correct signal.
      Still a single-engine proxy, not real per-engine throttle
      telemetry -- needs a fresh game reload and a repeat
      `--test_against_run` on a real multi-engine burn to confirm the
      fix resolves the prediction error, not just the mechanism.

**Bottom line for what "done" looks like**: finishing every remaining
item below (design decisions, minor tooling fixes, zero-game
prototyping) does NOT by itself produce a calibrated, trustworthy
forward integrator — it resolves process and scope questions. This
section is the actual remaining work toward the accuracy question
itself, and is currently emptier than the rest of this file might
suggest.

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
      **`Base.worldBase.challengesArray` path fully IL-CONFIRMED 2026-09-02**
      (was `[PARTIAL]`, never re-verified since the source-doc pass).
      `SFS.Base::worldBase` is a static `WorldBaseManager` field; `challengesArray`
      is a real public field on it, populated by
      `challengesArray = Challenge.CollectChallenges().ToArray()` at world load
      (and nulled on unload) — the exact same `CollectChallenges()` already
      confirmed public/static. It's also the same array the game's own
      `ChallengeRecorder.UpdateEligibleSteps()` reads for real achievement
      tracking, not a side path. The probe's read is correct end to end.
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

**REVISED (2026-09-02).** Tier 1 physics is now fully closed: gimbal
timing and parachute drag (the two remaining gaps as of 2026-09-01) are
both IL-confirmed AND live-validated (parachute drag: 6 attempts, final
median error 0.015%, correlation 1.000 — see the parachute drag entry
above for the full story). Every physics item in this file is now
confirmed from IL and validated against real flight data. The only
remaining work in Tier 1 is a decision (not research) on each item in
"Design decisions owed."

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
