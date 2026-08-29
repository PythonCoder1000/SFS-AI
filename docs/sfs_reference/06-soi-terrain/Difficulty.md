# `SFS.WorldBase.Difficulty` — the difficulty constant tables

**Migrated** from `docs/sfs_source_reference.md` §D1.5 (2026-08-28).
Signatures re-read from IL during migration.

Every planet constant, every heating multiplier and the ISP multiplier
are scaled by difficulty. **Nothing measured on one difficulty transfers
to another**, which is why several values in
`docs/sfs_physics_reference.md` §1.1 are difficulty-specific snapshots.

---

## Difficulty

**Namespace:** SFS.WorldBase
**Kind:** class (`serializable`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] tables · [PARTIAL] scaling bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @146044 · 24 methods / 12 fields

### Fields

The eleven static arrays are `private static initonly`, initialised via
`RuntimeHelpers.InitializeArray` from `<PrivateImplementationDetails>`
blobs. **The byte arrays were decoded from the `.data` section of the
dump**, which is how the table below was recovered — they are not
readable as IL literals.

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `difficulty` | `Difficulty/DifficultyType` | public | no | the selected level; every getter indexes the arrays with it | [CONFIRMED] |
| `maxPhysicsTimewarpIndex` | `int[]` | private | static readonly | | [CONFIRMED] |
| `defaultPlanetScales` | `double[]` | private | static readonly | | [CONFIRMED] |
| `defaultAtmosphereScales` | `double[]` | private | static readonly | | [CONFIRMED] |
| `defaultAtmosphereCurveScales` | `double[]` | private | static readonly | | [CONFIRMED] |
| `defaultDistanceScales` | `double[]` | private | static readonly | | [CONFIRMED] |
| `ispMultipliers` | `double[]` | private | static readonly | | [CONFIRMED] |
| `dryMassMultipliers` | `double[]` | private | static readonly | | [CONFIRMED] |
| `engineMassMultipliers` | `double[]` | private | static readonly | | [CONFIRMED] |
| `altitudeMilestones` | `int[][]` | private | static readonly | | [CONFIRMED] |
| `minHeatVelocityMultiplier` | `float[]` | private | static readonly | | [CONFIRMED] |
| `heatVelocityMultiplier` | `float[]` | private | static readonly | | [CONFIRMED] |

### DifficultyType (nested enum)

**`Normal = 0, Hard = 1, Realistic = 2`** — confirmed from the nested
enum @146873 and from getters of the form `array[this.difficulty]`.

### The decoded tables

**[CONFIRMED]** — all indexed by `DifficultyType`.

| Field | Normal | Hard | Realistic |
|---|---|---|---|
| `maxPhysicsTimewarpIndex` | 2 | 2 | 3 |
| `defaultPlanetScales` | 1.0 | 2.0 | 20.0 |
| `defaultAtmosphereScales` | 1.0 | 1.6666667 | 3.3333333 |
| `defaultAtmosphereCurveScales` | 1.0 | 1.5 | 3.0 |
| `defaultDistanceScales` | 1.0 | 2.0 | 20.0 |
| `ispMultipliers` | **1.0** | 1.0 | 1.5 |
| `dryMassMultipliers` | 1.0 | 1.0 | 0.25 |
| `engineMassMultipliers` | 1.0 | 1.0 | 0.5 |
| `minHeatVelocityMultiplier` | **1.0** | 1.3 | 3.0 |
| `heatVelocityMultiplier` | **1.0** | 1.3 | 4.5 |
| `altitudeMilestones` | 1000, 5000, 10000, 15000 | 1000, 10000, 20000, 30000 | 1000, 10000, 25000, 50000 |

**This independently confirms `sfs_physics_reference.md` §1.3's
`ispMultiplier (Normal) = 1.0000`** — measured empirically to 0.002%, and
now read as a literal from code.

### Methods

