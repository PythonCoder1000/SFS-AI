# `SFS.Logs.Challenge` and `SFS.Stats.ChallengeRecorder`

**Group file.** The challenge catalogue and the per-craft progress
recorder.

**Migrated** from `docs/sfs_source_reference.md` §E7.3 (2026-08-28).

**These are not Steamworks achievements** — pure in-game state, fully
reflectable, and serialised into the world save (see
[`../07-saveload/save-records.md`](../07-saveload/save-records.md), where
`WorldSave.completeChallenges` is a `HashSet<string>` of these ids).

---

## Challenge

**Namespace:** SFS.Logs
**Kind:** class (`serializable`)
**Extends:** UnityEngine.ScriptableObject
**Implements:** —
**Status:** [CONFIRMED] layout
**Depth:** FULL
**IL:** `scratch/full_il.txt` @73480 · 4 methods / 9 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `displayPriority` | `int` | public | no | | [CONFIRMED] |
| `id` | `string` | public | no | **the key stored in `WorldSave.completeChallenges`** | [CONFIRMED] |
| `owner` | `Planet` | public | no | which body the challenge belongs to | [CONFIRMED] |
| `icon` | `Sprite` | public | no | | [CONFIRMED] |
| `title` | `Func<string>` | public | no | **cast and invoke** to get the text | [CONFIRMED] |
| `description` | `Func<string>` | public | no | same | [CONFIRMED] |
| `difficulty` | `SFS.Logs.Difficulty` | public | no | | [CONFIRMED] |
| `steps` | `List<ChallengeStep>` | public | no | ordered | [CONFIRMED] |
| `returnSafely` | `bool` | public | no | | [CONFIRMED] |

### Methods

#### CollectChallenges() -> List&lt;Challenge&gt;

- **Access:** **public static** · IL @73561
- **Returns:** the full challenge catalogue, enumerable at runtime, with
  `id`, `owner` planet, `difficulty`, ordered `steps` and the
  `returnSafely` flag.
- **Status:** [CONFIRMED] signature · [OPEN] body

### The second, already-built catalogue

The earlier reference also records **`SFS.Base.worldBase.challengesArray`**
(`Challenge[]`, static), which is what the probe's `achievements` command
uses. Both reach the same data; `challengesArray` **avoids re-running the
collection**.

**That path is [UNTESTED-LIVE]** and the field was **not re-verified
against IL** in this pass — marked **[PARTIAL]**.

### ChallengeStep

`SFS.Logs.ChallengeStep` @74974 is an abstract base; **its subclasses
were not enumerated — [PARTIAL]**, so **what a step actually tests is
unconfirmed.**

### SFS.Logs.Difficulty

**Namespace:** SFS.Logs · **Kind:** enum · IL @75676 ·
**Status:** [CONFIRMED] shape · [OPEN] member names

> Note this is a **different type** from
> [`../06-soi-terrain/Difficulty.md`](../06-soi-terrain/Difficulty.md)
> (`SFS.WorldBase.Difficulty`, a class). Two unrelated `Difficulty`
> types exist in the assembly; `FindType` needs the full name.

---

## ChallengeRecorder

**Namespace:** SFS.Stats
**Kind:** class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] API
**Depth:** FULL
**IL:** `scratch/full_il.txt` @72460 · 9 methods / 4 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `eligibleSteps` | *(collection)* | **private** | no | | [CONFIRMED] shape |
| `progress` | `Dictionary<Challenge, (int, string)>` | **private** | no | serialised into the save | [CONFIRMED] |
| `complete` | `HashSet<Challenge>` | **private** | no | serialised into the save | [CONFIRMED] |
| `owner` | | **private** | no | | [CONFIRMED] shape |

### Methods

| Signature | IL | Note | Status |
|---|---|---|---|
| `UpdateEligibleSteps()` | @72504 | | [CONFIRMED] signature |
| `TryCompleteSteps(Location location)` | @72642 | **the evaluation call — takes a `Location`** | [CONFIRMED] signature |
| `OnCrash(float impactVelocity)` | @72807 | | [CONFIRMED] signature |
| `Merge(ChallengeRecorder b)` | @73046 | | [CONFIRMED] signature |
| `Split(out Dictionary<…> progress, out HashSet<Challenge> complete)` | @73181 | | [CONFIRMED] signature |
| `GetCompleteChallenges()` → `HashSet<Challenge>` | @73226 | **the clean per-craft achievement read** | [CONFIRMED] signature |

> **`TryCompleteSteps(Location)` taking a plain `Location` rather than a
> live craft is notable: challenge progress is evaluated against a state
> vector.** So in principle an agent could ask "would this trajectory
> complete a step" — **though `CompleteStep` has side effects (rewards,
> messages), so speculative evaluation is *not* safe without reading its
> body. [OPEN].**

`progress` / `complete` are serialised into the save, which is why
`StatsRecorder.Initialize` @70660 takes them as parameters.

## Status summary

| Item | Status |
|---|---|
| `Challenge` layout; `CollectChallenges()` is public static | [CONFIRMED] |
| Challenges are in-game state, not Steamworks | [CONFIRMED] |
| `ChallengeRecorder` public API | [CONFIRMED] |
| `TryCompleteSteps` takes a `Location` | [CONFIRMED] |
| `SFS.Base.worldBase.challengesArray` as an alternative catalogue | [PARTIAL] — not re-verified this pass · [UNTESTED-LIVE] |
| `ChallengeStep` subclasses — what a step tests | [PARTIAL] |
| Whether `TryCompleteSteps` is side-effect-free enough to use speculatively | [OPEN] — `CompleteStep` body not read |
| `SFS.Logs.Difficulty` member names | [OPEN] |
| All `ChallengeRecorder` and `Challenge` bodies | [OPEN] |
