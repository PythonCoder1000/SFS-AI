# RAM Session #5 — SFS Documentation, Phase 1 Step 1.5 + Preconditions backfill — 2026-08-29

## Where the project stands

The project is building an LLM agent that designs rockets in Spaceflight
Simulator, flies them, and adapts mid-flight. Still Tier 1
(research/architecture); no agent code exists. The current work item is the
**SFS Documentation** at `docs/sfs_reference/` — a standalone, complete
reference to Spaceflight Simulator 1.6.00.16's own decompiled source. This
session ran two units of work on top of session #4's Step 2 batch 1:
**backfilling the newly-required `Preconditions` field** into the four
files session #4 wrote, and **Phase 1 Step 1.5 (the Mod-Integration Safety
Audit)**, a one-time pass the plan added mid-session-#4 specifically to
find shipped mod commands built on unread method bodies before Step 2
resumes.

Coverage moved **113 → 116 of 936 in-scope types (12.4%)**, with two new
files (`12-world-scene-timewarp/SandboxSettings.md`,
`16-builds/BuildState.md`) written specifically to back live `sfsprobe`
commands that had zero or partial coverage. **Step 1.5 is done.** Its 8
findings were handed to a **concurrent session** working on `sfsprobe`
itself, which fixed all 8 in commit `1ab7b29` (already on `main`) —
confirmed by reading that commit's message and diff before writing this
handoff, not assumed.

**Next up, per the plan and Christian's explicit instruction this
session:** a fresh session's **first task, before touching Step 2 at all,**
is clearing the **Preconditions backlog** — 164 of 227 FULL-depth method
entries across the 43 Step 1 (migration) files still lack the field. This
was decided as "clear all 164 before Step 2, not after" specifically to
avoid the corpus staying permanently split into pre/post-rule halves while
Step 2 keeps adding to the total. Only after that backlog is at 0 does
Step 2 (net-new coverage of the remaining ~820 types) resume.

## Supersedes

- **The plan's Step 1.5 risk classification: `autostop` listed as
  state-mutating** (`docs/sfs_reference_plan.md`, added earlier in session
  #4) → **Wrong, corrected this session.** Reading `Probe.CheckAutoStop()`
  in full shows it only *reads* `location.Height`, `.VerticalVelocity` and
  `rb2d.mass`, and its only "mutation" is stopping the **mod's own**
  telemetry recording (`StopRecording()`, `AutoStop = false`) — it never
  writes any game state. It is read-only. Recorded as finding #8 in the
  Step 1.5 commit (`cbe6472`); not yet propagated into the plan file's risk
  list itself (that edit was not made — see Open).

- **Session #4's stated concern that the four Step 2 files "don't carry
  Preconditions fields... back-fill these before writing more Step 2
  files"** → **Done.** 51 Preconditions fields added across the four files
  (35 `terrain-chunks.md`, 12 `TerrainModule.md`, 3 `planet-data-modules.md`,
  1 `Atmosphere_Physics.md`), verified by `reference_audit.py --check`
  passing on those four files specifically.

- **`docs/sfs_reference/INVENTORY.md`'s "~26 vendored types excluded"
  and `docs/sfs_reference_plan.md`'s same figure** (both still literally
  present in those files as of session #4's handoff, which noted this as
  deliberate) → **`sfs_reference_plan.md` corrected in place this session**
  to 33 excluded / 936 in scope, with a dated note explaining why (it's the
  standing brief every session reads first, so a stale scope number there
  actively misleads, unlike the Step 0 artifact). `INVENTORY.md` was
  **not** changed — it now carries an inline `**CORRECTION (2026-08-29)**`
  block instead, matching the precedent `METHODOLOGY.md` already set for
  its own 2026-08-28 "Top-level types | 1,509" fix. `CORRECTIONS.md`'s
  entry from session #4 stands unchanged.

- Nothing else from sessions #1–#4 was overturned.

## Decided

