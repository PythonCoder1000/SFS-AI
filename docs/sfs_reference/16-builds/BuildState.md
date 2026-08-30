# BuildState — `SFS.Builds`

Written out of order, during **Phase 1 Step 1.5 (Mod-Integration Safety
Audit)**, because `sfsprobe`'s `loadblueprintbuild` command ships against
`BuildState.LoadBlueprint`. This is the **first file in `16-builds/`** and
it deliberately covers **one method** at FULL depth; the rest of the class
is signature-only, for ordinary Step 2.

`BuildState.LoadBlueprint` is the editor-side counterpart to
`RocketManager.SpawnBlueprint`
([`RocketManager.md`](../07-saveload/RocketManager.md)). They are **not**
alternatives to each other:

| | `BuildState.LoadBlueprint` | `RocketManager.SpawnBlueprint` |
|---|---|---|
| Scene | **`Build_PC`** | **`World_PC`** |
| Effect | **Replaces** the current editor design | **Adds** a live physics rocket |
| Clears first | Yes — `Clear(applyUndo)` | No |
| `WorldView.main` | Not touched | **Required** — first five instructions |
| Undo history | Integrates (`applyUndo`) | N/A |

The `World_PC`/`Build_PC` inversion between them is exactly the mixup that
prompted Step 1.5. See `../CORRECTIONS.md`.

---

## BuildState

**Namespace:** `SFS.Builds`
**Kind:** class
**Extends:** `UnityEngine.MonoBehaviour` (implied by `Awake`)
**Status:** PARTIAL
**Depth:** FULL (`LoadBlueprint`) / signature-only (everything else)
**IL:** `@94034`

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `BuildState` | public | **static** | Set in `Awake()`. The correct handle for reflection. | CONFIRMED |
| `buildCamera` | `BuildCamera` | public | no | Used by `CenterCameraOnParts`. | CONFIRMED |
| `buildMenus` | `BuildMenus` | public | no | `buildMenus.staging` is the `SFS.World.Staging` the blueprint's stages load into. | CONFIRMED |
| `buildGrid` | `BuildGrid` | public | no | `buildGrid.gridSize.centerX` is read on the non-auto-center path. | CONFIRMED |
| `selector` | `BuildSelector` | public | no | Not read by `LoadBlueprint`. | PARTIAL |

### Methods

#### LoadBlueprint(Blueprint blueprint, I_MsgLogger logger, bool autoCenterParts, bool applyUndo, [opt] Vector2 offset, [opt] Action onLoaded) -> void

- **Access:** public instance · IL `@94165`
- **Parameters:**
  - `blueprint` — **mutated in place**, see Gotchas.
  - `logger` — passed straight through to the private
    `BuildState.SpawnBlueprint(Blueprint, bool, I_MsgLogger)` and never
    called directly by this method.
  - `autoCenterParts` — `true` centres on the owned grid; `false` takes the
    `offset`/`blueprint.center` path instead.
  - `applyUndo` — forwarded to **both** `Clear` and `Staging.Load`, so it
    governs whether the wipe *and* the reload are undoable as one action.
  - `offset` — only consulted when `autoCenterParts` is false.
  - `onLoaded` — null-checked, invoked last.
- **Returns:** void.
- **Preconditions:** **`Build_PC` scene.** It dereferences `buildGrid`,
  `buildMenus.staging` and the static **`BuildOrientation.main`** with no
  null checks, and calls `GridSize.GetOwnedGridSize(true)` on the
  auto-centre path — all editor-scoped. It has **no** `WorldView`
  dependency, which is precisely why its scene requirement is the opposite
  of `RocketManager.SpawnBlueprint`'s. `blueprint.parts` and
  `blueprint.stages` must be non-null.
- **Behavior:**
  ```
  Clear(applyUndo);                                   // FIRST, unconditional
  if (blueprint.offset != Vector2.zero)
      foreach (PartSave p in blueprint.parts)
          p.position += blueprint.offset;             // mutates the blueprint
  Part[] parts = SpawnBlueprint(blueprint, applyUndo, logger).ToArray();
  if (autoCenterParts)
      Part_Utility.CenterParts(parts, GridSize.GetOwnedGridSize(true));
  else {
      offset.x += buildGrid.gridSize.centerX
                - (float.IsNaN(blueprint.center) ? 0f : blueprint.center);
      Part_Utility.OffsetPartPosition(offset, false, parts);
  }
  CenterCameraOnParts(parts);
  BuildOrientation.main.SetOrientation(blueprint.rotation, false);
  buildMenus.staging.Load(blueprint.stages, parts, applyUndo);
  onLoaded?.Invoke();
  ```
- **Side effects:** destroys the current editor design; creates parts;
  moves the build camera; sets build orientation; rewrites the staging
  list; mutates the passed-in `Blueprint`.
