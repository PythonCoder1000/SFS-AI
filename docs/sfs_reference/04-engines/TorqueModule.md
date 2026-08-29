# `SFS.Parts.Modules.TorqueModule` — reaction wheels

**Migrated** from `docs/sfs_source_reference.md` §D2.6 (2026-08-28).

---

## TorqueModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `SFS.UI.I_PartMenu` (explicit)
**Status:** [CONFIRMED] layout
**Depth:** FULL
**IL:** `scratch/full_il.txt` @265256 · 2 methods / 3 fields

**Three fields and no physics of its own.** The torque *application* is
not here — it lives in the rotation path, which sums
`Σ(enabled TorqueModule.torque)`. The probe's own `SumEnabledTorque`
helper matches that shape. See
[`../01-core-flight/Rocket.md`](../01-core-flight/Rocket.md) and
`docs/sfs_physics_reference.md` §2.4.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `enabled` | `Bool_Reference` | public | no | read as `t.enabled.Local \|\| t.enabled.Value` by `Rocket.GetTorque` — an **unbound** module counts as enabled | [CONFIRMED] |
| `torque` | `Composed_Float` | public | no | the contribution summed by the rotation path | [CONFIRMED] |
| `showDescription` | `bool` | public | no | UI only | [CONFIRMED] |

**Gotcha:** the `Local || Value` read is not redundant. `Local` means
"not bound to a shared variable", so an unbound `Bool_Reference` is
treated as enabled regardless of its `localValue`. See
[`../00-infrastructure/variables-wrapper-family.md`](../00-infrastructure/variables-wrapper-family.md).

### Methods

The only non-constructor method is an explicit `I_PartMenu.Draw`
implementation — UI only, **[OPEN]**.

## Status summary

| Item | Status |
|---|---|
| Three fields, no physics of its own | [CONFIRMED] |
| `enabled` is a `Bool_Reference` read with `Local \|\| Value` | [CONFIRMED] |
| Torque summation call site | [OPEN] — not located |
| `I_PartMenu.Draw` body | [OPEN] — UI only |
