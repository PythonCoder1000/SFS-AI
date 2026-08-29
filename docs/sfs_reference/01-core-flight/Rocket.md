# `SFS.World.Rocket` — the craft object

**Migrated** from `docs/sfs_source_reference.md` §B1 (2026-08-28).

Base class [`Player.md`](../10-control-input/Player.md); mass
[`Mass_Calculator.md`](Mass_Calculator.md); rails driver
[`Physics.md`](Physics.md); drag
[`../02-drag-aero/Aero_Rocket.md`](../02-drag-aero/Aero_Rocket.md).

---

## Rocket

**Namespace:** SFS.World
**Kind:** class
**Extends:** SFS.World.Player
**Implements:** `SFS.World.I_Physics` (**explicitly**)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @187563 · 52 methods / 23 fields

```
.class public auto ansi beforefieldinit Rocket
    extends SFS.World.Player
    implements SFS.World.I_Physics
```

> **`Rocket : Player` matters constantly.** `location`, `hasControl`,
> `isPlayer` and `GetSizeRadius()` are **on `Player`**, not on `Rocket`,
> so `typeof(Rocket).GetField("location")` returns null under
> `DeclaredOnly` and works only with inherited lookup. The probe's `Get`
> helper already walks the hierarchy; anything hand-rolled must.

### Fields

Read from the `.field` lines of the class body. All `public` except the
three marked private.

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `mass` | `SFS.Parts.Mass_Calculator` | public | no | drives `rb2d.mass` and `centerOfMass` | [CONFIRMED] |
| `rb2d` | `UnityEngine.Rigidbody2D` | public | no | the physics body | [CONFIRMED] |
| `partHolder` | `SFS.Parts.PartHolder` | public | no | part list + `GetModules<T>()` | [CONFIRMED] |
| `mapIcon` | `SFS.World.Maps.MapIcon` | public | no | | [CONFIRMED] |
| `arrowkeys` | `SFS.World.Arrowkeys` | public | no | **raw control input** | [CONFIRMED] |
| `throttle` | `SFS.World.Throttle` | public | no | | [CONFIRMED] |
| `staging` | `SFS.World.Staging` | public | no | | [CONFIRMED] |
| `resources` | `SFS.World.Resources` | public | no | | [CONFIRMED] |
| `aero` | `SFS.World.Drag.Aero_Rocket` | public | no | the drag subclass | [CONFIRMED] |
| `stats` | `SFS.Stats.StatsRecorder` | public | no | | [CONFIRMED] |
| `timeManager`, `partManager` | `GameObject` | public | no | | [CONFIRMED] |
| `rocketName` | `string` | public | no | | [CONFIRMED] |
| `jointsGroup` | `SFS.World.JointGroup` | public | no | | [CONFIRMED] |
| `collisionImmunity` | `float` | public | no | seconds remaining | [CONFIRMED] |
| `floating` | `bool` | public | no | **means "in water"**, not "off the ground" | [CONFIRMED] |
| `physics` | `SFS.World.Physics` | public | no | the rails/physics driver | [CONFIRMED] |
| `output_TurnAxisTorque` | `Float_Local` | public | no | ***computed*** turn axis | [CONFIRMED] |
| `output_TurnAxisWheels` | `Float_Local` | public | no | raw `arrowkeys.turnAxis` | [CONFIRMED] |
| `output_DirectionalAxis` | `Vector2_Local` | public | no | RCS translation input | [CONFIRMED] |
| `pipeFlows` | `List<(ResourceModule[], ResourceModule)>` | **private** | no | fuel-pipe graph | [CONFIRMED] |
| `sizeRadius`, `lastUpdateTime` | `float` | **private** | no | cache for `GetSizeRadius` | [CONFIRMED] |

> **`floating` means "in water".** Both call sites confirm it: in
> `CanTimewarp` it selects the `Cannot_Timewarp_While_Moving_Water`
> message over `..._On_Surface`, and in `GetTurnAxis` it damps rotation
> authority to 10%. **Do not read it as "off the ground".**

> **The three `output_*` fields are outputs, not inputs.** They are
> written every `FixedUpdate` and consumed by part modules through the
> `Inject_*` plumbing. **Writing to them from a mod is overwritten
> within one physics tick.** The inputs are on `arrowkeys`.