- **A wrong count inside a live, non-generated project file gets fixed
  in place, following the project's own existing precedent — not just
  logged in `CORRECTIONS.md`.** Christian's question this session was
  specifically whether `sfs_reference_plan.md` and `INVENTORY.md` "are
  meant to stay as originally written... rather than needing their own
  update." The answer: `METHODOLOGY.md` already has a live
  `**CORRECTION (2026-08-28)**` block fixing its own wrong "1,509" count in
  place, right next to the original sentence. That is the standing
  convention, and it is one level more specific than "document corrections,
  never overwrite them" — it says corrections to a *file's own claim about
  itself* (a count, a figure) get an inline fix with the correction visible
  at the point of the error, while corrections that overturn an earlier
  *reference entry's claim about the game* go in `CORRECTIONS.md`. Applied
  here: `sfs_reference_plan.md` (a live brief, re-read every session) got
  the inline fix; `INVENTORY.md` (a frozen Step 0 artifact) got an inline
  CORRECTION block rather than having its original figure silently changed,
  consistent with "document corrections, never overwrite them."

- **Clear the Preconditions backlog before resuming Step 2, not
  alongside it or after it.** Christian's explicit call, given two options
  (leave as tracked debt vs. clear first): "it's mechanical, and leaving it
  means the corpus stays split into pre/post-rule halves while Step 2 keeps
  growing the total." This is now the fresh session's first task,
  ahead of Step 2, and should be treated as a hard sequencing rule the same
  way Step 1.5 itself was.

- **Step 1.5's findings get handed off, not fixed, by the documentation
  session.** The plan is explicit about this ("that's Python/C# work, a
  different session's job") and it played out exactly that way: a
  concurrent session picked up all 8 findings from this session's commit
  message and shipped fixes in `1ab7b29` within the same session window.
  This validates the plan's division of labor — the documentation session's
  job is to make the gap precise enough that fixing it is a five-minute
  follow-up, not to touch `SFSProbe.cs` itself.

- **`reference_audit.py` is now the standing mechanism for the
  Preconditions rule**, not a one-off script. It has two modes matching
  `reference_index.py`'s convention (plain report vs. `--check`, silent
  pass / exit 1 fail) and is logged in `python_changelog.md`. The backlog
  number it reports (164, now the same run reports fewer after this
  session's two Step 1.5 files — rerun it fresh, don't trust this file's
  number) is the thing the next session should drive to zero.

- **Folder placement for the two Step 1.5 files, on the established
  "place by what it's for" rule:** `SandboxSettings` went to
  `12-world-scene-timewarp/` despite its `SFS.UI.*` field types, because
  what it *is* is world-scoped cheat state whose effects land in `Physics`,
  `AeroModule`, `HeatManager`, `FlowModule`. `BuildState` opened
  `16-builds/` (previously empty) as the obvious namespace-correct home —
  no cross-cutting call needed there.

- **A Step 1.5 file can be deliberately partial and say so up front.**
  `BuildState.md` covers exactly one method (`LoadBlueprint`) at FULL
  depth and states plainly at the top that everything else in the class is
  signature-only and left for ordinary Step 2 — Step 1.5's job is closing
  the "unread body, already shipped" gap, not achieving full coverage of
  whatever class that body happens to live in.

## What worked

### The Preconditions backfill: a table-driven script, not manual editing

51 insertions across 4 files by hand would have been slow and
inconsistent. The approach: build a Python dict mapping
`(filename, "#### heading-prefix")` → precondition text, then a second
pass that finds each heading, locates the right insertion point (before
`- **Behavior:**` if present, else before the first of
Note/Notes/Gotcha/Gotchas/Consequence/Side effects/Status, else end of
block), and inserts a `textwrap.fill`-formatted bullet.

```python
def add(f, h, t): P[(f, h)] = t
add("terrain-chunks.md", "#### UpdateChunks()",
 "World scene. `TerrainColliderManager.main` must be populated — the "
 "method ends in an unconditional `main.RemoveChunks`/`main.AddChunks` "
 "pair. ...")
# ... repeated per method
```

```python
for i, l in enumerate(lines):
    if l.startswith("## "): tname = l[3:].strip()
    elif l.startswith("#### "):
        matches = [i for i in heads if lines[i].startswith(key)]
        h = matches[occurrence - 1]
        end = next block boundary (#### / ## / ---)
        ins = index of "- **Behavior:**" in [h+1, end), else
              first of Note/Gotcha/Consequence/Side effects/Status, else end
        insert textwrap.fill("- **Preconditions:** " + text, width=76,
                              subsequent_indent="  ")
```

