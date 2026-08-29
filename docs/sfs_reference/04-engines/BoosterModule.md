# `SFS.Parts.Modules.BoosterModule` — solid rocket boosters

**Migrated** from `docs/sfs_source_reference.md` §D2.5 (2026-08-28).

---

## BoosterModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [PARTIAL]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @259149 · 27 methods / 20 fields

**SRBs are a separate code path from
[`EngineModule.md`](EngineModule.md).** This matters because **anything
scanning for `EngineModule` misses solid boosters entirely** — including
the probe's `GetEngineDirection`.

The same concepts carry **different field names**: `thrustVector` not
`thrustNormal`, `boosterPrimed` not `engineOn`, and fuel as a scalar
`fuelPercent` rather than a `ResourceModule`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `resourceType` | `ResourceType` | public | no | | [CONFIRMED] |
| `ISP` | `Composed_Float` | public | no | | [CONFIRMED] |
| `thrustVector` | `Composed_Vector2` | public | no | **not** `thrustNormal` | [CONFIRMED] |
| `thrustPosition` | `Composed_Vector2` | public | no | | [CONFIRMED] |
| `wetMass` | `Composed_Float` | public | no | | [CONFIRMED] |
| `dryMassPercent` | `Composed_Float` | public | no | | [CONFIRMED] |
| `fuelPercent` | `Float_Reference` | public | no | **not** a `ResourceModule` — a plain scalar | [CONFIRMED] |
| `boosterPrimed` | `Bool_Reference` | public | no | **not** `engineOn` | [CONFIRMED] |
| `throttle_Out` | `Float_Reference` | public | no | | [CONFIRMED] |
| `mass_Out` | `Double_Reference` | public | no | | [CONFIRMED] |
| `surfaceForCover` | `SurfaceData` | public | no | | [CONFIRMED] |
| `newIgnitionTime` | `float` | private | no | | [CONFIRMED] |
| `throttle_Input` | `Float_Local` | private | no | | [CONFIRMED] |
| `part` | `Part` | private | no | | [CONFIRMED] |

Plus `private float ThrustDuration { get; }` @259223.

The remaining fields of the 20 are [OPEN].

### Methods

#### FixedUpdate() -> void

- **Access:** private instance (Unity message) · IL @259801
- **Behavior:** fuel burn:
  ```csharp
  if (Rocket == null) return;
  if (!SandboxSettings.main.settings.infiniteFuel) {
      fuelPercent.Value -= Time.fixedDeltaTime / ThrustDuration * throttle_Out.Value;
      if (fuelPercent.Value <= 0f) {
          throttle_Out.Value = 0f;
          fuelPercent.Value  = 0f;
          this.enabled = false;              // component disables itself
      }
  }
  ...
  ```
- **Side effects:** mutates `fuelPercent` and `throttle_Out`; **disables
  its own component** when spent.
- **Gotchas:**
  - Uses `Time.fixedDeltaTime` (Unity clock), **not**
    `WorldTime.FixedDeltaTime` as the heat system uses — so it does not
    scale with rails timewarp.
  - `SandboxSettings.main.settings.infiniteFuel` is a **third** sandbox
    flag alongside `noAtmosphericDrag` and `noHeatDamage`, and it skips
    consumption entirely rather than refilling — see
    [`../09-resources-fuel/FlowModule.md`](../09-resources-fuel/FlowModule.md)
    for the same pattern on liquid fuel and why it changes mass, not just
    endurance.
  - A spent booster's component is `enabled = false`, so anything
    enumerating enabled components will stop seeing it.
- **Status:** [CONFIRMED] for the quoted fragment · [PARTIAL] for the
  rest of the body

#### ThrustDuration { get; } -> float

- **Access:** private instance property · IL @259223
- **Status:** [PARTIAL] — signature confirmed, body [OPEN]

#### RecalculateMass() -> void

- **Access:** instance · IL @259448
- **Status:** [OPEN] — body not read

The remaining ~24 methods are **[OPEN]** — Step 2.

## Status summary

| Item | Status |
|---|---|
| `BoosterModule` is a separate path with different field names | [CONFIRMED] |
| Field layout (14 of 20 named) | [CONFIRMED] |
| `FixedUpdate` fuel-burn fragment; self-disable on empty | [CONFIRMED] |
| Uses `Time.fixedDeltaTime`, not `WorldTime.FixedDeltaTime` | [CONFIRMED] |
| `infiniteFuel` sandbox flag skips consumption | [CONFIRMED] |
| Rest of `FixedUpdate` body | [PARTIAL] |
| `RecalculateMass`, `ThrustDuration` and the remaining methods | [OPEN] |
| The remaining 6 fields | [OPEN] |
