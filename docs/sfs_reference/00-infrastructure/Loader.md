# `ModLoader.Loader` — the built-in mod loader

**Migrated** from `docs/sfs_source_reference.md` §A4 (2026-08-28).
Signatures re-read from IL during migration. §A4.2–A4.5 (the Harmony
assembly-resolution dead end) are kept here as an appendix, because they
are entirely about what this class does and does not load.

---

## Loader

**Namespace:** ModLoader
**Kind:** class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @43220–43973 · 11 methods / 4 fields

The mod loader is **baked into `Assembly-CSharp.dll`** (namespace
`ModLoader`, 11 real types in the inventory). There is no standalone
`ModLoader.dll`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `main` | `ModLoader.Loader` | public | **static** | the singleton | [CONFIRMED] |
| `mods` | `List<Mod>` | private | no | every mod discovered | [CONFIRMED] |
| `loadedMods` | `List<Mod>` | private | no | the subset that loaded successfully | [CONFIRMED] |
| `Version_Regex` | `Regex` | private | static readonly | used by `VerifyVersion` | [CONFIRMED] signature · [OPEN] pattern |

### Methods

#### GetAllMods() -> Mod[]

#### GetLoadedMods() -> Mod[]

- **Access:** public instance
- **Returns:** `mods` / `loadedMods` as arrays. The difference is exactly
  "discovered" vs "loaded without throwing".
- **Status:** [CONFIRMED] signature · [PARTIAL] body

#### Initialize_EarlyLoad() -> void

#### Initialize_Load() -> void

- **Access:** public instance · IL @43255 / @43315
- **Behavior:** the two-phase entry points the game calls into.
- **Status:** [PARTIAL] — signatures confirmed, bodies not traced

#### MoveIndividualDLLs() -> void

- **Access:** private instance · IL @43376
- **Behavior:** enumerates files in the Mods folder **root**; for every
  file whose extension is exactly `"dll"`, creates a subfolder named
  after the DLL (minus extension) and **moves the file into it**.
- **Side effects:** moves files on disk. A loose DLL dropped in `Mods/`
  relocates itself on the next launch.
- **Gotchas:** the whole body is wrapped in a `try`/`catch` that only
  logs `"Failed to move Individual DLLs due to:"` — a failure here is
  silent apart from the Unity player log.
- **Status:** [CONFIRMED] from body

#### LoadModList() -> void

- **Access:** private instance · IL @43442
- **Behavior:** enumerates **subfolders** of the Mods folder, skipping
  those whose name matches `FileLocations.CustomAssetsFolder` or
  `CustomAssetsFolderOld`, then for each remaining folder loads
  ```
  <ModsFolder>/<FolderName>/<FolderName>.dll     via Assembly.LoadFrom(path)
  ```
  followed by `Assembly.GetTypes()` to find the `Mod` subclass.
- **Side effects:** loads assemblies into the process.
- **Gotchas:** two, both operational.
  - **The DLL must be named after its containing folder.**
    `SFSProbe/SFSProbe.dll` works; `SFSProbe/probe.dll` is never loaded.
  - **Sibling DLLs in the mod's folder are never explicitly loaded.**
    `LoadModList` loads exactly one assembly per folder. This is central
    to the Harmony appendix below.
  - Failures are caught per-folder and logged as
    `"Failed to load mod in folder: {0}.\nError:{1}"` — check the Unity
    player log, not just `probe.log`, when a mod silently fails to appear.
- **Status:** [CONFIRMED] from body

#### LoadMod(Mod mod) -> void

- **Access:** private instance · IL @43645
- **Status:** [PARTIAL] — signature confirmed, body not traced

#### VerifyVersion(string targetVersion, string currentVersion) -> bool

- **Access:** **private static** · IL @43739
- **Status:** [PARTIAL] — signature confirmed, body not traced; uses
  `Version_Regex`

#### LoadDependencies(Mod mod) -> bool

