# `SFS.World.Drag.HeatManager` — absorption, dissipation, destruction

**Migrated** from `docs/sfs_source_reference.md` §D1.3–D1.4 (2026-08-28).
Signatures re-read from IL during migration.

Heat ownership: [`HeatModuleBase.md`](HeatModuleBase.md). The air
temperature it is fed:
[`../02-drag-aero/AeroFormula.md`](../02-drag-aero/AeroFormula.md). It is
owned by [`../02-drag-aero/AeroModule.md`](../02-drag-aero/AeroModule.md),
whose `FixedUpdate` calls `DissipateHeat` every tick.

---

## HeatManager

**Namespace:** SFS.World.Drag
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] for the two main bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @217811 · 8 methods / 3 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `AbsorptionRate` | `float` | private | **const** | `0.02f` (IL literal `0.019999999552965164`) | [CONFIRMED] |
| `DissipationRate` | `float` | private | **const** | `0.01f` (IL literal `0.0099999997764825821`) | [CONFIRMED] |
| `heated` | `List<HeatModuleBase>` | private | no | the modules currently above the "not heated" sentinel | [CONFIRMED] |

> The `public List<HeatModuleBase> best` field that a naive extractor
> reports on this class does **not** exist — it is a closure field on the
> nested `<>c__DisplayClass6_0`. Exactly the artifact
> [`../METHODOLOGY.md`](../METHODOLOGY.md) warns about; caught again here.

### Methods

#### ApplyHeat(List&lt;Surface&gt; exposedSurfaces, float temperature, int frameIndex) -> void

- **Access:** public instance · IL @217819, full body read
- **Parameters:** `exposedSurfaces` — the shared exposed list from
  `AeroModule.FixedUpdate`, **mutated in place**; `temperature` — the
  global air temperature; `frameIndex` — `AeroModule.frameIndex`, used to
  apply at most once per module per frame
- **Behavior:**
  ```csharp
  float absorb = 0.02f * WorldTime.FixedDeltaTime;

  // 1. drop surfaces whose Valid token has been cleared
  for (int i = exposedSurfaces.Count - 1; i >= 0; i--)
      if (!exposedSurfaces[i].valid.valid) {
          exposedSurfaces.RemoveAt(i);
          AnalyticsUtility.SendEvent("Heat_Manager_Save_v2");
      }

  // 2. accumulate exposed width per owner (x-extent in velocity-aligned space)
  foreach (Surface s in exposedSurfaces)
      s.owner.ExposedSurface += (s.line.end.x - s.line.start.x);

  var overheated = new List<HeatModuleBase>();

  // 3. apply, at most once per module per frame
  foreach (Surface s in exposedSurfaces) {
      HeatModuleBase m = s.owner;
      if (m.LastAppliedIndex == frameIndex) continue;
      if (float.IsNegativeInfinity(m.Temperature)) { m.Temperature = 0f; heated.Add(m); }

      float delta = temperature - m.Temperature;
      if (delta <= 0f) continue;                       // ApplyHeat never cools

      float surfaceFactor = 1f + Mathf.Log10(m.ExposedSurface + 1f);
      float d = (delta < 1000f) ? delta : (delta * delta / 1000f);   // superlinear above 1000

      m.Temperature += surfaceFactor * d * absorb;
      m.LastAppliedIndex = frameIndex;

      if (m.Temperature > m.HeatTolerance * 1.03f
          && !SandboxSettings.main.settings.noHeatDamage
          && WorldTime.main.realtimePhysics.Value
          && !overheated.Contains(m))
          overheated.Add(m);
  }

  // 4. reset the accumulator
  foreach (Surface s in exposedSurfaces) s.owner.ExposedSurface = 0f;

  // 5. destroy
  foreach (HeatModuleBase m in overheated) m.OnOverheat(true);
  ```
- **Side effects:** mutates the caller's surface list, writes
  `Temperature` / `LastAppliedIndex` / `ExposedSurface` on every owner,
  appends to `heated`, sends an analytics event, and can destroy parts.
