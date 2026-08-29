# `SFS.World.Trajectory` — the rails path chain

**Migrated** from `docs/sfs_source_reference.md` §B5.2, §B5.2.1, §B5.2.2
and §D4.3 (2026-08-28).

> **Correction made during migration.** The old file's §B5.5 status table
> still listed "`Trajectory` path-transition machinery" as **[PARTIAL]**,
> but §B5.2.1 and §B5.2.2 were a later depth pass that read those bodies
> and marked them [CONFIRMED]. The status table was not updated. **The
> bodies are CONFIRMED**; the [PARTIAL] row was stale. Recorded rather
> than silently overwritten.

Driver: [`Physics.md`](Physics.md). Conic sections: [`Orbit.md`](Orbit.md).

---

## Trajectory

**Namespace:** SFS.World
**Kind:** class (`serializable`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @195673 · 15 methods / 1 field

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `paths` | `List<I_Path>` | public | no | the chain of conic sections; `paths[0]` is the current one | [CONFIRMED] |

**Almost every instance method is a forward to `paths[0]`** —
`GetLocation(time)` @195780, `GetPathEndTime()` @195796,
`GetStopTimewarpTime(old, new)` @195811 all index element 0 **with no
bounds check**. An empty `Trajectory`
(`Trajectory.Empty`) throws `ArgumentOutOfRangeException` on any of them.

### Statics

All public: `Empty`, `CreateTrajectory(Location)` @195724,
`CreateStationaryTrajectory(StaticWorldObject)`, `CreatePath(Location)`
@195754. **`CreatePath(Location)` is the direct "what orbit would I be on
from this state vector" call.**

### Methods

#### CheckPathTransition(double time) -> void

- **Access:** public instance · IL @195828, body read
- **Behavior:** `if (time > GetPathEndTime()) EnterNextPath();`
- **Gotchas:** **a strict `>`.** Exactly at `GetPathEndTime()` the
  transition does not fire.
- **Status:** [CONFIRMED]

#### EnterNextPath() -> void

- **Access:** public instance · IL @195863, body read
- **Behavior:**
  ```csharp
  if (paths.Count == 1) return;                       // never empties the list
  paths.RemoveAt(0);
  CalculatePaths();
  ```
- **Gotchas:** **`EnterNextPath` cannot empty `paths`.** The
  `paths.Count == 1` guard returns early, so `paths[0]` is always valid —
  which is what makes the unchecked `paths[0]` forwarding safe in
  practice **on a trajectory the game built**. A hand-constructed
  `Trajectory.Empty` still throws.
- **Called by:** the SOI-crossing branch of `Physics.Update()`.
- **Status:** [CONFIRMED]

#### CheckEncounters() -> void

- **Access:** public instance · IL @195845, body read
- **Behavior:** `if (paths.Last().UpdateEncounters()) CalculatePaths();`
- **Status:** [CONFIRMED]

#### ConicSectionsCount { get; } -> int

- **Access:** private instance property · IL @195886, body read
- **Behavior:** `VideoSettingsPC.main.settings.orbitLinesCount`
- **Gotchas:** > **How far ahead the game predicts is a *video
  setting*.** The number of future conic sections computed — and
  therefore **how many SOI transitions ahead a trajectory extends** —
  **depends on the player's graphics options**, not on physics. An agent
  that plans against `trajectory.paths` is planning against a
  **user-configurable horizon** and must not assume a fixed depth. This
  is the single least obvious thing in this entry.
- **Status:** [CONFIRMED]

#### CalculatePaths() -> void

- **Access:** private instance · IL @195899, body read
- **Behavior:**
  ```csharp
  while (paths.Count < ConicSectionsCount) {
      if (!GetNextPath(out I_Path next)) return;
      paths.Add(next);
  }
  ```
- **Gotchas:** stops **early and silently** whenever `GetNextPath`
  returns false, so **a short `paths` list is normal, not an error**.
- **Status:** [CONFIRMED]

#### GetNextPath(out I_Path nextPath) -> bool — the frame changes

- **Access:** private instance · IL @195932, body transcribed
- **Behavior:**
  ```csharp
  I_Path last = paths[paths.Count - 1];
  if (!(last is Orbit) || last.NextPlanet == null) { nextPath = null; return false; }

  if (last.PathType == PathType.Escape) {                 // leaving this SOI
      // bail-out: don't chain a third section after Encounter -> Escape
      if (paths.Count > 1
          && paths[paths.Count - 2].PathType == PathType.Encounter
          && ConicSectionsCount == 3) { nextPath = null; return false; }

      Location craft  = last.GetLocation(last.PathEndTime);
      Location parent = last.Planet.orbit.GetLocation(last.PathEndTime);
      nextPath = CreatePath(craft + parent);              // Location.op_Addition
      return true;
  }

  if (last.PathType == PathType.Encounter) {              // entering a satellite's SOI
      Location craft  = last.GetLocation(last.PathEndTime);
      Location target = last.NextPlanet.orbit.GetLocation(last.PathEndTime);
      nextPath = CreatePath(new Location(
          last.PathEndTime, last.NextPlanet,
          craft.position - target.position,
          craft.velocity - target.velocity));
      return true;
  }

  nextPath = null; return false;
  ```
- **Gotchas:** **the two branches are exact inverses, and together they
  are the game's whole patched-conic frame algebra:**
  - **Escape** *lifts* the state into the parent frame — add the craft's
    planet-relative state to the planet's own state in its parent's frame.
  - **Encounter** *descends* into the satellite frame — subtract the
    target's state from the craft's.

  The `ConicSectionsCount == 3` bail-out is a **deliberate truncation**:
  at the lowest orbit-line setting the game refuses to compute a third
  section after an encounter-then-escape chain. **Another place the
  prediction horizon depends on a video setting.**
- **Status:** [CONFIRMED]

---

## `Location.op_Addition` — resolved here

**[CONFIRMED]** @160891. The `GetNextPath` Escape branch is what it
exists for:

```csharp
public static Location operator +(Location a, Location b)
    => new Location(b.time, b.planet,
                    a.position + b.position,
                    a.velocity + b.velocity);
```

It takes **`time` and `planet` from the right operand** and sums the
vectors — so it is **not commutative**, and it is not "adding two
locations" in any general sense. **It is precisely a *frame lift*:**
`childRelativeState + frameState` = the same state expressed in the
frame's own planet. Use it only that way. The Encounter branch does the
inverse by hand rather than defining an operator for it.

---

## PathType

**Namespace:** SFS.World
**Kind:** enum
**Status:** [CONFIRMED]
**Depth:** FULL

`Eternal = 0`, `Escape = 1`, `Encounter = 2` — confirmed from the enum's
`literal` fields.

## Status summary

| Item | Status |
|---|---|
| `Trajectory` forwards to `paths[0]`, unchecked | [CONFIRMED] |
| `EnterNextPath` cannot empty `paths` | [CONFIRMED] |
| `CheckPathTransition` uses a strict `>` | [CONFIRMED] |
| **Prediction horizon is a video setting** (`orbitLinesCount`) | [CONFIRMED] |
| `CalculatePaths` stops silently on a short chain | [CONFIRMED] |
| `GetNextPath` Escape/Encounter frame algebra | [CONFIRMED] |
| `Location.op_Addition` is a frame lift, not commutative | [CONFIRMED] — resolves the open item in `Location.md` |
| `PathType` values | [CONFIRMED] |
| `CreateTrajectory` / `CreatePath` / `CreateStationaryTrajectory` bodies | [OPEN] |
| `GetStopTimewarpTime` body | [OPEN] |
| `I_Path`, `StaticWorldObject` own entries | [OPEN] — Step 2 |
