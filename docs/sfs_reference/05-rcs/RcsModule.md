# `SFS.Parts.Modules.RcsModule` — reaction control thrusters

**Migrated** from `docs/sfs_source_reference.md` §D3 (2026-08-28).

Both selection methods are read in full, along with `FixedUpdate`. The
logic is small — about 40 lines of C# equivalent — and the two angle
thresholds are per-part serialized data that must be read live.

---

## RcsModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `SFS.World.Rocket/INJ_Rocket`, `INJ_TurnAxisWheels`, `INJ_DirectionalAxis` (explicit)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @263099

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
| `TurnAxis` | `float` | private property | no | `INJ_TurnAxisWheels` sink | [CONFIRMED] |
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
- **Status:** [CONFIRMED]

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
- **Status:** [CONFIRMED]

#### DirectionThrust(Vector2 thrustDirection) -> bool

- **Access:** private instance · IL @263758, full body
- **Behavior:**
  ```csharp
  if (DirectionalAxis == Vector2.zero) return false;
  return Vector2.Angle(thrustDirection, DirectionalAxis) <= directionAngleThreshold;
  ```
- **Status:** [CONFIRMED]

#### Update_RCS_On() -> void

- **Access:** instance · IL @263311
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
- **Status:** [CONFIRMED]

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

Everything needed is readable; the only per-part unknowns are the two
angle thresholds, which are serialized and must be read live.

The probe currently exposes only `rcsOn` and a firing count
(`CountFiringThrusters`). That count is a reasonable proxy for `count`
above — but note the force depends on `sumNormal` too, which the probe
does not compute.

## Status summary

| Item | Status |
|---|---|
| `RcsModule` / `Thruster` field layout, all unwrapped | [CONFIRMED] |
| Deadzone `0.01` on both axes | [CONFIRMED] |
| Both selection tests always evaluated (non-short-circuit OR) | [CONFIRMED] |
| One combined force per module, at `thrustPosition` | [CONFIRMED] |
| Torque gate `\|TurnAxis\| ≥ 0.95` **or** `\|angularVelocity\| ≥ 2` | [CONFIRMED] — newly documented, explains RCS damping |
| ±0.1 `TurnAxis` sign band | [CONFIRMED] |
| `DirectionThrust` angle test | [CONFIRMED] |
| Mass flow `thrust·count/ISP`, no throttle, no `IspMultiplier` | [CONFIRMED] |
| RCS self-disables when fuel cannot flow | [CONFIRMED] |
| Force quadratic in firing-thruster count | [CONFIRMED] arithmetic, [OPEN] in flight |
| `directionAngleThreshold` / `torqueAngleThreshold` values | [OPEN] — serialized per part, read live |
| `RCS_On` backing store (for writing it) | [OPEN] |
| `ToggleRCS` bodies | [OPEN] |
