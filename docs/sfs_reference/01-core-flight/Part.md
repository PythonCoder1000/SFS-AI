# `SFS.Parts.Part` — the part object

**Migrated** from `docs/sfs_source_reference.md` §B3 (2026-08-28).

Heat contract:
[`../03-heat-destruction/HeatModuleBase.md`](../03-heat-destruction/HeatModuleBase.md).
Parametric fields:
[`../08-parametric-expressions/Compute.md`](../08-parametric-expressions/Compute.md).
Container: [`PartHolder.md`](PartHolder.md).

---

## Part

**Namespace:** SFS.Parts
**Kind:** class
**Extends:** **SFS.World.Drag.HeatModuleBase**
**Implements:** `SFS.World.Rocket/INJ_Rocket`
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @236080 · 30 methods / 20 fields

```
.class public auto ansi beforefieldinit Part          @236080
    extends SFS.World.Drag.HeatModuleBase
    implements SFS.World.Rocket/INJ_Rocket
```

**`Part : HeatModuleBase`** is why the heat chain can treat a bare `Part`
and a `HeatModule` interchangeably — they share the base. And `Part`
implements the injection interface `Rocket/INJ_Rocket`, which is how
`part.Rocket` gets set.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `displayName`, `pickCategoryName`, `description` | `TranslationVariable` | public | no | localised | [CONFIRMED] |
| `mass` | `Composed_Float` | public | no | **parametric** — an expression, not a number | [CONFIRMED] |
| `centerOfMass` | `Composed_Vector2` | public | no | parametric, part-local | [CONFIRMED] |
| `density` | `Float_Local` | public | no | | [CONFIRMED] |
| `orientation` | `OrientationModule` | public | no | | [CONFIRMED] |
| `variablesModule` | `VariablesModule` | public | no | **the binding `mass`'s expression resolves against** | [CONFIRMED] |
| `variants` | `Variants[]` | public | no | | [CONFIRMED] |
| `onPartUsed` | `UsePartUnityEvent` | public | no | | [CONFIRMED] |
| `burnMark` | `BurnMark` | public | no | `[NonSerialized]` | [CONFIRMED] |
| `frameIndex_WaterDamage` | `int` | public | no | `[NonSerialized]` | [CONFIRMED] |
| `temperature` | `float` | public | no | **a public field**, °C | [CONFIRMED] |
| `aboutToDestroy`, `onPartDestroyed` | `Action<Part>` | public | no | | [CONFIRMED] |
| `modules` | `Dictionary<string, object>` | **private** | no | **a query memo, not a registry** — see below | [CONFIRMED] |
| `moduleCount` | `Dictionary<string, int>` | **private** | no | same shape | [CONFIRMED] |
| `<Rocket>k__BackingField` | `Rocket` | private | no | | [CONFIRMED] |
| `<LastAppliedIndex>k__BackingField` | `int` | private | no | | [CONFIRMED] |
| `<ExposedSurface>k__BackingField` | `float` | private | no | drag/heat coupling | [CONFIRMED] |

**`mass` and `centerOfMass` are `Composed_*`, i.e. expression-backed.**
Reading `.Value` evaluates against `variablesModule`. This is why a
part's mass **cannot be read from the asset file** — a scaled tank's mass
literally *is* the string `"size * …"` until evaluated.

### Methods

#### GetModules&lt;T&gt;() -> T[] — a memo, not a registry

- **Access:** public instance, **generic** · IL @236536, body read
- **Behavior:**
  ```csharp
  public T[] GetModules<T>() {
      string key = typeof(T).Name;                       // SHORT name
      if (!modules.ContainsKey(key))
          modules.Add(key, GetComponentsInChildren<T>(true));   // includeInactive
      return (T[])modules[key];
  }

  public int GetModuleCount<T>() { /* same shape, moduleCount, .Length */ }
  public bool HasModule<T>()  => GetModuleCount<T>() > 0;
  ```
- **Side effects:** populates `modules` / `moduleCount` on first call for
  a given `T`.
