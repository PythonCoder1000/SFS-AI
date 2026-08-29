# Terrain chunks — `SFS.World.Terrain`

All seven types of the `SFS.World.Terrain` namespace, grouped into one
file because they are a single pipeline and none of them is meaningful
alone: `DynamicTerrain` + `DynamicChunk` are the **visual** binary-split
LOD tree, `Chunk` + `TerrainPoints` are the mesh it builds, and
`TerrainColliderManager` + its `Chunk` + `TerrainColliderModule` are a
**completely separate, parallel** system that builds the `PolygonCollider2D`
the craft actually lands on.

> **The single most important fact in this file:** the terrain you *see*
> and the terrain you *collide with* are built by two independent systems
> that share no geometry, no chunk indices, and no LOD scheme. The visual
> mesh comes from `DynamicTerrain`'s recursive split tree; the collider
> comes from `TerrainColliderManager`, keyed by a flat integer chunk index
> derived from the craft's angle around the planet. Both ultimately call
> `TerrainModule.GetTerrainPoints`, so they agree on heights, but they are
> sampled at different resolutions and are created and destroyed
> independently.

Both systems are pure consequences of `SFS.WorldBase.Planet` and
`SFS.World.PlanetModules.TerrainModule`; neither is a source of terrain
height data. For querying terrain height, use
`Location.GetTerrainHeight(bool)` → `Planet.GetTerrainHeightAtAngle`
(see [`Planet.md`](Planet.md)) — **not** anything in this file.

---

## TerrainColliderModule

**Namespace:** `SFS.World.Terrain`
**Kind:** class
**Extends:** `UnityEngine.MonoBehaviour`
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@204876`

The per-craft component that decides *which* collider chunks should exist
around this craft. One lives on each `Player` (rocket or astronaut) that
needs ground collision. It owns no geometry — it only computes an index
range and hands it to the singleton `TerrainColliderManager`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `player` | `SFS.World.Player` | public | no | The craft this module follows. Its `location.position` drives everything. | CONFIRMED |
| `loader` | `SFS.World.WorldLoader` | public | no | Gate — no colliders exist while `loader.Loaded` is false. | CONFIRMED |
| `chunkIndexes` | `List<int>` | private | no | The chunk indices currently requested by *this* module. Never shared; the manager reference-counts. | CONFIRMED |

### Methods

#### Start() -> void

- **Access:** private instance (Unity message)
- **Behavior:** Subscribes `UpdateChunks` to `player.location.position.OnChange`,
  and a `<Start>b__3_0(bool, bool)` thunk (which just calls `UpdateChunks`)
  to `loader.onLoadedChange_After`.
- **Gotcha:** **Collider updates are driven by the position observable, not
  by `Update`/`FixedUpdate`.** A craft whose `location.position` is not
  being written — anything on rails, or a craft you teleport by writing
  fields directly rather than through `WorldLocation` — will not get its
  collider chunks refreshed.
- **Status:** CONFIRMED

#### UpdateChunks() -> void

- **Access:** private instance
- **Behavior:** the whole algorithm, in order:
  1. If **not** (`loader.Loaded` **and**
     `position.Mag_LessThan(planet.Radius + planet.maxTerrainHeight + player.GetSizeRadius())`)
     → `Clear()` and return. This is the altitude cut-off: above
     `maxTerrainHeight` there are no colliders at all.
  2. If `planet.data.hasTerrain` is false → return **without** clearing.
  3. `center = (position.AngleRadians / 2π + 10.0) % 1.0` — the craft's
     angle around the planet normalised to `[0, 1)`. The `+ 10.0` is there
     purely to force the value positive before `%`.
  4. `halfWidth = (player.GetSizeRadius() + 5f) / planet.SurfaceArea` —
     the craft's angular half-extent, **plus a flat 5 m margin**.
  5. `chunkSize = TerrainColliderManager.GetAngularChunkSize(planet)`.
  6. `from = (int)((center - halfWidth) / chunkSize + 100.0) - 100`,
     `to = (int)((center + halfWidth) / chunkSize + 100.0) - 100`.
     The `+100 … -100` is a **floor** idiom: C#'s `double`→`int` conversion
     truncates toward zero, so biasing by 100 first makes negative indices
     floor correctly. It is only valid while `|index| < 100`.
  7. `chunkIndexes_New = [from … to]` inclusive of both ends.
  8. `remove = chunkIndexes.Where(i => !chunkIndexes_New.Contains(i))`,
     `add = chunkIndexes_New.Where(i => !chunkIndexes.Contains(i))` —
     both confirmed from `<>c__DisplayClass5_0::<UpdateChunks>b__0` / `b__1`.
  9. `chunkIndexes = chunkIndexes_New`, then
     `TerrainColliderManager.main.RemoveChunks(remove, this)` and
     `AddChunks(add, this)`.
- **Side effects:** creates/destroys `GameObject`s (via the manager),
  writes `TerrainColliderManager.main.hasColliders`.
- **Gotchas:**
  - Step 2 returns **without clearing**, unlike step 1. A craft that moves
    to a planet with `hasTerrain == false` keeps whatever collider chunks
    it last requested until it either leaves the altitude band or is destroyed.
  - The chunk index is **not planet-qualified** — see the gotcha on
    `TerrainColliderManager.chunks` below.
  - `AngleRadians` is a `Double2` property; the index therefore depends on
    `Double2`'s `Atan2(y, x)` convention (see [`Location.md`](../01-core-flight/Location.md)).
- **Status:** CONFIRMED

#### Clear() -> void

- **Access:** private instance
- **Behavior:** If `chunkIndexes.Count == 0`, returns immediately.
  Otherwise `TerrainColliderManager.main.RemoveChunks(chunkIndexes, this)`
  then `chunkIndexes.Clear()`.
- **Status:** CONFIRMED

#### OnDestroy() -> void

- **Access:** private instance (Unity message)
- **Behavior:** calls `Clear()`. This is the only thing that releases a
  destroyed craft's collider chunks.
- **Status:** CONFIRMED

---

## TerrainColliderManager

**Namespace:** `SFS.World.Terrain`
**Kind:** class
**Extends:** `UnityEngine.MonoBehaviour`
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@204449`

