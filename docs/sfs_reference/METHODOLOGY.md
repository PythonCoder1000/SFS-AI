# Methodology and provenance

How every claim in this reference was produced, and how to re-verify any
of it yourself. Migrated from `docs/sfs_source_reference.md` §Provenance,
§Status tags and §A2 during Phase 1 Step 1 (2026-08-28), content
unchanged.

**This is not a per-class file** and so does not follow the per-class
template — it is tooling and provenance, which has no class to attach to.
Companions: [`REFLECTION_TOOLKIT.md`](REFLECTION_TOOLKIT.md) (live
reflection recipes), [`CORRECTIONS.md`](CORRECTIONS.md) (the running
correction ledger), [`INDEX.md`](INDEX.md) (the per-class reference).

---

## Provenance — what "verified" means in this file

| | |
|---|---|
| Game | Spaceflight Simulator **1.6.00.16** (Steam, macOS) |
| Assembly | `Assembly-CSharp.dll`, md5 `cbad19d24f73252e5a7acd6b88cfa9c1` |
| Disassembler | `monodis`, Mono 6.14.1 |
| IL dump | `scratch/full_il.txt` — 13,324,890 bytes, md5 `dcf3f2dbfd670f9666d2de2fb6a5f2f0` |
| `.class` declarations | 1,509 |
| Real types (compiler-generated removed) | 969 — 738 top-level, 231 nested |

**CORRECTION (2026-08-28).** This table previously read "Top-level types |
1,509". That was wrong on two counts: 1,509 counts every `.class`
declaration in the dump, which includes nested types *and* 540
compiler-generated ones (closures, `<>c__DisplayClass*`, iterator state
machines, `<PrivateImplementationDetails>`). The real figure is 969 types,
of which 738 are top-level. Full per-namespace inventory:
`docs/sfs_reference/INVENTORY.md`.

The IL dump was re-generated from the pinned DLL at the start of this
work and came back **byte-identical** to the existing `scratch/full_il.txt`,
so that dump is current and every line reference below indexes into it.

**The assembly's own version field is useless for pinning.** `monodis
--assembly` reports `Version: 0.0.0.0` — Unity never stamps it. The md5
above is the only real identity check. If it stops matching, every line
number in this file is stale and every value in
`sfs_physics_reference.md` is suspect.

## Status tags

Applied **per item**, not per class. A section header carrying
"Confirmed" does not mean every field under it is confirmed.

- **[CONFIRMED]** — read directly from IL, including the method *body*
  where behavior (not just shape) is claimed.
- **[PARTIAL]** — shape confirmed from IL, behavior not traced; or some
  members read and others not.

## A2. Methodology — how to verify anything in this file yourself

**[CONFIRMED]** — this section is about the tooling, and every claim in
it was exercised producing the rest of the document.

Read this before adding to the file. The single most valuable finding
this project has made (§C1, the `dragArea` path) came from reading a
method *body* after an earlier pass had already read its *signature* and
concluded nothing useful was there. The discipline below is what
separates those two outcomes.

### Regenerating the dump

```bash
DLL=~/Library/Application\ Support/Steam/steamapps/common/Spaceflight\ Simulator/SpaceflightSimulatorGame.app/Contents/Resources/Data/Managed/Assembly-CSharp.dll
md5 -q "$DLL"     # must be cbad19d24f73252e5a7acd6b88cfa9c1
monodis --output=scratch/full_il.txt "$DLL"
```

`scratch/` is gitignored — the dump is decompiled copyrighted game code
and must never be committed.

### `monodis` output format — the two gotchas

**Gotcha 1: a method declaration spans two lines.** The `.method` line
carries only the attributes; the actual return type, name, and parameter
list are on the *next* line, beginning with `default`. This is why a
naive `grep '\.method'` returns a wall of `hidebysig instance` with no
names attached, and why an earlier pass could plausibly have concluded a
class was empty.

```
    .method private static hidebysig
           default valuetype ...ValueTuple`2<float32, ...Vector2> CalculateDragForce (...List`1<...Surface> surfaces)  cil managed