- **Access:** private instance · IL @43762
- **Behavior:** resolves **inter-mod** dependencies only, from
  `Mod.Dependencies` (`Dictionary<string,string>`, mod ID → version).
  Self-reference-checks (`", has a reference to itself. Aborting"`) and
  consults `ModsSettings.main.settings.modsActive`.
- **Gotchas:** it has **nothing to do with loading a mod's bundled
  library DLLs** — a natural misreading, and the one the Harmony
  appendix corrects.
- **Status:** [CONFIRMED] from body

---

## Appendix — the Harmony dead end

Migrated verbatim in substance from §A4.2–A4.5. Kept attached to this
class because every claim in it is about what `LoadModList` does and does
not load.

### CORRECTION — the stated Harmony root cause is not supported by the IL

An earlier `sfs_source_reference.md` and `high_level_checklist.md` both
stated that

> SFS's own built-in mod loader — baked directly into
> `Assembly-CSharp.dll` — already loads the old Harmony/MonoMod into the
> process before any individual mod's `Load()` callback runs

and concluded that bundling a newer HarmonyX **cannot** work, so the only
remaining fix is replacing the game's own `Managed/0Harmony.dll` (which
was deliberately declined).

**That mechanism is wrong.** Confirmed:

| Check | Result |
|---|---|
| Occurrences of `HarmonyLib` or `MonoMod` in the full IL of `Assembly-CSharp.dll` | **0** |
| Extern assembly references to `0Harmony` / `MonoMod.*` in `Assembly-CSharp.dll` | **none** (36 extern refs, all listed, none Harmony/MonoMod) |
| Assemblies in `Managed/` that reference `0Harmony` | **none** — every DLL in the folder checked with `monodis --assemblyref` |
| `Assembly-CSharp-firstpass.dll` type refs to Harmony/MonoMod | **none** |

The game ships `0Harmony.dll` (2.10.1.0), `MonoMod.RuntimeDetour` /
`MonoMod.Utils` (22.3.23.4) and `Mono.Cecil` (0.10.4.0) in `Managed/`
purely as a **convenience library for mods**. Nothing in the game
references or loads them. `LoadModList` in particular loads exactly one
assembly per mod folder and never touches Harmony.

So the old Harmony is **not pre-loaded before mods run**. The MVID
evidence recorded in memory is still valid — it proves the *old* DLL is
what ultimately got loaded — but it identifies the symptom, not the cause.

**The supported mechanism [PARTIAL — IL-grounded, not runtime-proven]:**
`SFSProbe.dll` carries a reference to `0Harmony`. When the JIT first
touches a `HarmonyLib` type, Mono resolves that reference by simple name
(both copies are **weak-named** — `monodis --assembly` reports a
zero-sized public key on the game's 2.10.1.0 *and* on the bundled
2.16.0.0, so only one `0Harmony` can exist per process and version is not
part of identity). Mono's default probing path is the **application
base** — `Managed/` — which is searched before the directory beside the
mod DLL.

`build.sh` states the opposite assumption in a comment:

> All 7 DLLs need to sit next to SFSProbe.dll at runtime — 0Harmony.dll
> pulls in the rest of this chain via Mono's normal assembly probing of
> the loading assembly's own directory.

Co-locating the DLLs is necessary but **not sufficient**: it does not
beat the app base for an assembly name that already exists there.

### What this changes, and what it does not

**Does not change:** the decision to stop pursuing Harmony was
reasonable, and this section is not an argument to resume it. The
`dragArea` goal that motivated it is now solved without Harmony — see
[`../02-drag-aero/`](../02-drag-aero/).

**Does change:** the claim that *no non-invasive fix exists* is
unsupported. If Harmony is ever wanted again, at least two options exist
that were never tried and that do **not** require modifying the game's
`Managed/` folder:

1. Install an `AppDomain.CurrentDomain.AssemblyResolve` handler, or
   `Assembly.LoadFrom` the bundled `0Harmony.dll` by absolute path, in
   the mod's entry point — **before any `HarmonyLib` type is touched**.
   The trigger point matters: type resolution happens on first JIT of a
   method that references the type, so the loading code must live in a
   method that itself has no Harmony references.