The world-scene singleton that owns every terrain collider. Reference-counted
by owning `TerrainColliderModule`, keyed by integer chunk index.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `TerrainColliderManager` | public | **static** | Set in `Awake()`, with no null-check and no destroy-on-duplicate. The reflection entry point. | CONFIRMED |
| `chunks` | `Dictionary<int, Chunk>` | private | no | Live collider chunks by index. **The key carries no planet identity.** | CONFIRMED |
| `hasColliders` | `SFS.Variables.Bool_Local` | public | no | Observable — true while `chunks.Count > 0`. Subscribable. | CONFIRMED |
| `VerticesPerChunk` | `int32` | private | **static literal** | `10`. A compile-time constant; call sites see the inlined literal, so changing the field by reflection does nothing. | CONFIRMED |

### Methods

#### Awake() -> void

- **Access:** private instance
- **Behavior:** `main = this`. Nothing else. Last one loaded wins.
- **Status:** CONFIRMED

#### AddChunks(List&lt;int&gt; indexes, TerrainColliderModule owner) -> void

- **Access:** public instance
- **Behavior:** For each index: if `chunks` does not already contain it,
  construct `new Chunk(chunkSize * index, chunkSize, planet, transform)`
  where `planet = owner.player.location.planet.Value` and
  `chunkSize = GetAngularChunkSize(planet)`, and store it. Then, in all
  cases, `chunks[index].owners.Add(owner)`.
  Finally, if `chunks.Count > 0`, set `hasColliders.Value = true`.
- **Gotchas:**
  - **The planet is taken from the *owner*, but the dictionary key is a bare
    `int`.** The first module to request index *N* fixes that chunk's
    geometry to *its* planet; a second craft on a different planet
    requesting the same index gets the first planet's collider, silently.
    Nothing in the code namespaces the key by planet.
  - `owners` is a `List`, not a set — the same owner added twice is counted
    twice, and `RemoveChunks` removes only one occurrence per call.
- **Status:** CONFIRMED

#### RemoveChunks(List&lt;int&gt; indexes, TerrainColliderModule owner) -> void

