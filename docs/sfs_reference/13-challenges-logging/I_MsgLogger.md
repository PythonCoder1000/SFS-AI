# `SFS.I_MsgLogger` and `SFS.UI.MsgDrawer` — the refusal-reason channel

**Migrated** from `docs/sfs_source_reference.md` §E7.1 (2026-08-28).

---

## I_MsgLogger

**Namespace:** SFS
**Kind:** interface
**Extends:** —
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @64110 · 1 method / 0 fields

```
.class interface public auto ansi abstract I_MsgLogger    @64110
    void Log(string msg)
```

**A single-method interface.** It is the `logger` parameter threaded
through:

| Call site | File |
|---|---|
| `Rocket.CanTimewarp(I_MsgLogger, bool, out bool)` | [`../01-core-flight/Rocket.md`](../01-core-flight/Rocket.md) |
| `WorldTime.CanTimewarp(bool, bool, out bool)` | [`../12-world-scene-timewarp/WorldTime.md`](../12-world-scene-timewarp/WorldTime.md) |
| `FlowModule.CanFlow(I_MsgLogger)` and `Flow.CanFlow_ElseShowMsg` | [`../09-resources-fuel/resources-and-flow.md`](../09-resources-fuel/resources-and-flow.md) |
| `GameManager.LoadSave(WorldSave, bool, I_MsgLogger)` | [`../12-world-scene-timewarp/GameManager.md`](../12-world-scene-timewarp/GameManager.md) |
| `RcsModule.Update_RCS_On` (via `MsgDrawer.main` or `MsgNone`) | [`../05-rcs/RcsModule.md`](../05-rcs/RcsModule.md) |

> ### The highest-value integration point in this area
>
> **An agent that passes its own `I_MsgLogger` implementation into those
> calls receives the game's own localised explanation of a refusal** —
> "cannot timewarp while moving on surface", "no control" — **instead of
> a bare `false`.** That is a diagnosis channel the probe does not
> currently use, and **it requires no Harmony and no patching**, only an
> object implementing one method.

`SFS.MsgNone` is the game's no-op implementation, used when the craft is
not the player's. Own entry [OPEN].

---

## MsgDrawer

**Namespace:** SFS.UI
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** `SFS.I_MsgLogger` (**explicitly**)
**Status:** [CONFIRMED] surface
**Depth:** FULL
**IL:** `scratch/full_il.txt` @122379 · 6 methods / 6 fields

The game's own implementation: a static `main`, `Log(string)` (**the
explicit interface method**, `final virtual`) and
`Log(string msg, bool big)` @122416.

**Gotcha:** **two overloads, ambiguous under naive `GetMethod("Log")`** —
and one of them is an explicit interface implementation, so it does not
reflect off the class by the plain name at all. Catalogued in
[`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.

**Status:** [CONFIRMED] surface · [OPEN] bodies and the other 4 fields.

## Status summary

| Item | Status |
|---|---|
| `I_MsgLogger` is a one-method interface | [CONFIRMED] |
| It is the refusal-reason channel across timewarp/control/fuel/load gates | [CONFIRMED] |
| `MsgDrawer.Log` has two overloads (ambiguous) | [CONFIRMED] |
| `MsgDrawer` bodies | [OPEN] |
| `MsgNone`, `MsgCollector` own entries | [OPEN] — Step 2 |
| Passing a custom `I_MsgLogger` into the game's gates | [UNTESTED-LIVE] |
