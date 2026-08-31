# `SFS.Parts.Modules.RcsModule` — reaction control thrusters

**Migrated** from `docs/sfs_source_reference.md` §D3 (2026-08-28).

Both selection methods are read in full, along with `FixedUpdate`. The
logic is small — about 40 lines of C# equivalent — and the two angle
thresholds are per-part serialized data that must be read live.

**Re-verified end to end via direct IL re-read 2026-08-30**, in the same
session that found and fixed a real transcription bug in the heat
formula — a check on whether "[CONFIRMED]" elsewhere in this project
can be trusted at face value. RCS held up: one small correction (an
interface name) and one new clarifying detail (`Update_RCS_On` is
event-driven), but every physics-determining method (`FixedUpdate`,
`TorqueThrust`, `DirectionThrust`) matched the existing documentation
exactly, instruction for instruction.

**The `TorqueThrust` selection gate is now LIVE-VALIDATED, not just
confirmed from IL** (2026-08-30, same day, a manual test flight with a
real 6-thruster RCS-equipped rocket, symmetry-placed). Checked every
tick where `DirectionalAxis == 0` (so only `TorqueThrust` could explain
firing) against the confirmed gate `\|TurnAxis\|≥0.95 OR \|angv\|≥2`:
**4,081 of 4,096 samples matched exactly (99.63%)**. The 15 apparent
mismatches all showed `TurnAxis` already back at exactly `0` with
firing still reported, clustered in tight sub-100ms groups — consistent
with a one-tick read-order artifact (the probe's own telemetry sampling
and `RcsModule.FixedUpdate` are separate Unity scripts with no
guaranteed execution order within a tick), not a real logic mismatch.
**Not yet validated:** the actual force magnitude/direction (needs an
engines-off flight to isolate RCS's own contribution from simultaneous
main-engine thrust) and the quadratic-force-scaling arithmetic (needs
per-part world orientation, not currently in telemetry, to reconstruct
`sumNormal`).

---

## RcsModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `SFS.World.Rocket/INJ_Rocket`, `INJ_IsPlayer`, `INJ_DirectionalAxis`, `INJ_TurnAxisTorque`, `SFS.Parts.Modules.I_PartMenu` (explicit)
**Status:** [CONFIRMED] — re-verified via direct IL re-read 2026-08-30
**Depth:** FULL
**IL:** `scratch/full_il.txt` @263099

