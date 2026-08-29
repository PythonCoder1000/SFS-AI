# The save records — `Blueprint`, `PartSave`, `RocketSave`, `StageSave`, `JointSave`, `WorldSave`

**Group file.** Six plain serializable records plus one nested type.
They are documented together because their schemas only make sense
relative to each other — in particular, **two of them reference parts by
array index**, which is a cross-record invariant no single entry can
carry.

`SFS.Builds.Blueprint` lives in `SFS.Builds` but is filed here rather
than in `16-builds/` because it is a save record, not editor UI. (The
plan explicitly leaves per-type folder assignment to Step 1/2.)

**Migrated** from `docs/sfs_source_reference.md` §D5.1–D5.3
(2026-08-28).

Serialization layer: [`JsonWrapper.md`](JsonWrapper.md). Turning these
back into a flying rocket: [`RocketManager.md`](RocketManager.md).

---

## Blueprint

**Namespace:** SFS.Builds
**Kind:** class (`[Serializable]`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @86743 · 4 methods / 6 fields

**The rocket design format.** Six fields, and **no joints** —
connectivity is *derived* at spawn time.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `center` | `float` | public | no | | [CONFIRMED] |
| `parts` | `PartSave[]` | public | no | the design | [CONFIRMED] |
| `stages` | `StageSave[]` | public | no | **references `parts` by index** | [CONFIRMED] |
| `rotation` | `float` | public | no | | [CONFIRMED] |
| `offset` | `Vector2` | public | no | | [CONFIRMED] |
| `interiorView` | `bool` | public | no | | [CONFIRMED] |

### On-disk layout

**[CONFIRMED]** from `Blueprint.Save` @86811 / `TryLoad` @86833 — one
**folder** per blueprint under `BlueprintsFolder`:

```
<BlueprintsFolder>/<name>/
    Version.txt        JsonWrapper.SaveAsJson(file, version, pretty: false)
    Blueprint.txt      JsonWrapper.SaveAsJson(file, blueprint, pretty: true)
```

`TryLoad` reads **only `Blueprint.txt`**, via
`JsonWrapper.TryLoadJson<Blueprint>`.

**Status:** [CONFIRMED] layout · [PARTIAL] `Save`/`TryLoad` bodies

---

## PartSave

**Namespace:** SFS.Parts
**Kind:** class (`[Serializable]`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @239253 · 5 methods / 8 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `name` | `string` | public | no | the part id — **must match a key in `PartsLoader.parts`** | [CONFIRMED] |
| `position` | `Vector2` | public | no | `transform.localPosition` | [CONFIRMED] |
| `orientation` | `Orientation` | public | no | | [CONFIRMED] |
| `temperature` | `float` | public | no | **field initialiser is `+∞`** — see the gotcha | [CONFIRMED] |
| `NUMBER_VARIABLES` | `Dictionary<string,double>` | public | no | part of the entire part configuration | [CONFIRMED] |
| `TOGGLE_VARIABLES` | `Dictionary<string,bool>` | public | no | | [CONFIRMED] |
| `TEXT_VARIABLES` | `Dictionary<string,string>` | public | no | | [CONFIRMED] |
| `burns` | `BurnMark.BurnSave` | public | no | burn marks; null if the part has none | [CONFIRMED] |

### Methods

#### .ctor(Part part)

- **Access:** public instance · IL @239346, body read
- **Behavior:**
  ```csharp
  temperature       = float.PositiveInfinity;      // field initialiser
  NUMBER_VARIABLES  = new(); TOGGLE_VARIABLES = new(); TEXT_VARIABLES = new();
  name              = part.name;
  position          = (Vector2)part.transform.localPosition;
  orientation       = part.orientation.orientation.Value;
  temperature       = part.temperature;
  if (part.burnMark != null) burns = new BurnSave(part.burnMark.burn);
  NUMBER_VARIABLES  = part.variablesModule.doubleVariables.GetSaveDictionary();
  TOGGLE_VARIABLES  = part.variablesModule.boolVariables.GetSaveDictionary();
  TEXT_VARIABLES    = part.variablesModule.stringVariables.GetSaveDictionary();
  ```
- **Gotchas:** two, both significant.
  1. **The three `*_VARIABLES` dictionaries are the entire part
     configuration** — size, variant, fuel level, custom text,
     everything parametric. They come from `Part.variablesModule`'s three
     `VariableList` objects via `GetSaveDictionary()`. This is the input
     side of the parametric-expression system — see
     [`../08-parametric-expressions/Compute.md`](../08-parametric-expressions/Compute.md).
  2. **`temperature`'s field initialiser is `+∞`** (`ldc.r4
     (00 00 80 7f)`) before being overwritten from the part. This is
     independent evidence that **`+∞` is the game's "not heated"
     sentinel** — which sharpens the open question in
     [`../03-heat-destruction/HeatManager.md`](../03-heat-destruction/HeatManager.md):
     `DissipateHeat` writing `+∞` looks *correct*, and the
     `IsNegativeInfinity` tests look like the anomaly. Still [OPEN]
     pending a live test, but the balance of evidence has shifted.
- **Status:** [CONFIRMED]

| Other members | IL | Status |
|---|---|---|
| `static PartSave[] CreateSaves(Part[] parts)` | @239282 | [CONFIRMED] signature |
| `.ctor(string, Vector2, Orientation, Dictionary×3)` | @239420 | [CONFIRMED] signature |
| `void OnSerialization(StreamingContext)` | @239465 | [PARTIAL] |

---

## RocketSave

**Namespace:** SFS.World
**Kind:** class (`[Serializable]`)
**Status:** [CONFIRMED] schema
**Depth:** FULL
**IL:** `scratch/full_il.txt` @192061 · 2 methods / 12 fields

A **flying instance** — a blueprint plus location, control state, and
frozen connectivity.

```csharp
public string rocketName;
public WorldSave.LocationData location;
public float  rotation, angularVelocity;
public bool   throttleOn;
public float  throttlePercent;
public bool   RCS;
public PartSave[]  parts;
public JointSave[] joints;          // <- Blueprint has no equivalent
public StageSave[] stages;
public bool   staging_EditMode;
public int    branch;
RocketSave(Rocket rocket)                             // @192103
```

**Gotcha:** `RocketSave` carries `joints`; `Blueprint` does **not**. A
blueprint is a *design*; a rocket save is a *flying instance* with its
connectivity frozen.

**Status:** [CONFIRMED] schema · **[OPEN]** the `RocketSave(Rocket)`
constructor body — so it may have side effects or assume editor/flight
context.

---

## StageSave

**Namespace:** SFS.World
**Kind:** class
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @192195 · 2 methods / 2 fields

```csharp
public int   stageId;
public int[] partIndexes;                                          // INDICES
static StageSave[] CreateSaves(Staging staging, List<Part> parts)  // @192202
```

---

## JointSave

**Namespace:** SFS.World
**Kind:** class
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @192316 · 2 methods / 2 fields

```csharp
public int partIndex_A, partIndex_B;                               // INDICES
static JointSave[] CreateSave(Rocket rocket)                       // @192333
```

> ### Cross-record invariant [CONFIRMED]
>
> **Both `StageSave.partIndexes` and `JointSave.partIndex_A/B` reference
> parts by index into the `parts` array** — not by id or name. **Any tool
> that reorders or filters `parts` must renumber both.** This is the
> single easiest way to silently corrupt a generated design.

---

## WorldSave

**Namespace:** SFS.World
**Kind:** class
**Status:** [CONFIRMED] schema
**Depth:** FULL
**IL:** `scratch/full_il.txt` @196925 · 7 methods / 8 fields

```csharp
public string version;
public CareerState career;
public WorldState state;
public Astronauts astronauts;
public RocketSave[] rockets;
public Dictionary<int, SFS.Stats.Branch> branches;
public HashSet<SFS.Logs.LogId> completeLogs;
public HashSet<string> completeChallenges;
```

### On-disk layout

**[CONFIRMED]** from `WorldSave.Save` @196938 — one folder per world
under `WorldsFolder`, **each value a separate JSON `.txt`**:

```
Version.txt   WorldState.txt   Rockets.txt   Branches.txt
Achievements.txt   Challenges.txt   Career.txt   Astronauts.txt
```

`Rockets.txt` and `Branches.txt` are written **only when
`saveRocketsAndBranches` is true**.

| Loader | IL | Status |
|---|---|---|
| `static bool TryLoad(IFolder, bool, I_MsgLogger, out WorldSave)` | @197028 | [CONFIRMED] signature |
| `Load_WorldState` | @197251 | [PARTIAL] |
| `Save_CareerState` | @197193 | [PARTIAL] |
| `Save_AstronautStates` | @197222 | [PARTIAL] |
| `static WorldSave CreateEmptyQuicksave(string version)` | @197276 | [PARTIAL] |

> **`completeChallenges` is a `HashSet<string>` of challenge ids** —
> which connects to the `achievements` probe command (v0.24) and
> `SFS.Logs.Challenge.id`. **Challenge completion is world save state,
> not Steam state**, consistent with what was already found. See
> [`../13-challenges-logging/Challenge.md`](../13-challenges-logging/Challenge.md).

---

## WorldSave/LocationData

**Namespace:** SFS.World
**Kind:** class (**nested** under `WorldSave`)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @197802 · 3 methods / 3 fields

```csharp
public string  address;          // the planet CODE NAME, a string
public Double2 position, velocity;
Location GetSaveLocation(double time)                 // @197847
```

**Gotcha:** `address` is the planet **code name string**, not an object
reference — which is why a save is **portable across sessions**.

## Gotchas, all records

- `StageSave.partIndexes` and `JointSave.partIndex_A/B` are **indices**
  into `parts`; renumber on any reorder.
- `PartSave.name` must match a key in `PartsLoader.parts`.
- `TryLoadJson<T>` / `FromJson<T>` are generic; `SaveAsJson` / `ToJson`
  are not.
- `LocationData.address` is the planet code name, not an object.
- `PartSave.temperature` defaults to `+∞`, not 0.

## Status summary

| Item | Status |
|---|---|
| `Blueprint` six-field schema | [CONFIRMED] |
| Blueprint on-disk layout (`Version.txt` + `Blueprint.txt`) | [CONFIRMED] |
| `PartSave` schema; three `*_VARIABLES` dictionaries hold all config | [CONFIRMED] |
| `PartSave.temperature` initialises to `+∞` | [CONFIRMED] — evidence for the heat sentinel question |
| `RocketSave` / `StageSave` / `JointSave` / `LocationData` schemas | [CONFIRMED] |
| Part references are **indices**, not ids | [CONFIRMED] |
| `WorldSave` schema and eight-file on-disk layout | [CONFIRMED] |
| `RocketSave(Rocket)` constructor body | [OPEN] |
| `Blueprint.Save` / `TryLoad` bodies | [PARTIAL] |
| `WorldSave` loader/saver bodies | [PARTIAL] |
| `Orientation`, `BurnMark.BurnSave`, `CareerState`, `WorldState`, `Astronauts`, `Branch`, `LogId` own entries | [OPEN] — Step 2 |