**Ambiguity handling that mattered:** two files have a method name that
appears twice under different types (`OnDestroy()` on both
`TerrainColliderModule` and `DynamicTerrain` in `terrain-chunks.md`). The
key scheme used a `#N` suffix (`"#### OnDestroy()#2"`) to disambiguate by
occurrence order, resolved by `re.search(r"#(\d+)$", key)` before matching.
Getting this wrong silently double-inserts into the first occurrence and
skips the second — worth a manual `grep -c "Preconditions:"` sanity check
per file after running, which is what caught nothing wrong here but would
catch it if it happened.

**For the handful of FULL-depth types with no `#### ` sections at all**
(field-only classes like `BasicModule`, `OrbitModule`, `WaterModule`,
`FlatZone`) — the audit script (below) flags these as a *separate*
category from "missing Preconditions", and the right fix is different: add
a `### Methods` section with a `.ctor()` entry carrying the field, not
retrofit a bullet into prose that has no method heading to attach to. Six
of these were added by hand this session (see per-file breakdown).

### `python/reference_audit.py` — new, permanent

```bash
python3 python/reference_audit.py            # full report
python3 python/reference_audit.py --check    # silent on pass, exit 1 on fail
```

Walks every `.md` under `docs/sfs_reference/` except the five standalone
files (`INVENTORY.md`, `INDEX.md`, `METHODOLOGY.md`, `REFLECTION_TOOLKIT.md`,
`CORRECTIONS.md`), tracks the current `## ` type heading and its
`**Depth:**` line, and for every `#### ` method entry under a FULL-depth
type checks for a `- **Preconditions:**` bullet in that entry's block
(bounded by the next `#### `, `## `, or `---`). Also reports FULL-depth
types with zero `#### ` entries — not a failure by itself, but worth
eyeballing since it can mean "methods not written up yet" as easily as
"genuinely has none beyond a compiler-generated ctor."

Run it fresh at the start of the next session — do not trust any specific
number quoted in this file, since Step 1.5's two new files already moved
it from 166 to a lower number mid-session and it will move again as the
backlog is cleared.

### Reading a private-static-caller cross-reference for a mod-integration audit

For Step 1.5, the useful move was reading `SFSProbe.cs`'s `Command()`
switch top to bottom (`grep -n "case \"" sfsprobe/SFSProbe.cs`) and, for
each case, tracing every reflection call (`FindType`/`GetMethod`/`Invoke`)
back to a real IL method, then checking `docs/sfs_reference/`'s current
coverage for that method. This surfaced two classes (`SandboxSettings`,
`BuildState`) with either zero or partial coverage backing live commands —
exactly the gap the plan wrote Step 1.5 to find. The mod's own
`Invoke`/`FindComponent` helpers were also worth reading directly (not just
the call sites) — that's what surfaced Finding #1 (`FindObjectsOfTypeAll`
vs. the confirmed `main` static field), since the bug is in the *helper*,
used identically by both `cheat` and (at lower risk) `loadblueprintbuild`.

### Verifying a concurrent session's fix landed, before writing this handoff

Rather than assume the findings handed off were acted on, this session ran
`git log --oneline -8` and `git show --stat 1ab7b29` / `git log -1
--format=%B 1ab7b29` before writing anything about their status here. This
confirmed all 8 findings were fixed in that single commit, already merged
to `main`, and let this handoff state that as a checked fact rather than a
hope. **Always do this before describing another session's work in a
handoff — a stated intention to fix something is not the same as a
commit that did.**

## What landed, file by file

**`docs/sfs_reference/12-world-scene-timewarp/SandboxSettings.md`** —
`SandboxSettings` (PARTIAL/FULL — the toggle path; UI path `[OPEN]`) +
`SandboxSettings/Data` (CONFIRMED/FULL). Backs the `cheat` command, which
had **no coverage at all** before this session. Key findings baked into
the file itself (not just the commit message): every `Toggle*` method is
**private**, all eight require a loaded world (`OnToggle()` dereferences
`Base.worldBase.paths`/`.settings` unguarded), and `OnToggle()` writes the
world settings file to disk **unconditionally** on every call. A complete
IL cross-reference table shows exactly which simulation path each of the
eight flags reaches (`noGravity` → `Physics.FixedUpdate`,
`noAtmosphericDrag` → `AeroModule.FixedUpdate`, etc.) — useful for an agent
that needs to know whether a cheat-flagged run is still physically
meaningful. Also documents the `infiniteOxygen`-has-no-backing-method gap
(9 UI buttons, 8 `Data` flags, 8 `Toggle*` methods) as `[OPEN]`.