- **Access:** public instance
- **Behavior:** For each index: if `chunks` lacks it, `Debug.LogError("Couldn't remove chunk: " + index)` and continue. Otherwise remove `owner` from
  `chunks[index].owners`; if the owner list is now empty, call
  `chunks[index].Destroy()` and remove the dictionary entry.
  Finally, if `chunks.Count == 0`, set `hasColliders.Value = false`.
- **Side effects:** `Debug.LogError` — visible in `ErrorLogger.lastLogs`
  (see [`ErrorLogger.md`](../13-challenges-logging/ErrorLogger.md)).
- **Status:** CONFIRMED

#### GetAngularChunkSize(Planet planet) -> float64

- **Access:** **public static** — directly callable, no instance needed
- **Returns:** the angular width of one collider chunk, in the same
  normalised `[0, 1)` = one full revolution units `UpdateChunks` uses.
- **Behavior:**
  ```
  double s = planet.data.terrain.GetChunkSize_Angular(8, planet.GetMaxLOD());
  int    v = planet.GetVerticeCount(s, planet.data.terrain.verticeSize);
  return s / (v - 1) * 10.0;
  ```
  The literal `8` is `DynamicTerrain.BaseChunkCount`; the trailing `10.0` is
  `VerticesPerChunk`, inlined by the compiler.
- **Gotcha:** this couples the **collider** grid to the **visual** system's
  base chunk count and max LOD, even though the two systems otherwise share
  nothing. Changing `verticeSize` or `GetMaxLOD` moves collider boundaries.
- **Status:** CONFIRMED

---

## TerrainColliderManager/Chunk

**Namespace:** `SFS.World.Terrain`
**Kind:** class (nested in `TerrainColliderManager`)
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@204688`

One collider chunk: a `GameObject` named `"Collider"` carrying a single
`PolygonCollider2D`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `owners` | `List<TerrainColliderModule>` | public | no | Reference count. Chunk is destroyed when this empties. | CONFIRMED |
| `gameObject` | `UnityEngine.GameObject` | private | no | The `"Collider"` object. | CONFIRMED |
| `position` | `Double2` | private | no | World position, written by `GetTerrainPoints`'s `out` parameter. | CONFIRMED |

### Methods

#### .ctor(float64 from, float64 size, Planet planet, Transform holder)

- **Behavior:** creates `new GameObject("Collider")`, parents it to `holder`
  with `worldPositionStays = false`, copies `holder`'s layer. Then, **only if
  `planet.data.hasTerrain && planet.data.terrain.collider`**:
  `planet.data.terrain.GetTerrainPoints(from, size, 11, true, true, planet, out position, out _, out _)`
  and assigns the resulting `points` (projected `Vector3 → Vector2`) to a
  newly-added `PolygonCollider2D`. Finally subscribes `Position` to
  `WorldView.main.positionOffset.OnChange`.
- **Gotchas:**
  - The point count is the hardcoded literal `11` — `VerticesPerChunk + 1`.
  - **If `terrain.collider` is false the chunk still exists and is still
    reference-counted, but has no collider component at all.** It is an empty
    `GameObject`, and `hasColliders` still reports true.
  - Because it subscribes to `WorldView.main.positionOffset`, colliders
    follow the floating origin — see [`WorldView.md`](../12-world-scene-timewarp/WorldView.md).
- **Status:** CONFIRMED

#### Position() -> void

- **Behavior:** `gameObject.transform.position = WorldView.ToLocalPosition(position)`.
- **Status:** CONFIRMED

#### Destroy() -> void

- **Behavior:** unsubscribes `Position` from `WorldView.main.positionOffset.OnChange`
  and destroys the `GameObject`.
- **Status:** CONFIRMED

---

## DynamicTerrain

**Namespace:** `SFS.World.Terrain`
**Kind:** class
**Extends:** `UnityEngine.MonoBehaviour`
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@202156`