- **Gotchas:** five, all model-relevant.
  1. **Destruction threshold is `Temperature > HeatTolerance * 1.03f`.**
  2. **Parts cannot break during timewarp.** Destruction is gated on
     `WorldTime.main.realtimePhysics.Value`. Heat still *accumulates*
     under warp; it just cannot kill. A rocket that survives reentry
     under warp and dies on exiting warp is expected behaviour, not a
     glitch.
  3. **`SandboxSettings.main.settings.noHeatDamage`** disables
     destruction while leaving heating — the heat analogue of
     `noAtmosphericDrag`.
  4. **Heating rate scales with `1 + log10(exposedWidth + 1)`** — very
     weakly with size. Exposed width is the x-extent in velocity-aligned
     space, summed across all that module's exposed segments.
  5. **Above a 1000° gap the absorption goes quadratic**
     (`delta²/1000`), so heating accelerates sharply in a fast reentry.
- **Status:** [CONFIRMED]

#### DissipateHeat(int frameIndex) -> void

- **Access:** public instance · IL @218066, full body read
- **Parameters:** `frameIndex` — modules heated *this* frame are skipped
- **Behavior:** called every `FixedUpdate` from `AeroModule.FixedUpdate`
  **regardless of atmosphere**.
  ```csharp
  float rate  = 0.01f * WorldTime.FixedDeltaTime;
  float floor = 10f   * WorldTime.FixedDeltaTime;
  for (int i = heated.Count - 1; i >= 0; i--) {
      HeatModuleBase m = heated[i];
      if (m.LastAppliedIndex == frameIndex) continue;    // heated this frame -- don't cool
      float t = m.Temperature;
      if (t >= 0f) m.Temperature -= (floor + t * rate);  // constant floor + proportional
      if (m.Temperature <= 0f) {
          m.Temperature = float.PositiveInfinity;        // ldc.r4 (00 00 80 7f)
          heated.RemoveAt(i);
      }
  }
  ```
  Cooling is `10·dt + 0.01·T·dt` per tick — a constant floor plus a
  proportional term.
- **Side effects:** writes `Temperature`, removes from `heated`.
- **Status:** [CONFIRMED]

> ### Apparent sign inconsistency [OPEN] — reported, not diagnosed
>
> `DissipateHeat` writes **positive** infinity when a module finishes
> cooling (`ldc.r4 (00 00 80 7f)` = `0x7F800000`), but both readers test
> for **negative** infinity: `ApplyHeat` @217923 calls
> `float32::IsNegativeInfinity`, and `HeatPart` @218292 tests
> `IsNegativeInfinity || IsNaN`. There is no `IsPositiveInfinity` call
> anywhere in `HeatManager`. Taken literally, a module that cools to zero
> is never re-initialised: `ApplyHeat` would compute
> `delta = temperature − (+∞) = −∞ ≤ 0` and skip it forever, while
> `HeatPart` would add to `+∞` and immediately exceed any tolerance.
>
> **It has not been verified that modules actually reach
> `Temperature ≤ 0` in practice**, and the whole question is empirically
> testable — read `Surface.owner.Temperature` across a heat-then-cool
> cycle. Do not build on this either way until it is tested; it is
> recorded because it would materially change any heat model.
>
> **Later evidence shifts the balance.** `PartSave.temperature`'s field
> initialiser is also `+∞` (see
> [`../07-saveload/PartSave.md`](../07-saveload/PartSave.md)), which says
> `+∞` — not `−∞` — is the game's "not heated" sentinel. On that reading
> `DissipateHeat` is correct and the two `IsNegativeInfinity` tests are
> the bug. Still **[OPEN]**: it remains a code reading, not a
> measurement.

#### HeatPart(HeatModuleBase a) -> void

- **Access:** public instance · IL @218292, body read
- **Behavior:** the **non-aerodynamic** heating path — adds a flat
  `150 * Time.fixedDeltaTime` per call, then runs the same tolerance
  test, calling `OnOverheat(false)` — note **`false`**, not `true`, so
  this path destroys the part outright rather than shedding a joint.
- **Gotchas:** it uses `Time.fixedDeltaTime`, **not**
  `WorldTime.FixedDeltaTime` like `ApplyHeat`/`DissipateHeat` — a
  different clock, so it does not scale with rails timewarp. See
  [`../12-world-scene-timewarp/WorldTime.md`](../12-world-scene-timewarp/WorldTime.md).
- **Status:** [CONFIRMED] body · **[OPEN]** which callers use it

#### OnSetParts(Part[] newParts) -> void

- **Access:** public instance · IL @218145
- **Status:** [PARTIAL] — signature confirmed, body not read

