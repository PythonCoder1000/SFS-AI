# RAM Session #4 — SFS Documentation, Phase 1 Step 2 batch 1 — 2026-08-29

## Where the project stands

The project is building an LLM agent that designs rockets in Spaceflight
Simulator, flies them, and adapts mid-flight. Still Tier 1
(research/architecture); no agent code exists. The current work item is the
**SFS Documentation** at `docs/sfs_reference/` — a standalone, complete
reference to Spaceflight Simulator 1.6.00.16's own decompiled source, one
markdown file per class under numbered category folders, following the
strict per-class template in `docs/sfs_reference_plan.md`, indexed by
`INDEX.md` and `manifest.json`. It documents **the game**, not the
`sfsprobe` mod; the mod is downstream, and the reference exists so the mod
can be re-verified whenever SFS ships an update.

**Phase 1 Step 1 (migration) completed in session #3. Phase 1 Step 2
(net-new coverage) started this session and is now in progress.** Coverage
went **94 → 113 of 936 in-scope types (12.1%)**, adding four files to
`docs/sfs_reference/06-soi-terrain/`. Everything is committed and pushed —
see `bbbe4f8`.

**Next up:** continue Step 2. The natural next unit is the rest of
`SFS.World.PlanetModules` (`Atmosphere_Visuals` + its 3 nested +
`ColorGradient/Key`, `PostProcessingModule` + `Key` = 7 types, all purely
visual → LIGHT depth), then `SFS.World.TerrainSampler`, which three
already-written files list as their top [OPEN] dependency. A fresh session
starts by reading `docs/sfs_reference_plan.md` and
`docs/sfs_reference/INDEX.md`.

`docs/sfs_source_reference.md` **is still on disk and is still what
`startup_prompt.md` / `README.md` / `CLAUDE.md` point at.** It is retired in
Step 3, not before — do not delete it yet.

## Supersedes