The **visual** terrain: a binary-split LOD tree of 8 root chunks covering
one revolution. Purely cosmetic — nothing here participates in collision,
drag, or terrain-height queries.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `BaseChunkCount` | `int32` | private | **static literal** | `8`. Compile-time constant, inlined at call sites. | CONFIRMED |
| `chunkPrefab` | `Transform` | public | no | Prefab each `Chunk` instantiates. | CONFIRMED |
| `rockData` | `TerrainModule/RockData` | public | no | Surface-rock scatter settings, consumed by `DynamicChunk.GenerateRocks`. | CONFIRMED |
| `rockPrefab` | `Transform` | public | no | Rock prefab. | CONFIRMED |
| `material` | `ValueTuple<Material, Material>` | public | no | (terrain, water) materials. | CONFIRMED |
| `useTerrainUV` | `bool` | public | no | Passed through to `Chunk`. | CONFIRMED |
| `verticeSizeMultiplier` | `float32` | private | no | Scales `TerrainModule.GetVerticeSize` — higher = coarser mesh. | CONFIRMED |
| `loadDistanceMultiplier` | `float32` | private | no | Scales `TerrainModule.GetLoadDistance` — the split/merge hysteresis distance. | CONFIRMED |
| `setupChunk` | `Action<DynamicChunk>` | private | no | Optional per-chunk callback, invoked in the `DynamicChunk` ctor if non-null. | CONFIRMED |
| `planet` | `SFS.WorldBase.Planet` | private | no | | CONFIRMED |
| `position` | `Double3` | private | no | The **view** position. `z` is a distance/zoom axis, not a third spatial coordinate. | CONFIRMED |
| `distanceMoved` | `float64` | private | no | Monotonically increasing odometer. Split/merge thresholds are stored as absolute values of this, never reset. | CONFIRMED |
| `layer` | `int32` | private | no | Unity layer applied to every active chunk. | CONFIRMED |
| `allChunks` | `List<DynamicChunk>` | private | no | Every node in the tree, active or not. | CONFIRMED |
| `activeChunks` | `List<DynamicChunk>` | private | no | Currently visible leaves. | CONFIRMED |
| `bestSplit` | `DynamicChunk` | private | no | Cached `argmin(updateSplit)` over `activeChunks`. | CONFIRMED |
| `bestMerge` | `DynamicChunk` | private | no | Cached `argmin(updateMerge)`, filtered by `CanMerge()` — **except the seed**. | CONFIRMED |

### Methods

#### Create(Planet, Double3 position, Action&lt;DynamicChunk&gt; setupChunk, float32 verticeSizeMultiplier, float32 loadDistanceMultiplier, string layer, ValueTuple&lt;Material,Material&gt; material, bool useTerrainUV, Transform chunkPrefab, TerrainModule/RockData rockData, Transform rockPrefab) -> DynamicTerrain

- **Access:** **public static** — the only construction path
- **Behavior:** creates `new GameObject(planet.codeName + " Dynamic Terrain")`,
  `AddComponent<DynamicTerrain>()`, assigns every field, resolves `layer`
  through `LayerMask.NameToLayer`, then **divides `position.z` by 3** and calls
  `Initialized(planet, position)`.
- **Gotcha:** `position.z` is divided by 3 here **and** halved again inside
  `Initialized`, so the initial view `z` is the caller's value **÷ 6**.
  Later `SetViewPosition` calls only divide by 3. The initial LOD state is
  therefore biased toward finer detail than any subsequent update at the
  same nominal `z`.
- **Status:** CONFIRMED

#### Initialized(Planet planet, Double3 position) -> void

- **Access:** private instance
- **Behavior:** `position.z *= 0.5`; stores `planet` and `position`;
  sets `distanceMoved = 1.0`; constructs 8 root chunks
  `new DynamicChunk(this, null, i / 8.0, 0)` for `i` in `0..7`; calls `LoadFully()`.
- **Status:** CONFIRMED

#### LoadFully() -> void

- **Access:** public instance
- **Behavior:** loops exactly **500** times; each iteration takes
  `GetBestSplit()` and, if `distanceMoved > chunk.updateSplit`, calls
  `TrySplit` then `CalculateBest()`.
- **Gotcha:** **there is no early exit.** Unlike `Update`, this runs the full
  500 iterations and calls `GetBestSplit()` every time even after the tree
  has converged. It is a synchronous, unbounded-cost call — do not invoke it
  from a per-frame path.
- **Status:** CONFIRMED

#### Update() -> void

