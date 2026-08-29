# `SFS.Parts.Modules.EngineModule` — liquid engines

**Migrated** from `docs/sfs_source_reference.md` §D2.0–D2.4, D2.7
(2026-08-28).

Solid boosters are a **separate code path** with different field names —
see [`BoosterModule.md`](BoosterModule.md). Reaction-control torque is
[`TorqueModule.md`](TorqueModule.md). The wrapper types every field is
built on are in
[`../00-infrastructure/variables-wrapper-family.md`](../00-infrastructure/variables-wrapper-family.md).

---

## EngineModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `SFS.World.Rocket/INJ_Rocket`, `INJ_Throttle`, `INJ_TurnAxisTorque` (explicit)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @261221 · 26 methods / 19 fields

### The multi-engine answer: there is no summation

**[CONFIRMED]** from `FixedUpdate()` @261841, full body.

**Each engine runs its own `FixedUpdate` and applies its own force at its
own position.** Nothing anywhere sums engine thrust. "Multi-engine
behaviour" is just Unity's `Rigidbody2D` accumulating N independent
`AddForceAtPosition` calls — which is also where off-axis engine torque
comes from for free.

Consequences for any model of this:

- Total thrust is `Σ thrustNormal·thrust·9.8·throttle_Out` over engines
  **with `Rb2d != null`** — but each term is a *vector* applied at a
  *distinct point*, so a scalar sum is only valid when every engine is
  parallel and through the CoM.
- Torque from asymmetric engines is emergent, not modelled separately.
- Force is applied at `thrustPosition.Value` (a `Composed_Vector2`),
  **not** the part origin.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `thrust` | `Composed_Float` | public | no | tonnes-force | [CONFIRMED] |
| `thrustNormal` | `Composed_Vector2` | public | no | direction, part-local | [CONFIRMED] |
| `ISP` | `Composed_Float` | public | no | specific impulse | [CONFIRMED] |
| `thrustPosition` | `Composed_Vector2` | public | no | application point, part-local | [CONFIRMED] |
| `source` | `FlowModule` | public | no | fuel source | [CONFIRMED] |
| `hasGimbal` | `bool` | public | no | | [CONFIRMED] |
| `gimbalOn` | `Bool_Reference` | public | no | | [CONFIRMED] |
| `gimbal` | `MoveModule` | public | no | gimbal is an *animation*, not an angle | [CONFIRMED] |
| `engineOn` | `Bool_Reference` | public | no | also cleared by `CheckOutOfFuel` | [CONFIRMED] |
| `throttle_Out` | `Float_Reference` | public | no | **the actual per-engine throttle** | [CONFIRMED] |
| `heatOn` | `Bool_Reference` | public | no | | [CONFIRMED] |
| `heatHolder` | `GameObject` | public | no | | [CONFIRMED] |
| `oldMass` | `float` | public | no | | [CONFIRMED] |
| `originalPosition` | `Vector3` | private | no | | [CONFIRMED] |
| `Rocket` | `Rocket` | private property | no | injected via `INJ_Rocket` | [CONFIRMED] |
| `IsPlayer` | `bool` | private property | no | | [CONFIRMED] |
| `Rb2d` | `Rigidbody2D` | private property | no | **null check gates `FixedUpdate` entirely** | [CONFIRMED] |
| `throttle_Input` | `Float_Local` | private readonly | no | `INJ_Throttle` sink | [CONFIRMED] |
| `turnAxis_Input` | `Float_Local` | private readonly | no | `INJ_TurnAxisTorque` sink | [CONFIRMED] |

**Gotcha:** `throttle_Input` and `turnAxis_Input` are written by the
injection interfaces `Rocket.INJ_Throttle.set_Throttle` @261340 and
`Rocket.INJ_TurnAxisTorque.set_TurnAxis` @261355 — **explicit** interface
implementations, so they are private and only reachable via the
interface. **Read the `Float_Local` fields instead.**

### Methods

#### FixedUpdate() -> void

- **Access:** private instance (Unity message) · IL @261841, full body
- **Behavior:**
  ```csharp
  if (Rb2d == null) return;

  Vector2 localForce = thrustNormal.Value * (thrust.Value * 9.8f * throttle_Out.Value);

  Vector2 worldForce = Base.worldBase.AllowsCheats
      ? (Vector2)transform.TransformVector((Vector3)localForce)          // scale-aware
      : Transform_Utility.TransformVectorUnscaled(transform, localForce);

  Vector2 worldPos = Rb2d.GetRelativePoint(
      Transform_Utility.LocalToLocalPoint(transform, Rb2d, thrustPosition.Value));

  Rb2d.AddForceAtPosition(worldForce, worldPos, ForceMode2D.Force);
  PositionFlameHitbox();
  ```