**`docs/sfs_reference/16-builds/BuildState.md`** — first file in
`16-builds/`. `LoadBlueprint` at FULL depth (full pseudo-C# reconstruction
of the body, `@94165`–`@94284`); everything else in the class
(`SpawnBlueprint` — name collision with the unrelated
`RocketManager.SpawnBlueprint`, `Clear`, `GetBlueprint`,
`UpdatePersistent*`) is `[OPEN]`, stated explicitly as deliberate. A
comparison table at the top contrasts `BuildState.LoadBlueprint`
(`Build_PC`, replaces, no `WorldView` dependency) against
`RocketManager.SpawnBlueprint` (`World_PC`, adds, requires `WorldView.main`)
— the exact inversion behind the original incident.

**Preconditions backfill locations** (by file, method count):
`terrain-chunks.md` 35, `TerrainModule.md` 12, `planet-data-modules.md` 3
(plus `### Methods` sections added by hand to `BasicModule`, `OrbitModule`,
`WaterModule`, `FlatZone`, since those are field-only FULL-depth types with
no prior method entries at all), `Atmosphere_Physics.md` 1. Two
already-existing entries from earlier sessions also got Preconditions
added because Step 1.5 commands depend on them:
`RocketManager.SpawnBlueprint` (`loadblueprint`) and
`GameManager.RevertToLaunch` (`revert`). `JsonWrapper.md`'s `FromJson<T>`
signature-table entry got a prose Preconditions note appended instead of a
`#### ` bullet, since that file documents the whole class as a signature
table with no per-method headings — flagged in the file as an intentional
template deviation for that reason.

## Step 1.5 — the audit table and findings

Full command-by-command classification (read-only vs. state-mutating,
methods called, body status) is in commit `cbe6472`'s message and is not
repeated field-by-field here; the 8 findings are, since Christian asked for
them in full and they are the actual deliverable of this phase.

1. **`cheat` resolves `SandboxSettings` via
   `Resources.FindObjectsOfTypeAll(t)[0]` instead of the confirmed public
   static `main` field `Awake()` publishes.** `FindObjectsOfTypeAll`
   returns inactive objects and prefabs in unspecified order. If `[0]`
   isn't the live component, the toggle flips a **detached** `Data` — and
   because `OnToggle()` saves the *global* `Base.worldBase.settings`
   rather than `this.settings`, the command still writes the file and
   still reports `"toggled X"` while changing nothing about the
   simulation. A silent-success failure mode. **Fixed in `1ab7b29`** —
   now uses the confirmed `SandboxSettings.main`.

2. **`cheat` writes the world settings file to disk on every invocation.**
   `OnToggle()` calls `SaveWorldSettings` unconditionally; nothing in the
   original mod code or its comment indicated this. Documented (not itself
   a bug); no fix needed beyond awareness.

3. **`cheat` requires a loaded world and had no scene gate.**
   `OnToggle()` dereferences `Base.worldBase.paths` with no null check, so
   calling it from the main menu threw uncaught. **Fixed in `1ab7b29`** —
   now checks `Base.worldBase` first.

4. **`arg` was interpolated into a method name unvalidated
   (`"Toggle" + arg`), case-sensitive, unlike `cmd`.** `cheat
   InfiniteOxygen` can never work regardless of casing — there is an
   `infiniteOxygen` UI button but no corresponding `Data` flag and no
   `ToggleInfiniteOxygen` method. **Documented, not changed** — `1ab7b29`'s
   message states the case-sensitivity is "correct behavior, not a bug"
   and documents (does not attempt to fix) the `InfiniteOxygen` gap, which
   is correct: there is no backing method to call regardless of casing
   fixes.

5. **`BuildState.LoadBlueprint`'s `Clear(applyUndo)` runs first and
   unconditionally, before the blueprint is validated at all.** A
   **failed** load therefore also destroys the current editor design;
   `loadblueprintbuild: FAILED reason=load_exception` read as "nothing
   happened" when it should read as "your design may be gone." **Fixed in
   `1ab7b29`** — `loadblueprintbuild` now pre-validates part names against
   the real part catalog *before* calling `LoadBlueprint` at all, catching
   the most likely failure mode while the design is still intact, and
   warns explicitly when a failure outside that check might have destroyed
   it anyway (since `Clear()` running first inside the game's own method is
   not something the mod can prevent, only warn about).

