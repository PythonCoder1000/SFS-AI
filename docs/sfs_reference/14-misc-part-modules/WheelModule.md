# `SFS.Parts.WheelModule`

**Migrated** from `docs/sfs_source_reference.md` §E6.2 (2026-08-28).

---

## WheelModule

**Namespace:** SFS.Parts
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `SFS.World.Rocket/INJ_TurnAxisWheels`, `INJ_Rb2d` (injection targets)
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @235157 · 9 methods / 8 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `power` | `float` | public | no | drive strength | [CONFIRMED] |
| `traction` | `float` | public | no | applied in `OnCollisionStay2D` | [CONFIRMED] |
| `maxAngularVelocity` | `float` | public | no | hard clamp | [CONFIRMED] |
| `wheelSize` | `float` | public | no | | [CONFIRMED] |
| `angularVelocity` | `float` | public | no | **live state** | [CONFIRMED] |
| `on` | `Bool_Reference` | public | no | | [CONFIRMED] |
| `<TurnAxis>k__BackingField` | `float` | private | no | injected | [CONFIRMED] |
| `<Rb2d>k__BackingField` | `Rigidbody2D` | private | no | injected | [CONFIRMED] |

> `TurnAxis` and `Rb2d` are `final virtual` public setters — **injection
> targets**. `TurnAxis` is fed from **`Rocket.output_TurnAxisWheels`,
> which is the raw, undamped `arrowkeys.turnAxis`**, *not* the
> SAS-processed one. **So wheels steer on manual input only and are
> unaffected by rotation damping.**

### Methods

#### Update() -> void

- **Access:** private instance (Unity message) · IL @235511
- **Behavior:** the spin-up/spin-down arithmetic:
  ```csharp
  if (on.Value && TurnAxis != 0f)
      angularVelocity += Time.deltaTime * power * ...;            // driven
  else
      angularVelocity = Mathf.Clamp(angularVelocity, on.Value ? -0.05f : -0.25f,
                                                     on.Value ?  0.05f :  0.25f);
  angularVelocity = Mathf.Clamp(angularVelocity, -maxAngularVelocity, maxAngularVelocity);
  ```
- **Gotchas:** the four literals — **−0.05 / 0.05 (powered) and −0.25 /
  0.25 (unpowered)** — are the **idle-roll clamps**: a powered wheel with
  no steering input is held near-stationary (**braking**), an unpowered
  one is allowed to **free-roll five times faster**.
- **Status:** [PARTIAL] — **exact placement of `power` / `deltaTime` in
  the driven branch was not fully transcribed**

#### OnCollisionStay2D(Collision2D) -> void

- **Access:** private instance · IL @235315 — **where `traction` is
  applied**
- **Status:** [PARTIAL] — not read

#### ToggleEnabled() -> void

- **Access:** **public** · IL @235227
- **Status:** [PARTIAL] — signature only

## Status summary

| Item | Status |
|---|---|
| `WheelModule` field layout | [CONFIRMED] |
| Wheels driven by raw `output_TurnAxisWheels`, no SAS | [CONFIRMED] |
| Idle clamps ±0.05 powered / ±0.25 unpowered | [CONFIRMED] |
| `Update` driven-branch arithmetic | [PARTIAL] |
| `OnCollisionStay2D` / traction model | [PARTIAL] |
| `ToggleEnabled` body | [OPEN] |
