# `SFS.World.Physics` — the physics/rails driver

**Migrated** from `docs/sfs_source_reference.md` §B5.1 and §D4.3
(2026-08-28).

The SOI-crossing branch of `Update()` is documented in
[`../06-soi-terrain/Planet.md`](../06-soi-terrain/Planet.md), since that
is where its two predicates live. Rails:
[`Trajectory.md`](Trajectory.md).

---

## Physics

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @159119 · 18 methods / 6 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `location` | `WorldLocation` | public | no | the live observable location | [CONFIRMED] |
| `loader` | `WorldLoader` | public | no | | [CONFIRMED] |
| `trajectory` | `Trajectory` | public | no | **maintained only on rails — do not read directly** | [CONFIRMED] |
| `savedObject` | `I_Physics` | **private** | no | the craft | [CONFIRMED] |
| `lastTrajectory_Input` | `(Double2, Double2, double)` | private | no | memo key | [CONFIRMED] |
| `lastTrajectory` | `Trajectory` | private | no | the physics-mode answer | [CONFIRMED] |

### Properties

`PhysicsObject` and `PhysicsMode` are **public properties here** — **use
these rather than `Rocket`'s explicit `I_Physics` implementations**,
which reflect badly. **`rocket.physics.PhysicsMode` is the clean read.**

### Methods

#### SetLocationAndState(Location newLocation, bool physicsMode) -> void

**The teleport entry point.**

- **Access:** public instance · IL @159246
- **Behavior** (physics-mode branch):
  ```csharp
  location.Value = newLocation;                                   // WorldLocation guard applies
  PhysicsObject.LocalPosition = WorldView.ToLocalPosition(location.position);
  PhysicsObject.LocalVelocity = WorldView.ToLocalVelocity(location.velocity);
  PhysicsObject.PhysicsMode   = true;
  trajectory = null;                                              // forces recompute
  ```
- **Side effects:** moves the craft; nulls `trajectory`.
- **Gotchas:** note the `WorldView.ToLocalPosition` / `ToLocalVelocity`
  conversions — world (`Double2`, planet-relative, metres) and
  Unity-local (`Vector2`) are **different frames**, and this is the
  sanctioned bridge. The `location.Value` write goes through
  `WorldLocation.set_Value`, so **a `Location` with a null planet
  silently does nothing here too** — the teleport appears to succeed and
  the craft does not move. See
  [`Location.md`](Location.md).
- **Status:** [CONFIRMED] · [UNTESTED-LIVE] as a teleport

#### set_PhysicsMode(bool) -> void

- **Access:** public instance property setter · IL @159169
- **Behavior:** `set_PhysicsMode(true)` **rebases the craft from the
  trajectory before enabling physics**:
  `location.Value = trajectory.GetLocation(WorldTime.main.worldTime)`,
  then pushes position and velocity through `WorldView.ToLocalPosition` /
  `ToLocalVelocity`.
- **Gotchas:** **leaving rails snaps the craft onto the analytic path** —
  a small discontinuity an agent measuring position across that
  transition will see.
- **Status:** [CONFIRMED]

#### Update() -> void

- **Access:** instance (Unity message) · IL @159627
- **Behavior:** the physics/rails branch, including the SOI-crossing
  test. **Full body transcribed in
  [`../06-soi-terrain/Planet.md`](../06-soi-terrain/Planet.md).**
- **Gotchas:** **crossing an SOI boundary in physics mode forces the
  craft onto rails** — `PhysicsMode = false`,
  `trajectory.EnterNextPath()`, then a re-entrant `Update()` in the same
  frame.
- **Status:** [CONFIRMED]

#### InOrbit() -> bool

- **Access:** public instance · IL @159595
- **Behavior:**
  ```csharp
  Orbit o = Orbit.TryCreateOrbit(location.Value, false, false, out bool success);
  return success && o.periapsis > o.Planet.OrbitRadius;
  ```
- **Gotchas:** **"in orbit" means periapsis above the planet's
  `OrbitRadius`** — *not* above the surface, and *not* "eccentricity
  < 1". `OrbitRadius` is a `Planet` property distinct from `Radius`.
- **Status:** [CONFIRMED]

#### GetTrajectory() -> Trajectory

- **Access:** public instance · IL @159766
- **Behavior:**
  ```csharp
  Trajectory GetTrajectory() {
      if (PhysicsObject.PhysicsMode) {
          var key = (location.Value.position - PhysicsObject.LocalVelocity * Time.deltaTime,
                     location.Value.velocity, location.Value.time);
          if (key != lastTrajectory_Input) {
              lastTrajectory_Input = key;
              lastTrajectory = Trajectory.CreateTrajectory(location.Value);
          }
          return lastTrajectory;          // physics mode
      }
      return trajectory;                  // rails only
  }
  ```
- **Gotchas:** memoises on a `(position, velocity, time)` tuple and
  **back-projects position by one frame**
  (`position - LocalVelocity * Time.deltaTime`) before hashing. So
  successive calls in one frame are cheap, and **the trajectory is
  computed from a position one `deltaTime` behind the current one.**

  **The public `trajectory` field is maintained only on rails.** In
  physics mode the live answer is the private `lastTrajectory`, and
  `trajectory` holds whatever was last written by `set_PhysicsMode` /
  `SetLocationAndState` — which `SetLocationAndState` sets to `null`
  outright. **Always call `GetTrajectory()`; never read the `trajectory`
  field.** This confirms from IL a gotcha recorded empirically in the
  earlier reference ("`.trajectory` field is STALE except on rails").
- **Status:** [CONFIRMED]

## Status summary

| Item | Status |
|---|---|
| `Physics` field layout; public `PhysicsMode` / `PhysicsObject` | [CONFIRMED] |
| `SetLocationAndState` body (teleport) | [CONFIRMED] |
| Null-planet teleport silently no-ops | [CONFIRMED] |
| `set_PhysicsMode(true)` rebases from the trajectory | [CONFIRMED] |
| `InOrbit()` = `periapsis > Planet.OrbitRadius` | [CONFIRMED] |
| `GetTrajectory` memo + one-frame back-projection | [CONFIRMED] |
| The public `trajectory` field is stale off rails | [CONFIRMED] |
| SOI crossing forces rails | [CONFIRMED] in IL · [UNTESTED-LIVE] |
| The remaining ~12 methods | [OPEN] |
| Teleport via `SetLocationAndState` | [UNTESTED-LIVE] |
