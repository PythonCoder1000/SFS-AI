# SFS Type Inventory — Assembly-CSharp.dll 1.6.00.16

Generated 2026-08-28 from `scratch/full_il.txt` (monodis IL disassembly).
Pinned build verified this session: `Assembly-CSharp.dll` md5 =
`cbad19d24f73252e5a7acd6b88cfa9c1`.

This file is the **scope definition** for `docs/sfs_reference/`. Every row
here is a type that must eventually have an entry in `INDEX.md` and a file
under a category folder, or be explicitly recorded as out of scope.

## Status

**Phase 1, Step 0 (inventory) — DONE, 2026-08-28.** Nothing has been migrated
or written yet.

- `INDEX.md` and `manifest.json` **do not exist yet** — they are built during
  Step 1 (migration). Until then, this file is the entry point for a fresh
  session.
- `docs/sfs_source_reference.md` is still the live reference and is still
  referenced by `docs/startup_prompt.md`, `README.md`, `CLAUDE.md`. It gets
  retired in Step 3, not before.
- **Next step:** Phase 1 Step 1 — split `docs/sfs_source_reference.md`
  (6,590 lines) into per-class files under the category folders proposed
  below, reformatted into the strict per-class template, building `INDEX.md`
  and `manifest.json` as it goes. Take a scratch backup of the old file first
  and diff-check that nothing is dropped.

## Method

Parsed every `.class` declaration in the 13.3 MB IL dump, tracking the
enclosing `.namespace` block and nesting depth, and counting `.method` /
`.field` declarations per type. Compiler-generated types are excluded:
closure classes (`<>c`, `<>c__DisplayClass*`), iterator/async state machines
(`<Method>d__N`), `<PrivateImplementationDetails>` and its
`__StaticArrayInitTypeSize=*` structs. 1509 `.class` declarations total →
**969 real types** after that filter (540 compiler-generated removed).

Member counts are **declaration counts from the IL**, so they include
compiler-emitted accessors (`get_X`/`set_X`), `.ctor`/`.cctor`, and backing
fields. They are an upper bound on what a human-facing doc must describe,
not a target.

## Totals

| | Count |
|---|---|
| Real types | 969 |
| Top-level | 738 |
| Nested | 231 |
| Namespaces (incl. global) | 53 |
| Method declarations | 6137 |
| Field declarations | 4078 |

| Kind | Count |
|---|---|
| class | 728 |
| enum | 71 |
| static class | 66 |
| abstract class | 35 |
| struct | 30 |
| interface | 28 |
| delegate | 11 |

## Coverage against the old single-file reference

`docs/sfs_source_reference.md` (6,590 lines) is the material Phase 1 Step 1
migrates. Two measures, because "mentioned" and "documented" are very
different bars:

- **67 types have a named heading** in the old doc — these are the ones
  with real per-type content to migrate.
- **266 types are mentioned anywhere** in its prose — an upper bound;
  most of these are one-line references inside another type's section, not
  documentation of the type itself.

So migration inherits substantive content for roughly **67–266 of 969**
types (6–27%). Everything else is Step 2 net-new writing.

## Namespace breakdown

`old-doc` = types with a named heading in `sfs_source_reference.md`.

| Namespace | Top-level | Nested | Total | Methods | Fields | old-doc | Note |
|---|---:|---:|---:|---:|---:|---:|---|
| `SFS.Parts.Modules` | 110 | 53 | 163 | 687 | 712 | 16 |  |
| `<global>` | 104 | 41 | 145 | 835 | 585 | 4 |  |
| `SFS.World` | 79 | 38 | 117 | 897 | 589 | 19 |  |
| `SFS.UI` | 87 | 9 | 96 | 528 | 458 | 1 |  |
| `SFS.Builds` | 25 | 13 | 38 | 294 | 232 | 2 |  |
| `SFS.Variables` | 34 | 2 | 36 | 170 | 49 | 3 |  |
| `SFS.Parts` | 25 | 7 | 32 | 150 | 123 | 5 |  |
| `SFS` | 24 | 4 | 28 | 841 | 141 | 2 |  |
| `SFS.World.Maps` | 19 | 8 | 27 | 205 | 76 | 0 |  |
| `SFS.Input` | 24 | 3 | 27 | 153 | 104 | 0 |  |
| `SFS.Career` | 16 | 3 | 19 | 134 | 94 | 1 |  |
| `SFS.UI.ModGUI` | 18 | 1 | 19 | 129 | 49 | 1 |  |
| `SFS.World.PlanetModules` | 10 | 9 | 19 | 35 | 125 | 0 |  |
| `SFS.Translations` | 17 | 1 | 18 | 86 | 48 | 1 |  |
| `SFS.WorldBase` | 14 | 3 | 17 | 158 | 120 | 2 |  |
| `SFS.Logs` | 13 | 0 | 13 | 39 | 43 | 2 |  |
| `SFS.Audio` | 9 | 4 | 13 | 45 | 50 | 0 |  |
| `ModLoader` | 10 | 1 | 11 | 61 | 27 | 2 |  |
| `SFS.Navigation` | 7 | 4 | 11 | 48 | 8 | 0 |  |
| `SFS.Sharing` | 4 | 6 | 10 | 40 | 49 | 0 |  |
| `SFS.Parsers.Constructed` | 1 | 8 | 9 | 20 | 5 | 1 |  |
| `SFS.World.Drag` | 9 | 0 | 9 | 69 | 25 | 2 |  |
| `SFS.Stats` | 4 | 4 | 8 | 63 | 50 | 2 |  |
| `SFS.World.Terrain` | 4 | 3 | 7 | 43 | 44 | 0 |  |
| `SFS.IO` | 7 | 0 | 7 | 62 | 7 | 0 |  |
| `InterplanetaryModule` | 6 | 0 | 6 | 28 | 44 | 0 |  |
| `SFS.Tutorials` | 5 | 1 | 6 | 34 | 26 | 0 |  |
| `SFS.Core` | 5 | 0 | 5 | 17 | 7 | 0 |  |
| `SFS.Parsers.Json` | 4 | 1 | 5 | 14 | 4 | 0 |  |
| `SFS.Parsers.Ini` | 3 | 2 | 5 | 34 | 14 | 0 |  |
| `ModLoader.UI` | 2 | 2 | 4 | 17 | 28 | 0 |  |
| `SFS.Cameras` | 4 | 0 | 4 | 20 | 12 | 0 |  |
| `TranslucentImage` | 3 | 0 | 3 | 37 | 26 | 0 | vendored third-party |
| `UnityEngine.Purchasing.Security` | 3 | 0 | 3 | 9 | 12 | 0 | vendored third-party |
| `UV` | 3 | 0 | 3 | 5 | 9 | 0 | vendored third-party |
| `SFS.Platform` | 3 | 0 | 3 | 3 | 7 | 0 |  |
| `SFS.Parsers.Json.Exclusions` | 3 | 0 | 3 | 6 | 2 | 0 |  |
| `Firebase.Internal` | 3 | 0 | 3 | 14 | 17 | 0 | vendored third-party |
| `SFS.Utilities` | 2 | 0 | 2 | 13 | 1 | 0 |  |
| `SFS.Analytics` | 2 | 0 | 2 | 20 | 11 | 0 |  |
| `_Game` | 1 | 0 | 1 | 4 | 2 | 0 |  |
| `_Game.Drawers` | 1 | 0 | 1 | 8 | 6 | 0 |  |
| `Assets.Scripts` | 1 | 0 | 1 | 3 | 0 | 0 |  |
| `Assets.Scripts.Utility` | 1 | 0 | 1 | 1 | 0 | 0 |  |
| `UI` | 1 | 0 | 1 | 3 | 3 | 0 |  |
| `Parts` | 1 | 0 | 1 | 1 | 9 | 0 |  |
| `Parts.Transform` | 1 | 0 | 1 | 4 | 1 | 0 |  |
| `Notifications` | 1 | 0 | 1 | 0 | 0 | 0 |  |
| `ModLoader.Helpers` | 1 | 0 | 1 | 1 | 10 | 1 |  |
| `ModLoader.IO` | 1 | 0 | 1 | 14 | 11 | 0 |  |
| `SFS.Tween` | 1 | 0 | 1 | 15 | 1 | 0 |  |
| `SFS.Parsers.Regex` | 1 | 0 | 1 | 10 | 2 | 0 |  |
| `SFS.World.Legacy` | 1 | 0 | 1 | 10 | 0 | 0 |  |

### Note on the three newly-in-scope namespaces

The task brief estimated `SFS.UI` at 87 types, `SFS.Builds` at 25, and
`SFS.UI.ModGUI` at 18. Those are the **top-level** counts and they are
correct: 87 / 25 / 18 exactly. Including nested types the real totals are
**96 / 38 / 19 = 153 types**, carrying 951 method and 739 field
declarations between them.

## Out-of-scope candidates

These are vendored third-party libraries compiled into `Assembly-CSharp.dll`,
not SFS's own code. They document nothing about the game's behaviour and
have upstream documentation of their own. Recommend excluding; flagging
rather than silently dropping, since the standing decision was "no exclusions".

| Namespace / type | Types | What it is |
|---|---:|---|
| `Firebase.Internal` | 3 | Firebase SDK internals |
| `TranslucentImage` | 3 | Asset-store blur/UI shader component |
| `UnityEngine.Purchasing.Security` | 3 | Unity IAP receipt validation |
| `UV` | 3 | Asset-store UV helper |
| `SD*` (global) | 8 | SDWebImage port — image download/cache |
| `GifDecoder` (global) | 1 | GIF decoding, part of the SDWebImage port |
| `GPGSIds`, `FbAuth`, `SteamManager` (global) | 3 | Platform SDK glue |

Total candidate exclusion: ~26 types. Everything else — including all of
`SFS.UI`, `SFS.Builds`, `SFS.UI.ModGUI` — is in scope.

**CORRECTION (2026-08-29, Phase 1 Step 2).** The "~26" above counts only
**top-level** vendored types. The SDWebImage port also contributes **7
nested** types that this inventory counts as real: `SDAnimatedImage/State`,
`/LoadingIndicatorType`, `/OnImageSizeReadyAction`, `/OnDecodingErrorAction`,
`/OnLoadingErrorAction`, `SDWebImage/LoadingIndicatorType`,
`/OnImageSizeReadyAction`, `/OnLoadingErrorAction`, and
`SDWebImageDownloaderError/ErrorType`. **The real exclusion count is 33, and
the in-scope total is 936, not 943.** `manifest.json` is corrected and
`INDEX.md` is regenerated from it; the table above is left as originally
written because it is the Step 0 artifact. Also logged in
[`CORRECTIONS.md`](CORRECTIONS.md).

## Proposed category folders

The brief's 18 folders were sized against the old doc's coverage, not against
969 types. Four namespaces have no home in that list at all — `SFS.World.Maps`,
`SFS.Career`, `SFS.Translations`, `SFS.Audio` — and `14-misc-part-modules`
would otherwise absorb ~110 unrelated types. Proposed adjustment: keep all 18
as named, add four (`18`–`21`). Counts are approximate because two namespaces
(`SFS.World`, `SFS.Parts.Modules`) split across several topic folders; the
per-type assignment gets finalised during Step 1/2 and recorded in `INDEX.md`.

