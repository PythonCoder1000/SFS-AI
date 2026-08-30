# SFS Documentation — index

Master table of contents and coverage tracker for the complete
reference to Spaceflight Simulator **1.6.00.16**'s own decompiled
source. This documents *the game*, not this project's `sfsprobe` mod.

Read [`../sfs_reference_plan.md`](../sfs_reference_plan.md) first if
you are picking this up fresh — it holds the settled scope decisions,
the per-class template, and the phase/session plan.

**This file is generated.** `manifest.json` is the source of truth;
run `python3 python/reference_index.py` to rebuild this file after
editing it.

## Coverage

| | Count |
|---|---:|
| Real types in the assembly | 969 |
| Excluded (vendored third-party) | 33 |
| **In scope** | **936** |
| Documented | 116 |
| — at FULL depth | 110 |
| — at LIGHT depth | 6 |
| **Remaining** | **820** |
| Coverage | 12.4% |

**Phase:** Phase 1, Step 2 in progress — net-new coverage

## Standalone files

| File | What it is |
|---|---|
| [`INVENTORY.md`](INVENTORY.md) | The full 969-type inventory — the scope definition |
| [`METHODOLOGY.md`](METHODOLOGY.md) | Provenance, status tags, and how to re-verify any claim |
| [`REFLECTION_TOOLKIT.md`](REFLECTION_TOOLKIT.md) | Live reflection helpers + ambiguous-overload catalogue |
| [`CORRECTIONS.md`](CORRECTIONS.md) | Running ledger of overturned claims |

## Documented types

### `00-infrastructure/`

Math, variables, parsers, IO, mod loader, core utilities

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Line2` | `<global>` | struct | [Line2.md](00-infrastructure/Line2.md) | Global 2D segment struct: 21 methods, three ambiguous overload pairs | PARTIAL | FULL |
| `Loader` | `ModLoader` | class | [Loader.md](00-infrastructure/Loader.md) | The built-in mod loader: one DLL per Mods subfolder, named after the folder | PARTIAL | FULL |
| `Matrix2x2` | `<global>` | class | [Matrix2x2.md](00-infrastructure/Matrix2x2.md) | Global 2x2 rotation matrix - a class, not a struct; four order-sensitive op_Multiply overloads | PARTIAL | FULL |
| `Composed` | `SFS.Variables` | abstract class | [variables-wrapper-family.md](00-infrastructure/variables-wrapper-family.md) | Expression evaluated against a VariablesModule; reading .Value compiles and subscribes | CONFIRMED | FULL |
| `Obs` | `SFS.Variables` | abstract class | [variables-wrapper-family.md](00-infrastructure/variables-wrapper-family.md) | Plain observable value with an optional rewriting filter and three change delegates | CONFIRMED | FULL |
| `ReferenceVariable` | `SFS.Variables` | abstract class | [variables-wrapper-family.md](00-infrastructure/variables-wrapper-family.md) | Value that is either local or bound by name to a shared VariablesModule variable | CONFIRMED | FULL |

### `01-core-flight/`

Rocket, Location, Physics, Orbit, Trajectory, Part, staging

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Kepler` | `<global>` | static class | [Kepler.md](01-core-flight/Kepler.md) | A complete public static orbital-mechanics library - elliptical, near-parabolic and hyperbolic solvers included | PARTIAL | FULL |
| `Double2` | `<global>` | struct | [Location.md](01-core-flight/Location.md) | Global double-precision vector struct; Atan2(y,x) convention, exact equality, and a Parse/ToParsableString pair that cannot round-trip | CONFIRMED | FULL |
| `Location` | `SFS.World` | class | [Location.md](01-core-flight/Location.md) | Immutable planet-relative snapshot; constructors silently coerce NaN to zero and the 2-arg form sets time = -1 | CONFIRMED | FULL |
| `WorldLocation` | `SFS.World` | class | [Location.md](01-core-flight/Location.md) | The live observable location; get_Value copies and stamps world time, set_Value silently no-ops on a null planet | CONFIRMED | FULL |
| `Mass_Calculator` | `SFS.Parts` | class | [Mass_Calculator.md](01-core-flight/Mass_Calculator.md) | Mass-weighted centroid over parts; invalidation is event-driven but suppressed while !realtimePhysics | CONFIRMED | FULL |
| `Orbit` | `SFS.World` | class | [Orbit.md](01-core-flight/Orbit.md) | Orbital elements from a state vector; period is 0.0 for escaping orbits and slr derives from periapsis | CONFIRMED | FULL |
| `Part` | `SFS.Parts` | class | [Part.md](01-core-flight/Part.md) | The part object; extends HeatModuleBase, mass is a parametric expression, and GetModules<T> is a never-invalidated memo keyed by short type name | CONFIRMED | FULL |
| `PartHolder` | `SFS.Parts` | class | [PartHolder.md](01-core-flight/PartHolder.md) | The craft part collection and the correct module-enumeration entry point; its cache IS invalidated by all six mutators | CONFIRMED | FULL |
| `Physics` | `SFS.World` | class | [Physics.md](01-core-flight/Physics.md) | Physics/rails driver: the teleport entry point, InOrbit, and GetTrajectory (the public trajectory field is stale off rails) | CONFIRMED | FULL |
| `Rocket` | `SFS.World` | class | [Rocket.md](01-core-flight/Rocket.md) | The craft object: rotation writes angularVelocity directly (inertia never involved), SAS is a deadbeat clamp, floating means in water | CONFIRMED | FULL |
| `Stage` | `SFS.World` | class | [Staging.md](01-core-flight/Staging.md) | One stage: stageId plus a part list and insert/remove events | PARTIAL | FULL |
| `Staging` | `SFS.World` | class | [Staging.md](01-core-flight/Staging.md) | The stage list plus public static CreateStages/OnSplit/OnMerge; the record flag is undo bookkeeping, not persistence | PARTIAL | FULL |
| `PathType` | `SFS.World` | enum | [Trajectory.md](01-core-flight/Trajectory.md) | Eternal=0, Escape=1, Encounter=2 | CONFIRMED | FULL |
| `Trajectory` | `SFS.World` | class | [Trajectory.md](01-core-flight/Trajectory.md) | The conic-section chain; its prediction horizon is a video setting, and GetNextPath is the whole patched-conic frame algebra | CONFIRMED | FULL |

