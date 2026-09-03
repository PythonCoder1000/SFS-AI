# Python — Changelog

Tracks Python-side work for the SFS agent: physics models, solvers,
analysis scripts, and (later) the design/flight agent code itself.
Not version-numbered like the mod — dated entries, newest first.

---

## 2026-09-02 (latest) — `--test_against_run`: control-input replay, real per-thruster RCS, mass-penalty fix

- **New: `getforwardstartinfo`-driven craft_config.** Added
  `load_craft_config_from_getforwardstartinfo()`, translating the
  probe's new `getforwardstartinfo` command (mod v0.54.0) into
  `forward_simulate`'s `craft_config` -- real per-part thrust/ISP/
  geometry/thresholds read live from the actual rocket, not empirical
  fits or hand-entered guesses. This is what "finishes" the forward
  integrator: it was previously always missing a real data source for
  this input.
- **New: `ControlSchedule` / `load_control_schedule()`.** Replays a
  real flight's REAL recorded control INPUTS
  (`output_TurnAxisTorque`, `output_DirectionalAxis.x/y`, optionally a
  throttle field) as t->value step functions (deliberately NOT
  interpolated -- a real control input is discontinuous between ticks).
  `forward_simulate` gained a `control_schedule` parameter: when
  supplied, turn_axis/directional_axis/throttle come from the real
  recording instead of being predicted (SAS, zero-RCS-input, constant
  throttle). Separates "does the confirmed physics predict correctly"
  from "can this module guess pilot behavior."
- **New: `test_against_run()` + `--test_against_run` CLI flag.** Runs
  the above end-to-end against a real flight and reports predicted vs
  actual height/speed/position error, same methodology as
  `prediction_demo.html`.