### Methods

#### FixedUpdate() -> void

- **Access:** private instance (Unity message) · IL @188822
- **Behavior:** in order, with nothing else in the body:
  ```csharp
  Inject_Location();
  UpdateMass();
  UpdateMapIconRotation();
  ApplyTorque();
  output_DirectionalAxis.Value = arrowkeys.rcs
      ? arrowkeys.horizontalAxis.Value + arrowkeys.verticalAxis.Value
      : Vector2.zero;
  FuelPipeModule.FixedUpdate_FuelPipeFlow(pipeFlows);
  ```
- **Gotchas:** note what is **absent** — no thrust, no drag, no heat.
  Those run in the part modules' own `FixedUpdate`s, so ordering between
  them and this method is **Unity's script execution order, not a call
  chain**. `output_DirectionalAxis` is the **sum** of the horizontal and
  vertical axis vectors, gated on `arrowkeys.rcs`; it is zero whenever
  RCS is toggled off, regardless of key state.
- **Status:** [CONFIRMED]

#### UpdateMass() -> void

- **Access:** instance · IL @187673
- **Behavior:** two lines, every tick:
  ```csharp
  rb2d.mass         = mass.GetMass();
  rb2d.centerOfMass = mass.GetCenterOfMass();
  ```
- **Gotchas:** `rb2d.mass` is therefore always current as of the last
  physics tick — **reading it live is safe and needs no recomputation.**
- **Status:** [CONFIRMED]

---

## Rotation control — the full model

**[CONFIRMED].** The single most useful thing in this entry, and **not
what a physics-based guess would predict.** It also independently
confirms `sfs_physics_reference.md` §2.4 from the code side: that section
already derives the same formula empirically, to 0.0006% error in vacuum,
including the `(mass/200)^0.35` divisor.

> **One reconciliation note:** §2.4 writes the threshold as "only when
> mass > 200t"; the IL compares `rb2d.mass > 200f` with **no unit
> conversion**, so the *tonne* reading rests on §2.4's empirical
> validation, not on anything visible in the IL.

#### GetTorque() -> float

- **Access:** instance · IL @187695
- **Behavior:**
  ```csharp
  float torque = 0f;
  foreach (TorqueModule t in partHolder.GetModules<TorqueModule>())
      if (t.enabled.Local || t.enabled.Value)      // note: Local first
          torque += t.torque.Value;                // Composed_Float
  return torque;
  ```
- **Gotchas:** the `Local ||` short-circuit means an **unbound**
  `Bool_Reference` counts as enabled — see
  [`../00-infrastructure/variables-wrapper-family.md`](../00-infrastructure/variables-wrapper-family.md).
- **Status:** [CONFIRMED]

#### ApplyTorque() -> void

- **Access:** instance · IL @188864
- **Behavior:**
  ```csharp
  float torque = GetTorque();
  if (rb2d.mass > 200f)
      torque /= Mathf.Pow(rb2d.mass / 200f, 0.35f);       // heavy-craft penalty

  output_TurnAxisTorque.Value = GetTurnAxis(torque, useStopRotation: true);

  if (output_TurnAxisTorque.Value != 0f && rb2d.simulated)
      rb2d.angularVelocity -= torque * 57.29578f / rb2d.mass
                            * output_TurnAxisTorque.Value * Time.fixedDeltaTime;

  output_TurnAxisWheels.Value = arrowkeys.turnAxis;       // raw, undamped
  ```
- **Side effects:** writes `rb2d.angularVelocity` and both
  `output_TurnAxis*` fields.