| Folder | Contents | ~Types |
|---|---|---:|
| `00-infrastructure/` | `SFS.Variables` (36), `SFS.Parsers.*` (23), `SFS.IO` (7), `ModLoader*` (17), `SFS.Core` (5), `SFS.Utilities` (2), plus the global math/utility layer (`Double2`, `Double3`, `Matrix2x2*`, `Math_Utility`, `Line`, `Line2`, `Units`, `FastLinq`, `Pool`, `FileLocations`, …) | ~150 |
| `01-core-flight/` | `SFS.World` flight core (`Rocket`, `Location`, `WorldLocation`, `Physics`, `Orbit`, `Trajectory`, `Staging`, `Stage`, `I_Physics`, `I_Path`) + `SFS.Parts` core (`Part`, `PartHolder`, `Mass_Calculator`, `Part_Utility`) + global `Kepler` | ~30 |
| `02-drag-aero/` | `SFS.World.Drag` (9) + global aero types (`AeroData`, `AeroFormula`, `AeroMesh`, `CurvedMesh`, `StraightMesh`, `BasicMeshData`, `ReentryData`, `Point`) + `SFS.World.Aero_Local`, `AeroDrawer` | ~20 |
| `03-heat-destruction/` | `HeatModule`, `HeatInfoModule`, `IsCoveredModule`, `BurnMark`, global `BurnManager`, `TemperatureTest`, `SFS.World.DestructionReason`, `TemperatureBar` | ~10 |
| `04-engines/` | `EngineModule`, `BoosterModule`, `TorqueModule`, `FlameModule`, `FlameRandomizer`, `EffectModule`, `ParticleModule` | ~8 |
| `05-rcs/` | `RcsModule` + its nested types | ~5 |
| `06-soi-terrain/` | `SFS.WorldBase` (17), `SFS.World.PlanetModules` (19), `SFS.World.Terrain` (7), `SFS.World.Atmosphere`, `TerrainSampler`, `InterplanetaryModule` (6) | ~52 |
| `07-saveload/` | `SFS.Parsers.Json*` (8), `SFS.Parsers.Ini` (5), `SFS.IO` (7), save records (`WorldSave`, `RocketSave`, `PartSave`, `StageSave`, `JointSave`), `SFS.Sharing` (10) | ~35 |
| `08-parametric-expressions/` | `SFS.Parsers.Constructed` (9) + `VariablesModule`/`ExternalVariableModule`/`VariableConverterModule`/`MathModule` | ~14 |
| `09-resources-fuel/` | `ResourceType`, `ResourceModule`, `FlowModule`, `FuelPipeModule`, `DisableOnNoFlow`, `SFS.World.Resources`, `Local_Resources`, `EVA_Resources`, `FuelTransferLine`, `FuelTransferUI`, `ResourceDrawer` | ~15 |
| `10-control-input/` | `SFS.Input` (27) + `Player`, `Player_Local`, `PlayerController`, `Arrowkeys*`, `Throttle*`, `Staging*`, `ControlModule` | ~40 |
| `11-joints-docking/` | `PartJoint`, `JointGroup`, `JointSave`, `DockingPortModule`, `DockingPortTrigger`, `MagnetModule`, `DetachModule`, `SeparatorBase`, `SplitModule`, `Splittable` family, `LinkModule` | ~20 |
| `12-world-scene-timewarp/` | `WorldTime`, `WorldView`, `GameManager`, `WorldLoader`, `Environment`, `WorldEnvironment`, `SFS.SceneLoader`, `SFS.Cameras` (4), `GameCamerasManager`, `SFS.Tween` | ~25 |
| `13-challenges-logging/` | `SFS.Logs` (13), `SFS.Stats` (8), `SFS.Analytics` (2), `ErrorLogger`, `SFS.I_MsgLogger`, `MsgCollector`, `MsgNone`, `TimeTracker` | ~30 |
| `14-misc-part-modules/` | the remaining ~90 of `SFS.Parts.Modules` — geometry/mesh (`Surfaces`, `PolygonMesh`, `Pipe*`, `ModelSurface`, …), colour/texture (`ColorModule`, `PartTex`, `Textures`, …), and behaviour modules (`ParachuteModule`, `WheelModule`, `ToggleModule`, `MoveModule`, `ActivationSequenceModule`, `LES_Module`, …) | ~110 |
| `15-ui/` | `SFS.UI` — all 96 (87 top-level + 9 nested) | 96 |
| `16-builds/` | `SFS.Builds` — all 38 (25 top-level + 13 nested) | 38 |
| `17-modgui/` | `SFS.UI.ModGUI` — all 19 (18 top-level + 1 nested) | 19 |
| `18-maps-navigation/` | **NEW** — `SFS.World.Maps` (27), `SFS.Navigation` (11), `MapPlayer`, `SelectableObject`, `Rings` | ~42 |
| `19-career-progression/` | **NEW** — `SFS.Career` (19), `SFS.Tutorials` (6), `SFS.World.SpaceCenter`/`SpaceCenterData`/`LegacyLaunchPad`, `SandboxSettings` | ~30 |
| `20-localization-audio/` | **NEW** — `SFS.Translations` (18), `SFS.Audio` (13), `AudioModule`, `SFS_Translation`, `TranslationUtility` | ~35 |
| `21-platform-rendering/` | **NEW** — `SFS.Platform` (3), `PlatformUtilities`, `SteamManager`, `DeeplinkManager`, `SFS.PostProcessing`, `RenderSorting*`, `SFS.VideoSettings*`, `FXAA`, `GLDrawer`, `Stars`/`StarGenerator`/`ShootingStar*` | ~30 |

Everything not listed above lands in `00-infrastructure/` or the vendored
exclusion list. No type is dropped without a row in this file saying so.

## Full type list

Columns: type, kind, `M`ethods / `F`ields (IL declaration counts), line in
`scratch/full_il.txt`, and `H` if the old doc has a named heading for it.
Nested types are indented under their parent and named `Parent/Nested`.

### `<global namespace>` — 145 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `GPGSIds` | static class | 0 | 9 | 165 |  |
| `Double2` | struct | 48 | 2 | 180 | H |
| `Double3` | struct | 37 | 3 | 1226 |  |
| `AuthCallback` | delegate | 4 | 0 | 2193 |  |
| `FbAuth` | static class | 6 | 1 | 2231 |  |
| `Matrix2x2` | class | 7 | 2 | 2535 |  |
| `Matrix2x2_Double` | class | 4 | 2 | 2757 |  |
| `MonoBehaviourCached` | class | 3 | 2 | 2860 |  |
| `ObservableMonoBehaviour` | class | 4 | 1 | 2928 |  |
| `Units` | static class | 24 | 1 | 2997 |  |
| `AndroidMigration` | static class | 5 | 2 | 3875 |  |
| `FileLocations` | static class | 23 | 4 | 4031 |  |
| `PlanetData_Old` | class | 1 | 9 | 4609 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/BasicModule` | class | 1 | 6 | 4644 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/SerializableColor` | class | 1 | 3 | 4681 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/MyVector2` | struct | 1 | 2 | 4723 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/TerrainModule_Old` | class | 1 | 4 | 4746 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/TerrainModule_Old/DetailLevel_Old` | class | 1 | 2 | 4770 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/TerrainModule_Old/TerrainTexture_Old` | class | 1 | 13 | 4790 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/AtmosphereModule_Old` | class | 1 | 4 | 4902 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/AtmosphereModule_Old/Physics_Old` | class | 1 | 3 | 4922 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/AtmosphereModule_Old/Gradient_Old` | class | 1 | 3 | 4952 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/AtmosphereModule_Old/Clouds_Old` | class | 1 | 6 | 4982 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/AtmosphereModule_Old/SerializableGradient_Old` | class | 1 | 1 | 5015 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/AtmosphereModule_Old/SerializableGradient_Old/Key` | class | 2 | 5 | 5032 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/ColorGradingGradient_Old` | class | 1 | 1 | 5093 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/ColorGradingGradient_Old/Key` | class | 2 | 8 | 5110 |  |
| &nbsp;&nbsp;↳ `PlanetData_Old/OrbitModule_Old` | class | 1 | 6 | 5187 |  |
| `ResourcesLoader` | class | 4 | 9 | 5219 |  |
| &nbsp;&nbsp;↳ `ResourcesLoader/ButtonIcons` | class | 1 | 18 | 5305 |  |
| &nbsp;&nbsp;↳ `ResourcesLoader/ChallengeIcons` | class | 1 | 13 | 5345 |  |
| `Stars` | class | 7 | 1 | 5437 |  |
| &nbsp;&nbsp;↳ `Stars/Star` | class | 1 | 2 | 5663 |  |
| `AutoDetachModule` | class | 7 | 7 | 5693 |  |
| `I_InitializePartModule` | interface | 2 | 0 | 6022 |  |
| `AndroidRestorePurchaseMenu` | class | 1 | 6 | 6045 |  |
| `RequireFullSwitchImplementationAttribute` | class | 1 | 0 | 6075 |  |
| `SaveLocationSettings` | class | 2 | 4 | 6095 |  |
| `DeeplinkManager` | class | 6 | 3 | 6133 |  |
| `SteamManager` | class | 9 | 4 | 6889 |  |
| `LLMComment` | class | 1 | 1 | 7154 |  |
| `LLMCommentShorten` | class | 1 | 0 | 7176 |  |
| `PopupManager` | class | 9 | 4 | 7197 |  |
| &nbsp;&nbsp;↳ `PopupManager/Popup` | class | 1 | 2 | 7491 |  |
| &nbsp;&nbsp;↳ `PopupManager/State` | class | 1 | 1 | 7511 |  |
| &nbsp;&nbsp;↳ `PopupManager/FeatureTracker` | class | 1 | 1 | 7533 |  |
| &nbsp;&nbsp;↳ `PopupManager/Feature` | enum | 0 | 5 | 7552 |  |
| `TimeTracker` | class | 15 | 2 | 7565 |  |
| &nbsp;&nbsp;↳ `TimeTracker/Data` | class | 1 | 3 | 7935 |  |
| `ColorAnimation` | class | 5 | 5 | 8025 |  |
| `PopupAnimation` | class | 7 | 5 | 8151 |  |
| `SizeAnimation` | class | 7 | 7 | 8320 |  |
| `IntEvent` | class | 1 | 0 | 8531 |  |
| `StatsMenu` | class | 23 | 20 | 8549 |  |
| &nbsp;&nbsp;↳ `StatsMenu/ElementData` | class | 1 | 4 | 9632 |  |
| `OpenTracker` | class | 4 | 2 | 10986 |  |
| `MyScaleToFit` | class | 4 | 4 | 11124 |  |
| `ButtonGroup` | class | 7 | 3 | 11268 |  |
| `CommunityPanel` | class | 4 | 0 | 11527 |  |
| `GravityTurnDrawer` | class | 2 | 3 | 11581 |  |
| `SafeArea` | class | 7 | 6 | 11678 |  |
| &nbsp;&nbsp;↳ `SafeArea/HorizontalMode` | enum | 0 | 5 | 11955 |  |
| &nbsp;&nbsp;↳ `SafeArea/VerticalMode` | enum | 0 | 5 | 11966 |  |
| `ApplicationUtility` | static class | 5 | 3 | 11979 |  |
| `CallbackAwaiter`&lt;1&gt; | class | 7 | 2 | 12375 |  |
| `CallbackAwaitable`&lt;1&gt; | class | 8 | 3 | 12585 |  |
| `Component_Utility` | static class | 11 | 0 | 12762 |  |
| `Transform_Utility` | static class | 4 | 0 | 13090 |  |
| `DevSettings` | class | 6 | 1 | 13183 |  |
| `DisableAtStart` | class | 2 | 1 | 13287 |  |
| `ErrorLogger` | class | 5 | 5 | 13341 | H |
| `FastLinq` | static class | 9 | 0 | 13986 |  |
| `FirebaseUtility` | class | 4 | 4 | 14454 |  |
| `FXAA` | class | 5 | 3 | 14548 |  |
| `GLDrawer` | class | 12 | 6 | 14666 |  |
| `I_GLDrawer` | interface | 1 | 0 | 15318 |  |
| `LineCommand` | struct | 0 | 4 | 15330 |  |
| `CircleCommand` | struct | 0 | 4 | 15340 |  |
| `LayoutUtility` | static class | 1 | 0 | 15350 |  |
| `Line` | struct | 8 | 2 | 15388 |  |
| `Line2` | struct | 21 | 2 | 15536 |  |
| `Color2` | struct | 2 | 2 | 16216 |  |
| `ListUtility` | static class | 7 | 0 | 16256 |  |
| `Math_Utility` | static class | 27 | 0 | 16591 |  |
| `OnFrameEnd` | class | 4 | 3 | 17330 |  |
| `PlatformUtilities` | class | 5 | 3 | 17395 |  |
| `PolygonPartioner` | static class | 19 | 0 | 17605 |  |
| &nbsp;&nbsp;↳ `PolygonPartioner/VertexWorkSet` | class | 1 | 5 | 19317 |  |
| `VertexChain` | class | 10 | 0 | 19351 |  |
| `Pool`&lt;1&gt; | class | 7 | 4 | 19592 |  |
| `SerializeUtility` | static class | 3 | 1 | 19774 |  |
| `TextureUtility` | static class | 4 | 0 | 19851 |  |
| `Text_Static` | static class | 3 | 0 | 20174 |  |
| `TransformExtensions` | static class | 2 | 0 | 20309 |  |
| `BuildVersionText` | class | 5 | 2 | 20802 |  |
| `INJECTED_BUILD_ID` | static class | 2 | 1 | 21178 |  |
| `BuildSelectMenu` | class | 6 | 2 | 21215 |  |
| `OptionalDelegate`&lt;1&gt; | class | 10 | 3 | 21546 |  |
| `Utility` | static class | 8 | 0 | 21780 |  |
| `PartIconCreator` | class | 13 | 2 | 22064 |  |
| `PartShopIcon` | class | 2 | 6 | 22803 |  |
| `TT_Base` | abstract class | 8 | 8 | 22942 |  |
| `AeroData` | class | 2 | 9 | 23254 |  |
| `CurvedMesh` | class | 3 | 4 | 23298 |  |
| `StraightMesh` | class | 2 | 1 | 23537 |  |
| `BasicMeshData` | class | 1 | 11 | 23574 |  |
| `AeroFormula` | struct | 5 | 4 | 23603 |  |
| `AeroMesh` | class | 13 | 6 | 23920 |  |
| &nbsp;&nbsp;↳ `AeroMesh/Data` | struct | 0 | 5 | 25977 |  |
| `BurnManager` | class | 4 | 3 | 26186 |  |
| `TemperatureTest` | class | 2 | 2 | 26477 |  |
| `ReentryData` | struct | 0 | 5 | 26844 |  |
| `Point` | struct | 0 | 4 | 26855 |  |
| `StarGenerator` | class | 2 | 7 | 26865 |  |
| `Kepler` | static class | 31 | 3 | 26996 | H |
| `DebugPacker` | class | 6 | 0 | 28017 |  |
| `PackDisplay` | class | 9 | 19 | 28478 |  |
| &nbsp;&nbsp;↳ `PackDisplay/DisplayPart` | class | 1 | 3 | 28984 |  |
| `SaleManager` | class | 1 | 1 | 29056 |  |
| `SalesSystem` | class | 1 | 4 | 29075 |  |
| `RotationController` | class | 3 | 2 | 29099 |  |
| `GifDecoder` | class | 31 | 43 | 29155 |  |
| &nbsp;&nbsp;↳ `GifDecoder/Status` | enum | 0 | 4 | 30958 | H |
| &nbsp;&nbsp;↳ `GifDecoder/GifFrame` | class | 1 | 2 | 30968 |  |
| `MainThread` | class | 4 | 3 | 30996 |  |
| `SDAnimatedImage` | class | 37 | 31 | 31156 |  |
| &nbsp;&nbsp;↳ `SDAnimatedImage/State` | enum | 0 | 7 | 32627 |  |
| &nbsp;&nbsp;↳ `SDAnimatedImage/LoadingIndicatorType` | enum | 0 | 5 | 32640 |  |
| &nbsp;&nbsp;↳ `SDAnimatedImage/OnImageSizeReadyAction` | delegate | 4 | 0 | 32651 |  |
| &nbsp;&nbsp;↳ `SDAnimatedImage/OnDecodingErrorAction` | delegate | 4 | 0 | 32689 |  |
| &nbsp;&nbsp;↳ `SDAnimatedImage/OnLoadingErrorAction` | delegate | 4 | 0 | 32727 |  |
| `SDImageCache` | class | 23 | 4 | 32953 |  |
| `SDWebImage` | class | 23 | 15 | 34086 |  |
| &nbsp;&nbsp;↳ `SDWebImage/LoadingIndicatorType` | enum | 0 | 5 | 34855 |  |
| &nbsp;&nbsp;↳ `SDWebImage/OnImageSizeReadyAction` | delegate | 4 | 0 | 34866 |  |
| &nbsp;&nbsp;↳ `SDWebImage/OnLoadingErrorAction` | delegate | 4 | 0 | 34904 |  |
| `SDWebImageDownloader` | class | 10 | 2 | 35105 |  |
| `SDWebImageDownloaderError` | class | 1 | 2 | 36383 |  |
| &nbsp;&nbsp;↳ `SDWebImageDownloaderError/ErrorType` | enum | 0 | 8 | 36461 |  |
| `SDWebImageDownloaderOperation` | class | 7 | 7 | 36477 |  |
| `SDWebImageOptions` | enum | 0 | 5 | 36708 |  |
| `SDWebImageManager` | class | 3 | 1 | 36721 |  |
| `Singleton`&lt;1&gt; | abstract class | 3 | 1 | 36953 |  |
| `UnitySourceGeneratedAssemblyMonoScriptTypes_v1` | class | 2 | 0 | 37036 |  |
| &nbsp;&nbsp;↳ `UnitySourceGeneratedAssemblyMonoScriptTypes_v1/MonoScriptData` | struct | 0 | 5 | 37100 |  |

