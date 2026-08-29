# `SFS.World.WorldTime` — the simulation clock and timewarp

**Migrated** from `docs/sfs_source_reference.md` §E5.1 (2026-08-28).

---

## WorldTime

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @198504 · 25 methods / 5 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `WorldTime` | public | **static** | the singleton | [CONFIRMED] |
| `timewarpIndex` | `int` | public | no | the UI's ladder position — **not updated by `SetState`** | [CONFIRMED] |
| `worldTime` | `double` | public | no | the simulation clock, seconds; persists across saves | [CONFIRMED] |
| `timewarpSpeed` | `double` | public | no | | [CONFIRMED] |
| `realtimePhysics` | `Bool_Local` | public | no | **false ⇒ on rails** | [CONFIRMED] |

`realtimePhysics` is the flag that gates **heat destruction**, **mass
recalculation** and **manual rotation input**, and it is the one
`Physics.Update` clears on an SOI crossing. `worldTime` is what
`WorldLocation.get_Value` stamps into a `Location`.

### The two timewarp ladders

**Decoded from the `.data` blobs.**

#### GetTimewarpSpeed_Physics(int i) -> double

- **Access:** public · IL @198909 — blob `D_00140030`,
  `01 00 00 00 02 00 00 00 03 00 00 00 05 00 00 00`
- **Behavior:**
  ```
  physics = [1, 2, 3, 5]
  speed   = physics[i]
  ```
- **Status:** [CONFIRMED]

#### GetTimewarpSpeed_Rails(int i) -> double

- **Access:** public · IL @198927 — blob `D_00140008`,
  `01 00 00 00 05 00 00 00 19 00 00 00`
- **Behavior:**
  ```csharp
  int[] rails = { 1, 5, 25 };
  speed = rails[i % 3] * Math.Pow(100.0, (int)((float)i / 3f));
  ```
  which expands to **1, 5, 25, 100, 500, 2 500, 10 000, 50 000,
  250 000, …** — a repeating 1/5/25 pattern stepped by ×100 every three
  indices, unbounded in principle and capped by `MaxIndex` (private).
- **Status:** [CONFIRMED]

`maxPhysicsTimewarpIndex = [2, 2, 3]` by difficulty bounds the physics
ladder — see
[`../06-soi-terrain/Difficulty.md`](../06-soi-terrain/Difficulty.md).

### The two modes work in opposite directions

```csharp
float TimeScale       => realtimePhysics ?  (float)timewarpSpeed : 1f;
static float FixedDeltaTime =>
    main.realtimePhysics ? Time.fixedDeltaTime
                         : (float)main.timewarpSpeed * Time.fixedDeltaTime;
```

- **Physics timewarp** (`realtimePhysics == true`) raises Unity's
  `Time.timeScale`; the simulation runs *faster in real time* with an
  unchanged step. **Everything is still simulated.**
- **Rails timewarp** (`realtimePhysics == false`) leaves `timeScale` at 1
  and instead multiplies `WorldTime.FixedDeltaTime`; **the world steps
  analytically in large chunks.**

> **`WorldTime.FixedDeltaTime` and `Time.fixedDeltaTime` are NOT
> interchangeable.** `HeatManager` uses the former;
> `Rocket.ApplyTorque` and `BoosterModule.FixedUpdate` use the latter.
> **Code that swaps them silently changes behaviour under warp only.**

### Methods

#### SetState(double timewarpSpeed, bool realtimePhysics, bool showMsg) -> void

**The direct control point.**

- **Access:** **public** instance · IL @199281, body read
- **Behavior:**
  ```csharp
  this.timewarpSpeed = timewarpSpeed;
  this.realtimePhysics.Value = realtimePhysics;
  Time.timeScale = TimeScale;
  if (showMsg) MsgDrawer.main.Log(Loc.main.Msg_Timewarp_Speed.Inject(...));
  ```
- **Side effects:** sets Unity's global `Time.timeScale`.
- **Gotchas:** **no validation** — no `CanTimewarp` check, no clamp
  against `MaxIndex`, no difficulty bound. **An agent can set an
  arbitrary speed and mode directly, bypassing every gate that
  `AccelerateTime` applies.** It also **does not update
  `timewarpIndex`**, so the UI and the actual speed can disagree after a
  direct call.
- **Status:** [CONFIRMED] · [UNTESTED-LIVE] as a control path

#### The gated path

`AccelerateTime()` @198689 → `Accelerate_Rails()` /
`Accelerate_Physics()` → `ApplyState(bool)`, with `DecelerateTime()`,
`StopTimewarp(bool)` @199040, `CheckStopTimewarp_ForChangedPlayer()`
@199014 and the private `ExitAutomaticTimewarp` /
`CheckStopTimewarp_ForUpdate(timeOld, timeNew)` @199114 — **the last is
what consults `Trajectory.GetStopTimewarpTime` to drop out of warp at an
encounter.**

**Bodies not read — [PARTIAL].**

#### Other public members

| Signature | IL | Status |
|---|---|---|
| `static bool CanTimewarp(bool showMsg, bool showSpeed, out bool isInWater)` | @198526 | [CONFIRMED] — delegates to `Player.CanTimewarp` |
| `SetTimewarpIndex_ForLoad(int)` | @198673 | [CONFIRMED] signature |
| `MaxTimewarpSpeed` | | public static property |
| `MaxIndex`, `MaxPhysicsIndex` | | **private** |
| `static ShowCannotTimewarpBelowHeightMsg(double, I_MsgLogger, bool)` | | used by `Rocket.CanTimewarp` |

## Status summary

| Item | Status |
|---|---|
| `WorldTime` field layout; `realtimePhysics` = not-on-rails | [CONFIRMED] |
| Physics ladder `[1, 2, 3, 5]` | [CONFIRMED] — blob decoded |
| Rails ladder `rails[i%3] · 100^(i/3)` from `[1, 5, 25]` | [CONFIRMED] — blob decoded |
| `TimeScale` and `FixedDeltaTime` scale in opposite modes | [CONFIRMED] |
| `SetState` is public and validates nothing | [CONFIRMED] |
| `SetState` does not update `timewarpIndex` | [CONFIRMED] |
| `AccelerateTime` / `ApplyState` / `CheckStopTimewarp_ForUpdate` bodies | [PARTIAL] |
| `MaxIndex` / `MaxPhysicsIndex` values | [OPEN] |
| Direct `SetState` timewarp control | [UNTESTED-LIVE] |
