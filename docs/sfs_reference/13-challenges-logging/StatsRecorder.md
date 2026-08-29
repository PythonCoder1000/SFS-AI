# `SFS.Stats.StatsRecorder` — the game's own flight-achievement record

**Migrated** from `docs/sfs_source_reference.md` §E7.2 (2026-08-28).

Relevant to an agent because **this is the game's own answer to "what has
this flight achieved" — a ready-made reward signal.**

---

## StatsRecorder

**Namespace:** SFS.Stats
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @70185 · 31 methods / 7 fields

`private const float RecordTime = 1f` — **the sampling period.**

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `location` | `WorldLocation` | public | no | | [CONFIRMED] |
| `player` | `Player` | public | no | | [CONFIRMED] |
| `branch` | `int` | public | no | index into `LogManager.branches` | [CONFIRMED] |
| `location_Old` | `Location` | **private** | no | previous sample | [CONFIRMED] |
| `tracker` | `StatsRecorder.Tracker` | public | no | | [CONFIRMED] |
| `challengeRecorder` | `ChallengeRecorder` | public | no | | [CONFIRMED] |
| `RecordTime` | `float` | private | **const** | `1f` | [CONFIRMED] |

`Rocket.stats` points here.

### Methods

#### Record() -> void

- **Access:** instance · IL @70722
- **Behavior:** runs on the 1-second cadence and calls four tracker
  methods **in order**:
  ```csharp
  Location l = location.Value;
  tracker.Record_Landed(l);
  tracker.Record_Height(l);
  tracker.Record_Orbit(l);
  tracker.Record_Atmosphere(l);
  ```
- **Gotchas:** **the game continuously classifies the craft's state into
  landed / height band / orbit state / atmosphere state**, each with its
  own `Log_*` formatter (`Log_Landed`, `Log_Height`, `Log_Orbit`,
  `Log_Atmosphere`, `Log_Reentry`, `Log_Planet`, `Log_LeftCapsule`,
  `Log_Flag`, `Log_CollectRock` — all `private static`, returning
  `List<string>`).
- **Status:** [CONFIRMED]

`Tracker` exposes the nested value types `State_Orbit` and
`State_Atmosphere`, visible in `Initialize`'s signature @70660. **Tracker
internals are [PARTIAL].**

#### Public event hooks

| Signature | IL | Status |
|---|---|---|
| `OnLeaveCapsule(string astronautName)` | | [CONFIRMED] signature |
| `OnPlantFlag(double angleDegrees)` | | [CONFIRMED] signature |
| `OnCollectRock(double angleDegrees)` | | [CONFIRMED] signature |
| `OnCrash(float impactVelocity)` | | [CONFIRMED] signature |
| **`static OnSplit(StatsRecorder A, StatsRecorder B)`** | @70385 | [CONFIRMED] signature |
| **`static OnMerge(StatsRecorder A, StatsRecorder B)`** | @70472 | [CONFIRMED] signature |

The two statics are the stats-side counterparts to `Staging.OnSplit` /
`OnMerge` and `JointGroup.RecreateRockets`.

#### HasFlown() -> bool

- **Access:** public instance · IL @70885
- **Behavior:** walks `LogManager.branches` (a `Dictionary<int, Branch>`,
  each `Branch` having `parentA`) with a **hard iteration cap of 1000**
  and a user-visible message on overrun — i.e. **the flight history is a
  linked branch tree, guarded against cycles.**
- **Gotchas:** **mission history is per-branch and survives splits and
  merges**, which means an agent can ask the game "has this vehicle
  flown" rather than tracking it itself.
- **Status:** [CONFIRMED] · `LogManager` itself **not read — [PARTIAL]**

## Status summary

| Item | Status |
|---|---|
| `StatsRecorder` layout; `RecordTime = 1f` | [CONFIRMED] |
| `Record()` calls four `Tracker.Record_*` classifiers | [CONFIRMED] |
| Public event hooks + static `OnSplit`/`OnMerge` | [CONFIRMED] |
| `HasFlown()` walks a branch tree with a 1000-iteration cap | [CONFIRMED] |
| `Tracker` internals (`State_Orbit`, `State_Atmosphere`) | [PARTIAL] |
| `LogManager` / `Branch` | [PARTIAL] |
| The nine `Log_*` formatters | [OPEN] |
| `Initialize` body | [OPEN] |
