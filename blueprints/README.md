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

Via `sfsprobe_load_blueprint` (sfsprobe_mcp) / the mod's `loadblueprint`
command -- reads the file directly (does NOT require it to be inside the
game's own `Saving/Blueprints/` folder), deserializes it via the game's
own `JsonWrapper.FromJson<Blueprint>`, and calls
`RocketManager.SpawnBlueprint` through reflection. No editor UI
interaction needed.

**Must be called from `World_PC` (a loaded flight/world), not
`Build_PC` (the editor).** Found the hard way, 2026-08-29: the first
live test (from `Build_PC`, an untested assumption) threw a
`NullReferenceException`. Reading `SpawnBlueprint`'s actual IL body
showed why -- its first instructions call
`WorldView.main.SetViewLocation(...)`, and that singleton is only
populated in `World_PC`. The mod enforces this now (`reason=
not_in_world` if called from the wrong scene).

**CONFIRMED WORKING, 2026-08-29.** Retested from `World_PC` after the
scene fix: `sfsprobe_load_blueprint(name="single_capsule")` returned
`success: true`, rocket count went 1->2, part count went 8->9, and
Christian visually confirmed a real capsule spawned next to the
existing rocket in-game. The whole pipeline works end to end -- write a
plain JSON file, no editor interaction, spawn through the game's own
code.

**Still open:** only a single-part blueprint has been tested. Multi-part
designs (joint generation via `GenerateJoints`, whether parts actually
connect into something flyable) and the documented possible DLC/
ownership gate (`OnPartNotOwned`/`OwnershipState` -- `Capsule` is
presumably a free/base part, so this test doesn't rule that out for
locked parts) remain unverified.