### `Assets.Scripts` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `ForceIncludeSecurityLibraries` | class | 3 | 0 | 37736 |  |

### `Assets.Scripts.Utility` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `DictionaryUtils` | static class | 1 | 0 | 37927 |  |

### `Firebase.Internal` — 3 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `FirebaseInterops` | static class | 11 | 17 | 284299 |  |
| `HttpHelpers` | static class | 2 | 0 | 285759 |  |
| `HttpRequestExceptionExtensions` | static class | 1 | 0 | 286157 |  |

### `InterplanetaryModule` — 6 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `AtmosphericFlameModule` | class | 3 | 3 | 39738 |  |
| `BalloonModule` | class | 12 | 14 | 39827 |  |
| `FlapModule` | class | 4 | 8 | 40506 |  |
| `GravityRingModule` | class | 3 | 8 | 40668 |  |
| `RepeatMoveModule` | class | 3 | 6 | 40845 |  |
| `SurfaceShadingModule` | class | 3 | 5 | 41012 |  |

### `ModLoader` — 11 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `AssetPackMod` | class | 5 | 7 | 41438 |  |
| `IMod` | interface | 4 | 0 | 42698 |  |
| `IUnloadableMod` | interface | 1 | 0 | 42746 |  |
| `Mod` | abstract class | 14 | 2 | 42761 |  |
| `ModKeybindings` | abstract class | 13 | 1 | 42951 |  |
| `TexturePackMod` | class | 1 | 0 | 43199 |  |
| `Loader` | class | 11 | 4 | 43220 | H |
| `ModLoader` | class | 3 | 1 | 44107 | H |
| `ModsSettings` | class | 6 | 2 | 44158 |  |
| &nbsp;&nbsp;↳ `ModsSettings/Data` | class | 1 | 4 | 44269 |  |
| `PackData` | class | 2 | 6 | 44308 |  |

### `ModLoader.Helpers` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `SceneHelper` | static class | 1 | 10 | 44364 | H |

### `ModLoader.IO` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Console` | class | 14 | 11 | 45504 |  |

### `ModLoader.UI` — 4 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `ModsListElement` | class | 4 | 10 | 44413 |  |
| &nbsp;&nbsp;↳ `ModsListElement/ModData` | struct | 0 | 8 | 44711 |  |
| &nbsp;&nbsp;↳ `ModsListElement/ModType` | enum | 0 | 5 | 44725 |  |
| `ModsMenu` | class | 13 | 5 | 44968 |  |

### `Notifications` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `NotificationUtilities` | static class | 0 | 0 | 41429 |  |

### `Parts` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `PartVisualizer` | class | 1 | 9 | 39605 |  |

### `Parts.Transform` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `CraftFlipModule` | class | 4 | 1 | 39635 |  |

### `SFS` — 28 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Base` | static class | 0 | 9 | 46080 |  |
| `BaseAssigner` | class | 2 | 9 | 46098 |  |
| `SceneLoader` | class | 18 | 9 | 46165 | H |
| &nbsp;&nbsp;↳ `SceneLoader/Settings` | class | 1 | 3 | 46600 |  |
| `CameraRotator` | class | 2 | 2 | 47193 |  |
| `PostProcessing` | class | 4 | 10 | 47237 |  |
| `InteriorManager` | class | 5 | 5 | 47497 |  |
| `RenderSortingManager` | class | 8 | 4 | 47626 |  |
| `RenderSortingModule` | class | 6 | 7 | 47844 |  |
| &nbsp;&nbsp;↳ `RenderSortingModule/SortingMode` | enum | 0 | 5 | 48037 |  |
| `VideoSettings` | class | 22 | 15 | 48053 |  |
| &nbsp;&nbsp;↳ `VideoSettings/Data` | class | 1 | 7 | 48714 |  |
| `VideoSettingsComponent` | class | 4 | 5 | 48883 |  |
| `VideoSettingsPC` | class | 19 | 16 | 48999 |  |
| &nbsp;&nbsp;↳ `VideoSettingsPC/Data` | class | 1 | 9 | 49869 |  |
| `SFS_Translation` | class | 707 | 3 | 49973 |  |
| `TranslationUtility` | static class | 1 | 0 | 64006 |  |
| `MsgCollector` | class | 2 | 1 | 64037 |  |
| `MsgNone` | class | 2 | 0 | 64078 |  |
| `I_MsgLogger` | interface | 1 | 0 | 64110 | H |
| `FOV_Sync` | class | 2 | 2 | 64125 |  |
| `Polygon` | class | 6 | 2 | 64183 |  |
| `ConvexPolygon` | class | 9 | 2 | 64513 |  |
| `TimeEvent` | class | 3 | 3 | 64996 |  |
| `UV_Utility` | static class | 4 | 0 | 65085 |  |
| `Selector` | class | 5 | 2 | 65603 |  |
| `ShootingStar` | class | 3 | 2 | 65795 |  |
| `ShootingStarManager` | class | 3 | 9 | 65895 |  |

### `SFS.Analytics` — 2 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `AnalyticsUtility` | static class | 5 | 0 | 283324 |  |
| `FbRemoteSettings` | class | 15 | 11 | 283720 |  |

### `SFS.Audio` — 13 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `MusicPlaylist` | class | 3 | 3 | 281680 |  |
| &nbsp;&nbsp;↳ `MusicPlaylist/OnStart` | enum | 0 | 3 | 281737 |  |
| &nbsp;&nbsp;↳ `MusicPlaylist/OnEnd` | enum | 0 | 3 | 281746 |  |
| `MusicTrack` | class | 1 | 4 | 281760 |  |
| &nbsp;&nbsp;↳ `MusicTrack/OnTrackEnd` | enum | 0 | 3 | 281790 |  |
| `MusicPlaylistPlayer` | class | 12 | 6 | 281804 |  |
| `Sound` | class | 1 | 5 | 282196 |  |
| `SoundEffect` | class | 3 | 1 | 282245 |  |
| `SoundPlayer` | class | 8 | 9 | 282303 |  |
| `PlayingSoundEffect3D` | class | 7 | 2 | 282733 |  |
| `PlayingSoundEffect2D` | class | 2 | 2 | 283052 |  |
| `AudioSettings` | class | 7 | 7 | 283141 |  |
| &nbsp;&nbsp;↳ `AudioSettings/Data` | class | 1 | 2 | 283291 |  |