6. **`LoadBlueprint` mutates `blueprint.parts[i].position` in place** when
   `blueprint.offset != Vector2.zero`. Calling it twice with the same
   in-memory `Blueprint` applies the offset twice. Safe today only because
   `sfsprobe` deserializes a fresh `Blueprint` per invocation. Documented;
   no code depends on reusing a `Blueprint` instance, so no fix needed.

7. **`BuildState.Clear` and `SandboxSettings.Refill` are public,
   state-mutating, and were unread at the time of the audit.** Neither is
   wired to any command. Per the plan's HARD RULE they must not be wired
   until their bodies are read. Still `[OPEN]` in the reference; not
   addressed by `1ab7b29` since nothing calls them.

8. **Correction to the plan's own Step 1.5 risk-classification list**:
   `autostop` is listed there as state-mutating; reading
   `Probe.CheckAutoStop()` shows it only reads `location.Height`,
   `.VerticalVelocity`, `rb2d.mass`, and its only mutation is stopping the
   **mod's own** telemetry recording. It never writes game state. This is
   a correction to `sfs_reference_plan.md`'s Step 1.5 section, not yet
   applied to that file — see Open.

## Dead ends

None specific to this session — the extraction tooling from session #4
(`mem.py`, the nested-class stop fix) worked without modification for both
`SandboxSettings` and `BuildState`.

## Open

- **The Preconditions backlog — 164 (as of the last check before Step
  1.5's two new files; rerun `python3 python/reference_audit.py` fresh) of
  227 FULL-depth method entries, entirely in the 43 Step 1 migration
  files.** This is the fresh session's **first task**, ahead of Step 2, per
  Christian's explicit decision this session. It is mechanical — the
  backfill approach from this session (table-driven script keyed by
  `(file, heading)`, checked against IL for each entry rather than restated
  from memory) is reusable, but 164 entries across 43 files is real
  research work, not just formatting: each precondition still needs to be
  checked against the actual method body, the way this session's four
  files were, not filled in generically.

- **`sfs_reference_plan.md`'s Step 1.5 section still lists `autostop` as
  state-mutating.** Finding #8 above corrects this but the plan file
  itself was not edited to match. A five-minute fix for whoever touches
  that section next.

- **A concurrent session is actively committing to this repo.** As of
  this handoff, `sfsprobe/SFSProbe.cs` has **uncommitted changes on top
  of** `1ab7b29` (the Step 1.5 fix commit) — `git status --short` shows it
  modified, and `git diff --stat 1ab7b29 -- sfsprobe/SFSProbe.cs` shows 62
  insertions / 2 deletions beyond that commit. **A fresh session should run
  `git log --oneline -10` and `git status` before assuming a clean starting
  point** — this is not this documentation track's work and should not be
  touched by it, but it means the repo state is actively moving on a
  parallel track. Do not assume the commit hash cited in this file (`1ab7b29`)
  is still `HEAD` by the time a new session starts.

- **Phase 1 Step 2 — resumes only after the Preconditions backlog is
  clear.** ~820 types remain (936 in scope − 116 done). `SFS.World.TerrainSampler`
  is still the highest-value next target once Step 2 resumes (per session
  #4's handoff — three files already reference it as their top open
  dependency).

- **`SandboxSettings`'s UI/purchase-gating half** (`Start`, `OnOpen`,
  `UnlockCheats`, `Refill`, `UpdatePreventUse`, `ShowUnlockCheats`) and
  **`BuildState`'s non-`LoadBlueprint` methods** (`SpawnBlueprint`,
  `Clear`, `GetBlueprint`, `UpdatePersistent*`) remain `[OPEN]`,
  deliberately, for ordinary Step 2 coverage of `12-world-scene-timewarp/`
  and `16-builds/` respectively. `GetBlueprint` is flagged in-file as the
  highest-value next read in `BuildState` — the natural editor-design-dump
  counterpart to `LoadBlueprint`.

- **Phase 1 Step 3 — retire `docs/sfs_source_reference.md`.** Still not
  started; unchanged from session #4's handoff.

- **`scratch/full_il.txt` must never be committed** (unchanged from prior
  sessions). md5 `dcf3f2dbfd670f9666d2de2fb6a5f2f0`; assembly md5
  `cbad19d24f73252e5a7acd6b88cfa9c1`. Both recorded in `manifest.json`.
