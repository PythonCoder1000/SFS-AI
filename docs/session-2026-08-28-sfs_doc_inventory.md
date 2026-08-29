# SFS Documentation restructure — Phase 1 Step 0 (inventory) — 2026-08-28

## Where the project stands

`docs/sfs_source_reference.md` — a single 6,590-line file documenting
Spaceflight Simulator 1.6.00.16's own decompiled source — is being
replaced by a multi-file, machine-readable API reference at
`docs/sfs_reference/`: one markdown file per class under numbered
category folders, following a strict per-class template, indexed by
`INDEX.md` (navigation + coverage tracker) and `manifest.json`
(machine-readable companion). This documents **the game**, completely and
independent of `sfsprobe`; the mod is downstream of it, and the point of
the reference is to re-verify the mod whenever SFS ships a new version.

This session did **Phase 1, Step 0 only: the inventory**. Nothing has
been migrated or written yet. `docs/sfs_reference/` currently holds
exactly two files — `INVENTORY.md` and `inventory.json` — and
`docs/sfs_source_reference.md` is still the live reference, still pointed
at by `startup_prompt.md`, `README.md` and `CLAUDE.md`. It is retired in
Step 3, not before.

The headline number: **969 real types**, not the ~400-ish the old file's
structure implied, and the old file gives only **67** of them a named
heading. Step 2 (net-new writing) is the overwhelming bulk of the work.

## Supersedes

- **"Top-level types | 1,509"** (`docs/sfs_source_reference.md`, provenance
  table, from 2026-08-27) → Wrong on two counts. 1,509 is every `.class`
  declaration in the dump, which includes nested types *and* 540
  compiler-generated ones (closures, `<>c__DisplayClass*`, iterator state
  machines, `<PrivateImplementationDetails>` and its
  `__StaticArrayInitTypeSize=*` structs). Real figure: **969 types, 738
  top-level, 231 nested**. Corrected in place in that file this session,
  with the correction noted rather than silently overwritten.

- **"Scope: exclude `SFS.UI` (87 types), `SFS.Builds` (25), and
  `SFS.UI.ModGUI` (18)"** (`docs/session-2026-08-27-sfs_source_code_docs.md`,
  Decided section) → Reversed by Christian. All three are **in scope now**,
  same writing bar as everything else, no exclusions. The open design
  question that motivated the exclusion ("does the agent play the in-game
  editor?") is no longer a gate on documenting them.

- **The single-file structure itself** (implicit in every prior session)
  → Superseded. No more appending to one growing markdown file.

Nothing else from the 2026-08-27 handoff or the physics reference was
overturned — those files still stand as written.

## Decided

- **Include all of `SFS.UI` / `SFS.Builds` / `SFS.UI.ModGUI`** — settled by
  Christian, not re-litigable. Full game coverage.
- **Multi-file structure over one file** — the old file had already reached
  6,590 lines while covering 67 types. Linear extrapolation to 969 types is
  unreadable and unnavigable; per-class files plus a strict template make
  it machine-readable without switching to a JSON-only format.
- **Consistency is what makes it machine-readable, not the format** — the
  per-class markdown template is followed identically everywhere, and
  `manifest.json` carries the same fields as each `INDEX.md` row so a script
  can answer "which file documents X" / "what's our coverage %" without
  parsing prose.
- **Save the inventory as a script, not a one-off** — `python/il_inventory.py`,
  so the inventory can be regenerated against a future SFS build and diffed.
  That diff is exactly the "did the game update break us" check the whole
  reference exists to support.

## What worked

Verify the pinned build before trusting the dump (do this every session):

```bash
md5 "/Users/christianjin/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/SpaceflightSimulatorGame.app/Contents/Resources/Data/Managed/Assembly-CSharp.dll"
# expect cbad19d24f73252e5a7acd6b88cfa9c1
md5 -q "scratch/full_il.txt"
# expect dcf3f2dbfd670f9666d2de2fb6a5f2f0
```

Both matched this session, so `scratch/full_il.txt` line references are
still valid.

Regenerate the inventory (run from the project root):

```bash
python3 python/il_inventory.py
```

Prints `class declarations: 1509 | real types: 969` and rewrites
`docs/sfs_reference/inventory.json`.

Two parsing gotchas in `monodis` output, both hit and fixed — worth
knowing before writing any new IL-parsing tooling:

- The type name is the **first token after the flag keywords**, not the
  last token on the line. Generic declarations end in their type-parameter
  list — `.class public auto ansi abstract beforefieldinit Singleton`1<(class [UnityEngine.CoreModule]UnityEngine.Component) T>`
  — so a last-token heuristic yields `T>`.
- Quoted names (`'<>c__10`1'`) must be unquoted **before** splitting on
  `` ` `` or `<`, or they parse to the empty string.

`monodis` also closes each type with `} // end of class <Name>`, which is
what the parser uses to pop the nesting stack — more reliable than brace
counting, since IL bodies contain braces.

## Inventory results

| | Count |
|---|---|
| `.class` declarations | 1,509 |
| Compiler-generated (excluded) | 540 |
| **Real types** | **969** |
| Top-level / nested | 738 / 231 |
| Namespaces (incl. global) | 53 |
| Method declarations | 6,137 |
| Field declarations | 4,078 |

Kinds: 728 class, 71 enum, 66 static class, 35 abstract class, 30 struct,
28 interface, 11 delegate.

Ten biggest namespaces: `SFS.Parts.Modules` 163, global 145, `SFS.World`
117, `SFS.UI` 96, `SFS.Builds` 38, `SFS.Variables` 36, `SFS.Parts` 32,
`SFS` 28, `SFS.World.Maps` 27, `SFS.Input` 27.

The brief's estimates for the three newly-in-scope namespaces (87 / 25 /
18) are exactly right as **top-level** counts. Including nested types the
real totals are **96 / 38 / 19 = 153 types**, 951 methods, 739 fields.

