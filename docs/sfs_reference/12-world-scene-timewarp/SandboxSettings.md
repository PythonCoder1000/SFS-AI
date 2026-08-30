# SandboxSettings — `SFS.World`

Written out of order, during **Phase 1 Step 1.5 (Mod-Integration Safety
Audit)**, because `sfsprobe`'s `cheat` command already ships against it:

```csharp
case "cheat":
    object ss = FindComponent("SFS.World.SandboxSettings");
    Invoke(ss, "Toggle" + arg, new object[0]);
```

That is a **state-mutating** command built on a class with no coverage at
all. This entry closes that gap. It does **not** attempt full coverage of
the type — the UI half (`OnOpen`, `UnlockCheats`, `UpdatePreventUse`,
`ShowUnlockCheats`, `Refill`) is still `[OPEN]` and is left for ordinary
Step 2.

Filed under `12-world-scene-timewarp/` rather than `15-ui/` on the
standing "place by what the type is for" rule: despite its `SFS.UI.*`
field types, what this class *is* is the world's cheat state, and its
effects land in `Physics`, `AeroModule`, `HeatManager`, `FlowModule` and
`ColliderModule`.

---

## SandboxSettings

**Namespace:** `SFS.World`
**Kind:** class
**Extends:** `UnityEngine.MonoBehaviour` (via a UI menu base — not confirmed)
**Status:** PARTIAL
**Depth:** FULL (the toggle path) / `[OPEN]` (the UI path)
**IL:** `@154215`

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `SandboxSettings` | public | **static** | Set in `Awake()`. **This is the correct handle — see the finding below.** | CONFIRMED |
| `settings` | `SandboxSettings/Data` | public | no | The eight cheat booleans. **World-scoped: swapped by `WorldBaseManager.EnterWorld`/`ExitWorld`.** | CONFIRMED |
| `initialized` | `bool` | public | no | Gates `UpdateUI`; false on an instance whose `Start()` has not run. | CONFIRMED |
| `onToggleCheat` | `SFS.Variables.Event_Local` | public | no | Fired at the end of `OnToggle()`, null-checked. Subscribable. | CONFIRMED |
| `infiniteBuildArea`, `partClipping`, `infiniteFuel`, `infiniteOxygen`, `noAtmosphericDrag`, `unbreakableParts`, `noGravity`, `noHeatDamage`, `noBurnMarks` | `SFS.UI.ToggleButton` | public | no | The nine UI toggles. Note **nine buttons, eight `Data` flags** — see below. | CONFIRMED |
| `buyInfiniteBuildAreaButton`, `buyCheatsButton`, `preventUse_InfiniteArea`, `preventUse_Cheats`, `teleportButton`, `refillButton`, `unlockCheatsButton` | `SFS.UI.Button` | public | no | Purchase/unlock gating UI. `[OPEN]` | PARTIAL |
| `containerElement`, `settingsMenuSizer`, `fullVersionButton`, `fullVersionElements`, `settingsTransform` | various UI | public | no | Layout. `[OPEN]` | PARTIAL |

**There is an `infiniteOxygen` ToggleButton but no `infiniteOxygen` flag on
`Data` and no `ToggleInfiniteOxygen()` method.** Nine buttons, eight
toggles, eight `Data` booleans. Whatever drives that button, it is not the
`Toggle*` family. `cheat infiniteOxygen` therefore throws
`"no method ToggleInfiniteOxygen on SandboxSettings"` from the mod's own
`Invoke` helper. [OPEN — what wires that button is not established]

### Methods

#### Awake() -> void

- **Access:** private instance (Unity message)
- **Preconditions:** None beyond a valid instance.
- **Behavior:** `main = this`. Nothing else — no null check, no
  destroy-on-duplicate.
- **Status:** CONFIRMED

#### ToggleInfiniteFuel() / TogglePartClipping() / ToggleInfiniteBuildArea() / ToggleNoAtmosphericDrag() / ToggleUnbreakableParts() / ToggleNoGravity() / ToggleNoHeatDamage() / ToggleNoBurnMarks() -> void

- **Access:** **private** instance, all eight. Reachable only with
  `BindingFlags.NonPublic` — `sfsprobe`'s `Invoke` helper does pass it.
- **Preconditions:** **A loaded world.** Every one of these ends in
  `OnToggle()`, which dereferences `SFS.Base.worldBase.paths` and
  `SFS.Base.worldBase.settings` with **no null check** — outside a loaded
  world this NREs. `settings` must be non-null (it is created lazily in
  `Start()` if still null, and replaced on world entry/exit). For the
  toggle to have any gameplay effect, `this` must be the **live** instance,
  i.e. `SandboxSettings.main`, not an arbitrary one.