- **Gotchas:**
  - **`Clear(applyUndo)` runs first and unconditionally, before the
    blueprint is validated in any way.** If `SpawnBlueprint` throws on a
    malformed blueprint, the editor is left **empty**, not unchanged. There
    is no rollback. Any caller must treat this as destructive from its
    first instruction.
  - **The offset loop mutates `blueprint.parts[i].position` in place.**
    Calling `LoadBlueprint` twice with the same in-memory `Blueprint`
    applies `blueprint.offset` twice. Safe in `sfsprobe` today only because
    it deserializes a fresh `Blueprint` per invocation.
  - `blueprint.center` is explicitly `NaN`-guarded on the non-auto-centre
    path — `NaN` is treated as `0f`. `blueprint.rotation` is **not**
    guarded before `SetOrientation`.
  - `logger` is never used by this method itself, so passing `null` only
    matters if the private `SpawnBlueprint` dereferences it — **not
    established.** `sfsprobe` passes `SFS.UI.MsgDrawer`, which is the safe
    choice.
- **Status:** CONFIRMED (body read `@94165`–`@94284`)

#### SpawnBlueprint(Blueprint blueprint, bool applyUndo, I_MsgLogger logger) -> Part[]

- **Access:** **private** instance · IL `@94284`
- **Preconditions:** **Not established — body `[OPEN]`.** Reached only via
  `LoadBlueprint`, so its preconditions apply transitively. Whether it
  dereferences `logger` is the open question that decides if a null logger
  is safe.
- **Status:** OPEN. Note the name collision with the unrelated public
  static `SFS.World.RocketManager.SpawnBlueprint` — different type,
  different scene, different effect.

#### Clear(bool applyUndo) -> void

- **Access:** public instance · IL `@94468`
- **Preconditions:** **Not established — body `[OPEN]`.** Two local
  functions hang off it (`<Clear>g__ClearCrew|13_0(PartHolder)` `@94535`
  and `<Clear>g__Record|13_1(PartGrid, bool)` `@94592`), so it touches crew
  and the part grid as well as parts.
- **Status:** OPEN — **and it is destructive.** Per the plan's HARD RULE,
  do not wire a command directly to it until the body is read.

#### GetBlueprint([opt] bool forceVertical) -> Blueprint

- **Access:** public instance · IL `@94089`
- **Preconditions:** Not established — body `[OPEN]`. Almost certainly
  `Build_PC`, by symmetry with `LoadBlueprint`.
- **Status:** OPEN. This is the obvious *read* counterpart to
  `LoadBlueprint` — the natural way to dump the current editor design — and
  is the highest-value next read in this class.

#### UpdatePersistent_NoCache() / UpdatePersistent([opt] bool forceVertical) / LoadPersistent() / CenterCameraOnParts(Part[] parts) / Awake() / .ctor()

- **Preconditions:** Not established — bodies `[OPEN]`, except `Awake()`,
  which by the pattern of every other `main`-holding type sets
  `main = this`. **Not read; stated as inference, not fact.**
- **Status:** OPEN — ordinary Step 2 work.

---

## Findings — Step 1.5, `sfsprobe`'s `loadblueprintbuild` command

Documentation of the gap, per the plan's instruction to flag rather than
fix. **No mod-code change made here.**

1. **The command is correct on the point that caused the incident.** It
   gates on `Build_PC`, resolves `SFS.Builds.BuildState` via
   `FindComponent`, and passes `autoCenterParts=true, applyUndo=true,
   offset=Vector2.zero, onLoaded=null` — which matches what the real UI
   load does. Reading the body confirms rather than corrects it.

2. **The destructiveness is understated.** The command's own comment says
   "REPLACING the current design", which is accurate, but
   `Clear(applyUndo)` runs *before* any validation, so a **failed** load
   also destroys the current design. `loadblueprintbuild: FAILED
   reason=load_exception` currently reads as "nothing happened"; it should
   read as "your design is gone." A one-line message change.

3. **`FindComponent` vs `main`, again.** Same issue as `cheat`:
   `BuildState` publishes a public static `main`, and the mod resolves the
   instance with `Resources.FindObjectsOfTypeAll(...)[0]` instead. Lower
   risk here than for `cheat` — the `Build_PC` gate means a live instance
   exists — but `main` is still the correct handle.

4. **`BuildState.Clear` is public, destructive, and unread.** Nothing wires
   a command to it today. It must not be wired until its body is read.

## Open

- Everything in this class except `LoadBlueprint`. This file is
  deliberately a Step 1.5 spot-read, not Step 2 coverage of `SFS.Builds`.
- `BuildMenus`, `BuildGrid`, `BuildCamera`, `BuildSelector`,
  `BuildOrientation`, `GridSize`, `PartGrid`, `HoldGrid`,
  `Part_Utility.CenterParts` / `.OffsetPartPosition`, and
  `SFS.World.Staging.Load(StageSave[], Part[], bool)` are all referenced
  above and none is documented. [OPEN]
