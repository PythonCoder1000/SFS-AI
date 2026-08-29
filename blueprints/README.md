# blueprints/

Rocket designs, split by trust level.

## research/

Hand-crafted or exploratory blueprints, usable now. This is where a test
rocket goes when validating the load/spawn mechanism itself, or when a
design is being iterated on manually (by Christian or Claude) before any
design agent exists.

## live/

**Not used yet.** Reserved for once the design agent is actually built
and connected -- its generated output will land here, kept separate from
`research/` so it's always clear which blueprints came from a human/
manual process versus the agent itself.

## Format

Each blueprint is its own folder, matching the game's real on-disk
layout (`SFS.Builds.Blueprint.Save`, confirmed via
`docs/sfs_reference/07-saveload/RocketManager.md` and
`docs/sfs_source_reference.md` section D5.1):

```
<name>/
    Version.txt      the SFS build version string, e.g. "1.6.00.16"
    Blueprint.txt     the actual design -- JSON, six fields:
                      center, parts[], stages[], rotation, offset, interiorView
```

`parts[]` entries: `{"n": "<part name, must match PartsLoader.parts keys>",
"p": {"x":, "y":}, "o": {"x":, "y":, "z":}}`. `stages[]`: `{"stageId":,
"partIndexes": [...]}` -- indices into `parts`, not names. No joints are
stored -- connectivity is derived from geometry at spawn time
(`RocketManager.GenerateJoints`).

## Loading into the game

Via `sfsprobe_load_blueprint` (sfsprobe_mcp) with a `target` param, or
the mod's two commands directly. Both read the file directly (does NOT
require it to be inside the game's own `Saving/Blueprints/` folder) and
deserialize via the game's own `JsonWrapper.FromJson<Blueprint>` — no
editor UI interaction needed for either.

**Two genuinely different mechanisms, not two ways of doing the same
thing:**

- **`target='build'` (default) — `loadblueprintbuild`. SAFE, routinely
  repeatable. CONFIRMED WORKING, 2026-08-29.** The real mechanism
  behind the game's own "Load Blueprint" button (`BuildState.
  LoadBlueprint`). **Replaces** the current editor design (calls
  `BuildState.Clear()` first) — confirmed live: loaded `single_capsule`
  and it correctly replaced the prior design. Requires `Build_PC`. One
  minor known gap: the part doesn't land at the editor's visual center
  (only somewhere grid-valid) — `Part_Utility.CenterParts`'s internals
  were never read, and this wasn't pursued further since a real launch
  auto-centers the rocket regardless, so it has no practical effect.
- **`target='world'` — `loadblueprint`. DO NOT USE DURING A LIVE
  FLIGHT.** Its first action moves the camera to the launch pad — the
  signature of a one-time internal Build-to-World launch-transition
  primitive (the actual "Launch" button's own mechanism), not a general
  spawn tool the game itself ever calls mid-flight or repeatedly.
  **Confirmed working, 2026-08-29** (a single-part blueprint spawned a
  real, visually-confirmed part) — but that confirms the reflection
  mechanism works, not that it's safe or intended for routine use.
  Materializing a fully-fueled part mid-flight has none of a real
  launch's cost/sequence/achievement tracking -- functionally cheating.
  Reserve for one-off future research only.

**Still open for both:** only a single-part blueprint has been tested.
Multi-part designs (joint generation via `GenerateJoints`, whether parts
actually connect into something flyable) and the documented possible
DLC/ownership gate (`OnPartNotOwned`/`OwnershipState` — `Capsule` is
presumably a free/base part, so this doesn't rule it out for locked
parts) remain unverified.