- **Real bug found and fixed during this pass (caught by a smoke test
  against tonight's actual flight, not by inspection):** the first
  version of the control_schedule wiring skipped `apply_sas` entirely
  when a schedule was active (reasoning: turn_axis is already resolved,
  don't re-predict it via SAS) -- but `apply_sas` was ALSO the only
  place the confirmed rotation formula's omega UPDATE happened, so
  skipping it silently stopped integrating rotation at all. Caught via
  a real-flight smoke test: predicted theta diverged ~39° over 5s.
  Fixed by splitting `apply_sas` into `compute_turn_axis` (SAS's OWN
  turn_axis prediction) + a new `apply_rotation_update()` (the actual
  physics integration step, given ANY turn_axis regardless of source).
  Re-tested after the fix: predicted theta within **0.029°** of the
  real recorded value over a 5s control-replay window (wrapped mod
  360°) -- aero torque was deliberately zeroed in the smoke test's
  minimal craft_config, which explains the remaining omega-endpoint
  mismatch, not a code issue.
- **`_rcs_force` fully rewritten** to replicate REAL per-thruster
  `TorqueThrust`/`DirectionThrust` selection (confirmed IL, D3.1-D3.3)
  each call, given real per-thruster geometry + thresholds from
  `getforwardstartinfo`, instead of a precomputed static
  `sum_normal_local` direction that could only ever represent rotation,
  never real translational RCS firing (a genuine gap, confirmed missing
  during today's earlier RCS validation session, not a known
  simplification until this rewrite).
- **`compute_turn_axis`/`apply_sas` mass>200t penalty fix:**
  previously expected an already-penalized `torque_effective` constant
  from the caller; now correctly re-derives the penalty from the LIVE
  (possibly integrated, changing) mass every call. Wrong before for any
  sim whose mass crosses 200t mid-burn -- moot for any flight logged so
  far (max mass this project has seen is ~115t), but a real correctness
  fix for future heavier craft.
- **`_engine_thrust` gained `throttle_override`** for the same replay
  mechanism, applied uniformly across all engines (documented
  approximation -- no flight logged so far captured genuine per-engine
  throttle, only `gimbalThrottleOut`'s single-representative-engine
  scoping).
- Everything above is ADDITIVE and backward-compatible: no
  `control_schedule` supplied means identical behavior to before this
  pass (verified via a blind-mode regression check in the same smoke
  test).

---

## 2026-09-02 (later) — `forward_sim.py` parachute drag + rotation VALIDATED

- **Updated `forward_sim.py`'s top-of-file disclaimer** (previously
  "NONE of it has been validated") to reflect the real result of a
  flight this same day: `parachute_drag`'s exact formula as wired into
  this module (confirmed gravity + `parachuteForceX/Y` / real per-tick
  mass) checked against real telemetry — correlation 1.000, 100% sign
  agreement, median error 0.015%. No formula change was needed; the
  IL-confirmed formula was already implemented correctly, this pass
  only updates validation status. Also independently reconfirmed the
  body-fixed rotation formula (theta/omega integration) across 3 real
  staging events on a different flight — resolves the "rotation sign
  convention assumed-not-confirmed" item from the 7 documented
  Bucket-A simplifying assumptions (now 6). See
  `bookkeeping/active_state.md` and `docs/high_level_checklist.md` for
  the full 6-attempt parachute-drag story and the staging-event
  rotation fit. Everything else NEW in the 2026-09-02 Bucket-A
  integration pass (thrust, fuel_burn, gimbal discrete timing as wired
  into this module, RCS force+torque, heat, terrain, staging) remains
  explicitly unvalidated end-to-end in this module.

---

## 2026-09-02 — AoA -> dragArea empirical lookup table (`aoa_dragarea.py`)

- **Built `analysis/aoa_dragarea.py`**, replacing `forward_sim.py`'s
  frozen-starting-value `dragArea` with a per-craft angle-of-attack
  lookup, per the plan recorded in `active_state.md`'s "Immediate next
  experiment". `dragArea` is a deterministic function of AoA alone for
  a fixed rigid craft design — this builds an empirical table straight
  from real telemetry rather than porting live per-part geometry
  (still blocked on the surface-mount-part gap).
- **AoA convention**: `heading = rot + 90` (matches
  `sfs_source_reference.md` §B1.4's `GetRotation()` `ControlModule`
  fallback path, same `atan2(y,x)` frame as velocity heading); `AoA =
  wrap(heading - velocity_heading)` to `[-180, 180]`.
- **No fresh calibration flight needed** — checked the existing
  2026-08-31 aero-torque validation flight
  (`flight01_truth_2026-08-31_19-57-17.jsonl`, 4,969 samples,
  `partCount` stable at 19 throughout) first, per the plan, and it
  already sweeps the full `-180..+180` deg range with a physically
  sensible pattern (`dragArea` minimal `~3.5` near 0 deg AoA, rising to
  `~9-10` i.e. `~2.5-2.8x` at high AoA).
- **Table**: 2-degree bins (180 total), median `dragArea` per bin, 0
  empty bins, 13/180 low-confidence (<5 samples). Saved to
  `analysis/aoa_dragarea_table_capsule_reentry.json`.
- **Held-out validation** (train on even-indexed samples, test on
  odd-indexed, 2,484 test pairs, genuinely unseen during table
  construction): **median error 0.25%, mean 0.31%, p90 0.67%, max
  2.01%** — tight, in the same range as several of this project's other
  confirmed physics formulas.
- **Table is per-craft-design specific**, not general — encodes one
  part list/geometry via a `craft_signature` fingerprint (`heatParts`
  names + `partCount`). Reusing it for a different rocket is invalid; a
  different design needs its own table built the same way.
- **Not yet done**: wiring `lookup_dragarea()` into `forward_sim.py`'s
  `accel()`. That also requires adding rotation state (`theta`,
  angular velocity) to the integrator, plus the confirmed rotation
  formula and aero-torque formula — `dragArea` alone isn't enough
  without the integrator tracking its own evolving orientation.

---

## 2026-09-02 (continued) — wired AoA→dragArea into forward_sim.py; rotation state added; coordinate-frame gotcha found

- **`forward_sim.py` rewritten** with a rotating-state integrator:
  state now includes `theta` (orientation, deg) and `omega` (angular
  velocity, deg/s) alongside the original `px,py,vx,vy,m`. `dragArea`
  is looked up from the AoA table at every RK4 sub-step instead of
  staying frozen at the starting sample's value — the translational
  wiring asked for is fully working and requires no extra live data
  (dragArea is pure geometry, zero altitude/density dependency,
  confirmed via IL).
- **Old frozen-dragArea/no-rotation behavior preserved** as a fallback
  when no `aoa_table` is passed (`forward_simulate(..., aoa_table=None)`)
  — verified byte-for-byte equivalent to the pre-rewrite version on a
  synthetic test case.
- **Aero-torque model implemented** (`compute_aero_torque()`), following
  `sfs_source_reference.md` §C1.10's confirmed formula exactly:
  `torqueZ = (cop_applied - com_local) × F_drag`,
  `alpha_deg = (torqueZ / inertia) * 57.29578`. **Verified numerically**
  against the real live-read snapshot in `sfs_probe_aerotorque.json`:
  reproduced `torqueZ=11.018437336` against the probe's own
  `11.018437386` (float32 rounding only), and
  `alpha_deg=1.5770399538` against `1.5770399570`. The `*57.29578`
  rad→deg factor is **not explicit in the doc's pseudocode but is
  required** — confirmed here for the first time; `sfs_source_reference.md`
  §C1.10 should get a one-line addition noting this.
- **Coordinate-frame gotcha found and documented, not previously
  flagged anywhere:** `dragCopX`/`dragCopY` and `worldCenterOfMass`
  (needed for the torque formula) live in Unity's small-scale LOCAL
  physics frame (floating-origin-relative, order ~10^2–10^3) — **not**
  the same frame as `Location.position` (`px,py`, order ~10^5–10^6,
  used everywhere else in this project for gravity/translation).
  Mixing them (e.g. treating `px,py` as `worldCenterOfMass`) silently
  produces a nonsense torque — caught only because a first attempt at
  computing torque from archived flight data returned exactly 0.0 for
  every single tick, which traced back to this, not (as first
  suspected) to the flight being in vacuum (see below — that was also
  true, but a separate issue).
- **`inertia` and `com_local` are required parameters, deliberately
  not fabricated or defaulted.** A `sfs_probe_aerotorque.json` snapshot
  existed with a real `inertia` value (400.313232421875), but its
  `craft_signature` does NOT match the AoA table's craft (verified via
  `aoa_dragarea.craft_signature` on both flights' first samples) —
  reusing a different craft's inertia would be worse than not modeling
  torque at all, so it was not used. If `inertia`/`com_local` aren't
  supplied, `theta` still advances kinematically from the starting
  `angv`, but `omega` stays frozen (zero-torque assumption) rather than
  silently guessing.
- **Found the AoA table's source flight is entirely above the
  atmosphere** (h=81,510–91,078m, ceiling is 30,000m) — confirmed by
  checking every sample's `h`. The wide AoA sweep used to build the
  table is the craft freely tumbling in vacuum from momentum
  conservation after stage separation, not atmosphere-driven
  weathercocking. Doesn't affect `dragArea`/`centerOfDrag` validity
  (pure geometry, no altitude dependency) but means this flight cannot
  be used to derive or validate real aero-torque magnitude or a
  craft's `rb2d.inertia` — a genuinely different flight (real
  atmospheric descent, h<30,000m) or a fresh live `aerotorque` read is
  needed for that.
- **`aoa_dragarea.py` extended** to bin `dragCopX`/`dragCopY` alongside
  `dragArea` (generalized `build_table`/`lookup_field`, kept
  `lookup_dragarea` as a backward-compatible wrapper). Table rebuilt;
  held-out validation unchanged (median 0.25%, mean 0.31%, p90 0.67%).
