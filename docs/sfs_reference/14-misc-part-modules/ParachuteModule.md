# `SFS.Parts.Modules.ParachuteModule`

**Migrated** from `docs/sfs_source_reference.md` §E6.1 (2026-08-28).

Deprioritised by agreement and written last in the old file. **Structure
and the load-bearing constants only; several bodies are deliberately
left [PARTIAL].**

The drag path this feeds:
[`../02-drag-aero/AeroModule.md`](../02-drag-aero/AeroModule.md) and
[`../02-drag-aero/Aero_Rocket.md`](../02-drag-aero/Aero_Rocket.md).

---

## ParachuteModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @262464 · 9 methods / 11 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `maxDeployHeight` | `double` | public | no | compared against **terrain-relative** height | [CONFIRMED] |
| `maxDeployVelocity` | `double` | public | no | | [CONFIRMED] |
| `drag` | `AnimationCurve` | public | no | **serialized Unity data — live-only** | [CONFIRMED] shape · [OPEN] values |
| `parachute` | `Transform` | public | no | **the force application point** | [CONFIRMED] |
| `state` | `Float_Reference` | public | no | current deployment, 0–1 | [CONFIRMED] |
| `targetState` | `Float_Reference` | public | no | commanded deployment | [CONFIRMED] |
| `onDeploy` | `UnityEvent` | public | no | | [CONFIRMED] |
| `deploySound_Partial`, `deploySound_Fully` | `AudioModule` | public | no | | [CONFIRMED] |
| `oldPosition` | `Double2` | **private** | no | for the visual weathervaning | [CONFIRMED] |

### Methods

#### DeployParachute(UsePartData data) -> void

- **Access:** **public** · IL @262542
- **Behavior:** the gates, read from the opcodes **in order**:
  - `Location.planet.HasAtmospherePhysics` — refuses in vacuum with
    `Msg_Cannot_Deploy_Parachute_In_Vacuum`
  - `planet.data.atmospherePhysics.parachuteMultiplier` — **a per-planet
    parachute effectiveness scalar**, on `Atmosphere_Physics`. Not
    previously recorded.
  - `Location.Height` vs `planet.AtmosphereHeightPhysics * 0.9` — deploy
    is only allowed **below 90% of the physics atmosphere height**
  - `Location.GetTerrainHeight(bool)` vs `maxDeployHeight` — **the deploy
    ceiling is measured above terrain**, not above the datum, so it
    behaves differently over mountains
  - `targetState` / `state` compared against `0f`
- **Gotchas:** the terrain-relative ceiling is the trap — a chute that
  deploys fine over an ocean may refuse over a mountain at the same
  `Location.Height`.
- **Status:** [PARTIAL] — **the full branch structure and which check
  produces which message were not fully transcribed**

`UpdateEnabled` @262847, `LateUpdate` @262873 and `AngleToOldPosition`
@262997 (the visual weathervaning) are **not read — [OPEN]**.

---

## `Aero_Rocket.ApplyParachuteDrag` — structure now read

@220368 — the method the drag chain flagged as **mutating both arguments
and bypassing the 0.2 lerp damping.**

```csharp
foreach (ParachuteModule p in rocket.partHolder.GetModules<ParachuteModule>()) {
    // gated on p.targetState.Value against 1f and 2f
    Vector2 pointVel = rocket.rb2d.GetPointVelocity(p.parachute.position);
    double  v2       = WorldView.ToGlobalVelocity(pointVel).sqrMagnitude;
    float   f        = (float)v2 * p.drag.Evaluate(p.state.Value);
    // accumulate f, and a force-weighted sum of p.parachute.position
}
// force += Σf ; centerOfDrag_World = weighted centroid
```

Two things worth noting.

- It uses **`rb2d.GetPointVelocity` at the parachute's own position**, so
  **a spinning craft gives each chute a different airspeed** — parachute
  drag is **the one place in the whole drag chain that is
  rotation-aware.**
- The coefficient is an **`AnimationCurve` evaluated at the deployment
  `state`**, i.e. **partial deployment is a curve lookup, not a linear
  ramp**, and the curve is serialized data that **must be read live.**

**Exact accumulation arithmetic not fully transcribed — [PARTIAL].**

## Status summary

| Item | Status |
|---|---|
| `ParachuteModule` field layout | [CONFIRMED] |
| `DeployParachute` is public; gate *set* identified | [CONFIRMED] |
| Deploy ceiling is terrain-relative, not datum-relative | [CONFIRMED] |
| 90% of `AtmosphereHeightPhysics` deploy limit | [CONFIRMED] |
| `Atmosphere_Physics.parachuteMultiplier` exists | [CONFIRMED] |
| `ApplyParachuteDrag` uses per-chute `GetPointVelocity` | [CONFIRMED] |
| Drag coefficient is an `AnimationCurve` of `state` | [CONFIRMED] — curve is live-only data |
| `DeployParachute` full branch structure | [PARTIAL] |
| `ApplyParachuteDrag` exact accumulation | [PARTIAL] |
| `UpdateEnabled` / `LateUpdate` / `AngleToOldPosition` | [OPEN] |
| The `drag` curve's actual values | [OPEN] — live-only |