### `SFS.Builds` — 38 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `UIDepthSorted` | class | 4 | 3 | 86148 |  |
| `AreaSelect` | class | 11 | 6 | 86246 |  |
| `Blueprint` | class | 4 | 6 | 86743 | H |
| `BuildCamera` | class | 10 | 9 | 86879 |  |
| `BuildGrid` | class | 21 | 6 | 87186 |  |
| &nbsp;&nbsp;↳ `BuildGrid/PartCollider` | class | 2 | 2 | 88587 |  |
| `BuildManager` | class | 37 | 21 | 88932 |  |
| &nbsp;&nbsp;↳ `BuildManager/ExampleRocket` | class | 1 | 2 | 90670 |  |
| `Blueprint_Saving` | class | 15 | 0 | 91244 |  |
| `BuildMenus` | class | 26 | 22 | 91935 |  |
| `BuildOrientation` | class | 6 | 6 | 93387 |  |
| `BuildSelector` | class | 8 | 7 | 93573 |  |
| `BuildState` | class | 12 | 5 | 94034 |  |
| `BuildStatsDrawer` | class | 11 | 10 | 94801 |  |
| `ExpandMenu` | class | 5 | 2 | 95513 |  |
| `GridSize` | class | 7 | 10 | 95622 |  |
| `HoldGrid` | class | 33 | 19 | 96037 |  |
| &nbsp;&nbsp;↳ `HoldGrid/Data` | class | 2 | 4 | 98752 |  |
| &nbsp;&nbsp;↳ `HoldGrid/GridPointData` | class | 1 | 2 | 98817 |  |
| `PartGrid` | class | 8 | 3 | 99171 |  |
| `PickCategoriesMenu` | class | 7 | 9 | 99384 |  |
| `PickCategory` | class | 1 | 1 | 99862 |  |
| `SkinMenu` | class | 9 | 6 | 99886 |  |
| `SkinMenuButton` | class | 2 | 3 | 100547 |  |
| `PickCategoryUI` | class | 2 | 5 | 100630 |  |
| `PickGridIcon` | class | 2 | 3 | 100671 |  |
| `PickGridPositioner` | class | 6 | 8 | 100752 |  |
| `PickGridUI` | class | 13 | 17 | 100881 |  |
| &nbsp;&nbsp;↳ `PickGridUI/CategoryParts` | class | 1 | 2 | 101803 |  |
| `Undo` | class | 21 | 7 | 102315 |  |
| &nbsp;&nbsp;↳ `Undo/Step` | class | 1 | 2 | 103446 |  |
| &nbsp;&nbsp;↳ `Undo/AddPart` | class | 1 | 5 | 103472 |  |
| &nbsp;&nbsp;↳ `Undo/AddPartToStage` | class | 1 | 5 | 103594 |  |
| &nbsp;&nbsp;↳ `Undo/AddStage` | class | 1 | 4 | 103632 |  |
| &nbsp;&nbsp;↳ `Undo/OtherAction` | class | 1 | 1 | 103677 |  |
| &nbsp;&nbsp;↳ `Undo/OtherAction/Type` | enum | 0 | 5 | 103697 | H |
| &nbsp;&nbsp;↳ `Undo/ActionBase` | abstract class | 1 | 0 | 103710 |  |
| &nbsp;&nbsp;↳ `Undo/GridType` | enum | 0 | 4 | 103728 |  |

### `SFS.Cameras` — 4 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `ActiveCamera` | class | 6 | 2 | 143304 |  |
| `CameraManager` | class | 10 | 7 | 143418 |  |
| `CameraManager_Local` | class | 2 | 0 | 143754 |  |
| `RotateToCamera` | class | 2 | 3 | 143788 |  |

### `SFS.Career` — 19 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `AllowPerMode` | class | 2 | 2 | 76715 |  |
| `CareerState` | class | 22 | 4 | 76775 |  |
| `TreeComponent` | class | 7 | 10 | 77587 |  |
| &nbsp;&nbsp;↳ `TreeComponent/Root` | class | 1 | 2 | 77832 | H |
| `TT_Builder` | class | 5 | 4 | 78567 |  |
| &nbsp;&nbsp;↳ `TT_Builder/TT_Element` | class | 11 | 6 | 79122 |  |
| `TT_Creator` | class | 9 | 8 | 79597 |  |
| `I_TechTreeData` | interface | 4 | 0 | 80794 |  |
| `TechTreeData_Static` | static class | 1 | 0 | 80846 |  |
| `TT_Info` | class | 7 | 3 | 80891 |  |
| `TT_InfoData` | class | 6 | 2 | 81013 |  |
| `TT_PartPackData` | class | 5 | 4 | 81122 |  |
| `TT_Parts` | class | 8 | 7 | 81230 |  |
| `TT_Upgrade` | class | 8 | 6 | 81704 |  |
| `TT_UpgradeData` | class | 6 | 3 | 81927 |  |
| `AstronautState` | class | 13 | 4 | 82038 |  |
| &nbsp;&nbsp;↳ `AstronautState/State` | enum | 0 | 6 | 82523 |  |
| `HubManager` | class | 18 | 23 | 82851 |  |
| `HubView` | class | 1 | 0 | 84299 |  |

### `SFS.Core` — 5 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `SecurePlayerPrefs` | static class | 2 | 0 | 112451 |  |
| `Encryptor` | static class | 8 | 1 | 112495 |  |
| `SecurityMode` | enum | 0 | 3 | 112871 |  |
| `ActionQueue` | class | 6 | 3 | 112883 |  |
| `Links` | static class | 1 | 0 | 113069 |  |

### `SFS.IO` — 7 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `BasePath` | abstract class | 6 | 1 | 221472 |  |
| `FilePath` | class | 19 | 1 | 221617 |  |
| `FolderPath` | class | 19 | 0 | 222128 |  |
| `OrderedPathList` | class | 6 | 3 | 223964 |  |
| `PathUtility` | static class | 5 | 0 | 224355 |  |
| `SettingsBase`&lt;1&gt; | abstract class | 6 | 1 | 224619 |  |
| `DisableSavingReceiver` | class | 1 | 1 | 224741 |  |

### `SFS.Input` — 27 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `InputManager` | class | 16 | 3 | 224763 |  |
| &nbsp;&nbsp;↳ `InputManager/InputState` | class | 1 | 6 | 225699 |  |
| `OnInputStartData` | class | 1 | 2 | 225795 |  |
| `OnInputStayData` | class | 1 | 3 | 225824 |  |
| `OnInputEndData` | class | 2 | 3 | 225857 |  |
| `OnTouchLongClickData` | class | 1 | 1 | 225920 |  |
| `OnNotStationary` | class | 1 | 1 | 225945 |  |
| `InputType` | enum | 0 | 4 | 225970 |  |
| `TouchPosition` | class | 2 | 1 | 225983 |  |
| `DragData` | class | 2 | 1 | 226039 |  |
| `ZoomData` | class | 1 | 2 | 226110 |  |
| `TouchElements` | static class | 9 | 2 | 226139 |  |
| `I_Touchable` | interface | 11 | 0 | 226641 |  |
| `InputMask2D` | class | 3 | 1 | 226726 |  |
| `ScreenManager` | class | 12 | 5 | 226795 |  |
| `Screen_Base` | abstract class | 7 | 1 | 227069 |  |
| `Screen_Game` | class | 17 | 10 | 227171 |  |
| `KeysNode` | class | 6 | 4 | 227465 |  |
| `Axis` | class | 4 | 3 | 227873 |  |
| `Screen_Menu` | abstract class | 8 | 1 | 228061 |  |
| `CloseMode` | enum | 0 | 4 | 228251 |  |
| `TextBox` | class | 15 | 10 | 228264 |  |
| `KeyBinder` | class | 11 | 6 | 229340 |  |
| `KeybindingsPC` | class | 11 | 7 | 229753 |  |
| &nbsp;&nbsp;↳ `KeybindingsPC/Data` | class | 1 | 21 | 230267 |  |
| &nbsp;&nbsp;↳ `KeybindingsPC/Key` | class | 7 | 2 | 230510 |  |
| `I_Key` | interface | 3 | 0 | 230636 |  |

### `SFS.Logs` — 13 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Challenge` | class | 4 | 9 | 73480 | H |
| `ChallengeStep` | abstract class | 4 | 1 | 74974 |  |
| `Step_Height` | class | 2 | 2 | 75036 |  |
| `Step_Downrange` | class | 2 | 1 | 75088 |  |
| `Step_Orbit` | class | 2 | 1 | 75148 |  |
| `Step_Land` | class | 2 | 0 | 75195 |  |
| `Step_Impact` | class | 2 | 1 | 75244 |  |
| `Step_Any_Landmarks` | class | 3 | 1 | 75277 |  |
| `MultiStep` | class | 3 | 1 | 75472 |  |
| `Difficulty` | enum | 0 | 5 | 75676 | H |
| `LogsModule` | class | 14 | 5 | 75690 |  |
| `LogType` | enum | 0 | 13 | 76662 |  |
| `LogId` | struct | 1 | 3 | 76684 |  |

### `SFS.Navigation` — 11 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Intersection` | static class | 7 | 0 | 66038 |  |
| `Iterator_Velocity` | class | 4 | 0 | 66597 |  |
| &nbsp;&nbsp;↳ `Iterator_Velocity/GetSample` | delegate | 4 | 0 | 66888 |  |
| `Iterator_Orbit` | class | 5 | 3 | 66931 |  |
| `Iterator` | class | 4 | 3 | 67422 |  |
| &nbsp;&nbsp;↳ `Iterator/Feedback`&lt;1&gt; | delegate | 4 | 0 | 67501 |  |
| &nbsp;&nbsp;↳ `Iterator/Valid`&lt;1&gt; | delegate | 4 | 0 | 67539 |  |
| `Basic` | static class | 5 | 0 | 67582 |  |
| `Escape` | static class | 6 | 0 | 68308 |  |
| `Utility` | static class | 1 | 0 | 69565 |  |
| &nbsp;&nbsp;↳ `Utility/FlybyTime` | class | 4 | 2 | 69613 |  |

### `SFS.Parsers.Constructed` — 9 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Compute` | static class | 4 | 0 | 115724 | H |
| &nbsp;&nbsp;↳ `Compute/Add` | class | 2 | 0 | 116446 |  |
| &nbsp;&nbsp;↳ `Compute/Subtract` | class | 2 | 0 | 116485 |  |
| &nbsp;&nbsp;↳ `Compute/Multiply` | class | 2 | 0 | 116524 |  |
| &nbsp;&nbsp;↳ `Compute/Divide` | class | 2 | 0 | 116563 |  |
| &nbsp;&nbsp;↳ `Compute/Operator` | abstract class | 2 | 2 | 116602 |  |
| &nbsp;&nbsp;↳ `Compute/Number` | class | 3 | 1 | 116633 |  |
| &nbsp;&nbsp;↳ `Compute/Variable` | class | 2 | 2 | 116688 |  |
| &nbsp;&nbsp;↳ `Compute/I_Node` | interface | 1 | 0 | 116730 |  |

### `SFS.Parsers.Ini` — 5 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `IniConverter` | class | 11 | 2 | 114097 |  |
| &nbsp;&nbsp;↳ `IniConverter/StringReader` | struct | 10 | 2 | 114669 |  |
| `IniDataEnv` | class | 6 | 2 | 115406 |  |
| &nbsp;&nbsp;↳ `IniDataEnv/Value` | class | 3 | 4 | 115535 |  |
| `IniDataSection` | class | 4 | 4 | 115589 |  |

### `SFS.Parsers.Json` — 5 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `ExclusionList` | class | 3 | 1 | 113356 |  |
| `JsonWrapper` | static class | 7 | 1 | 113505 |  |
| &nbsp;&nbsp;↳ `JsonWrapper/VersionedData`&lt;1&gt; | class | 1 | 1 | 113740 |  |
| `LegacyNameAttribute` | class | 1 | 1 | 113764 |  |
| `MainContractResolver` | class | 2 | 0 | 113791 |  |

### `SFS.Parsers.Json.Exclusions` — 3 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `BaseExclusion` | abstract class | 2 | 0 | 113865 |  |
| `Exclusion`&lt;1&gt; | class | 2 | 1 | 113893 |  |
| `Inclusion`&lt;1&gt; | class | 2 | 1 | 113995 |  |

### `SFS.Parsers.Regex` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `SimpleRegex` | class | 10 | 2 | 113101 |  |

