# SFS Documentation — the plan (persistent reference)

This file is the standing instructions for building "the SFS Documentation"
(`docs/sfs_reference/`). Any new session working on this should read this
file plus `docs/sfs_reference/INVENTORY.md` before doing anything else --
don't re-derive scope or re-decide settled questions from scratch.

## What this actually is

**This is "the SFS Documentation" -- a standalone, complete reference to
Spaceflight Simulator 1.6.00.16's own decompiled source code.** It is NOT
documentation of `sfsprobe` (our mod), and it isn't scoped to "what this
project currently needs" -- it documents the game itself, completely,
independent of anything built on top of it. The only relationship to our
mod is downstream: we use this documentation to verify our mod still
works correctly, especially whenever SFS itself updates versions.

**Full game coverage, including UI/Builds/ModGUI.** `SFS.UI`,
`SFS.Builds`, and `SFS.UI.ModGUI` are in scope, same as everything else.

**~26 vendored third-party types are excluded** (Firebase,
TranslucentImage, Unity IAP, the SDWebImage port, Steam/GPGS glue) --
recorded with the reason, not silently dropped. These aren't SFS's own
code and document nothing about game behavior.

## Structure -- no monolithic file

```
docs/sfs_reference/
  INDEX.md              -- master table of contents + coverage tracker
  manifest.json          -- machine-readable companion index
  INVENTORY.md            -- the full 969-type inventory (Phase 1 Step 0 output)
  inventory.json          -- machine-readable inventory
  00-infrastructure/
  01-core-flight/
  02-drag-aero/
  03-heat-destruction/
  04-engines/
  05-rcs/
  06-soi-terrain/
  07-saveload/
  08-parametric-expressions/
  09-resources-fuel/
  10-control-input/
  11-joints-docking/
  12-world-scene-timewarp/
  13-challenges-logging/
  14-misc-part-modules/
  15-ui/
  16-builds/
  17-modgui/
  18-maps-navigation/     -- SFS.World.Maps
  19-career-progression/  -- SFS.Career
  20-localization-audio/  -- SFS.Translations + SFS.Audio
  21-platform-rendering/
```

**One markdown file per class** (or a small tightly-coupled group) --
not one file per category.

**Strict per-class template, followed identically everywhere:**

```markdown
## ClassName

**Namespace:** SFS.Whatever
**Kind:** class | interface | struct | abstract class
**Extends:** BaseClass (if any)
**Implements:** IInterface1, IInterface2 (if any)
**Status:** [CONFIRMED] | [PARTIAL] | [OPEN]
**Depth:** FULL | LIGHT (see tiered depth bar below)

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|

### Methods

#### MethodName(ParamType paramName, ...) -> ReturnType

- **Access:** public/private/protected, static/instance
- **Parameters:** what each one means, valid range/units if known
- **Returns:** what it means, including null/default cases
- **Behavior:** what the IL body actually does (FULL depth only --
  LIGHT depth may skip this and note "not read, low-priority UI class")
- **Side effects:** state mutation, events fired, allocations
- **Gotchas:** known hangs, no-ops, ordering requirements, ambiguous overloads
- **Status:** [CONFIRMED] | [PARTIAL] | [OPEN]
```

**Tiered depth bar:** FULL depth (real IL-body behavior read) for
anything reflectable/callable -- simulation, gameplay logic, anything an
agent could plausibly call. LIGHT depth (signature + one-line purpose
only, explicitly marked, no full behavior narrative) for pure-view/
UI-only classes with no simulation relevance. Every class still gets an
entry either way -- LIGHT is not "skip," it's "less depth, explicitly
marked as such."

**`INDEX.md`** -- one row per documented type: name, namespace, kind,
file path, one-line summary, status, depth, coverage count.

**`manifest.json`** -- same fields as INDEX.md rows, machine-readable,
kept in sync incrementally per class, not regenerated in one pass.

## Definition of done

Every class's documentation needs to answer: real signature, inputs,
outputs; what the code does and how (FULL depth: from IL bodies, not
names; LIGHT depth: at minimum an accurate signature and purpose);
how it's structured; when/how/where it's accessible; what can/cannot be
safely run. AND it needs to live in the right file, follow the template,
and be reflected in INDEX.md and manifest.json.

Standing rules throughout: live IL-body reads not signatures-only (for
FULL-depth classes), Confirmed/Partial/Open per member, document
corrections rather than silently overwrite, save incrementally (disk +
Mnemoverse) not batched at the end, checkpoint every 3-4 classes and wait.

## Phases

**Phase 1, Step 0 (inventory) -- DONE.** See `INVENTORY.md`. 969 real
types, 53 namespaces, 6,137 methods, 4,078 fields.

**Phase 1, Step 1 -- migrate existing content.** The old
`docs/sfs_source_reference.md` (~6,590 lines) gives named headings to
only 67 of 969 types (266 mentioned anywhere in prose). This is a real
but bounded job. Split into the new structure, one class per file,
reformatted into the strict template. `docs/` is untracked in git --
scratch-backup first, diff-check nothing gets silently dropped. Build
`INDEX.md` and `manifest.json` from this as you go.

**Phase 1, Step 2 -- cover everything else.** ~90% of the total work.
Includes all of UI/Builds/ModGUI now. Same template, tiered depth bar
above.

**Phase 1, Step 3 -- retire the old file.** Once migration + new
coverage are done and confirmed, delete `docs/sfs_source_reference.md`,
repoint every reference to it (`docs/startup_prompt.md`, `README.md`,
`CLAUDE.md`, `mod_changelog.md`, `python_changelog.md`) at
`docs/sfs_reference/INDEX.md`. Grep the whole project first.

**Phase 2 -- confirmed empirical values** (only after Phase 1 is fully
done). Lives in `docs/sfs_reference/CONFIRMED_VALUES.md`. Pull every
genuinely CONFIRMED value from `sfs_physics_reference.md` section 1.
**Explicitly exclude anything drag-related** -- the dragArea mechanism
is confirmed live (2026-08-28), but the values aren't empirically
validated against measured flight deceleration yet
(`python/analyze_dragarea.py` exists for that, hasn't been run against a
real flight). One master table, cross-referenced from elsewhere rather
than duplicated.

**Phase 3 -- final verification pass** (only after Phases 1 and 2).
Full re-audit of every file against fresh IL, not just new material.
Corrections documented, not silently overwritten. Confirm INDEX.md/
manifest.json accuracy and that the old file's retirement was complete.
Close with an honest check against the Definition of Done above.

## Session boundaries -- stop and hand off explicitly

This task is too large for one continuous session. At each of these
points: run `/session-save`, summarize progress and what's next, and
tell Christian to start a new session before continuing.

- After Step 1 (migration) -- before starting Step 2
- Roughly every 15-20 classes within Step 2
- After Step 2, before Step 3
- Between Phase 1 and Phase 2
- Between Phase 2 and Phase 3
- Within Phase 3's audit, roughly every 20-30 files

A fresh session starts by reading this file plus
`docs/sfs_reference/INDEX.md` (once it exists) to see exactly where the
last one left off.
