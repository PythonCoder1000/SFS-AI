# `SFS.Parts.PartHolder` — the craft's part collection

**Migrated** from `docs/sfs_source_reference.md` §B4 (2026-08-28).

**This is the correct place to ask "what modules does this rocket
have"** — unlike [`Part.md`](Part.md), whose own cache is never
invalidated.

---

## PartHolder

**Namespace:** SFS.Parts
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @238276 · 18 methods / 8 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `parts` | `List<Part>` | public | no | ordered | [CONFIRMED] |
| `partsSet` | `HashSet<Part>` | public | no | for O(1) `ContainsPart` | [CONFIRMED] |
| `onPartsAdded` | `Action<Part[]>` | public | no | | [CONFIRMED] |
| `onPartsRemoved` | `Action<Part[]>` | public | no | | [CONFIRMED] |
| `onPartsChanged` | `Action` | public | no | | [CONFIRMED] |
| `cachedArray` | `Part[]` | **private** | no | memo for `GetArray()` | [CONFIRMED] |
| `modules` | `Dictionary<string, object>` | **private** | no | module cache — **invalidated**, unlike `Part`'s | [CONFIRMED] |
| `moduleCount` | `Dictionary<string, int>` | **private** | no | | [CONFIRMED] |

**Gotcha:** `parts` and `partsSet` are **parallel containers** — `parts`
for order, `partsSet` for `ContainsPart` in O(1). **Mutating `parts`
directly desyncs them**; use the mutators.

### Methods

#### GetModules&lt;T&gt;() -> T[]

- **Access:** public instance, **generic** · IL @238644, body read
- **Behavior:**
  ```csharp
  public T[] GetModules<T>() {
      string key = typeof(T).Name;
      if (!modules.ContainsKey(key)) modules.Add(key, CollectModules<T>());
      return (T[])modules[key];
  }

  private T[] CollectModules<T>() {              // @238723
      var list = new List<T>();
      foreach (Part p in parts) {
          var m = p.GetModules<T>();             // delegates to Part's own memo
          if (m.Any()) list.AddRange(m);
      }
      return list.ToArray();
  }
  ```
- **Gotchas:** same short-name key, same `castclass`, **same collision
  risk** as `Part.GetModules<T>()`. **The difference that matters:
  `PartHolder` clears its cache** — see `ResetModules` below. Also note
  it is **generic**, so reflection needs `MakeGenericMethod`.
- **Status:** [CONFIRMED]

#### ResetModules() -> void

- **Access:** private instance · IL @238795
- **Behavior:** `modules.Clear(); moduleCount.Clear();`
- **Called from all six mutators** — `AddParts` @238332, `AddPartAtIndex`
  @238375, `RemoveParts` @238450, `RemovePartAtIndex` @238499,
  `SetParts` @238553, `ClearParts` @238607. **Verified exhaustively by
  grep.**
- **Gotchas:** so after staging or a collision the **holder's** answer is
  fresh, while the **surviving parts' own** caches are not (harmless,
  since a part's own components don't change).
- **Status:** [CONFIRMED]

#### GetArray() -> Part[]

- **Access:** public instance · IL @238289
- **Behavior:** memoises `parts.ToArray()` into `cachedArray`.
- **Gotchas:** `ResetModules` does **not** touch `cachedArray` — but each
  of the six mutators nulls it **itself**, on the instruction immediately
  preceding its `ResetModules()` call (`ldnull; stfld cachedArray` at
  @238330, @238373, @238448, @238497, @238551, @238605). `grep` on
  `PartHolder::cachedArray` returns exactly nine sites: three in
  `GetArray` and those six. **`GetArray()` is correctly invalidated on
  every structure change and is safe to use.**
- **Status:** [CONFIRMED]

#### TrackParts / TrackModules&lt;T&gt;

```csharp
void TrackParts(Action<Part> onPartAdded, Action<Part> onPartRemoved,
                Action onPartRemoved_After);
void TrackModules<T>(Action<T> onModuleAdded, Action<T> onModuleRemoved,
                     Action onModulesRemoved_After);
```

- **Access:** public instance
- **Behavior:** `TrackModules<T>` is **the clean way for an agent to
  react to engines appearing or disappearing** (staging, docking)
  **without polling** — it is what `Rocket.Awake` uses for
  `ControlModule` (`b__17_0` / `b__17_1`).
- **Status:** [PARTIAL] — signatures confirmed, bodies not read

### The six mutators

`AddParts`, `AddPartAtIndex`, `RemoveParts`, `RemovePartAtIndex`,
`SetParts`, `ClearParts`. All null `cachedArray` and call
`ResetModules()`. **[PARTIAL]** — signatures confirmed, bodies beyond
those two steps not read.

## How to enumerate a craft's modules, correctly

```csharp
// PREFERRED -- fresh, cache-invalidated, whole craft:
MethodInfo gm = partHolder.GetType().GetMethod("GetModules")
                          .MakeGenericMethod(moduleType);
Array mods = (Array)gm.Invoke(partHolder, null);

// Cache-free alternative, bypasses the short-name key entirely:
Component[] mods = partHolder.GetComponentsInChildren(moduleType, true);
```

**Do not** enumerate either `modules` dictionary. **Do not** assume
`GetArray()` is stale — it isn't; that is `Part`'s problem, not this
one's.

## Status summary

| Item | Status |
|---|---|
| `PartHolder : MonoBehaviour`, field layout | [CONFIRMED] |
| `GetModules<T>` / `CollectModules<T>` bodies | [CONFIRMED] |
| `ResetModules` called by all six mutators | [CONFIRMED] — grep-exhaustive |
| Short-name key collision risk (inherited from `Part`) | [CONFIRMED] mechanism |
| `GetArray()` caches; all six mutators null it themselves | [CONFIRMED] — grep-exhaustive |
| `TrackParts` / `TrackModules<T>` bodies | [PARTIAL] — signatures only |
| The six mutators' full bodies | [PARTIAL] |