### `02-drag-aero/`

SFS.World.Drag geometry and the dragArea pipeline

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `AeroFormula` | `<global>` | struct | [AeroFormula.md](02-drag-aero/AeroFormula.md) | The global reentry temperature formula; four coefficients are serialized data and must be read live | PARTIAL | FULL |
| `AeroModule` | `SFS.World.Drag` | abstract class | [AeroModule.md](02-drag-aero/AeroModule.md) | Abstract base for the whole drag+heating pipeline; owns CalculateDragForce (= dragArea) and ApplyForce | CONFIRMED | FULL |
| `Aero_Rocket` | `SFS.World.Drag` | class | [Aero_Rocket.md](02-drag-aero/Aero_Rocket.md) | AeroModule subclass for rockets; static GetDragSurfaces works on any PartHolder | CONFIRMED | FULL |
| `Surface` | `SFS.World.Drag` | struct | [geometry-types.md](02-drag-aero/geometry-types.md) | One drag segment: owner heat module, shared Valid token, Line2 in velocity-aligned space | CONFIRMED | FULL |
| `SurfaceData` | `SFS.Parts.Modules` | abstract class | [geometry-types.md](02-drag-aero/geometry-types.md) | Per-part geometry provider; surfacesFast is the drag geometry, Drag is the opt-out | PARTIAL | FULL |
| `Surfaces` | `SFS.Parts.Modules` | class | [geometry-types.md](02-drag-aero/geometry-types.md) | One outline: readonly points, owner transform, loop flag | CONFIRMED | FULL |
| `Valid` | `SFS.World.Drag` | class | [geometry-types.md](02-drag-aero/geometry-types.md) | Reference-type shared invalidation token wrapping a single bool | CONFIRMED | FULL |

### `03-heat-destruction/`