- **Side effects:** applies force to the rigidbody; repositions the flame
  hitbox.
- **Gotchas:** **`Base.worldBase.AllowsCheats` selects a different
  transform function.** With cheats allowed the game uses scale-aware
  `Transform.TransformVector`; otherwise
  `Transform_Utility.TransformVectorUnscaled`. For a part with non-unit
  `lossyScale` these give **different thrust**. A cheats-enabled world is
  not physically identical to a normal one even with no cheat active.
- **Cross-check:** confirms `sfs_physics_reference.md` §2.2's
  `F = thrustNormal · thrust · 9.8 · throttle_Out` exactly, and shows the
  `9.8` is a literal `ldc.r4` in this method.
- **Status:** [CONFIRMED]

#### RecalculateEngineThrottle() -> void

- **Access:** instance · IL @261752
- **Behavior:** `throttle_Out.Value = engineOn.Value ? throttle_Input.Value : 0f;`
- **Gotchas:** **no interpolation, no ramp** — throttle response is
  instant. This is the IL confirmation of
  `sfs_physics_reference.md` §2.2's claim.
- **Status:** [CONFIRMED]

#### RecalculateMassFlow() -> void

- **Access:** instance · IL @261680
- **Behavior:**
  ```csharp
  float scale = transform.TransformVector((Vector3)thrustNormal.Value).magnitude;
  source.SetMassFlow(
      thrust.Value * scale * throttle_Out.Value
      / (ISP.Value * (float)Base.worldBase.settings.difficulty.IspMultiplier));
  ```
- **Gotchas:** matches `sfs_physics_reference.md` §1.3's
  `thrust · throttle / (ISP · ispMultiplier)` — **plus a `scale` term
  that is not in that doc**: the magnitude of `thrustNormal` after the
  part's world transform. For an unscaled part with a unit-length
  `thrustNormal` this is 1.0, which is why the empirical check came out
  at 0.002% error. **For a scaled part it is not 1.0 and the documented
  formula is wrong.**
- **`IspMultiplier`** is 1.0 / 1.0 / 1.5 by difficulty — see
  [`../06-soi-terrain/Difficulty.md`](../06-soi-terrain/Difficulty.md).
- **Status:** [CONFIRMED]

#### CheckOutOfFuel() -> void

- **Access:** instance · IL @261727
- **Behavior:** `if (engineOn.Value && !HasFuel(Logger)) engineOn.Value = false;`
- **Gotchas:** **engines shut themselves off.** `engineOn` going false is
  not necessarily a player action; fuel exhaustion produces the same
  observable.
- **Status:** [CONFIRMED]

#### RecalculateGimbal() -> void

- **Access:** instance · IL @261776
- **Behavior:**
  ```csharp
  if (!hasGimbal || !gimbalOn.Value) return;
  gimbal.targetTime.Value = throttle_Out.Value > 0f
      ? turnAxis_Input.Value * Transform_Utility.RotationDirection(transform)
      : 0f;
  ```
- **Gotchas:** a gimbal only deflects while `throttle_Out > 0`.
  `RotationDirection` handles mirrored parts. **Deflection is expressed
  as a `targetTime` on a `MoveModule`**, so gimbal geometry is an
  animation parameter, not an angle — the resulting thrust direction
  change shows up through `thrustNormal`, which is a `Composed_Vector2`
  recomputed from the moved transform.
- **Status:** [CONFIRMED]

---

## The control chain, end to end

**[CONFIRMED]** — every step read from IL.

```
Throttle.throttlePercent (Float_Local)   +   Throttle.throttleOn (Bool_Local)
        │  Throttle.UpdateThrottle()  @184711
        ▼
Throttle.output_Throttle = throttleOn ? throttlePercent : 0
        │  (injected into each engine as throttle_Input)
        ▼
EngineModule.throttle_Input  +  EngineModule.engineOn
        │  RecalculateEngineThrottle()  @261752
        ▼
EngineModule.throttle_Out = engineOn ? throttle_Input : 0
        │
        ├──▶ FixedUpdate()          -> thrust force
        ├──▶ RecalculateMassFlow()  -> fuel consumption
        └──▶ RecalculateGimbal()    -> gimbal deflection
```