```

**Gotcha 2: nesting is expressed purely by indentation.** Top-level
classes are at two spaces (`  .class`), nested types deeper. The
namespace is a separate `.namespace` block above, so a type's real full
name is `<namespace>.<class>` and nested types append with `/`. Getting
this wrong means `FindType()` silently returns `null` rather than
throwing — see §A1.

### The extractor

Reconstructs real signatures from the split format. Kept in the session
scratchpad rather than the repo; reproduced here so it survives.

```bash
#!/bin/bash
# sig.sh <ClassName> -- fields + flattened method signatures for a top-level class
IL="scratch/full_il.txt"
start=$(grep -n "^  \.class .*[ .]$1$" "$IL" | head -1 | cut -d: -f1)
if [ -z "$start" ]; then echo "NOT FOUND: $1"; exit 1; fi
awk -v s="$start" '
NR<s {next}
{ lines[NR]=$0 }
NR>s && (/^  \} \/\/ end of class/ || /^  \.class .*nested/) { end=NR; stop=$0; exit }
END {
  for(i=s;i<=end;i++){
    l=lines[i]
    if (l ~ /^  \.class/ && i==s) { print "CLASS@"i": " l }
    else if (l ~ /^    \.field/)  { print "  FIELD: " l }
    else if (l ~ /^    \.method/) {
      sig=lines[i]
      for(j=i+1;j<=i+4;j++){ sig=sig" "lines[j]; if(lines[j] ~ /\)/) break }
      gsub(/[ \t]+/," ",sig)
      print "  METHOD@"i": " sig
    }
  }
  if (stop ~ /nested/) print "  [truncated at first nested type @"end" -- nested members NOT shown]"
}' "$IL"
```

**The `.class .*nested` stop is not optional — it is a correctness fix.**
Without it the extractor walks past the outer type's closing brace into
the compiler-generated `<>c__DisplayClassN_M` types that C# emits for
closures and local functions, and attributes *their* fields to the outer
class. This produced a real false positive during this work: both
`AeroModule` and `Aero_Rocket` appeared to have a
`public List<Surface> output` field. They do not. `output` is a captured
local on `AeroModule/<>c__DisplayClass16_0` and
`Aero_Rocket/<>c__DisplayClass5_0`. Anything named `<>c`,
`<>c__DisplayClassN_M`, or `<Method>d__N` is compiler scaffolding, not
API — and `<Method>g__Name|N_M` is a local function, reachable but never
part of the contract.

The pattern must be `.*nested`, not a literal `.class nested`. Closure
types render as `.class nested private auto ansi sealed beforefieldinit
'<>c__DisplayClass16_0'`, but **nested interfaces put the kind first** —
`.class interface nested public auto ansi abstract INJ_Rocket` — so an
anchored `^  \.class nested` sails straight past them. This cost a second
false positive: `Rocket` appeared to declare
`public abstract void set_Rocket(Rocket)`, an abstract method on a
concrete class, which is impossible. It belongs to the nested interface
`Rocket/INJ_Rocket`. **An `abstract` member showing up on a concrete
class is the tell that the extractor has overrun.**

`METHOD@<line>` gives the line number to `sed -n` into for the body.

### Reading a body

```bash
sed -n '216053,216152p' scratch/full_il.txt      # decl through "end of method"
```

Three things in a body carry information a signature never does:

1. **`.custom` attribute blobs**, dumped as raw hex with an ASCII
   comment column. This is how `CalculateDragForce`'s tuple element
   names were recovered — the compiler stored `drag` and `centerOfDrag`
   in a `TupleElementNamesAttribute`, and `monodis` renders them
   legibly in the comment:

   ```
   .custom instance void ...TupleElementNamesAttribute::'.ctor'(string[]) =  (
       01 00 02 00 00 00 04 64 72 61 67 0C 63 65 6E 74   // .......drag.cent
       65 72 4F 66 44 72 61 67 00 00                   ) // erOfDrag..
   ```

   A signature says the method returns `ValueTuple<float, Vector2>`. The
   body says which is which. That difference is the whole §C1 finding.

2. **The arithmetic itself**, which can be matched against a candidate
   formula. §C1's `dragArea` claim rests on tracing the accumulation
   `weight = dx/(dx+|dy|)`, `drag += dx*weight` and matching it to the
   documented `Σ dx²/(dx+|dy|)` — an exact match, not a resemblance.

3. **Real call sites**, which reveal what callers actually pass. The
   rotation-matrix correction in §C1 came from reading
   `AeroModule.FixedUpdate()`'s body to see what it fed
   `GetDragSurfaces`, rather than assuming identity.

### Finding call sites

Call instructions name the full method, so the same grep finds both the
declaration and everyone who calls it:

```bash
grep -n "CalculateDragForce" scratch/full_il.txt
# 215966:  IL_0001:  call ...AeroModule::CalculateDragForce(...)   <- a CALLER
# 216055:  default ...CalculateDragForce (...)                      <- the DECLARATION
# 216152:  } // end of method AeroModule::CalculateDragForce        <- the end
```

Lines with `IL_xxxx:  call` are callers. Use them; a method with exactly
one caller tells you its real contract far faster than its signature does.

### The rule

> A method name tells you what it is called, not what it does.

Do not write a behavioral claim into this file from a signature alone.
If only the signature was read, the item is **[PARTIAL]**, and saying so
is the point — a section that reads as finished when half of it is
unverified is worse than one that admits the gap.