- **Access:** private instance (Unity message)
- **Behavior:** loops at most **20** times per frame. Each iteration:
  if `distanceMoved > GetBestSplit().updateSplit` → `TrySplit`, `CalculateBest`,
  continue; else if `distanceMoved > GetBestMerge().updateMerge` → `TryMerge`,
  `CalculateBest`, continue; **else return**.
- **Note:** split is strictly prioritised over merge, and the loop terminates
  the moment neither applies — the opposite of `LoadFully`'s behaviour.
- **Status:** CONFIRMED

#### SetViewPosition(Double3 newPosition) -> void

- **Access:** public instance
- **Behavior:** `newPosition.z /= 3.0`;
  `distanceMoved += (position - newPosition).magnitude`; `position = newPosition`.
- **Gotcha:** `distanceMoved` accumulates **path length**, not displacement.
  Moving away and back does not restore the previous LOD thresholds — it
  advances the odometer past both. The stored `updateSplit`/`updateMerge`
  values are absolute points on that odometer.
- **Status:** CONFIRMED

#### SetLayer(string layer) -> void

- **Access:** public instance
- **Behavior:** `this.layer = LayerMask.NameToLayer(layer)`, then
  `SetLayer(layer)` on every chunk in `activeChunks`.
- **Gotcha:** only **active** chunks are updated. Chunks re-enabled later
  pick up the new layer through `EnableChunk`, but chunks in `allChunks`
  that are inactive right now are not touched.
- **Status:** CONFIRMED

#### GetBestSplit() -> DynamicChunk / GetBestMerge() -> DynamicChunk

- **Access:** private instance
- **Behavior:** returns the cached `bestSplit` / `bestMerge`, first calling
  `CalculateBest()` if the cache is null **or** the cached chunk's
  `chunk.terrainTransform` compares equal to `null` under
  `UnityEngine.Object.op_Equality` (i.e. has been destroyed).
- **Status:** CONFIRMED

#### CalculateBest() -> void

- **Access:** private instance
- **Behavior:** `bestSplit` = the element of `activeChunks` with the smallest
  `updateSplit`, seeded from `activeChunks[0]`. `bestMerge` = likewise for
  `updateMerge`, but candidates must also satisfy `CanMerge()` — **again
  seeded from the unfiltered `activeChunks[0]`**.
- **Gotchas:**
  - **Throws `ArgumentOutOfRangeException` if `activeChunks` is empty** —
    both scans index `[0]` before looping. In normal operation the 8 root
    chunks guarantee non-empty.
  - Because the merge seed skips the `CanMerge()` filter, `bestMerge` can
    be a chunk that cannot merge. `TryMerge` re-checks `CanMerge()` and
    returns false, so the result is a wasted `Update` iteration, not a bug.
- **Status:** CONFIRMED

#### OnDestroy() -> void

- **Behavior:** `foreach (var c in allChunks.ToArray()) c.DestroyChunk();`
  The `ToArray()` copy is required because `DestroyChunk` mutates `allChunks`.
- **Status:** CONFIRMED

---

## DynamicTerrain/DynamicChunk

