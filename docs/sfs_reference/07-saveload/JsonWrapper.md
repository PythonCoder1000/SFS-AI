# `SFS.Parsers.Json.JsonWrapper` — the serialization layer

**Migrated** from `docs/sfs_source_reference.md` §D5.0 (2026-08-28).

The whole save format is **plain JSON via Newtonsoft**, stored in files
with a `.txt` extension. Schemas:
[`save-records.md`](save-records.md). Spawning from them:
[`RocketManager.md`](RocketManager.md).

---

## JsonWrapper

**Namespace:** SFS.Parsers.Json
**Kind:** static class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] signatures · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @113505 · 7 methods / 1 field

Backed by **Newtonsoft.Json**, an extern assembly reference of
`Assembly-CSharp.dll`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `SerializerSettings` | `JsonSerializerSettings` | private | static readonly | shared settings; installs `MainContractResolver` | [CONFIRMED] shape · [OPEN] contents |

### Methods

| Signature | IL | Generic? | Status |
|---|---|---|---|
| `static bool TryLoadJson<T>(IFile file, out T data)` | @113513 | **yes** | [CONFIRMED] signature |
| `static void SaveAsJson(IFile file, object data, bool pretty)` | @113564 | no | [CONFIRMED] signature |
| `static T FromJson<T>(string json)` | @113580 | **yes** | [CONFIRMED] signature |
| `static string ToJson(object data, bool pretty)` | @113660 | no | [CONFIRMED] signature |
| `static string Serialize(JsonSerializer serializer, object data)` | @113683 | no | [CONFIRMED] signature |
| `private static VersionedData<T> FromJsonVersionData<T>(string json)` | @113620 | **yes** | [CONFIRMED] signature |

**Gotcha:** `TryLoadJson<T>` and `FromJson<T>` are **generic** — reaching
them by reflection needs `MakeGenericMethod`. **Writing is easier**:
`SaveAsJson` and `ToJson` take `object` and are not generic.

**Preconditions (added during Phase 1 Step 1.5).** This file documents
`JsonWrapper` as a signature table rather than per-method `####` entries,
so the template's per-method Preconditions field has nowhere to live. The
one that matters to shipped mod code, for `FromJson<T>(string)`:

- **None beyond valid arguments — no scene, no singleton, no loaded
  world.** It is a pure Newtonsoft wrapper; `sfsprobe`'s `loadblueprint`
  and `loadblueprintbuild` both call it before their scene gates would
  matter.
- **Its failure behaviour on malformed input is `[OPEN]`** — the body has
  not been read, so whether it throws or returns `null` for a given input
  is not established. `sfsprobe` handles both (`deserialize_error` from a
  caught exception, `deserialize_null` from a null return), which is the
  correct defensive posture given the body is unread.
- **The rest of this table is signature-only.** Anything here that a
  state-mutating command comes to depend on needs its body read first, per
  the plan's HARD RULE.

### Supporting types

All in `SFS.Parsers.Json`; own entries **[OPEN]** (Step 2).

| Type | IL | What it is |
|---|---|---|
| `JsonWrapper/VersionedData<T>` | @113740 | wraps a payload with its save version |
| `LegacyNameAttribute` | @113764 | field renames across save versions — **the reason old saves still load** |
| `MainContractResolver` | @113791 | the Newtonsoft contract resolver |
| `ExclusionList` | @113356 | with `Exclusion<T>` / `Inclusion<T>` in `SFS.Parsers.Json.Exclusions` |

---

## FileLocations

**Namespace:** *(none — top-level, global namespace)*
**Kind:** static class
**Status:** [CONFIRMED] property list
**Depth:** FULL
**IL:** `scratch/full_il.txt` @4031 · 23 methods / 4 fields

All the game's on-disk roots, as **static properties** returning
`IFolder`:

```
SavingFolder            CacheFolder             LogsFolder
SolarSystemsFolder      CustomAssetsFolder      CustomAssetsFolderOld
ModsFolder              PublicTranslationFolder TranslationCacheFolder
BlueprintsFolder        WorldsFolder
```

`ModsFolder` is the one [`../00-infrastructure/Loader.md`](../00-infrastructure/Loader.md)
scans. `BlueprintsFolder` and `WorldsFolder` are the two the save records
use.

**Status:** [CONFIRMED] names · [OPEN] the resolved paths and the other
12 members.

## Reflection recipe

**[UNTESTED-LIVE]**

```csharp
Type bpType = FindType("SFS.Builds.Blueprint");
Type jsonWrapper = FindType("SFS.Parsers.Json.JsonWrapper");

// TryLoadJson<T> is generic -> MakeGenericMethod
MethodInfo tryLoad = jsonWrapper.GetMethod("TryLoadJson",
        BindingFlags.Public | BindingFlags.Static)
    .MakeGenericMethod(bpType);

// Serializing any save object out is easier -- ToJson is NOT generic:
string json = (string)InvokeStatic(jsonWrapper, "ToJson",
    new Type[] { typeof(object), typeof(bool) },
    new object[] { someSaveObject, true });
```

Reading an existing blueprint off disk needs no game at all — it is JSON.

## Status summary

| Item | Status |
|---|---|
| JSON via Newtonsoft; `.txt` files | [CONFIRMED] |
| `JsonWrapper` API surface, and which members are generic | [CONFIRMED] |
| `FileLocations` folder property names | [CONFIRMED] |
| All `JsonWrapper` method bodies | [OPEN] |
| `SerializerSettings` contents | [OPEN] |
| `VersionedData`, `LegacyNameAttribute`, `MainContractResolver`, `ExclusionList` | [OPEN] — Step 2 |
| The other 12 `FileLocations` members and resolved paths | [OPEN] |