- **Behavior:** identical shape in all eight — flip the corresponding
  `settings.<flag>` boolean, then call `OnToggle()`. Confirmed from
  `ToggleInfiniteFuel` (`@154732`); the other seven are the same nineteen
  instructions against a different field.
- **Side effects:** everything `OnToggle()` does, below — **including an
  immediate write to disk.**
- **Gotchas:**
  - These are *toggles*, not setters. There is no "set infiniteFuel = true"
    entry point; calling one twice is a no-op with two disk writes.
  - **`ToggleInfiniteOxygen` does not exist** (see above).
- **Status:** CONFIRMED

#### OnToggle() -> void

- **Access:** private instance
- **Preconditions:** **`SFS.Base.worldBase`, `.paths` and `.settings` must
  all be non-null — a loaded world.** Unconditional dereference on the
  first two instructions. `BuildManager.main` and `onToggleCheat` are both
  null-checked and need not exist.
- **Behavior:**
  ```
  Base.worldBase.paths.SaveWorldSettings(Base.worldBase.settings);
  UpdateUI(false);
  if (BuildManager.main != null)
      BuildManager.main.buildGridSize.UpdateBuildSpaceSize();
  onToggleCheat?.Invoke();
  ```
- **Side effects:** **writes the world settings file to disk, immediately
  and unconditionally, on every single toggle.** This is not an in-memory
  flag flip.
- **Status:** CONFIRMED

#### UpdateUI(bool instantAnimation) -> void

- **Access:** public instance
- **Preconditions:** None — it early-returns when `initialized` is false,
  so it is safe on a prefab or a not-yet-started instance. Past that gate
  it dereferences the nine `ToggleButton` fields without null checks.
- **Behavior:** forwards `instantAnimation` to `ToggleButton.UpdateUI(bool)`
  on each toggle button.
- **Status:** CONFIRMED

#### Start() / OnOpen() / UnlockCheats() / Refill() / UpdatePreventUse() / ShowUnlockCheats() -> void

- **Preconditions:** **Not established — bodies `[OPEN]`.** `Start()` was
  read only far enough to confirm it lazily creates `settings` when null
  (`@154261`) and wires the eight `Toggle*` methods to their buttons.
- **Status:** OPEN — the UI/purchase-gating half of this class is out of
  scope for Step 1.5 and is left for ordinary Step 2 coverage. **`Refill()`
  in particular is a state-mutating method that nothing has read**; do not
  build a command on it before it is read.

---

## SandboxSettings/Data