2. Strong-name the bundled copy so it no longer collides on simple name.

**[OPEN]** — neither has been tried, and neither is proven to work.
`Mono.Cecil` presents the same collision independently (game 0.10.4.0 vs
bundle 0.11.6, also weak-named), so a fix must cover the whole chain.

**Independent of all of the above**, the ceiling on Harmony here may
still be low: MonoMod issue #230 (`ILHookOnMonoShouldSucceed`) was still
failing CI on macOS 14 arm64 sysmono as of 2025-09-30 — a near-exact
match for this environment. Fixing assembly resolution could simply trade
the current `NullReferenceException` for `InvalidProgramException` at the
same conceptual step. Expect a different error, not a guaranteed success.

### The original failure signature, for recognition

**[CONFIRMED]** — observed live, reproduced with an isolating test.

```
HarmonyLib.HarmonyException: IL Compile Error (unknown location)
 ---> System.NullReferenceException
  at MonoMod.RuntimeDetour.DetourHelper.GetIdentifiable(MethodBase)
  at MonoMod.RuntimeDetour.ILHook..ctor(...)
  at HarmonyLib.Public.Patching.ManagedMethodPatcher.DetourTo(MethodBase)
  at HarmonyLib.PatchFunctions.UpdateWrapper(...)
```

Environment-wide, not target-specific: patching a trivial no-op method in
the mod's **own** assembly fails identically
(`GeometryPatches.TestTrivialPatch`, still present in `SFSProbe.cs`).
Setting `MONOMOD_DMDType=Cecil` produced a byte-identical stack trace,
placing the failure upstream of DMD generation, in detour-runtime
platform selection.

Root cause of *that* crash (as opposed to the resolution problem above):
MonoMod 22.3.23.4 predates Apple Silicon macOS support, added in MonoMod
PR #241 (merged 2025-08-15, first shipped in HarmonyX 2.15.0). Apple's
Hardened Runtime uses W^X `MAP_JIT` pages requiring dedicated unmanaged
helper code to patch running methods, which that build never had.

### Version inventory

**[CONFIRMED]** via `monodis --assembly` on each file, 2026-08-27.

| Assembly | Game `Managed/` | Bundled `sfsprobe/lib/harmonyx_2.16.0/` |
|---|---|---|
| `0Harmony` | 2.10.1.0 | 2.16.0.0 |
| `MonoMod.RuntimeDetour` | 22.3.23.4 | 25.3.3 |
| `MonoMod.Utils` | 22.3.23.4 | 25.0.11 |
| `Mono.Cecil` | 0.10.4.0 | 0.11.6 |

All weak-named on both sides. The game also ships `Mono.Cecil.Mdb`,
`Mono.Cecil.Pdb`, `Mono.Cecil.Rocks`. The bundle adds `MonoMod.Backports`,
`MonoMod.Core`, `MonoMod.ILHelpers`. The bundled files are inert as long
as nothing resolves to them — harmless to leave in place.

## Status summary

| Item | Status |
|---|---|
| `Loader` field layout | [CONFIRMED] |
| `MoveIndividualDLLs` body | [CONFIRMED] |
| `LoadModList` body — one DLL per folder, name must match folder | [CONFIRMED] |
| `LoadDependencies` body — inter-mod only | [CONFIRMED] |
| `Initialize_EarlyLoad` / `Initialize_Load` / `LoadMod` / `VerifyVersion` bodies | [OPEN] |
| `Version_Regex` pattern | [OPEN] |
| Assembly-CSharp has zero Harmony/MonoMod references | [CONFIRMED] |
| Assembly-name-resolution-against-app-base mechanism | [PARTIAL] — IL-grounded, not runtime-proven |
| The two untried non-invasive Harmony fixes | [OPEN] |
| The other 10 `ModLoader*` types | [OPEN] — Step 2 |