- **End-to-end validation against real flight data:**
  - Translational (position/altitude) prediction: mean **0.001% error**
    over four 10s forward-sims from different points in the flight —
    matches the project's established noise floor, confirms the new
    integrator introduces no regressions.
  - Rotation (`theta`) prediction, zero-torque fallback: **works
    exactly where the assumption holds, fails informatively where it
    doesn't.** Real `angv` is nonzero (active tumbling/SAS correction)
    for samples 215–2230, then drops to exactly 0 and stays there
    (SAS-locked steady state) for the rest of the flight. Forward-sims
    started inside the locked window matched real `theta` exactly
    (0.00° error); forward-sims started inside the active window
    diverged substantially (49.7°, 178.5° error at 10s) — expected and
    correct behavior, since the zero-torque model doesn't (and isn't
    meant to) capture SAS's active correction or real time-varying
    torque. Not a bug; documents exactly what this fallback does and
    doesn't cover.
- **Not yet done:** a live `aerotorque` read (`inertia` + `worldCenterOfMass`)
  for the AoA table's actual craft, taken while it's in real atmosphere,
  to activate and validate the full torque model end to end. Also not
  done: modeling SAS itself (fully confirmed, §B1.3/§2.4 — deadbeat
  controller nulling `angularVelocity` within one tick's authority
  whenever `hasControl && !IsOnSurface` and no manual input), which
  would be needed to match real hands-off flight behavior beyond pure
  aero torque.

---

## 2026-09-02 (continued) — SAS added to forward_sim.py; found and documented the RCS torque-damping gap

- **`apply_sas()` added** to `forward_sim.py`, implementing the
  confirmed deadbeat SAS formula
  (`sfs_source_reference.md` §B1.3 / `sfs_physics_reference.md` §2.4)
  exactly: `omega -= torque_effective*57.29578/mass*clamp(omega/delta,-1,1)*dt`.
  Applied once per RK4 outer step (not a fine-grained inner tick loop) --
  **proved mathematically, then confirmed empirically, that a single
  big-step application is EXACT for the pure-SAS mechanism** (chaining
  the real per-tick formula many times over the same window gives an
  identical result, differing only in the 17th decimal place).
- **Validated against this exact craft's own real flight data**
  (same flight the AoA table was built from -- entirely vacuum, so no
  aero-torque confound): using the craft's own real `torque=5` field
  (`SumEnabledTorque`, confirmed via `SFSProbe.cs`) and real per-tick
  mass, single-tick predictions across all 4,168 real hands-off
  (`turnAxis==0`) ticks: **median error exactly 0.0 deg/s**, mean 0.15,
  p90 0.61, max 0.75.
- **Found and documented a real, honest gap, not swept under the rug:**
  the near-zero aggregate error hides that it's concentrated almost
  entirely in low-`|omega|` ticks. Digging into where the larger errors
  cluster: stretches with `|omega| >= 2 deg/s` show a consistent
  ~0.45-0.61 deg/s UNDER-prediction of real deceleration PER TICK,
  compounding to ~30+ deg/s of error over a 1-second window. Root cause
  identified and confirmed, not just suspected: `RcsModule.TorqueThrust`
  (`sfs_source_reference.md` §D3.2) fires RCS thrusters for rotational
  damping whenever `|angularVelocity| >= 2` deg/s -- exactly the regime
  where the gap appears -- and this craft's own recorded `rcsFiring`
  field confirms 5 of 6 RCS thrusters were actively firing throughout
  the high-omega stretches checked. RCS's torque contribution is a
  SEPARATE mechanism (real `AddForceAtPosition` physics, needing
  per-thruster position + `rb2d.inertia` -- same class of missing
  ingredient as the aero-torque model) and is **not modeled**. Net:
  `apply_sas()` is accurate under ~2 deg/s or on any RCS-disabled craft;
  under-predicts real hands-off damping on a spinning RCS-equipped craft.
- **`torque_effective` required as an explicit parameter**, same
  treatment as `inertia`/`com_local` -- never fabricated. For this
  specific craft it's legitimately available from the same flight's own
  `inputs.jsonl` (`torque=5`), not borrowed from a different craft.
- **Also found in passing, while investigating an initial apparent
  discrepancy that turned out not to be a bug:** a low-`|omega|` window
  (angv~0.3 deg/s) where SAS's confirmed formula predicts an immediate
  null but the real craft's angv stayed completely flat for a full
  second. Most likely explanation: `hasControl` was false during that
  window (e.g. camera/focus elsewhere) -- SAS's gate
  (`hasControl && !IsOnSurface`) requires it, and we have no
  per-tick `hasControl` telemetry to confirm either way. Documented as
  an open unknown, not resolved.
- **Regression-checked:** translational (position/altitude) accuracy
  unchanged (0.001% mean error, same four-point test as the dragArea
  wiring); backward-compatible frozen-dragArea path still works
  unmodified.

---

## 2026-09-02 (continued) — isolation flags added to forward_sim.py

- **`flags` parameter added** to `forward_simulate()`/`accel()`/`_rk4_step()`:
  `{"gravity", "drag", "aero_torque", "sas"}`, each defaulting to `True`.
  Lets a divergence between predicted and real be narrowed to ONE
  physics component (e.g. `flags={"drag": False}`) instead of guessed
  at, without needing to strip out the corresponding data
  (`aoa_table`/`inertia`/`com_local`/`torque_effective`) to test it --
  "I have the data but want this off for a test" is now separate from
  "I don't have this data" (the pre-existing `None`-means-off
  behavior); both work independently.
- Unknown flag names raise `ValueError` immediately (fails loud, not
  silently ignored).
- **Verified**: all-flags-off reduces to exact constant-velocity
  straight-line motion (analytic check, not just "looks plausible").
  `flags={"sas": False}` on a real validated case correctly freezes
  omega at its starting value instead of nulling to 0, isolating
  exactly what the flag claims to isolate. Default flags (all `True`)
  reproduce byte-identical results to the pre-flags code on every
  existing regression check (0.001% mean h error, 0.0 deg/s SAS median
  error) -- adding the flag layer introduced no behavior change when
  left at defaults.

---

## 2026-09-02 (continued) — Bucket A fully integrated into forward_sim.py (INTEGRATION-ONLY PASS, no flight validation)