- **Gotchas:** four, all load-bearing. **This resolves the "walking
  `Part.modules` is unreliable" problem.**
  1. **`modules` is a lazy cache of queries already made**, not an
     inventory. A part nobody has asked about `EngineModule` has no
     `"EngineModule"` key. **Enumerating the dictionary tells you what
     has been queried, not what the part has.** Any probe that walks
     `modules` to list a part's modules **under-reports,
     non-deterministically**, depending on what the game happened to ask
     for first.
  2. **The correct route is to *call* the method.** Via reflection:
     ```csharp
     MethodInfo gm = typeof(Part).GetMethod("GetModules")
                                 .MakeGenericMethod(moduleType);
     Array mods = (Array)gm.Invoke(part, null);
     ```
     Or skip `Part` entirely and call
     `part.GetComponentsInChildren(moduleType, true)` — the Unity
     non-generic overload, which is what the cache wraps anyway and needs
     no `MakeGenericMethod`.
  3. **The key is `typeof(T).Name`, the short name.** Two types sharing a
     short name across namespaces collide in one cache slot, and the
     second caller gets a `castclass` on the wrong array type →
     `InvalidCastException`. **A mod that defines its own `EngineModule`
     in its own namespace can break the base game's lookup on any part it
     touches.** Not observed; the mechanism is confirmed from the
     opcodes.
  4. **The cache is never invalidated.** `Part::modules` is written only
     in the constructor (@237369) and read only in these two methods —
     `grep` on `Part::modules` returns exactly those sites, no `Clear`.
     Harmless in practice, because a part's component set is fixed after
     `InitializePart`, but **a module added at runtime is invisible to
     every later `GetModules<T>()` on that part.**

  Note [`PartHolder`](PartHolder.md) uses the same cache shape but
  **does** invalidate correctly.
- **Status:** [CONFIRMED]

#### InitializePart() -> void

- **Access:** public instance, **zero arguments** · IL @236871
- **Behavior:** collects `I_InitializePartModule` via
  `GetComponentsInChildren(true)`, **sorts** them with a comparison
  lambda, then invokes each — so module initialisation has a **defined
  order**, set by whatever `b__31_0` compares (not read; likely a
  priority field).
- **Gotchas:** it takes **zero arguments**. An earlier
  `sfs_physics_reference.md` claim of `InitializePart(bool)` is wrong —
  see [`../CORRECTIONS.md`](../CORRECTIONS.md).
- **Status:** [PARTIAL] — the sort comparison is unread

### Heat members — and what `Part` actually contributes

**[CONFIRMED].** All `virtual`, i.e. overridable by `HeatModule`:

```csharp
virtual string Name             => (string)GetDisplayName();
virtual bool   IsHeatShield     => false;
virtual float  Temperature      { get => temperature;            set => temperature = value; }
virtual int    LastAppliedIndex { get; set; }                    // plain auto-property
virtual float  ExposedSurface   { get; set; }                    // plain auto-property
virtual float  HeatTolerance    => AeroModule.GetHeatTolerance(HeatTolerance.Low);
```

**`Part.HeatTolerance` is hardcoded to `Low`** — `ldc.i4.0` straight into
`GetHeatTolerance`. It reads no part config at all. With `Low => 400f`
and the `× 1.03` destruction threshold, this is the direct confirmation
that **a plain part breaks at 412.0 °C**, and that the figure is **not
configurable per part on `Part` itself**; a heat-shield-style tolerance
must come from a `HeatModule` override.

> **Refinement to the probe finding.** `Part.get_Temperature` returns
> exactly the `temperature` field, so **on a `Part` the property and the
> field agree** and the probe's field read is correct there. The mismatch
> only arises when the object in hand is a *different* `HeatModuleBase`
> subclass whose override reads a `Float_Reference`. So the fix is not
> "the property beats the field on `Part`" — it is **hold the
> `HeatModuleBase` reference (e.g. `Surface.owner`) and read
> `Temperature` virtually**, which dispatches to whichever subclass is
> actually there. Reading `Part.temperature` off a part whose heat is
> owned by a module is what under-reports.

#### OnOverheat(bool breakup) / OnOverheat(HeatModuleBase module, bool breakup)

- **Access:** public instance · @237163 / @237177
- **Behavior:** the one-argument form is a **one-line forward** to
  `OnOverheat(this, breakup)`. The two-argument form is the real
  destruction path — destroy `joints[0]` and cool 20% rather than
  exploding; full body in
  [`../03-heat-destruction/HeatManager.md`](../03-heat-destruction/HeatManager.md).
- **Gotchas:** both exist, same name, different arity —
  **`GetMethod("OnOverheat")` is ambiguous.**
- **Status:** [CONFIRMED]

#### DestroyPart(bool createExplosion, bool updateJoints, DestructionReason reason) -> void

- **Access:** public instance · IL @237290, body read
- **Behavior:**
  ```csharp
  if (createExplosion)
      EffectManager.CreateExplosion(
          transform.TransformPoint(centerOfMass.Value),
          mass.Value * 2f + 0.5f);                 // explosion size from mass
  Action<Part> cb = onPartDestroyed;
  onPartDestroyed = null;                          // cleared BEFORE invoke
  cb?.Invoke(this);
  if (updateJoints)
      JointGroup.OnPartDestroyed(this, Rocket, reason);
  Object.Destroy(gameObject);
  ```