Heating, temperature, overheat destruction, burn marks

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `HeatManager` | `SFS.World.Drag` | class | [HeatManager.md](03-heat-destruction/HeatManager.md) | Heat absorption, dissipation and the overheat destruction path; no destruction under rails timewarp | CONFIRMED | FULL |
| `DestructionReason` | `SFS.World` | enum | [HeatModuleBase.md](03-heat-destruction/HeatModuleBase.md) | TerrainCollision, WaterCollision, RocketCollision, Overheat, Intentional | CONFIRMED | FULL |
| `HeatModule` | `SFS.Parts.Modules` | class | [HeatModuleBase.md](03-heat-destruction/HeatModuleBase.md) | Opt-in per-part heat module: the only route to Mid/High tolerance or heat-shield status | PARTIAL | FULL |
| `HeatModuleBase` | `SFS.World.Drag` | abstract class | [HeatModuleBase.md](03-heat-destruction/HeatModuleBase.md) | Abstract heat contract; Part implements it directly, so a plain part is always tolerance 400 | CONFIRMED | FULL |
| `HeatTolerance` | `SFS.World.Drag` | enum | [HeatModuleBase.md](03-heat-destruction/HeatModuleBase.md) | Low=400, Mid=1000, High=6000; parts break above tolerance x 1.03 | CONFIRMED | FULL |

### `04-engines/`

Engines, boosters, torque, thrust effects

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `BoosterModule` | `SFS.Parts.Modules` | class | [BoosterModule.md](04-engines/BoosterModule.md) | Solid boosters - a separate path with different field names; anything scanning for EngineModule misses them | PARTIAL | FULL |
| `EngineModule` | `SFS.Parts.Modules` | class | [EngineModule.md](04-engines/EngineModule.md) | Liquid engine: per-engine AddForceAtPosition with no summation anywhere; F = thrustNormal*thrust*9.8*throttle_Out | CONFIRMED | FULL |
| `TorqueModule` | `SFS.Parts.Modules` | class | [TorqueModule.md](04-engines/TorqueModule.md) | Reaction wheel: three fields, no physics of its own; torque is summed by the rotation path | CONFIRMED | FULL |

### `05-rcs/`

RCS thrusters

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `RcsModule` | `SFS.Parts.Modules` | class | [RcsModule.md](05-rcs/RcsModule.md) | RCS: one combined force per module; torque thrusters fire only at |TurnAxis|>=0.95 or |angularVelocity|>=2 | CONFIRMED | FULL |
| `Thruster` | `SFS.Parts.Modules` | class | [RcsModule.md](05-rcs/RcsModule.md) | One RCS thruster: part-local thrustNormal plus a visual MoveModule | CONFIRMED | FULL |

### `06-soi-terrain/`