#### get_Normal() / get_Hard() / get_Realistic() -> Difficulty

- **Access:** **public static** properties · IL @146061 / @146075 /
  @146089
- **Returns:** a `Difficulty` instance preset to that level.
- **Status:** [CONFIRMED] signature · [PARTIAL] body

#### The accessors

All public instance properties; each indexes its static array with
`this.difficulty`.

| Property | IL | Returns |
|---|---|---|
| `MaxPhysicsTimewarpIndex` | @146147 | `int` |
| `IspMultiplier` | @146161 | `double` |
| `DryMassMultiplier` | @146175 | `double` |
| `EngineMassMultiplier` | @146189 | `double` |
| `AltitudeMilestones` | @146203 | `int[]` |
| `MinHeatVelocityMultiplier` | @146217 | `float` |
| `HeatVelocityMultiplier` | @146231 | `float` |
| `DefaultRadiusScale` | @146653 | `double` |
| `DefaultAtmoHeightScale` | @146667 | `double` |
| `DefaultAtmoCurveScale` | @146681 | `double` |
| `DefaultSmaScale` | @146695 | `double` |

**Status:** [CONFIRMED] signatures · [PARTIAL] bodies (the indexing
pattern is confirmed; individual bodies not each transcribed).

#### ScalePlanetData(PlanetData planet) -> void

- **Access:** public instance · IL @146245 — the largest method on the
  class
- **Behavior:** applies the scale factors to a planet's data **once, at
  load**. This is why live planet reads are correct and static asset
  parsing is not.
- **Side effects:** mutates `PlanetData`.
- **Status:** [PARTIAL] — role confirmed from call sites, body not fully
  transcribed

| Supporting scale methods | IL | Access |
|---|---|---|
| `double RadiusScale(PlanetData)` | @146484 | public |
| `double AtmosphereScale(PlanetData)` | @146509 | public |
| `double GravityScale(PlanetData)` | @146555 | private |
| `double AtmosphereCurveScale(PlanetData)` | @146579 | private |
| `double SmaScale(PlanetData)` | @146604 | private |
| `double SoiScale(PlanetData)` | @146629 | private |

**Status:** [PARTIAL] — signatures confirmed, bodies [OPEN].

#### GetName() -> string

- **Access:** public instance · IL @146103
- **Status:** [PARTIAL]

## Gotcha — atmosphere constants are difficulty-scaled

`Atmosphere_Physics` @200297 carries
`Dictionary<DifficultyType, double> curveScale` and
`heightDifficultyScale` — **atmosphere density and height scale with
difficulty**. The Earth constants recorded in
`docs/sfs_physics_reference.md` §1.1 (`ρ0 = 0.005`, `curve = 10`,
`AtmosphereHeightPhysics = 30,000`) are therefore only valid for the
difficulty they were measured on, and that document does not currently
say which.

Full `Atmosphere_Physics` field list: `height`, `density`, `curve`,
`curveScale`, `parachuteMultiplier`, `upperAtmosphere`,
`heightDifficultyScale`, `shockwaveIntensity`,
`minHeatingVelocityMultiplier`. Its own entry is [OPEN] — Step 2.

## Status summary

| Item | Status |
|---|---|
| `DifficultyType` is `Normal=0, Hard=1, Realistic=2` | [CONFIRMED] |
| All eleven constant tables, decoded from `.data` blobs | [CONFIRMED] |
| `ispMultiplier (Normal) = 1.0` | [CONFIRMED] — matches the empirical 0.002% measurement |
| Accessor pattern `array[this.difficulty]` | [CONFIRMED] |
| `ScalePlanetData` scales planet constants once, at load | [PARTIAL] |
| `ScalePlanetData` and the six scale-helper bodies | [OPEN] |
| `GetName`, `get_Normal/Hard/Realistic` bodies | [OPEN] |
| `Atmosphere_Physics` own entry | [OPEN] — Step 2 |