**Namespace:** `SFS.World.Terrain`
**Kind:** class (nested in `DynamicTerrain`)
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@202665`

One node of the LOD tree. A node is either a visible leaf (in `activeChunks`)
or a disabled interior node whose two halves are visible.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `owner` | `DynamicTerrain` | private | no | | CONFIRMED |
| `parentChunk` | `DynamicChunk` | private | no | Null for the 8 roots — which is why roots can never merge. | CONFIRMED |
| `otherHalf` | `DynamicChunk` | private | no | Set **only on the first half** by `Split`. The second half's `otherHalf` stays null. | CONFIRMED |
| `chunk` | `Chunk` | public | no | The mesh. | CONFIRMED |
| `topSizeHalf` | `float64` | private | no | Half the chunk's arc length at `Radius + maxTerrainHeight`. | CONFIRMED |
| `topPosition` | `Double2` | private | no | World position of the chunk's angular midpoint, at `Radius + maxTerrainHeight`. | CONFIRMED |
| `from` | `float64` | private | no | Chunk start, in normalised `[0, 1)` revolutions. | CONFIRMED |
| `LOD` | `int32` | private | no | Subdivision depth; roots are 0. | CONFIRMED |
| `updateSplit` | `float64` | **public** | no | The `owner.distanceMoved` value past which this chunk should be re-tested for splitting. `+∞` when it may never split again. | CONFIRMED |
| `updateMerge` | `float64` | **public** | no | Same, for merging. Initialised to `+∞` for the roots (`parentChunk == null`). | CONFIRMED |
| `rocks` | `List<Transform>` | private | no | Scatter instances, registered in `RockSelector.main.rockInstances`. | CONFIRMED |

### Methods

#### .ctor(DynamicTerrain owner, DynamicChunk parentChunk, float64 from, int32 LOD)

- **Behavior:** if `parentChunk == null`, `updateMerge = +∞`. Stores the four
  arguments. Then:
  ```
  topSizeHalf  = terrain.GetChunkSize_Angular(8, LOD) * (Radius + maxTerrainHeight) * π
  topPosition  = Double2.CosSin(from + chunkSize/2 * 2π, Radius + maxTerrainHeight)
  chunk        = new Chunk(chunkPrefab, from, chunkSize,
                           planet.GetVerticeCount(chunkSize,
                               terrain.GetVerticeSize(LOD, GetMaxLOD()) * verticeSizeMultiplier),
                           planet, material, useTerrainUV, transform, true)
  chunk.terrainTransform.name = "Chunk - LOD: " + LOD
  setupChunk?.Invoke(this)
  GenerateRocks()
  owner.allChunks.Add(this)
  EnableChunk()
  ```
- **Side effects:** the constructor **registers itself and turns itself on.**
  Constructing a `DynamicChunk` is not a pure allocation.
- **Status:** CONFIRMED

#### GetDistanceToViewPosition(DynamicTerrain loader) -> float64

- **Access:** public instance
- **Returns:** the LOD metric — distance from the view position to this
  chunk's arc, in metres, **minus** a proportional slice of the chunk's own
  half-size.
- **Behavior:**
  ```
  t = clamp(Math_Utility.GetClosestPointOnLine(Double2.zero, topPosition, (Double2)loader.position), 0, 1)
  return ((Double3)topPosition * t - loader.position).magnitude - topSizeHalf * t
  ```
  `t` is the normalised projection of the view position onto the ray from the
  planet centre out to the chunk. The `topSizeHalf * t` subtraction shrinks
  the effective chunk radius as the viewer approaches the planet centre.
- **Note:** `loader.position.z` participates in the `Double3` magnitude, so
  camera zoom directly drives LOD — this is the "distance" that `/3` scaling
  in `SetViewPosition` is calibrated against.
- **Status:** CONFIRMED

#### TrySplit(DynamicTerrain loader) -> bool

- **Access:** public instance
- **Behavior:**
  ```
  d = GetDistanceToViewPosition(loader)
      - terrain.GetLoadDistance(LOD, GetMaxLOD()) * loader.loadDistanceMultiplier
  if (d < 0) {
      Split(out firstHalf, out secondHalf);
      if (LOD + 1 == GetMaxLOD()) { firstHalf.updateSplit = +∞; secondHalf.updateSplit = +∞; }
      secondHalf.updateMerge = +∞;
      return true;
  }
  updateSplit = loader.distanceMoved + d;   // re-test after moving d further
  return false;
  ```
- **Gotchas:**
  - **Only `secondHalf.updateMerge` is set to `+∞`**, matching `Split`'s
    asymmetric wiring (only `firstHalf.otherHalf` is set). Merging is always
    driven from the first half.
  - At max LOD, `updateSplit = +∞` is set on the *children*, not on this
    chunk — so a chunk at `GetMaxLOD() - 1` is still re-tested forever.
  - The `+∞` used is the raw IL constant `00 00 00 00 00 00 f0 7f` =
    `double.PositiveInfinity`. Comparisons use `ble.un` (unordered), so a
    `NaN` in `distanceMoved` would make every test fall through to the
    "no action" branch rather than throwing.
- **Status:** CONFIRMED

#### TryMerge(DynamicTerrain loader) -> bool

- **Access:** public instance
- **Behavior:**
  ```
  if (!CanMerge()) return false;
  d = parentChunk.GetDistanceToViewPosition(loader)
      - terrain.GetLoadDistance(LOD - 1, GetMaxLOD()) * loader.loadDistanceMultiplier
  if (d > 0) { Merge(); return true; }
  updateMerge = loader.distanceMoved - d;   // note: minus, because d <= 0
  return false;
  ```
- **Note:** the hysteresis is genuine — split tests this chunk's distance
  against `GetLoadDistance(LOD)`, merge tests the **parent's** distance
  against `GetLoadDistance(LOD - 1)`.
- **Status:** CONFIRMED

#### CanMerge() -> bool

- **Behavior:** `otherHalf != null && otherHalf.chunk != null && otherHalf.chunk.terrainTransform.gameObject.activeSelf`.
- **Consequence:** false for the 8 roots (no `otherHalf`), false for every
  second half (its `otherHalf` is never set), and false while the sibling is
  itself split. Merging is therefore always initiated by a first half whose
  sibling is a visible leaf.
- **Status:** CONFIRMED

#### Split([out] DynamicChunk firstHalf, [out] DynamicChunk secondHalf) -> void

- **Access:** public virtual
- **Behavior:** `DisableChunk()`; then
  `firstHalf  = new DynamicChunk(owner, this, from, LOD + 1)` and
  `secondHalf = new DynamicChunk(owner, this, from + terrain.GetChunkSize_Angular(8, LOD + 1), LOD + 1)`;
  then `firstHalf.otherHalf = secondHalf`.
- **Gotcha:** **`secondHalf.otherHalf` is left null** — deliberately, per
  `CanMerge` above, but it means `otherHalf` is not a symmetric sibling link.
- **Status:** CONFIRMED

#### Merge() -> void

- **Behavior:** `DestroyChunk(); otherHalf.DestroyChunk(); parentChunk.EnableChunk();`
- **Status:** CONFIRMED

#### EnableChunk() / DisableChunk() -> void

- **Behavior:** add/remove `this` in `owner.activeChunks`, `SetActive(true/false)`
  on `chunk.terrainTransform.gameObject`, and add/remove every rock in `rocks`
  from `RockSelector.main.rockInstances`. `EnableChunk` also re-applies
  `owner.layer` via `SetLayer`.
- **Gotcha:** both dereference `RockSelector.main` unconditionally.
- **Status:** CONFIRMED

#### DestroyChunk() -> void

- **Behavior:** removes `this` from both `allChunks` and `activeChunks`;
  `Object.Destroy(chunk.terrainTransform.gameObject)`;
  `Object.DestroyImmediate` on `chunk.terrainMesh` **and** `chunk.waterMesh`;
  removes every rock from `RockSelector.main.rockInstances`.
- **Note:** the meshes use `DestroyImmediate` while the GameObject uses
  `Destroy` — meshes are not owned by the object graph and would otherwise leak.
- **Status:** CONFIRMED

#### SetLayer(int32 layer) -> void

- **Behavior:** sets the terrain object's layer; also handles the water
  transform when `planet.data.hasWater`.
- **Status:** PARTIAL — water branch read only to the `hasWater` test.

---

## Chunk

**Namespace:** `SFS.World.Terrain`
**Kind:** class
**Status:** PARTIAL
**Depth:** FULL
**IL:** `@203712`

The mesh pair for one angular slice — terrain and, optionally, water.
Used by `DynamicChunk`; **not** used by the collider system, which builds
its `PolygonCollider2D` points directly from `TerrainModule.GetTerrainPoints`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `terrainTransform` | `Transform` | public | no | Doubles as the liveness flag — `DynamicTerrain` null-checks it to detect destroyed chunks. | CONFIRMED |
| `waterTransform` | `Transform` | public | no | Only meaningful when `planet.data.hasWater`. | CONFIRMED |
| `terrainMesh` | `Mesh` | public | no | Explicitly `DestroyImmediate`d by `DynamicChunk.DestroyChunk`. | CONFIRMED |
| `waterMesh` | `Mesh` | public | no | Likewise. | CONFIRMED |

### Methods

#### .ctor(Transform chunkPrefab, float64 from, float64 size, int32 pointCount, Planet planet, ValueTuple&lt;Material,Material&gt; material, bool useTerrainUV, Transform parent, bool offsetTerrain)

- **Status:** **PARTIAL — body not read in full.** It is ~590 lines of IL
  (`@203721`–`@204310`) doing mesh construction: instantiating `chunkPrefab`,
  calling `TerrainModule.GetTerrainPoints`, and building the terrain and
  water meshes via `CreateMesh`. No simulation logic was identified in the
  parts read. Flagged rather than guessed.

#### CreateMesh(Transform, Vector3[] points, int32[] indices, string sortingLayer, int32 sortingOrder, Material) -> Mesh

- **Access:** private **static**
- **Status:** PARTIAL — signature confirmed, body not read (pure Unity mesh setup).

#### GetIndices(int32 length) -> int32[]

- **Access:** private instance
- **Behavior:** builds a triangle fan from vertex 0:
  for `i` in `0 .. length-3`, emits `(0, i+2, i+1)`.
  Capacity is pre-set to `(length - 2) * 3`.
- **Note:** winding is `0, i+2, i+1` — clockwise in Unity's convention, so
  the mesh faces the camera in SFS's 2D setup.
- **Status:** CONFIRMED

#### GetAngleBetweenPoints(float64 size, int32 pointCount) -> float64

- **Access:** **public static**
- **Behavior:** `return size * π * 2.0 / (pointCount - 1);`
- **Returns:** angular spacing in radians between adjacent vertices, where
  `size` is in normalised `[0, 1)` revolutions.
- **Gotcha:** divides by `pointCount - 1`; `pointCount == 1` divides by zero
  (returns `∞`, no exception, since these are doubles).
- **Status:** CONFIRMED

---

## Chunk/TerrainPoints

**Namespace:** `SFS.World.Terrain`
**Kind:** class (nested in `Chunk`)
**Status:** CONFIRMED
**Depth:** FULL
**IL:** `@204416`

A plain two-array carrier, returned by
`TerrainModule.GetTerrainPoints(...)`. It is the shared output type of both
the visual and the collider paths — the one place the two systems meet.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `points` | `Vector3[]` | public | no | The terrain vertices. The collider path projects these to `Vector2` and feeds them straight to `PolygonCollider2D.points`. | CONFIRMED |
| `otherData` | `Vector2[]` | public | no | Parallel per-vertex data (UV / shading inputs). Not consumed by the collider path. | CONFIRMED |

### Methods

#### .ctor(int32 pointCount)

- **Behavior:** allocates both arrays at `pointCount`. Nothing else.
- **Status:** CONFIRMED

---

## Reflection notes

- `TerrainColliderManager.main` is a public static field — the reachable
  entry point for the whole collider system. `hasColliders` on it is a
  `Bool_Local`, so it can be subscribed with the ordinary `Obs<bool>`
  pattern in [`REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md).