Planets, SOI, atmosphere, terrain, interplanetary

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Atmosphere_Physics` | `SFS.World.PlanetModules` | class | [Atmosphere_Physics.md](06-soi-terrain/Atmosphere_Physics.md) | The nine atmosphere physics constants; height and curve are difficulty-mutated in place, and parachuteMultiplier is shared with balloons | CONFIRMED | FULL |
| `Difficulty` | `SFS.WorldBase` | class | [Difficulty.md](06-soi-terrain/Difficulty.md) | The eleven difficulty constant tables, decoded from .data blobs; scales planets, ISP, mass and heating | CONFIRMED | FULL |
| `Planet` | `SFS.WorldBase` | class | [Planet.md](06-soi-terrain/Planet.md) | Body constants and queries: mass is mu not kg, per-angle terrain is real, and an SOI crossing forces the craft onto rails | CONFIRMED | FULL |
| `FlatZone` | `SFS.World.PlanetModules` | class | [TerrainModule.md](06-soi-terrain/TerrainModule.md) | Flattened launch/landing region - four fields whose semantics are decided inside TerrainSampler | PARTIAL | FULL |
| `HeightMap` | `SFS.World.PlanetModules` | class | [TerrainModule.md](06-soi-terrain/TerrainModule.md) | 1-D float lookup with linear interpolation; Evaluate WRAPS rather than clamps and EvaluateDoubleOut is not actually double-precision | CONFIRMED | FULL |
| `RockData` | `SFS.World.PlanetModules` | class | [TerrainModule.md](06-soi-terrain/TerrainModule.md) | Cosmetic surface-scatter settings, consumed only by DynamicChunk.GenerateRocks | CONFIRMED | LIGHT |
| `TerrainModule` | `SFS.World.PlanetModules` | class | [TerrainModule.md](06-soi-terrain/TerrainModule.md) | The terrain geometry source for both the visual and collider paths; LOD ratios are 2.55 (mesh) and 2.05 (load distance), and formulas are difficulty-dependent | CONFIRMED | FULL |
| `TerrainTexture` | `SFS.World.PlanetModules` | class | [TerrainModule.md](06-soi-terrain/TerrainModule.md) | Rendering-only texture settings; field layout confirmed, no simulation relevance | CONFIRMED | LIGHT |
| `BasicModule` | `SFS.World.PlanetModules` | class | [planet-data-modules.md](06-soi-terrain/planet-data-modules.md) | Radius and gravity - the most-read data block; velocityArrowsHeight defaults to NaN and gravity reaches wheel friction and EVA, not just orbits | CONFIRMED | FULL |
| `FrontCloudsModule` | `SFS.World.PlanetModules` | class | [planet-data-modules.md](06-soi-terrain/planet-data-modules.md) | Purely visual front cloud layer; positionZ defaults to -5000 and is difficulty-scaled along with height | CONFIRMED | LIGHT |
| `OrbitModule` | `SFS.World.PlanetModules` | class | [planet-data-modules.md](06-soi-terrain/planet-data-modules.md) | The planet own orbit and SOI multiplier; parent is a code-name string and everything but parent/sma is read once in SetupInteractions | CONFIRMED | FULL |
| `RingsModule` | `SFS.World.PlanetModules` | class | [planet-data-modules.md](06-soi-terrain/planet-data-modules.md) | Purely visual rings - no collider, no drag, no gravity; all three geometry fields are difficulty-scaled in place | CONFIRMED | LIGHT |
| `WaterMask` | `SFS.World.PlanetModules` | class | [planet-data-modules.md](06-soi-terrain/planet-data-modules.md) | Three floats (must/cannot/global) read only by CreateWaterMaterial; blend semantics live in a shader outside the assembly | CONFIRMED | LIGHT |
| `WaterModule` | `SFS.World.PlanetModules` | class | [planet-data-modules.md](06-soi-terrain/planet-data-modules.md) | 22 fields of which only lowerTerrain, oceanDepth and wavesSize affect simulation; wavesSize crosses into buoyancy | CONFIRMED | FULL |
| `Chunk` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | The visual mesh pair; terrainTransform doubles as the liveness flag. Mesh-building ctor not read in full | PARTIAL | FULL |
| `Chunk` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | One PolygonCollider2D chunk; exists even when terrain.collider is false, in which case it has no collider at all | CONFIRMED | FULL |
| `DynamicChunk` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | One LOD node; its constructor registers and enables itself, and otherHalf is deliberately asymmetric | CONFIRMED | FULL |
| `DynamicTerrain` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | The visual LOD tree - cosmetic only, shares no geometry with the collider system; distanceMoved is a path-length odometer | CONFIRMED | FULL |
| `TerrainColliderManager` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | Singleton owning every terrain collider, reference-counted by owning module and keyed by a bare int chunk index | CONFIRMED | FULL |
| `TerrainColliderModule` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | Per-craft collider requester; driven by the position observable, not Update, and the chunk index has no planet identity | CONFIRMED | FULL |
| `TerrainPoints` | `SFS.World.Terrain` | class | [terrain-chunks.md](06-soi-terrain/terrain-chunks.md) | Two-array carrier returned by TerrainModule.GetTerrainPoints - the one type both the visual and collider paths share | CONFIRMED | FULL |

### `07-saveload/`

JSON/INI serialization, save records, sharing

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `FileLocations` | `<global>` | static class | [JsonWrapper.md](07-saveload/JsonWrapper.md) | Static IFolder properties for every on-disk root: Mods, Blueprints, Worlds, Logs, Cache | PARTIAL | FULL |
| `JsonWrapper` | `SFS.Parsers.Json` | static class | [JsonWrapper.md](07-saveload/JsonWrapper.md) | Newtonsoft-backed JSON layer; TryLoadJson/FromJson are generic, SaveAsJson/ToJson are not | PARTIAL | FULL |
| `PartsLoader` | `SFS.Parts` | class | [RocketManager.md](07-saveload/RocketManager.md) | The part catalog keyed by name, and CreateParts(PartSave[]) with its ownership gate | PARTIAL | FULL |
| `RocketManager` | `SFS.World` | class | [RocketManager.md](07-saveload/RocketManager.md) | Public static SpawnBlueprint plus GenerateJoints - a rocket can be built with no editor UI | PARTIAL | FULL |
| `Blueprint` | `SFS.Builds` | class | [save-records.md](07-saveload/save-records.md) | The rocket design format: six fields and no joints - connectivity is derived at spawn | CONFIRMED | FULL |
| `JointSave` | `SFS.World` | class | [save-records.md](07-saveload/save-records.md) | A joint as two part INDEXES into the parts array | CONFIRMED | FULL |
| `LocationData` | `SFS.World` | class | [save-records.md](07-saveload/save-records.md) | Planet code-name string plus position and velocity - which is why saves are portable | CONFIRMED | FULL |
| `PartSave` | `SFS.Parts` | class | [save-records.md](07-saveload/save-records.md) | Per-part record; the three *_VARIABLES dictionaries are the entire part configuration | CONFIRMED | FULL |
| `RocketSave` | `SFS.World` | class | [save-records.md](07-saveload/save-records.md) | A flying instance: blueprint plus location, control state and frozen joints | CONFIRMED | FULL |
| `StageSave` | `SFS.World` | class | [save-records.md](07-saveload/save-records.md) | Stage id plus part INDEXES into the parts array | CONFIRMED | FULL |
| `WorldSave` | `SFS.World` | class | [save-records.md](07-saveload/save-records.md) | Whole-world state across eight separate JSON .txt files; challenge completion lives here, not in Steam | CONFIRMED | FULL |

### `08-parametric-expressions/`

The part-variable expression compiler and AST

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Add` | `SFS.Parsers.Constructed` | class | [Compute.md](08-parametric-expressions/Compute.md) | A.Value + B.Value | CONFIRMED | FULL |
| `Composed_Float` | `SFS.Variables` | class | [Compute.md](08-parametric-expressions/Compute.md) | Holds the raw expression string plus its compiled AST; reading .Value evaluates it against bound variables | CONFIRMED | FULL |
| `Compute` | `SFS.Parsers.Constructed` | static class | [Compute.md](08-parametric-expressions/Compute.md) | Public static expression compiler for part variables; Compile and GetVariablesUsed are directly callable | PARTIAL | FULL |
| `Divide` | `SFS.Parsers.Constructed` | class | [Compute.md](08-parametric-expressions/Compute.md) | A.Value / B.Value | CONFIRMED | FULL |
| `I_Node` | `SFS.Parsers.Constructed` | interface | [Compute.md](08-parametric-expressions/Compute.md) | AST node interface: a single float Value property that evaluates the tree | CONFIRMED | FULL |
| `Multiply` | `SFS.Parsers.Constructed` | class | [Compute.md](08-parametric-expressions/Compute.md) | A.Value * B.Value - body confirmed | CONFIRMED | FULL |
| `Number` | `SFS.Parsers.Constructed` | class | [Compute.md](08-parametric-expressions/Compute.md) | Numeric literal AST node | CONFIRMED | FULL |
| `Operator` | `SFS.Parsers.Constructed` | abstract class | [Compute.md](08-parametric-expressions/Compute.md) | Abstract binary operator node holding two child I_Nodes | CONFIRMED | FULL |
| `Subtract` | `SFS.Parsers.Constructed` | class | [Compute.md](08-parametric-expressions/Compute.md) | A.Value - B.Value | CONFIRMED | FULL |
| `Variable` | `SFS.Parsers.Constructed` | class | [Compute.md](08-parametric-expressions/Compute.md) | Variable reference with a scalar modifier; multiplies in float32, not double | CONFIRMED | FULL |
| `VariablesModule` | `SFS.Variables` | class | [Compute.md](08-parametric-expressions/Compute.md) | Three VariableLists (double/bool/string) - the entire parametric configuration of a part | PARTIAL | FULL |