**Namespace:** `SFS.World`
**Kind:** class (nested)
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@155121`

Eight booleans and a default constructor. This *is* the cheat state.

| Name | Type | Access | Description | Status |
|---|---|---|---|---|
| `infiniteFuel` | `bool` | public | | CONFIRMED |
| `noAtmosphericDrag` | `bool` | public | | CONFIRMED |
| `unbreakableParts` | `bool` | public | | CONFIRMED |
| `noGravity` | `bool` | public | | CONFIRMED |
| `noHeatDamage` | `bool` | public | | CONFIRMED |
| `noBurnMarks` | `bool` | public | | CONFIRMED |
| `infiniteBuildArea` | `bool` | public | Editor-only. | CONFIRMED |
| `partClipping` | `bool` | public | Editor-only. | CONFIRMED |

#### .ctor()

- **Preconditions:** None beyond valid arguments.
- **Behavior:** all eight default to `false`.
- **Status:** CONFIRMED

### Where each cheat actually lands

Complete IL cross-reference. This is the useful part: it says exactly which
simulation paths each flag changes, which is what an agent needs in order to
know whether a run is still physically meaningful.

| Flag | Read by |
|---|---|
| `infiniteFuel` | `FlowModule.UpdateState`, `FlowModule.FlowNegative`, `BoosterModule.CanUseBooster`, `BoosterModule.FixedUpdate`, `EVA_Resources.ConsumeFuel`, `Astronaut_EVA.OnFixedUpdate`, `CheatsDrawer.UpdateText` |
| `noGravity` | **`Physics.FixedUpdate`**, `Water_Rocket.FixedUpdate`, `CheatsDrawer.UpdateText` |
| `noAtmosphericDrag` | **`AeroModule.FixedUpdate`**, `CheatsDrawer.UpdateText` |
| `unbreakableParts` | `ColliderModule.OnCollisionEnter2D`, `Water_Rocket.FixedUpdate`, `Astronaut_EVA.OnFixedUpdate`, `CheatsDrawer.UpdateText` |
| `noHeatDamage` | `HeatManager.ApplyHeat`, `HeatManager.HeatPart`, `CheatsDrawer.UpdateText` |
| `noBurnMarks` | `AeroModule.FixedUpdate_Reentry_And_Heating`, `CheatsDrawer.UpdateText` |
| `infiniteBuildArea` | `BuildCamera.get_MaxCameraDistance` / `.set_CameraPosition` / `.LateUpdate`, `BuildGrid.ClampToLimits`, `BuildMenus.Rotate`, `GridSize.GetOwnedGridSize` / `.OnSizeChange` / `.InsideGrid` / `.Update` |
| `partClipping` | `BuildGrid.ApplyOrientationChange_BuildGrid`, `BuildGrid.AddParts`, `HoldGrid.EndHold`, `HoldGrid.GetSnapPosition` |

Notes that follow directly from the table:

- **`infiniteFuel` does not refill anything.** It is read inside
  `FlowModule.FlowNegative`, which — per
  [`resources-and-flow.md`](../09-resources-fuel/resources-and-flow.md) —
  **skips consumption entirely**, so mass never drops and the vehicle flies
  differently, not merely longer. Already in `../CORRECTIONS.md`; this is
  the cross-reference that shows where the flag enters.
- **`noGravity` and `noAtmosphericDrag` are read in `FixedUpdate`**, i.e.
  every physics tick, in `Physics` and `AeroModule` respectively. Toggling
  either mid-flight changes the simulation from the very next tick, with no
  transition.
- `infiniteBuildArea` and `partClipping` are read **only** by editor types.
  They are inert in `World_PC`.
- The `Data` object itself is constructed in `CreateWorldMenu.CreateWorld`,
  `WorldBaseManager.EnterWorld`, `WorldBaseManager.ExitWorld`,
  `WorldReference.LoadWorldSettings` and `SandboxSettings.Start` —
  which is what makes it world-scoped rather than global.

---

## Findings — Step 1.5, `sfsprobe`'s `cheat` command

Documentation of the gap, per the plan's instruction to flag rather than
fix. **None of this is a mod-code change made here.**

1. **`FindComponent` is the wrong handle; `SandboxSettings.main` is the
   right one.** `sfsprobe` resolves the instance with
   `Resources.FindObjectsOfTypeAll(t)` and takes `[0]`.
   `FindObjectsOfTypeAll` returns inactive objects and assets, including
   prefabs, and the ordering is not specified. `Awake()` publishes the live
   instance as the **public static `main`** field. If `[0]` is not the live
   component, the toggle flips a detached `Data` — and because
   `OnToggle()`'s disk write targets the global
   `Base.worldBase.settings` rather than `this.settings`, the command still
   **writes the settings file and still reports `"toggled X"`**, while
   changing nothing about the simulation. A silent-success failure mode.
   Five-minute fix: read the static `main` field instead.

2. **`cheat` writes to disk on every invocation.** `OnToggle()` calls
   `SaveWorldSettings` unconditionally. Nothing in the mod's `case "cheat"`
   or its one-line comment indicates this. It is not destructive, but it is
   an on-disk side effect on a command that reads as an in-memory flag flip.

3. **`cheat` requires a loaded world and has no scene gate.**
   `OnToggle()` dereferences `Base.worldBase.paths` with no null check.
   Unlike `loadblueprint`/`loadblueprintbuild`, `case "cheat"` performs no
   scene check, so calling it from the main menu throws out of
   `Invoke` into the command handler. Same class of gap as the
   `World_PC`/`Build_PC` incident, one layer down.

4. **`arg` is interpolated into a method name unvalidated.**
   `"Toggle" + arg` with `arg = a[1]` verbatim — case-sensitive, and not
   lowercased the way `cmd` is. `cheat infinitefuel` throws
   `"no method ToggleInfinitefuel"`; only `cheat InfiniteFuel` works.
   `cheat InfiniteOxygen` can never work — that method does not exist.

5. **`Refill()` exists, is state-mutating, and has never been read.** It is
   not currently wired to any command. Per the plan's HARD RULE it must not
   be, until its body is read.

## Open

- `Start`, `OnOpen`, `UnlockCheats`, `UpdatePreventUse`, `ShowUnlockCheats`,
  `Refill` bodies. [OPEN]
- What drives the `infiniteOxygen` ToggleButton, given there is no
  corresponding flag or `Toggle*` method. [OPEN]
- `SandboxSettings`'s actual base class — it has `OnOpen()` as
  `public virtual`, so it derives from a UI menu base that is not yet
  documented. [OPEN]
- `WorldReference.SaveWorldSettings` / `LoadWorldSettings` and the
  `WorldSettings` ↔ `SandboxSettings/Data` relationship. [OPEN]
