# Resources and fuel flow — `ResourceType`, `ResourceModule`, `FlowModule`, `FuelPipeModule`, `Resources`

**Group file.** Five types cooperate: `ResourceType` (the substance),
`ResourceModule` (a tank or a *group* of tanks), `FlowModule` + its
nested `Flow` (a consumer's straw into those tanks), `FuelPipeModule`
(cross-feed), and `SFS.World.Resources` (the per-craft coordinator).

[`../04-engines/EngineModule.md`](../04-engines/EngineModule.md) covers
how an engine computes its mass flow; this file covers **where the
propellant actually comes from**.

**Migrated** from `docs/sfs_source_reference.md` §E1 (2026-08-28).

---

## ResourceType

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.ScriptableObject
**Implements:** —
**Status:** [CONFIRMED] layout · **values are live-only data**
**Depth:** FULL
**IL:** `scratch/full_il.txt` @246649 · 1 method / 5 fields

A pure data holder — no methods but the constructor.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `displayName` | `TranslationVariable` | public | no | | [CONFIRMED] |
| `resourceUnit` | `TranslationVariable` | public | no | | [CONFIRMED] |
| `resourceMass` | `double` | public | no | mass per unit of resource | [CONFIRMED] shape · **[OPEN] value** |
| `transferRate` | `double` | public | no | units/second for fuel transfer | [CONFIRMED] shape · **[OPEN] value** |
| `density` | `float` | public | no | | [CONFIRMED] shape · **[OPEN] value** |

> **All five values are serialized Unity data, not IL literals**, so per
> the data-trust rule they **must be read live**. Nothing in this
> reference can tell you what `resourceMass` is for liquid fuel.

> **Identity is by reference.** `Resources.SetupResourceGroups` keys a
> `Dictionary<ResourceType, …>` on the object itself, so **two
> `ResourceType` assets with identical fields are still distinct
> resources.**

---

## ResourceModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `I_InitializePartModule`, `ResourceDrawer.I_Resource` (**explicitly**)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @245548 · 25 methods / 13 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `resourceType` | `ResourceType` | public | no | | [CONFIRMED] |
| `wetMass` | `Double_Reference` | public | no | full-tank mass | [CONFIRMED] |
| `dryMassPercent` | `Double_Reference` | public | no | fraction of `wetMass` that is structure | [CONFIRMED] |
| `resourcePercent` | `Double_Reference` | public | no | **fill fraction, 0–1 — this is the fuel gauge, and the only state** | [CONFIRMED] |
| `mass` | `Double_Reference` | public | no | output, written by `RecalculateMass` | [CONFIRMED] |
| `setMass`, `setDensity` | `bool` | public | no | whether this module drives the part's mass/density | [CONFIRMED] |
| `parent` | `ResourceModule` | public | no | | [CONFIRMED] |
| `children` | `List<ResourceModule>` | public | no | | [CONFIRMED] |
| `flowModules` | `List<FlowModule.Flow>` | public | no | consumers attached to this module | [CONFIRMED] |
| `part` | `Part` | **private** | no | | [CONFIRMED] |
| `showDescription` | `bool` | public | no | | [CONFIRMED] |

> `ResourceDrawer.I_Resource` is implemented **explicitly**, so
> `ResourceType`, `WetMass` and `ResourcePercent` **do not reflect off
> the class by those names** — same trap as `Rocket`'s `I_Physics`
> members. `ResourceModule` also implements `I_InitializePartModule`
> with an explicit `Priority`, feeding `Part.InitializePart`'s sorted
> invocation.

### The quantity model

Bodies read @245671–245763.

```csharp
double DryMassMultiplier {
    get {
        if (!Application.isPlaying || !Base.worldBase.insideWorld.Value) return 1.0;
        return Base.worldBase.settings.difficulty.DryMassMultiplier;
    }
}
double DryMassPercent        => dryMassPercent.Value * DryMassMultiplier;
double TotalResourceCapacity => (1.0 - DryMassPercent) * wetMass.Value;
double ResourceAmount        => TotalResourceCapacity * resourcePercent.Value;
double ResourceSpace         => TotalResourceCapacity * (1.0 - resourcePercent.Value);
```

> **Fuel is stored as a fraction, never as an absolute quantity.**
> `resourcePercent` is the only state; everything else is derived. An
> agent reading "how much fuel is left" **must multiply by
> `TotalResourceCapacity`**, and that capacity is **difficulty-scaled** —
> `dryMassMultipliers = [1.0, 1.0, 0.25]` means a Realistic tank holds
> *more* propellant for the same `wetMass`, because less of it is
> structure.
>
> The multiplier is **bypassed (forced to 1.0) outside play mode and
> outside a loaded world**, which is exactly the condition under which
> static asset parsing runs — another instance of the pattern where
> offline reads are systematically wrong.

#### RecalculateMass() -> void

- **Access:** instance · IL @245831, body read
- **Behavior:**
  ```csharp
  mass.Value = DryMassPercent * wetMass.Value
             + ResourceAmount * resourceType.resourceMass;
  if (setDensity)
      part.density.Value = Mathf.Lerp((float)DryMassPercent, 1f,
                                      (float)resourcePercent.Value)
                         * resourceType.density;
  ```
- **Side effects:** writes into the variable system via
  `Double_Reference`, which propagates to `Part.mass` (a
  `Composed_Float`) and from there to `Mass_Calculator`.
- **Status:** [CONFIRMED]

> ### The burn → mass-loss chain, confirmed end to end
>
> `Flow.FlowNegative` → `TakeResource` → `resourcePercent` write →
> `RecalculateMass` → `mass` variable → `Part.mass` recompute →
> `Composed.onChange` → `MarkDirty` → `rb2d.mass`.

#### TakeResource(double takeAmount) -> void

- **Access:** public instance · IL @245921, body read
- **Behavior:**
  ```csharp
  if (resourcePercent.Value == 0.0) return;              // exact compare
  takeAmount = Math.Min(takeAmount, ResourceAmount);
  TakeFromParent(takeAmount);
  TakeFromChildren(1.0 - takeAmount / ResourceAmount);   // NB: re-reads ResourceAmount
  resourcePercent.Value -= takeAmount / TotalResourceCapacity;
  ```
- **Gotchas:** `TakeFromChildren` takes a **leftover fraction** and
  scales each child's `resourcePercent` by it, so **a group drains
  proportionally rather than sequentially.**

  The empty test is an **exact `== 0.0` comparison** on a double that is
  repeatedly decremented — reaching exactly zero is not guaranteed, which
  is a plausible source of a tank that reads as non-empty at ~1e-17.
  **Not observed — [OPEN].**
- **Status:** [CONFIRMED]

`AddResource` @246040 mirrors this with `AddToParent` / `AddToChildren`.

#### CreateGroup(List&lt;ResourceModule&gt;, GameObject) -> ResourceModule

- **Access:** **public static** · IL @246190
- **Behavior:** builds a **synthetic parent `ResourceModule` on a new
  `GameObject`** whose `children` are the real tanks. **Group objects are
  therefore `ResourceModule`s that own no part.**
- **Status:** [CONFIRMED] role · [PARTIAL] body

#### ToggleTransfer() -> void

- **Access:** public instance · IL @246172 — the entry for the
  fuel-transfer UI. [PARTIAL]

---

## FlowModule and FlowModule/Flow

**Namespace:** SFS.Parts.Modules
**Kind:** class (`Flow` is nested)
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @243461 (`FlowModule`) / @243876 (`Flow`)

### FlowModule fields

`Flow[] sources`, a private `massFlow`, and an `onStateChange` event.

#### SetMassFlow(double newMassFlow) -> void

- **Access:** public instance
- **Behavior:**
  ```csharp
  if (newMassFlow == massFlow) return;               // exact compare
  massFlow = newMassFlow;
  double perUnit = GetMassFlowPerUnit();
  double unitRate = perUnit > 0.0 ? newMassFlow / perUnit : 1.0;
  foreach (Flow f in sources)
      f.flowRate.Value = unitRate * f.flowPercent;
  UpdateEnabled();
  ```
- **Gotchas:** **this is the seam between engines and resources.** An
  engine computes a mass flow and calls `SetMassFlow`; the module splits
  it across its `Flow` entries by `flowPercent`, normalised by
  `GetMassFlowPerUnit()`. **A bicharge engine (fuel + oxidiser) is two
  `Flow`s** with different `resourceType`s and different `flowPercent`s.
- **Status:** [CONFIRMED]

#### FixedUpdate() -> void

`foreach (Flow f in sources) f.OnFixedUpdate();` — [CONFIRMED]

### Flow (nested)

Fields: `resourceType`, `flowPercent`, `sourceSearchMode` (`SourceMode`),
`surface` (`SurfaceData`), `flowType` (`FlowType`), `flowRate`
(`Double_Reference`), `state` (`State_Local`), `sources`
(`ResourceModule[]`).

**Two enums, values confirmed from the `literal` fields:**

```
SourceMode : Global = 0, Surfaces = 1, Local = 2
FlowType   : Negative = 0, Positive = 1
```

`SourceMode` selects `GetGlobally` / `GetBySurfaces` / `GetLocally` —
draw from anywhere on the craft, only from tanks touching a named
surface, or only from this part. **Bodies [PARTIAL].**

#### OnFixedUpdate() -> void

```csharp
if (flowType == FlowType.Negative) { FlowNegative(); return; }   // consume
if (flowType == FlowType.Positive) FlowPositive();               // fill
```

#### FlowNegative() — and the infinite-fuel cheat

```csharp
if (SandboxSettings.main.settings.infiniteFuel) return;     // consumes nothing
double available = GetSourcesResourceAmount();
...
```

> **Infinite fuel is implemented by skipping consumption entirely** —
> per flow, per tick — **not by refilling tanks.** So with the cheat on,
> `resourcePercent` never moves and **craft mass never drops**, which
> changes the *trajectory*, not just the endurance. **Anything the agent
> learns under infinite fuel is learned on a different vehicle.** This is
> the setting the probe's `cheat` command touches.

**Status:** [CONFIRMED] for the cheat branch · [PARTIAL] for the rest of
the body.

#### FlowPositive()

```csharp
double space = GetSourcesResourceSpace();
double frac  = Math.Min(flowRate.Value * Time.fixedDeltaTime / space, 1.0);
foreach (ResourceModule m in sources)
    m.AddResource(m.ResourceSpace * frac);
```

**Gotcha:** it divides by `space` with **no zero guard** — a full set of
sources gives `Infinity`, clamped to 1.0 by the `Math.Min`, so **the
degenerate case happens to be safe.** [CONFIRMED]

#### CanFlow / CanFlow_ElseShowMsg

`FlowModule.CanFlow(I_MsgLogger)` and
`Flow.CanFlow_ElseShowMsg(I_MsgLogger)` are the pre-flight checks that
produce "no fuel"-style messages — **useful to an agent as a *reason*
rather than a bare failure.** See
[`../13-challenges-logging/I_MsgLogger.md`](../13-challenges-logging/I_MsgLogger.md).
**Bodies not read — [PARTIAL].**

---

## FuelPipeModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Status:** [PARTIAL]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @244786 · 7 methods / 5 fields

Fields: `surface_In` / `surface_Out` (`SurfaceData`), `previousPipes`,
`resource_In`, `resource_Out`.

| Method | Access | Status |
|---|---|---|
| `FindNeighbours(JointGroup group)` | public | [CONFIRMED] signature |
| `FindFlow()` → `(ResourceModule[], ResourceModule)?` | public | [CONFIRMED] signature |
| `FindFlowsForEngine(FlowModule.FlowType flowType)` → `List<ResourceModule>` | public | [CONFIRMED] signature |
| `FindFromTanks()` | private | [CONFIRMED] signature |
| `FixedUpdate_FuelPipeFlow(List<(ResourceModule[], ResourceModule)> flows)` | **public static** | [CONFIRMED] signature |

**Gotcha:** the static `FixedUpdate_FuelPipeFlow` is the one
`Rocket.FixedUpdate` calls with `Rocket.pipeFlows` — **pipes are driven
from the craft, not from the module's own `FixedUpdate`.**

**Bodies not read — [PARTIAL].** Cross-feed topology is therefore
documented as **structure only**.

---

## SFS.World.Resources — per-craft coordination

**Namespace:** SFS.World
**Kind:** class
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @182791 · 6 methods / 6 fields

Fields: `groupsHolder` (`GameObject`), `localGroups`, `globalGroups`
(both `ResourceModule[]`), `boosters` (`BoosterModule[]`), `transfers`
(`List<Resources.Transfer>`), `onGroupsSetup` (`Action`).

#### SetupResourceGroups(Rocket rocket) -> void

- **Access:** public instance · IL @182802, body read
- **Behavior:**
  ```csharp
  Destroy(globalGroups); Destroy(localGroups);            // old group GameObjects
  foreach (List<ResourceModule> connected in rocket.jointsGroup.GetResourceGroups()) {
      ResourceModule group = ResourceModule.CreateGroup(connected, groupsHolder);
      localGroups.Add(group);
      byType[group.resourceType] ??= new List<ResourceModule>();
      byType[group.resourceType].Add(group);
  }
  boosters     = rocket.partHolder.GetModules<BoosterModule>();
  globalGroups = byType.Values.Select(b__6_0).ToArray();   // one per resource type
  onGroupsSetup?.Invoke();
  ```
- **Gotchas:** **fuel topology is derived from joint connectivity**, via
  `JointGroup.GetResourceGroups()` — **not from part positions and not
  from anything in the save file.** `localGroups` is one group per
  connected cluster per resource type; `globalGroups` is one group per
  resource type across the whole craft. That is what `SourceMode.Global`
  vs `SourceMode.Local` select between.

  This runs on **every structure change**, and it **destroys and rebuilds
  the group `GameObject`s.** **Any reference an agent caches to a
  `ResourceModule` group is invalidated by staging or docking** — cache
  the `Resources` component and re-read, or subscribe to
  `onGroupsSetup`.
- **Status:** [CONFIRMED]

#### FixedUpdate() -> void

- **Access:** instance · IL @182938
- **Behavior:** services `transfers`: each `Transfer` moves at
  `resourceType.transferRate * WorldTime.FixedDeltaTime`, clamped by both
  the source's `ResourceAmount` and the destination's capacity, with a
  `1.000001` epsilon in the completion test.
- **Status:** [PARTIAL] — clamping confirmed, exact completion condition
  not transcribed

`ToggleTransfer(Part, ResourceModule)` @183033 and
`RemoveInvalidTransfers(PartHolder)` @183097 are the public mutators —
[PARTIAL].

---

## What an agent should read

| Question | Read |
|---|---|
| fuel fraction in one tank | `resourceModule.resourcePercent.Value` |
| fuel **quantity** in one tank | `resourceModule.ResourceAmount` (property — **do not derive it yourself**) |
| total per resource type on the craft | iterate `rocket.resources.globalGroups`, match `resourceType`, sum `ResourceAmount` |
| whether the craft is dry | `ResourceAmount == 0.0` on the relevant **global group** — *not* `resourcePercent`, which is per-tank |
| whether infinite fuel is on | `SandboxSettings.main.settings.infiniteFuel` |
| react to staging changing the fuel graph | subscribe `rocket.resources.onGroupsSetup` |

## Status summary

| Item | Status |
|---|---|
| `ResourceType` field layout | [CONFIRMED] — values are live-only data |
| `ResourceModule` field layout | [CONFIRMED] |
| Capacity/amount/space formulas | [CONFIRMED] |
| Fuel stored as a fraction, not a quantity | [CONFIRMED] |
| `DryMassMultiplier` difficulty-scaled, bypassed offline | [CONFIRMED] |
| `RecalculateMass` body; burn → `rb2d.mass` chain end to end | [CONFIRMED] |
| `TakeResource` / proportional child draining | [CONFIRMED] |
| `CreateGroup` is public static | [CONFIRMED] |
| `SetMassFlow` splits by `flowPercent` | [CONFIRMED] |
| `SourceMode` and `FlowType` enum values | [CONFIRMED] |
| Infinite fuel skips consumption, does not refill | [CONFIRMED] |
| `FlowPositive` body | [CONFIRMED] |
| Fuel topology derives from `JointGroup.GetResourceGroups()` | [CONFIRMED] |
| Group `GameObject`s destroyed/rebuilt on every structure change | [CONFIRMED] |
| Exact `== 0.0` empty test may leave residue | [OPEN] — mechanism only |
| `FuelPipeModule` bodies | [PARTIAL] — signatures only |
| `CanFlow` / `CanFlow_ElseShowMsg` bodies | [PARTIAL] |
| `Resources.FixedUpdate` transfer completion condition | [PARTIAL] |
| `Flow.GetGlobally` / `GetBySurfaces` / `GetLocally` bodies | [PARTIAL] |
| `Resources/Transfer`, `State_Local`, `ResourceDrawer` own entries | [OPEN] — Step 2 |
