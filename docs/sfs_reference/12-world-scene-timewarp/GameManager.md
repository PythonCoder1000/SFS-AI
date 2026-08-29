# `SFS.World.GameManager`, `SFS.SceneLoader`, `ModLoader.Helpers.SceneHelper`

**Group file.** The world-scene singleton and the two ways to know which
scene is loaded.

**Migrated** from `docs/sfs_source_reference.md` §E5.3–E5.4
(2026-08-28).

---

## GameManager

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @178293 · 31 methods / 9 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `GameManager` | public | **static** | the world-scene singleton | [CONFIRMED] |
| `environment` | `WorldEnvironment` | public | no | | [CONFIRMED] |
| `world_Input`, `map_Input` | `Screen_Game` | public | no | | [CONFIRMED] |
| `aeroData` | `AeroData` | public | no | **where the serialized `AeroFormula` coefficients live** | [CONFIRMED] |
| `rockets` | `List<Rocket>` | public | no | **every craft in the world** | [CONFIRMED] |
| `particles` | `List<WorldParticle>` | public | no | | [CONFIRMED] |
| `fuelManager` | `GameObject` | public | no | | [CONFIRMED] |
| `timeSinceLastSave` | `float` | **private** | no | | [CONFIRMED] |

- **`GameManager.main.rockets` is the craft enumeration point** — the
  probe's `world` command territory.
- **`GameManager.main.aeroData` is where the `velPow` / `densityPow` /
  `tempOffset` / `m` coefficients live** that
  [`../02-drag-aero/AeroFormula.md`](../02-drag-aero/AeroFormula.md)
  marks [OPEN]. Reading it live closes that gap. **The `AeroData` type's
  own layout was not read — [PARTIAL].**

### Methods

Signatures confirmed.

| Method | IL | Note | Status |
|---|---|---|---|
| `RevertToLaunch(bool skipConfirmation)` | @178885 | see below | [CONFIRMED] |
| `RevertToBuild(bool skipConfirmation)` | @178958 | | [PARTIAL] |
| `ExitToBuild()`, `ExitToHub()`, `ExitToMainMenu()` | | scene transitions | [PARTIAL] |
| `OpenMenu()`, `OpenSave()`, `OpenLoad()` | | UI | [PARTIAL] |
| `LoadSave(WorldSave save, bool forLaunch, I_MsgLogger logger)` | @179389 | **the programmatic world-load entry** | [PARTIAL] |

#### RevertToLaunch(bool skipConfirmation) -> void

- **Access:** public instance · IL @178885
- **Behavior:** reads a revert point through
  `SavingCache.TryLoadRevertToLaunch(out WorldSave)`, compares
  `WorldTime.main.worldTime` against `revertSave.state.worldTime`, and —
  unless `skipConfirmation` — routes through
  `MenuGenerator.OpenConfirmation`, gated by a one-time notification
  keyed `"Revert_Functionality"` via
  `FileLocations.GetOneTimeNotification`.
- **Gotchas:** **`skipConfirmation: true` is the headless path**, which
  is what the probe's `revert` command needs.
- **Status:** [CONFIRMED]

Private helpers: `CreateWorldSave()` @179164,
`UpdatePersistent(bool, bool, bool)` @179146,
`LoadPersistentAndLaunch()` @179239, `ClearWorld()` @179712,
`static IsOnLaunchpad(string planet, Double2 position)` @179870. All
**[PARTIAL]** — signatures.

---

## SceneLoader

**Namespace:** SFS
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] scene names and signatures
**Depth:** FULL
**IL:** `scratch/full_il.txt` @46165 · 18 methods / 9 fields

**Five scene names**, read from the `ldstr` literals @46185–46229:
**`"Base"`, `"Home"`, `"Hub"`, `"Build"`, `"World"`** — with `Base`
persistent.

### Methods

| Signature | Status |
|---|---|
| `LoadHomeScene(string openShop)` | [CONFIRMED] signature |
| `LoadHubScene()` | [CONFIRMED] signature |
| `LoadBuildScene(bool askBuildNew)` | [CONFIRMED] signature |
| `LoadWorldScene(bool launch = …)` | [CONFIRMED] signature |
| `static ExitToMainMenu()` | [CONFIRMED] signature |

> **Loading is async** (`LoadSceneAsync`, an `IEnumerator` coroutine), so
> **a scene change does not complete within the calling frame** — an
> agent must wait on an event, not assume.

`SFS.Base` @46080 is the static service locator holding `sceneLoader`,
`worldBase`, `planetLoader`, `partsLoader`, `inputManager`, `language`,
`sound`, `screenTracker`, `saver`. Own entry [OPEN] — Step 2.

---

## SceneHelper

**Namespace:** ModLoader.Helpers
**Kind:** static class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @44364 · 1 method / 10 fields

**Ten `OptionalDelegate<Scene>` hooks**, all `public static`:

| Field | Type | Access | Static |
|---|---|---|---|
| `OnHomeSceneLoaded` / `OnHomeSceneUnloaded` | `OptionalDelegate<Scene>` | public | static |
| `OnHubSceneLoaded` / `OnHubSceneUnloaded` | `OptionalDelegate<Scene>` | public | static |
| `OnBuildSceneLoaded` / `OnBuildSceneUnloaded` | `OptionalDelegate<Scene>` | public | static |
| `OnWorldSceneLoaded` / `OnWorldSceneUnloaded` | `OptionalDelegate<Scene>` | public | static |
| `OnSceneLoaded` / `OnSceneUnloaded` | `OptionalDelegate<Scene>` | public | static |

> **These are the clean subscription points for "the world is ready"**,
> and they require **no Harmony**. The only method is the `.cctor`
> @44379.

**Status:** [CONFIRMED] surface · [OPEN] `.cctor` body and
`OptionalDelegate<T>`'s own entry.

## Status summary

| Item | Status |
|---|---|
| `GameManager` field layout; `rockets`, `aeroData` | [CONFIRMED] |
| `aeroData` is where the open `AeroFormula` coefficients live | [CONFIRMED] — location; values still live-only |
| `RevertToLaunch` confirmation path and `skipConfirmation` | [CONFIRMED] |
| Five scene names | [CONFIRMED] — string literals |
| Scene loading is async | [CONFIRMED] |
| `SceneHelper`'s ten scene hooks | [CONFIRMED] |
| `AeroData` layout | [PARTIAL] |
| `LoadSave` body | [PARTIAL] |
| `SceneLoader` method bodies | [PARTIAL] |
| `WorldEnvironment`, `Screen_Game`, `WorldParticle`, `SFS.Base`, `SavingCache`, `OptionalDelegate<T>` | [OPEN] — Step 2 |