**Scope: every remaining Bucket A item from active_state.md's physics
status list wired into the predictor** -- thrust, fuel burn, gimbal,
RCS (force + torque), parachute drag, staging separation, heat
accumulation, terrain collision. Explicitly NOT validated against any
real flight in this pass -- that was out of scope for the task this was
written under. Backup of the pre-integration file saved as
`forward_sim.py.bak-pre-bucketA`.

**State model expanded**: continuous RK4-integrated state grew from
(px,py,vx,vy,m,theta,omega) to (px,py,vx,vy,m,theta,omega,heat_temp) --
mass is now a real integrated state (was frozen), heat_temp is new.
Discrete post-step state added: gimbal_times (one per gimbaled engine).
SAS/gimbal/RCS/staging/terrain are all DISCRETE post-step corrections
(operator splitting), not blended into the continuous derivative --
matches how SAS was already handled, extended to the new mechanisms for
the same reason (all are genuinely discrete/gated/rate-limited, not
smooth ODEs).

**Formulas used, all pulled directly from sfs_physics_reference.md /
sfs_source_reference.md, re-read this session rather than assumed from
memory:**
- Thrust (section 2.2), fuel-flow rate incl. the `scale` term
  (section 1.3), multi-engine as N independent forces not a resultant
  (section 5.2)
- Gimbal (section B1.10): target = turnAxis_Input * rotation_direction
  = the SAME signal SAS uses (compute_turn_axis() extracted so both
  reuse one implementation); MoveTowards rate-limited chase, confirmed
  linear on the one real engine read live
- RCS (section 5.3): gate is `|turn_axis| >= 0.95 OR |omega| >= 2` --
  **caught and fixed during design, not left in**: an earlier draft
  used `|omega| >= 2` alone and would have MISSED the common case where
  SAS saturates turn_axis to +-1 well before omega reaches 2 deg/s on a
  weak-torque craft. Force per-module (not pooled -- the ~6x
  overstatement mistake already caught once in this project, guarded
  against again here).
- Parachute drag (section 2.8): refactored `_aero_force_and_cop()` to
  match the confirmed pseudocode's pre-density/pre-direction
  intermediate `force` scalar exactly, so base drag and parachute
  blending share ONE implementation (previously would have been
  duplicated between the translation and torque call sites).
- Staging (section 2.7): momentum conservation; angular velocity
  confirmed to carry over unchanged, not touched by a staging event here
- Heat (section 5.1): reused sfs_telemetry.py's ALREADY-VALIDATED
  (0.18% mean peak error) absorb/dissipate rates verbatim rather than
  re-deriving from the formula text, specifically to avoid re-risking
  the additive-vs-multiplicative bug already found and fixed once in
  this project's air-temperature formula
- Terrain (section 5.4): flat-datum fallback when no live
  `terrain_lookup` supplied

**Integration-only validation performed (NOT flight validation)**: syntax
check, then 15 targeted crash/edge-case checks (all-flags-off reduces to
an exact analytic straight line; inertia=0, isp=0, mass->0 without a dry
mass floor, gimbal animation_time=0, r->0 degenerate case, empty
engines/rcs/parachutes lists, unknown flag names, staging ejecting more
mass than exists, terrain collision early-stop, backward-compat frozen
path) plus 40 randomized-parameter trials checking every output field
stays finite (no NaN/Inf) across random combinations of engines/RCS/
parachutes/staging/inertia-presence/terrain. All passed. Built and
syntax/crash-tested in an isolated sandbox first, transferred only after
passing, to avoid leaving a broken file on a real machine mid-session.

**Known deviations/assumptions, honestly flagged, not silently
buried -- see the integration report for the full writeup:**
1. Body-fixed vector rotation convention (CCW-positive, standard Unity
   default) is ASSUMED, not independently IL-confirmed for arbitrary
   part positions specifically.
2. RCS/SAS/gimbal execution order within one step is a REASONED,
   defensible choice (matches the confirmed pseudocode's described
   order), not proven to exactly match Unity's actual per-tick script
   execution order (which this project's own docs note is NOT a
   guaranteed call chain elsewhere).
3. Heat is a single representative "hottest part" scalar, not full
   per-part tracking (a real scope limit, not an approximation
   presented as complete).
4. Parachute drag_curve uses linear interpolation, not the real Hermite
   AnimationCurve (no real chute keyframes have been read live, unlike
   the one gimbal curve that was).
5. Gimbal's discrete big-step timing has NOT been proven exact under
   RK4 operator splitting the way SAS's deadbeat law was (SAS's
   telescoping proof doesn't extend to gimbal's different, rate-limited-
   toward-a-moving-target mechanism).
6. Staging's velocity-kick term (`eject_delta_v_local`) has no source of
   real values -- `separationForce` is an unread parametric expression
   for any specific craft; defaults to zero (pure mass drop) unless the
   caller supplies real data.
7. `position_local` for engines/RCS/parachutes is defined here as
   CoM-relative by this module's own convention, not something
   IL-confirmed to be suppliable directly in that frame -- caller's job
   to get this right.

---

## 2026-08-30 (later same day) — heat formula bug found and fixed via direct live comparison; HEAT FULLY CLOSED

- **Root-caused and fixed a real transcription bug** in
  `predicted_reentry_temperature`'s ascent-correction term. An earlier
  documentation pass recorded it as multiplicative
  (`t += t * (tempOffset·X + 0.2)`); the real IL (re-read directly from
  `scratch/full_il.txt`, not re-derived from the old doc) is additive:
  `t += tempOffset · (X + 0.2)`. With `tempOffset=-500` confirmed live,
  the wrong multiplicative version drove `t` deeply negative whenever
  the ascent term neared its `0.4` cap, silently collapsing the whole
  formula to `0` during real ascent-phase heating — which is exactly
  the symptom that led to catching this: a live-vs-Python comparison
  (`realAirTemp`, a new sfsprobe v0.43.0 telemetry field calling
  `AeroModule.GetTemperatureAndShockwave` directly) showed the real
  game reporting up to 1439°C air temperature during ascent while the
  Python formula returned exactly 0.00 at the same instants.