### `09-resources-fuel/`

Resource types, tanks, flow, fuel transfer

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Flow` | `SFS.Parts.Modules` | class | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | One consumer straw into the tanks; infinite fuel is implemented here by skipping consumption entirely | PARTIAL | FULL |
| `FlowModule` | `SFS.Parts.Modules` | class | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | Splits an engine mass flow across Flow entries by flowPercent - the seam between engines and tanks | CONFIRMED | FULL |
| `FlowType` | `SFS.Parts.Modules` | enum | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | Negative=0 (consume), Positive=1 (fill) | CONFIRMED | FULL |
| `FuelPipeModule` | `SFS.Parts.Modules` | class | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | Cross-feed; driven from Rocket.FixedUpdate via the static FixedUpdate_FuelPipeFlow, not its own | PARTIAL | FULL |
| `ResourceModule` | `SFS.Parts.Modules` | class | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | A tank or tank group; fuel is stored as a fraction only, and capacity is difficulty-scaled | CONFIRMED | FULL |
| `ResourceType` | `SFS.Parts.Modules` | class | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | The substance record; all five values are serialized data and identity is by object reference | PARTIAL | FULL |
| `Resources` | `SFS.World` | class | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | Per-craft fuel topology, derived from joint connectivity and rebuilt on every structure change | CONFIRMED | FULL |
| `SourceMode` | `SFS.Parts.Modules` | enum | [resources-and-flow.md](09-resources-fuel/resources-and-flow.md) | Global=0, Surfaces=1, Local=2 | CONFIRMED | FULL |

### `10-control-input/`

SFS.Input, player control, arrowkeys, throttle

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Arrowkeys` | `SFS.World` | class | [control-input.md](10-control-input/control-input.md) | Pure control state - six Obs fields, no methods, no validation and no clamping | CONFIRMED | FULL |
| `ArrowkeysDrawer` | `SFS.World` | class | [control-input.md](10-control-input/control-input.md) | The on-screen pad and the ONLY writer of Arrowkeys for rockets; the hasControl and timewarp gates live here, in the UI | CONFIRMED | FULL |
| `ControlModule` | `SFS.Parts.Modules` | class | [control-input.md](10-control-input/control-input.md) | One Bool_Reference - so whether a capsule grants control can itself be a part variable | CONFIRMED | FULL |
| `Player` | `SFS.World` | abstract class | [control-input.md](10-control-input/control-input.md) | Abstract base of Rocket; owns location, isPlayer and hasControl as subscribable Obs values | CONFIRMED | FULL |
| `Throttle` | `SFS.World` | class | [control-input.md](10-control-input/control-input.md) | Three fields; output_Throttle is the authoritative command and recomputes synchronously on write, with no gates | CONFIRMED | FULL |

