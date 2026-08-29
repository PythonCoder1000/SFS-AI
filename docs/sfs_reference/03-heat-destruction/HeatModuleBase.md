# `SFS.World.Drag.HeatModuleBase` and `HeatModule` — heat ownership

**Group file.** The abstract heat contract and its two implementations.
`SFS.Parts.Part` is the other implementation and is documented in
[`../01-core-flight/Part.md`](../01-core-flight/Part.md); only its heat
members are described here.

**Migrated** from `docs/sfs_source_reference.md` §D1.0 (2026-08-28).
Signatures re-read from IL during migration.

Accumulation and destruction: [`HeatManager.md`](HeatManager.md).
The temperature the atmosphere supplies:
[`../02-drag-aero/AeroFormula.md`](../02-drag-aero/AeroFormula.md).

## Type layout — `Part` IS a `HeatModuleBase`

**[CONFIRMED]** — `Part` @236080, `HeatModuleBase` @218451,
`HeatModule` @273416.

```
abstract SFS.World.Drag.HeatModuleBase                     @218451
  ├── SFS.Parts.Part                : HeatModuleBase       @236080
  └── SFS.Parts.Modules.HeatModule  : HeatModuleBase       @273416
```

`SFS.Parts.Part` **extends `SFS.World.Drag.HeatModuleBase`** and
implements `SFS.World.Rocket/INJ_Rocket`. This is not incidental — it
means **a part with no dedicated heat module acts as its own heat
owner.**

---

## HeatModuleBase

**Namespace:** SFS.World.Drag
**Kind:** abstract class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @218451 · 13 methods / 1 field

One field, nine abstract members. **All the state is virtual**, so the
backing storage differs per subclass — which is the trap below.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `valid` | `SFS.World.Drag.Valid` | public | no | the only real field — the shared invalidation token also carried by `Surface` | [CONFIRMED] |

### Methods

| Signature | IL | Status |
|---|---|---|
| `private void OnEnable()` | @218457 | [PARTIAL] — Unity message, body not read |
| `private void OnDisable()` | @218471 | [PARTIAL] |
| `public abstract string Name { get; }` | @218485 | [CONFIRMED] |
| `public abstract bool IsHeatShield { get; }` | @218492 | [CONFIRMED] |
| `public abstract float Temperature { get; set; }` | @218499 / @218506 | [CONFIRMED] |
| `public abstract int LastAppliedIndex { get; set; }` | @218513 / @218520 | [CONFIRMED] |
| `public abstract float ExposedSurface { get; set; }` | @218527 / @218534 | [CONFIRMED] |
| `public abstract float HeatTolerance { get; }` | @218541 | [CONFIRMED] |
| `public abstract void OnOverheat(bool breakup)` | @218548 | [CONFIRMED] |

### Storage differs between the two implementations — and it matters

| Member | `Part` | `HeatModule` |
|---|---|---|
| `Temperature` | plain `public float temperature` field | `Float_Reference temperature` (**wrapped**) |
| `IsHeatShield` | hardcoded **`false`** @237057 | `public bool isHeatShield` field |
| `HeatTolerance` | hardcoded **`GetHeatTolerance(Low)` = 400** @237151 | `GetHeatTolerance(this.heatTolerance)` @273583 |
| `OnOverheat` | `this.OnOverheat(this, breakup)` @237163 | `part.OnOverheat(this, breakup)` @273596 |

**So an ordinary part is always tolerance 400 and never a heat shield.**
Only a part carrying a `HeatModule` can have `Mid`/`High` tolerance or
heat-shield status.

### Which one owns a surface

**[PARTIAL].** `SurfaceData.heatModule` is assigned once in
`SurfaceData.Start()` @268922:

```csharp
heatModule = Component_Utility.GetComponentInParentTree<HeatModuleBase>(transform);
```

It walks up the transform tree for the nearest `HeatModuleBase`. Because
`Part` is itself one, the answer is "the `HeatModule` if the part has one,
otherwise the `Part`" — **but when both components sit on the same
GameObject the winner depends on Unity component order, which the IL does
not determine.** [OPEN], and settleable live by dumping
`Surface.owner.GetType()` per part.

> **Tooling bug this implies [PARTIAL].** `SFSProbe.cs`'s `GetHeatState`
> reads `Get(part, "temperature")` — the plain `Part.temperature` field —
> for every part. For any part whose surfaces are owned by a `HeatModule`
> instead, the real temperature lives in that module's `Float_Reference`
> and `Part.temperature` is never written. The rocket-wide max would then
> silently under-report. Worth checking before trusting heat telemetry;
> the fix is to read `Surface.owner`'s `Temperature` property, or to check
> both.

---

## HeatModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** SFS.World.Drag.HeatModuleBase
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @273416 · 21 methods / 8 fields

The opt-in per-part heat module. A part only gets `Mid`/`High` tolerance
or heat-shield status by carrying one.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `heatTolerance` | `SFS.World.Drag.HeatTolerance` | public | no | `Low`/`Mid`/`High` — feeds `get_HeatTolerance` | [CONFIRMED] |
| `isHeatShield` | `bool` | public | no | backs `IsHeatShield`; a heat shield sheds no joints on overheat | [CONFIRMED] |
| `useCustomName` | `bool` | public | no | | [CONFIRMED] |
| `customName` | `SFS.Translations.TranslationVariable` | public | no | | [CONFIRMED] |
| `temperature` | `SFS.Variables.Float_Reference` | public | no | **wrapped** — going at the field directly needs `GetWrapped` | [CONFIRMED] |
| `part` | `SFS.Parts.Part` | private | no | the owning part; `OnOverheat` forwards to it | [CONFIRMED] |
| `<LastAppliedIndex>k__BackingField` | `int` | private | no | auto-property backing field | [CONFIRMED] |
| `<ExposedSurface>k__BackingField` | `float` | private | no | auto-property backing field | [CONFIRMED] |