- **Verified against the game's own live computation, not just
  self-consistency:** 2,989 real samples across a full ascent-to-
  reentry flight, comparing `predicted_reentry_temperature`'s output
  directly against `AeroModule.GetTemperatureAndShockwave`'s real
  return value at the same tick. **Median error 0.0000%, mean 0.0001%,
  max 0.0047%** — effectively exact, floating-point-level agreement.
- **This also fully explains the ~50% heat-accumulation overprediction**
  chased earlier the same session (which the `ExposedSurface`-filtering
  fix, v0.41.0, only partially closed to ~46.6%): the wrong
  multiplicative version added a spurious ~20% bonus to `t` every
  single tick during descent, and that error compounds across the
  ~1000+ ticks of a real reentry integration far more than a one-off
  formula error would suggest.
- **Re-ran the full per-part `ApplyHeat`/`DissipateHeat` accumulation
  model** (same one built earlier this session, now using both the
  corrected formula and the correctly-filtered `ExposedSurface`) against
  a real destruction event (3 Hawk Engines, symmetric, all crossing the
  confirmed 412°C threshold together): **mean peak-temperature error
  0.18%** across all 7 heated parts (0.09–0.30% individually) — tighter
  than or matching every other confirmed formula in this project
  (drag: 0.098%, gravity: 0.008–0.13%, multi-engine: 0.14%).
- **Heat is now fully closed**: formula confirmed exact against the
  game's own live output, full accumulation model validated against a
  real destruction event, coefficients read live, `ExposedSurface`
  correctly filtered through the real `RemoveHighSlopeSurfaces`/
  `ApplyProtectionZone`. No remaining open items in the heat model
  itself — only RCS and terrain remain unvalidated among the original
  four "confirmed from code, untested live" physics items.

---

## 2026-08-30 (later same day) — multi-engine LIVE-VALIDATED