### `SFS.Parts` — 32 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `PartsLoader` | class | 9 | 8 | 230665 |  |
| `OnPartNotOwned` | enum | 0 | 4 | 231512 |  |
| `CustomAssetsLoader` | static class | 5 | 3 | 231525 |  |
| `CustomAssetsPacksLoader` | static class | 2 | 0 | 231855 |  |
| &nbsp;&nbsp;↳ `CustomAssetsPacksLoader/AssetBundlePack` | class | 2 | 5 | 232396 |  |
| `TextureLoader` | static class | 3 | 2 | 233410 |  |
| &nbsp;&nbsp;↳ `TextureLoader/T2DConverter` | class | 3 | 0 | 233649 |  |
| &nbsp;&nbsp;↳ `TextureLoader/ShadowTextureConverter` | class | 3 | 0 | 233736 |  |
| &nbsp;&nbsp;↳ `TextureLoader/SpriteConverter` | class | 3 | 0 | 233783 |  |
| `WheelModule` | class | 9 | 8 | 235157 | H |
| `Mass_Calculator` | class | 8 | 4 | 235824 | H |
| `Part` | class | 30 | 20 | 236080 | H |
| `UsePartUnityEvent` | class | 1 | 0 | 238198 |  |
| `UsePartData` | class | 1 | 3 | 238219 |  |
| &nbsp;&nbsp;↳ `UsePartData/SharedData` | class | 1 | 3 | 238247 |  |
| `PartHolder` | class | 18 | 8 | 238276 | H |
| `PartSave` | class | 5 | 8 | 239253 | H |
| `BasicTexture` | class | 1 | 3 | 239517 |  |
| &nbsp;&nbsp;↳ `BasicTexture/Layer` | class | 2 | 3 | 239538 |  |
| `ColorTexture` | class | 2 | 3 | 239623 |  |
| `Segment` | class | 1 | 2 | 239667 |  |
| `TextureAssetBase` | abstract class | 4 | 2 | 239692 |  |
| `PartTexture` | class | 10 | 10 | 239842 |  |
| `PerValueTexture` | class | 1 | 2 | 240568 |  |
| `BorderData` | class | 2 | 3 | 240591 |  |
| `CenterData` | class | 2 | 5 | 240636 |  |
| &nbsp;&nbsp;↳ `CenterData/CenterMode` | enum | 0 | 4 | 240683 |  |
| `VerticalSizeMode` | enum | 0 | 3 | 240698 |  |
| `ShadowTexture` | class | 2 | 1 | 240710 |  |
| `ShapeTexture` | class | 2 | 4 | 240750 |  |
| `Part_Utility` | static class | 17 | 0 | 240795 |  |
| `PartHit` | class | 1 | 2 | 242098 |  |

### `SFS.Parts.Modules` — 163 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `FlameModule` | class | 7 | 13 | 242127 |  |
| `BuildColor` | class | 2 | 1 | 243005 |  |
| `ColorByScene` | class | 2 | 3 | 243049 |  |
| `ColorModule` | abstract class | 2 | 0 | 243116 |  |
| `CompositeColor` | class | 2 | 1 | 243144 |  |
| `CustomColor` | class | 2 | 1 | 243210 |  |
| `SeparatorColor` | class | 5 | 5 | 243247 |  |
| `FramingColliderBounds` | class | 1 | 1 | 243366 |  |
| `FramingOverwrite` | class | 2 | 2 | 243388 |  |
| `LaunchColliderBounds` | class | 1 | 1 | 243439 |  |
| `FlowModule` | class | 11 | 3 | 243461 | H |
| &nbsp;&nbsp;↳ `FlowModule/Flow` | class | 16 | 8 | 243876 | H |
| &nbsp;&nbsp;↳ `FlowModule/State_Local` | class | 2 | 0 | 244639 |  |
| &nbsp;&nbsp;↳ `FlowModule/SourceMode` | enum | 0 | 4 | 244670 |  |
| &nbsp;&nbsp;↳ `FlowModule/FlowType` | enum | 0 | 3 | 244680 |  |
| &nbsp;&nbsp;↳ `FlowModule/FlowState` | enum | 0 | 6 | 244689 |  |
| `FuelPipeModule` | class | 7 | 5 | 244786 | H |
| `ResourceModule` | class | 25 | 13 | 245548 | H |
| `ResourceType` | class | 1 | 5 | 246649 | H |
| `AdaptModule` | class | 19 | 8 | 246686 |  |
| &nbsp;&nbsp;↳ `AdaptModule/Point` | class | 1 | 16 | 248045 |  |
| &nbsp;&nbsp;↳ `AdaptModule/TriggerType` | enum | 0 | 3 | 248081 |  |
| &nbsp;&nbsp;↳ `AdaptModule/ReceiverType` | enum | 0 | 3 | 248090 |  |
| &nbsp;&nbsp;↳ `AdaptModule/PriorityType` | enum | 0 | 6 | 248099 |  |
| &nbsp;&nbsp;↳ `AdaptModule/ExtraType` | class | 1 | 3 | 248111 |  |
| `AdaptTriggerModule` | class | 4 | 3 | 248166 |  |
| `AdaptTriggerPoint` | class | 3 | 13 | 248298 |  |
| `ColliderModule` | class | 7 | 6 | 248385 |  |
| &nbsp;&nbsp;↳ `ColliderModule/ImpactTolerance` | enum | 0 | 5 | 248680 |  |
| `DockingPortModule` | class | 17 | 12 | 248764 | H |
| `DockingPortTrigger` | class | 4 | 4 | 249687 |  |
| `LES_Module` | class | 6 | 2 | 249811 |  |
| `MagnetModule` | class | 8 | 2 | 250369 |  |
| &nbsp;&nbsp;↳ `MagnetModule/Point` | class | 1 | 2 | 250923 |  |
| `BaseMesh` | abstract class | 12 | 5 | 250975 |  |
| `PartTex` | struct | 1 | 6 | 251656 |  |
| `PipeMesh` | class | 12 | 10 | 251690 |  |
| `Textures` | class | 4 | 5 | 252966 |  |
| &nbsp;&nbsp;↳ `Textures/TextureKey` | class | 1 | 2 | 253262 |  |
| &nbsp;&nbsp;↳ `Textures/TextureSelector` | class | 1 | 2 | 253282 |  |
| &nbsp;&nbsp;↳ `Textures/WidthMode` | enum | 0 | 3 | 253302 |  |
| `Colors` | class | 2 | 3 | 253325 |  |
| &nbsp;&nbsp;↳ `Colors/ColorKey` | class | 1 | 2 | 253439 |  |
| &nbsp;&nbsp;↳ `Colors/ColorSelector` | class | 2 | 3 | 253459 |  |
| &nbsp;&nbsp;↳ `Colors/ColorSelector/Type` | enum | 0 | 3 | 253501 | H |
| `Mode` | enum | 0 | 3 | 253517 |  |
| `Splittable` | abstract class | 5 | 0 | 253529 |  |
| `Points_Splittable` | class | 4 | 1 | 253686 |  |
| `UV_Splittable` | class | 3 | 1 | 253888 |  |
| `Color_Splittable` | class | 3 | 1 | 254088 |  |
| `MeshData` | class | 1 | 6 | 254296 |  |
| `PolygonMesh` | class | 9 | 9 | 254354 |  |
| &nbsp;&nbsp;↳ `PolygonMesh/UVOptions` | enum | 0 | 4 | 254907 |  |
| &nbsp;&nbsp;↳ `PolygonMesh/ColorType` | enum | 0 | 3 | 254917 |  |
| `SkinModule` | class | 10 | 8 | 254931 |  |
| `ModelPolygon` | class | 8 | 4 | 255511 |  |
| `ModelSetup` | class | 12 | 14 | 255648 |  |
| `ModelSurface` | class | 5 | 2 | 256018 |  |
| &nbsp;&nbsp;↳ `ModelSurface/Surface` | class | 1 | 2 | 256125 |  |
| `DisableOnNoFlow` | class | 2 | 4 | 256153 |  |
| `ExternalVariableModule` | class | 5 | 26 | 256283 |  |
| `MathModule` | class | 3 | 3 | 256730 |  |
| &nbsp;&nbsp;↳ `MathModule/NumericCalculator` | struct | 1 | 2 | 256862 |  |
| &nbsp;&nbsp;↳ `MathModule/BooleanComparisonCalculator` | struct | 2 | 7 | 256946 |  |
| &nbsp;&nbsp;↳ `MathModule/BooleanComparisonCalculator/Condition` | enum | 0 | 6 | 257205 |  |
| &nbsp;&nbsp;↳ `MathModule/BooleanOperatorCalculator` | struct | 2 | 4 | 257219 |  |
| &nbsp;&nbsp;↳ `MathModule/BooleanOperatorCalculator/Operator` | enum | 0 | 7 | 257386 |  |
| `MultiStepToggleSequenceModule` | class | 4 | 2 | 257406 |  |
| `VariableConverterModule` | class | 3 | 6 | 257501 |  |
| &nbsp;&nbsp;↳ `VariableConverterModule/BoolToDouble` | struct | 1 | 2 | 257838 |  |
| &nbsp;&nbsp;↳ `VariableConverterModule/DoubleToBool` | struct | 1 | 3 | 257869 |  |
| &nbsp;&nbsp;↳ `VariableConverterModule/DoubleToString` | struct | 1 | 2 | 257905 |  |
| &nbsp;&nbsp;↳ `VariableConverterModule/StringToDouble` | struct | 1 | 2 | 257935 |  |
| &nbsp;&nbsp;↳ `VariableConverterModule/BoolToString` | struct | 1 | 5 | 257968 |  |
| &nbsp;&nbsp;↳ `VariableConverterModule/StringToBool` | struct | 1 | 4 | 258022 |  |
| `OwnModule` | class | 3 | 1 | 258119 |  |
| &nbsp;&nbsp;↳ `OwnModule/PartPack` | enum | 0 | 4 | 258173 |  |
| `OwnershipState` | enum | 0 | 4 | 258188 |  |
| `Own_Size` | class | 2 | 1 | 258201 |  |
| &nbsp;&nbsp;↳ `Own_Size/AllowedSize` | class | 1 | 2 | 258247 |  |
| `Variants` | class | 1 | 2 | 258324 |  |
| &nbsp;&nbsp;↳ `Variants/Variant` | class | 2 | 3 | 258350 |  |
| &nbsp;&nbsp;↳ `Variants/Variable` | class | 2 | 5 | 258463 |  |
| &nbsp;&nbsp;↳ `Variants/Variable/ValueType` | enum | 0 | 4 | 258527 |  |
| &nbsp;&nbsp;↳ `Variants/PickTag` | class | 1 | 2 | 258539 |  |
| `VariantRef` | class | 14 | 3 | 258564 |  |
| `BoosterModule` | class | 27 | 20 | 259149 | H |
| `DetachModule` | class | 9 | 11 | 260322 | H |
| &nbsp;&nbsp;↳ `DetachModule/DetachData` | struct | 0 | 3 | 260924 |  |
| `EngineModule` | class | 26 | 19 | 261221 | H |
| `ParachuteModule` | class | 9 | 11 | 262464 | H |
| `RcsModule` | class | 19 | 11 | 263099 |  |
| &nbsp;&nbsp;↳ `RcsModule/Thruster` | class | 1 | 2 | 263824 |  |
| `SeparatorBase` | abstract class | 4 | 0 | 263849 |  |
| `SplitModule` | class | 15 | 11 | 264010 |  |
| &nbsp;&nbsp;↳ `SplitModule/Fragment` | class | 1 | 5 | 264914 |  |
| `TorqueModule` | class | 2 | 3 | 265256 | H |
| `CopyPipe` | class | 4 | 1 | 265322 |  |
| `CurvePipe` | class | 6 | 6 | 265450 |  |
| `CustomPipe` | class | 4 | 4 | 265802 |  |
| `EdgePipe` | class | 6 | 4 | 265906 |  |
| `PipeData` | abstract class | 8 | 6 | 266230 |  |
| `Pipe` | class | 4 | 1 | 266883 |  |
| `PipePoint` | class | 6 | 5 | 267025 |  |
| `AdvancedCut` | class | 1 | 1 | 267187 |  |
| &nbsp;&nbsp;↳ `AdvancedCut/Cut` | class | 1 | 2 | 267204 |  |
| `SimplePipe` | class | 4 | 4 | 267236 |  |
| `BoxPolygon` | class | 5 | 2 | 267369 |  |
| `CustomPolygon` | class | 4 | 1 | 267490 |  |
| `PolygonCollider` | class | 4 | 3 | 267570 |  |
| `PolygonData` | abstract class | 13 | 9 | 267787 |  |
| `CustomSurfaces` | class | 6 | 6 | 268103 |  |
| `ComposedSurfaces` | class | 2 | 2 | 268315 |  |
| `PipeSurface` | class | 4 | 5 | 268358 |  |
| `SurfaceCollider` | class | 4 | 1 | 268650 |  |
| `SurfaceData` | abstract class | 8 | 6 | 268763 |  |
| `Surfaces` | class | 3 | 3 | 268970 |  |
| `SurfaceUtility` | static class | 11 | 3 | 269120 |  |
| `BurnMark` | class | 20 | 8 | 270014 |  |
| &nbsp;&nbsp;↳ `BurnMark/Burn` | class | 2 | 5 | 271347 |  |
| &nbsp;&nbsp;↳ `BurnMark/BurnSave` | class | 5 | 5 | 271401 |  |
| &nbsp;&nbsp;↳ `BurnMark/MeshReference` | class | 1 | 2 | 271714 |  |
| &nbsp;&nbsp;↳ `BurnMark/Bounds` | struct | 0 | 4 | 271740 |  |
| `StrutTexModule` | class | 4 | 3 | 271850 |  |
| `ActiveModule` | class | 4 | 2 | 271993 |  |
| `InteriorModule` | class | 4 | 1 | 272084 |  |
| &nbsp;&nbsp;↳ `InteriorModule/LayerType` | enum | 0 | 3 | 272187 |  |
| `MaterialByScene` | class | 2 | 3 | 272201 |  |
| `SceneType` | enum | 0 | 3 | 272265 |  |
| `OrientationModule` | class | 6 | 1 | 272277 |  |
| `Orientation_Local` | class | 2 | 0 | 272448 |  |
| `Orientation` | class | 5 | 3 | 272510 |  |
| `PositionModule` | class | 4 | 1 | 272652 |  |
| `RotationModule` | class | 3 | 1 | 272725 |  |
| `ScaleModule` | class | 3 | 1 | 272785 |  |
| `ActivationSequenceModule` | class | 4 | 2 | 272843 |  |
| `ActivationZoneModule` | class | 2 | 4 | 272931 |  |
| &nbsp;&nbsp;↳ `ActivationZoneModule/Zone` | class | 1 | 2 | 273036 |  |
| `AudioModule` | class | 6 | 7 | 273061 |  |
| `CannotClickModule` | class | 1 | 0 | 273246 |  |
| `CannotStageModule` | class | 1 | 0 | 273267 |  |
| `ControlModule` | class | 1 | 1 | 273288 | H |
| `FlameRandomizer` | class | 2 | 2 | 273310 |  |
| `HeatInfoModule` | class | 2 | 0 | 273366 |  |
| `HeatModule` | class | 12 | 8 | 273416 |  |
| `IsCoveredModule` | class | 2 | 3 | 273663 |  |
| `LinkModule` | class | 3 | 2 | 273721 |  |
| `MassModule` | class | 5 | 3 | 273779 |  |
| `MoveModule` | class | 11 | 6 | 273975 | H |
| `MoveData` | class | 8 | 11 | 274547 |  |
| &nbsp;&nbsp;↳ `MoveData/Type` | enum | 0 | 15 | 274700 | H |
| `MovingMassModule` | class | 4 | 3 | 274726 |  |
| `I_PartMenu` | interface | 1 | 0 | 274807 |  |
| `PartDrawSettings` | class | 2 | 8 | 274822 |  |
| `SeparatorPanel` | class | 7 | 5 | 274891 |  |
| `ToggleModule` | class | 3 | 2 | 275143 | H |
| `VariablesDrawer` | class | 2 | 1 | 275390 |  |
| &nbsp;&nbsp;↳ `VariablesDrawer/DrawElement` | class | 3 | 11 | 275596 |  |
| &nbsp;&nbsp;↳ `VariablesDrawer/VariableType` | enum | 0 | 4 | 275680 |  |
| &nbsp;&nbsp;↳ `VariablesDrawer/FloatDrawType` | enum | 0 | 3 | 275690 |  |
| &nbsp;&nbsp;↳ `VariablesDrawer/StringDrawType` | enum | 0 | 3 | 275699 |  |
| `EffectModule` | class | 2 | 3 | 276242 |  |
| `ParticleModule` | class | 6 | 5 | 276302 |  |