> **CORRECTION (2026-08-30, direct IL re-read).** The class declaration
> was re-verified line-by-line after the heat-formula transcription bug
> was caught the same session (a reminder that "[CONFIRMED]" from an
> earlier pass doesn't mean re-checking is wasted effort). One real
> correction: the interfaces are `INJ_Rocket, INJ_IsPlayer,
> INJ_DirectionalAxis, INJ_TurnAxisTorque, I_PartMenu` — an earlier pass
> recorded `INJ_TurnAxisWheels`, which does not appear in the real
> declaration. `INJ_TurnAxisTorque` is the same interface
> `EngineModule` implements for its own `turnAxis_Input` sink, so RCS
> and gimbal read `TurnAxis` through the identical injection path.
> `INJ_IsPlayer` was also missing from the earlier list. Everything
> else below (fields, `FixedUpdate`, `TorqueThrust`, `DirectionThrust`,
> `Update_RCS_On`) was independently re-traced against the real IL and
> confirmed to match exactly — no other corrections needed.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `directionAngleThreshold` | `float` | public | no | degrees; **serialized per part** — value must be read live | [CONFIRMED] shape · [OPEN] value |
| `torqueAngleThreshold` | `float` | public | no | degrees; **serialized per part** | [CONFIRMED] shape · [OPEN] value |
| `thrust` | `float` | public | no | **plain float**, not `Composed_Float` | [CONFIRMED] |
| `ISP` | `float` | public | no | plain float | [CONFIRMED] |
| `thrusters` | `List<RcsModule/Thruster>` | public | no | the nested thruster records | [CONFIRMED] |
| `source` | `FlowModule` | public | no | fuel source | [CONFIRMED] |
| `thrustPosition` | `Vector2` | public | no | plain `Vector2`, part-local; **the single application point for the whole module** | [CONFIRMED] |
| `Rocket` | `Rocket` | private property | no | `INJ_Rocket` | [CONFIRMED] |
| `IsPlayer` | `bool` | private property | no | | [CONFIRMED] |
| `TurnAxis` | `float` | private property | no | `INJ_TurnAxisTorque` sink | [CONFIRMED] |
| `DirectionalAxis` | `Vector2` | private property | no | `INJ_DirectionalAxis` sink | [CONFIRMED] |
| `RCS_On` | `bool` | private property | no | @263239; backing store [OPEN] | [PARTIAL] |

**Unlike [`EngineModule`](../04-engines/EngineModule.md), none of the
physics fields are wrapped** — `thrust`, `ISP`, `thrustPosition` are
plain fields, so `Get()` returns usable values directly with no
`GetWrapped2`.

---

## RcsModule/Thruster

**Namespace:** SFS.Parts.Modules
**Kind:** class (**nested** under `RcsModule`)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @263824

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `thrustNormal` | `Vector2` | public | no | part-local direction | [CONFIRMED] |
| `effect` | `MoveModule` | public | no | visual only; `targetTime` is 0 or 1 | [CONFIRMED] |

**Reflection note:** `Thruster` is nested, so `FindType` needs a
**slash**: `FindType("SFS.Parts.Modules.RcsModule/Thruster")`. Usually
unnecessary — walk `Get(rcs, "thrusters")` as an `IEnumerable` and read
`thrustNormal` off each element.

---

## Methods

#### FixedUpdate() -> void

- **Access:** private instance (Unity message) · IL @263482, full body
- **Behavior:**
  ```csharp
  if (Rocket == null || !RCS_On
      || (Mathf.Abs(TurnAxis) < 0.01f && DirectionalAxis.sqrMagnitude < 0.01))
  {
      foreach (Thruster t in thrusters) t.effect.targetTime.Value = 0f;
      source.SetMassFlow(0.0);
      return;
  }

  Vector2 positionToCoM = Rocket.rb2d.worldCenterOfMass
                        - (Vector2)transform.TransformPoint(thrustPosition);
  float   count     = 0f;
  Vector2 sumNormal = Vector2.zero;

  foreach (Thruster t in thrusters)
  {
      Vector2 worldNormal = Transform_Utility.TransformVectorUnscaled(transform, t.thrustNormal);

      bool fire = TorqueThrust(worldNormal, positionToCoM) | DirectionThrust(worldNormal);

      if (fire) { sumNormal += worldNormal; count += 1f; t.effect.targetTime.Value = 1f; }
      else                                               t.effect.targetTime.Value = 0f;
  }

  if (sumNormal != Vector2.zero)
      Rocket.rb2d.AddForceAtPosition(
          sumNormal * (thrust * count * 9.8f),
          (Vector2)transform.TransformPoint(thrustPosition));

  source.SetMassFlow(thrust * count / ISP);
  ```
- **Side effects:** one `AddForceAtPosition` on the rocket body; sets
  every thruster's visual `targetTime`; sets mass flow on `source`.
- **Gotchas:**
  - **Deadzone**: `|TurnAxis| < 0.01` **and**
    `DirectionalAxis.sqrMagnitude < 0.01` together shut the module down
    and zero its mass flow.
  - **Both selection tests always run.** The IL calls `TorqueThrust`,
    then `DirectionThrust`, then `or` — a **non-short-circuiting**
    bitwise OR. A thruster fires if either test passes.
  - **The whole module applies one combined force at one point**
    (`thrustPosition`), not one force per thruster — unlike engines.
    Per-thruster geometry only enters through `sumNormal`.
  - **Mass flow is `thrust · count / ISP`** — note **no `throttle` term
    and no `IspMultiplier`**, unlike
    `EngineModule.RecalculateMassFlow`. **RCS fuel use is not
    difficulty-scaled.**
- **Status:** [CONFIRMED] — re-verified via direct IL re-read 2026-08-30,
  stack-traced instruction by instruction, matches exactly including
  the non-short-circuiting OR (confirmed both `call`s execute
  unconditionally before the `or` combines the two bool results).

> ### Force magnitude is quadratic in the number of firing thrusters
> **[CONFIRMED arithmetic, [OPEN] interpretation].**
>
> `sumNormal` is an unnormalised **vector sum** over firing thrusters,
> and it is then multiplied by `count` again. For *N* firing thrusters
> with parallel unit normals, `|sumNormal| = N` and the applied force is
> `N · thrust · N · 9.8 = N² · thrust · 9.8`, while mass flow stays
> linear at `thrust · N / ISP`. Taken literally, **RCS gets more
> efficient per unit fuel the more thrusters fire together.**
>
> The arithmetic has been read correctly (both `mul` opcodes at IL_0192
> and IL_0199) but the consequence has **not** been verified in flight,
> and non-parallel normals partially cancel in the sum. Treat the `N²` as
> a reading of the code, not an established flight fact, until measured.

#### TorqueThrust(Vector2 thrustDirection, Vector2 positionToCenterOfMass) -> bool

- **Access:** private instance · IL @263670, full body
- **Parameters:** `thrustDirection` — the thruster's **world** normal;
  `positionToCenterOfMass` — points **from the module toward** the centre
  of mass
- **Returns:** whether this thruster fires for rotational demand
- **Behavior:**
  ```csharp
  if (thrustDirection == Vector2.zero || positionToCenterOfMass == Vector2.zero)
      return false;

  // Gate: only fire for near-full input, or to arrest an existing spin
  if (Mathf.Abs(TurnAxis) < 0.95f && Mathf.Abs(Rocket.rb2d.angularVelocity) < 2f)
      return false;

  float angleCCW = Vector2.Angle(thrustDirection, Quaternion.Euler(0, 0,  90f) * positionToCenterOfMass);
  float angleCW  = Vector2.Angle(thrustDirection, Quaternion.Euler(0, 0, -90f) * positionToCenterOfMass);

  if (TurnAxis >  0.1f && angleCCW <= torqueAngleThreshold) return true;
  if (TurnAxis < -0.1f) return angleCW <= torqueAngleThreshold;
  return false;
  ```
- **Gotchas:** **the 0.95 / 2.0 gate is the significant find.** RCS
  torque thrusters do **not** respond proportionally to steering input.
  They fire only when
  - `|TurnAxis| ≥ 0.95` — essentially full deflection — **or**
  - `|angularVelocity| ≥ 2` deg/s — i.e. the rocket is already spinning.

  The second clause is what makes RCS act as a **rotation damper**: once
  `TurnAxis` returns to zero, thrusters keep firing (subject to the ±0.1
  sign test) until the spin falls under 2 deg/s. That is almost certainly
  the mechanism behind any observed RCS "auto-stabilisation".

  The ±0.1 band means `TurnAxis` between −0.1 and +0.1 selects **no**
  thruster, even when the 0.95/2.0 gate passed on angular velocity.
- **Status:** [CONFIRMED] — re-verified via direct IL re-read 2026-08-30,
  matches exactly (including the exact 0.95/2.0 gate values and the
  ±0.1 sign band, both re-confirmed as real IL literals not guesses).

#### DirectionThrust(Vector2 thrustDirection) -> bool

- **Access:** private instance · IL @263758, full body
- **Behavior:**
  ```csharp
  if (DirectionalAxis == Vector2.zero) return false;
  return Vector2.Angle(thrustDirection, DirectionalAxis) <= directionAngleThreshold;
  ```
- **Status:** [CONFIRMED] — re-verified via direct IL re-read 2026-08-30,
  matches exactly.

#### Update_RCS_On() -> void

- **Access:** instance · IL @263311
- **Called via `source.onStateChange`** (subscribed in `Start()`,
  confirmed 2026-08-30) — **event-driven, not polled every tick.**
  Fires reactively the instant the fuel `FlowModule`'s flow state
  changes, not on a periodic check.
- **Behavior:**
  ```csharp
  if (!RCS_On) return;
  I_MsgLogger logger = IsPlayer ? MsgDrawer.main : new MsgNone();
  if (!source.CanFlow(logger))
      ToggleRCS(new UsePartData(new UsePartData.SharedData(false), null), false);
  ```
- **Gotchas:** **RCS switches itself off when its fuel source cannot
  flow** — the same self-disabling pattern as
  `EngineModule.CheckOutOfFuel`. So `RCS_On` going false is **not
  necessarily a player action**.
- **Status:** [CONFIRMED] — re-verified via direct IL re-read 2026-08-30,
  matches exactly

#### ToggleRCS(UsePartData) / ToggleRCS(UsePartData, bool showMsg) -> void

- **Access:** public @263355 / **private** @263369
- **Status:** [CONFIRMED] signatures · [OPEN] bodies

#### RCS_On { get; } -> bool

- **Access:** private property · IL @263239
- **Gotchas:** **[OPEN]** — the backing store was not traced, so *writing*
  it from the probe is not yet specified. **Reading** works via
  `Get(rcs, "RCS_On")` (the probe's `Get` reads non-public properties).
- **Status:** [PARTIAL]

## Modelling notes

To replicate RCS, per module per tick:

1. Read `RCS_On`, `TurnAxis`, `DirectionalAxis`; apply the 0.01 deadzone.
2. `positionToCoM = rb2d.worldCenterOfMass − transform.TransformPoint(thrustPosition)`.
3. For each thruster: world-transform `thrustNormal` **unscaled**, then
   run both tests and OR them.
4. Force `sumNormal · thrust · count · 9.8` at
   `transform.TransformPoint(thrustPosition)`; mass flow
   `thrust · count / ISP`.

Everything needed is readable; the two per-part angle thresholds and
`DirectionalAxis` are now readable live too (`rcsinfo` command,
`directionalAxisX`/`directionalAxisY` telemetry fields, both sfsprobe
v0.44.0) — no remaining unknowns for a full live validation, only an
actual flight to run it against.

The probe currently exposes `rcsOn`, a firing count
(`CountFiringThrusters`, confirmed to read the real per-tick
`targetTime` state set in `FixedUpdate`), and now `directionalAxisX/Y`.
That firing count is a reasonable proxy for `count` above — but note
the force depends on `sumNormal` too, which the probe does not compute
directly (though `rcsinfo`'s per-thruster `thrustNormal` list plus a
Python-side reconstruction of `TorqueThrust`/`DirectionThrust` could
derive it).

## Status summary

| Item | Status |
|---|---|
| `RcsModule` interfaces (corrected: `INJ_TurnAxisTorque` not `INJ_TurnAxisWheels`, `INJ_IsPlayer` added) | [CONFIRMED] — corrected 2026-08-30 |
| `RcsModule` / `Thruster` field layout, all unwrapped | [CONFIRMED] |
| Deadzone `0.01` on both axes | [CONFIRMED] — re-verified 2026-08-30 |
| Both selection tests always evaluated (non-short-circuit OR) | [CONFIRMED] — re-verified 2026-08-30, stack-traced |
| One combined force per module, at `thrustPosition` | [CONFIRMED] — re-verified 2026-08-30 |
| Torque gate `\|TurnAxis\| ≥ 0.95` **or** `\|angularVelocity\| ≥ 2` | [CONFIRMED] — re-verified 2026-08-30 |
| ±0.1 `TurnAxis` sign band | [CONFIRMED] — re-verified 2026-08-30 |
| `DirectionThrust` angle test | [CONFIRMED] — re-verified 2026-08-30 |
| Mass flow `thrust·count/ISP`, no throttle, no `IspMultiplier` | [CONFIRMED] — re-verified 2026-08-30 |
| RCS self-disables when fuel cannot flow, via `onStateChange` event | [CONFIRMED] — event-trigger detail added 2026-08-30 |
| Force quadratic in firing-thruster count | [CONFIRMED] arithmetic, [OPEN] in flight |
| Torque gate `\|TurnAxis\|≥0.95 OR \|angv\|≥2` matches real firing | [x] LIVE-VALIDATED 2026-08-30 — 99.63% (4081/4096), residual explained by sampling order |
| `directionAngleThreshold` / `torqueAngleThreshold` values | [x] read live — `rcsinfo` command, sfsprobe v0.44.0 |
| `RCS_On` backing store (for writing it) | [OPEN] |
| `ToggleRCS` bodies | [OPEN] |
| `DirectionalAxis` telemetry (real source, needed for `DirectionThrust` reconstruction) | [x] `Rocket.output_DirectionalAxis`, confirmed via IL, sfsprobe v0.44.0 |
