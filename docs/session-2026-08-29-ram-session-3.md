# RAM Session #3 — SFS Documentation, Phase 1 Step 1 (migration) — 2026-08-29

## Where the project stands

The project is building an LLM agent that designs rockets in Spaceflight
Simulator, flies them, and adapts mid-flight. Still Tier 1
(research/architecture); no agent code exists. The current work item is
the **SFS Documentation restructure** laid out in
`docs/sfs_reference_plan.md`: replacing the single 6,599-line
`docs/sfs_source_reference.md` with a multi-file, machine-readable
reference at `docs/sfs_reference/` — one markdown file per class, under
numbered category folders, following a strict per-class template, indexed
by `INDEX.md` and `manifest.json`. It documents **the game** (SFS
1.6.00.16's own decompiled source), not the `sfsprobe` mod; the mod is
downstream, and the reference exists so the mod can be re-verified
whenever SFS ships an update.

**Phase 1 Step 1 (migration) is complete as of this session.** All 6,599
lines of the old file are now represented in `docs/sfs_reference/` across
**48 markdown files** — 43 per-class/group files covering **94 of 943
in-scope types (10.0%)**, plus five standalone files (`INDEX.md`,
`INVENTORY.md`, `METHODOLOGY.md`, `REFLECTION_TOOLKIT.md`,
`CORRECTIONS.md`). Folders `00-infrastructure` through
`14-misc-part-modules` are populated; `15-ui` through
`21-platform-rendering` are still empty directories.

`docs/sfs_source_reference.md` **is still on disk and still the file that
`startup_prompt.md` / `README.md` / `CLAUDE.md` point at.** It is retired
in Step 3, not before — do not delete it yet.

**Next up: Phase 1 Step 2** — net-new coverage of the remaining 849
types, ~90% of the total work. Not started. A fresh session picks it up
by reading `docs/sfs_reference_plan.md` and
`docs/sfs_reference/INDEX.md`.

## Supersedes

- **"33 per-class/group files"** (stated by Claude in this session's
  chat, and in the pre-compaction working summary) → **Wrong count. It is
  43.** Per-folder: 00→4, 01→10, 02→4, 03→2, 04→3, 05→1, 06→2, 07→3,
  08→1, 09→1, 10→1, 11→1, 12→3, 13→4, 14→3. Plus 5 standalone files = 48
  `.md` files total under `docs/sfs_reference/`. The 94-types and
  48-files figures were always right; only the "33" was wrong.

- **`docs/sfs_source_reference.md` §B5.5 status table: "`Trajectory`
  path-transition machinery — [PARTIAL]" and the `Orbit` encounter search
  as [PARTIAL]** (from 2026-08-27) → **Stale within the old file itself.**
  §B5.2.1 / §B5.2.2 / §B5.3.1 were a later depth pass that read those
  bodies and marked them [CONFIRMED]; the summary table was never
  updated. The bodies are **CONFIRMED**. Recorded as explicit
  "Correction made during migration" blockquotes at the top of
  `01-core-flight/Trajectory.md` and `01-core-flight/Orbit.md` rather
  than silently overwritten.

- **`docs/sfs_source_reference.md`: "`SFS.Variables` has 37 types" and
  "`ModLoader` has 10 types"** → Wrong. `inventory.json` (parsed from the
  IL dump) gives **36** and **11**. Corrected inline in the migrated
  files. The inventory is authoritative over the old file's hand-counted
  figures.

- **Any reference to `sfs_full_reference.md`** → That file no longer
  exists (it was renamed to `sfs_source_reference.md` on 2026-08-27). One
  stale mention survived in the old file and was **deliberately not
  carried forward** into the new corpus. It is the only identifier from
  the old file absent from the new one, and that is correct.

Nothing in `docs/sfs_physics_reference.md`,
`docs/high_level_checklist.md`, or the two earlier session files
(`session-2026-08-27-sfs_source_code_docs.md`,
`session-2026-08-28-sfs_doc_inventory.md`) was overturned this session.
Those still stand as written.

## Decided

- **Batch bounded work; checkpoint open-ended work.** The plan's standing
  rule says "checkpoint every 3-4 classes and wait." Step 1 was run as
  **one continuous pass instead**, and Christian confirmed that was the
  right call: migration is a *bounded* unit of work with a known input
  (one file) and a mechanical definition of done, so stopping every few
  classes adds round-trips without adding safety. **Step 2 is different
  and must actually checkpoint every 3-4 classes** — 849 types is
  open-ended, and periodic checkpoints matter there. This is now an
  explicit instruction, not a default to be re-reasoned about.

- **Three standalone top-level files for non-per-class content.** The
  per-class template covers classes only, but the plan forbids dropping
  anything. `METHODOLOGY.md` (old §Provenance + §Status tags + §A2),
  `REFLECTION_TOOLKIT.md` (old §A1 + §A1.1 ambiguous-overload
  catalogue), and `CORRECTIONS.md` (old corrections table) each carry an
  explicit "This is not a per-class file and so does not follow the
  per-class template" label so a future reader doesn't treat the
  deviation as sloppiness.

- **The Harmony dead-end analysis (old §A4.2–A4.5) is an appendix to
  `00-infrastructure/Loader.md`, not its own file.** Every claim in it is
  about what `ModLoader.Loader` does and doesn't load, so it belongs to
  that class. This avoids an orphan file, consistent with CLAUDE.md's
  "don't create ad-hoc notes files" rule.

- **`INDEX.md` is generated, never hand-edited.** `manifest.json` is the
  source of truth for it; `inventory.json` is the source of truth for
  namespace, kind, IL line number, and method/field counts. Callers of
  `reference_add.py` supply only `fq` / `file` / `summary` / `status` /
  `depth` — **the assembly-derived fields cannot be passed in, so they
  cannot drift from the real assembly.** Drift is prevented by
  construction rather than by discipline.

- **Folder placement for cross-cutting types** (the plan explicitly
  delegates per-type assignment to Steps 1/2 — these calls are now
  settled precedent for Step 2):
  - `SFS.Builds.Blueprint` → `07-saveload/save-records.md`. It's a save
    record, not editor UI, despite the `SFS.Builds` namespace.
  - `RocketManager` + `PartsLoader` → `07-saveload/RocketManager.md`.
    They're the load path.
  - `Double2` (global namespace) → `01-core-flight/Location.md`. Every
    trap in it is a coordinate-system trap, so it reads correctly beside
    `Location` / `WorldLocation` and nowhere else.
  - `SFS.WorldBase.Difficulty` → `06-soi-terrain/Difficulty.md`.
  - `AeroFormula` → `02-drag-aero/AeroFormula.md`.
  - **Rule extracted:** place by *what the type is for*, not by its
    namespace. Namespace is recorded in the file header and in
    `manifest.json` either way, so nothing is lost by cross-filing.

- **Group files are allowed** where a type is trivially small and
  delegates all behaviour elsewhere (e.g. `ToggleModule` inside
  `MoveModule.md`, the seven save records inside `save-records.md`). Each
  group file states why it's grouped at the top. Each contained type
  still gets its own `manifest.json` row, so coverage counting is
  unaffected.

## What worked

Both scripts are new this session and are logged in `python_changelog.md`
under 2026-08-28.

**Add types to the manifest incrementally** (from the repo root):

```bash
echo '[{"fq":"SFS.World.Rocket","file":"01-core-flight/Rocket.md","summary":"...","status":"CONFIRMED","depth":"FULL"}]' | python3 python/reference_add.py
```

It merges into `docs/sfs_reference/manifest.json`, fills namespace / kind
/ `il_line` / method+field counts from `inventory.json`, validates
`status` against `{CONFIRMED, PARTIAL, OPEN}` and `depth` against
`{FULL, LIGHT}`, then reruns the index build. It also accepts an object
form to extend the old-file §-section → new-file map:

```bash
echo '{"section_map":[["§B5.2","01-core-flight/Trajectory.md"]]}' | python3 python/reference_add.py
```

**Rebuild and validate the index:**

```bash
python3 python/reference_index.py
```

```bash
python3 python/reference_index.py --check
```

`--check` verifies every manifest `file` path exists on disk and every
`fq` is a real type in `inventory.json`. Silent success = pass.

**The diff-check that proved nothing was dropped.** Run from `docs/`.
It compares every `@NNNNN` IL line reference and every backticked
identifier in the old file against the whole new corpus:

```bash
cd docs && python3 -c '
import re, os, glob
old = open("sfs_source_reference.md", errors="replace").read()
new = "\n".join(open(f, errors="replace").read() for f in glob.glob("sfs_reference/**/*.md", recursive=True)
                if os.path.basename(f) not in ("INVENTORY.md","INDEX.md"))
old_il, new_il = set(re.findall(r"@(\d{3,6})", old)), set(re.findall(r"@(\d{3,6})", new))
print("IL refs missing:", sorted(old_il-new_il, key=int))
def idents(t):
    out=set()
    for m in re.findall(r"`([^`\n]{2,80})`", t):
        out |= set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", m))
    return out
miss = [w for w in sorted(idents(old) - idents(new)) if w not in new]
print("Identifiers absent from new corpus entirely:", miss)'
```

Final result: **`IL refs missing: []`** and
**`Identifiers absent: ['sfs_full_reference']`** — the one stale filename
noted under Supersedes. The `if w not in new` filter is what makes the
output usable: without it the raw identifier diff was 34 entries, 29 of
which were false positives (words appearing in code blocks, method names
in headings that aren't backticked, English words inside backticked
spans). **Filter against the raw new text, not just against the extracted
identifier set.**

The first run of that check found **4 genuinely dropped IL refs**
(`@195780`, `@195796`, `@195811` on `Trajectory`'s `paths[0]` forwards;
`@279388` on `ReferenceVariable<T>.set_Value`) and **5 genuinely dropped
identifiers** (`SumEnabledTorque`, `DynamicTerrain`,
`TerrainColliderModule`, `TerrainPoints`, `Chunk`). All nine were
restored by patch. **The check earns its keep — run it again at the end
of Step 2 against whatever is left of the old file.**

## Dead ends

- **Indent-based member extraction from `monodis` output is broken, and
  it fails silently.** A scratch helper (`sig.py`) that walked lines
  under a `.class` declaration and stopped at `} // end of class` at the
  matching indent reported two fields that **do not exist**:
  `public List<HeatModuleBase> best` on `SFS.World.HeatManager`, and
  `public float drag` on `AeroFormula`. Both are actually fields on
  nested `<>c__DisplayClass` **closure** types.

  Root cause: **in `monodis` output, nested classes are declared at the
  SAME indentation as the outer class**, so an indent-based scan walks
  straight past the class boundary and attributes the closure's fields to
  the outer type. This is exactly the artifact
  `docs/sfs_reference/METHODOLOGY.md` already warns about — it was
  reproduced independently here, which is decent evidence the warning is
  real and not folklore.

  Fix: **stop at the first `.class` line after the start line**, not only
  at the matching-indent `} // end of class`:

  ```python
  if depth_pat.match(l): break
  if i > start and re.match(r"^\s*\.class ", l):
      out.append(f"  [STOP: nested/next class @{i+1}: {l.strip()[:70]}]")
      break
  ```

  Both false fields are now explicitly called out as non-existent in
  `03-heat-destruction/HeatManager.md` and `02-drag-aero/AeroFormula.md`,
  so a future reader who sees them in a naive dump knows they're
  artifacts. **Step 2 will read ~849 more types this way — any field list
  produced without that stop condition is suspect.**

- **Unquoted zsh globs in `grep`.** `grep -rl "$t" --include=*.md .`
  fails with `(eval):1: no matches found: --include=*.md` because zsh
  expands the glob before `grep` sees it. Use:

  ```bash
  grep -rl --include="*.md" -- "$t" .
  ```

- **The inventory's "has a heading in the old doc" (`H`) flag has false
  positives.** Of the 67 flagged types, several match on generic
  headings: `GifDecoder/Status` ← "## Status tags"; several nested `Type`
  enums; `SFS.Career.TreeComponent/Root` ← "Root". **Don't treat
  `in_old_doc_heading` as a reliable "already documented" signal in Step
  2** — check the actual heading.

## Open

- **Phase 1 Step 2 — 849 types remaining.** Folders `15-ui`,
  `16-builds`, `17-modgui`, `18-maps-navigation`,
  `19-career-progression`, `20-localization-audio`,
  `21-platform-rendering` are entirely empty. **Checkpoint every 3-4
  classes** (Christian's explicit instruction — see Decided). The plan
  also wants a session hand-off roughly every 15–20 classes within Step 2.

- **Phase 1 Step 3 — retire `docs/sfs_source_reference.md`.** Not yet.
  Requires grepping the whole project and repointing
  `docs/startup_prompt.md`, `README.md`, `CLAUDE.md`, `mod_changelog.md`,
  and `python_changelog.md` at `docs/sfs_reference/INDEX.md`.

- **`docs/` is untracked in git.** The whole reference — 48 files of it
  now — has no version control. Worth deciding before Step 2 multiplies
  it tenfold.

- **`scratch/full_il.txt` must never be committed** (13.3 MB of
  decompiled copyrighted game code, currently gitignored). Its md5 is
  `dcf3f2dbfd670f9666d2de2fb6a5f2f0`; the assembly's is
  `cbad19d24f73252e5a7acd6b88cfa9c1`. Both are recorded in
  `manifest.json` so a future session can tell whether its dump matches
  what the reference was written against.

- **Several [OPEN] items carried through migration** are values that can
  only be resolved live, per CLAUDE.md's data-trust rule — notably
  `AeroFormula`'s four drag coefficients (serialized data), which parts
  set `MoveModule.unscaledTime`, and the `HeatManager` `+∞` vs
  `IsNegativeInfinity` mismatch. These are flagged in their files; they
  are not Step 2 blockers.