### `SFS.Platform` — 3 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `PlatformManager` | class | 2 | 2 | 86026 |  |
| `PlatformSpecific` | class | 1 | 2 | 86113 |  |
| `PlatformType` | enum | 0 | 3 | 86136 |  |

### `SFS.Sharing` — 10 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `RequestUtil` | class | 11 | 4 | 106083 |  |
| &nbsp;&nbsp;↳ `RequestUtil/InitResult` | enum | 0 | 3 | 106373 |  |
| `SharingRequester` | class | 15 | 7 | 106429 |  |
| &nbsp;&nbsp;↳ `SharingRequester/RocketURL` | class | 1 | 1 | 107103 |  |
| &nbsp;&nbsp;↳ `SharingRequester/RocketsTabManager` | class | 8 | 7 | 107122 |  |
| &nbsp;&nbsp;↳ `SharingRequester/RocketsPage` | class | 1 | 2 | 107520 |  |
| &nbsp;&nbsp;↳ `SharingRequester/RocketData` | class | 3 | 13 | 107540 |  |
| &nbsp;&nbsp;↳ `SharingRequester/VoteResult` | class | 1 | 1 | 107607 |  |
| `ReturnCodes` | enum | 0 | 7 | 108364 |  |
| `InitializationResult` | enum | 0 | 4 | 108380 |  |

### `SFS.Stats` — 8 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `LogManager` | class | 9 | 4 | 69745 |  |
| `Branch` | class | 2 | 5 | 70115 |  |
| `StatsRecorder` | class | 31 | 7 | 70185 | H |
| &nbsp;&nbsp;↳ `StatsRecorder/Tracker` | class | 12 | 8 | 71704 |  |
| &nbsp;&nbsp;↳ `StatsRecorder/Tracker/State_Orbit` | enum | 0 | 7 | 72370 |  |
| &nbsp;&nbsp;↳ `StatsRecorder/Tracker/State_Atmosphere` | enum | 0 | 4 | 72385 |  |
| &nbsp;&nbsp;↳ `StatsRecorder/EventType` | enum | 0 | 11 | 72399 |  |
| `ChallengeRecorder` | class | 9 | 4 | 72460 | H |

### `SFS.Translations` — 18 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `LanguageSettings` | class | 10 | 6 | 108393 |  |
| `Field` | class | 15 | 1 | 108934 | H |
| &nbsp;&nbsp;↳ `Field/Builder` | class | 7 | 2 | 109226 |  |
| `FontSetter` | class | 6 | 5 | 109506 |  |
| `Loc` | static class | 2 | 4 | 109695 |  |
| `SubExport` | class | 2 | 4 | 109792 |  |
| `TranslationEditorHelper` | static class | 2 | 0 | 109993 |  |
| `FieldReference` | class | 6 | 3 | 110056 |  |
| `TranslationManager` | class | 13 | 8 | 110233 |  |
| `LanguageReference` | class | 2 | 3 | 111198 |  |
| `TranslationSelector` | class | 5 | 1 | 111244 |  |
| `TranslationVariable` | class | 4 | 3 | 111416 |  |
| `TranslationSerialization` | static class | 6 | 0 | 111551 |  |
| `Unexported` | class | 1 | 0 | 112293 |  |
| `MarkAsSub` | class | 1 | 0 | 112314 |  |
| `LocSpace` | class | 1 | 2 | 112335 |  |
| `Group` | class | 2 | 3 | 112366 |  |
| `Documentation` | class | 1 | 3 | 112416 |  |

### `SFS.Tutorials` — 6 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `FailureMenu` | class | 12 | 9 | 103806 |  |
| `PartShowcaseModule` | class | 2 | 1 | 104444 |  |
| `Tutorial_Base` | abstract class | 6 | 1 | 104478 |  |
| &nbsp;&nbsp;↳ `Tutorial_Base/TimeDelay` | class | 3 | 3 | 104618 |  |
| `Tutorial_Build` | class | 9 | 8 | 104820 |  |
| `Tutorial_World` | class | 2 | 4 | 105678 |  |

### `SFS.Tween` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `TweenManager` | static class | 15 | 1 | 84320 |  |

### `SFS.UI` — 96 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `DevelopmentMenu` | class | 1 | 0 | 116761 |  |
| `DownloadMenu` | class | 7 | 1 | 116782 |  |
| `ImageTools` | static class | 3 | 0 | 117440 |  |
| `ElementGenerator` | class | 5 | 3 | 117513 |  |
| `MenuGenerator` | static class | 7 | 0 | 117846 |  |
| `ButtonBuilder` | class | 5 | 5 | 118582 |  |
| `TextBuilder` | class | 3 | 1 | 118764 |  |
| `NewElementBuilder`&lt;1&gt; | abstract class | 6 | 6 | 118819 |  |
| `ElementBuilder` | abstract class | 3 | 0 | 118971 |  |
| `SizeSyncerBuilder` | class | 4 | 3 | 119018 |  |
| &nbsp;&nbsp;↳ `SizeSyncerBuilder/Carrier` | class | 1 | 1 | 119125 |  |
| `DraggableWindowModule` | class | 6 | 3 | 119149 |  |
| `AttachableStatsMenu` | class | 5 | 2 | 119322 |  |
| `AttachWithArrow` | class | 14 | 13 | 119830 |  |
| &nbsp;&nbsp;↳ `AttachWithArrow/Placement` | enum | 0 | 7 | 120852 |  |
| `Button` | class | 29 | 27 | 120926 |  |
| `HoldUnityEvent` | class | 1 | 0 | 121893 |  |
| `ClickUnityEvent` | class | 1 | 0 | 121914 |  |
| `CheatsDrawer` | class | 5 | 1 | 121935 |  |
| `CycleSelector` | class | 6 | 4 | 122112 |  |
| `IconButton` | class | 4 | 3 | 122262 |  |
| `LoadMenuElement` | class | 1 | 4 | 122354 |  |
| `MsgDrawer` | class | 6 | 6 | 122379 | H |
| `RadioButton` | class | 6 | 3 | 122532 |  |
| `RadioGroup` | class | 4 | 3 | 122700 |  |
| `Raycastable` | class | 6 | 2 | 122792 |  |
| `RelativeSizeFitter` | class | 9 | 8 | 122883 |  |
| &nbsp;&nbsp;↳ `RelativeSizeFitter/Reference` | class | 1 | 2 | 123233 |  |
| `ReorderingGroup` | class | 7 | 15 | 123330 |  |
| `ElementLayout` | enum | 0 | 4 | 123654 |  |
| `ReorderingModule` | class | 8 | 4 | 123667 |  |
| `ScrollElement` | class | 19 | 15 | 124313 |  |
| &nbsp;&nbsp;↳ `ScrollElement/ClampType` | enum | 0 | 4 | 125036 |  |
| `SizeSyncGroup` | class | 2 | 2 | 125152 |  |
| `SkipUI` | class | 14 | 1 | 125299 |  |
| `TextInputElement` | class | 1 | 3 | 125477 |  |
| `ToggleButton` | class | 7 | 3 | 125501 |  |
| `FillSlider` | class | 5 | 9 | 125658 |  |
| `Menu` | class | 2 | 12 | 125891 |  |
| `BasicMenu` | class | 5 | 2 | 125952 |  |
| `LoadingScreen` | class | 7 | 5 | 126057 |  |
| `LoadMenu` | class | 20 | 16 | 126408 |  |
| `I_SavingBase` | interface | 10 | 0 | 127343 |  |
| `ImportAvailability` | enum | 0 | 4 | 127429 |  |
| `Quicksave_Saving` | class | 11 | 3 | 127442 |  |
| `ReadMenu` | class | 11 | 8 | 128053 |  |
| `ContainerElement` | class | 6 | 3 | 128512 |  |
| `ContainerElementWithScaling` | class | 3 | 4 | 128698 |  |
| `FitBetween` | class | 2 | 4 | 128824 |  |
| &nbsp;&nbsp;↳ `FitBetween/Provider` | struct | 0 | 3 | 129072 |  |
| `HorizontalLayout` | class | 4 | 0 | 129086 |  |
| `LayoutGroup` | abstract class | 17 | 9 | 129484 |  |
| &nbsp;&nbsp;↳ `LayoutGroup/SpaceDistributionMode` | enum | 0 | 4 | 129946 |  |
| `LayoutGroupUpdater` | class | 5 | 2 | 130046 |  |
| `LayoutUtility` | static class | 2 | 0 | 130181 |  |
| `SizeMode` | enum | 0 | 4 | 130385 |  |
| `NewElement` | abstract class | 14 | 8 | 130398 |  |
| &nbsp;&nbsp;↳ `NewElement/Cached`&lt;1&gt; | class | 5 | 4 | 130818 |  |
| `NewSizeSyncGroup` | class | 7 | 5 | 130927 |  |
| `ReadTextContainer` | class | 7 | 7 | 131266 |  |
| `ScaleTextToFit` | class | 8 | 9 | 131486 |  |
| `SettingsMenuSizer` | class | 3 | 2 | 131753 |  |
| `VerticalLayout` | class | 4 | 0 | 131845 |  |
| `ClampSize` | class | 2 | 4 | 132268 |  |
| &nbsp;&nbsp;↳ `ClampSize/OptionalFloat` | class | 3 | 2 | 132351 |  |
| `ForceUpdateLayout` | class | 1 | 1 | 132426 |  |
| `Margin` | class | 1 | 2 | 132448 |  |
| `MultiCycleUI` | class | 1 | 1 | 132471 |  |
| `NewPadding` | class | 1 | 2 | 132496 |  |
| `UIUpdater` | class | 6 | 10 | 132519 |  |
| `MenuElement` | delegate | 4 | 0 | 132705 |  |
| `OptionsMenuDrawer` | class | 5 | 9 | 132746 |  |
| `CancelButton` | enum | 0 | 4 | 133014 |  |
| `BuildMenuBar` | class | 2 | 3 | 133027 |  |
| `ButtonPC` | class | 10 | 10 | 133258 |  |
| `SliderText` | class | 3 | 4 | 133602 |  |
| `Rect_Utility` | static class | 5 | 0 | 133682 |  |
| `Rubberbanding` | static class | 3 | 0 | 133892 |  |
| `ScreenTracker` | class | 3 | 2 | 134123 |  |
| `ScreenOrientation_Local` | class | 2 | 0 | 134194 |  |
| `TextInputMenu` | class | 13 | 9 | 134228 |  |
| `UI_Raycaster` | static class | 3 | 0 | 134664 |  |
| `I_Raycastable` | interface | 2 | 0 | 134894 |  |
| `TextAdapter` | class | 7 | 3 | 134920 |  |
| `TextBoxAdapter` | class | 10 | 3 | 135133 |  |
| `AstronautElement` | class | 1 | 5 | 135367 |  |
| `AstronautMenu` | class | 16 | 9 | 135393 |  |
| `ResourceBar` | class | 2 | 3 | 136051 |  |
| `CreateWorldMenu` | class | 14 | 13 | 136095 |  |
| `HomeManager` | class | 16 | 10 | 136883 |  |
| `ProductThumbnail` | class | 1 | 2 | 138508 |  |
| `ShopManager` | class | 1 | 34 | 138531 |  |
| &nbsp;&nbsp;↳ `ShopManager/BuyButton` | class | 1 | 1 | 138583 |  |
| `ShopManagerMac` | class | 1 | 6 | 138607 |  |
| `WorldElement` | class | 5 | 10 | 138634 |  |
| `WorldsMenu` | class | 18 | 10 | 138875 |  |

