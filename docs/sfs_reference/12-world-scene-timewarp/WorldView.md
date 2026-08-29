# `SFS.World.WorldView` — the floating origin *and* floating velocity frame

**Migrated** from `docs/sfs_source_reference.md` §E5.2 (2026-08-28).

---

## WorldView

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @199446 · 20 methods / 20 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `ScaledSpaceScale` | `float` | public | **const** | `10000f` | [CONFIRMED] |
| `ScaledSpaceThreshold` | `float` | private | **const** | `50000f` — **a rendering switch, not necessarily the rebase threshold** | [CONFIRMED] |
| `main` | `WorldView` | public | static | the singleton | [CONFIRMED] |
| `positionOffset` | `Double2_Local` | public | no | the floating origin | [CONFIRMED] |
| `velocityOffset` | `Double2_Local` | public | no | **the floating velocity frame** | [CONFIRMED] |
| `framing`, `viewDistance`, `scaledSpace`, `canVelocityOffset` | `Obs<T>` | public | no | | [CONFIRMED] |
| `ViewLocation` | `Location` | public (private set) | no | property | [CONFIRMED] |

Four public events: `onViewLocationChange_Before` / `_After`,
`onPositionOffset`, `onVelocityOffset`.

### The four conversions

**All `public static`** — the sanctioned bridge between world coordinates
(`Double2`, planet-relative, metres) and Unity scene coordinates
(`Vector2`).

```csharp
static Vector2 ToLocalPosition(Double2 globalPosition)
    => (Vector2)(globalPosition - main.positionOffset);
static Vector2 ToLocalVelocity(Double2 globalVelocity)
    => (Vector2)(globalVelocity - main.velocityOffset);
static Double2 ToGlobalPosition(Vector2 localPosition);     // the inverse
static Double2 ToGlobalVelocity(Vector2 localVelocity);
```

> ### SFS uses both a floating origin *and* a floating velocity frame
>
> `positionOffset` is the usual origin-rebasing trick. **`velocityOffset`
> is less common** — the Unity rigidbody's velocity is *relative to a
> moving reference*, which is why `Rocket`'s `I_Physics.LocalVelocity`
> (`rb2d.linearVelocity`) is **not** the craft's world velocity.
> **Anything comparing a `Vector2` velocity to a `Double2` one must
> convert.** `Physics.SetLocationAndState` uses exactly these calls.

### Rebasing

`positionOffset` and `velocityOffset` are recomputed by the private
`CalculatePositionOffset` @199818 and `CalculateVelocityOffset` @199862,
with `Physics.OnPositionOffset` / `OnVelocityOffset` subscribing to the
two events so tracked objects are shifted in step.

> **An agent caching a Unity-space position across frames must re-base
> it** — or subscribe to `onPositionOffset`.

**Bodies of the offset calculators not read — [PARTIAL]**, so **the
trigger threshold for a rebase is unconfirmed.**
`ScaledSpaceThreshold = 50000f` is a *rendering* switch, used by
`UpdateIsScaledSpace` @199656, and **should not be assumed to be the
rebase threshold.**

`GetOffset(Double2 a, double b)` @199952 is public static — **[PARTIAL]**,
body not read.

## Status summary

| Item | Status |
|---|---|
| `WorldView` conversions; floating origin **and** velocity frame | [CONFIRMED] |
| `ScaledSpaceScale = 10000`, `ScaledSpaceThreshold = 50000` | [CONFIRMED] — literals |
| `rb2d.linearVelocity` is not world velocity | [CONFIRMED] |
| Whether `ScaledSpaceThreshold` also triggers origin rebase | [OPEN] — **do not assume** |
| `CalculatePositionOffset` / `CalculateVelocityOffset` bodies | [PARTIAL] |
| `GetOffset` body | [PARTIAL] |
| `UpdateIsScaledSpace` body and the remaining members | [OPEN] |