- **Gotchas:** explosion size is `mass * 2 + 0.5`. `onPartDestroyed` is
  **nulled before being invoked**, so a handler that re-subscribes during
  the callback is *not* cleared — and re-entrancy cannot loop. Note
  **`aboutToDestroy` is not invoked here**; it must fire from a caller
  upstream — [OPEN], its call sites are unread. `Object.Destroy` is
  **deferred to end of frame**, so the part is still alive and readable
  for the remainder of the current tick.
- **Status:** [CONFIRMED]

#### GetOwnershipState() -> OwnershipState — the DLC/career gate

- **Access:** public instance · IL @236807, body read
- **Returns:** `SFS.Parts.Modules.OwnershipState` —
  `NotOwned = 0`, `NotUnlocked = 1`, `OwnedAndUnlocked = 2`
- **Behavior:**
  ```csharp
  if (!GetModules<OwnModule>().All(m => m.IsOwned || !m.IsPremium))
      return OwnershipState.NotOwned;
  if (!CareerState.main.HasPart(this))
      return OwnershipState.NotUnlocked;
  return OwnershipState.OwnedAndUnlocked;
  ```
- **Gotchas:** the predicate is `IsOwned || !IsPremium` — **a non-premium
  part passes regardless of ownership.** This is the gate behind the
  `OnPartNotOwned` parameter on `PartsLoader.CreateParts` and behind
  `BuildState.SpawnBlueprint`'s filtering, and it is the **most likely
  content of the unread `Rocket.CanUsePart` check**. **An agent
  generating blueprints should call this per part before spawning**,
  rather than discovering the rejection downstream.

  **`CareerState.main` is dereferenced without a null check** — calling
  this outside a loaded career context is an **NRE**, not a
  `NotUnlocked`.
- **Status:** [CONFIRMED]

### Other confirmed members

| Member | Signature | Note | Status |
|---|---|---|---|
| `Rocket` | `Rocket { get; set; }` | `set_Rocket` is the `INJ_Rocket` impl — `final virtual`, but **public**, so unlike `Rocket`'s own `I_Physics` members it reflects normally | [CONFIRMED] |
| `Position` | `Vector2 { get; set; }` | wraps `transform.position` | [CONFIRMED] |
| `GetClickPolygons()` | `List<PolygonData>` | feeds `Rocket.UseParts` | [PARTIAL] |
| `GetBuildColliderPolygons(bool forAttach = …)` | `(ConvexPolygon[], bool)` | build-time geometry | [PARTIAL] |
| `GetAttachmentSurfacesWorld()` | `Line2[]` | **world-space attach lines** — the geometry an auto-assembler needs | [PARTIAL] |
| `IsFront()` | `bool` | | [PARTIAL] |
| `RegenerateMesh()` | `void` | call after changing variables to refresh visuals | [PARTIAL] |
| `SetSortingLayer(string)` | `void` | forwards to every `BaseMesh` | [PARTIAL] |
| `DrawPartStats(Part[], StatsMenu, PartDrawSettings)` | `void` | UI | [PARTIAL] |

## Status summary

| Item | Status |
|---|---|
| `Part : HeatModuleBase, INJ_Rocket` | [CONFIRMED] |
| Full field layout | [CONFIRMED] |
| `mass` / `centerOfMass` are `Composed_*` (parametric) | [CONFIRMED] |
| `GetModules<T>` is a lazy memo keyed by short type name | [CONFIRMED] |
| Walking `modules` under-reports | [CONFIRMED] |
| Short-name key collision → `InvalidCastException` | [CONFIRMED] mechanism · [OPEN] never observed |
| `Part.modules` never cleared | [CONFIRMED] — grep-exhaustive |
| `InitializePart()` takes **zero** arguments | [CONFIRMED] — corrects an earlier claim |
| `Part.HeatTolerance` hardcoded `Low` → 412 °C break | [CONFIRMED] |
| `Part.Temperature` == `temperature` field | [CONFIRMED] |
| `OnOverheat` is an ambiguous 2-overload name | [CONFIRMED] |
| `DestroyPart` body, explosion size `mass*2+0.5` | [CONFIRMED] |
| `GetOwnershipState` body + enum values | [CONFIRMED] |
| `CareerState.main` unguarded | [CONFIRMED] |
| `InitializePart` ordering comparison | [PARTIAL] — lambda unread |
| `aboutToDestroy` call sites | [OPEN] |
| Geometry method bodies | [PARTIAL] — signatures only |
| `OwnModule`, `Variants`, `OrientationModule`, `PolygonData` own entries | [OPEN] — Step 2 |