### `SFS.UI.ModGUI` — 19 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Builder` | static class | 18 | 2 | 139672 |  |
| &nbsp;&nbsp;↳ `Builder/SceneToAttach` | enum | 0 | 3 | 140586 |  |
| `Box` | class | 7 | 1 | 140706 |  |
| `Button` | class | 10 | 3 | 140902 |  |
| `ButtonWithLabel` | class | 2 | 2 | 141122 |  |
| `Container` | class | 3 | 0 | 141195 |  |
| `TextInput` | class | 10 | 3 | 141304 |  |
| `InputWithLabel` | class | 2 | 2 | 141523 |  |
| `Label` | class | 16 | 1 | 141596 |  |
| `Separator` | class | 2 | 0 | 141885 |  |
| `Slider` | class | 12 | 2 | 141930 |  |
| `Space` | class | 2 | 0 | 142230 |  |
| `Toggle` | class | 4 | 1 | 142275 |  |
| `ToggleWithLabel` | class | 2 | 2 | 142362 |  |
| `WebImage` | class | 12 | 3 | 142435 |  |
| `Window` | class | 17 | 5 | 142671 |  |
| `GUIElement` | abstract class | 9 | 2 | 143096 |  |
| `Type` | enum | 0 | 3 | 143247 | H |
| `ModGUIPrefabsLoader` | class | 1 | 14 | 143259 |  |

### `SFS.Utilities` — 2 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `WorldAddress` | static class | 11 | 1 | 276490 |  |
| `GZipUtility` | static class | 2 | 0 | 277341 |  |

### `SFS.Variables` — 36 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Local_GenericTarget` | class | 2 | 0 | 277470 |  |
| `Obs_Destroyable`&lt;1&gt; | abstract class | 4 | 0 | 277504 |  |
| `I_ObservableMonoBehaviour` | interface | 2 | 0 | 277607 |  |
| `Planet_Local` | class | 2 | 0 | 277634 |  |
| `Double2_Local` | class | 2 | 0 | 277668 |  |
| `Double3_Local` | class | 2 | 0 | 277702 |  |
| `MinMaxRange` | class | 1 | 2 | 277736 |  |
| `SizeRange` | class | 1 | 2 | 277759 |  |
| `Composed_Pipe` | class | 4 | 1 | 277782 |  |
| `Composed_PipePoint` | class | 4 | 2 | 277905 |  |
| `Composed_Rect` | class | 4 | 2 | 277998 |  |
| `Composed_Vector2` | class | 5 | 2 | 278080 |  |
| `Composed_Float` | class | 5 | 2 | 278208 |  |
| `Composed_Double` | class | 4 | 2 | 278388 |  |
| `Composed`&lt;1&gt; | abstract class | 18 | 5 | 278513 | H |
| `Vector2_Local` | class | 2 | 0 | 278920 |  |
| `Float_Local` | class | 3 | 0 | 278954 |  |
| `Double_Local` | class | 2 | 0 | 279003 |  |
| `Int_Local` | class | 2 | 0 | 279037 |  |
| `Bool_Local` | class | 2 | 0 | 279071 |  |
| `String_Local` | class | 2 | 0 | 279105 |  |
| `Obs`&lt;1&gt; | abstract class | 22 | 6 | 279139 | H |
| `Event_Local` | class | 6 | 1 | 279683 |  |
| `Float_Reference` | class | 4 | 0 | 279832 |  |
| `Double_Reference` | class | 4 | 0 | 279898 |  |
| `Bool_Reference` | class | 4 | 0 | 279960 |  |
| `String_Reference` | class | 4 | 0 | 280022 |  |
| `ReferenceVariable`&lt;1&gt; | abstract class | 22 | 8 | 280084 | H |
| `VariableList`&lt;1&gt; | class | 16 | 2 | 280735 |  |
| &nbsp;&nbsp;↳ `VariableList/Variable` | class | 8 | 5 | 281225 |  |
| &nbsp;&nbsp;↳ `VariableList/IVariable` | interface | 2 | 0 | 281473 |  |
| `VariableSave` | class | 1 | 4 | 281556 |  |
| `VariablesModule` | class | 1 | 3 | 281584 |  |
| `DoubleVariableList` | class | 1 | 0 | 281617 |  |
| `BoolVariableList` | class | 1 | 0 | 281638 |  |
| `StringVariableList` | class | 1 | 0 | 281659 |  |

### `SFS.World` — 117 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `CrewModule` | class | 14 | 8 | 152605 |  |
| &nbsp;&nbsp;↳ `CrewModule/Seat` | class | 8 | 5 | 153410 |  |
| `SandboxSettings` | class | 28 | 25 | 154215 |  |
| &nbsp;&nbsp;↳ `SandboxSettings/Data` | class | 1 | 8 | 155121 |  |
| `TeleportMenu` | class | 24 | 25 | 155273 |  |
| &nbsp;&nbsp;↳ `TeleportMenu/Mode` | enum | 0 | 3 | 156582 |  |
| `AstronautManager` | class | 7 | 6 | 156709 |  |
| `Astronaut_EVA` | class | 33 | 26 | 157027 |  |
| `EVA_Resources` | class | 12 | 6 | 158824 |  |
| `Physics` | class | 18 | 6 | 159119 | H |
| `I_Physics` | interface | 8 | 0 | 159884 | H |
| `StaticWorldObject` | class | 5 | 2 | 159963 |  |
| `WorldLoader` | class | 15 | 6 | 160099 |  |
| `WorldLocation` | class | 4 | 3 | 160568 | H |
| `Location` | class | 9 | 4 | 160698 | H |
| `AeroDrawer` | class | 6 | 5 | 160932 |  |
| `TemperatureBar` | class | 1 | 4 | 161316 |  |
| `Aero_Local` | class | 2 | 0 | 161341 |  |
| `ArrowkeysDrawer` | class | 13 | 15 | 161375 | H |
| `EndMissionMenu` | class | 30 | 21 | 162079 |  |
| `State` | class | 6 | 7 | 164317 |  |
| `FlightInfoDrawer` | class | 2 | 6 | 164782 |  |
| `FuelTransferLine` | class | 1 | 2 | 165037 |  |
| `FuelTransferUI` | class | 2 | 3 | 165060 |  |
| `GameMenuLayout_Mobile` | class | 7 | 14 | 165130 |  |
| `GameMenus` | class | 6 | 4 | 165559 |  |
| `LocationDrawer` | class | 4 | 9 | 165718 |  |
| `AngleInfo` | class | 1 | 3 | 166250 |  |
| `ResourceDrawer` | class | 14 | 12 | 166283 |  |
| &nbsp;&nbsp;↳ `ResourceDrawer/I_Resource` | interface | 3 | 0 | 167027 |  |
| `StageUI` | class | 6 | 15 | 168091 |  |
| `StagingDrawer` | class | 39 | 19 | 168464 |  |
| `ThrottleDrawer` | class | 22 | 8 | 170696 |  |
| `VelocityArrowDrawer` | class | 10 | 3 | 171423 |  |
| &nbsp;&nbsp;↳ `VelocityArrowDrawer/Arrow` | class | 3 | 6 | 172212 |  |
| `Atmosphere` | class | 6 | 2 | 172728 |  |
| `FrontClouds` | class | 4 | 0 | 172948 |  |
| `Rings` | class | 4 | 0 | 173171 |  |
| `RockSelector` | class | 22 | 3 | 173458 |  |
| `TerrainSampler` | static class | 2 | 0 | 173979 |  |
| &nbsp;&nbsp;↳ `TerrainSampler/TerrainSample` | class | 2 | 4 | 174242 |  |
| &nbsp;&nbsp;↳ `TerrainSampler/Executor` | class | 2 | 1 | 174308 |  |
| &nbsp;&nbsp;↳ `TerrainSampler/Executor/SampleCommand` | delegate | 4 | 0 | 174383 |  |
| &nbsp;&nbsp;↳ `TerrainSampler/Compiler` | static class | 8 | 0 | 174423 |  |
| `WorldEnvironment` | class | 12 | 13 | 175601 |  |
| `Environment` | class | 1 | 6 | 177044 |  |
| `EffectManager` | class | 8 | 5 | 177071 |  |
| &nbsp;&nbsp;↳ `EffectManager/Effect` | class | 2 | 2 | 177263 |  |
| `WorldEffect` | class | 4 | 1 | 177510 |  |
| `Flag` | class | 11 | 4 | 177594 |  |
| `GameCamerasManager` | class | 8 | 6 | 178056 |  |
| `GameManager` | class | 31 | 9 | 178293 | H |
| `ElementDrawer` | class | 9 | 5 | 180567 |  |
| &nbsp;&nbsp;↳ `ElementDrawer/Element` | class | 1 | 4 | 181187 |  |
| &nbsp;&nbsp;↳ `ElementDrawer/TextElement` | class | 1 | 2 | 181209 |  |
| `GameSelector` | class | 15 | 12 | 181234 |  |
| &nbsp;&nbsp;↳ `GameSelector/Selectable_Local` | class | 2 | 0 | 182060 |  |
| `MapPlayer` | abstract class | 11 | 1 | 182159 |  |
| `SelectableObject` | abstract class | 22 | 1 | 182376 |  |
| `Arrowkeys` | class | 1 | 6 | 182636 | H |
| `Arrowkeys_Local` | class | 2 | 0 | 182663 |  |
| `Player` | abstract class | 6 | 4 | 182697 | H |
| `Player_Local` | class | 2 | 0 | 182757 |  |
| `Resources` | class | 6 | 6 | 182791 | H |
| &nbsp;&nbsp;↳ `Resources/Transfer` | class | 1 | 2 | 183196 |  |
| `Local_Resources` | class | 2 | 0 | 183227 |  |
| `Staging` | class | 13 | 5 | 183261 | H |
| `Stage` | class | 9 | 6 | 184226 | H |
| `Staging_Local` | class | 2 | 0 | 184641 |  |
| `Throttle` | class | 3 | 3 | 184675 | H |
| `Throttle_Local` | class | 2 | 0 | 184751 |  |
| `PlayerController` | class | 25 | 9 | 184785 |  |
| &nbsp;&nbsp;↳ `PlayerController/ShakeEffect` | class | 1 | 3 | 185980 |  |
| `PartJoint` | class | 3 | 3 | 186373 | H |
| `JointGroup` | class | 15 | 3 | 186469 | H |
| `Rocket` | class | 52 | 23 | 187563 | H |
| &nbsp;&nbsp;↳ `Rocket/INJ_Rocket` | interface | 1 | 0 | 189780 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_IsPlayer` | interface | 1 | 0 | 189796 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_HasControl` | interface | 1 | 0 | 189812 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_ThrottleOn` | interface | 1 | 0 | 189828 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_Throttle` | interface | 1 | 0 | 189844 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_TurnAxisTorque` | interface | 1 | 0 | 189860 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_TurnAxisWheels` | interface | 1 | 0 | 189876 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_DirectionalAxis` | interface | 1 | 0 | 189892 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_Physics` | interface | 1 | 0 | 189908 |  |
| &nbsp;&nbsp;↳ `Rocket/INJ_Location` | interface | 1 | 0 | 189924 |  |
| `RocketManager` | class | 13 | 3 | 190305 |  |
| `DestructionReason` | enum | 0 | 6 | 192046 |  |
| `RocketSave` | class | 2 | 12 | 192061 |  |
| `StageSave` | class | 2 | 2 | 192195 |  |
| `JointSave` | class | 2 | 2 | 192316 |  |
| `SpaceCenter` | class | 2 | 3 | 192442 |  |
| &nbsp;&nbsp;↳ `SpaceCenter/Building` | class | 1 | 1 | 192515 |  |
| `SpaceCenterData` | class | 4 | 3 | 192539 |  |
| &nbsp;&nbsp;↳ `SpaceCenterData/BuildingPosition` | class | 2 | 2 | 192660 |  |
| `LegacyLaunchPad` | class | 1 | 2 | 192714 |  |
| `Orbit` | class | 34 | 21 | 192745 | H |
| `Stationary` | class | 9 | 1 | 195525 |  |
| `Trajectory` | class | 15 | 1 | 195673 | H |
| `I_Path` | interface | 7 | 0 | 196074 |  |
| `PathType` | enum | 0 | 4 | 196147 |  |
| `WorldParticle` | class | 14 | 4 | 196160 |  |
| `WorldSave` | class | 7 | 8 | 196925 |  |
| &nbsp;&nbsp;↳ `WorldSave/WorldState` | class | 2 | 8 | 197331 |  |
| &nbsp;&nbsp;↳ `WorldSave/Astronauts` | class | 2 | 5 | 197444 |  |
| &nbsp;&nbsp;↳ `WorldSave/Astronauts/Data` | class | 2 | 2 | 197522 |  |
| &nbsp;&nbsp;↳ `WorldSave/Astronauts/Crew_World` | class | 2 | 1 | 197560 |  |
| &nbsp;&nbsp;↳ `WorldSave/Astronauts/EVA` | class | 2 | 8 | 197594 |  |
| &nbsp;&nbsp;↳ `WorldSave/Astronauts/Flag` | class | 2 | 2 | 197686 |  |
| &nbsp;&nbsp;↳ `WorldSave/CareerState` | class | 2 | 7 | 197736 |  |
| &nbsp;&nbsp;↳ `WorldSave/CareerState/UnlockType` | enum | 0 | 3 | 197791 |  |
| &nbsp;&nbsp;↳ `WorldSave/LocationData` | class | 3 | 3 | 197802 |  |
| &nbsp;&nbsp;↳ `WorldSave/LocationData/LocationConverter` | class | 5 | 1 | 197865 |  |
| `WorldSmoke` | class | 3 | 4 | 198173 |  |
| &nbsp;&nbsp;↳ `WorldSmoke/Point` | class | 1 | 2 | 198479 |  |
| `WorldTime` | class | 25 | 5 | 198504 | H |
| `WorldView` | class | 20 | 20 | 199446 | H |

