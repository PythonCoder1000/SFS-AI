# `ErrorLogger` — the game's own log tail

**Migrated** from `docs/sfs_source_reference.md` §E7.4 (2026-08-28).

---

## ErrorLogger

**Namespace:** *(none — top-level, global namespace)*
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] surface
**Depth:** FULL
**IL:** `scratch/full_il.txt` @13341 · 5 methods / 5 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `ErrorLogger` | public | **static** | the singleton | [CONFIRMED] |
| `lastLogs` | `List<string>` | **public** | no | **the simplest possible "what did the game just complain about" read** | [CONFIRMED] |
| `logs` | `Queue<(string condition, string stackTrace, LogType)>` | private | no | | [CONFIRMED] |
| `logLocation` | `IFile` | private | no | | [CONFIRMED] |
| `logBuilder` | | private | no | | [CONFIRMED] shape |

### Methods

#### Awake() -> void

- **Access:** private instance (Unity message) · IL @13351
- **Behavior:** reads `FileLocations.LogsFolder/counter.txt`, parses a
  `long`, and rotates — **a numbered log rotation with a small retention
  count** (`ldc.i4.5` appears in the rotation arithmetic).
- **Status:** [PARTIAL] — **the exact retention semantics were not
  transcribed**

#### GetLogsDumpBase64Gzip() -> string

- **Access:** **public** · IL @13474
- **Returns:** the log dump as a **base64 gzip string**
- **Gotchas:** **a ready-made way to pull the game's own log tail out
  through the probe's existing text channel** without touching the
  filesystem.
- **Status:** [CONFIRMED] signature · [OPEN] body

#### LogMessage(string condition, string stackTrace, LogType) -> void

- **Access:** instance · IL @13600 — the Unity log callback
- **Status:** [PARTIAL]

#### LogLoop() -> void

- **Access:** instance · IL @13571 — drains the queue
- **Status:** [PARTIAL]

---

## Why this matters for the probe

**`ErrorLogger.main.lastLogs` is a public `List<string>`** — and it is
directly useful against the swallowed-exception problem documented in
[`../04-engines/EngineModule.md`](../04-engines/EngineModule.md): the
bare `catch { }` blocks in `SFSProbe.cs` log **nothing**, but a Unity
exception thrown *inside game code* **does** land here.

## Status summary

| Item | Status |
|---|---|
| `ErrorLogger` layout; `lastLogs` public | [CONFIRMED] |
| `GetLogsDumpBase64Gzip()` is public | [CONFIRMED] |
| Log rotation retention semantics | [PARTIAL] |
| `LogMessage` / `LogLoop` / `GetLogsDumpBase64Gzip` bodies | [OPEN] |