- `TerrainColliderManager.GetAngularChunkSize(Planet)` and
  `Chunk.GetAngleBetweenPoints(double, int)` are public statics with unique
  names — no ambiguous-overload hazard.
- `DynamicTerrain.Create` has 11 parameters and is the only construction
  path; there is no default-argument overload, so a reflection call must
  supply all 11.
- `DynamicChunk.updateSplit` / `updateMerge` are public fields on a nested
  type; reaching them requires
  `typeof(DynamicTerrain).GetNestedType("DynamicChunk", BindingFlags.Public)`.
- **Nothing in this file is a terrain-height oracle.** Read heights through
  `Planet.GetTerrainHeightAtAngle` instead.

## Open

- `Chunk..ctor` and `Chunk.CreateMesh` bodies not read (mesh construction,
  no simulation relevance identified). [OPEN]
- `DynamicChunk.GenerateRocks` (`@202816`, ~330 lines) not read — surface
  scatter placement, cosmetic. [OPEN]
- `DynamicChunk.SetLayer`'s water branch read only as far as the
  `hasWater` test. [OPEN]
- Whether two craft on different planets can actually collide on the shared
  `TerrainColliderManager.chunks` integer key is a **structural** reading of
  `AddChunks`, confirmed from IL; it has **not** been reproduced live.
  [PARTIAL]