### `11-joints-docking/`

Part joints, joint groups, docking, separators, splitting

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `DetachModule` | `SFS.Parts.Modules` | class | [joints-and-docking.md](11-joints-docking/joints-and-docking.md) | Separators; Detach(UsePartData) is public and separationForce is a parametric expression | PARTIAL | FULL |
| `DockingPortModule` | `SFS.Parts.Modules` | class | [joints-and-docking.md](11-joints-docking/joints-and-docking.md) | Docking is a plain distance test; alignment is not checked but FORCED, snapped to the nearest 90 degrees | CONFIRMED | FULL |
| `JointGroup` | `SFS.World` | class | [joints-and-docking.md](11-joints-docking/joints-and-docking.md) | The connectivity graph; splitting is connected-component counting and fuel groups come from the same traversal | CONFIRMED | FULL |
| `PartJoint` | `SFS.World` | class | [joints-and-docking.md](11-joints-docking/joints-and-docking.md) | An undirected graph edge with an anchor - no strength, no break force, not a Unity Joint2D | CONFIRMED | FULL |

### `12-world-scene-timewarp/`

World time, floating origin, scenes, cameras

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `GameManager` | `SFS.World` | class | [GameManager.md](12-world-scene-timewarp/GameManager.md) | World-scene singleton: rockets is the craft enumeration point and aeroData holds the reentry coefficients | PARTIAL | FULL |
| `SceneHelper` | `ModLoader.Helpers` | static class | [GameManager.md](12-world-scene-timewarp/GameManager.md) | Ten static scene-load/unload delegates - the Harmony-free way to know the world is ready | CONFIRMED | FULL |
| `SceneLoader` | `SFS` | class | [GameManager.md](12-world-scene-timewarp/GameManager.md) | Five scenes (Base, Home, Hub, Build, World); loading is async so a scene change does not finish in-frame | PARTIAL | FULL |
| `Data` | `SFS.World` | class | [SandboxSettings.md](12-world-scene-timewarp/SandboxSettings.md) | The eight cheat booleans - world-scoped, swapped by WorldBaseManager.EnterWorld/ExitWorld; full map of which physics path each flag changes | CONFIRMED | FULL |
| `SandboxSettings` | `SFS.World` | class | [SandboxSettings.md](12-world-scene-timewarp/SandboxSettings.md) | The eight cheat flags: every Toggle* is PRIVATE, requires a loaded world, and writes the settings file to disk on every call | PARTIAL | FULL |
| `WorldTime` | `SFS.World` | class | [WorldTime.md](12-world-scene-timewarp/WorldTime.md) | The simulation clock and both timewarp ladders; SetState is public and validates nothing | CONFIRMED | FULL |
| `WorldView` | `SFS.World` | class | [WorldView.md](12-world-scene-timewarp/WorldView.md) | Floating origin AND floating velocity frame - which is why rb2d.linearVelocity is not world velocity | CONFIRMED | FULL |