- **Real flight test of the "no summation, N independent forces" model**
  (confirmed via IL in an earlier session, never flight-tested until
  now). Christian hand-built a real symmetric 3-engine rocket in the
  editor (three parallel Fuel Tank+Engine Hawk columns at x=8/10/12,
  shared capsule+parachute+nose cones) after magnet-based stacking
  turned out unable to place two engines in series (an engine is a
  single-connector "cap" part — real, useful negative finding, logged
  in `blueprint_builder.py`'s docstring context).
- Flew it full-throttle for ~26s (1,594 samples). Validation method:
  sum 3 independent per-engine thrust contributions (each
  `thrustNormal · thrust · 9.8 · throttle_Out`, no shared resultant —
  this IS the "no summation" model, not a simplification of it) plus
  the confirmed gravity+drag formula, compare against measured
  (finite-difference) acceleration.
- **Result: 1,576 clean pairs, median error 0.14%, mean 0.21%** —
  tighter than the 0.098%-median drag validation, this project's
  previous best. Strong, direct confirmation the multi-engine model is
  correct, not just plausible.
- **18 outlier pairs found and explained, not silently dropped:** 16
  were a finite-difference artifact — one tick in the recording had
  irregular (half-length) spacing, which distorts a central-difference
  "measured" acceleration that assumes even spacing. The remaining 2
  were a genuine one-tick `engineOn` flicker on a single engine (all 3
  on at one sample, one dropped to off+throttle 0 the very next sample,
  then presumably back on), most likely an asynchronous fuel-draw
  transient across the rocket's 3 separate tanks — not investigated
  further, flagged rather than hidden.
- `partCount` held at 10 for the entire burn, confirming the hand-built
  rocket was genuinely one rigid connected craft, not three separate
  physics bodies that happened to look adjacent.
- **This flight is also what surfaced sfsprobe's long-standing
  `AmbiguousMatchException`** on engine reads clearly enough to finally
  root-cause and fix it (v0.37.0, see `mod_changelog.md`) — a pad-idle
  sanity check before this flight showed EVERY engine read failing, not
  the rare one-off it had previously looked like.

---

## 2026-08-30 — `predicted_reentry_temperature` (AeroFormula.GetTemperature port)

- **Added to `sfs_telemetry.py`: `predicted_reentry_temperature` +
  `predicted_reentry_temperature_for_sample`.** Full port of
  `AeroFormula.GetTemperature`, confirmed via IL
  (`docs/sfs_reference/02-drag-aero/AeroFormula.md`), now runnable end
  to end because the last two unknowns got read live today:
  - The 4 `AeroFormula` coefficients (`velPow=1.85`, `densityPow=2.2`,
    `tempOffset=-500`, `m=1.47`) via the new `aeroformula` probe command
    (sfsprobe v0.36.0).
  - Earth's `atmospherePhysics.minHeatingVelocityMultiplier=1.0` and
    `shockwaveIntensity=1.0` via the new `atmophysics` probe command
    (sfsprobe v0.36.1) — the ctor default happened to match, but per the
    project's data-trust rule this was read, not assumed.
  Difficulty multipliers (`HeatVelocityMultiplier`/
  `MinHeatVelocityMultiplier`) are assumed **Normal** (1.0/1.0), matching
  every other empirical check this project has run (e.g. `ispMultiplier
  = 1.0000`) — flag if a flight was ever actually run on Hard/Realistic.
- **This is the GLOBAL instantaneous air temperature (the forcing
  input), not a per-part accumulated temperature.** `HeatManager
  .ApplyHeat`'s absorption/dissipation integration over time is a
  separate step, **not yet implemented in Python** — this function
  answers "how hot is the air right now", not "how hot has this part
  gotten."
- **Sanity-checked against the real 73,108-sample reentry flight**
  (`flight01_2026-08-29`, the same one behind the 0.098%-error drag
  validation): predicted air temperature is essentially zero for the
  whole vacuum-coast portion above 30km (atmosphere cutoff engaging
  correctly), then ramps sharply exactly during the real high-speed
  low-altitude descent (~t=1089–1100s, h≈20,000m→10,000m, v≈1700m/s),
  peaking near 5900°C as *air* temperature — physically consistent with
  why the actual PART temperature (subject to slow absorption) crossed
  the 412°C break threshold and started shedding parts right around
  that same window. Not a full validation (that needs the part-level
  integration plus a fresh flight recorded with the fixed `GetHeatState`
  — see below), but strong corroborating evidence the formula's right
  before investing in that integration layer.
- **Next step:** implement `HeatManager.ApplyHeat`/`DissipateHeat`'s
  per-part accumulation in Python, then fly a fresh reentry (the
  existing archived flight predates the `GetHeatState` fix in sfsprobe
  v0.36.0, so its `maxTemp` telemetry may be silently wrong for any
  `HeatModule`-carrying part) to get real per-part temperature data to
  validate the full accumulation model against, not just this
  instantaneous forcing-function sanity check.

---

## 2026-08-29 (later same day) — forward_sim.py + interactive trajectory-prediction demo

- **Added `python/forward_sim.py`.** Forward-integrates (RK4, not Euler)
  the CONFIRMED gravity+drag formula — a verbatim port of
  `sfs_telemetry.py`'s `predicted_gravity_drag_accel`/
  `atmospheric_density`, not reimplemented from scratch — starting from
  any real telemetry sample, for a chosen duration. Built to power an
  interactive predicted-vs-actual trajectory demo using the exact
  physics validated that same day at 0.098% median error across 70,858
  pairs (see `docs/high_level_checklist.md`, "Drag FORCE formula").

  `dragArea` is deliberately held constant at the starting sample's
  real value for the whole prediction window — a documented
  simplification (valid for an unpowered coast, where orientation stays
  roughly fixed), not an oversight; noted in the module docstring as
  something that would need revisiting for a window including active
  thrust/rotation/staging.

  `prep_demo_data()` loads a real archived flight, downsamples it for
  embedding in a UI, and runs a **self-test** before shipping any
  numbers into a demo: a 10s forward-simulation from a real mid-flight
  sample, compared against the ACTUAL recorded trajectory at the
  matching later timestamp. Against the real 73,108-sample drag-
  validation flight: **0.0001% altitude error** — confirms the RK4 port
  matches the validated formula before any UI gets built on top of it,
  rather than assuming the port is correct.

- **Built an interactive React artifact** (`TrajectoryPredictor.jsx`,
  delivered directly, not committed to this repo) on top of
  `forward_sim.py`'s output: pick a real sample (slider) and a
  prediction duration (slider), see the live-computed predicted
  trajectory (JS port of the same RK4 physics) overlaid on the real
  recorded one, with a numeric predicted-vs-actual comparison at the
  end of the window. Deliberately surfaces the real, still-unexplained
  divergence zone found during validation (26–30km altitude,
  high-speed ascent) as a shaded region when a chosen window crosses
  it, rather than hiding a known limitation behind a clean-looking demo.

## 2026-08-29 (later same day) — blueprint_builder.py + sfsprobe_build_stack_blueprint

- **Added `python/blueprint_builder.py`** — builds SFS blueprints from a
  part list using REAL, empirically-confirmed magnet-point data instead
  of guessed positions. Confirmed 2026-08-29 against a real hand-built,
  connected 4-part rocket (see `docs/high_level_checklist.md`,
  "Blueprint construction"): SFS's part-connection system is
  `SFS.Builds.HoldGrid` + `MagnetModule`, not a coordinate-snap grid. A
  part's own position ("pivot") is NOT its geometric center —
  `MagnetModule.points` are local offsets FROM that pivot. The
  magnet-chain formula (`next_pivot = prev_pivot + prev_exit_offset -
  next_entry_offset`) is exact against real data, not derived from the
  centerOfMass/height heuristics tried first (which produced a
  too-narrow tank and an overlapping parachute).

  Pure, testable functions, no game interaction: `scout_blueprint`
  (rough far-apart placement, just to turn parts into placed instances
  so their real magnet points become readable), `build_stack_from_scout`
  (the actual chaining math + centering — also the fix for the
  "blueprints end up off to the side" bug), `write_blueprint`,
  `check_connectivity` (uses the game's own live `occupied` flag rather
  than reimplementing collision geometry). Sanity-tested directly
  against today's real confirmed numbers — relative spacing matched
  exactly.

  **Explicit, deliberate limitation:** parts with no `MagnetModule`
  (`magnetPoints: null`, confirmed for `Parachute`, `Parachute Side`,
  `Side Separator` — likely all "surface-mount" parts) raise
  `SurfaceMountPartError` rather than silently guessing a position. Real
  geometry/edge-matching (`HoldGrid.CollectSurfaceSnaps`) is a separate,
  harder, deliberately-deferred problem — see the checklist.

- **Added `sfsprobe_build_stack_blueprint`** to `sfsprobe_mcp` — the live
  orchestration on top of the pure module: scout-place → read real
  magnet points via the mod's `getplacedmagnets` (v0.35.5) → compute the
  correct stack → write and load the final blueprint → re-verify real
  connectivity via the `occupied` flag rather than assuming success from
  a successful load call alone. Compiles and imports clean. **Not yet
  live-tested end to end** — the underlying primitives
  (`loadblueprintbuild`, `getplacedmagnets`) are each individually
  confirmed working; this specific new orchestration hasn't been run.

## 2026-08-29 — reference_audit.py (template compliance checker)

- **New `python/reference_audit.py`.** Mechanically enforces the
  `Preconditions` rule added to `docs/sfs_reference_plan.md` the same day:
  every `#### ` method entry under a **FULL**-depth type must carry a
  `- **Preconditions:**` bullet. An absent field looks identical to "not
  checked yet", which is precisely the gap behind the `loadblueprint`
  `World_PC`/`Build_PC` incident, so it is checked by a script rather than
  by discipline.
- Also reports FULL-depth types that document **no** method entries at all.
  Not a failure — many types genuinely have none beyond a
  compiler-generated constructor — but a FULL-depth type with no methods
  written up is worth eyeballing.
- Two modes, matching `reference_index.py`'s convention:

  ```bash
  python3 python/reference_audit.py            # full report
  python3 python/reference_audit.py --check    # silent on pass, exit 1 on fail
  ```

- **First run found 166 of 216 FULL-depth method entries missing the
  field** — every one of them in the 43 files produced by Phase 1 Step 1
  (migration), which predates the rule. The four Step 2 files written on
  2026-08-29 pass. Backfilling the migrated corpus is tracked in the
  session handoff, not done here.
- Skips the five standalone files (`INVENTORY.md`, `INDEX.md`,
  `METHODOLOGY.md`, `REFLECTION_TOOLKIT.md`, `CORRECTIONS.md`), which
  deliberately do not follow the per-class template.

---

## 2026-08-29 — blueprints/ folder + sfsprobe_load_blueprint tool

- **Created `blueprints/`** at the project root, split into `research/`
  (usable now — hand-crafted/exploratory designs, including the first
  test blueprint `single_capsule`) and `live/` (not used yet — reserved
  for once the design agent is built and connected, kept separate so
  it's always clear which designs came from a human/manual process vs.
  the agent itself).
- **`sfsprobe_load_blueprint`** added to `sfsprobe_mcp` (Stage 12) —
  wraps the new mod command (`loadblueprint`, v0.30.0). Resolves a
  blueprint by `name` (looked up in `blueprints/research/`) or an
  explicit `path`, sends the command, and maps the mod's distinct
  `reason=` failure tokens to proper `error_code` values
  (`NOT_IN_DESIGN`, `FILE_NOT_FOUND`, `FILE_ERROR`,
  `TYPE_RESOLUTION_FAILED`, `PARSE_ERROR`, `SPAWN_FAILED`) — exactly the
  distinguishable-failure-reasons behavior asked for, not one generic
  error.
- Path-resolution logic (name lookup, missing-blueprint case,
  missing-both-name-and-path case) smoke-tested directly — all correct.
  **The actual spawn call itself has not been tested live yet** —
  needs a game reload (to pick up mod v0.30.0) and a Claude Desktop
  restart (to pick up the new MCP tool). Genuinely untested-live territory
  per the mod changelog's own caveat — treat the first real call as an
  experiment.

---

## 2026-08-28 (later same day) — sfs_telemetry.py + 24 new sfsprobe_mcp tools

- **Created `python/sfs_telemetry.py`** — pulls `analyze_dragarea.py`'s
  analysis logic (sample loading, planet constants, atmospheric density,
  clean-segment detection, predicted-vs-measured validation) out into a
  real importable module, generalized rather than drag-specific.
  `analyze_dragarea.py` still works standalone as a thin CLI.
  New capabilities beyond what the script had: `field_stats`,
  `search_field`, `downsample`, `field_at_time` (Stage 1 -- generic
  stats/search, not built ad-hoc per question anymore); `flight_summary`,
  `detect_phases`, `find_events` (Stage 2 -- heuristic phase segmentation
  and named/indexable event detection: engine_start/cutoff, apoapsis,
  periapsis, max_velocity, max_dynamic_pressure, part_count_drop with a
  heuristic destruction-vs-separation guess, impact); `resolve_scope`
  (Stage 3 -- lets other tools restrict analysis to a phase or a window
  around/before/after a named event); `validate_gravity_drag` (Stage 4,
  generalized from the script, now scope-aware), `noise_floor` (the
  determinism check from the original architecture doc), `find_clean_segments`
  (coast or burn, exposed standalone); `compute_apoapsis_periapsis`,
  `estimate_delta_v` (Stage 5 -- ISP not reliably in telemetry, honestly
  returns a note rather than a fabricated number if not supplied),
  `compare_flights` (Stage 6); `rocket_summary`, `part_lookup` (Stage 8 --
  from a live `snapshot` dump, real mass values, best-effort thrust/ISP).

- **Fixed a real bug found while building `flight_summary`**: `location.time`
  ('t' in telemetry) is NOT guaranteed monotonic across an archived flight
  — found on flight01 (crashed), which gave a negative duration when
  naively computed as last-t minus first-t. `flight_summary` now detects
  this and returns a `time_anomaly` note plus a max(t)-min(t) fallback
  instead of a silently wrong negative number. Root cause not yet
  confirmed (candidates: `ActiveRocket()` switching tracked object after
  a part-count event, or a scene/object handoff resetting the clock).

- **Added 24 new tools to `sfsprobe_mcp`** across Stages 1–11 (data
  analysis breadth, flight orchestration) — see `sfsprobe_mcp/README.md`
  for the full list and `mod_changelog.md`... actually there is no mod
  change here, this is Python/MCP-only, no `SFSProbe.cs` touched. New
  tool categories: generic stats/search/downsample; flight summary/phase/
  event detection; scoped analysis (phase- or event-relative, e.g. "drag
  error during the last 10s before impact"); generalized formula
  validation + noise-floor determinism check; apoapsis/periapsis/delta-v/
  divergence-check derived metrics; flight comparison + regression check
  ("does our mod still work" after an SFS update); bookkeeping
  (`list_flights`/`tag_flight`/`flight_to_csv` writing to a new
  `flights_log.jsonl` at the project root, so results stop evaporating
  between sessions); live rocket/part summary from a `snapshot` dump;
  `checklist_status` parsing `high_level_checklist.md`; and scripted
  flight orchestration (`run_flight_script` — ordered command batches,
  fixed delays, and **live-telemetry-condition waits**, e.g. cut engine
  once altitude exceeds X, repeatable across rocket designs unlike a
  fixed-time script; `run_and_analyze` closes the test-analyze loop into
  one call).

- **Verified**: `sfs_telemetry.py` compiles and sanity-tested directly
  against a real archived flight (flight01) — `load_samples`,
  `flight_summary`, `detect_phases`, `find_events`, and
  `validate_gravity_drag` all reproduced expected/consistent results.
  `sfsprobe_mcp/server.py` compiles clean, starts without error, and a
  smoke test calling ~12 of the 24 new tools directly (bypassing the MCP
  transport, which needs a Claude Desktop restart to pick up) ran with no
  exceptions and sensible output, including a genuine edge case correctly
  handled: `{'before_event':'impact', ...}` scoping fell back to the full
  flight range because flight01's telemetry never actually recorded a
  sample below 5m altitude (recording stopped just before real impact) —
  not a bug, `resolve_scope` correctly found no matching event. **Not yet
  tested through an actual live MCP connection** — needs a Claude Desktop
  restart, same as every previous `sfsprobe_mcp` change.

---

## 2026-08-28

- **`reference_index.py` / `reference_add.py`** — the bookkeeping pair for
  the `docs/sfs_reference/` split (Phase 1 Step 1).

  `reference_add.py` merges entries into
  `docs/sfs_reference/manifest.json` from stdin JSON, one or many at a
  time, then reruns the index build — so the manifest grows *as classes
  land* rather than in one pass at the end. Callers supply only
  `fq` / `file` / `summary` / `status` / `depth`; **namespace, kind, IL
  line number and method/field counts are filled from `inventory.json`,
  never from the caller**, so those can't drift from the assembly. Also
  accepts `{"section_map": [[old, new], ...]}` to extend the old-file
  §-section → new-file map. `status` is validated against
  CONFIRMED/PARTIAL/OPEN and `depth` against FULL/LIGHT.

  `reference_index.py` regenerates `docs/sfs_reference/INDEX.md` wholly
  from `manifest.json` + `inventory.json` — coverage table, standalone
  files, per-folder type tables, and the old-file section map. **INDEX.md
  is generated, never hand-edited**; drift between it and the manifest is
  prevented by construction. `--check` verifies every manifest `file`
  path exists on disk and every `fq` is a real inventory type.

- **`il_inventory.py`** — parses the `monodis` IL dump
  (`scratch/full_il.txt`, 13.3 MB, gitignored) into
  `docs/sfs_reference/inventory.json`: one record per `.class` declaration
  with namespace, kind, `extends`, nesting/parent, generic arity, line
  number in the dump, and `.method`/`.field` declaration counts. Filters
  compiler-generated types (closures, `<>c__DisplayClass*`, iterator state
  machines, `<PrivateImplementationDetails>` and its
  `__StaticArrayInitTypeSize=*` structs) — 1,509 `.class` declarations →
  **969 real types**. Also annotates each type with whether the
  pre-split `docs/sfs_source_reference.md` gives it a named heading
  (67 types) or merely mentions it (266). Written for Phase 1 Step 0 of
  the SFS Documentation restructure; output drives
  `docs/sfs_reference/INVENTORY.md`.

  Two parsing gotchas worth keeping: type names must be read as the first
  token *after* the flag keywords, not the last token on the line —
  generic declarations end in the type-parameter list
  (`.class ... Singleton\`1<(class ...Component) T>`), so a
  last-token heuristic yields `T>`. And quoted names (`'<>c__10\`1'`) have
  to be unquoted before splitting on `` ` `` or `<`, or they parse to the
  empty string.

- **Created `python/` folder** — didn't exist before this entry, despite
  being referenced by the 2026-08-26 changelog entries below. The
  two-body orbit solver and lower-envelope drag solver mentioned there
  were never actually found on disk when checked — likely only ever
  existed in a past chat session and were never saved. **Lesson: verify
  code mentioned in this changelog is actually on disk, don't assume
  because it's logged here that it's retrievable.** If those solvers are
  needed again, they'll need to be rebuilt from scratch or recovered from
  chat history.
- **`analyze_dragarea.py`** — validates the live-tested dragArea
  reflection path (mod_changelog.md v0.27.0) against real measured
  deceleration, the same rigor already applied to gravity/thrust/
  rotation/staging. Reads a truth.jsonl recorded with v0.28.0+ (which
  samples dragArea automatically every tick), finds coasting segments
  (mass flat across the whole span — same proxy `CheckAutoStop()` uses),
  and for each sample pair compares: measured acceleration (finite
  difference of `vx`/`vy` over real elapsed time) against predicted
  acceleration (gravity via confirmed `mu/r^2`, plus drag via the real
  `ApplyForce` force-application formula found during the doc-writing
  pass — `1.5 * dragArea * |v|^2 * density(h) / mass`, no extra unit
  constant needed since `AddForceAtPosition` is mass-normalized). Reports
  per-pair and aggregate magnitude/direction error, with the project's
  existing confirmed-formula error bars (gravity 0.008–0.13%, thrust
  0.4%, rotation 0.0006%, staging 0.003–0.006%, empirical noise floor
  ~0.006–0.03%) printed as the comparison bar. Only Earth's atmosphere
  constants are populated in `PLANET_CONSTANTS`; other bodies are
  skipped with a count, not silently mispredicted. Known gap: doesn't
  detect/filter parachute-deployed flight, where `ApplyParachuteDrag`
  bypasses this formula entirely (found same session, not yet handled
  here). Smoke-tested with fabricated data to confirm the pipeline runs
  end-to-end (parses, computes, reports) — **not yet run against a real
  flight**, which is the actual validation step.

---

## 2026-08-26

- **Two-body orbit solver**, built from scratch. Matches the game's own
  `Physics.GetTrajectory()` output to two decimal places at every
  sampled tick of a real coast, and matched the real eventual outcome
  of a 370km climb to 6.6m (0.0018%) — predicted *before* the rocket
  got there.
- **Lower-envelope / visible-surface solver**, built to eventually
  compute `dragArea` once real part geometry is available (see
  `sfs_physics_reference.md` §7.1 — geometry capture is still blocked
  on a Harmony patch, not yet written). Validated against synthetic
  test cases: 5/5 passed, including exact full-shielding and
  partial-shielding numbers, with the "pointed shape has lower drag"
  physical intuition falling out naturally from the formula. Not yet
  fed real geometry.

---

## Earlier history

No Python code existed before this date — the project was
research/planning only until the 2026-08-26 session (see
`SFS_Starting_point_Context` and `session-2026-08-26-gpu-session-1.md`
for the full narrative).
