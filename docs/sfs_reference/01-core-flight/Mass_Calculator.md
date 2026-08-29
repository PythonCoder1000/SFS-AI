# `SFS.Parts.Mass_Calculator` — craft mass and centre of mass

**Migrated** from `docs/sfs_source_reference.md` §B6 (2026-08-28).

A small class, but it closes the loop between the expression evaluator
([`../08-parametric-expressions/Compute.md`](../08-parametric-expressions/Compute.md))
and the rigidbody — and it has a timewarp gate worth knowing about.

---

## Mass_Calculator

**Namespace:** SFS.Parts
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @235824 · 8 methods / 4 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `partHolder` | `PartHolder` | public | no | the parts summed over | [CONFIRMED] |
| `dirty` | `bool` | **private** | no | recalculation flag | [CONFIRMED] |
| `mass` | `float` | **private** | no | cached total | [CONFIRMED] |
| `centerOfMass` | `Vector2` | **private** | no | cached centroid | [CONFIRMED] |

### Methods

#### GetMass() -> float

#### GetCenterOfMass() -> Vector2

- **Access:** public instance · IL @235889 / @235903
- **Behavior:** both call `Calculate()` first, so **they are always
  current** — no caller has to remember to refresh.
- **Status:** [CONFIRMED]

#### Calculate() -> void

- **Access:** instance · IL @235917, body read
- **Behavior:**
  ```csharp
  if (!dirty) return;
  mass = 0f;
  centerOfMass = Vector2.zero;
  foreach (Part p in partHolder.parts) {
      mass += p.mass.Value;
      centerOfMass += (p.Position + (p.centerOfMass.Value * p.orientation))
                    * p.mass.Value;
  }
  centerOfMass /= mass;
  dirty = false;
  ```
  A plain mass-weighted centroid.
- **Gotchas:** two.
  - Each part's local `centerOfMass` is run through
    `OrientationModule.op_Multiply(Vector2, OrientationModule)` before
    being added to `Position` — **mirrored and rotated parts have their
    CoM offset transformed**, so an agent computing CoM itself **must
    apply the orientation**, not just the position.
  - **`centerOfMass /= mass` is unguarded.** A craft with zero total mass
    yields NaN, and `Rocket.UpdateMass` writes that **straight into
    `rb2d.centerOfMass` every tick**. Not reachable with real parts;
    worth knowing if an agent ever constructs a degenerate craft.
- **Status:** [CONFIRMED]

#### Start() -> void

- **Access:** private instance (Unity message) · IL @235833
- **Behavior:** wires three things:
  ```csharp
  partHolder.TrackParts(b__1_0, b__1_1, MarkDirty);          // add / remove / after-remove
  WorldTime.main.realtimePhysics.OnChange += MarkDirty;
  ```
  and the per-part handlers @236016 / @236046 subscribe and unsubscribe
  `MarkDirty` on **that part's `mass.OnChange` and
  `centerOfMass.OnChange`** — the `Composed<T>` change events.
- **Status:** [CONFIRMED]

> ### This is the mechanism by which craft mass follows fuel burn
>
> A `ResourceModule` write changes a variable → the part's
> `Composed_Float mass` recomputes → its `OnChange` fires → `MarkDirty` →
> the next `GetMass()` recalculates. **Nothing polls.** It also means an
> agent that writes a part variable directly gets a correct `rb2d.mass`
> on the next tick for free.

#### MarkDirty() -> void

- **Access:** instance · IL @235867, body read
- **Behavior:**
  ```csharp
  if (WorldTime.main != null && !WorldTime.main.realtimePhysics.Value) return;
  dirty = true;
  ```
- **Gotchas:** **mass changes are ignored while `realtimePhysics` is
  false** — i.e. on rails / during timewarp, the same flag that gates
  heat destruction. The `realtimePhysics.OnChange += MarkDirty`
  subscription is what **repairs** this: when the flag goes false→true,
  `MarkDirty` runs *after* the flag is already true, so it sets `dirty`
  and the first post-timewarp read recalculates.

  **Leaving timewarp is therefore safe; reading `GetMass()` *during*
  timewarp can return a value that predates any mass change made while
  warping.** Same "goes stale on rails" pattern as the heat and SOI
  findings.
- **Status:** [CONFIRMED]

## Status summary

| Item | Status |
|---|---|
| Field layout; `GetMass`/`GetCenterOfMass` always call `Calculate` | [CONFIRMED] |
| Mass-weighted centroid formula, orientation-transformed CoM | [CONFIRMED] |
| `centerOfMass /= mass` unguarded → NaN at zero mass | [CONFIRMED] |
| Invalidation via per-part `Composed<T>.OnChange` | [CONFIRMED] |
| `MarkDirty` suppressed while `!realtimePhysics` | [CONFIRMED] |
| `realtimePhysics.OnChange` repairs it on timewarp exit | [CONFIRMED] |
| Stale mass during timewarp observed in game | [UNTESTED-LIVE] |
| `OrientationModule.op_Multiply` own entry | [OPEN] — Step 2 |