- **"~26 vendored third-party types are excluded"** (stated in
  `docs/sfs_reference_plan.md`, `docs/sfs_reference/INVENTORY.md`
  "Out-of-scope candidates", and `manifest.json`'s `excluded_types: 26`)
  → **Wrong. It is 33.** The 26 counted only *top-level* vendored types.
  The SDWebImage port also contributes **7 nested** types
  (`SDAnimatedImage/State`, `/LoadingIndicatorType`,
  `/OnImageSizeReadyAction`, `/OnDecodingErrorAction`,
  `/OnLoadingErrorAction`, `SDWebImage/LoadingIndicatorType`,
  `/OnImageSizeReadyAction`, `/OnLoadingErrorAction`,
  `SDWebImageDownloaderError/ErrorType`), which `inventory.json` counts as
  real types.

  Consequences: **in scope is 936, not 943**, and the Step 2 remainder at
  the start of this session was **842, not 849**. `manifest.json` corrected,
  `INDEX.md` regenerated, and the correction logged in
  `docs/sfs_reference/CORRECTIONS.md` under a new "Corrections made during
  Phase 1 Step 2" table. **`INVENTORY.md` and `sfs_reference_plan.md` still
  say 26** — deliberately, since the plan file is the standing brief and
  `INVENTORY.md` is a Step 0 artifact; `CORRECTIONS.md` is the mechanism the
  project already uses for this. A future session reading either of those
  two files should treat `manifest.json` as authoritative.

- **`docs/session-2026-08-29-ram-session-3.md` "Open": "`docs/` is untracked
  in git. The whole reference — 48 files of it now — has no version
  control."** → **Resolved before this session started.** All 59 files
  including `sfs_reference/` are committed and pushed to `origin/main`. No
  action needed. Christian added a standing instruction on top of this: at
  each Step 2 session boundary, commit the new/changed files under
  `docs/sfs_reference/` (plus `INDEX.md` and `manifest.json`) with a
  descriptive message **before** running session-save and stopping.

- Nothing in `docs/sfs_physics_reference.md`, `docs/high_level_checklist.md`,
  or sessions #1–#3 was otherwise overturned. In particular, **session #3's
  `sig.py` nested-class dead end was independently re-confirmed as real this
  session** — the stop-at-next-`.class` fix was required from the first
  extraction and is baked into the scripts below.

## Decided

- **Checkpoint means "save incrementally and report", not "block for
  approval".** Session #3 recorded Christian's instruction that Step 2
  must checkpoint every 3–4 classes, in contrast to Step 1 which was
  correctly run as one continuous pass. This session ran that as three
  save-points (7 types → 6 → 6), each one writing the file to disk,
  registering the types in `manifest.json`, regenerating `INDEX.md`, and
  running `reference_index.py --check` before moving on. The point is that
  no work is ever held only in context; it is not a request for a
  round-trip. Christian's framing for this session was "checkpointing every
  3-4 classes, and stop for a fresh session roughly every 15-20", which
  reads as save-points plus one hard stop. 19 types landed before stopping.

- **For a field-only serialized data class, the valuable content is the
  constructor defaults and the consumer map, not the field list.** Several
  of these classes have no methods at all beyond `.ctor()`, so the template's
  Methods section is nearly empty and a naive entry is just a retyped field
  table. Two things make them worth reading:
  1. **Real defaults read from IL**, which are often sentinels rather than
     zero — `Atmosphere_Physics.height`/`density`/`curve` default to `-1.0`
     (that is how a vacuum body is expressed *and* how a malformed planet
     file fails), and `BasicModule.velocityArrowsHeight` defaults to
     **`NaN`**, so every comparison against it is false.
  2. **A whole-assembly IL cross-reference of who reads each field**, which
     is where the cross-cutting facts live:
     `BasicModule.gravity` reaches `WheelModule.OnCollisionStay2D` and
     `Astronaut_EVA`, not only `Orbit.TryCreateOrbit`;
     `WaterModule.wavesSize` feeds buoyancy via
     `Water_Rocket.<FixedUpdate>g__GetWaveHeight|2_0`, not only the shader;
     `Atmosphere_Physics.parachuteMultiplier` is read by `BalloonModule` as
     well as `ParachuteModule`; `OrbitModule` is **read-once** in
     `Planet.SetupInteractions`, so writing to it post-load does nothing.
  This is now the standing approach for the many remaining data classes.

- **Folder placement, continuing session #3's "place by what the type is
  for, not by namespace" precedent:**
  - All 7 `SFS.World.Terrain` types → `06-soi-terrain/terrain-chunks.md`.
  - `SFS.World.PlanetModules.*` → `06-soi-terrain/`, split three ways:
    `TerrainModule.md` (terrain geometry + `HeightMap`),
    `Atmosphere_Physics.md` (its own file — it is cross-referenced from
    `Difficulty.md` and the drag/heat chain and deserves a stable target),
    `planet-data-modules.md` (the six field-only modules).
  - The remaining purely-visual `Atmosphere_Visuals` /
    `PostProcessingModule` families are **not** grouped in with
    `planet-data-modules.md` — they belong in `21-platform-rendering/`
    on the same "what it is for" rule, since nothing in them is planet
    physics. This is a call for the next session to execute, not one already
    made in a file.

- **Group files carry an explicit "why grouped" header**, per session #3's
  rule. All three group files here open with one: `terrain-chunks.md`
  ("a single pipeline and none of them is meaningful alone"),
  `TerrainModule.md` ("pure serialized-data holders reachable only as
  `TerrainModule` fields"), `planet-data-modules.md` ("every one is a
  field-only class with no methods but a constructor").

## What worked

### The IL extraction scripts

Both live in the **session scratchpad only** and will be gone next session
— that is why they're reproduced here in full. Nothing was added to
`python/`; these are ad-hoc dev helpers, not project code, and CLAUDE.md's
"don't spawn note files" rule cuts against checking in a second copy of a
throwaway.

**`mem.py` — the one actually used all session.** Members of a type: fields
plus full method signatures, reassembled from monodis's two-line form.
Takes the 1-based IL line number from `inventory.json`.

```python
#!/usr/bin/env python3
"""Members of a type: fields + full method signatures (2-line monodis form).
Stops at the first nested/next `.class` -- see session-3 dead-end note."""
import re, sys
L = open("/Users/christianjin/Documents/VSCode/SFS AI/scratch/full_il.txt", errors="replace").read().split("\n")
start = int(sys.argv[1]) - 1
indent = len(L[start]) - len(L[start].lstrip())
end_pat = re.compile(r"^\s{%d}\} // end of class" % indent)
print(f"{start+1}: {L[start].strip()}")
i = start + 1
while i < len(L):
    l = L[i]
    if end_pat.match(l):
        print(f"[END @{i+1}]"); break
    if re.match(r"^\s*\.class ", l):
        print(f"[STOP nested/next class @{i+1}: {l.strip()[:90]}]"); break
    if re.match(r"^\s*\.field ", l):
        print(f"{i+1}: {l.strip()}")
    elif re.match(r"^\s*\.method ", l):
        sig = l.strip()
        j = i + 1
        while j < len(L) and "cil managed" not in L[j] and "runtime managed" not in L[j]:
            sig += " " + L[j].strip(); j += 1
        if j < len(L): sig += " " + L[j].strip()
        print(f"{i+1}: {sig}")
        i = j
    elif re.match(r"^\s*\.property ", l):
        print(f"{i+1}: {l.strip()}")
    i += 1
```

Usage — `201039` is `TerrainModule`'s `line` field in `inventory.json`:

```bash
python3 /path/to/scratchpad/mem.py 201039
```

**`sig.py` — the fuller variant**, kept because `--body` and name-lookup are
occasionally useful. `mem.py` superseded it for routine work.

```python
#!/usr/bin/env python3
"""Extract a type's IL declaration block from scratch/full_il.txt.

CRITICAL: monodis emits nested classes at the SAME indentation as the
outer class, so an indent-only scan walks past the class boundary and
attributes closure fields to the outer type (see session-3 handoff,
"Dead ends"). We stop at the first `.class` line after the start.

Usage:  sig.py <TypeName> [--line N] [--members] [--body MethodName]
"""
import re, sys, os

IL = "/Users/christianjin/Documents/VSCode/SFS AI/scratch/full_il.txt"
LINES = open(IL, errors="replace").read().split("\n")

def block(start):
    """Lines of the type declared at 0-based `start`, stopping at the
    first subsequent `.class` or the matching `} // end of class`."""
    out = [LINES[start]]
    indent = len(LINES[start]) - len(LINES[start].lstrip())
    end_pat = re.compile(r"^\s{%d}\} // end of class" % indent)
    for i in range(start + 1, min(start + 40000, len(LINES))):
        l = LINES[i]
        if end_pat.match(l):
            out.append(f"[END @{i+1}]")
            break
        if re.match(r"^\s*\.class ", l):
            out.append(f"[STOP: nested/next class @{i+1}: {l.strip()[:90]}]")
            break
        out.append(l)
    return out

def find(name):
    pat = re.compile(r"^\s*\.class .*\b%s\b" % re.escape(name))
    return [i for i, l in enumerate(LINES) if pat.match(l)]

if __name__ == "__main__":
    a = sys.argv[1:]
    name = a[0]
    ln = None
    if "--line" in a: ln = int(a[a.index("--line")+1]) - 1
    starts = [ln] if ln is not None else find(name)
    for s in starts:
        if "--members" in a:
            for j, l in enumerate(block(s)):
                if re.match(r"^\s*(\.class |\.field |\.method |\[)", l) or l.startswith("[END"):
                    print(f"{s+j+1}: {l.strip()}")
        else:
            print(f"=== @{s+1} ===")
            print("\n".join(block(s)))
```

### Reading a method body

`mem.py` gives line numbers; `sed` + `grep` on the range gives a readable
body. The `grep -v` filter is what makes long methods legible — it strips
the stack-shuffling noise:

```bash
sed -n '204923,205095p' scratch/full_il.txt | grep -E "IL_[0-9a-f]{4}:|// end of method" | sed 's/^\s*//' | grep -vE ":  (dup|nop|pop|ldarg\.0|stloc|ldloc)"
```

Drop `stloc|ldloc` when the local-slot traffic actually matters (it does for
anything computing a formula). Keep `// end of method` in the `-E` so
multi-method ranges stay separable.

### The whole-assembly consumer cross-reference

This is the technique that made the data-class files worth writing. For each
IL reference to `<Type>::<field>`, it walks backwards to find the enclosing
method and top-level class:

```bash
cd "/Users/christianjin/Documents/VSCode/SFS AI" && python3 - <<'EOF'
import re
L=open("/Users/christianjin/Documents/VSCode/SFS AI/scratch/full_il.txt",errors="replace").read().split("\n")
for T in ("BasicModule::","OrbitModule::","WaterModule::","RingsModule::","FrontCloudsModule::"):
    print("=====",T)
    seen=set()
    for h,l in enumerate(L):
        if T in l and ".ctor" not in l:
            fld=l.strip().split("::")[-1]
            cls=meth=None
            for j in range(h,-1,-1):
                if meth is None and re.match(r"^\s*\.method ",L[j]):
                    meth=" ".join(x.strip() for x in L[j+1:j+2])[:100]
                if re.match(r"^\s*\.class ",L[j]) and "nested" not in L[j]:
                    cls=L[j].strip().split()[-1]; break
            k=(cls,meth,fld)
            if k in seen: continue
            seen.add(k)
            op = "WRITE" if "stfld" in l else "read"
            print(f"  {fld:32s} {op:5s} {cls}:: {meth}")
EOF
```

The `stfld`-vs-`ldfld` split is the important part — it is what surfaced
that `Difficulty.ScalePlanetData` **writes back into** `BasicModule.radius`,
`.gravity`, `.timewarpHeight`, `Atmosphere_Physics.height`, `.curve`,
`OrbitModule.semiMajorAxis`, `.multiplierSOI`, `RingsModule`'s three
geometry fields and `FrontCloudsModule`'s three. Those live values are
already scaled; applying a difficulty factor to them again double-counts.

### Reading constructor defaults

`paste - -` pairs each `ldc` with the `stfld` that consumes it:

```bash
sed -n '202086,202130p' scratch/full_il.txt | grep -E "ldc\.|stfld|newobj" | sed 's/^\s*IL_[0-9a-f]*:  //;s/SFS.World.PlanetModules.//' | paste - -
```

Watch for raw hex constants — `ldc.r8 (00 00 00 00 00 00 f0 7f)` is
`double.PositiveInfinity` and `(00 00 00 00 00 00 f8 ff)` is `NaN`. monodis
prints ordinary values decimally and these two forms as bytes, so a scan for
`ldc.r8 -?[0-9]` silently misses them. Both turned up in real fields this
session (`DynamicChunk.updateSplit`/`updateMerge`, and
`BasicModule.velocityArrowsHeight`).

### Registering types (unchanged from session #3, still correct)

```bash
echo '[{"fq":"SFS.World.Terrain.Chunk","file":"06-soi-terrain/terrain-chunks.md","summary":"...","status":"CONFIRMED","depth":"FULL"}]' | python3 python/reference_add.py
```

```bash
python3 python/reference_index.py --check
```

`reference_add.py` reruns the index build itself, so a separate
`reference_index.py` call is only needed after editing `manifest.json`
directly. `--check` verifies every manifest `file` exists and every `fq` is
a real type in `inventory.json`; silent success = pass. It passed after all
three checkpoints.

Nested types are registered by their **inventory `fq` with a slash** —
`SFS.World.Terrain.Chunk/TerrainPoints`, not `.TerrainPoints`. Getting this
wrong is caught by `--check`.

## What landed, file by file

**`06-soi-terrain/terrain-chunks.md`** — 670 lines, all 7
`SFS.World.Terrain` types, grouped because they are one pipeline and none is
meaningful alone.

| Type | Status | Depth |
|---|---|---|
| `TerrainColliderModule` | CONFIRMED | FULL |
| `TerrainColliderManager` | CONFIRMED | FULL |
| `TerrainColliderManager/Chunk` | CONFIRMED | FULL |
| `DynamicTerrain` | CONFIRMED | FULL |
| `DynamicTerrain/DynamicChunk` | CONFIRMED | FULL |
| `Chunk` | PARTIAL | FULL |
| `Chunk/TerrainPoints` | CONFIRMED | FULL |

The headline finding, stated as a blockquote at the top of the file: **the
terrain you see and the terrain you collide with are two independent
systems.** `DynamicTerrain` is a binary-split visual LOD tree;
`TerrainColliderManager` builds the `PolygonCollider2D` from a flat integer
chunk index derived from the craft's angle around the planet. They share no
geometry and no chunk indexing — only the common call into
`TerrainModule.GetTerrainPoints`. Neither is a terrain-height oracle; use
`Location.GetTerrainHeight` → `Planet.GetTerrainHeightAtAngle`.

Other things worth carrying forward from it:
- Collider updates are driven by `player.location.position.OnChange`, **not**
  by `Update`/`FixedUpdate`. A craft whose `location.position` isn't being
  written gets no collider refresh.
- `TerrainColliderManager.chunks` is keyed by a bare `int` with **no planet
  identity**, while `AddChunks` takes the planet from the *owner*. Two craft
  on different planets requesting the same index share one chunk's geometry.
  Read from IL, **not reproduced live** — marked PARTIAL.
- `UpdateChunks` uses a `(int)(x + 100.0) - 100` floor idiom that is only
  valid while `|index| < 100`.
- `DynamicTerrain.LoadFully()` loops 500 times with **no early exit**, unlike
  `Update()` which caps at 20 and returns as soon as nothing applies.
- `distanceMoved` accumulates **path length**, not displacement — moving away
  and back does not restore prior LOD thresholds.
- `CalculateBest()` seeds both scans from `activeChunks[0]` and would throw
  on an empty list; the merge seed also skips the `CanMerge()` filter.
- `DynamicChunk`'s constructor **registers and enables itself** — it is not a
  pure allocation.

**`06-soi-terrain/TerrainModule.md`** — 401 lines. `TerrainModule` (CONFIRMED
/FULL), `TerrainTexture` (CONFIRMED/LIGHT), `FlatZone` (PARTIAL/FULL),
`RockData` (CONFIRMED/LIGHT), `HeightMap` (CONFIRMED/FULL).

Confirmed formulas, all read from IL:
- `GetVerticeSize(LOD, LOD_Max) = Math.Pow(2.55, LOD_Max - LOD) * verticeSize`
- `GetLoadDistance(LOD, LOD_Max) = Math.Pow(2.05, LOD_Max - LOD) * 250.0`
  — `2.05` and `250.0` are inlined literals, not fields; not tunable per planet
- `GetChunkSize_Angular(baseChunkCount, LOD) = 1.0 / ((int)Math.Pow(2, LOD) * baseChunkCount)`
- `Chunk.GetAngleBetweenPoints(size, pointCount) = size * π * 2.0 / (pointCount - 1)`
- `TerrainColliderManager.GetAngularChunkSize` couples the *collider* grid to
  the *visual* system's base chunk count and max LOD

`GetTerrainPoints` is written out in full pseudo-C#. Slot 0 of its output is
**not a terrain vertex** — for a visual chunk it is the planet centre (which
is what `Chunk.GetIndices`' `0, i+2, i+1` triangle fan needs); for a collider
chunk, slot 0 and the last slot are a skirt dropped 1000 m below the terrain,
clamped by `Math.Max(1.0, …)`.

`HeightMap` has three real traps: **`Evaluate` wraps rather than clamps**
(`Evaluate(1f)` returns `points[0]`, and a negative argument throws);
**`EvaluateDoubleOut` is not double-precision** (only the argument and return
type are `double`, the lerp runs in `float32`); and **`EvaluateClamped`
returns `points[^1]` for `NaN`** because the comparisons are the unordered
forms. The `Texture2D` constructor reads the **alpha** channel and **reverses
the columns**.

**`06-soi-terrain/Atmosphere_Physics.md`** — the nine physics constants, all
defaults confirmed, plus a complete assembly-wide consumer table. `height`
and `curve` are difficulty-mutated in place; `density` is not.
`upperAtmosphere` has exactly one consumer and it is `StatsRecorder`, i.e.
statistics, not physics. `shockwaveIntensity` and
`minHeatingVelocityMultiplier` are `float32` while everything else on the
class is `float64`.

**`06-soi-terrain/planet-data-modules.md`** — `BasicModule` (FULL),
`OrbitModule` (FULL), `WaterModule` (FULL), `WaterModule/WaterMask` (LIGHT),
`RingsModule` (LIGHT), `FrontCloudsModule` (LIGHT). Per-field consumer maps
for all six. `WaterModule` has 22 fields of which **exactly three** affect
simulation (`lowerTerrain`, `oceanDepth`, `wavesSize`); the other nineteen
are marked LIGHT within a FULL-depth entry, which the template supports and
which is the honest description.

## Dead ends

- **`sig.py`'s indent-based extraction, re-confirmed broken.** Session #3
  recorded it; it reproduced immediately here. In monodis output nested
  classes sit at the **same indentation** as the outer class, so a scan that
  only stops at the matching-indent `} // end of class` walks straight into
  the closure types and reports their fields as the outer type's. Both
  scripts above carry the fix — stop at the **first `.class` line after the
  start**, whatever its indentation. Every field list in this session's four
  files was produced with that stop condition in place. **A field list
  produced without it is suspect.**

- **`grep -E "ldc\.r8 -?[0-9]"` misses the two constants that matter.**
  monodis prints `double.PositiveInfinity` and `NaN` as raw byte tuples
  (`(00 00 00 00 00 00 f0 7f)` and `(00 00 00 00 00 00 f8 ff)`), not
  decimally. Grep for `ldc\.` unqualified and read the tuples.

- **`awk`-based enclosing-method lookup for the cross-reference was a false
  start** — an `awk` one-liner tracking the last `.method` before a hit
  produced empty output because the method *name* is on the line **after**
  `.method`. The Python version above reads `L[j+1:j+2]` for exactly that
  reason. Not worth retrying in `awk`.

## Open

- **Phase 1 Step 2 — 823 types remaining** (936 in scope − 113 done).
  Folders `15-ui`, `16-builds`, `17-modgui`, `18-maps-navigation`,
  `19-career-progression`, `20-localization-audio`, `21-platform-rendering`
  are still entirely empty. Checkpoint every 3–4 classes; hand off every
  15–20; **commit before each hand-off**.

- **`SFS.World.TerrainSampler` is the highest-value next target.** Three of
  the four files written this session list it as their top [OPEN]: it holds
  `Compiler`, `Executor`, `GetTerrainSamples` and `GetTextureSamples`, it is
  the actual terrain evaluator, and the semantics of `FlatZone.angle` /
  `width` / `transition` are decided entirely inside it.

- **`SFS.WorldBase.PlanetData` (`@150017`, 20 fields) should be documented
  before or alongside the rest of `PlanetModules`.** `planet-data-modules.md`
  asserts the field names that expose the six modules (`basic`, `orbit`,
  `water`, `rings`, `frontClouds`) **from usage, not from `PlanetData`
  itself** — that is flagged [OPEN] in the file and is a real loose end.

- **`Planet.GetMaxLOD()` and `Planet.GetVerticeCount(double, double)`** are
  referenced throughout `TerrainModule.md` and `terrain-chunks.md` but their
  bodies were not read. They belong to `06-soi-terrain/Planet.md`, which
  exists from the migration — check whether it already covers them before
  re-deriving.

- **Not read, deliberately, and flagged in-file:** `Chunk..ctor` and
  `Chunk.CreateMesh` (~590 lines of Unity mesh construction, no simulation
  logic identified), `DynamicChunk.GenerateRocks` (`@202816`, ~330 lines,
  cosmetic scatter), and `DynamicChunk.SetLayer`'s water branch past the
  `hasWater` test.

- **Whether `Difficulty.ScalePlanetData` is idempotent** — i.e. whether
  calling it twice scales `height`/`curve`/`radius`/`gravity` twice — is not
  established. It matters to any mod that reloads planet data, and it is now
  flagged in two files.

- **`docs/sfs_reference/INVENTORY.md` and `docs/sfs_reference_plan.md` still
  say "~26 excluded".** Corrected in `manifest.json` and `CORRECTIONS.md`
  only. If a future session finds this confusing rather than useful, fixing
  the two source files is a five-minute job — but the project's convention
  is to correct via `CORRECTIONS.md` rather than silently overwrite, so this
  was left as-is on purpose.

- **The IL extraction scripts live only in the session scratchpad** and are
  reproduced in full above. If Step 2 keeps using them at this rate,
  promoting `mem.py` into `python/` (with a `python_changelog.md` entry)
  would be reasonable — but it is project tooling, not a decision to make
  unilaterally.

- **Phase 1 Step 3 — retire `docs/sfs_source_reference.md`.** Not yet.
  Requires grepping the whole project and repointing
  `docs/startup_prompt.md`, `README.md`, `CLAUDE.md`, `mod_changelog.md`,
  and `python_changelog.md` at `docs/sfs_reference/INDEX.md`. Session #3's
  diff-check script (in that handoff, under "What worked") should be re-run
  against whatever is left of the old file at the end of Step 2.

- **`scratch/full_il.txt` must never be committed** (13.3 MB of decompiled
  copyrighted game code, gitignored). md5 `dcf3f2dbfd670f9666d2de2fb6a5f2f0`;
  the assembly's is `cbad19d24f73252e5a7acd6b88cfa9c1`. Both are recorded in
  `manifest.json` so a future session can tell whether its dump matches what
  the reference was written against.

## Added after writing — the template changed underneath this session

A **concurrent session** edited `docs/sfs_reference_plan.md` while this
work was in progress (the edit is still uncommitted in the working tree as
of this handoff, alongside commits `1f8542d`, `5a3645f`, `c28e4a9` from that
same line of work on the blueprint loader). Two changes matter to Step 2:

1. **The per-class template gained a required `Preconditions` field** on
   every FULL-depth method — what must already be true before the call
   (required scene, a live singleton that must be non-null, initialization
   or ordering requirements). If nothing is required, the field must still
   be present, reading "None beyond valid arguments", because an absent
   field is indistinguishable from "not checked yet". The stated motivation
   is that this would have caught the `loadblueprint` `World_PC`/`Build_PC`
   mixup before any mod code was written.

2. **A hard rule:** a method whose body is marked `[OPEN]` must not be
   wired into a live `SFSProbe.cs` command if that command mutates game
   state.

**Consequence for this session's output: the four files written today
predate change (1) and do not carry `Preconditions` fields.** They are
otherwise template-conformant. Back-filling them is a bounded job — the
FULL-depth methods needing it are in `terrain-chunks.md` (about 25 methods)
and `TerrainModule.md` (7), and the preconditions are mostly already stated
as prose under **Gotchas** (`TerrainColliderManager.main` must be populated;
`SetupSamplers` must have run before `GetTerrainPoints`; `SetupSamplers`
itself needs a loaded world for `Base.worldBase.settings.difficulty`;
`CalculateBest` requires a non-empty `activeChunks`). **A future session
should back-fill these before writing more Step 2 files**, so the corpus
doesn't split into pre- and post-rule halves.

Nothing in this session's files is *wrong* under the new template — only
incomplete against it.