### `SFS.World.Drag` — 9 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `AeroModule` | abstract class | 25 | 9 | 215749 |  |
| `Surface` | struct | 1 | 3 | 217767 |  |
| `HeatTolerance` | enum | 0 | 4 | 217798 |  |
| `HeatManager` | class | 8 | 3 | 217811 | H |
| `HeatModuleBase` | abstract class | 13 | 1 | 218451 | H |
| `Valid` | class | 1 | 1 | 218601 |  |
| `Water_Rocket` | class | 5 | 2 | 218623 |  |
| `Aero_Astronaut` | class | 7 | 1 | 219863 |  |
| `Aero_Rocket` | class | 9 | 1 | 220145 |  |

### `SFS.World.Legacy` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `LegacyConverter` | static class | 10 | 0 | 220582 |  |

### `SFS.World.Maps` — 27 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `MapAstronaut` | class | 15 | 1 | 205207 |  |
| `Landmark` | class | 6 | 3 | 205483 |  |
| `LandmarkData` | class | 3 | 3 | 206762 |  |
| `MapFlag` | class | 16 | 2 | 206832 |  |
| `LineDrawer` | class | 6 | 6 | 207200 |  |
| `Map` | class | 2 | 16 | 207431 |  |
| `MapDrawer` | class | 10 | 3 | 207502 |  |
| `MapEnvironment` | class | 8 | 5 | 207823 |  |
| `MapPlanetEnvironment` | class | 1 | 3 | 208336 |  |
| `MapIcon` | class | 7 | 3 | 208360 |  |
| `MapManager` | class | 17 | 4 | 208641 |  |
| `MapNavigation` | class | 19 | 3 | 210012 |  |
| `ManeuverTree` | class | 5 | 3 | 211520 |  |
| `Maneuver` | class | 1 | 3 | 211759 |  |
| `MapPlanet` | class | 19 | 1 | 211792 |  |
| `MapRocket` | class | 15 | 1 | 212205 |  |
| `MapView` | class | 20 | 4 | 212562 |  |
| &nbsp;&nbsp;↳ `MapView/View` | class | 3 | 3 | 213430 |  |
| &nbsp;&nbsp;↳ `MapView/MapObject_Local` | class | 2 | 0 | 213542 |  |
| `TimewarpTo` | class | 16 | 3 | 213865 |  |
| &nbsp;&nbsp;↳ `TimewarpTo/Select` | class | 1 | 1 | 214882 |  |
| &nbsp;&nbsp;↳ `TimewarpTo/Select_Point` | class | 1 | 2 | 214901 |  |
| &nbsp;&nbsp;↳ `TimewarpTo/Select_TransferWindow` | class | 1 | 0 | 214921 |  |
| &nbsp;&nbsp;↳ `TimewarpTo/I_Warp` | interface | 1 | 0 | 214939 |  |
| &nbsp;&nbsp;↳ `TimewarpTo/Warp_Point` | class | 2 | 2 | 214955 |  |
| &nbsp;&nbsp;↳ `TimewarpTo/Warp_TransferWindow` | class | 2 | 1 | 214992 |  |
| `TrajectoryDrawer` | static class | 6 | 0 | 215042 |  |

### `SFS.World.PlanetModules` — 19 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `Atmosphere_Physics` | class | 1 | 9 | 200297 |  |
| `Atmosphere_Visuals` | class | 1 | 3 | 200354 |  |
| &nbsp;&nbsp;↳ `Atmosphere_Visuals/Gradient` | class | 1 | 4 | 200373 |  |
| &nbsp;&nbsp;↳ `Atmosphere_Visuals/Clouds` | class | 1 | 6 | 200407 |  |
| &nbsp;&nbsp;↳ `Atmosphere_Visuals/ColorGradient` | class | 2 | 1 | 200446 |  |
| &nbsp;&nbsp;↳ `Atmosphere_Visuals/ColorGradient/Key` | class | 1 | 2 | 200567 |  |
| `BasicModule` | class | 1 | 9 | 200600 |  |
| `FrontCloudsModule` | class | 1 | 6 | 200661 |  |
| `OrbitModule` | class | 1 | 8 | 200700 |  |
| `PostProcessingModule` | class | 3 | 1 | 200741 |  |
| &nbsp;&nbsp;↳ `PostProcessingModule/Key` | class | 2 | 9 | 200900 |  |
| `RingsModule` | class | 1 | 5 | 201013 |  |
| `TerrainModule` | class | 7 | 11 | 201039 |  |
| &nbsp;&nbsp;↳ `TerrainModule/TerrainTexture` | class | 1 | 15 | 201530 |  |
| &nbsp;&nbsp;↳ `TerrainModule/FlatZone` | class | 1 | 4 | 201634 |  |
| &nbsp;&nbsp;↳ `TerrainModule/RockData` | class | 1 | 6 | 201656 |  |
| `HeightMap` | class | 7 | 1 | 201685 |  |
| `WaterModule` | class | 1 | 22 | 202059 |  |
| &nbsp;&nbsp;↳ `WaterModule/WaterMask` | class | 1 | 3 | 202130 |  |

### `SFS.World.Terrain` — 7 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `DynamicTerrain` | class | 11 | 17 | 202156 |  |
| &nbsp;&nbsp;↳ `DynamicTerrain/DynamicChunk` | class | 13 | 11 | 202665 |  |
| `Chunk` | class | 4 | 4 | 203712 |  |
| &nbsp;&nbsp;↳ `Chunk/TerrainPoints` | class | 1 | 2 | 204416 |  |
| `TerrainColliderManager` | class | 5 | 4 | 204449 |  |
| &nbsp;&nbsp;↳ `TerrainColliderManager/Chunk` | class | 3 | 3 | 204688 |  |
| `TerrainColliderModule` | class | 6 | 3 | 204876 |  |

### `SFS.WorldBase` — 17 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `PlanetLoader` | class | 23 | 19 | 143870 |  |
| `PlanetLoader_Static` | static class | 2 | 0 | 145953 |  |
| `SolarSystemSettings` | class | 1 | 7 | 145996 |  |
| `Difficulty` | class | 24 | 12 | 146044 | H |
| &nbsp;&nbsp;↳ `Difficulty/DifficultyType` | enum | 0 | 4 | 146873 |  |
| `Planet` | class | 52 | 24 | 146888 | H |
| `PlanetData` | class | 2 | 20 | 150017 |  |
| `SavingCache` | class | 16 | 4 | 150189 |  |
| &nbsp;&nbsp;↳ `SavingCache/Data`&lt;1&gt; | class | 3 | 2 | 150801 |  |
| `Revert` | static class | 12 | 0 | 151319 |  |
| `SolarSystemReference` | class | 1 | 1 | 151590 |  |
| `WorldBaseManager` | class | 8 | 7 | 151615 |  |
| `WorldSettings` | class | 2 | 5 | 152158 |  |
| `WorldPlaytime` | class | 2 | 2 | 152211 |  |
| `WorldMode` | class | 3 | 2 | 152252 |  |
| &nbsp;&nbsp;↳ `WorldMode/Mode` | enum | 0 | 4 | 152340 |  |
| `WorldReference` | class | 7 | 7 | 152357 |  |

### `TranslucentImage` — 3 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `TranslucentImage` | class | 9 | 5 | 38052 |  |
| `TranslucentImageNode` | class | 3 | 1 | 38354 |  |
| `TranslucentImageSource` | class | 25 | 20 | 38414 |  |

### `UI` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `ScrollToButtonAttach` | class | 3 | 3 | 37964 |  |

### `UV` — 3 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `StartEnd_UV` | class | 2 | 6 | 41245 |  |
| `Color_Channel` | class | 1 | 1 | 41338 |  |
| `StartEnd_Color` | class | 2 | 2 | 41363 |  |

### `UnityEngine.Purchasing.Security` — 3 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `AppleTangle` | class | 3 | 4 | 39407 |  |
| `GooglePlayTangle` | class | 3 | 4 | 39474 |  |
| `UnityChannelTangle` | class | 3 | 4 | 39541 |  |

### `_Game` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `GameMusic` | class | 4 | 2 | 37115 |  |

### `_Game.Drawers` — 1 types

| Type | Kind | M | F | IL line | H |
|---|---|---:|---:|---:|:-:|
| `FuelTransferDrawer` | class | 8 | 6 | 37277 |  |