- **Gotchas:** three, all confirmed from the opcodes.
  1. **Rotation is not a torque.** It writes `rb2d.angularVelocity`
     **directly**. Unity's `AddTorque` is never called, and the
     rigidbody's **moment of inertia is never involved**. Rotational
     authority is `torque / mass`, not `torque / I`. **A long rocket and
     a compact one of equal mass turn at exactly the same rate.** Any
     agent model that computes an inertia tensor is modelling a game that
     does not exist.
  2. **The heavy-craft penalty is `mass^-0.35` above 200.** Below 200 the
     divisor is skipped entirely, so authority is flat-then-decaying with
     a kink at exactly 200. Combined with the `/rb2d.mass` in the
     integration step, net angular acceleration scales as `m^-1` below
     200 and `m^-1.35` above it.
  3. `57.29578f` is rad→deg (Unity's `angularVelocity` is deg/s), and the
     sign is **subtract** — positive `turnAxis` *reduces*
     `angularVelocity`.
- **Status:** [CONFIRMED]

#### GetTurnAxis(float torque, bool useStopRotation) -> float

- **Access:** instance · IL @188939
- **Behavior:**
  ```csharp
  if (arrowkeys.turnAxis != 0f) return arrowkeys.turnAxis;   // manual wins
  if (useStopRotation && hasControl && !IsOnSurface)
      return GetStopRotationTurnAxis(torque) * (floating ? 0.1f : 1f);
  return 0f;
  ```
- **Status:** [CONFIRMED]

#### GetStopRotationTurnAxis(float torque) -> float — **this is SAS**

- **Access:** instance · IL @188987
- **Behavior:**
  ```csharp
  float angVel = rb2d.angularVelocity;
  float delta  = torque * 57.29578f / rb2d.mass * Time.fixedDeltaTime;
  if (delta == 0f) return 0f;
  return Mathf.Clamp(angVel / delta, -1f, 1f);
  ```
- **Gotchas:** `delta` is exactly the angular-velocity change one tick of
  full-authority torque produces, so the returned axis is **the fraction
  of one tick's authority needed to null the rotation**, clamped. Within
  one tick's worth of authority it lands on **zero exactly**; beyond it,
  it saturates at full deflection. **There is no PID, no gain, no
  overshoot — the damping is deadbeat by construction.**

  Auto-stabilisation is **off** whenever any of: the player is holding a
  turn key, `hasControl` is false, or `IsOnSurface` is true. It is damped
  to **10% in water**.
- **Status:** [CONFIRMED]

#### get_IsOnSurface() -> bool

- **Access:** instance property · IL @189641
- **Behavior:**
  ```csharp
  Collider2D[] contacts = new Collider2D[5];               // fixed size 5
  rb2d.GetContacts(contacts);
  return contacts.Any(<>c.b__84_0);
  ```
- **Gotchas:** the buffer is **hard-capped at 5 contacts** and the return
  count is discarded (`pop`). The array is a fresh `newarr` each call, so
  stale entries are not a risk, but **a craft with more than 5
  simultaneous contacts only sees the first 5.**
- **Status:** [CONFIRMED]

---

#### GetRotation() -> float

- **Access:** instance · IL @187766
- **Returns:** heading in **degrees**
- **Behavior:** picks its reference in this priority order:
  1. Sum of `transform.TransformVector(thrustNormal.Value * thrust.Value)`
     over engines with `engineOn.Value == true`. If nonzero →
     `Atan2(y, x) * 57.29578f`.
  2. Else the same sum over engines with `engineOn == false`. If nonzero
     → same `Atan2`.
  3. Else the **first** `ControlModule`'s `transform.eulerAngles.z + 90f`.
  4. Else `transform.eulerAngles.z` (**no `+90`**).
- **Gotchas:** two traps. The `+90f` in case 3 and its absence in case 4
  mean **the fallbacks are not on the same angular convention** — a craft
  with a control module and one without report headings 90° apart. And
  cases 1/2 are a **thrust-weighted vector sum**, so on a craft with
  opposed engines the "heading" can swing wildly or fall to case 3 as
  engines toggle. **For an agent, `GetRotation()` is a UI convenience;
  derive heading from `transform.eulerAngles.z` (or the velocity vector)
  instead.**
- **Status:** [CONFIRMED]

---

## The `Inject_*` mechanism

**[CONFIRMED].** Eleven private methods (`Inject_Rocket`, `_IsPlayer`,
`_HasControl`, `_ThrottleOn`, `_Throttle`, `_TurnAxisTorque`,
`_TurnAxisWheels`, `_DirectionalAxis`, `_Location`, `_Physics`) plus
`InjectPartDependencies` @189026, `Start_RocketInjector` @188683 and
`OnDestroy_RocketInjector` @188767.

Each pairs with a **nested interface** on `Rocket` — `Rocket/INJ_Rocket`,
`Rocket/INJ_IsPlayer`, and so on — each declaring a single setter
property. A part module opts in by implementing the interface; the
injector finds implementors and pushes the value in. **This is how
`EngineModule.throttle_Out` gets populated without the module holding a
`Rocket` reference.**

Only `Inject_Location()` runs from `FixedUpdate`. The rest run from
`Start_RocketInjector` / `SetParts`, i.e. **on craft-structure change**.

> **Extractor note:** `INJ_Rocket`'s `set_Rocket` is `abstract`, and an
> earlier pass of `sig.sh` attributed it to `Rocket` itself. An
> `abstract` member on a concrete class is always an extractor overrun —
> see [`../METHODOLOGY.md`](../METHODOLOGY.md).

---

## `I_Physics` — explicitly implemented, and reflection-hostile

**[CONFIRMED].** All seven `I_Physics` members are **explicit interface
implementations**, emitted as
`private final virtual ... SFS.World.I_Physics.get_PhysicsMode` with an
`.override`. Consequences for reflection:

- `typeof(Rocket).GetProperty("PhysicsMode")` returns **null**.
- The member's real reflected name contains dots:
  `"SFS.World.I_Physics.PhysicsMode"`, and it is **non-public**.
- **The clean route is the interface**: cast to `I_Physics`, or
  `typeof(I_Physics).GetProperty("PhysicsMode").GetValue(rocket)`, which
  dispatches through the interface map correctly.

Bodies:

```csharp
bool    PhysicsMode   => rb2d != null && rb2d.simulated;
Vector2 LocalPosition => (Vector2)rb2d.transform.position
                       + (Vector2)transform.TransformVector(mass.GetCenterOfMass());
Vector2 LocalVelocity => rb2d.linearVelocity;
void    OnCrashIntoPlanet() => RocketManager.DestroyRocket(this, (DestructionReason)0);

set_PhysicsMode(bool value) {
    rb2d.simulated = value;
    foreach (Collider2D c in partHolder.GetComponentsInChildren<Collider2D>(true))
        c.enabled = value;
    if (!rb2d.simulated) rb2d.angularVelocity = 0f;
}
```

> **`LocalPosition` is the centre of mass, not the transform origin**,
> and the setter subtracts the same offset before writing. So `Physics` /
> `Trajectory` track the **CoM**. A position read from
> `transform.position` and one read through `I_Physics` differ by the CoM
> offset — **for a tall rocket that is metres, not noise.**

> **`set_PhysicsMode(false)` disables every collider on the craft** and
> zeroes angular velocity. This is exactly what the SOI-crossing branch
> in `Physics.Update()` triggers: crossing an SOI boundary in physics
> mode **silently drops the craft's colliders and stops its rotation.**
> See [`../06-soi-terrain/Planet.md`](../06-soi-terrain/Planet.md).

---

#### CanTimewarp(I_MsgLogger logger, bool showSpeed, out bool isInWater) -> bool

- **Access:** instance · IL @188430
- **Returns:** false, with a **localised message via `logger`**, on the
  first failing check
- **Behavior:**
  ```csharp
  isInWater = floating;
  double minRadius = Planet.GetTimewarpRadius_AscendDescend(location.Value);
  if (location.Value.Radius < minRadius) {
      if (!IsOnSurface && !floating)
          WorldTime.ShowCannotTimewarpBelowHeightMsg(
              minRadius - location.Value.planet.Value.Radius, logger, showSpeed);
      else if (location.Value.velocity.Value.Mag_MoreThan(floating ? 3.0 : 0.1))
          ... return false;                       // "moving on surface" / "in water"
  }
  if (engines.Any(e => e.throttle_Out.Value != 0f) ||
      boosters.Any(b => b.throttle_Out.Value != 0f)) { ... return false; }
  return true;
  ```
- **Gotchas:** the surface speed limit is **0.1 m/s on land, 3.0 m/s in
  water** (`Double2.Mag_MoreThan`, a squared-magnitude compare — no
  sqrt). The accelerating check reads **`throttle_Out`, not `engineOn`**
  — an engine that is on at zero throttle does **not** block timewarp.
- **Related:** `Planet.GetTimewarpRadius_AscendDescend` is `public
  static` and takes a `Location`, so an agent can **pre-compute the
  altitude at which timewarp becomes legal** without trial and error.
  Passing a custom `I_MsgLogger` gets the game's own reason for a refusal
  instead of a bare `false` — see
  [`../13-challenges-logging/I_MsgLogger.md`](../13-challenges-logging/I_MsgLogger.md).
- **Status:** [CONFIRMED]

#### GetSizeRadius() -> float

- **Access:** instance, overrides `Player.GetSizeRadius()` · IL @188147
- **Behavior:**
  ```csharp
  if (Time.time - lastUpdateTime < 1f) return sizeRadius;      // stale up to 1s
  float maxSq = partHolder.parts.Max(p => /* b__0: dist² from centerOfMass */);
  sizeRadius  = Mathf.Sqrt(maxSq) + 3f;
  lastUpdateTime = Time.time;
  return sizeRadius;
  ```
- **Gotchas:** the **`+ 3f` padding** and the **1-second cache** both
  matter for clearance checks: right after staging the value is up to a
  second out of date, and it is inflated by 3 m by design.
- **Status:** [CONFIRMED]

### Static and structural helpers

| Member | Access | Note | Status |
|---|---|---|---|
| `UseParts(bool fromStaging, (Part, PolygonData)[] regions)` | **public static** | returns `UsePartData[]`; **the programmatic "click a part" entry point** | [PARTIAL] |
| `SetPlayerToBestControllable(Rocket[] rockets)` | public static | picks the player craft after a split | [PARTIAL] |
| `SetParts(Part[] newParts)` | public | rebuilds holder, joints, injections | [PARTIAL] |
| `SetJointGroup(JointGroup)` | public | | [PARTIAL] |
| `EnableCollisionImmunity(float duration)` | public | | [PARTIAL] |

**`UseParts` is the non-UI path** to activating parts (staging, toggles,
docking) without synthesising touch input — `Rocket.ClickPart` /
`RaycastPart` / `CanUsePart` are the UI path and all take
`SFS.Input.TouchPosition`. **Body not read.** `UsePartData` and
`PolygonData` are unexamined, and `CanUsePart` @188347 has an **unread
gate that likely rejects parts of unowned DLC** — [OPEN].

## Status summary

| Item | Status |
|---|---|
| `Rocket : Player, I_Physics` | [CONFIRMED] |
| Full field layout | [CONFIRMED] |
| `floating` means in water | [CONFIRMED] — both call sites |
| `FixedUpdate` call order and contents | [CONFIRMED] |
| `UpdateMass` runs every tick | [CONFIRMED] |
| Rotation writes `angularVelocity`, ignores inertia | [CONFIRMED] |
| `mass^-0.35` penalty above 200 | [CONFIRMED] |
| SAS = deadbeat `clamp(ω / one-tick-authority, ±1)` | [CONFIRMED] |
| SAS gates: manual input / `hasControl` / `IsOnSurface` / water 10% | [CONFIRMED] |
| `IsOnSurface` 5-contact cap | [CONFIRMED] |
| `GetRotation` 4-level fallback, `+90` inconsistency | [CONFIRMED] |
| `I_Physics` members are explicit implementations | [CONFIRMED] |
| `LocalPosition` is centre of mass | [CONFIRMED] |
| `set_PhysicsMode(false)` disables all colliders | [CONFIRMED] |
| Timewarp limits 0.1 / 3.0 m/s | [CONFIRMED] |
| `GetSizeRadius` 1 s cache, `+3` pad | [CONFIRMED] |
| `Inject_*` ↔ nested `INJ_*` interface mechanism | [CONFIRMED] |
| `UseParts` / `SetParts` bodies | [PARTIAL] — signatures only |
| `CanUsePart` gate | [OPEN] |
| Rotation model verified against live flight | [UNTESTED-LIVE] |
| The nested `INJ_*` interfaces' own entries | [OPEN] — Step 2 |