**Coverage baseline for migration:** of 969 types, the old file gives 67
a named heading (real per-type content to migrate) and mentions 266
anywhere in its prose (a loose upper bound — most are one-line references
inside another type's section). Migration therefore inherits substantive
content for roughly 7–27% of the inventory.

Full per-namespace tables and the complete 969-row type list are in
`docs/sfs_reference/INVENTORY.md`.

## Open — needs Christian's call before Step 1 starts

1. **Four extra category folders.** The brief's 18 folders were sized
   against the old doc's coverage, not against 969 types. Four namespaces
   have no home in that list at all — `SFS.World.Maps` (27), `SFS.Career`
   (19), `SFS.Translations` (18), `SFS.Audio` (13) — and
   `14-misc-part-modules` would otherwise absorb ~110 unrelated types.
   Proposed: keep all 18 as named, add `18-maps-navigation`,
   `19-career-progression`, `20-localization-audio`,
   `21-platform-rendering`. Full mapping table in `INVENTORY.md`.

2. **~26 vendored third-party types.** Flagged rather than dropped,
   because "no exclusions" was the standing decision — but these are
   third-party libraries compiled into `Assembly-CSharp.dll`, not SFS's
   own code, and they document nothing about game behaviour:
   `Firebase.Internal` (3), `TranslucentImage` (3),
   `UnityEngine.Purchasing.Security` (3), `UV` (3), the SDWebImage port in
   the global namespace (`SD*` ~9 plus `GifDecoder`), and platform SDK glue
   (`GPGSIds`, `FbAuth`, `SteamManager`). Recommend excluding with a row in
   `INVENTORY.md` recording why.

3. **Scale check.** 969 types at the stated writing bar (real IL-body
   reads, every parameter, return semantics, side effects, gotchas,
   per-member status) is a genuinely large amount of work — the brief's
   "15–20 classes per session" pacing puts it at roughly 50 sessions.
   Worth deciding now whether that's the actual intent, or whether some
   tiers get a lighter bar (e.g. layout-and-signature only for pure-UI
   view classes, full depth for anything an agent would call).

## Next step

Phase 1, Step 1 — migration. In order:

1. Scratch-backup `docs/sfs_source_reference.md` (it is untracked in git,
   so there is no other copy).
2. Split it into per-class files under the category folders, reformatted
   into the strict per-class template.
3. Diff-check that nothing was silently dropped in the split.
4. Build `INDEX.md` and `manifest.json` incrementally as classes land, not
   in one pass at the end.

Checkpoint every 3–4 classes. A fresh session should start by reading
`docs/sfs_reference/INVENTORY.md`.
