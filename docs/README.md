# docs/ -- index

Quick map of what's in here, since it's grown a lot. Nothing in this
folder has been moved or renamed as part of adding this index -- every
path below is exactly where the many prompts/handoffs already given
throughout this project expect it to be. If you're a fresh session
picking this project up, start with `startup_prompt.md`.

## Read first, every new session

- **`startup_prompt.md`** -- what to read before doing any real work.

## Live, actively-maintained reference

- **`high_level_checklist.md`** -- Tier 1 physics research status:
  what's confirmed, what's still open, design decisions owed.
- **`sfs_physics_reference.md`** -- confirmed physics formulas and
  constants (gravity, drag, thrust, staging, etc.), with corrections
  documented inline rather than silently overwritten.
- **`sfs_source_reference.md`** -- the OLD single-file source-code
  reference. Being superseded by `sfs_reference/` (below) -- stays
  canonical until that migration's Step 3 (retirement) completes, don't
  edit both.

## The SFS Documentation (generated, standalone)

- **`sfs_reference/`** -- standalone, complete reference to SFS 1.6's
  own decompiled source (not this project's mod). One file per class,
  generated `INDEX.md`/`manifest.json` that can't drift from the real
  assembly. In progress -- see the plan file below for current phase.
- **`sfs_reference_plan.md`** -- the standing instructions for the SFS
  Documentation effort (scope, structure, phases). Any new Claude Code
  session working on this reads this file first.

## Session handoffs (historical record, not living docs)

- **`session-2026-08-27-sfs_source_code_docs.md`**
- **`session-2026-08-28-sfs_doc_inventory.md`**

These capture what a specific past session found/decided/corrected --
useful as a record, but `high_level_checklist.md` and
`sfs_physics_reference.md` are the up-to-date live references, not these.