#### GetMostHeatedModules(int count) -> List&lt;HeatModuleBase&gt;

- **Access:** public instance · IL @218227
- **Behavior:** uses two compiler-emitted local functions,
  `<GetMostHeatedModules>g__GetTargetIndex|6_0` @218363 and
  `g__GetHeatScore|6_1` @218408. The score function was read in passing:
  it is `Temperature / HeatTolerance`, then, **only for heat shields**,
  `Mathf.Lerp(0.35f, 1f, ratio)` — i.e. heat shields are ranked lower for
  the same fractional load.
- **Gotchas:** relevant only to the UI temperature bar.
- **Status:** [PARTIAL] — `GetHeatScore` confirmed, the main body [OPEN]

---

## The destruction path

**[CONFIRMED]** — `Part.OnOverheat(HeatModuleBase, bool)` @237177.
Documented in full here because it is the heat system's terminal step;
the class entry is
[`../01-core-flight/Part.md`](../01-core-flight/Part.md).

```csharp
public void OnOverheat(HeatModuleBase module, bool breakup)
{
    List<PartJoint> joints = Rocket.jointsGroup.GetConnectedJoints(this);

    if (breakup && joints.Count > 0 && !module.IsHeatShield)
    {
        // BREAK OFF rather than destroy
        Rocket rocket = Rocket;
        JointGroup.DestroyJoint(joints[0], Rocket, out bool split, out Rocket newRocket);
        EffectManager.CreatePartOverheatEffect(
            transform.TransformPoint(centerOfMass.Value), mass.Value + ...);
        if (split) {
            rocket.EnableCollisionImmunity(1.5f);
            newRocket.EnableCollisionImmunity(1.5f);
            if (rocket.isPlayer)
                Rocket.SetPlayerToBestControllable(new[] { rocket, newRocket });
        }
        module.Temperature *= 0.8f;     // cools 20% after shedding the joint
        return;
    }

    // otherwise: full destruction (falls through to the same work as DestroyPart)
    EffectManager.CreateExplosion(transform.TransformPoint(centerOfMass.Value),
                                  mass.Value * 2f + 0.5f);
    onPartDestroyed?.Invoke(this);  onPartDestroyed = null;
    JointGroup.OnPartDestroyed(this, Rocket, DestructionReason.Overheat);
    Destroy(gameObject);
}
```

**Overheating does not destroy a part outright while it still has
joints.** It destroys **one joint** (`joints[0]`), sheds that connection,
and cools the module by 20%. Only a jointless part — or a heat-shield
module, or `breakup == false` — is actually destroyed. This is why part
count drops gradually rather than all at once during a bad reentry, and
it means **a single overheat event can split the rocket into two
independently-tracked `Rocket` objects**, with 1.5 s of mutual collision
immunity.

Related, **[CONFIRMED]** signature:

```
public void Part.DestroyPart(bool createExplosion, bool updateJoints, DestructionReason reason)  @237290
```

Explosion size is `mass * 2 + 0.5`.

## Gotchas before predicting destruction

- Check `SandboxSettings.main.settings.noHeatDamage`.
- Check `WorldTime.main.realtimePhysics.Value` — no destruction under
  rails timewarp.
- Check `aeroData.testShock` / `testReentry` before trusting the
  temperature that feeds this at all.

## Status summary

| Item | Status |
|---|---|
| Absorption `0.02`, dissipation `0.01`, cooling floor `10·dt` | [CONFIRMED] |
| `ApplyHeat` full body | [CONFIRMED] |
| `1 + log10(exposedWidth+1)` scaling; quadratic above Δ1000 | [CONFIRMED] |
| Destruction threshold `> tolerance × 1.03` | [CONFIRMED] |
| No destruction during timewarp | [CONFIRMED] |
| `DissipateHeat` full body | [CONFIRMED] |
| `HeatPart` body — flat 150·`Time.fixedDeltaTime`, `OnOverheat(false)` | [CONFIRMED] |
| Overheat breaks a **joint** first, destroys only jointless parts | [CONFIRMED] |
| `+∞` vs `IsNegativeInfinity` mismatch | [OPEN] — reported, needs a live test |
| `HeatPart` callers | [OPEN] |
| `OnSetParts` body | [OPEN] |
| `GetMostHeatedModules` main body | [OPEN] — UI only |