### `13-challenges-logging/`

Stats, challenges, logs, analytics, message logging

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `Challenge` | `SFS.Logs` | class | [Challenge.md](13-challenges-logging/Challenge.md) | In-game challenge record (not Steamworks); CollectChallenges() enumerates the whole catalogue at runtime | PARTIAL | FULL |
| `ChallengeRecorder` | `SFS.Stats` | class | [Challenge.md](13-challenges-logging/Challenge.md) | Per-craft challenge progress; TryCompleteSteps evaluates against a plain Location, not a live craft | PARTIAL | FULL |
| `Difficulty` | `SFS.Logs` | enum | [Challenge.md](13-challenges-logging/Challenge.md) | Challenge difficulty enum - distinct from SFS.WorldBase.Difficulty | PARTIAL | LIGHT |
| `ErrorLogger` | `<global>` | class | [ErrorLogger.md](13-challenges-logging/ErrorLogger.md) | lastLogs is a public List<string> and GetLogsDumpBase64Gzip is public - the game own log tail, readable | PARTIAL | FULL |
| `I_MsgLogger` | `SFS` | interface | [I_MsgLogger.md](13-challenges-logging/I_MsgLogger.md) | One-method interface threaded through every refusal gate - pass your own to get the game localised reason instead of a bare false | CONFIRMED | FULL |
| `MsgDrawer` | `SFS.UI` | class | [I_MsgLogger.md](13-challenges-logging/I_MsgLogger.md) | The game I_MsgLogger implementation; Log has two overloads, one an explicit interface method | PARTIAL | FULL |
| `StatsRecorder` | `SFS.Stats` | class | [StatsRecorder.md](13-challenges-logging/StatsRecorder.md) | 1 Hz classifier of landed/height/orbit/atmosphere state; HasFlown walks a per-branch flight history | PARTIAL | FULL |

### `14-misc-part-modules/`

Remaining SFS.Parts.Modules: geometry, colour, behaviour

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `MoveModule` | `SFS.Parts.Modules` | class | [MoveModule.md](14-misc-part-modules/MoveModule.md) | The generic animation driver behind toggles, gimbals and RCS visuals; its state lives in the variable system | PARTIAL | FULL |
| `ToggleModule` | `SFS.Parts.Modules` | class | [MoveModule.md](14-misc-part-modules/MoveModule.md) | Two fields; all behaviour delegates to MoveModule | CONFIRMED | FULL |
| `ParachuteModule` | `SFS.Parts.Modules` | class | [ParachuteModule.md](14-misc-part-modules/ParachuteModule.md) | Deploy ceiling is terrain-relative and capped at 90% of atmosphere height; drag is an AnimationCurve of deployment state | PARTIAL | FULL |
| `WheelModule` | `SFS.Parts` | class | [WheelModule.md](14-misc-part-modules/WheelModule.md) | Steered by the raw undamped turn axis, never by SAS; idle clamps are +/-0.05 powered and +/-0.25 free-rolling | PARTIAL | FULL |

### `15-ui/`

SFS.UI

*Nothing migrated or written yet.*

### `16-builds/`

SFS.Builds — the in-game editor

| Type | Namespace | Kind | File | Summary | Status | Depth |
|---|---|---|---|---|---|---|
| `BuildState` | `SFS.Builds` | class | [BuildState.md](16-builds/BuildState.md) | The editor-side blueprint loader; LoadBlueprint requires Build_PC (the opposite of RocketManager.SpawnBlueprint) and Clear() runs before any validation | PARTIAL | FULL |

### `17-modgui/`

SFS.UI.ModGUI

*Nothing migrated or written yet.*

### `18-maps-navigation/`

SFS.World.Maps, SFS.Navigation

*Nothing migrated or written yet.*

### `19-career-progression/`

SFS.Career, SFS.Tutorials, space centre

*Nothing migrated or written yet.*

### `20-localization-audio/`

SFS.Translations, SFS.Audio

*Nothing migrated or written yet.*

### `21-platform-rendering/`

Platform glue, post-processing, stars, video settings