See [`../10-control-input/Throttle.md`](../10-control-input/Throttle.md)
for the source end. Note `Throttle` has **three** fields, not two, and
`output_Throttle` is the authoritative commanded value.

---

## Appendix — root-causing the thrust telemetry bugs

`high_level_checklist.md` lists these as confirmed broken:

> - `thrustDirX`/`thrustDirY`/`gimbalOn`/`throttleOut` — never populate
> - `GetEngineDirection()` — only returns the first active engine found

**The second is by design and confirmed** — `GetEngineDirection` returns
on the first `EngineModule` with `engineOn` true. Given that there is no
thrust summation, a single engine's direction is not a meaningful summary
of a multi-engine rocket anyway; the fix is to emit a per-engine array,
not to pick a better single engine. It also **skips `BoosterModule`
entirely**.

**For the first, the IL rules out the obvious explanations.** All four
field names and every wrapper access in `GetEngineDirection` are correct:

| Probe access | IL says | Verdict |
|---|---|---|
| `Get(mv, "thrustNormal")` | `public Composed_Vector2 thrustNormal` | correct |
| `Get(normal, "x")` / `"y"` | `Composed_Vector2` has **public `Composed_Float x, y` fields** | correct |
| `GetWrapped2(nx)` | `Composed<T>` has a public `Value` property | correct |
| `GetWrapped2(Get(mv,"gimbalOn"))` | `Bool_Reference : ReferenceVariable<bool>`, inherits public `Value` | correct |
| `GetWrapped2(Get(mv,"throttle_Out"))` | `Float_Reference : Double_Reference`, declares `get_Value` | correct |
| `GetWrapped2(Get(mv,"engineOn"))` | as `gimbalOn` | correct |

Lazy initialisation is also not the cause: `Composed<T>.get_Value()`
@278674 calls `CheckInitialize()` first, which computes `GetResult(...)`
on first access. **Reading `.Value` is self-initialising.**

**So the cause is upstream.** All four keys are emitted inside a single
`if (eng != null)` block (`SFSProbe.cs` ~L772), so they fail *together*
exactly when `GetEngineDirection` returns `null`. That leaves three
candidates, **[OPEN]** between them:

1. `ModuleValues(part)` yields no object with
   `GetType().Name == "EngineModule"`.
2. Every `EngineModule` has `engineOn == false` at sample time — which is
   **correct behaviour** if telemetry was sampled outside a burn, and is
   also what `CheckOutOfFuel` produces on fuel exhaustion.
3. An exception is thrown and silently swallowed — `GetEngineDirection`
   ends in a bare `catch { }` with no logging.

Candidate 3 is what makes this hard to diagnose, and is worth fixing
first regardless: log the exception, and log which of the three branches
was taken. That converts an unexplained absence into a one-run answer.

> The same bare-`catch`-returns-null pattern appears in `GetHeatState`,
> `InvokeReturn`, and `Get` — see
> [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md). The newer
> `InvokeStatic` helper logs instead, and is the better model.

## Status summary

| Item | Status |
|---|---|
| No thrust summation — per-engine `AddForceAtPosition` | [CONFIRMED] |
| `F = thrustNormal · thrust · 9.8 · throttle_Out` | [CONFIRMED] — literal `9.8` in `FixedUpdate` |
| Force applied at `thrustPosition`, not part origin | [CONFIRMED] |
| `AllowsCheats` switches scaled/unscaled transform | [CONFIRMED] — newly documented |
| `throttle_Out = engineOn ? throttle_Input : 0`, no ramp | [CONFIRMED] |
| Fuel flow `thrust·scale·throttle / (ISP·IspMultiplier)` | [CONFIRMED] — `scale` term newly documented |
| Engines self-disable on fuel exhaustion | [CONFIRMED] |
| Gimbal deflects only while `throttle_Out > 0` | [CONFIRMED] |
| `GetEngineDirection` single-engine limit | [CONFIRMED] by design; also misses boosters |
| Why `thrustDirX`/etc. never populate | [OPEN] — narrowed to `GetEngineDirection` returning null; naming and wrapper access ruled out |
| `PositionFlameHitbox`, `HasFuel` and the remaining ~20 methods | [OPEN] |