### Methods

All the `HeatModuleBase` members are overridden here as
`public virtual … specialname`. Bodies confirmed for the two that carry
real logic:

#### get_HeatTolerance() -> float

- **Access:** public override · IL @273583
- **Behavior:** `AeroModule.GetHeatTolerance(this.heatTolerance)` — so
  400 / 1000 / 6000 depending on the serialized enum.
- **Status:** [CONFIRMED]

#### OnOverheat(bool breakup) -> void

- **Access:** public override · IL @273596
- **Behavior:** `part.OnOverheat(this, breakup)` — forwards to
  [`Part.OnOverheat(HeatModuleBase, bool)`](../01-core-flight/Part.md),
  passing **itself** as the module, which is how the destruction path
  knows whether the overheating module was a heat shield.
- **Status:** [CONFIRMED]

| Other members | IL | Status |
|---|---|---|
| `private void Start()` | @273437 | [OPEN] |
| `get_Name` | @273452 | [PARTIAL] — uses `useCustomName` / `customName` |
| `get_IsHeatShield` | @273486 | [CONFIRMED] — returns `isHeatShield` |
| `get_Temperature` / `set_Temperature` | @273498 / @273511 | [CONFIRMED] — through the `Float_Reference` |
| `get_/set_LastAppliedIndex` | @273525 / @273539 | [CONFIRMED] — auto-property |
| `get_/set_ExposedSurface` | @273554 / @273568 | [CONFIRMED] — auto-property |

---

## HeatTolerance

**Namespace:** SFS.World.Drag
**Kind:** enum
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @217798

`Low = 0, Mid = 1, High = 2`

### The destruction thresholds

**[CONFIRMED]** — `AeroModule.GetHeatTolerance(HeatTolerance)` @216396,
a plain `switch`:

```csharp
public static float GetHeatTolerance(HeatTolerance a) => a switch {
    HeatTolerance.Low  => 400f,
    HeatTolerance.Mid  => 1000f,
    HeatTolerance.High => 6000f,
    _                  => 0f,
};
```

Destruction fires at `Temperature > HeatTolerance * 1.03f` (see
[`HeatManager.md`](HeatManager.md)), so:

| Tolerance | Value | **Actual break temperature** |
|---|---|---|
| `Low` (default for any plain `Part`) | 400 | **412.0** |
| `Mid` | 1000 | **1030.0** |
| `High` | 6000 | **6180.0** |

**This resolves an open data point.** The project's single observation
was 410.8 °C at the moment `partCount` began dropping — against a
computed threshold of 412.0 for a default part. The "~400 °C community
claim" was the tolerance constant, not the break point; the 3% margin
accounts for the rest.

---

## DestructionReason

**Namespace:** SFS.World
**Kind:** enum
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @192046

`TerrainCollision = 0, WaterCollision = 1, RocketCollision = 2,
Overheat = 3, Intentional = 4`

## Reflection recipe — per-part temperature

Read through `Surface.owner`, **not** `Part.temperature`:

```csharp
// owner is a HeatModuleBase: either the Part itself or its HeatModule
object owner = Get(surface, "owner");
float temp   = ToF(Get(owner, "Temperature"));       // property, works on both subclasses
float tol    = ToF(Get(owner, "HeatTolerance"));     // 400 / 1000 / 6000
bool  shield = ToB(Get(owner, "IsHeatShield"));
string name  = (string)Get(owner, "Name");
bool  willBreak = temp > tol * 1.03f;
```

`Get` reads properties as well as fields, so the virtual `Temperature` /
`HeatTolerance` / `IsHeatShield` resolve correctly for either subclass
without a type test.

**Gotchas:**

- `HeatModule.temperature` is a **`Float_Reference`** — going at the
  field directly needs `GetWrapped`. The `Temperature` **property**
  avoids this; prefer it.
- `Part.temperature` is a plain `float` field and is **not** the
  authoritative value when a `HeatModule` owns the surfaces.
- `+∞` / `−∞` are sentinel values, not real temperatures — see
  [`HeatManager.md`](HeatManager.md).

## Status summary

| Item | Status |
|---|---|
| `Part : HeatModuleBase` | [CONFIRMED] |
| `HeatModuleBase` — one field, nine abstract members | [CONFIRMED] |
| Storage differs per subclass (`float` vs `Float_Reference`) | [CONFIRMED] |
| Plain `Part` is always `Low` tolerance, never a heat shield | [CONFIRMED] |
| Tolerance values 400 / 1000 / 6000 | [CONFIRMED] |
| Break threshold `> tolerance × 1.03` → **412 °C** default | [CONFIRMED] — explains the 410.8 °C data point |
| `HeatModule` field layout | [CONFIRMED] |
| `HeatModule.get_HeatTolerance` / `OnOverheat` bodies | [CONFIRMED] |
| `HeatModule.Start` / `get_Name` bodies | [OPEN] |
| `HeatModuleBase.OnEnable` / `OnDisable` bodies | [OPEN] |
| Which `HeatModuleBase` owns a surface when both are on one GameObject | [OPEN] |
| Probe `GetHeatState` may under-report | [PARTIAL] — needs a live check |