*Nothing migrated or written yet.*

## Old-file section map

Where each section of the retired `docs/sfs_source_reference.md` went.
Kept so that cross-references written as `§B1`, `§C1.4` etc. — which
still appear inside migrated text — can be resolved.

| Old section | New location |
|---|---|
| Corrections to earlier documents | CORRECTIONS.md |
| Provenance / Status tags | METHODOLOGY.md |
| §A1 Reflection toolkit | REFLECTION_TOOLKIT.md |
| §A1.1 Ambiguous-overload catalogue | REFLECTION_TOOLKIT.md |
| §A2 Methodology | METHODOLOGY.md |
| §A3 SFS.Variables wrapper family | 00-infrastructure/variables-wrapper-family.md |
| §A4.1 ModLoader.Loader | 00-infrastructure/Loader.md |
| §A4.2–A4.5 Harmony dead end | 00-infrastructure/Loader.md (appendix) |
| §B1 Rocket | 01-core-flight/Rocket.md |
| §B2 Location / WorldLocation / Double2 | 01-core-flight/Location.md |
| §B3 Part | 01-core-flight/Part.md |
| §B4 PartHolder | 01-core-flight/PartHolder.md |
| §B5.1 Physics | 01-core-flight/Physics.md |
| §B5.2 Trajectory | 01-core-flight/Trajectory.md |
| §B5.3 Orbit | 01-core-flight/Orbit.md |
| §B5.4 Kepler | 01-core-flight/Kepler.md |
| §B6 Mass_Calculator | 01-core-flight/Mass_Calculator.md |
| §B7 Staging / Stage | 01-core-flight/Staging.md |
| §C1.0–C1.1, C1.4–C1.9 AeroModule | 02-drag-aero/AeroModule.md |
| §C1.2 GetDragSurfaces | 02-drag-aero/Aero_Rocket.md |
| §C1.3 Geometry types | 02-drag-aero/geometry-types.md + 00-infrastructure/Line2.md + Matrix2x2.md |
| §D1.0–D1.1 Heat type layout, tolerances | 03-heat-destruction/HeatModuleBase.md |
| §D1.2 Temperature formula | 02-drag-aero/AeroFormula.md |
| §D1.3–D1.4 HeatManager, destruction path | 03-heat-destruction/HeatManager.md |
| §D1.5 Difficulty constants | 06-soi-terrain/Difficulty.md |
| §D1.6 Heat reflection recipe | 03-heat-destruction/HeatModuleBase.md |
| §D2 Engines | 04-engines/EngineModule.md |
| §D2.5 BoosterModule | 04-engines/BoosterModule.md |
| §D2.6 TorqueModule | 04-engines/TorqueModule.md |
| §D3 RCS | 05-rcs/RcsModule.md |
| §D4 Planets / SOI / atmosphere / terrain | 06-soi-terrain/Planet.md |
| §D5.0 Serialization layer | 07-saveload/JsonWrapper.md |
| §D5.1–D5.3 Save records | 07-saveload/save-records.md |
| §D5.4–D5.5 Spawning | 07-saveload/RocketManager.md |
| §E1 Resources and fuel flow | 09-resources-fuel/resources-and-flow.md |
| §E2 Control and input | 10-control-input/control-input.md |
| §E3 Joints, splitting, docking | 11-joints-docking/joints-and-docking.md |
| §E4 Parametric expressions | 08-parametric-expressions/Compute.md |
| §E5.1 WorldTime | 12-world-scene-timewarp/WorldTime.md |
| §E5.2 WorldView | 12-world-scene-timewarp/WorldView.md |
| §E5.3–E5.4 GameManager / SceneLoader / SceneHelper | 12-world-scene-timewarp/GameManager.md |
| §E6.1 ParachuteModule | 14-misc-part-modules/ParachuteModule.md |
| §E6.2 WheelModule | 14-misc-part-modules/WheelModule.md |
| §E6.3 ToggleModule / MoveModule | 14-misc-part-modules/MoveModule.md |
| §E7.1 I_MsgLogger / MsgDrawer | 13-challenges-logging/I_MsgLogger.md |
| §E7.2 StatsRecorder | 13-challenges-logging/StatsRecorder.md |
| §E7.3 Challenge / ChallengeRecorder | 13-challenges-logging/Challenge.md |
| §E7.4 ErrorLogger | 13-challenges-logging/ErrorLogger.md |
