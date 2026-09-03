# SFS Source Code Reference

The complete, IL-verified code dictionary for Spaceflight Simulator's
internals, as they exist in this project's pinned build. **This is the
single canonical source-code reference for the project.** It absorbed
and replaced the earlier, much shorter file of the same name on
2026-08-27; there is no separate `sfs_full_reference.md`. Companion
document: `sfs_physics_reference.md` (what is physically true, confirmed
vs. open). If anything here conflicts with a wiki or a community mod's
assumptions, this file wins — it is read from the actual compiled code.

**Every claim in this file traces to real IL.** Nothing here is inferred
from a method name, copied from a wiki, or carried over from a community
mod's assumptions. Where something could not be verified it is marked
**OPEN** rather than filled in with plausible-sounding invention — this
project has been burned specifically and repeatedly by plausible-sounding
invention (see `sfs_physics_reference.md` §1.2 for the receipts).

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
- **[OPEN]** — not yet read. Named here so the gap is visible rather
  than invisible.
- **[UNTESTED-LIVE]** — IL-confirmed but never executed against the
  running game. Distinct from CONFIRMED: the IL says what the code does,
  not that our reflection path successfully reaches it.

## Corrections to earlier documents

Collected here so regressions are visible rather than silently
overwritten. Each is expanded in its own section.

| Claim in an earlier doc | Correction | Section |
|---|---|---|
| `Part.InitializePart(bool)` | Takes **zero arguments** | §B3 |
| `GetDragSurfaces` reachable by plain name lookup | Two overloads, throws `AmbiguousMatchException` | §C1.2 |
| Rotation matrix into `GetDragSurfaces` is identity | Derived from velocity angle; there are **two** matrices | §C1.1 |
| SFS's mod loader pre-loads Harmony/MonoMod, so bundling a newer one cannot work | `Assembly-CSharp.dll` has **zero** Harmony/MonoMod references; nothing in `Managed/` loads them. The real mechanism is assembly-name resolution against the app base | §A4.2 |
| `AeroModule` is the "per-part-module level" of drag | `AeroModule` is an **abstract base class**; `GetDragSurfaces` on it is `protected abstract` with no body | §C1.0 |
| `AeroModule` / `Aero_Rocket` have a `public List<Surface> output` field | Neither does — it is a nested closure field, an extractor artifact | §C1.0, §A2 |
| "No Python-side evaluator exists" for parametric part values | The game ships a full expression compiler (`Compute`), and `.Value` already evaluates it — live reads were always correct | §E4 |
| Heat/destruction has "no formula read from code" | Whole chain read; default part breaks at **412 °C**, explaining the 410.8 °C data point | §D1 |
| Fuel flow is `thrust · throttle / (ISP · ispMultiplier)` | Also multiplied by a `scale` term — the world-transformed `thrustNormal` magnitude. Only 1.0 for unscaled parts | §D2.3 |
| Earth atmosphere `ρ0 = 0.005`, `curve = 10`, height 30,000 m stated unconditionally | `Atmosphere_Physics` scales curve **and** height by difficulty; the values hold only for the difficulty they were measured on | §D1.5 |
| Multi-engine thrust needs a summation model | No summation exists — each engine calls `AddForceAtPosition` independently | §D2.0 |
| RCS responds proportionally to steering input | Torque thrusters fire only at `\|TurnAxis\| ≥ 0.95` **or** `\|angularVelocity\| ≥ 2` | §D3.2 |
| `maxTerrainHeight` is "not real terrain geometry" | Per-angle terrain **is** queryable — `Location.GetTerrainHeight(bool)` → `Planet.GetTerrainHeightAtAngle`. `maxTerrainHeight` is only a fast-reject bound | §D4.4, §B2.1 |
| `Rocket.floating` reads as "off the ground" | It means **in water** — both call sites confirm (water timewarp message; 10% rotation damping) | §B1.1 |
| Walking `Part.modules` enumerates a part's modules | It is a **lazy memo of queries already made**, keyed by short type name, never cleared. Enumerating it under-reports | §B3.2 |
| `sig.sh` stop pattern `^  \.class nested` | Misses nested **interfaces** (`.class interface nested`), which put the kind first — a second extractor overrun | §A2 |
| Control input is validated by the model | The `hasControl` and timewarp gates live in **`ArrowkeysDrawer` (UI)**. Writing `Arrowkeys` directly bypasses both, and `turnAxis` is unclamped on the manual branch | §E2.3 |
| `WorldTime.FixedDeltaTime` ≈ `Time.fixedDeltaTime` | They diverge under warp, in opposite directions: rails scales `FixedDeltaTime`, physics timewarp scales `Time.timeScale` | §E5.1 |
| Infinite fuel refills tanks | It **skips consumption entirely**, so mass never drops — the vehicle flies differently, not just longer | §E1.3 |
| `AeroFormula` coefficients have no known location | They live on `GameManager.main.aeroData`; the *values* remain live-only | §E5.3, §D1 |
| Parachute drag is part of the ordinary drag sum | It is a separate rotation-aware path using per-chute `rb2d.GetPointVelocity` and an `AnimationCurve`, and it bypasses the 0.2 damping | §E6.1, §C1 |

Two places this document **confirms** rather than corrects an earlier
claim, from the code side where the earlier work was empirical:
`sfs_physics_reference.md` §2.4 (the rotation formula, including the
`(mass/200)^0.35` divisor — §B1.3) and §2.1 (`Planet.mass` is μ —
§B5.3). Neither needed changing.

---

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

---

## A1. Reflection toolkit

**[CONFIRMED]** — read from `sfsprobe/SFSProbe.cs` v0.26.0 as shipped;
every helper below is in live use.

The whole probe reaches the game through nine helpers. Consolidated here
because the rest of this file assumes them by name.
`sfs_source_reference.md` documented six and omitted `Unwrap`,
`SetWrapped`, and `ActiveRocket` — `Unwrap` in particular is **not**
interchangeable with `GetWrapped2`, and confusing the two produces
silently wrong reads. See the comparison below.

### `FindType(string full)` — resolve a type by name

```csharp
static Type FindType(string full)
{
    foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
    {
        Type t = null;
        try { t = a.GetType(full, false); } catch { }
        if (t != null) return t;
    }
    return null;
}
```

Searches every loaded assembly. Requires the **exact**
namespace-qualified name.

**Failure mode: returns `null`, never throws.** A typo, a missing
namespace, or a wrong nesting separator is indistinguishable from "the
type isn't loaded yet". Always null-check and log which name failed;
several hours have been lost in this project to a silent `null` that
read as "the feature doesn't exist".

Naming traps confirmed in this assembly:

| Type | Correct name for `FindType` |
|---|---|
| `Part` | `SFS.Parts.Part` |
| `AeroModule` | `SFS.World.Drag.AeroModule` |
| `Matrix2x2` | `Matrix2x2` — **top-level, no namespace at all** |
| `Double2` | `Double2` — **also top-level, no namespace** |
| Nested types | `Outer/Nested`, slash not dot |

### `FindComponent(string typeName)` — reach a live instance

```csharp
static object FindComponent(string typeName)
{
    Type t = FindType(typeName);
    UnityEngine.Object[] f = Resources.FindObjectsOfTypeAll(t);
    return (f == null || f.Length == 0) ? null : f[0];
}
```

`Resources.FindObjectsOfTypeAll` rather than chasing a singleton
reference chain — more robust across scene loads. Used for
`SFS.World.GameManager`, `SFS.World.PlayerController`,
`SFS.WorldBase.PlanetLoader`, `SFS.Parts.PartsLoader`.

**Caveat:** it returns *all* objects of the type including inactive ones
and, in the editor-adjacent scenes, prefab assets. `f[0]` is a guess
that has held so far for the manager singletons; it is **[PARTIAL]** for
any type with more than one live instance.

### `Get(object o, string member)` — read a field or property

```csharp
internal static object Get(object o, string member)
{
    Type t = o as Type ?? o.GetType();
    object target = (o is Type) ? null : o;
    var flags = BindingFlags.Public | BindingFlags.NonPublic |
                (target == null ? BindingFlags.Static : BindingFlags.Instance);
    var f = t.GetField(member, flags);
    if (f != null) return f.GetValue(target);
    var p = t.GetProperty(member, flags);
    if (p != null) { try { return p.GetValue(target, null); } catch { return null; } }
    return null;
}
```

Fields first, then properties; public and non-public both. Pass a `Type`
instead of an instance to read a **static** member —
`Get(FindType("SFS.Base"), "worldBase")`.

Because it checks properties too, computed values work transparently:
`Get(velocity, "AngleRadians")` on a `Double2` returns the computed
angle, not null. This is load-bearing for §C1.

### `GetWrapped2(object w)` — unwrap exactly one layer

```csharp
static object GetWrapped(object owner, string member) { return GetWrapped2(Get(owner, member)); }
static object GetWrapped2(object w)
{
    if (w == null) return null;
    Type t = w.GetType();
    var p = t.GetProperty("Value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
    if (p != null) { try { return p.GetValue(w, null); } catch { } }
    var f = t.GetField("value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
    if (f != null) { try { return f.GetValue(w); } catch { } }
    return w;
}
```

SFS wraps many simple values (`throttlePercent`, `engineOn`) in
observable wrapper types; plain `Get()` returns the wrapper. Tries
`.Value` property, falls back to `.value` field, returns the input
unchanged if neither exists. See §A3 for which wrapper types exist.

### `Unwrap(object o)` — unwrap *repeatedly*, with type stops

```csharp
static object Unwrap(object o)
{
    for (int i = 0; i < 6 && o != null; i++)
    {
        Type t = o.GetType();
        if (t.Name.Contains("Rocket") || t.Name == "Location" || t.Name == "Planet") return o;
        var p = t.GetProperty("Value", ...Instance);
        var f = t.GetField("value", ...Instance);
        object next = null;
        if (p != null) { try { next = p.GetValue(o, null); } catch { } }
        if (next == null && f != null) { try { next = f.GetValue(o); } catch { } }
        if (next == null || ReferenceEquals(next, o)) return o;
        o = next;
    }
    return o;
}
```

**Not a synonym for `GetWrapped2`.** Three real differences:

1. **It loops** up to 6 times, peeling nested wrappers
   (`Reference<Reference<T>>` chains do occur).
2. **It stops early on target types** — anything whose type name
   *contains* `"Rocket"`, or is exactly `Location` or `Planet`, is
   returned as-is rather than unwrapped further. Without this guard the
   loop would descend into a `Rocket`'s own `Value`-named member and
   return something else entirely.
3. **It is heuristic.** The `Contains("Rocket")` test is a substring
   match on a type *name*, exactly the kind of name-based inference this
   document otherwise forbids. It works today; it is **[PARTIAL]** and
   would break on any new type whose name happens to contain "Rocket".

Rule of thumb: `GetWrapped2` for a known single-wrapped scalar,
`Unwrap` for an object reference of uncertain wrapping depth.

### `SetWrapped(object owner, string member, object val)` — write

```csharp
static bool SetWrapped(object owner, string member, object val)
{
    object w = Get(owner, member);
    if (w == null) return false;
    Type t = w.GetType();
    var p = t.GetProperty("Value", ...Instance);
    if (p != null && p.CanWrite)
        { try { p.SetValue(w, Convert.ChangeType(val, p.PropertyType), null); return true; } catch { } }
    var f = t.GetField("value", ...Instance);
    if (f != null)
        { try { f.SetValue(w, Convert.ChangeType(val, f.FieldType)); return true; } catch { } }
    return false;
}
```

Mirror of `GetWrapped2`, with `Convert.ChangeType` to coerce the caller's
value. Returns `bool` — **check it**; every failure path returns `false`
silently rather than throwing. This is how `throttle` and `master` write
control state.

### `Invoke` / `InvokeReturn` — call a method

```csharp
static object InvokeReturn(object o, string method, object[] args)
{
    Type t = o as Type ?? o.GetType();
    object target = (o is Type) ? null : o;
    var m = t.GetMethod(method, BindingFlags.Public | BindingFlags.NonPublic |
            (target == null ? BindingFlags.Static : BindingFlags.Instance));
    if (m == null) return null;
    try { return m.Invoke(target, args); } catch { return null; }
}
```

**Throws `AmbiguousMatchException` on any overloaded method** — caught by
the `try` and returned as `null`, so an ambiguity is indistinguishable
from "no such method". Every confirmed ambiguous case in this assembly
is catalogued in §A1.1 below.

For those, resolve the overload explicitly:

```csharp
static object InvokeStatic(Type t, string method, Type[] paramTypes, object[] args)
{
    try
    {
        MethodInfo m = t.GetMethod(method,
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static,
            null, paramTypes, null);
        if (m == null) return null;
        return m.Invoke(null, args);
    }
    catch (Exception e)
    {
        ProbeMod.Log("InvokeStatic " + method + " failed: " +
            (e.InnerException != null ? e.InnerException.Message : e.Message));
        return null;
    }
}
```

Note it **logs** rather than swallowing. `InvokeReturn`'s bare
`catch { return null; }` is a real liability for anything new — prefer
the logging form.

### `ModuleValues(object part)` — walk `Part.modules` correctly

```csharp
internal static IEnumerable<object> ModuleValues(object part)
{
    var mf = part.GetType().GetField("modules", BindingFlags.NonPublic | BindingFlags.Instance);
    object modules = mf != null ? mf.GetValue(part) : null;
    var men = modules as System.Collections.IEnumerable;
    if (men == null) yield break;
    var seen = new HashSet<object>(ReferenceEqualityComparer.Instance);
    foreach (object kv in men)
    {
        object mv = Get(kv, "Value");
        if (mv == null) continue;
        if (mv.GetType().IsArray)
        {
            foreach (object el in (System.Collections.IEnumerable)mv)
                if (el != null && seen.Add(el)) yield return el;
        }
        else if (seen.Add(mv)) yield return mv;
    }
}
```

`Part.modules` is a **`Dictionary<string, object>`** — see the
correction below — with two traps, both confirmed the hard way:

1. **Values are arrays**, not bare modules — `EngineModule[]`, not
   `EngineModule`. In practice usually single-element.
2. **The same physical module appears under multiple keys**, so
   deduping must be by **reference identity**, not by key.

Walking it naively counted one real engine **six times**.

**Correction to the earlier `sfs_source_reference.md`**, which described
this as `Dictionary<Type, object>` keyed by "every interface and base
class". The IL (§B3.2, `Part::modules` @236536) shows the key type is
**`string`**, and the key is `typeof(T).Name` — the *short* type name of
whatever `T` a caller passed to `GetModules<T>()`. The two descriptions
agree on behaviour and differ on mechanism: because `T` may be an
interface or a base class and `GetComponentsInChildren<T>` resolves
those, one instance genuinely does land under several keys — but they
are *name strings for types that were queried*, not a complete type
index. The practical consequence is the one §B3.2 spells out:
**enumerating this dictionary under-reports**, because a type nobody has
asked for has no key at all. `ModuleValues` remains correct for what it
does; it is just not a complete inventory. Prefer calling
`PartHolder.GetModules<T>()` (§B4.4).

### `ActiveRocket()` — the rocket the player is flying

```csharp
static object ActiveRocket()
{
    object r = Unwrap(Get(FindComponent("SFS.World.PlayerController"), "player"));
    if (r != null && r.GetType().Name.Contains("Rocket")) return r;
    var list = Get(FindComponent("SFS.World.GameManager"), "rockets") as System.Collections.IEnumerable;
    if (list != null) foreach (object o in list) { object u = Unwrap(o); if (u != null) return u; }
    return null;
}
```

`PlayerController.player` first, falling back to the first entry of
`GameManager.rockets`.

**The fallback is not equivalent to the primary path.** `player` can
legitimately be an `Astronaut_EVA` rather than a `Rocket` (hence the
name test), and on the fallback path "first rocket in the list" is not
necessarily the controlled one. **[PARTIAL]** — adequate for
single-rocket flights, unvalidated with multiple rockets in scene.

### A1.1 Ambiguous-overload catalogue

Methods where plain `GetMethod(name, flags)` throws
`AmbiguousMatchException` and the explicit-parameter-types form is
mandatory. **[CONFIRMED]** for the entries listed; the catalogue itself
is **[PARTIAL]** — it grows as classes are read, and only classes read
so far are represented.

| Class | Method | Overloads (disambiguating parameter types) |
|---|---|---|
| `SFS.World.Drag.Aero_Rocket` | `GetDragSurfaces` | `protected` instance `(Matrix2x2)` · `public static` `(PartHolder, Matrix2x2)` |
| `SFS.Parts.Modules.SurfaceData` | `SetData` | `(List<Surfaces>)` · `(List<Surfaces>, List<Surfaces>)` — both `protected` |
| `Line2` | `Lerp` | `(float)` · `(float, float)` |
| `Line2` | `LerpUnclamped` | `(float)` · `(float, float)` |
| `Line2` | `GetSlope` | instance `()` · static `(Vector2, Vector2)` |
| `SFS.Parsers.Constructed.Compute` | `Compile` | public `(string, VariablesModule, out List<string>)` · private `(ref int, ref string, VariablesModule, out List<string>)` |
| `SFS.WorldBase.Planet` | `GetGravity` | `(double radius)` · `(Double2 position)` |
| `Matrix2x2` | `op_Multiply` | `(Matrix2x2, Vector2)` · `(Vector2, Matrix2x2)` · `(Matrix2x2, Vector3)` · `(Vector3, Matrix2x2)` — **argument order is not commutative here** |
| `Double2` | `op_Addition` | `(Double2, Double2)` · `(Double2, Vector3)` · `(Double2, Vector2)` |
| `Double2` | `op_Subtraction` | same three |
| `Double2` | `op_Multiply` | `(Double2, Double2)` · `(Double2, Vector2)` · `(Double2, double)` · `(double, Double2)` |
| `Double2` | `ToDouble2` | static `(Vector2)` · static `(Vector3)` |
| `Double2` | `CosSin` | static `(double)` · static `(double, double)` |
| `Double2` | `Equals` | `(object)` · `(Double2)` |
| `Double2` | `op_Explicit` | `(Vector2)` · `(Double3)` |
| `SFS.World.Location` | `.ctor` | `(double, Planet, Double2, Double2)` · `(Planet, Double2, Double2 = default)` |
| `Kepler` | `GetTrueAnomalyAtRadius` | `(double r, double l, double e)` · `(Orbit, double r)` |
| `Kepler` | `GetTimeToPeriapsis` | `(double r, double e, double l, double meanMotion)` · `(double trueAnomaly, double e, double meanMotion, int direction)` — **both 4-arg, both all-`double` but for the trailing `int`; easy to bind to the wrong one** |
| `SFS.Parts.Part` | `OnOverheat` | `(bool breakup)` · `(HeatModuleBase module, bool breakup)` |
| `SFS.UI.MsgDrawer` | `Log` | `(string)` — the explicit `I_MsgLogger` impl · `(string, bool big)` |
| `SFS.Variables.Obs<T>` | `op_Addition` / `op_Subtraction` | `(Obs<T>, Action)` · `(Obs<T>, Action<T>)` · `(Obs<T>, Action<T,T>)` — same on `ReferenceVariable<T>`; `Composed<T>` has the `Action` and `Action<T,T>` forms only |

**`Double2.op_Implicit` cannot be disambiguated by parameter types at
all.** There are two, both `static Double2 → …`, differing *only* in
return type: `op_Implicit(Double2) → Vector2` and
`op_Implicit(Double2) → Vector3`. C# permits this; `GetMethod(name,
Type[])` does not model it, so **both the no-arg and the `Type[]` form
throw `AmbiguousMatchException`.** The only route is to enumerate and
filter on `ReturnType`:

```csharp
MethodInfo toV2 = typeof(Double2)
    .GetMethods(BindingFlags.Public | BindingFlags.Static)
    .First(m => m.Name == "op_Implicit"
             && m.ReturnType == typeof(UnityEngine.Vector2));
```

In practice, prefer the properties `ToVector2` / `ToVector3` (§B2.3) —
they are unambiguous and do the same thing.


---

## A3. `SFS.Variables` — the wrapper type family

37 types in this namespace. Nearly every interesting value on a
`Rocket`, `Part` or module is wrapped in one of them, so getting the
unwrapping right is a prerequisite for every other section. §E4 covers
the expression evaluator that sits behind `Composed_*`; this section
covers the wrappers themselves.

### A3.0 The three families [CONFIRMED]

There are three independent abstract bases. They are **not** related by
inheritance — a helper that handles one does not handle the others.

| Base | Concrete types | What it is |
|---|---|---|
| `Obs<T>` | `Float_Local`, `Double_Local`, `Int_Local`, `Bool_Local`, `String_Local`, `Vector2_Local`, `Double2_Local`, `Double3_Local`, `Planet_Local`, `Event_Local` | a plain observable value |
| `ReferenceVariable<T>` | `Float_Reference`, `Double_Reference`, `Bool_Reference`, `String_Reference` | a value that may be **local** or **bound to a named shared variable** |
| `Composed<T>` | `Composed_Float`, `Composed_Double`, `Composed_Vector2`, `Composed_Rect`, `Composed_Pipe`, `Composed_PipePoint` | an **expression** evaluated against a `VariablesModule` |

Plus `Obs_Destroyable<T>` (constrained to `I_ObservableMonoBehaviour`),
the `VariableList<T>` storage family (`DoubleVariableList`,
`BoolVariableList`, `StringVariableList`), `VariablesModule`,
`VariableSave`, and the value helpers `MinMaxRange`, `SizeRange`,
`Local_GenericTarget`.

**All three bases expose a public `Value` property**, which is why the
probe's single "unwrap anything with a `Value`" helper works across all
of them. But the three `Value` getters do materially different things,
and two of them have side effects.

### A3.1 `Obs<T>` [CONFIRMED]

Fields: `value`, `hasFilter`, `filter` (`Func<T,T,T>`), `onChange`
(`Action`), `onChangeNew` (`Action<T>`), `onChangeOldNew`
(`Action<T,T>`) — all private.

`get_Value()` is a plain field read, no side effects. `set_Value`
@279388:

```csharp
if (hasFilter) value = filter(this.value, value);   // filter may CHANGE what you wrote
if (IsEqual(this.value, value)) return;             // no-op, no events, if unchanged
T old = this.value;
this.value = value;
onChange?.Invoke();
onChangeNew?.Invoke(value);
onChangeOldNew?.Invoke(old, value);
```

Two things an agent must account for:

- **`set_Filter` is public and the filter can rewrite the value.** A
  write is not guaranteed to stick as given; read back after writing if
  it matters. `hasFilter` is set by the `Filter` setter.
- **Writing an equal value fires nothing.** `IsEqual` is `protected
  abstract`, so each concrete type defines equality — for float types
  that is exact comparison unless the override says otherwise (not
  checked per type — [OPEN]).

Subscription is via operators, not `+=` on an event:
`op_Addition`/`op_Subtraction` are overloaded for `Action`,
`Action<T>` and `Action<T,T>`, and the C# idiom is
`obs.OnChange += SomeMethod;` where `OnChange` is a property whose
getter returns the `Obs<T>` itself. In reflection that reads as
`get_OnChange` returning `Obs<T>` and `set_OnChange` taking one — which
looks nonsensical until you see the operator overloads. **Three
`op_Addition` overloads differing only in delegate type** — ambiguous
under naive `GetMethod`.

`op_Implicit(Obs<T>) → T` exists, which is why call sites in §B1 read
`arrowkeys.turnAxis` directly with no `.Value`.

### A3.2 `ReferenceVariable<T>` [CONFIRMED]

Fields: `variableName` (private string), `referenceToVariables`
(**public** `VariablesModule`), `localValue` (**public** `T`),
`initialized`, `variable` (`VariableList<T>.Variable<T>`), plus the
three change delegates.

```csharp
public bool Local {
    get {
        if (variableName.Length == 0) return true;
        if (referenceToVariables == null) return true;
        return Variable == null;
    }
}
public virtual T Value {
    get => Local ? localValue : Variable.Value;
    set { if (Local) { if (IsEqual(localValue, value)) return; ... } ... }
}
```

**`Local` means "not bound to a shared variable", not "has a local
override".** A `Bool_Reference` with `Local == true` reads and writes
`localValue`; one with `Local == false` reads and writes through the
`VariablesModule`. This is exactly the distinction `Rocket.GetTorque`
(§B1.3) exploits with `t.enabled.Local || t.enabled.Value` — treat an
unbound torque module as enabled.

`get_Variable()` lazily resolves and caches into `variable`, setting
`initialized = true`. `GetVariable(string)` and `GetVariableList()` are
`public abstract` — each concrete type knows which list on the
`VariablesModule` it belongs to.

`Value` here is `virtual newslot` — a concrete type may override it. Not
surveyed per type — [OPEN].

### A3.3 `Composed<T>` [CONFIRMED] — the one with side effects

Fields: `variables` (`protected VariablesModule`), `initialized`,
`value`, `onChange`, `onChangeOldNew`. Abstract members:
`GetResult(bool initialize)`, `Equals(T, T)`, `Overwrite(T)`.

```csharp
public T Value { get { CheckInitialize(); return value; } }

private void CheckInitialize() {
    if (initialized) return;
    initialized = Application.isPlaying;          // false outside play mode
    Value = GetResult(initialized);               // note: passes the NEW flag
}

protected void Recalculate() { Value = GetResult(false); }

public void set_Value(T v) {
    initialized = Application.isPlaying;
    if (Equals(this.value, v)) return;            // no-op if unchanged
    T old = this.value; this.value = v;
    onChange?.Invoke();
    onChangeOldNew?.Invoke(old, v);
}
```

**Reading `.Value` can compile an expression and register callbacks.**
`GetResult(true)` on `Composed_Float` (§E4) compiles the `input` string
and subscribes `Recalculate` to every variable it uses. That happens on
the *first* read in play mode, transparently — which is why the probe's
parametric mass reads have been correct without any setup.

**Outside play mode `initialized` never latches**, so every `.Value`
read re-runs `GetResult(false)` — a full recompile per read. Irrelevant
for a running game; relevant if any tooling ever evaluates these
headless.

`Recalculate` passes `initialize: false`, so a recalculation does not
re-register callbacks — registration happens exactly once.

`Composed<T>` is the base for `Part.mass` and `Part.centerOfMass`, and
its `onChange` is what `Mass_Calculator` subscribes to (§B6.2). The
chain **variable write → `Recalculate` → `set_Value` → `onChange` →
`MarkDirty` → `rb2d.mass`** is fully confirmed end to end.

### A3.4 Reflection notes

- The single `Value` property lookup works for all three families, but
  on `Composed<T>` it is **not** a pure read. A probe that walks every
  field and unwraps everything with a `Value` is triggering expression
  compilation as a side effect of introspection. Harmless in practice;
  worth knowing before blaming a first-frame stall on something else.
- `Obs<T>`, `ReferenceVariable<T>` and `Composed<T>` each declare
  `op_Addition` / `op_Subtraction` **three times** (`Action`,
  `Action<T>`, `Action<T,T>` — `Composed<T>` omits the `Action<T>`
  form and has two). Always pass explicit parameter types.
- `Composed_Vector2` has real `public Composed_Float x, y` fields — it
  is not a wrapper around a `Vector2` field. Confirmed while
  investigating the probe's `thrustDirX/Y` bug (§D2), where it ruled out
  the obvious explanation.
- `ReferenceVariable<T>.localValue` and `referenceToVariables` are
  **public fields**, so a bound value's local fallback can be read
  without invoking anything.

### A3.5 Status

| Item | Status |
|---|---|
| 37 types; three unrelated abstract bases | **[CONFIRMED]** |
| All three expose public `Value` | **[CONFIRMED]** |
| `Obs<T>` field layout and `set_Value` body | **[CONFIRMED]** |
| Filter can rewrite a written value | **[CONFIRMED]** |
| Equal writes fire no events | **[CONFIRMED]** |
| `ReferenceVariable<T>.Local` semantics and `Value` body | **[CONFIRMED]** |
| `Composed<T>.Value` compiles + registers on first play-mode read | **[CONFIRMED]** |
| `Composed<T>` recompiles every read outside play mode | **[CONFIRMED]** |
| `Recalculate` does not re-register | **[CONFIRMED]** |
| Triple `op_Addition` / `op_Subtraction` ambiguity | **[CONFIRMED]** |
| Per-type `IsEqual` / `Equals` overrides | **[OPEN]** — not surveyed |
| Per-type `Value` overrides on `ReferenceVariable<T>` | **[OPEN]** — not surveyed |
| `Overwrite(T)` call sites | **[OPEN]** |
| `Obs_Destroyable<T>`, `MinMaxRange`, `SizeRange`, `Local_GenericTarget` | **[OPEN]** — named only |

---

## A4. The mod loader, and the Harmony dead end

### A4.1 `ModLoader.Loader` — how mods are actually loaded

**[CONFIRMED]** — bodies read at `full_il.txt:43220–43973`.

The mod loader is baked into `Assembly-CSharp.dll` (namespace
`ModLoader`, 10 real types); there is no standalone `ModLoader.dll`.

```
ModLoader.Loader                                        @43220
  static Loader main
  List<Mod> mods, loadedMods
  void Initialize_EarlyLoad()                           @43255
  void Initialize_Load()                                @43315
  void MoveIndividualDLLs()                             @43376
  void LoadModList()                                    @43442
  void LoadMod(Mod mod)                                 @43645
  static bool VerifyVersion(string target, string current)  @43739
  bool LoadDependencies(Mod mod)                        @43762
  Mod[] GetAllMods(), GetLoadedMods()
```

**`MoveIndividualDLLs()` [CONFIRMED from body]** — enumerates files in
the Mods folder root; for every file whose extension is exactly `"dll"`,
creates a subfolder named after the DLL (minus extension) and **moves the
file into it**. A loose DLL dropped in `Mods/` relocates itself on next
launch. Wrapped in a `try`/`catch` that only logs
`"Failed to move Individual DLLs due to:"` — a failure here is silent
apart from the Unity log.

**`LoadModList()` [CONFIRMED from body]** — enumerates *subfolders* of
the Mods folder, skipping those whose name matches
`FileLocations.CustomAssetsFolder` or `CustomAssetsFolderOld`, then for
each remaining folder loads:

```
<ModsFolder>/<FolderName>/<FolderName>.dll     via Assembly.LoadFrom(path)
```

followed by `Assembly.GetTypes()` to find the `Mod` subclass. Two
consequences that matter operationally:

- **The DLL must be named after its containing folder.** `SFSProbe/SFSProbe.dll` works; `SFSProbe/probe.dll` is never loaded.
- **Sibling DLLs in the mod's folder are never explicitly loaded.** `LoadModList` loads exactly one assembly per folder. This is central to §A4.2.

Failures are caught per-folder and logged as
`"Failed to load mod in folder: {0}.\nError:{1}"` — check the Unity
player log, not just `probe.log`, when a mod silently fails to appear.

**`LoadDependencies(Mod)` [CONFIRMED from body]** — resolves
**inter-mod** dependencies only, from `Mod.Dependencies`
(`Dictionary<string,string>`, mod ID → version). It has nothing to do
with loading a mod's bundled library DLLs. It self-reference-checks
(`", has a reference to itself. Aborting"`) and consults
`ModsSettings.main.settings.modsActive`.

### A4.2 CORRECTION — the stated Harmony root cause is not supported by the IL

`sfs_source_reference.md` and `high_level_checklist.md` both state that

> SFS's own built-in mod loader — baked directly into
> `Assembly-CSharp.dll` — already loads the old Harmony/MonoMod into the
> process before any individual mod's `Load()` callback runs

and conclude from this that bundling a newer HarmonyX **cannot** work,
so the only remaining fix is replacing the game's own
`Managed/0Harmony.dll` (which was deliberately declined).

**That mechanism is wrong.** Confirmed:

| Check | Result |
|---|---|
| Occurrences of `HarmonyLib` or `MonoMod` in the full IL of `Assembly-CSharp.dll` | **0** |
| Extern assembly references to `0Harmony` / `MonoMod.*` in `Assembly-CSharp.dll` | **none** (36 extern refs, all listed, none Harmony/MonoMod) |
| Assemblies in `Managed/` that reference `0Harmony` | **none** — every DLL in the folder was checked with `monodis --assemblyref` |
| `Assembly-CSharp-firstpass.dll` type refs to Harmony/MonoMod | **none** |

The game ships `0Harmony.dll` (2.10.1.0), `MonoMod.RuntimeDetour` /
`MonoMod.Utils` (22.3.23.4) and `Mono.Cecil` (0.10.4.0) in `Managed/`
purely as a **convenience library for mods**. Nothing in the game
references or loads them. The mod loader in particular
(`LoadModList` above) loads exactly one assembly per mod folder and
never touches Harmony.

So the old Harmony is **not pre-loaded before mods run**. The MVID
evidence recorded in memory is still valid — it proves the *old* DLL is
what ultimately got loaded — but it identifies the symptom, not the
cause.

**The supported mechanism [PARTIAL — IL-grounded, not runtime-proven]:**
`SFSProbe.dll` carries a reference to `0Harmony`. When the JIT first
touches a `HarmonyLib` type, Mono resolves that reference by simple name
(both copies are **weak-named** — `monodis --assembly` reports a
zero-sized public key on the game's 2.10.1.0 *and* on the bundled
2.16.0.0, so only one `0Harmony` can exist per process and version is
not part of identity). Mono's default probing path is the **application
base** — `Managed/` — which is searched before the directory beside the
mod DLL.

`build.sh` states the opposite assumption in a comment:

> All 7 DLLs need to sit next to SFSProbe.dll at runtime — 0Harmony.dll
> pulls in the rest of this chain via Mono's normal assembly probing of
> the loading assembly's own directory.

Co-locating the DLLs is necessary but **not sufficient**: it does not
beat the app base for an assembly name that already exists there.

### A4.3 What this changes, and what it does not

**Does not change:** the decision to stop pursuing Harmony was
reasonable, and this section is not an argument to resume it. The
`dragArea` goal that motivated it is now solved without Harmony (§C1).

**Does change:** the claim that *no non-invasive fix exists* is
unsupported. If Harmony is ever wanted again, at least two options exist
that were never tried and that do **not** require modifying the game's
`Managed/` folder:

1. Install an `AppDomain.CurrentDomain.AssemblyResolve` handler, or
   `Assembly.LoadFrom` the bundled `0Harmony.dll` by absolute path, in
   the mod's entry point — **before any `HarmonyLib` type is touched**.
   The trigger point matters: type resolution happens on first JIT of a
   method that references the type, so the loading code must live in a
   method that itself has no Harmony references.
2. Strong-name the bundled copy so it no longer collides on simple name.

**[OPEN]** — neither has been tried, and neither is proven to work.
`Mono.Cecil` presents the same collision independently (game 0.10.4.0 vs
bundle 0.11.6, also weak-named), so a fix must cover the whole chain.

**Independent of all of the above**, the ceiling on Harmony here may
still be low: MonoMod issue #230 (`ILHookOnMonoShouldSucceed`) was still
failing CI on macOS 14 arm64 sysmono as of 2025-09-30 — near-exact match
for this environment. Fixing assembly resolution could simply trade the
current `NullReferenceException` for `InvalidProgramException` at the
same conceptual step. Expect a different error, not a guaranteed success.

### A4.4 The original failure signature, for recognition

**[CONFIRMED]** — observed live, reproduced with an isolating test.

```
HarmonyLib.HarmonyException: IL Compile Error (unknown location)
 ---> System.NullReferenceException
  at MonoMod.RuntimeDetour.DetourHelper.GetIdentifiable(MethodBase)
  at MonoMod.RuntimeDetour.ILHook..ctor(...)
  at HarmonyLib.Public.Patching.ManagedMethodPatcher.DetourTo(MethodBase)
  at HarmonyLib.PatchFunctions.UpdateWrapper(...)
```

Environment-wide, not target-specific: patching a trivial no-op method
in the mod's **own** assembly fails identically
(`GeometryPatches.TestTrivialPatch`, still present in `SFSProbe.cs`).
Setting `MONOMOD_DMDType=Cecil` produced a byte-identical stack trace,
placing the failure upstream of DMD generation, in detour-runtime
platform selection.

Root cause of *that* crash (as opposed to the resolution problem above):
MonoMod 22.3.23.4 predates Apple Silicon macOS support, added in MonoMod
PR #241 (merged 2025-08-15, first shipped in HarmonyX 2.15.0). Apple's
Hardened Runtime uses W^X `MAP_JIT` pages requiring dedicated unmanaged
helper code to patch running methods, which that build never had.

### A4.5 Version inventory

**[CONFIRMED]** via `monodis --assembly` on each file, 2026-08-27.

| Assembly | Game `Managed/` | Bundled `sfsprobe/lib/harmonyx_2.16.0/` |
|---|---|---|
| `0Harmony` | 2.10.1.0 | 2.16.0.0 |
| `MonoMod.RuntimeDetour` | 22.3.23.4 | 25.3.3 |
| `MonoMod.Utils` | 22.3.23.4 | 25.0.11 |
| `Mono.Cecil` | 0.10.4.0 | 0.11.6 |

All weak-named on both sides. The game also ships `Mono.Cecil.Mdb`,
`Mono.Cecil.Pdb`, `Mono.Cecil.Rocks`. The bundle adds
`MonoMod.Backports`, `MonoMod.Core`, `MonoMod.ILHelpers`. The bundled
files are inert as long as nothing resolves to them — harmless to leave
in place.

---

## C1. Drag and aerodynamics — `SFS.World.Drag`

The highest-priority system in the project: it produces `dragArea` and
center-of-pressure, which gate aerodynamic torque magnitude and
atmospheric ascent prediction. Every method body in the drag path has now
been read.

### C1.0 Architecture — CORRECTION

**[CONFIRMED]** — `AeroModule` @215749, `Aero_Rocket` @220145.

`sfs_source_reference.md` describes these as two levels of the same idea:

> `SFS.World.Drag.Aero_Rocket` — drag/aero, rocket level
> `SFS.World.Drag.AeroModule` — drag/aero, per-part-module level
> `instance List<Surface> GetDragSurfaces(Matrix2x2 rotate)` — per-module version (single part)

**That is wrong.** `AeroModule` is an **abstract base class**, not a
per-part module. `AeroModule.GetDragSurfaces(Matrix2x2)` is
`family virtual newslot abstract` — i.e. `protected abstract` — and has
no body at all. `Aero_Rocket` is a **subclass** that overrides it. There
is no per-part drag module; drag is computed for a whole `PartHolder` at
once.

```
abstract AeroModule                       @215749
  ├── Aero_Rocket    : AeroModule         @220145   (rockets)
  ├── Aero_Astronaut : AeroModule                   (EVA astronauts)
  └── Water_Rocket                                  (separate, see C2)
```

The five abstract members a subclass must supply — all `protected`, so
reflection **must** include `BindingFlags.NonPublic`:

```
protected abstract bool           PhysicsMode      { get; }   @217512
protected abstract Location       GetLocation()               @217519
protected abstract List<Surface>  GetDragSurfaces(Matrix2x2)  @217526
protected abstract void           AddForceAtPosition(Vector2 force, Vector2 position)  @217533
protected abstract float          GetMass()                   @217540
```

`AeroModule` instance fields **[CONFIRMED]** — nine, all non-physics
except `heatManager`:

```
public HeatManager  heatManager      <- §D1
public BurnManager  burnManager
public AeroMesh     shockEdge, shockOuter, reentryEdge, reentryOuter   (visuals)
public AudioModule  airflowSound, burnSound                            (audio)
private int         frameIndex
```

`Aero_Rocket` has exactly **one** instance field: `public Rocket rocket`.

> **Neither class has an `output` field.** An earlier pass of this
> document listed one on both. It is a compiler-generated closure field
> on a nested `<>c__DisplayClass` — see §A2. Corrected before publication;
> noted here because the same artifact will recur on any class with
> closures.

### C1.1 The real pipeline, from `FixedUpdate`

**[CONFIRMED]** — body read at @215769–215950.

```csharp
frameIndex++;
Location location = GetLocation();
if (IsInsideAtmosphereAndIsMoving(location)) {
    GetTemperatureAndShockwave(location, out float Q, out float shockOpacity, out float temperature);

    bool applyDrag = PhysicsMode && !SandboxSettings.main.settings.noAtmosphericDrag;
    bool applyHeat = temperature > 0f;

    if (applyDrag || applyHeat) {
        float a = (float)location.velocity.AngleRadians - 1.5707964f;   // - PI/2
        Matrix2x2 toVelocity  = Matrix2x2.Angle(-a);                    // -> GetDragSurfaces
        Matrix2x2 localToWorld = Matrix2x2.Angle(a);                    // -> ApplyForce / heating

        List<Surface> exposed = GetExposedSurfaces(GetDragSurfaces(toVelocity));

        if (applyDrag) ApplyForce(exposed, location, localToWorld, out float g_ForSound);
        if (applyHeat) FixedUpdate_Reentry_And_Heating(temperature, exposed, a, localToWorld, out drewReentryMesh);
    }
    // ... airflow/burn audio ...
} else {
    airflowSound.volume.Value = 0f;  burnSound.volume.Value = 0f;
}
heatManager.DissipateHeat(frameIndex);
```

Four things worth extracting:

1. **`IsInsideAtmosphereAndIsMoving(location)` is a hard gate** — public
   static @217489. Outside it, drag *and* heating are both entirely
   skipped. Call it before trusting any drag number.
2. **`SandboxSettings.main.settings.noAtmosphericDrag`** disables drag
   while leaving heating active. A sandbox world with this set produces
   zero drag with no other symptom — check it before concluding a
   measurement is wrong.
3. **There are two rotation matrices, negations of each other.**
   `Matrix2x2.Angle(-a)` goes into `GetDragSurfaces`; `Matrix2x2.Angle(a)`
   is the `localToWorld` used to map the resulting center-of-drag back to
   world space. Using one where the other belongs mirrors the result.
4. **`GetExposedSurfaces` output is shared** between the drag path and
   the heating path — computed once per `FixedUpdate`.

**Precision note on `a`.** The game computes
`(float)location.velocity.AngleRadians - 1.5707964f` — the cast to
`float32` happens **before** the subtraction (`conv.r4` at IL_0071,
`ldc.r4` at IL_0072). The drafted probe code computes
`(float)(-(velocityAngle - Math.PI / 2.0))` in `double` and casts at the
end. These differ in the last ulp. Irrelevant for a magnitude check,
relevant if ever bit-matching the game's own output.

### C1.2 `GetDragSurfaces` — geometry source, and the ambiguous overload

**[CONFIRMED]** — instance @220181 (18 bytes), static @220196 (355 bytes).

Two overloads on `Aero_Rocket`, same name. This is the confirmed
`AmbiguousMatchException` case (§A1.1).

```
protected override List<Surface> GetDragSurfaces(Matrix2x2 rotate)                        @220181
public static     List<Surface> GetDragSurfaces(PartHolder partsHolder, Matrix2x2 rotate) @220196
```

The instance overload is a **pure forwarder** — its entire body is
`return GetDragSurfaces(this.rocket.partHolder, rotate);`. Confirmed, 18
bytes of IL.

**This matters more than it looks.** Because the instance version only
supplies `rocket.partHolder`, the static version works on **any**
`PartHolder` — including one not attached to a flying rocket. The game
itself relies on this: `BurnManager` (top-level, no namespace) calls the
**static** overload directly at @26301. So drag area is computable for a
design before it flies, which is directly relevant to the design-agent
side of this project. **[UNTESTED-LIVE]** for a non-flying `PartHolder`.

The static body, decompiled:

```csharp
public static List<Surface> GetDragSurfaces(PartHolder partsHolder, Matrix2x2 rotate)
{
    var output = new List<Surface>();                     // fresh list every call
    foreach (SurfaceData sd in partsHolder.GetModules<SurfaceData>())
    {
        if (!sd.Drag) continue;                           // per-part opt-out
        Vector3 scale = sd.transform.lossyScale;
        bool flip = (scale.x > 0f) != (scale.y > 0f);     // mirrored part
        HeatModuleBase heatModule = sd.heatModule;
        foreach (Surfaces s in sd.surfacesFast)
        {
            var pts = new Vector2[s.points.Length];
            for (int i = 0; i < s.points.Length; i++)
                pts[i] = (Vector2)s.owner.TransformPoint((Vector3)s.points[i]) * rotate;
            // ... AddLine over consecutive points (local fn <GetDragSurfaces>g__AddLine|5_0) ...
        }
    }
    return output;
}
```

Confirmed consequences:

- **The returned list is freshly allocated per call.** Safe to hold and
  inspect; it is not a reused buffer.
- **Output is in velocity-aligned world space**, not part-local space.
  Points go through `Transform.TransformPoint` (local → world) and are
  then multiplied by `rotate`. Do not expect part-local outlines back.
- **`SurfaceData.Drag` gates participation per part.** Backed by the
  private `dragSurfaces` field via `get_Drag()` @268796. A part with it
  false contributes nothing.
- **`flip` is derived from `lossyScale` sign mismatch** — mirrored parts
  need their winding reversed.

**Reflection gotcha: `PartHolder.GetModules<T>()` is generic** (@238644,
`instance !!T[] GetModules<T>()`). Reaching it needs
`MakeGenericMethod(surfaceDataType)`, not a plain `GetMethod` call. This
only matters if reimplementing the walk — calling `GetDragSurfaces`
itself avoids the problem entirely.

### C1.3 Geometry types

**[CONFIRMED]**

```
SFS.Parts.Modules.SurfaceData                    @268763   (abstract)
  private bool                  attachmentSurfaces
  private bool                  dragSurfaces
  public  List<Surfaces>        surfaces
  public  List<Surfaces>        surfacesFast          <- the drag geometry
  public  Event_Local           onChange              (notserialized)
  public  HeatModuleBase        heatModule            (notserialized)
  public  bool  Attachment { get; }                   @268778
  public  bool  Drag       { get; }                   @268796
  public  abstract void Output()                      @268814
  protected void SetData(List<Surfaces>)              @268821
  protected void SetData(List<Surfaces>, List<Surfaces>)  @268835   <- AMBIGUOUS PAIR
  public static bool IsSurfaceCovered(SurfaceData)    @268854

SFS.Parts.Modules.Surfaces                       @268970
  public readonly Vector2[]  points
  public readonly Transform  owner
  public readonly bool       loop
  public Line2[] GetSurfacesWorld()                   @268999

SFS.World.Drag.Surface                           @217767   (struct)
  public HeatModuleBase  owner
  public Valid           valid
  public Line2           line

SFS.World.Drag.Valid                             @218601   (CLASS, not struct)
  public bool valid
```

**`SetData` is a second confirmed ambiguous overload pair** — added to
§A1.1. Both are `family` (protected).

**`Valid` is a reference type holding one `bool`.** It is a shared
invalidation token, not a per-surface flag: many `Surface` structs point
at the same `Valid` instance, so flipping it invalidates a whole group at
once. Reading `surface.valid` gives you the token object — you want
`Get(Get(surface,"valid"),"valid")`.

**`Line2` @15536 is a struct** with a much richer API than previously
recorded — 20 methods, not 2 fields:

```
public Vector2 start, end
public Vector2 Size { get; }   public float SizeX { get; }   public float SizeY { get; }
public static Line2 StartSize(Vector2 start, Vector2 size)
public Vector2 Lerp(float t)                    public Vector2 Lerp(float tX, float tY)      <- AMBIGUOUS
public Vector2 LerpUnclamped(float t)           public Vector2 LerpUnclamped(float tX, float tY)  <- AMBIGUOUS
public void Flip()  public void FlipHorizontally()  public void FlipVertically()
public Vector2 GetPositionAtX(float x)          public Vector2 GetPositionAtY(float y)
public Vector2 GetPositionAtX_Unclamped(float x)
public float GetHeightAtX(float x)              public float GetHeightAtX_Unclamped(float x)
public float GetSlope()
public static float GetSlope(Vector2 start, Vector2 end)      <- AMBIGUOUS with the instance one
public static float GetSlope_Abs(Vector2 start, Vector2 end)
public static bool FindIntersection_Unclamped(Line2 a, Line2 b, out Vector2 position)
```

`Lerp`, `LerpUnclamped`, and `GetSlope` are all ambiguous pairs — §A1.1.

**`Matrix2x2` @2535 is a CLASS, not a struct** (reference type,
`auto ansi`, private `Vector2 x, y`), top-level with **no namespace**:

```
public static Matrix2x2 Angle(float angleRadians)              @2542
public static Vector2 operator *(Matrix2x2 m, Vector2 b)       @2573
public static Vector2 operator *(Vector2 b, Matrix2x2 m)       @2610
public static Vector2 operator *(Matrix2x2 m, Vector3 b)       @2647
public static Vector2 operator *(Vector3 b, Matrix2x2 m)       @2684
public float GetX(Vector2 b)                                   @2721
```

Four `op_Multiply` overloads — ambiguous, and note `GetDragSurfaces` uses
the `(Vector2, Matrix2x2)` order while `ApplyForce` uses
`(Matrix2x2, Vector2)`. They are **not** the same operation.

### C1.4 `CalculateDragForce` — this IS `dragArea`

**[CONFIRMED]** — full body read @216054–216155. `private static`.

```csharp
private static (float drag, Vector2 centerOfDrag) CalculateDragForce(List<Surface> surfaces)
{
    float drag = 0f;
    Vector2 centerOfDrag = Vector2.zero;
    for (int i = 0; i < surfaces.Count; i++)
    {
        Surface s = surfaces[i];
        Vector2 d = s.line.end - s.line.start;
        if (d.x < 0.01f) continue;                            // cull
        float weight = d.x / (d.x + Mathf.Abs(d.y));
        float w      = d.x * weight;                          // == dx^2 / (dx + |dy|)
        drag         += w;
        centerOfDrag += (s.line.start + s.line.end) * w;
    }
    if (drag > 0f)
        centerOfDrag /= drag * 2f;
    return (drag, centerOfDrag);
}
```

**Tuple element names are not inferred.** The method carries a
`TupleElementNamesAttribute` whose blob decodes to `drag` and
`centerOfDrag` — `Item1` is drag area, `Item2` is center of drag. Read
directly from the attribute (§A2).

**Exact agreement with `sfs_physics_reference.md` §2.3:**

- `drag = Σ dx²/(dx+|dy|)` — the documented `dragArea` formula, exactly.
- `centerOfDrag = Σ((start+end)·w) / (2·drag) = Σ(midpoint·w) / drag` —
  the documented CoP formula, exactly.

**NEW — the `d.x < 0.01f` cull threshold, not previously documented.**
Segments whose x-extent in velocity-aligned space is below 0.01 are
skipped entirely. Because the comparison is `<` on a signed value, this
culls **both** leeward-facing segments (negative `dx`) and near-edge-on
ones. It is the windward-face selection *and* a small-segment filter in
one test. Any Python reimplementation must reproduce the 0.01 threshold,
not just the sign test — the two differ for finely-tessellated outlines.

### C1.5 `ApplyForce` — the force law, confirmed

**[CONFIRMED]** — full body read @215950–216054.

```csharp
private void ApplyForce(List<Surface> exposedSurfaces, Location location,
                        Matrix2x2 localToWorld, out float g_ForSound)
{
    (float drag, Vector2 centerOfDrag) = CalculateDragForce(exposedSurfaces);

    float density = (float)location.planet.GetAtmosphericDensity(location.Height);
    float f       = drag * 1.5f * (float)location.velocity.sqrMagnitude;
    Vector2 cop   = localToWorld * centerOfDrag;

    g_ForSound = f * density / GetMass() / 9.8f;

    if (this is Aero_Rocket ar)
    {
        cop = Vector2.Lerp(ar.rocket.rb2d.worldCenterOfMass, cop, 0.2f);
        ar.ApplyParachuteDrag(ref f, ref cop);          // mutates BOTH
    }

    Vector2 force = -location.velocity.ToVector2.normalized * (f * density);

    if (!float.IsNaN(force.x + force.y + cop.x + cop.y))
        AddForceAtPosition(force, cop);
}
```

Confirms `sfs_physics_reference.md` §2.3 precisely: the `1.5` constant,
`|v|²` via `sqrMagnitude`, and the `Lerp(CoM, CoP, 0.2)` application
point. Four details that were **not** previously documented:

1. **`ApplyParachuteDrag` runs *after* the 0.2 lerp** and mutates both
   the force magnitude and the application point by reference. Parachute
   drag is therefore **not** subject to the CoP damping that surface drag
   is. A parachute-carrying rocket does not follow the §2.3 model alone —
   see §C1.7.
2. **The 0.2 lerp is `Aero_Rocket`-only.** `Aero_Astronaut` applies drag
   at the raw CoP with no damping.
3. **`g_ForSound` is `f·ρ/mass/9.8`** — a g-force figure computed *only*
   to drive audio. It is not used in physics, but it is a free, correct
   g-load readout if ever wanted.
4. **A NaN guard suppresses the force entirely** if any component is NaN.
   A rocket silently experiencing zero drag may be hitting this rather
   than a zero drag area.

**`Planet.GetAtmosphericDensity(double height)`** is the real public
density entry point — see §D4.

### C1.6 `GetExposedSurfaces` — occlusion

**[PARTIAL]** — `public static` @216431, 1,523 bytes of IL. Control flow
traced and constants confirmed; not every branch transcribed.

```
public static List<Surface> GetExposedSurfaces(List<Surface> surfacesList)
```

Confirmed structure:

- **Empty input returns a new empty list**, not null.
- Input is first passed through `AeroModule.Sort(List<Surface>)`
  (public static @216974), which delegates to a **`RadixSort`** over
  `uint` keys (@217040) — a bucket sort on the x-coordinate, not a
  comparison sort.
- It then performs a **sweep along the x axis**, maintaining an ordered
  list of exposed "sections" and using four compiler-emitted local
  functions to edit it:
  `<GetExposedSurfaces>g__InsertSection|16_0` @217659,
  `g__RemoveSection|16_1` @217587,
  `g__SetSectionStart|16_2` @217603,
  `g__SetSectionEnd|16_3` @217631.
- Overlaps are resolved by comparing `y` at shared `x`, splitting
  segments with `Line2.GetPositionAtX_Unclamped` and keeping the
  windward one.
- **Epsilon is `0.001f` throughout** — used for both x-ordering
  comparisons and for treating a `y` difference as zero before taking
  `Mathf.Sign`.

**This is the "lower envelope / visible surface" problem** the Python
solver in `python_changelog.md` was built to solve. The game's own
implementation is public and callable, so the solver is not needed to
obtain the value — though it remains useful as an independent
cross-check.

**[OPEN]** — the exact tie-breaking behaviour when two segments share
both `x` and `y`, and the handling of surfaces belonging to different
`owner` parts at the same `x`, were not fully traced.

### C1.7 Neighbouring methods, now catalogued

**[PARTIAL]** — signatures confirmed; bodies not read except where noted.

```
public static void  GetTemperatureAndShockwave(Location, out float Q,
                        out float shockOpacity, out float temperature)   @216283
public static float GetIntensity(float value, float halfPoint)           @216381
public static float GetHeatTolerance(HeatTolerance a)                    @216396
public static Surface[] Sort(List<Surface> list)                         @216974
public static Line2[]   RotateSurfaces(List<Surface>, Matrix2x2)         @217439
public static bool  IsInsideAtmosphereAndIsMoving(Location)              @217489
private static List<Surface> RemoveHighSlopeSurfaces(List<Surface>, float maxSlope)  @217195
private static void ApplyProtectionZone(List<Surface> surfaces)          @217218
private void FixedUpdate_Reentry_And_Heating(float temperature, List<Surface>,
                        float velocityAngleRad, Matrix2x2, out bool)     @216155
```

**Call-site finding [CONFIRMED]:** `RemoveHighSlopeSurfaces` and
`ApplyProtectionZone` each have exactly **one** caller, at @216191 and
@216194 — both inside `FixedUpdate_Reentry_And_Heating`. They are part
of the **heating** path only and play no role in drag. A reimplementation
of drag must not apply them; a reimplementation of heating must.

`GetTemperatureAndShockwave` is `public static` and takes only a
`Location` — a directly callable entry point for §D1.

`Aero_Rocket.ApplyParachuteDrag(ref float force, ref Vector2 centerOfDrag_World)`
@220367 — **[OPEN]**, body not yet read. Needed before any
parachute-carrying descent can be predicted.

### C1.8 Reflection recipe

**[UNTESTED-LIVE]** — **applied** to `SFSProbe.cs` as the `dragarea`
command in **v0.27.0** (2026-08-28), built, but not yet run against the
running game. The code below matches what shipped.

Two details of the shipped version verified against the IL for this
document:

- It reads the velocity as `GetWrapped(dloc, "velocity")` rather than
  plain `Get`. **This is safe.** `Double2` (@180) is a struct with only
  public `x`/`y` fields and computed properties — it has no `Value`
  property and no `value` field — so `GetWrapped2` finds neither and
  returns the `Double2` unchanged. `AngleRadians` (@341) then resolves
  as a property via `Get`.
- `Unwrap(Get(r, "location"))` is the correct peel. `Rocket.location` is
  declared on the base class `SFS.World.Player` as a
  **`WorldLocation`**, whose `get_Value()` returns `SFS.World.Location`
  (confirmed in `Aero_Rocket.GetLocation()`'s body @220167). `Unwrap`
  peels the wrapper and stops on its `t.Name == "Location"` guard —
  exactly one layer, landing on the right type.

It resolves `CalculateDragForce` with
`Public | NonPublic | Static`. The method is `private static`, so the
`NonPublic` flag is the one doing the work; the `Public` flag is
harmless.

Binding flags that are not optional:

| Target | Required flags | Why |
|---|---|---|
| `Aero_Rocket.GetDragSurfaces(Matrix2x2)` | `NonPublic \| Instance` | `protected override` |
| `AeroModule.GetExposedSurfaces` | `Public \| Static` | |
| `AeroModule.CalculateDragForce` | `NonPublic \| Static` | `private static` |
| `Aero_Rocket.GetDragSurfaces(PartHolder, Matrix2x2)` | `Public \| Static` | |

All four `GetDragSurfaces`/`CalculateDragForce` resolutions **must** use
the explicit-parameter-types form (§A1). `rocket.aero` is an
`Aero_Rocket`; `Matrix2x2` resolves as a bare `"Matrix2x2"`.

```csharp
case "dragarea":
{
    object r = ActiveRocket();
    if (r == null) { ProbeMod.Result("dragarea: no active rocket"); break; }
    object aero = Get(r, "aero");
    if (aero == null) { ProbeMod.Result("dragarea: rocket.aero is null"); break; }

    Type matrixType     = FindType("Matrix2x2");
    Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
    if (matrixType == null || aeroModuleType == null)
    { ProbeMod.Result("dragarea: FAILED to resolve Matrix2x2 or AeroModule"); break; }

    // Rotation input, confirmed from AeroModule.FixedUpdate()'s own IL.
    // NOT identity. Game computes this in float32; see C1.1 precision note.
    object location = Unwrap(Get(r, "location"));
    object velocity = Get(location, "velocity");
    double velocityAngle = ToD(Get(velocity, "AngleRadians"));
    float rotationInput  = (float)(-(velocityAngle - Math.PI / 2.0));
    object matrix = InvokeStatic(matrixType, "Angle",
        new Type[] { typeof(float) }, new object[] { rotationInput });
    if (matrix == null) { ProbeMod.Result("dragarea: Matrix2x2.Angle FAILED"); break; }

    // protected override -> NonPublic|Instance, explicit param types (2 overloads)
    MethodInfo getDragSurfaces = aero.GetType().GetMethod("GetDragSurfaces",
        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
        null, new Type[] { matrixType }, null);
    if (getDragSurfaces == null)
    { ProbeMod.Result("dragarea: couldn't resolve 1-arg GetDragSurfaces"); break; }

    object allSurfaces;
    try { allSurfaces = getDragSurfaces.Invoke(aero, new object[] { matrix }); }
    catch (Exception e)
    {
        ProbeMod.Result("dragarea: GetDragSurfaces threw: " +
            (e.InnerException != null ? e.InnerException.Message : e.Message));
        break;
    }

    object exposed = allSurfaces == null ? null :
        InvokeStatic(aeroModuleType, "GetExposedSurfaces",
            new Type[] { allSurfaces.GetType() }, new object[] { allSurfaces });

    // private static -> NonPublic|Static
    MethodInfo calcDrag = aeroModuleType.GetMethod("CalculateDragForce",
        BindingFlags.NonPublic | BindingFlags.Static,
        null, new Type[] { exposed.GetType() }, null);
    var tuple = (System.ValueTuple<float, Vector2>)calcDrag.Invoke(null, new object[] { exposed });
    // tuple.Item1 = dragArea, tuple.Item2 = centerOfDrag (velocity-aligned space)
    break;
}
```

**Gotchas confirmed from the IL:**

- `GetDragSurfaces` returns a **fresh** `List<Surface>` — safe to retain.
- `Surface.line.start/end` are in **velocity-aligned world space**. To
  get world coordinates, multiply by `Matrix2x2.Angle(+a)` (the
  non-negated matrix), or use `AeroModule.RotateSurfaces`.
- `Surface.valid` is a `Valid` **object**; the bool is one level deeper.
- `CalculateDragForce` culls `dx < 0.01f`, so a nonzero surface count
  can still yield `drag == 0`.
- If the rocket is outside the atmosphere or stationary, the game skips
  this whole path — but these methods will still happily compute a
  number. Gate on `IsInsideAtmosphereAndIsMoving` to match the game.
- Sandbox `noAtmosphericDrag` does **not** affect these methods; it only
  gates whether `ApplyForce` runs.

### C1.9 Status summary

| Item | Status |
|---|---|
| `AeroModule` is abstract; `GetDragSurfaces` is protected abstract | **[CONFIRMED]** — corrects earlier doc |
| Rotation input `-(velocityAngle - π/2)`, and its `+` twin | **[CONFIRMED]** from `FixedUpdate` body |
| `CalculateDragForce` returns `(drag, centerOfDrag)` | **[CONFIRMED]** from attribute blob |
| `dragArea = Σ dx²/(dx+\|dy\|)`, CoP formula | **[CONFIRMED]** — exact match to §2.3 |
| `dx < 0.01f` cull threshold | **[CONFIRMED]** — newly documented |
| Force law `1.5·drag·\|v\|²·ρ`, applied at `Lerp(CoM,CoP,0.2)` | **[CONFIRMED]** from `ApplyForce` body |
| Parachute drag bypasses the 0.2 damping | **[CONFIRMED]** — newly documented |
| Static overload works on any `PartHolder` | **[CONFIRMED]** in IL; **[UNTESTED-LIVE]** off-rocket |
| `GetExposedSurfaces` sweep structure, eps `0.001f` | **[PARTIAL]** |
| `GetExposedSurfaces` tie-breaking | **[OPEN]** |
| `ApplyParachuteDrag` body | **[OPEN]** |
| The probe `dragarea` command | **[UNTESTED-LIVE]** — applied in v0.27.0, built, not yet run live |

### C1.10 Aerodynamic torque — [CONFIRMED], live-validated 2026-08-31

The torque itself needed no new IL — every piece was already confirmed
above. What it needed was actually wiring two of those pieces together
correctly, which nothing in the probe had done before this session.

```csharp
// TryComputeAeroTorque, sfsprobe/SFSProbe.cs v0.49.0
float localToWorldInput = (float)(velocityAngle - Math.PI / 2.0);   // the NON-negated angle
object localToWorldMatrix = Matrix2x2.Angle(localToWorldInput);
Vector2 copWorld = localToWorldMatrix * new Vector2(dragCopVelX, dragCopVelY);

float copAppliedX = comX + (copWorld.x - comX) * 0.2f;              // confirmed §2.3 Lerp
float copAppliedY = comY + (copWorld.y - comY) * 0.2f;

float torqueZ = (copAppliedX - comX) * forceY - (copAppliedY - comY) * forceX;  // r x F, 2D
float alphaPred = torqueZ / rb2d.inertia;
```

> **ADDITION (2026-09-02, forward_sim.py wiring session) -- alphaPred
> above is in rad/s^2, not deg/s^2.** Not called out when this section
> was first written. Confirmed by reproducing sfs_probe_aerotorque.json's
> predictedAngularAccelDegPerSec2 field by hand: torqueZ / inertia alone
> gives 0.027524539..., matching neither the snapshot's predictedTorque
> (that is torqueZ itself, already matched) nor
> predictedAngularAccelDegPerSec2 (1.5770399570465088) directly --
> multiplying by 57.29578 (rad->deg, the same constant B1.3's ApplyTorque
> uses) closes the gap exactly: 0.027524539... * 57.29578 = 1.5770399538,
> matching the snapshot to float32 rounding. Consistent with this being
> genuine Unity rotational physics (AddForceAtPosition, radian-based
> internally) unlike player-commanded rotation, which writes
> angularVelocity (deg/s) directly and needs no such conversion at the
> call site (the 57.29578 there converts torque/mass, a different
> quantity, at a different point in the calculation).
> Reimplementations should use
> alphaPred_degPerSec2 = (torqueZ / rb2d.inertia) * 57.29578f.

**Bug found and fixed:** `dragCopX`/`dragCopY` in `truth.jsonl` (sampled
every tick since v0.28.0) are the raw `centerOfDrag` output of
`CalculateDragForce` (§C1.4) — which is in **velocity-aligned space**,
not real world/scene coordinates. The rotation needed to convert it —
the non-negated `Matrix2x2.Angle(velocityAngle - π/2)`, opposite sign
from the `rotate` matrix `GetDragSurfaces` uses to build the
velocity-aligned surfaces in the first place — was confirmed via IL in
§C1.2's gotchas list long before this session, but nothing had ever
actually applied it. Any CoM-relative use of the telemetry field before
now (there wasn't one) would have silently used the wrong frame.

**`rb2d.inertia`** — a stock `UnityEngine.Rigidbody2D` property, not
game-specific IL — was read live for the first time this session. It's
required because aero force is applied via the real
`Rigidbody2D.AddForceAtPosition` (§C1.5's `ApplyForce`), which is genuine
Unity rotational physics; this is unlike player-commanded rotation
(§B1.3), which writes `angularVelocity` directly and never touches
inertia at all. Two different rotation mechanisms in the same game,
confirmed to behave completely differently.

**Live validation** (real capsule+heat-shield reentry, hands off all
controls, engine/RCS off): 12,174 clean ticks (stable `rb2d.inertia`,
`output_TurnAxisTorque == 0` on both tick endpoints) gave **correlation
0.9986** between predicted and real finite-differenced angular
acceleration; on the 117 ticks with |real α| > 5°/s², **100% sign
agreement**, magnitude ratio 0.985–1.011 at the largest swings, median
error 4.66%.

**The confound, and why three earlier flights failed:** SAS
auto-stabilization (§B1.3's `GetStopRotationTurnAxis`, deadbeat
damping) engages whenever `hasControl && !IsOnSurface` and
`arrowkeys.turnAxis == 0` — i.e. exactly whenever nothing else is
commanding rotation. It writes `angularVelocity` directly through the
same code path as manual input (§B1.3's `ApplyTorque`), so it completely
bypasses `rb2d.inertia` and the aero-torque model above, and it does so
silently — there is no in-game SAS toggle or indicator. "Hands off
controls" turns out to be precisely SAS's trigger condition, not the
absence of it. **Filtering on raw `arrowkeys.turnAxis == 0` is not
enough** to isolate pure aero torque; the correct signal is
`Rocket.output_TurnAxisTorque` — the value `ApplyTorque` actually applies
that tick, from either source. On the successful validation flight,
`output_TurnAxisTorque` was nonzero on 12,532 of 25,491 ticks; of those,
11,575 had zero manual input, i.e. SAS alone. Three prior flights (all
filtered on raw `turnAxis`) showed near-zero or contradictory
correlation for exactly this reason — not a flaw in the formula.

**Known caveat, deliberately not handled:** invalid mid-parachute-
deployment, since `ApplyParachuteDrag` (§C1.9's status table, §2.3)
mutates force and CoP by reference and that mutation is not replicated
here.

Probe support: `aerotorque` command (on-demand) and
`computed:aeroTorque` scoped-telemetry field, both v0.49.0.

### C1.11 `ApplyParachuteDrag` — [CONFIRMED]

Small, self-contained, fully decoded. Called from within `ApplyForce`
(§C1.5) right after the normal `Lerp(worldCenterOfMass, cop_world, 0.2)`
has already run — **corrects an earlier claim** (2026-08-27 source-doc
pass) that this method bypasses that Lerp; confirmed via the real call
site that it doesn't, it blends further on top of the already-Lerp'd cop.

```csharp
void Aero_Rocket.ApplyParachuteDrag(ref float force, ref Vector2 cop)
{
    foreach (ParachuteModule chute in rocket.partHolder.GetModules<ParachuteModule>())
    {
        if (chute.targetState.Value != 1f && chute.targetState.Value != 2f)
            continue;   // 0 = stowed, contributes nothing

        Double2 chuteVel = WorldView.ToGlobalVelocity(
            rb2d.GetPointVelocity(chute.parachute.transform.position));
        float chuteDrag = (float)chuteVel.sqrMagnitude * chute.drag.Evaluate(chute.state.Value);

        cop = (cop * force + (Vector2)chute.parachute.transform.position * chuteDrag)
              / (force + chuteDrag);
        force = force + chuteDrag;
    }
}
```

`ParachuteModule` fields involved: `state`/`targetState`
(`Float_Reference`, no named enum — `targetState` 1/2 inferred from the
adjacent `deploySound_Partial`/`deploySound_Fully` fields as
partial/full deployment, 0 presumably stowed), `drag`
(`AnimationCurve`, keyed by `state.Value` — confirms "partial deployment
is a curve lookup" exactly), `parachute` (`Transform`, the chute's own
world position).

**`rb2d.GetPointVelocity` is genuinely rotation-aware** — true local
velocity at the chute's position (bulk + ω×r). This is the one place in
the entire confirmed aero/torque chain that accounts for the craft's
spin; everywhere else (§C1.4's `CalculateDragForce`, §C1.5's
`ApplyForce`, §B1.10's gimbal chain) uses a single whole-craft
`location.velocity` with zero ω-dependence.

**`chuteDrag` carries no density term of its own** — it's added
directly into the shared pre-density `force` scalar (the same `force`
as §C1.5's `f = dragArea * 1.5f * speedSq`, before direction/density are
applied). Density gets multiplied in exactly once, uniformly, on the
combined total after this method returns — so the chute's contribution
is density-scaled indirectly, not explicitly. A reimplementation that
multiplies `chuteDrag` by density itself before adding it in would
double-apply density to the chute's share.

**Multiple deployed chutes compound sequentially, not independently**
— each loop iteration's weighted-average `cop` blend uses `force` as
updated by the *previous* chute in the same call, not the original
pre-parachute value. This is an ordinary incremental weighted-position
update (same shape as an incremental center-of-mass computation), not a
batch average.

Not yet live-validated — no probe support yet either (`aerotorque`/
`computed:aeroTorque` explicitly do NOT replicate this path, per their
own caveat above). Next step for either: extend the probe to read
`ParachuteModule.state`/`targetState` and replicate this exact
compounding logic, then a real flight with a deployed chute comparing
predicted vs. real force/torque.

---

## D1. Heat and destruction

`sfs_physics_reference.md` §5 lists this as open: *"one real data point
(peak 410.8 °C right as `partCount` began dropping), no formula read from
code, no per-part temperature breakdown."*

**The whole chain is now read from IL** — temperature formula, absorption,
dissipation, the destruction threshold, and the destruction path. The
410.8 °C observation is explained exactly: the threshold for a default
part is **412 °C**.

### D1.0 Type layout — `Part` IS a `HeatModuleBase`

**[CONFIRMED]** — `Part` @236080, `HeatModuleBase` @218451,
`HeatModule` @273416.

```
abstract SFS.World.Drag.HeatModuleBase                     @218451
  ├── SFS.Parts.Part                : HeatModuleBase       @236080
  └── SFS.Parts.Modules.HeatModule  : HeatModuleBase       @273416
```

`SFS.Parts.Part` **extends `SFS.World.Drag.HeatModuleBase`** and
implements `SFS.World.Rocket/INJ_Rocket`. This is not incidental — it
means a part with no dedicated heat module acts as its own heat owner.

`HeatModuleBase` contract — one field, nine abstract members. All the
state is virtual, so the backing storage differs per subclass:

```
public Valid valid                                   (the only real field)

public abstract string Name          { get; }        @218485
public abstract bool   IsHeatShield  { get; }        @218492
public abstract float  Temperature   { get; set; }   @218499 / @218506
public abstract int    LastAppliedIndex { get; set; }@218513 / @218520
public abstract float  ExposedSurface  { get; set; } @218527 / @218534
public abstract float  HeatTolerance { get; }        @218541
public abstract void   OnOverheat(bool breakup)      @218548
```

**Storage differs between the two implementations, and this matters:**

| Member | `Part` | `HeatModule` |
|---|---|---|
| `Temperature` | plain `public float temperature` field | `Float_Reference temperature` (**wrapped**) |
| `IsHeatShield` | hardcoded **`false`** @237057 | `public bool isHeatShield` field |
| `HeatTolerance` | hardcoded **`GetHeatTolerance(Low)` = 400** @237151 | `GetHeatTolerance(this.heatTolerance)` @273583 |
| `OnOverheat` | `this.OnOverheat(this, breakup)` @237163 | `part.OnOverheat(this, breakup)` @273596 |

So an ordinary part is **always tolerance 400 and never a heat shield**.
Only a part carrying a `HeatModule` can have `Mid`/`High` tolerance or
heat-shield status.

**Which one owns a surface [PARTIAL]:** `SurfaceData.heatModule` is
assigned once in `SurfaceData.Start()` @268922:

```csharp
heatModule = Component_Utility.GetComponentInParentTree<HeatModuleBase>(transform);
```

It walks up the transform tree for the nearest `HeatModuleBase`. Because
`Part` is itself one, the answer is "the `HeatModule` if the part has
one, otherwise the `Part`" — but when both components sit on the same
GameObject the winner depends on Unity component order, which the IL does
not determine. **[OPEN]**, and settleable live by dumping
`Surface.owner.GetType()` per part.

> **Tooling bug this implies [PARTIAL].** `SFSProbe.cs`'s `GetHeatState`
> reads `Get(part, "temperature")` — the plain `Part.temperature` field —
> for every part. For any part whose surfaces are owned by a `HeatModule`
> instead, the real temperature lives in that module's `Float_Reference`
> and `Part.temperature` is never written. The rocket-wide max would then
> silently under-report. Worth checking before trusting heat telemetry;
> the fix is to read `Surface.owner`'s `Temperature` property, or to
> check both.

Enums, **[CONFIRMED]**:

```
SFS.World.Drag.HeatTolerance   @217798 : Low = 0, Mid = 1, High = 2
SFS.World.DestructionReason    @192046 : TerrainCollision = 0, WaterCollision = 1,
                                         RocketCollision = 2, Overheat = 3, Intentional = 4
```

### D1.1 Heat tolerance values — the destruction thresholds

**[CONFIRMED]** — `AeroModule.GetHeatTolerance(HeatTolerance)` @216396,
a plain `switch`:

```csharp
public static float GetHeatTolerance(HeatTolerance a) => a switch {
    HeatTolerance.Low  => 400f,
    HeatTolerance.Mid  => 1000f,
    HeatTolerance.High => 6000f,
    _                  => 0f,
};
```

Destruction fires at `Temperature > HeatTolerance * 1.03f` (§D1.3), so:

| Tolerance | Value | **Actual break temperature** |
|---|---|---|
| `Low` (default for any plain `Part`) | 400 | **412.0** |
| `Mid` | 1000 | **1030.0** |
| `High` | 6000 | **6180.0** |

**This resolves the open data point.** The project's single observation
was 410.8 °C at the moment `partCount` began dropping — against a
computed threshold of 412.0 for a default part. The "~400 °C community
claim" was the tolerance constant, not the break point; the 3% margin
accounts for the rest.

### D1.2 The temperature formula

**[CONFIRMED]** — the air temperature a rocket sees is **global**, not
per-part. Entry point:

```
public static void AeroModule.GetTemperatureAndShockwave(
    Location location, out float Q, out float shockOpacity, out float temperature)   @216283
```

Public, static, takes only a `Location` — directly callable.

```csharp
AeroData aeroData = GameManager.main.aeroData;

// Debug override path -- ignores physics entirely
if (aeroData.testShock || aeroData.testReentry) {
    Q = 0f;
    shockOpacity = aeroData.testShock ? aeroData.shockOpacity / 100f : 0f;
    temperature  = aeroData.testReentry
        ? aeroData.reentryPercent / (100f - aeroData.reentryPercent) * 3000f : 0f;
    return;
}

aeroData.Formula.GetEverything(
    location.velocity.magnitude,
    location.VerticalVelocity,
    location.planet.GetAtmosphericDensity(location.Height),
    location.planet.data.atmospherePhysics.minHeatingVelocityMultiplier,
    location.planet.data.atmospherePhysics.shockwaveIntensity,
    out Q, out shockOpacity, out temperature, out _);
```

The `testShock` / `testReentry` branch is a developer override on
`AeroData` that produces temperatures with no relation to flight state —
check it is false before trusting a reading.

**`AeroFormula`** @23603 is a 4-field struct, reached via
`GameManager.main.aeroData.Formula` →
`AeroData.formulaHolder.formula` (`TemperatureTest.formula` @26477):

```
public float velPow, densityPow, tempOffset, m
```

**[OPEN] — these four coefficients are serialized Unity data, not IL
literals.** They must be read live. Per the project's data-trust rule,
do not assume values for them.

**Where to read them** *(added while writing §E5.3)*:
`GameManager.main.aeroData` is a serialized `AeroData` field on the
world-scene `GameManager` singleton, and it is what supplies these. So
the read is `GameManager.main.aeroData` → the relevant `AeroFormula` →
these four fields, all reachable from the probe with no new plumbing.
The `AeroData` type's own layout is **[PARTIAL]** — not read — so the
exact path from `aeroData` to an `AeroFormula` still needs one live
introspection pass.

`GetEverything` @23612:

```csharp
Q = GetQ(velocity, density);                              // = (float)(v*v*density)
temperature = GetTemperature(velocity, velocity_Y, density,
    startHeatingVelocityMultiplier
      * Base.worldBase.settings.difficulty.MinHeatVelocityMultiplier
      * 250f);
shockOpacity = GetShockOpacity(Q, (float)velocity, (float)density, shockwaveM, temperature, out pure);
```

`GetTemperature` @23756, the core — **[CONFIRMED]**, full body:

```csharp
private float GetTemperature(double velocity, double velocity_Y, double density, float minHeatVelocity)
{
    float hvm = Base.worldBase.settings.difficulty.HeatVelocityMultiplier;
    velocity        /= hvm;
    velocity_Y      /= hvm;
    minHeatVelocity /= hvm;

    // Ascending? discount some speed -- climbing out heats less than falling in.
    if (velocity_Y > 0.0)
        velocity -= Math.Min(velocity_Y * 2.5, velocity * 0.5);

    float t = (float)(Math.Pow(velocity, velPow) * Math.Pow(density, 1f / densityPow)) / m;

    t += t * (float)(tempOffset * (velocity_Y > 0.0
                                    ? Math.Min(velocity_Y / velocity * 2.0, 0.4)
                                    : 0.0)
                     + 0.2);

    // Hard cap tied to how far above the heating-onset speed you are
    float cap = ((float)velocity - minHeatVelocity) * 6f;
    if (t > cap) t = cap;

    // Soft knee above 2000
    if (t > 2000f) t = 2000f + (t - 2000f) / 1.5f;

    return t > 0f ? t : 0f;
}
```

Constants confirmed as literals: `2.5`, `0.5`, `0.2`, `0.4`, `2.0`, `6f`,
`2000f`, `1.5f`, and the `250f` in `GetEverything`.

`GetIntensity(value, halfPoint) = value / (value + halfPoint)` @216381 —
a saturating curve, used for visuals.

### D1.3 `HeatManager` — absorption, destruction

**[CONFIRMED]** — @217811. Two literal rates:

```
private const float AbsorptionRate  = 0.02f;
private const float DissipationRate = 0.01f;
private List<HeatModuleBase> heated;
```

`ApplyHeat(List<Surface> exposedSurfaces, float temperature, int frameIndex)`
@217819, full body:

```csharp
float absorb = 0.02f * WorldTime.FixedDeltaTime;

// 1. drop surfaces whose Valid token has been cleared
for (int i = exposedSurfaces.Count - 1; i >= 0; i--)
    if (!exposedSurfaces[i].valid.valid) {
        exposedSurfaces.RemoveAt(i);
        AnalyticsUtility.SendEvent("Heat_Manager_Save_v2");
    }

// 2. accumulate exposed width per owner (x-extent in velocity-aligned space)
foreach (Surface s in exposedSurfaces)
    s.owner.ExposedSurface += (s.line.end.x - s.line.start.x);

var overheated = new List<HeatModuleBase>();

// 3. apply, at most once per module per frame
foreach (Surface s in exposedSurfaces) {
    HeatModuleBase m = s.owner;
    if (m.LastAppliedIndex == frameIndex) continue;
    if (float.IsNegativeInfinity(m.Temperature)) { m.Temperature = 0f; heated.Add(m); }

    float delta = temperature - m.Temperature;
    if (delta <= 0f) continue;                       // ApplyHeat never cools

    float surfaceFactor = 1f + Mathf.Log10(m.ExposedSurface + 1f);
    float d = (delta < 1000f) ? delta : (delta * delta / 1000f);   // superlinear above 1000

    m.Temperature += surfaceFactor * d * absorb;
    m.LastAppliedIndex = frameIndex;

    if (m.Temperature > m.HeatTolerance * 1.03f
        && !SandboxSettings.main.settings.noHeatDamage
        && WorldTime.main.realtimePhysics.Value
        && !overheated.Contains(m))
        overheated.Add(m);
}

// 4. reset the accumulator
foreach (Surface s in exposedSurfaces) s.owner.ExposedSurface = 0f;

// 5. destroy
foreach (HeatModuleBase m in overheated) m.OnOverheat(true);
```

Five things worth stating plainly:

1. **Destruction threshold is `Temperature > HeatTolerance * 1.03f`.**
2. **Parts cannot break during timewarp.** Destruction is gated on
   `WorldTime.main.realtimePhysics.Value`. Heat still *accumulates*
   under warp; it just cannot kill. A rocket that survives reentry under
   warp and dies on exiting warp is expected behaviour, not a glitch.
3. **`SandboxSettings.main.settings.noHeatDamage`** disables destruction
   while leaving heating — the heat analogue of `noAtmosphericDrag`.
4. **Heating rate scales with `1 + log10(exposedWidth + 1)`**, i.e. very
   weakly with size. Exposed width is the x-extent in velocity-aligned
   space, summed across all that module's exposed segments.
5. **Above a 1000° gap the absorption goes quadratic** (`delta²/1000`),
   so heating accelerates sharply in a fast reentry.

`DissipateHeat(int frameIndex)` @218066, called every `FixedUpdate` from
`AeroModule.FixedUpdate` regardless of atmosphere:

```csharp
float rate  = 0.01f * WorldTime.FixedDeltaTime;
float floor = 10f   * WorldTime.FixedDeltaTime;
for (int i = heated.Count - 1; i >= 0; i--) {
    HeatModuleBase m = heated[i];
    if (m.LastAppliedIndex == frameIndex) continue;    // heated this frame -- don't cool
    float t = m.Temperature;
    if (t >= 0f) m.Temperature -= (floor + t * rate);  // constant floor + proportional
    if (m.Temperature <= 0f) {
        m.Temperature = float.PositiveInfinity;        // ldc.r4 (00 00 80 7f)
        heated.RemoveAt(i);
    }
}
```

Cooling is `10·dt + 0.01·T·dt` per tick — a constant floor plus a
proportional term.

> **Apparent sign inconsistency [OPEN] — reported, not diagnosed.**
> `DissipateHeat` writes **positive** infinity when a module finishes
> cooling (`ldc.r4 (00 00 80 7f)` = `0x7F800000`), but both readers test
> for **negative** infinity: `ApplyHeat` @217923 calls
> `float32::IsNegativeInfinity`, and `HeatPart` @218292 tests
> `IsNegativeInfinity || IsNaN`. There is no `IsPositiveInfinity` call
> anywhere in `HeatManager`. Taken literally, a module that cools to zero
> is never re-initialised: `ApplyHeat` would compute
> `delta = temperature − (+∞) = −∞ ≤ 0` and skip it forever, while
> `HeatPart` would add to `+∞` and immediately exceed any tolerance.
> **I have not verified that modules actually reach `Temperature ≤ 0` in
> practice**, and the whole question is empirically testable — read
> `Surface.owner.Temperature` across a heat-then-cool cycle. Do not build
> on this either way until it is tested; it is recorded because it would
> materially change any heat model.
>
> **Later evidence (§D5.2) shifts the balance.** `PartSave.temperature`'s
> field initialiser is also `+∞`, which says `+∞` — not `−∞` — is the
> game's "not heated" sentinel. On that reading `DissipateHeat` is
> correct and the two `IsNegativeInfinity` tests are the bug. Still
> **[OPEN]**: it remains a code reading, not a measurement.

Remaining `HeatManager` members, **[PARTIAL]** (signatures confirmed,
bodies not read):

```
public void OnSetParts(Part[] newParts)                          @218145
public List<HeatModuleBase> GetMostHeatedModules(int count)       @218227
public void HeatPart(HeatModuleBase a)                            @218292   (body read)
```

`HeatPart` @218292 is the **non-aerodynamic** heating path — it adds a
flat `150 * Time.fixedDeltaTime` per call and then runs the same
tolerance test, calling `OnOverheat(false)` (note: `false`, not `true`).
Note it uses `Time.fixedDeltaTime`, **not** `WorldTime.FixedDeltaTime`
like `ApplyHeat`/`DissipateHeat` — a different clock. **[OPEN]** which
callers use it.

`GetMostHeatedModules` uses two local functions,
`g__GetTargetIndex|6_0` @218363 and `g__GetHeatScore|6_1` @218408 —
**[OPEN]**, relevant only to the UI temperature bar.

### D1.4 The destruction path

**[CONFIRMED]** — `Part.OnOverheat(HeatModuleBase, bool)` @237177.

```csharp
public void OnOverheat(HeatModuleBase module, bool breakup)
{
    List<PartJoint> joints = Rocket.jointsGroup.GetConnectedJoints(this);

    if (breakup && joints.Count > 0 && !module.IsHeatShield)
    {
        // BREAK OFF rather than destroy
        Rocket rocket = Rocket;
        JointGroup.DestroyJoint(joints[0], Rocket, out bool split, out Rocket newRocket);
        EffectManager.CreatePartOverheatEffect(
            transform.TransformPoint(centerOfMass.Value), mass.Value + ...);
        if (split) {
            rocket.EnableCollisionImmunity(1.5f);
            newRocket.EnableCollisionImmunity(1.5f);
            if (rocket.isPlayer)
                Rocket.SetPlayerToBestControllable(new[] { rocket, newRocket });
        }
        module.Temperature *= 0.8f;     // cools 20% after shedding the joint
        return;
    }

    // otherwise: full destruction (falls through to the same work as DestroyPart)
    EffectManager.CreateExplosion(transform.TransformPoint(centerOfMass.Value),
                                  mass.Value * 2f + 0.5f);
    onPartDestroyed?.Invoke(this);  onPartDestroyed = null;
    JointGroup.OnPartDestroyed(this, Rocket, DestructionReason.Overheat);
    Destroy(gameObject);
}
```

**Overheating does not destroy a part outright while it still has
joints.** It destroys **one joint** (`joints[0]`), sheds that connection,
and cools the module by 20%. Only a jointless part — or a heat-shield
module, or `breakup == false` — is actually destroyed. This is why part
count drops gradually rather than all at once during a bad reentry, and
it means a single overheat event can split the rocket into two
independently-tracked `Rocket` objects, with 1.5 s of mutual collision
immunity.

Related, **[CONFIRMED]** signature:

```
public void Part.DestroyPart(bool createExplosion, bool updateJoints, DestructionReason reason)  @237290
```

Explosion size is `mass * 2 + 0.5`.

### D1.5 Difficulty constants — decoded from the static blobs

**[CONFIRMED]** — `SFS.WorldBase.Difficulty` @146044. The static arrays
are initialised via `RuntimeHelpers.InitializeArray` from
`<PrivateImplementationDetails>` blobs; the byte arrays were decoded from
the `.data` section of the dump. All are indexed by
`DifficultyType` — **`Normal = 0, Hard = 1, Realistic = 2`**, confirmed
from the nested enum and from getters of the form
`array[this.difficulty]`.

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
`ispMultiplier (Normal) = 1.0000`** — measured empirically to 0.002%,
and now read as a literal from code.

Accessors: `MaxPhysicsTimewarpIndex`, `IspMultiplier`,
`DryMassMultiplier`, `EngineMassMultiplier`, `AltitudeMilestones`,
`MinHeatVelocityMultiplier`, `HeatVelocityMultiplier`, plus static
`Difficulty.Normal` / `.Hard` / `.Realistic`.

> **Note for §D4 / the physics reference:** `Atmosphere_Physics`
> @200297 carries `Dictionary<DifficultyType, double> curveScale` and
> `heightDifficultyScale` — **atmosphere density and height scale with
> difficulty**. The Earth constants recorded in
> `sfs_physics_reference.md` §1.1 (`ρ0 = 0.005`, `curve = 10`,
> `AtmosphereHeightPhysics = 30,000`) are therefore only valid for the
> difficulty they were measured on. Full field list: `height`, `density`,
> `curve`, `curveScale`, `parachuteMultiplier`, `upperAtmosphere`,
> `heightDifficultyScale`, `shockwaveIntensity`,
> `minHeatingVelocityMultiplier`.

### D1.6 Reflection recipe

**[UNTESTED-LIVE]** — nothing below has been run against the game.

Global air temperature, no rocket needed beyond a `Location`:

```csharp
Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
object location = Unwrap(Get(ActiveRocket(), "location"));

MethodInfo m = aeroModuleType.GetMethod("GetTemperatureAndShockwave",
    BindingFlags.Public | BindingFlags.Static);          // no overloads -- plain lookup is safe
object[] args = new object[] { location, 0f, 0f, 0f };   // out params
m.Invoke(null, args);
float Q            = (float)args[1];
float shockOpacity = (float)args[2];
float temperature  = (float)args[3];
```

Per-part temperature — read through `Surface.owner`, **not**
`Part.temperature` (§D1.0):

```csharp
// owner is a HeatModuleBase: either the Part itself or its HeatModule
object owner = Get(surface, "owner");
float temp   = ToF(Get(owner, "Temperature"));       // property, works on both subclasses
float tol    = ToF(Get(owner, "HeatTolerance"));     // 400 / 1000 / 6000
bool  shield = ToB(Get(owner, "IsHeatShield"));
string name  = (string)Get(owner, "Name");
bool  willBreak = temp > tol * 1.03f;
```

`Get` reads properties as well as fields, so the virtual
`Temperature` / `HeatTolerance` / `IsHeatShield` resolve correctly for
either subclass without a type test.

Gotchas:

- `HeatModule.temperature` is a **`Float_Reference`** — going at the
  field directly needs `GetWrapped`. The `Temperature` **property**
  avoids this; prefer it.
- `Part.temperature` is a plain `float` field and is **not** the
  authoritative value when a `HeatModule` owns the surfaces.
- `+∞` / `−∞` are sentinel values, not real temperatures (§D1.3).
- Check `SandboxSettings.main.settings.noHeatDamage` and
  `WorldTime.main.realtimePhysics.Value` before predicting destruction.
- Check `aeroData.testShock` / `testReentry` before trusting a
  temperature.

### D1.7 Status summary

| Item | Status |
|---|---|
| `Part : HeatModuleBase` | **[CONFIRMED]** |
| Tolerance values 400 / 1000 / 6000 | **[CONFIRMED]** |
| Break threshold `> tolerance × 1.03` → **412 °C** default | **[CONFIRMED]** — explains the 410.8 °C data point |
| Plain `Part` is always `Low` tolerance, never a heat shield | **[CONFIRMED]** |
| `GetTemperature` formula and its literal constants | **[CONFIRMED]** |
| `AeroFormula` coefficients `velPow`/`densityPow`/`tempOffset`/`m` | **[OPEN]** (values) — serialized data, must be read live; **location [CONFIRMED]**: `GameManager.main.aeroData`, §E5.3 |
| Absorption `0.02`, dissipation `0.01`, cooling floor `10·dt` | **[CONFIRMED]** |
| `1 + log10(exposedWidth+1)` scaling; quadratic above Δ1000 | **[CONFIRMED]** |
| No destruction during timewarp | **[CONFIRMED]** |
| Overheat breaks a **joint** first, destroys only jointless parts | **[CONFIRMED]** |
| Difficulty constant tables | **[CONFIRMED]** — decoded from `.data` blobs |
| `+∞` vs `IsNegativeInfinity` mismatch | **[OPEN]** — reported, needs a live test |
| Which `HeatModuleBase` owns a surface when both are on one GameObject | **[OPEN]** |
| `GetShockOpacity`, `GetMostHeatedModules`, `OnSetParts` bodies | **[OPEN]** — visuals/UI only |
| Probe `GetHeatState` may under-report | **[PARTIAL]** — needs a live check |

---

## D2. Engines, thrust, and multi-engine behaviour

`sfs_physics_reference.md` §5 lists multi-engine rockets as untested, and
`high_level_checklist.md` carries three confirmed-broken tooling bugs
around thrust telemetry. Both are addressed here.

### D2.0 The multi-engine answer: there is no summation

**[CONFIRMED]** — `EngineModule.FixedUpdate()` @261841, full body.

```csharp
private void FixedUpdate()
{
    if (Rb2d == null) return;

    Vector2 localForce = thrustNormal.Value * (thrust.Value * 9.8f * throttle_Out.Value);

    Vector2 worldForce = Base.worldBase.AllowsCheats
        ? (Vector2)transform.TransformVector((Vector3)localForce)          // scale-aware
        : Transform_Utility.TransformVectorUnscaled(transform, localForce);

    Vector2 worldPos = Rb2d.GetRelativePoint(
        Transform_Utility.LocalToLocalPoint(transform, Rb2d, thrustPosition.Value));

    Rb2d.AddForceAtPosition(worldForce, worldPos, ForceMode2D.Force);
    PositionFlameHitbox();
}
```

**Each engine runs its own `FixedUpdate` and applies its own force at its
own position.** Nothing anywhere sums engine thrust. "Multi-engine
behaviour" is just Unity's `Rigidbody2D` accumulating N independent
`AddForceAtPosition` calls, which is also where off-axis engine torque
comes from for free.

Consequences for any model of this:

- Total thrust is `Σ thrustNormal·thrust·9.8·throttle_Out` over engines
  **with `Rb2d != null`** — but each term is a *vector* applied at a
  *distinct point*, so a scalar sum is only valid when every engine is
  parallel and through the CoM.
- Torque from asymmetric engines is emergent, not modelled separately.
- Force is applied at `thrustPosition.Value` (a `Composed_Vector2`),
  **not** the part origin.
- This confirms `sfs_physics_reference.md` §2.2's
  `F = thrustNormal · thrust · 9.8 · throttle_Out` exactly, and shows the
  `9.8` is a literal `ldc.r4` in this method.

**Undocumented gotcha:** `Base.worldBase.AllowsCheats` selects a
**different transform function**. With cheats allowed the game uses
scale-aware `Transform.TransformVector`; otherwise
`Transform_Utility.TransformVectorUnscaled`. For a part with non-unit
`lossyScale` these give different thrust. A cheats-enabled world is not
physically identical to a normal one even with no cheat active.

### D2.1 `EngineModule` field layout

**[CONFIRMED]** — @261221. Wrapper types matter; see §A3.

```
public Composed_Float    thrust            (tonnes-force)
public Composed_Vector2  thrustNormal      direction, part-local
public Composed_Float    ISP
public Composed_Vector2  thrustPosition    application point, part-local
public FlowModule        source            fuel source
public bool              hasGimbal
public Bool_Reference    gimbalOn
public MoveModule        gimbal
public Bool_Reference    engineOn
public Float_Reference   throttle_Out      <- the actual per-engine throttle
public Bool_Reference    heatOn
public GameObject        heatHolder
private Vector3          originalPosition
private Rocket           Rocket   { get; set; }      (INJ_Rocket)
private bool             IsPlayer { get; set; }
private Rigidbody2D      Rb2d     { get; set; }
private readonly Float_Local throttle_Input          <- INJ_Throttle sink
private readonly Float_Local turnAxis_Input          <- INJ_TurnAxisTorque sink
public float             oldMass
```

`throttle_Input` and `turnAxis_Input` are written by the injection
interfaces `Rocket.INJ_Throttle.set_Throttle` @261340 and
`Rocket.INJ_TurnAxisTorque.set_TurnAxis` @261355 — explicit interface
implementations, so they are **private** and only reachable via the
interface. Read the `Float_Local` fields instead.

### D2.2 The control chain, end to end

**[CONFIRMED]** — every step read from IL.

```
Throttle.throttlePercent (Float_Local)   +   Throttle.throttleOn (Bool_Local)
        │  Throttle.UpdateThrottle()  @184711
        ▼
Throttle.output_Throttle = throttleOn ? throttlePercent : 0
        │  (injected into each engine as throttle_Input)
        ▼
EngineModule.throttle_Input  +  EngineModule.engineOn
        │  RecalculateEngineThrottle()  @261752
        ▼
EngineModule.throttle_Out = engineOn ? throttle_Input : 0
        │
        ├──▶ FixedUpdate()          -> thrust force
        ├──▶ RecalculateMassFlow()  -> fuel consumption
        └──▶ RecalculateGimbal()    -> gimbal deflection
```

`Throttle` @184675 has **three** fields, not two:

```
public Bool_Local  throttleOn
public Float_Local throttlePercent
public Float_Local output_Throttle      <- authoritative commanded throttle
```

`UpdateThrottle()` @184711:
`output_Throttle.Value = throttleOn.Value ? throttlePercent.Value : 0f`.

> **`output_Throttle` is the value the probe should be logging** and
> currently does not — it reads `throttlePercent` and `throttleOn`
> separately and reconstructs. Equivalent in principle, but
> `output_Throttle` is the single value the engines actually receive.

`RecalculateEngineThrottle()` @261752:
`throttle_Out.Value = engineOn.Value ? throttle_Input.Value : 0f`.

This is the IL confirmation of `sfs_physics_reference.md` §2.2's
three-layer control model (amount / per-engine / master) and of "throttle
response is instant, no ramp" — there is no interpolation anywhere in
either method.

### D2.3 Fuel flow — confirmed, with an undocumented factor

**[CONFIRMED]** — `RecalculateMassFlow()` @261680.

```csharp
float scale = transform.TransformVector((Vector3)thrustNormal.Value).magnitude;
source.SetMassFlow(
    thrust.Value * scale * throttle_Out.Value
    / (ISP.Value * (float)Base.worldBase.settings.difficulty.IspMultiplier));
```

Matches `sfs_physics_reference.md` §1.3's
`thrust · throttle / (ISP · ispMultiplier)` — **plus a `scale` term that
is not in the doc**: the magnitude of `thrustNormal` after the part's
world transform. For an unscaled part with a unit-length `thrustNormal`
this is 1.0, which is why the empirical check came out at 0.002% error.
For a **scaled** part it is not 1.0 and the documented formula is wrong.

`IspMultiplier` is 1.0 / 1.0 / 1.5 by difficulty (§D1.5).

`CheckOutOfFuel()` @261727 — **engines shut themselves off**:

```csharp
if (engineOn.Value && !HasFuel(Logger)) engineOn.Value = false;
```

So `engineOn` going false is not necessarily a player action; fuel
exhaustion produces the same observable.

### D2.4 Gimbal

**[CONFIRMED]** — `RecalculateGimbal()` @261776.

```csharp
if (!hasGimbal || !gimbalOn.Value) return;
gimbal.targetTime.Value = throttle_Out.Value > 0f
    ? turnAxis_Input.Value * Transform_Utility.RotationDirection(transform)
    : 0f;
```

A gimbal only deflects while `throttle_Out > 0`. `RotationDirection`
handles mirrored parts. Deflection is expressed as a `targetTime` on a
`MoveModule`, so gimbal geometry is an animation parameter, not an angle
— the resulting thrust direction change shows up through
`thrustNormal`, which is a `Composed_Vector2` recomputed from the moved
transform.

### D2.5 `BoosterModule` — SRBs are a separate code path

**[CONFIRMED]** — @259149. This matters because **anything scanning for
`EngineModule` misses solid boosters entirely.**

```
public ResourceType     resourceType
public Composed_Float   ISP
public Composed_Vector2 thrustVector          <- NOT "thrustNormal"
public Composed_Vector2 thrustPosition
public Composed_Float   wetMass, dryMassPercent
public Float_Reference  fuelPercent           <- NOT a ResourceModule
public Bool_Reference   boosterPrimed         <- NOT "engineOn"
public Float_Reference  throttle_Out
public Double_Reference mass_Out
public SurfaceData      surfaceForCover
private float           newIgnitionTime
private Float_Local     throttle_Input
private Part            part
private float ThrustDuration { get; }         @259223
```

Different field names for the same concepts: `thrustVector` not
`thrustNormal`, `boosterPrimed` not `engineOn`, and fuel as a scalar
`fuelPercent` rather than a `ResourceModule`.

`FixedUpdate()` @259801 — fuel burn:

```csharp
if (Rocket == null) return;
if (!SandboxSettings.main.settings.infiniteFuel) {
    fuelPercent.Value -= Time.fixedDeltaTime / ThrustDuration * throttle_Out.Value;
    if (fuelPercent.Value <= 0f) {
        throttle_Out.Value = 0f;
        fuelPercent.Value  = 0f;
        this.enabled = false;              // component disables itself
    }
}
...
```

Note `Time.fixedDeltaTime` (Unity clock), **not**
`WorldTime.FixedDeltaTime` as the heat system uses. Also
`SandboxSettings.main.settings.infiniteFuel` — a third sandbox flag
alongside `noAtmosphericDrag` and `noHeatDamage`.

**[PARTIAL]** — `RecalculateMass()` @259448 and the rest of
`BoosterModule`'s 33 methods were not read.

### D2.6 `TorqueModule`

**[CONFIRMED]** — @265256, three fields, no physics of its own:

```
public Bool_Reference  enabled
public Composed_Float  torque
public bool            showDescription
```

The only non-constructor method is an explicit `I_PartMenu.Draw`. The
torque *application* is not here — it lives in the rotation path
(`sfs_physics_reference.md` §2.4), which sums
`Σ(enabled TorqueModule.torque)`. The probe's `SumEnabledTorque` matches
this shape. **[OPEN]** — the summation call site was not located.

### D2.7 Root-causing the thrust telemetry bugs

`high_level_checklist.md` lists these as confirmed broken:

> - `thrustDirX`/`thrustDirY`/`gimbalOn`/`throttleOut` — never populate
> - `GetEngineDirection()` — only returns the first active engine found

**The second is by design and confirmed** — `GetEngineDirection` returns
on the first `EngineModule` with `engineOn` true. Given §D2.0, a single
engine's direction is not a meaningful summary of a multi-engine rocket
anyway; the fix is to emit a per-engine array, not to pick a better
single engine. It also **skips `BoosterModule` entirely** (§D2.5).

**For the first, the IL rules out the obvious explanations.** All four
field names and every wrapper access in `GetEngineDirection` are correct:

| Probe access | IL says | Verdict |
|---|---|---|
| `Get(mv, "thrustNormal")` | `public Composed_Vector2 thrustNormal` | correct |
| `Get(normal, "x")` / `"y"` | `Composed_Vector2` has **public `Composed_Float x, y` fields** | correct |
| `GetWrapped2(nx)` | `Composed<T>` has a public `Value` property | correct |
| `GetWrapped2(Get(mv,"gimbalOn"))` | `Bool_Reference : ReferenceVariable<bool>`, inherits public `Value` | correct |
| `GetWrapped2(Get(mv,"throttle_Out"))` | `Float_Reference : Double_Reference`, declares `get_Value` | correct |
| `GetWrapped2(Get(mv,"engineOn"))` | as `gimbalOn` | correct |

Lazy initialisation is also not the cause: `Composed<T>.get_Value()`
@278674 calls `CheckInitialize()` first, which computes `GetResult(...)`
on first access. Reading `.Value` is self-initialising.

**So the cause is upstream.** All four keys are emitted inside a single
`if (eng != null)` block (`SFSProbe.cs` ~L772), so they fail *together*
exactly when `GetEngineDirection` returns `null`. That leaves three
candidates, **[OPEN]** between them:

1. `ModuleValues(part)` yields no object with
   `GetType().Name == "EngineModule"`.
2. Every `EngineModule` has `engineOn == false` at sample time — which
   is **correct behaviour** if telemetry was sampled outside a burn, and
   is also what `CheckOutOfFuel` (§D2.3) produces on fuel exhaustion.
3. An exception is thrown and silently swallowed — `GetEngineDirection`
   ends in a bare `catch { }` with no logging.

Candidate 3 is what makes this hard to diagnose, and is worth fixing
first regardless: log the exception, and log which of the three branches
was taken. That converts an unexplained absence into a one-run answer.

> Note the same bare-`catch`-returns-null pattern appears in
> `GetHeatState`, `InvokeReturn`, and `Get` — §A1 flags it. The newer
> `InvokeStatic` helper logs instead, and is the better model.

### D2.8 Status summary

| Item | Status |
|---|---|
| No thrust summation — per-engine `AddForceAtPosition` | **[CONFIRMED]** |
| `F = thrustNormal · thrust · 9.8 · throttle_Out` | **[CONFIRMED]** — literal `9.8` in `FixedUpdate` |
| Force applied at `thrustPosition`, not part origin | **[CONFIRMED]** |
| `AllowsCheats` switches scaled/unscaled transform | **[CONFIRMED]** — newly documented |
| `throttle_Out = engineOn ? throttle_Input : 0`, no ramp | **[CONFIRMED]** |
| `Throttle.output_Throttle` is the authoritative command | **[CONFIRMED]** — probe doesn't log it |
| Fuel flow `thrust·scale·throttle / (ISP·IspMultiplier)` | **[CONFIRMED]** — `scale` term newly documented |
| Engines self-disable on fuel exhaustion | **[CONFIRMED]** |
| Gimbal deflects only while `throttle_Out > 0` | **[CONFIRMED]** |
| `BoosterModule` is a separate path with different field names | **[CONFIRMED]** |
| `GetEngineDirection` single-engine limit | **[CONFIRMED]** by design; also misses boosters |
| Why `thrustDirX`/etc. never populate | **[OPEN]** — narrowed to `GetEngineDirection` returning null; naming and wrapper access ruled out |
| Torque summation call site | **[OPEN]** |
| `BoosterModule.RecalculateMass` and remaining methods | **[OPEN]** |

---

## D3. RCS

`sfs_physics_reference.md` §5: *"deliberately unmodeled. Per-thruster
selection logic (`TorqueThrust`/`DirectionThrust` checks) is real and
non-trivial but not replicated; only a firing-count flag exists."*

Both selection methods are now read in full, along with `FixedUpdate`.
The logic is small — about 40 lines of C# equivalent — and the two
angle thresholds are per-part serialized data.

### D3.0 Types

**[CONFIRMED]** — `RcsModule` @263099, `RcsModule/Thruster` @263824.

```
SFS.Parts.Modules.RcsModule
  public float      directionAngleThreshold      <- serialized, per part
  public float      torqueAngleThreshold         <- serialized, per part
  public float      thrust                       (plain float, NOT Composed_Float)
  public float      ISP                          (plain float)
  public List<RcsModule/Thruster> thrusters
  public FlowModule source
  public Vector2    thrustPosition               (plain Vector2, part-local)
  private Rocket    Rocket          { get; set; }
  private bool      IsPlayer        { get; set; }
  private float     TurnAxis        { get; set; }   <- INJ_TurnAxisWheels sink
  private Vector2   DirectionalAxis { get; set; }   <- INJ_DirectionalAxis sink
  private bool      RCS_On          { get; set; }   @263239

SFS.Parts.Modules.RcsModule/Thruster        (NESTED type)
  public Vector2    thrustNormal               part-local direction
  public MoveModule effect                     visual; targetTime 0 or 1
```

**Unlike `EngineModule`, none of the physics fields are wrapped** —
`thrust`, `ISP`, `thrustPosition` are plain fields, so `Get()` returns
usable values directly with no `GetWrapped2`. `TurnAxis` and
`DirectionalAxis` are auto-properties fed by the injection interfaces
`INJ_TurnAxisWheels` and `INJ_DirectionalAxis`.

**Reflection note:** `Thruster` is nested. `FindType` needs a **slash**:
`FindType("SFS.Parts.Modules.RcsModule/Thruster")`. Usually unnecessary —
walk `Get(rcs, "thrusters")` as an `IEnumerable` and read `thrustNormal`
off each element.

### D3.1 `FixedUpdate` — the firing loop

**[CONFIRMED]** — @263482, full body.

```csharp
if (Rocket == null || !RCS_On
    || (Mathf.Abs(TurnAxis) < 0.01f && DirectionalAxis.sqrMagnitude < 0.01))
{
    foreach (Thruster t in thrusters) t.effect.targetTime.Value = 0f;
    source.SetMassFlow(0.0);
    return;
}

Vector2 positionToCoM = Rocket.rb2d.worldCenterOfMass
                      - (Vector2)transform.TransformPoint(thrustPosition);
float   count     = 0f;
Vector2 sumNormal = Vector2.zero;

foreach (Thruster t in thrusters)
{
    Vector2 worldNormal = Transform_Utility.TransformVectorUnscaled(transform, t.thrustNormal);

    bool fire = TorqueThrust(worldNormal, positionToCoM) | DirectionThrust(worldNormal);

    if (fire) { sumNormal += worldNormal; count += 1f; t.effect.targetTime.Value = 1f; }
    else                                               t.effect.targetTime.Value = 0f;
}

if (sumNormal != Vector2.zero)
    Rocket.rb2d.AddForceAtPosition(
        sumNormal * (thrust * count * 9.8f),
        (Vector2)transform.TransformPoint(thrustPosition));

source.SetMassFlow(thrust * count / ISP);
```

Points that matter:

- **Deadzone**: `|TurnAxis| < 0.01` **and** `DirectionalAxis.sqrMagnitude
  < 0.01` together shut the module down and zero its mass flow.
- **Both selection tests always run.** The IL calls `TorqueThrust`, then
  `DirectionThrust`, then `or` — a **non-short-circuiting** bitwise OR.
  A thruster fires if either test passes.
- **The whole module applies one combined force at one point**
  (`thrustPosition`), not one force per thruster — unlike engines
  (§D2.0). Per-thruster geometry only enters through `sumNormal`.
- **Mass flow is `thrust · count / ISP`** — note **no `throttle` term and
  no `IspMultiplier`**, unlike `EngineModule.RecalculateMassFlow`
  (§D2.3). RCS fuel use is not difficulty-scaled.

> **Force magnitude is quadratic in the number of firing thrusters
> [CONFIRMED arithmetic, [OPEN] interpretation].** `sumNormal` is an
> unnormalised **vector sum** over firing thrusters, and it is then
> multiplied by `count` again. For *N* firing thrusters with parallel
> unit normals, `|sumNormal| = N` and the applied force is
> `N · thrust · N · 9.8 = N² · thrust · 9.8`, while mass flow stays
> linear at `thrust · N / ISP`. Taken literally, RCS gets *more
> efficient per unit fuel* the more thrusters fire together. I have read
> the arithmetic correctly (both `mul` opcodes at IL_0192 and IL_0199)
> but have **not** verified the consequence in flight, and non-parallel
> normals partially cancel in the sum. Treat the `N²` as a reading of the
> code, not an established flight fact, until measured.

### D3.2 `TorqueThrust` — rotational selection

**[CONFIRMED]** — @263670, full body.

```csharp
private bool TorqueThrust(Vector2 thrustDirection, Vector2 positionToCenterOfMass)
{
    if (thrustDirection == Vector2.zero || positionToCenterOfMass == Vector2.zero)
        return false;

    // Gate: only fire for near-full input, or to arrest an existing spin
    if (Mathf.Abs(TurnAxis) < 0.95f && Mathf.Abs(Rocket.rb2d.angularVelocity) < 2f)
        return false;

    float angleCCW = Vector2.Angle(thrustDirection, Quaternion.Euler(0, 0,  90f) * positionToCenterOfMass);
    float angleCW  = Vector2.Angle(thrustDirection, Quaternion.Euler(0, 0, -90f) * positionToCenterOfMass);

    if (TurnAxis >  0.1f && angleCCW <= torqueAngleThreshold) return true;
    if (TurnAxis < -0.1f) return angleCW <= torqueAngleThreshold;
    return false;
}
```

**The 0.95 / 2.0 gate is the significant find.** RCS torque thrusters do
**not** respond proportionally to steering input. They fire only when:

- `|TurnAxis| ≥ 0.95` — essentially full deflection — **or**
- `|angularVelocity| ≥ 2` deg/s — i.e. the rocket is already spinning.

The second clause is what makes RCS act as a rotation damper: once
`TurnAxis` returns to zero, thrusters keep firing (subject to the ±0.1
sign test below) until the spin falls under 2 deg/s. That is almost
certainly the mechanism behind any observed RCS "auto-stabilisation".

Direction selection is a 90° rotation of the lever arm: a thruster fires
for counter-clockwise demand if its world thrust direction is within
`torqueAngleThreshold` of `positionToCoM` rotated +90°, and for clockwise
demand of the −90° rotation. Note `positionToCoM` points **from the
module toward** the centre of mass.

The ±0.1 band means `TurnAxis` between −0.1 and +0.1 selects no
thruster, even when the 0.95/2.0 gate passed on angular velocity.

### D3.3 `DirectionThrust` — translational selection

**[CONFIRMED]** — @263758, full body.

```csharp
private bool DirectionThrust(Vector2 thrustDirection)
{
    if (DirectionalAxis == Vector2.zero) return false;
    return Vector2.Angle(thrustDirection, DirectionalAxis) <= directionAngleThreshold;
}
```

Straightforward: fire if the thruster points within
`directionAngleThreshold` degrees of the commanded translation axis.

### D3.4 Enable / disable

**[CONFIRMED]** — `Update_RCS_On()` @263311:

```csharp
if (!RCS_On) return;
I_MsgLogger logger = IsPlayer ? MsgDrawer.main : new MsgNone();
if (!source.CanFlow(logger))
    ToggleRCS(new UsePartData(new UsePartData.SharedData(false), null), false);
```

**RCS switches itself off when its fuel source cannot flow** — the same
self-disabling pattern as `EngineModule.CheckOutOfFuel` (§D2.3). So
`RCS_On` going false is not necessarily a player action.

`RCS_On` is a private property @263239. `ToggleRCS(UsePartData)` @263355
is public; the two-argument form @263369 with `showMsg` is private.

**[OPEN]** — `RCS_On`'s backing store was not traced, so writing it from
the probe is not yet specified. Reading it works via `Get(rcs, "RCS_On")`
(the probe's `Get` reads non-public properties).

### D3.5 Modelling notes

To replicate RCS, per module per tick:

1. Read `RCS_On`, `TurnAxis`, `DirectionalAxis`; apply the 0.01 deadzone.
2. `positionToCoM = rb2d.worldCenterOfMass − transform.TransformPoint(thrustPosition)`.
3. For each thruster: world-transform `thrustNormal` **unscaled**, then
   run both tests and OR them.
4. Force `sumNormal · thrust · count · 9.8` at
   `transform.TransformPoint(thrustPosition)`; mass flow
   `thrust · count / ISP`.

Everything needed is readable; the only per-part unknowns are the two
angle thresholds, which are serialized and must be read live.

The probe currently exposes only `rcsOn` and a firing count
(`CountFiringThrusters`). That count is a reasonable proxy for `count`
above — but note the force depends on `sumNormal` too, which the probe
does not compute.

### D3.6 Status summary

| Item | Status |
|---|---|
| `RcsModule` / `Thruster` field layout, all unwrapped | **[CONFIRMED]** |
| Deadzone `0.01` on both axes | **[CONFIRMED]** |
| Both selection tests always evaluated (non-short-circuit OR) | **[CONFIRMED]** |
| One combined force per module, at `thrustPosition` | **[CONFIRMED]** |
| Torque gate `\|TurnAxis\| ≥ 0.95` **or** `\|angularVelocity\| ≥ 2` | **[CONFIRMED]** — newly documented, explains RCS damping |
| ±0.1 `TurnAxis` sign band | **[CONFIRMED]** |
| `DirectionThrust` angle test | **[CONFIRMED]** |
| Mass flow `thrust·count/ISP`, no throttle, no `IspMultiplier` | **[CONFIRMED]** |
| RCS self-disables when fuel cannot flow | **[CONFIRMED]** |
| Force quadratic in firing-thruster count | **[CONFIRMED-LIVE]** — 2026-08-31, real flight measurement matches predicted magnitude to 0.06% (29.38 real vs 29.4 predicted), median per-tick direction error 6.1°. See D3.8. |
| `directionAngleThreshold` / `torqueAngleThreshold` values | **[CONFIRMED-LIVE]** — read live via `rcsinfo` (v0.44.0) |
| `RCS_On` backing store (for writing it) | **[OPEN]** |

### D3.7 `rcsforce` probe command — force validation tooling

**[CONFIRMED]**, added 2026-08-30 (v0.47.0). Fresh IL re-read of
`RcsModule.FixedUpdate` (RVA 0x65f34) confirmed the exact real-call
sequence matches the D3.1 writeup precisely, including the two
Unity-side calls not previously traced in detail:
`Transform.TransformPoint(Vector3)` (converting the local `thrustPosition`
via `Vector2`'s `op_Implicit` operator first) for `positionToCoM`, and
`Rigidbody2D.worldCenterOfMass`. Both are plain Unity engine calls, not
game-specific logic — confirmed via the exact IL call sequence, not
assumed.

Rather than reimplementing this math, `rcsforce` calls the **real game
functions directly via reflection** for every piece that has one:
`Rigidbody2D.worldCenterOfMass`, `Transform.TransformPoint`,
`Transform_Utility.TransformVectorUnscaled`, and the private
`TorqueThrust`/`DirectionThrust` selection methods themselves (reflection
already supports non-public methods — `InvokeReturn` uses
`BindingFlags.NonPublic`). Only the final vector sum and the
`thrust·count·9.8` scaling are computed in the probe, matching
`FixedUpdate`'s own IL exactly. This sidesteps any risk of a subtly wrong
reimplementation of Unity transform/rotation math.

One implementation note: `Transform.TransformPoint` and `Vector2`'s
`op_Implicit` conversions live in `UnityEngine.CoreModule`, outside this
project's own `Assembly-CSharp.dll` IL dump, and Unity commonly overloads
both (`TransformPoint(Vector3)` vs. `TransformPoint(float,float,float)`).
A plain `GetMethod(name)` call risks `AmbiguousMatchException` there, so
`rcsforce` resolves both by explicit parameter type rather than using the
shared `InvokeReturn` helper for those two calls specifically.
`Transform_Utility.TransformVectorUnscaled` and the two selection methods
are confirmed single-overload within the game's own assembly, so those
use the normal `InvokeReturn` path.

Per `RcsModule`, `rcsforce` reports: `rcsOn`, `turnAxis`, `directionalAxis`,
whether the module hit `FixedUpdate`'s own top-level deadzone gate
(`moduleDeadzoned` — replicated exactly: `!RCS_On || (|TurnAxis|<0.01 &&
DirectionalAxis.sqrMagnitude<0.01)`), the module's world-space
`thrustPosition`, per-thruster world normals and real fire/no-fire
decisions (from the actual `TorqueThrust`/`DirectionThrust` calls), the
resulting `sumNormal`, firing count, and the predicted force vector and
mass flow. Rocket-wide totals and `rocketMass` (`rb2d.mass`) are included
for a straightforward predicted-acceleration comparison against a real
finite-difference measurement from an engines-off flight.

**Still blocked on the same thing as before**: an actual engines-off
test flight to compare `rcsforce`'s predicted force/acceleration against
a real finite-difference measurement of velocity change. The command
itself is tooling-complete; only the flight is outstanding.

### D3.8 Force magnitude/direction — live-validated 2026-08-31

**[CONFIRMED-LIVE]**. Engines-off, RCS-on coast flight (Earth, 81.5-91km
altitude, well clear of the atmosphere, 83s / 4969 samples, `thrOn=false`
throughout). `turnAxis` was purely discrete keyboard input, `{-1, 0, 1}`
only, never analog. Real per-tick acceleration was finite-differenced
from recorded `vx`/`vy`, with gravity (`μ/r²`, `μ` independently
re-derived from a 45.7s quiet no-RCS window on the same flight, `μ ≈
9.67e11`) subtracted out to isolate the RCS contribution.

**Important correction, made honestly rather than silently:** the first
Python re-derivation of the predicted force pooled all 18 thrusters
across all 6 `RcsModule`s into one shared `count` and `sumNormal`. This
is wrong — `FixedUpdate` is an **instance** method, so each of the 6
modules runs its own independent copy with its own local `count` (0-3,
only that module's own 3 thrusters) and `sumNormal`, and each module
applies its own `AddForceAtPosition` call separately. The pooled version
over-predicted `turnAxis<0`'s force by ~6x (176.4 vs the correct 29.4).
The `rcsforce` probe command itself (§D3.7) was already scoped correctly
per-module — only the ad-hoc Python re-derivation had the bug, not the
tooling or the originally-documented IL formula.

**Corrected result**, using real in-flight `rcsforce` readings recovered
from `probe.log` (the live JSON snapshot file only holds the most recent
press, so the summary line — module count and total force — in the log
was what made recovery possible after a later, unrelated `rcsforce` call
overwrote the file):

| | Predicted (`sumNormal·thrust·count·9.8`, summed per-module) | Real (measured) |
|---|---|---|
| `turnAxis<0`, n=350 samples | **29.4** (constant, by design) | **29.38** average — ratio 0.9994 |
| `turnAxis>0`, n=441 samples | **0** (exact cancellation by design) | ~16-30 average, modestly above the ~10 (mean) / ~4.3 (median) noise floor measured on the same flight's quiet no-RCS window |

Per-tick direction error (angle between predicted and real force
vectors, `turnAxis<0` samples): **median 6.1°**, mean pulled up to 32° by
a handful of noisy/transient ticks — plausibly from rapid stick
oscillation (the person reported pressing the opposite key briefly by
accident, and RCS toggling rapidly between +1/-1 at points during the
flight).

**This closes the last open piece of RCS.** The `turnAxis<0` magnitude
match (0.06% off) directly confirms the `count`-scaled force formula
(§D3.1) is correct as originally read from IL — the earlier `[OPEN]`
status was about live validation being outstanding, not any doubt about
the reading itself, and that reading holds up. The `turnAxis>0` case
(predicted exactly zero from geometric cancellation across the two
top-mounted thruster pairs) landing close to, but not exactly at, the
measurement noise floor is consistent with minor real-world imperfection
(float precision, slight CoM drift between the flight and the later
geometry snapshot used for the local-frame derivation) rather than a
modeling gap.

**Process note for future live-snapshot work**: `sfs_probe_rcsforce.json`
(like other on-demand command outputs) only ever holds the most recent
call's result — a later, unrelated call to the same command silently
destroys any earlier live-flight snapshot. `probe.log` retains a
one-line summary (timestamp + the `ProbeMod.Result` text) of every call
ever made, which was enough to recover this flight's real in-flight
readings after the snapshot file itself got overwritten, but only the
summary fields (module count, total force here) survive that way, not
the full per-module/per-thruster JSON breakdown. Read the JSON snapshot
(or the log, if it's already gone) before making any further calls to
the same command, if the current contents might be needed later.

---

## D4. Planets, SOI, atmosphere, terrain

`sfs_physics_reference.md` §5: *"SOI transitions, real terrain shape —
essentially untouched. SOI radii are confirmed for all 40 bodies and the
model is confirmed single-body/patched-conic, but an actual crossing has
never been observed in flight."*

The crossing **mechanism** is now read, and it has a consequence for the
project that observation alone would not have made obvious.

### D4.0 `SFS.WorldBase.Planet`

**[CONFIRMED]** — @146888. Physics-relevant public fields:

```
public string   codeName
public double   mass                <- this is μ (gravitational parameter), NOT kg
public double   SOI                 <- plain public field, metres
public double   maxTerrainHeight
public Planet   parentBody
public Planet[] satellites
public Orbit    orbit
public Trajectory trajectory
public PlanetData data
public int      orbitalDepth, satelliteIndex, commonDenominator, surfaceWavesRepeat
public Landmark[] landmarks
```

Key computed properties:

```
double Radius                   => data.basics.radius                       @146919
double SurfaceArea              => Radius * 2π    (a circumference — 2D game) @146933
double AtmosphereHeightPhysics  => HasAtmospherePhysics ? data.atmospherePhysics.height
                                                        : +∞                @146947
double TimewarpRadius_Ascend / _Descend                                     @146967 / @146997
double OrbitRadius, RewardMultiplier
bool   HasParent, HasAtmospherePhysics, HasAtmosphereVisuals,
       HasFrontClouds, HasRings
```

> **Gotcha [CONFIRMED]:** `AtmosphereHeightPhysics` returns
> **positive infinity** for an airless body (`ldc.r8 (00 00 00 00 00 00
> f0 7f)`), not 0. Any comparison of the form
> `height < planet.AtmosphereHeightPhysics` is therefore **true
> everywhere** on the Moon. `GetAtmosphericDensity` guards separately and
> is safe; ad-hoc checks are not.

### D4.1 Gravity — confirmed

**[CONFIRMED]** — @148021, @148037.

```csharp
public double  GetGravity(double radius)   => mass / (radius * radius);
public Double2 GetGravity(Double2 position) => -position.normalized * (mass / position.sqrMagnitude);
```

Confirms `sfs_physics_reference.md` §2.1 exactly, and confirms that
`Planet.mass` **is** μ rather than a true mass — no `G` appears anywhere.

Two overloads of `GetGravity` — **ambiguous**, added to §A1.1.

### D4.2 Atmospheric density — confirmed, and the difficulty question resolved

**[CONFIRMED]** — `GetAtmosphericDensity(double height)` @148579:

```csharp
if (!data.hasAtmospherePhysics)      return 0.0;
if (height > AtmosphereHeightPhysics) return 0.0;
double c = data.atmospherePhysics.curve;
return (Math.Exp(height / AtmosphereHeightPhysics * -c) - Math.Exp(-c))
       * data.atmospherePhysics.density;
```

Exactly `sfs_physics_reference.md` §2.3's
`ρ(h) = (e^(−curve·h/H) − e^(−curve)) · ρ0`, with the hard cutoff.

**This refines the note in §D1.5.** `GetAtmosphericDensity` reads
`curve`, `density`, and `height` **directly** — it does *not* consult
`curveScale` / `heightDifficultyScale` at call time. Those dictionaries
are applied **once at load**, mutating the `PlanetData` in place:

**[CONFIRMED]** — `Difficulty.ScalePlanetData(PlanetData)` @146246:

```csharp
basics.radius              *= RadiusScale(planet);
basics.gravity             *= GravityScale(planet);
basics.timewarpHeight      *= AtmosphereScale(planet);
atmospherePhysics.height   *= AtmosphereScale(planet);
atmospherePhysics.curve    *= AtmosphereCurveScale(planet);
orbitModule.semiMajorAxis  *= SmaScale(planet);
// + SOI via SoiScale, rings, clouds, gradients, post-processing …
```

Each `*Scale` method (@146485–@146654) looks the planet's own
per-difficulty dictionary up by
`Base.worldBase.settings.difficulty.difficulty`, falling back to
`DefaultRadiusScale` / `DefaultAtmoHeightScale` / `DefaultAtmoCurveScale`
or `1.0`.

So the practical rules are:

- **Values read live from `Planet`/`PlanetData` at runtime are already
  difficulty-scaled** and are correct as-is. No extra scaling to apply.
- **Values read from the planet JSON on disk are unscaled** and are only
  correct for the default difficulty.
- **Radius, gravity, SOI, and semi-major axis all scale too**, not just
  the atmosphere — so §1.1's Earth numbers (radius 314,970, μ, SOI,
  atmosphere height 30,000) are a *difficulty-specific snapshot*, and the
  doc does not record which difficulty they came from.

`Atmosphere_Physics` @200297 full field list, **[CONFIRMED]**:

```
double height, density, curve
Dictionary<DifficultyType,double> curveScale, heightDifficultyScale
double parachuteMultiplier          <- previously undocumented
double upperAtmosphere              <- previously undocumented
float  shockwaveIntensity, minHeatingVelocityMultiplier    (feed §D1.2)
```

`IsInsideAtmosphere(Double2 position)` @148547 — **[PARTIAL]**,
signature only.

### D4.3 SOI — the transition mechanism

**[CONFIRMED]** — the two tests @148626 / @148640:

```csharp
public bool IsOutsideSOI(Double2 position)          // position RELATIVE TO THIS PLANET
    => position.Mag_MoreThan(SOI);

public bool IsInsideSOI(Double2 positionToParent)   // position in the PARENT's frame
    => (positionToParent - orbit.GetLocation(WorldTime.main.worldTime).position)
       .Mag_LessThan(SOI);
```

Note the asymmetry: `IsOutsideSOI` takes a planet-relative position;
`IsInsideSOI` takes a parent-relative one and subtracts the satellite's
own orbital position at the current world time. Passing the wrong frame
silently returns a wrong answer.

**Both have exactly one caller each**, and both are in
`SFS.World.Physics.Update()` @159627 — **[CONFIRMED]** from the body:

```csharp
if (PhysicsObject.PhysicsMode)
{
    location.position.Value = WorldView.ToGlobalPosition(PhysicsObject.LocalPosition);
    location.velocity.Value = WorldView.ToGlobalVelocity(PhysicsObject.LocalVelocity);
    location.planet.Value   = WorldView.main.ViewLocation.planet;

    if (WorldView.main.ViewLocation.planet.IsOutsideSOI(location.position)
        || location.planet.Value.satellites.Any(s => s.IsInsideSOI(location.position)))
    {
        PhysicsMode = false;          // <-- drop off physics, onto rails
        trajectory.EnterNextPath();
        Update();                     // re-enter, now in the rails branch
        return;
    }
}
else
{
    trajectory.CheckEncounters();
    trajectory.CheckPathTransition(WorldTime.main.worldTime);
    location.Value = trajectory.GetLocation(WorldTime.main.worldTime);
    ...
}
```

> **The finding: crossing an SOI boundary in physics mode forces the
> craft onto rails.** It is not a smooth reference-frame handover — the
> game sets `PhysicsMode = false`, calls `Trajectory.EnterNextPath()`,
> and re-enters `Update()` on the rails branch in the same frame.
>
> For this project that matters directly: any powered burn, drag force,
> or per-tick integration in progress **stops being simulated** at the
> instant of an SOI crossing. A flight agent burning through an SOI
> boundary is not doing what it thinks it is doing, and telemetry
> sampled across that boundary changes meaning mid-stream. Also note
> §D1.3: destruction is gated on `realtimePhysics`, so a craft dropped
> onto rails at an SOI crossing also stops being destroyable.
>
> **[UNTESTED-LIVE]** — read from IL; never observed in flight, which is
> exactly the gap `sfs_physics_reference.md` §5 records. It is now a
> *specific* thing to look for: watch `Physics.PhysicsMode` flip at the
> boundary.

The satellite test scans **only `location.planet.Value.satellites`** —
direct children of the current body, one level down. Combined with
`IsOutsideSOI` for the way out, this is the patched-conic model the
physics doc already infers, now confirmed at the code level.

`Trajectory` @195673 is the rails side:

```
public List<I_Path> paths
public Location GetLocation(double time)             @195780
public double   GetPathEndTime()                     @195796
public double   GetStopTimewarpTime(double timeOld, double timeNew)  @195811
public void     CheckPathTransition(double time)     @195828
public void     CheckEncounters()                    @195845
public void     EnterNextPath()                      @195863
private void    CalculatePaths()                     @195899
private bool    GetNextPath(out I_Path nextPath)     @195932
public static Trajectory CreateTrajectory(Location)  @195724
public static I_Path     CreatePath(Location)        @195754
```

**[PARTIAL]** — signatures confirmed; only the `Update()` call sites were
traced. `CheckEncounters` and `CalculatePaths` are where future
SOI-encounter prediction would live and are **[OPEN]**.

`Trajectory.paths` → `Orbit` remains as documented in
`sfs_source_reference.md`: `apoapsis`/`periapsis` are **radii from planet
centre**, so subtract `Planet.Radius` before comparing to
`location.Height`.

### D4.4 Terrain

**[CONFIRMED]** — signatures @148203–@148458, bodies read for the first two.

```csharp
public bool IsInsideTerrain(Double2 position, double threshold, bool clampToWater)   @148203
{
    if (position.Mag_MoreThan(Radius + maxTerrainHeight)) return false;   // fast reject
    double surface = Radius + GetTerrainHeightAtAngle(position.AngleRadians, clampToWater) - threshold;
    return position.Mag_LessThan(surface);
}

public double GetTerrainHeightAtAngle(double angleRadians, bool clampToWater)        @148294
    => GetTerrainHeightAtAngles(new[] { angleRadians }, clampToWater)[0];
```

**Terrain is real per-angle geometry, not a single bound. [CONFIRMED-LIVE]**
`maxTerrainHeight` is only a fast-reject radius; the actual surface comes
from `GetTerrainHeightAtAngles(double[] angleRadians, bool clampToWater)`
@148458, which is **batched by design** — the single-angle form allocates
a one-element array and calls it. For any sweep (landing-site search,
terrain profile), call the array form once rather than looping the scalar
one.

Live-validated 2026-08-30 via the new `terrain` probe command (Earth,
landed near a small coastal landmass): a 13-point angular sweep
(±30° in steps) showed genuine per-angle variation — real land values
around 45-52m right where the craft sat, dropping to deep underwater
terrain (down to -3557m with `clampToWater=false`, correctly clamped to
0 with `clampToWater=true`) just a few degrees either side. `maxTerrainHeight`
for Earth reported 261.4m at the same time — well above the real local
surface, confirming it's just the fast-reject bound and not usable as an
actual height. Cross-check also passed exactly: `Location.Height` (61.72m)
minus `Location.GetTerrainHeight(true)` (13.72m groundClearance) equals
the swept value at offset 0 (48.0m) to full precision, confirming
`Location.GetTerrainHeight` and `Planet.GetTerrainHeightAtAngle` read the
same underlying function.

This corrects the impression in `sfs_physics_reference.md` §5 that
"`maxTerrainHeight` is a single bound per body, not real terrain
geometry". The *bound* is a single value, but real per-angle terrain is
available and queryable.

Also available:

```
Double2   GetTerrainNormal(Double2 globalPosition)        @148240
float[]   GetTerrainNormals(double[] angles_Radians)      @148315
Color     GetTerrainColor(Double2 position)               @149756
int       GetMaxLOD()                                     @148158
```

**[CONFIRMED-LIVE]** — 2026-08-30, via the new `terraingeo` probe command
(v0.46.0). `IsInsideTerrain` was exercised at three points on Earth: the
real craft position (`false`, correctly not embedded), a synthetic point
constructed 5m below the local surface at the same angle (`true`,
confirming the real surface-comparison branch), and a synthetic point
1000m above `maxTerrainHeight` at the same angle (`false`, confirming the
fast-reject branch). `GetTerrainColor` returned a plausible grass green
(`r=0.272 g=0.403 b=0.245 a=1`) matching the landmass the craft sat on.
`GetMaxLOD()` returned `12`.

**`GetTerrainNormal` is misnamed — it returns a TANGENT, not a normal.
[CONFIRMED]**, IL body read 2026-08-30:

```csharp
Double2 GetTerrainNormal(Double2 globalPosition)
{
    double angle = globalPosition.AngleRadians;
    double delta = 0.1 / SurfaceArea;
    Double2 p1 = Double2.CosSin(angle + delta,
                     Radius + GetTerrainHeightAtAngle(angle + delta, clampToWater: false));
    Double2 p2 = Double2.CosSin(angle - delta,
                     Radius + GetTerrainHeightAtAngle(angle - delta, clampToWater: false));
    return (p2 - p1).normalized;   // note: p2 - p1, not p1 - p2
}
```

`Double2.CosSin(angleRadians, radius)` (confirmed two-arg overload,
param order angle-then-radius) builds a point in the same **global XY**
frame as `Location.position` — so this is a central-difference secant
between two nearby points on the real terrain surface, normalized. It is
a **tangent** direction along the surface profile, not a perpendicular
surface normal, and it lives in global XY, not a local frame.

This matches the live v0.46.0 reading exactly: at
`currentAngleDeg≈89.93°` (≈π/2), the tangent direction (in the `-θ`
sense used here) of a circle is `(sinθ, -cosθ) ≈ (1, 0)` — precisely
matching the observed `(0.99999933, -0.00115861)`, with the tiny
nonzero y-component directly encoding the real local slope (consistent
with the gently-varying 45-52m land patch the `terrain` sweep found
across ±2°). Both earlier working theories (global-radial, local
tangent-frame) are now superseded by this direct IL read — it's simply
a global-frame tangent vector.

**`GetTerrainHeightAtAngles` body. [CONFIRMED]**, IL body read
2026-08-30 (RVA 0x37740):

```csharp
double[] GetTerrainHeightAtAngles(double[] angleRadians, bool clampToWater)
{
    double[] normAngles = angleRadians.Select(Kepler.PositiveAngle).ToArray();  // -> [0, 2π)

    if (!data.hasTerrain)
        return new double[angleRadians.Length];   // all zeros -- airless/no-surface bodies

    double[] samples = TerrainSampler.GetTerrainSamples(this, normAngles, 0.0, 2 * Math.PI);

    if (data.hasWater && clampToWater)
        for (int i = 0; i < samples.Length; i++)
            if (samples[i] < 0) samples[i] = 0;    // floor negative (underwater) to 0

    return samples;
}
```

Confirms the live `terrain` sweep exactly: `clampToWater` only floors
negative values, never affects positive land heights; a body with
`hasTerrain == false` (gas giants, no solid surface) silently returns an
all-zero array rather than erroring — worth remembering so a future
flight controller doesn't mistake that `0` for "at sea level."

`TerrainSampler.GetTerrainSamples(Planet, angles, angleMin, angleMax)`
(IL read 2026-08-30) does three things in order:
1. Calls `TerrainModule.terrainSampler.Calculate(angles, planetRadius)`
   — the actual noise/heightmap evaluation. **[OPEN, deprioritized]**:
   `Executor.Calculate` (IL read) is a **command pipeline** — it builds
   one shared `TerrainSample` object and invokes an ordered
   `List<SampleCommand>` of delegates on it, almost certainly a
   per-planet configured chain of noise layers (octaves, ridges, domain
   warping) set up once at planet load. Genuinely deep and
   planet-specific; not traced further since the wrapper API above is
   already fully validated and callable — reimplementing SFS's own
   noise generator isn't needed for using its output.
2. If `hasWater && water.lowerTerrain`: further **lowers** underwater
   samples using a water-color-driven depth adjustment (`GetWaterColor`
   sampled at a texture-rotated angle, scaled by `oceanDepth`, plus a
   flat +50 base) — this is why the live sweep's unclamped underwater
   readings were so deep (down to -3557m) rather than a simple
   continuation of the land noise: ocean floors are actively pushed
   deeper by this step, not just naturally negative.
3. **Flat-zone blending**: for the current world difficulty, looks up
   `TerrainModule.flatZonesDifficulties[difficulty]` (falling back to
   `flatZones`), and for each `FlatZone` whose angular range (plus a
   transition band) overlaps the sample angle, blends the raw sample
   toward that zone's target `height` via `InverseLerp`/`Lerp` — this is
   the mechanism behind guaranteed flat landing sites near launchpads.

### D4.4b `SFS.World.Terrain` namespace — scoped, not traced further

**[CONFIRMED-SCOPED]** — IL read 2026-08-30 confirmed this namespace is
Unity rendering/physics-collider plumbing, separate from the height-query
API above, and out of scope for the design-phase/reflex-controller work
(the game handles real collision automatically; the agent only needs the
math query API, which is fully validated):

- **`DynamicTerrain`** (`MonoBehaviour`, `BaseChunkCount = 8`): a
  quadtree-style LOD mesh chunking system (`allChunks`/`activeChunks`,
  `bestSplit`/`bestMerge`, `loadDistanceMultiplier`) that generates and
  splits/merges terrain mesh chunks near the camera/craft as it moves —
  purely visual. Matches the live `GetMaxLOD()=12` reading from
  `terraingeo`.
- **`TerrainColliderModule`** (`MonoBehaviour`): subscribes to the
  player's `location.position` change event and to world-load events,
  calling `UpdateChunks()` to spawn/move real Unity physics colliders
  (`chunkIndexes`) near the craft. This is what makes actual ground
  collision work — handled automatically by the engine, not something
  the agent calls into directly.
- `TerrainPoints`, `Chunk` — not traced; supporting data structures for
  the two systems above.

### D4.5 Timewarp radius

**[CONFIRMED]** — @146967:

```csharp
double TimewarpRadius_Ascend =>
    Radius + Math_Utility.Round(
        data.basics.timewarpHeight,
        Math.Pow(10, Math.Floor(Math.Log10(data.basics.timewarpHeight / 2))) / 2);
```

i.e. the raw `timewarpHeight` rounded to a "nice" increment scaled to its
own magnitude. `TimewarpRadius_Descend` @146997 starts from
`Radius + maxTerrainHeight` instead. Also
`static double GetTimewarpRadius_AscendDescend(Location location)`
@148665 — **[PARTIAL]**, signature only.

Relevant to the open **"safe timewarp ceiling"** decision in
`high_level_checklist.md`: the game's own ascend/descend thresholds are
computed properties, readable live per planet, rather than something to
be measured empirically. `Difficulty.MaxPhysicsTimewarpIndex` (2 / 2 / 3,
§D1.5) bounds the physics-warp index separately.

### D4.6 Reflection recipe

**[UNTESTED-LIVE]**

```csharp
object pl      = FindComponent("SFS.WorldBase.PlanetLoader");
object planets = Get(pl, "planets");                 // Dictionary<string, Planet>

object loc    = Unwrap(Get(ActiveRocket(), "location"));
object planet = Get(loc, "planet");                  // may be Planet_Local -> Unwrap
planet = Unwrap(planet);                             // Unwrap stops on name "Planet"

double mu     = ToD(Get(planet, "mass"));            // μ, not kg
double soi    = ToD(Get(planet, "SOI"));
double radius = ToD(Get(planet, "Radius"));          // property
double maxTer = ToD(Get(planet, "maxTerrainHeight"));

double h   = ToD(Get(loc, "Height"));
double rho = ToD(InvokeReturn(planet, "GetAtmosphericDensity", new object[] { h }));

// GetGravity is AMBIGUOUS -- two overloads. Resolve explicitly:
MethodInfo g = planet.GetType().GetMethod("GetGravity",
    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
    null, new Type[] { typeof(double) }, null);
double gAtR = (double)g.Invoke(planet, new object[] { radius + h });

// Are we on rails or under physics?  (the SOI-crossing tell)
object physics    = Get(ActiveRocket(), "physics");
bool   physicsMode = ToB(Get(physics, "PhysicsMode"));    // non-public property
```

Gotchas:

- `Planet.mass` is **μ**; never treat it as kilograms.
- `AtmosphereHeightPhysics` is **+∞** on airless bodies (§D4.0).
- `GetGravity` needs explicit overload resolution (§A1.1).
- `Orbit.apoapsis`/`periapsis` are **radii**, not altitudes.
- `IsInsideSOI` wants a **parent-frame** position; `IsOutsideSOI` wants a
  **planet-relative** one.
- Live planet values are already difficulty-scaled; JSON values are not.

### D4.7 Status summary

| Item | Status |
|---|---|
| `Planet` field/property layout | **[CONFIRMED]** |
| `mass` is μ; `g = μ/r²` both overloads | **[CONFIRMED]** |
| `ρ(h)` formula and hard cutoff | **[CONFIRMED]** — matches §2.3 exactly |
| Difficulty scaling applied once at load via `ScalePlanetData` | **[CONFIRMED]** — live reads are pre-scaled |
| Radius / gravity / SOI / SMA also difficulty-scaled | **[CONFIRMED]** — newly documented |
| `AtmosphereHeightPhysics` = +∞ when airless | **[CONFIRMED]** — trap |
| `IsOutsideSOI` / `IsInsideSOI` semantics and frames | **[CONFIRMED]** |
| **SOI crossing in physics mode forces rails** | **[CONFIRMED]** in IL, **[UNTESTED-LIVE]** |
| Satellite scan is one level deep (patched conic) | **[CONFIRMED]** |
| Real per-angle terrain height is queryable | **[CONFIRMED-LIVE]** — 2026-08-30, corrects "single bound" impression |
| `IsInsideTerrain` / `GetTerrainColor` / `GetMaxLOD` | **[CONFIRMED-LIVE]** — 2026-08-30, both true/false branches of `IsInsideTerrain` exercised |
| `GetTerrainNormal` is a tangent, not a normal, in global XY | **[CONFIRMED]** — 2026-08-30 IL read, matches live reading precisely |
| `GetTerrainHeightAtAngles` body (wrapper) | **[CONFIRMED]** — 2026-08-30 IL read: normalize angles, zero-array if no terrain, delegate to `TerrainSampler`, clamp underwater to 0 |
| `TerrainSampler.Executor.Calculate` noise internals | **[OPEN, deprioritized]** — confirmed to be a per-planet `SampleCommand` pipeline; not traced further, not needed to use the API |
| `SFS.World.Terrain` namespace (`DynamicTerrain`, `TerrainColliderModule`) | **[CONFIRMED-SCOPED]** — 2026-08-30, Unity mesh/collider plumbing, out of scope for the agent |
| `Trajectory.CheckEncounters` / `CalculatePaths` | **[OPEN]** |
| Timewarp radius formula | **[CONFIRMED]** — feeds the open ceiling decision |

---

## D5. Save / load format

Directly relevant to the open **"editor automation vs. file-writing"**
decision in `high_level_checklist.md`. Short version: the whole format is
plain JSON via Newtonsoft, the schema is small, and the game exposes a
**public static spawn entry point** that takes a `Blueprint` object — so
an agent can build a rocket without ever touching the editor UI.

### D5.0 Serialization layer

**[CONFIRMED]** — `SFS.Parsers.Json.JsonWrapper` @113505, static class:

```
static bool   TryLoadJson<T>(IFile file, out T data)                @113513
static void   SaveAsJson(IFile file, object data, bool pretty)      @113564
static T      FromJson<T>(string json)                              @113580
static string ToJson(object data, bool pretty)                      @113660
static string Serialize(JsonSerializer serializer, object data)     @113683
private static VersionedData<T> FromJsonVersionData<T>(string json)  @113620
private static readonly JsonSerializerSettings SerializerSettings
```

Backed by **Newtonsoft.Json** (an extern assembly reference of
`Assembly-CSharp.dll`). Files are plain `.txt` containing JSON.
Supporting types: `VersionedData<T>`, `LegacyNameAttribute` (field
renames across versions), `MainContractResolver`, `ExclusionList` /
`Exclusion<T>` / `Inclusion<T>`.

`FromJson<T>` and `TryLoadJson<T>` are **generic** — reaching them by
reflection needs `MakeGenericMethod`. Writing is easier: `SaveAsJson`
takes `object` and is not generic.

Paths, from `FileLocations` (top-level, no namespace) @~4040:

```
IFolder SavingFolder, CacheFolder, LogsFolder, SolarSystemsFolder,
        CustomAssetsFolder, CustomAssetsFolderOld, ModsFolder,
        PublicTranslationFolder, TranslationCacheFolder,
        BlueprintsFolder, WorldsFolder
```

All static properties. `ModsFolder` is the one `ModLoader.Loader` scans
(§A4.1).

### D5.1 Blueprint — the rocket design format

**[CONFIRMED]** — `SFS.Builds.Blueprint` @86743. Six fields:

```csharp
[Serializable] class Blueprint {
    public float      center;
    public PartSave[] parts;
    public StageSave[] stages;
    public float      rotation;
    public Vector2    offset;
    public bool       interiorView;
}
```

On-disk layout **[CONFIRMED]** from `Blueprint.Save` @86811 /
`TryLoad` @86833 — one folder per blueprint under `BlueprintsFolder`:

```
<BlueprintsFolder>/<name>/
    Version.txt        JsonWrapper.SaveAsJson(file, version, pretty: false)
    Blueprint.txt      JsonWrapper.SaveAsJson(file, blueprint, pretty: true)
```

`TryLoad` reads only `Blueprint.txt` via
`JsonWrapper.TryLoadJson<Blueprint>`.

**There are no joints in a blueprint.** Connectivity is *derived* at
spawn time — see §D5.4.

### D5.2 `PartSave` — the part record

**[CONFIRMED]** — @239253.

```csharp
[Serializable] class PartSave {
    public string  name;                                  // part id, e.g. the prefab key
    public Vector2 position;                              // transform.localPosition
    public Orientation orientation;
    public float   temperature;
    public Dictionary<string,double> NUMBER_VARIABLES;
    public Dictionary<string,bool>   TOGGLE_VARIABLES;
    public Dictionary<string,string> TEXT_VARIABLES;
    public BurnMark.BurnSave burns;
}
static PartSave[] CreateSaves(Part[] parts)               @239282
PartSave(Part part)                                       @239346
PartSave(string, Vector2, Orientation, Dictionary×3)      @239420
void OnSerialization(StreamingContext)                    @239465
```

`PartSave(Part)` @239346, **[CONFIRMED]** from the body:

```csharp
temperature       = float.PositiveInfinity;      // field initialiser
NUMBER_VARIABLES  = new(); TOGGLE_VARIABLES = new(); TEXT_VARIABLES = new();
name              = part.name;
position          = (Vector2)part.transform.localPosition;
orientation       = part.orientation.orientation.Value;
temperature       = part.temperature;
if (part.burnMark != null) burns = new BurnSave(part.burnMark.burn);
NUMBER_VARIABLES  = part.variablesModule.doubleVariables.GetSaveDictionary();
TOGGLE_VARIABLES  = part.variablesModule.boolVariables.GetSaveDictionary();
TEXT_VARIABLES    = part.variablesModule.stringVariables.GetSaveDictionary();
```

Two things worth extracting:

1. **The three `*_VARIABLES` dictionaries are the entire part
   configuration** — size, variant, fuel level, custom text, everything
   parametric. They come from `Part.variablesModule`'s three
   `VariableList` objects via `GetSaveDictionary()`. This is the input
   side of the parametric-expression system in §E4.
2. **`temperature`'s field initialiser is `+∞`** (`ldc.r4 (00 00 80 7f)`)
   before being overwritten from the part. This is independent evidence
   that **`+∞` is the game's "not heated" sentinel** — which sharpens the
   open question in §D1.3: `DissipateHeat` writing `+∞` looks *correct*,
   and the `IsNegativeInfinity` tests in `ApplyHeat`/`HeatPart` look like
   the anomaly. Still **[OPEN]** pending a live test, but the balance of
   evidence has shifted.

### D5.3 The remaining save records

**[CONFIRMED]**

```csharp
class RocketSave {                                        // @192061
    public string rocketName;
    public WorldSave.LocationData location;
    public float  rotation, angularVelocity;
    public bool   throttleOn;
    public float  throttlePercent;
    public bool   RCS;
    public PartSave[]  parts;
    public JointSave[] joints;
    public StageSave[] stages;
    public bool   staging_EditMode;
    public int    branch;
    RocketSave(Rocket rocket)                             // @192103
}

class StageSave { public int stageId; public int[] partIndexes; }        // @192195
        static StageSave[] CreateSaves(Staging staging, List<Part> parts) // @192202

class JointSave { public int partIndex_A, partIndex_B; }                  // @192316
        static JointSave[] CreateSave(Rocket rocket)                      // @192333

class WorldSave.LocationData {                                            // @197802 (nested)
    public string  address;          // planet code name
    public Double2 position, velocity;
    Location GetSaveLocation(double time)                                 // @197847
}
```

**Both `StageSave` and `JointSave` reference parts by index into the
`parts` array** — not by id or name. Any tool that reorders or filters
`parts` must renumber both.

`RocketSave` carries `joints`; `Blueprint` does not. A blueprint is a
design; a rocket save is a flying instance with its connectivity frozen.

`WorldSave` @196925:

```csharp
public string version;
public CareerState career;
public WorldState state;
public Astronauts astronauts;
public RocketSave[] rockets;
public Dictionary<int, SFS.Stats.Branch> branches;
public HashSet<SFS.Logs.LogId> completeLogs;
public HashSet<string> completeChallenges;
```

On-disk layout **[CONFIRMED]** from `WorldSave.Save` @196938 — one folder
per world under `WorldsFolder`, each value a separate JSON `.txt`:

```
Version.txt   WorldState.txt   Rockets.txt   Branches.txt
Achievements.txt   Challenges.txt   Career.txt   Astronauts.txt
```

`Rockets.txt` and `Branches.txt` are written only when
`saveRocketsAndBranches` is true. Loaders:
`TryLoad(IFolder, bool, I_MsgLogger, out WorldSave)` @197028,
`Load_WorldState` @197251, `Save_CareerState` @197193,
`Save_AstronautStates` @197222, `CreateEmptyQuicksave(string version)`
@197276.

> **`completeChallenges` is a `HashSet<string>` of challenge ids** —
> which connects to the `achievements` probe command (v0.24) and
> `SFS.Logs.Challenge.id`. Challenge completion is world save state, not
> Steam state, consistent with what was already found.

### D5.4 Spawning — the file-writing path is viable

**[CONFIRMED]** — `SFS.World.RocketManager` @190305, all static:

```
public static void SpawnBlueprint(Blueprint blueprint)                    @190336
public static List<PartJoint> GenerateJoints(Part[] parts)                @190532
public static void LoadRocket(RocketSave rocketSave, out bool hasNonOwnedParts)  @191085
public static Rocket CreateRocket_Child(JointGroup, Rocket parent, Vector2 offset) @191198
public static void MergeRockets(Rocket a, Part partA, Rocket b, Part partB, Vector2 anchor) @191330
public static void DestroyRocket(Rocket rocket, DestructionReason reason) @191488
private static Rocket[]  SpawnRockets(List<JointGroup> groups)            @190939
private static Location  GetSpawnLocation(JointGroup group)               @191007
private static Rocket    CreateRocket(JointGroup, string name, bool throttleOn,
                             float throttlePercent, bool RCS, float rotation,
                             float angularVelocity, Func<Rocket,Location> location,
                             bool physicsMode)                            @191274
```

And `SFS.Parts.PartsLoader` @230665:

```
public Dictionary<string, Part> parts                   // the catalog, keyed by name
public Dictionary<string, VariantRef> partVariants
public static Part[] CreateParts(PartSave[] partSaves, Transform holder,
        string sortingLayer, OnPartNotOwned onPartNotOwned,
        out OwnershipState[] ownershipState)            @230936
public static Dictionary<string, Part> LoadParts()      @230809
public static (Dictionary<string,Part>, Dictionary<string,VariantRef>) LoadPartVariants()  @230712
```

**This is the finding that bears on the open design decision.**
`RocketManager.SpawnBlueprint(Blueprint)` is `public static` and takes a
plain serializable object. `PartsLoader.CreateParts` turns `PartSave[]`
into real `Part[]`, and `RocketManager.GenerateJoints(Part[])` **derives
connectivity from geometry** — so a generated design does not need to
author joints at all.

So there are three viable construction routes, in increasing order of
coupling to the UI:

1. **Write `Blueprint.txt` to disk** and load it through the game's own
   blueprint menu. Fully offline; the schema is the six fields in §D5.1.
2. **Construct a `Blueprint` in memory** by reflection and call
   `RocketManager.SpawnBlueprint` — no file, no editor, no menu.
   **[UNTESTED-LIVE]**.
3. **Drive the editor UI** (`SFS.Builds`, excluded from this document).

Route 2 is the one the IL most directly supports, and it is worth a
live test before the design decision is made. Its risks are real but
narrow: `SpawnBlueprint`'s body was **not** read (**[OPEN]**), part
`name` keys must match `PartsLoader.parts`, and `OnPartNotOwned` /
`OwnershipState` suggest a DLC/ownership gate on some parts that a
generated design could trip.

### D5.5 Reflection recipe

**[UNTESTED-LIVE]** — none of this has been run.

Reading an existing blueprint off disk needs no game at all — it is JSON.
To go through the game's own loader instead:

```csharp
Type bpType = FindType("SFS.Builds.Blueprint");
Type jsonWrapper = FindType("SFS.Parsers.Json.JsonWrapper");

// TryLoadJson<T> is generic -> MakeGenericMethod
MethodInfo tryLoad = jsonWrapper.GetMethod("TryLoadJson",
        BindingFlags.Public | BindingFlags.Static)
    .MakeGenericMethod(bpType);

// Serializing any save object out is easier -- ToJson is NOT generic:
string json = (string)InvokeStatic(jsonWrapper, "ToJson",
    new Type[] { typeof(object), typeof(bool) },
    new object[] { someSaveObject, true });
```

Dumping the live rocket as a `RocketSave` (a complete, round-trippable
snapshot in one call):

```csharp
Type rocketSaveType = FindType("SFS.World.RocketSave");
ConstructorInfo ctor = rocketSaveType.GetConstructor(
    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
    null, new Type[] { FindType("SFS.World.Rocket") }, null);
object save = ctor.Invoke(new object[] { ActiveRocket() });
string json = (string)InvokeStatic(jsonWrapper, "ToJson",
    new Type[] { typeof(object), typeof(bool) }, new object[] { save, true });
```

> This would be a genuinely useful probe command — a single call that
> captures parts, positions, orientations, **all part variables**,
> stages, joints, location, and control state in the game's own schema.
> It also sidesteps the `Part.modules` walking problem (§A1) entirely.
> **[UNTESTED-LIVE]** — the `RocketSave(Rocket)` constructor body was not
> read, so it may have side effects or assume editor/flight context.

Gotchas:

- `StageSave.partIndexes` and `JointSave.partIndex_A/B` are **indices**
  into `parts`; renumber on any reorder.
- `PartSave.name` must match a key in `PartsLoader.parts`.
- `TryLoadJson<T>` / `FromJson<T>` are generic; `SaveAsJson` / `ToJson`
  are not.
- `LocationData.address` is the planet **code name** string, not an
  object reference — so a save is portable across sessions.
- `PartSave.temperature` defaults to `+∞`, not 0 (§D5.2).

### D5.6 Status summary

| Item | Status |
|---|---|
| JSON via Newtonsoft; `.txt` files; `JsonWrapper` API | **[CONFIRMED]** |
| `Blueprint` six-field schema | **[CONFIRMED]** |
| Blueprint on-disk layout (`Version.txt` + `Blueprint.txt`) | **[CONFIRMED]** |
| `PartSave` schema; three `*_VARIABLES` dictionaries hold all config | **[CONFIRMED]** |
| `PartSave.temperature` initialises to `+∞` | **[CONFIRMED]** — evidence for §D1.3 |
| `RocketSave` / `StageSave` / `JointSave` / `LocationData` schemas | **[CONFIRMED]** |
| Part references are **indices**, not ids | **[CONFIRMED]** |
| `WorldSave` schema and eight-file on-disk layout | **[CONFIRMED]** |
| `RocketManager.SpawnBlueprint` is public static | **[CONFIRMED]** — enables the no-editor route |
| `GenerateJoints` derives connectivity from geometry | **[CONFIRMED]** — blueprints need no joints |
| `SpawnBlueprint` / `CreateParts` bodies | **[OPEN]** |
| `RocketSave(Rocket)` constructor body | **[OPEN]** |
| Ownership / DLC gating (`OnPartNotOwned`, `OwnershipState`) | **[OPEN]** |
| Round-tripping a generated blueprint in the live game | **[UNTESTED-LIVE]** |

---

## E4. Parametric part variables and the expression evaluator

`sfs_physics_reference.md` §1.2 states:

> Part masses are **parametric expressions** (e.g. a nose cone's mass
> field is literally the string `"size * 0.05"`), resolved only at
> runtime once a part is placed and its variables are bound. **No
> Python-side evaluator exists for this**; values must be read live,
> post-placement.

The game ships a complete expression compiler and evaluator, and it is
public and callable. This section replaces "no evaluator exists" with the
real one — and explains *why* live reads have always worked while static
parsing has always failed.

### E4.0 The mechanism, end to end

**[CONFIRMED]** — the loop closes at `Composed_Float.GetResult`.

```
Part.mass : Composed_Float
   ├── public string input           "size * 0.05"     <- the raw expression
   └── private Compute.I_Node compiled                 <- the AST

Composed<T>.Value  (property)                          @278674
   └── CheckInitialize()                               @278825
         └── GetResult(initialize)                     @278215  (Composed_Float override)
               └── Compute.Compile(input, variables, out usedVariables)
                     └── returns I_Node;  I_Node.Value evaluates the tree
```

`Composed_Float` @278208 has exactly two fields:

```csharp
public  string           input;      // the expression text
private Compute.I_Node   compiled;   // compiled AST, built lazily
```

`GetResult(bool initialize)` @278215, **[CONFIRMED]** from the body:

```csharp
if (initialize) {
    compiled = Compute.Compile(input, this.variables, out List<string> usedVariables);
    foreach (string v in usedVariables)
        this.variables.doubleVariables.RegisterOnVariableChange(this.Recalculate, v);
}
if (compiled == null)
    compiled = Compute.Compile(input, this.variables, out _);   // lazy fallback
return compiled.Value;
```

Two consequences that explain the project's whole experience with part
constants:

1. **Reading `.Value` already returns the fully-resolved parametric
   number.** The probe's existing `GetWrapped2(Get(part, "mass"))` has
   been evaluating the expression all along — nothing extra is needed to
   get correct masses from a placed part.
2. **The expression is only meaningful against a bound
   `VariablesModule`.** A `Composed_Float` read off an unplaced catalog
   prefab has no variables bound, which is exactly why static asset
   parsing produced the wrong Titan mass and wrong Hawk thrust/ISP that
   §1.2 records. **The data-trust rule in `CLAUDE.md` is now explained,
   not just observed.**

`Composed_Float` also has `void Offset(float offset)` @278339, which
calls `Compute.Compile` again — so offsets are applied to the expression
layer, not to a cached number.

`Composed_Double` @278415 works identically for `double`-typed values.

### E4.1 `SFS.Parsers.Constructed.Compute` — the compiler

**[CONFIRMED]** — @115724, `public abstract sealed` (static class).

```csharp
public static I_Node Compile(string code, VariablesModule variables,
                             out List<string> usedVariables)        @115729
private static I_Node Compile(ref int i, ref string input,
                             VariablesModule variables,
                             out List<string> usedVariables)        @115748
public static List<string> GetVariablesUsed(string valueString)     @116287
```

**`Compile` is `public static`** and takes a plain string plus a
`VariablesModule` — so any expression can be compiled and evaluated
against any part's variables, not just the ones the game authored.

**`GetVariablesUsed(string)` is `public static` and takes only a
string** — no game object needed. It answers "which variables does this
expression depend on?" for an arbitrary expression.

### E4.2 The AST

**[CONFIRMED]** — all nested inside `Compute`, all `private` except the
interface. Reaching them by name needs the **slash** form
(`SFS.Parsers.Constructed.Compute/I_Node`), and `NonPublic` binding
flags.

```
interface Compute/I_Node                       @116730
    float Value { get; }

class Compute/Number : I_Node                  @116633
    float Value { get; set; }

class Compute/Variable : I_Node                @116688
    public double modifier
    public VariableList<double>.Variable variable
    float Value => (float)variable.Value * (float)modifier      @116695

abstract class Compute/Operator : I_Node       @116602
    public I_Node A, B

class Compute/Add      : Operator  @116446     => A.Value + B.Value
class Compute/Subtract : Operator  @116485     => A.Value - B.Value
class Compute/Multiply : Operator  @116524     => A.Value * B.Value    @116529 (confirmed body)
class Compute/Divide   : Operator  @116563     => A.Value / B.Value
```

**The whole language is four binary operators, numeric literals, and
variable references with a scalar `modifier`.** No functions, no
comparisons, no conditionals, no parenthesised precedence beyond what
`Compile`'s recursive descent builds. That is small enough to
reimplement in Python exactly, if a game-free evaluator is ever wanted.

**Everything evaluates in `float32`.** `Compute.Variable` holds its
source value as `double` and its `modifier` as `double`, but
`get_Value()` converts **both to `float32` before multiplying**
(`conv.r4`, `conv.r4`, `mul`). Precision matches the game only if a
reimplementation does the same.

**[OPEN]** — `Compile`'s parser body (@115748, the recursive-descent
core) and `<Compile>g__Operator|1_0` @116391 were not read, so operator
precedence and the exact accepted grammar are unconfirmed. The
`modifier` field on `Variable` suggests the parser folds a constant
factor into a variable reference, but that is inference, not IL.

### E4.3 Where the variables live

**[CONFIRMED]**

```csharp
class SFS.Variables.VariablesModule {                   // @281584
    public DoubleVariableList doubleVariables;
    public BoolVariableList   boolVariables;
    public StringVariableList stringVariables;
}
```

Each list is a `VariableList<T>` @~280700:

```
public List<VariableSave> saves
private List<VariableList<T>.Variable> _variables

T        GetValue(string variableName)                              @280782
Variable GetVariable(string variableName)                           @280807
void     SetValue(string variableName, T newValue,
                  ValueTuple<bool,bool> addMissingVariables = ...)   @280870
bool     Has(string variableName)                                   @280907
void     RegisterOnVariableChange(Action onChange, string name)     @280954
List<string> GetVariableNameList()                                  @280973
Dictionary<string,T> GetSaveDictionary()                            @280997
void     LoadDictionary(Dictionary<string,T> inputs,
                        ValueTuple<bool,bool> addMissingVariables)   @281050
void     AddVariable() / RemoveVariable(...) / RemoveVariableByIndex(int)
bool     SyncVariables(List<Variable> variables)                     @281141
```

`GetVariableNameList()` and `GetSaveDictionary()` are the two useful
enumeration entry points — the second is the same call `PartSave` uses
(§D5.2), so **the part's saved variable dictionary and its live variable
state are literally the same data**.

`SetValue` + `LoadDictionary` are the write side, and
`Composed_Float.GetResult` registers `Recalculate` against every variable
its expression uses — so **writing a variable propagates to every
dependent `Composed_*` automatically**. That is the mechanism a design
agent would use to resize a part and have mass, thrust, and geometry all
follow.

### E4.4 What this unblocks

- **Symbolic inspection.** `Composed_Float.input` exposes the raw
  expression text for any parametric field. A probe dump can record
  `"size * 0.05"` alongside the evaluated `0.1`, making part behaviour
  legible instead of a black-box number.
- **Dependency analysis without the game.**
  `Compute.GetVariablesUsed(string)` needs only a string.
- **A faithful Python evaluator is now cheap.** Four operators, literals,
  variables-with-modifier, `float32` arithmetic. §1.2's "no Python-side
  evaluator exists" is a gap that can be closed deliberately rather than
  a blocker — **though it is still only worth doing if game-free
  evaluation is actually needed**; live reads already return correct
  values.
- **Parametric what-if.** `SetValue` on a variable then re-read the
  dependent `Composed_*.Value` gives the resized part's real numbers,
  computed by the game. **[UNTESTED-LIVE]**, and it mutates live game
  state — not something to do casually mid-flight.

### E4.5 Reflection recipe

**[UNTESTED-LIVE]**

Reading the symbolic expression alongside the evaluated value:

```csharp
object massWrapper = Get(part, "mass");                  // Composed_Float
string expression  = (string)Get(massWrapper, "input");  // "size * 0.05"
float  evaluated   = ToF(GetWrapped2(massWrapper));      // 0.1  -- already resolved
```

Enumerating a part's variables:

```csharp
object vm = Get(part, "variablesModule");
foreach (string listName in new[] { "doubleVariables", "boolVariables", "stringVariables" })
{
    object list = Get(vm, listName);
    var dict = InvokeReturn(list, "GetSaveDictionary", null)
               as System.Collections.IDictionary;      // same data PartSave stores
    // names also available via GetVariableNameList()
}
```

Compiling an arbitrary expression against a part:

```csharp
Type computeType = FindType("SFS.Parsers.Constructed.Compute");
Type vmType      = FindType("SFS.Variables.VariablesModule");

MethodInfo compile = computeType.GetMethod("Compile",
    BindingFlags.Public | BindingFlags.Static,
    null,
    new Type[] { typeof(string), vmType,
                 typeof(System.Collections.Generic.List<string>).MakeByRefType() },
    null);

object[] args = new object[] { "size * 2 + 1", Get(part, "variablesModule"), null };
object node = compile.Invoke(null, args);                 // Compute/I_Node
var usedVariables = args[2];                              // List<string>, filled by the out param
float value = ToF(Get(node, "Value"));                    // I_Node.Value -- a property
```

Gotchas:

- **`Compile` is overloaded** — public `(string, VariablesModule, out List<string>)`
  and private `(ref int, ref string, VariablesModule, out List<string>)`.
  Plain name lookup throws `AmbiguousMatchException`; resolve by explicit
  parameter types, using `MakeByRefType()` for the `out` parameter.
  Added to §A1.1.
- The AST types are **nested and private** — `Compute/I_Node` with a
  slash, and `NonPublic` flags. `Get(node, "Value")` works because the
  probe's `Get` reads non-public properties.
- **Everything is `float32`.** Do not compare against `double` maths.
- `Composed_Float.input` on an **unplaced prefab** is still readable, but
  its `.Value` is not trustworthy — no bound variables (§E4.0).
- Setting a variable triggers registered `Recalculate` callbacks —
  intended, but it is a live mutation.

### E4.6 Status summary

| Item | Status |
|---|---|
| `Composed_Float` holds `input` (expression) + `compiled` (AST) | **[CONFIRMED]** |
| `.Value` compiles and evaluates; live reads are already correct | **[CONFIRMED]** — explains §1.2 |
| Why static asset parsing gave wrong constants | **[CONFIRMED]** — no bound `VariablesModule` |
| `Compute.Compile` is public static | **[CONFIRMED]** |
| `Compute.GetVariablesUsed(string)` needs no game object | **[CONFIRMED]** |
| AST: `Number`, `Variable(modifier)`, `Add/Subtract/Multiply/Divide` | **[CONFIRMED]** |
| All arithmetic is `float32` | **[CONFIRMED]** |
| `VariablesModule` / `VariableList<T>` read + write API | **[CONFIRMED]** |
| Variable writes auto-propagate via `RegisterOnVariableChange` | **[CONFIRMED]** |
| `Compile` parser body — precedence, exact grammar | **[OPEN]** |
| Whether `modifier` is a parser constant-folding artifact | **[OPEN]** — inference, not IL |
| Parametric what-if via `SetValue` | **[UNTESTED-LIVE]** |

---

## B1. `SFS.World.Rocket` — the craft object

Declared at IL line 187563:

```
.class public auto ansi beforefieldinit Rocket
    extends SFS.World.Player
    implements SFS.World.I_Physics
```

**[CONFIRMED]** `Rocket : Player`. This matters constantly: `location`,
`hasControl`, `isPlayer` and `GetSizeRadius()` are **on `Player`**, not
on `Rocket`, so `typeof(Rocket).GetField("location")` returns null under
`DeclaredOnly` and works only with inherited lookup. The probe's `Get`
helper already walks the hierarchy; anything hand-rolled must.

### B1.1 Field layout [CONFIRMED]

Every field below was read from the `.field` lines of the class body.
All are `public` except the three marked private.

| Field | Type | Note |
|---|---|---|
| `mass` | `SFS.Parts.Mass_Calculator` | drives `rb2d.mass` and `centerOfMass` |
| `rb2d` | `UnityEngine.Rigidbody2D` | the physics body |
| `partHolder` | `SFS.Parts.PartHolder` | part list + `GetModules<T>()` |
| `mapIcon` | `SFS.World.Maps.MapIcon` | |
| `arrowkeys` | `SFS.World.Arrowkeys` | **raw control input** |
| `throttle` | `SFS.World.Throttle` | |
| `staging` | `SFS.World.Staging` | |
| `resources` | `SFS.World.Resources` | |
| `aero` | `SFS.World.Drag.Aero_Rocket` | the C1 subclass |
| `stats` | `SFS.Stats.StatsRecorder` | |
| `timeManager`, `partManager` | `GameObject` | |
| `rocketName` | `string` | |
| `jointsGroup` | `SFS.World.JointGroup` | |
| `collisionImmunity` | `float` | seconds remaining |
| `floating` | `bool` | **in water**, not "in space" |
| `physics` | `SFS.World.Physics` | the D4 driver |
| `output_TurnAxisTorque` | `Float_Local` | *computed* turn axis (see B1.3) |
| `output_TurnAxisWheels` | `Float_Local` | raw `arrowkeys.turnAxis` |
| `output_DirectionalAxis` | `Vector2_Local` | RCS translation input |
| `pipeFlows` *(private)* | `List<(ResourceModule[], ResourceModule)>` | fuel-pipe graph |
| `sizeRadius`, `lastUpdateTime` *(private)* | `float` | cache for `GetSizeRadius` |

**`floating` means "in water".** Both call sites confirm it: in
`CanTimewarp` it selects the `Cannot_Timewarp_While_Moving_Water`
message over `..._On_Surface`, and in `GetTurnAxis` it damps rotation
authority to 10%. Do not read it as "off the ground".

The three `output_*` fields are **outputs, not inputs.** They are written
every `FixedUpdate` and consumed by part modules through the `Inject_*`
plumbing (B1.5). Writing to them from a mod is overwritten within one
physics tick. The inputs are on `arrowkeys`.

### B1.2 `FixedUpdate` — the per-tick order [CONFIRMED]

`Rocket::FixedUpdate` @188822, in order, with nothing else in the body:

```csharp
void FixedUpdate() {
    Inject_Location();
    UpdateMass();
    UpdateMapIconRotation();
    ApplyTorque();
    output_DirectionalAxis.Value = arrowkeys.rcs
        ? arrowkeys.horizontalAxis.Value + arrowkeys.verticalAxis.Value
        : Vector2.zero;
    FuelPipeModule.FixedUpdate_FuelPipeFlow(pipeFlows);
}
```

Note what is **absent**: no thrust, no drag, no heat. Those run in the
part modules' own `FixedUpdate`s (D2, C1, D1), so ordering between them
and this method is Unity's script execution order, not a call chain.

`UpdateMass` @187673 is two lines and runs **every tick**:

```csharp
rb2d.mass          = mass.GetMass();
rb2d.centerOfMass  = mass.GetCenterOfMass();
```

So `rb2d.mass` is always current as of the last physics tick — reading
it live is safe and needs no recomputation. `output_DirectionalAxis` is
the **sum** of the horizontal and vertical axis vectors, gated on
`arrowkeys.rcs`; it is zero whenever RCS is toggled off, regardless of
key state.

### B1.3 Rotation control — the full model [CONFIRMED]

This is the single most useful thing in this section, and it is not what
a physics-based guess would predict. It also **independently confirms
`sfs_physics_reference.md` §2.4** from the code side: that section
already derives the same formula empirically, to 0.0006% error in
vacuum, including the `(mass/200)^0.35` divisor. The IL below is where
it comes from. One reconciliation note — §2.4 writes the threshold as
"only when mass > 200t"; the IL compares `rb2d.mass > 200f` with no unit
conversion, so the tonne reading rests on §2.4's empirical validation,
not on anything visible here.

`GetTorque` @187695:

```csharp
float torque = 0f;
foreach (TorqueModule t in partHolder.GetModules<TorqueModule>())
    if (t.enabled.Local || t.enabled.Value)      // note: Local first
        torque += t.torque.Value;                // Composed_Float
return torque;
```

`ApplyTorque` @188864:

```csharp
float torque = GetTorque();
if (rb2d.mass > 200f)
    torque /= Mathf.Pow(rb2d.mass / 200f, 0.35f);       // heavy-craft penalty

output_TurnAxisTorque.Value = GetTurnAxis(torque, useStopRotation: true);

if (output_TurnAxisTorque.Value != 0f && rb2d.simulated)
    rb2d.angularVelocity -= torque * 57.29578f / rb2d.mass
                          * output_TurnAxisTorque.Value * Time.fixedDeltaTime;

output_TurnAxisWheels.Value = arrowkeys.turnAxis;       // raw, undamped
```

Three consequences, all confirmed from the opcodes:

1. **Rotation is not a torque.** It writes `rb2d.angularVelocity`
   directly. Unity's `AddTorque` is never called, and the rigidbody's
   **moment of inertia is never involved**. Rotational authority is
   `torque / mass`, not `torque / I`. A long rocket and a compact one of
   equal mass turn at exactly the same rate. Any agent model that
   computes an inertia tensor is modelling a game that does not exist.
2. **The heavy-craft penalty is `mass^-0.35` above 200 kg.** Below 200
   the divisor is skipped entirely, so authority is flat-then-decaying,
   with a kink at exactly 200. Combined with the `/rb2d.mass` in the
   integration step, net angular acceleration scales as
   `m^-1` below 200 and `m^-1.35` above it.
3. `57.29578f` is rad→deg (Unity's `angularVelocity` is deg/s), and the
   sign is **subtract** — positive `turnAxis` reduces `angularVelocity`.

`GetTurnAxis` @188939:

```csharp
float GetTurnAxis(float torque, bool useStopRotation) {
    if (arrowkeys.turnAxis != 0f) return arrowkeys.turnAxis;   // manual wins
    if (useStopRotation && hasControl && !IsOnSurface)
        return GetStopRotationTurnAxis(torque) * (floating ? 0.1f : 1f);
    return 0f;
}
```

`GetStopRotationTurnAxis` @188987 — **this is SAS**:

```csharp
float angVel = rb2d.angularVelocity;
float delta  = torque * 57.29578f / rb2d.mass * Time.fixedDeltaTime;
if (delta == 0f) return 0f;
return Mathf.Clamp(angVel / delta, -1f, 1f);
```

`delta` is exactly the angular-velocity change one tick of full-authority
torque produces. So the returned axis is **the fraction of one tick's
authority needed to null the rotation**, clamped. Within one tick's worth
of authority it lands on zero exactly; beyond it, it saturates at full
deflection. There is no PID, no gain, no overshoot — the damping is
deadbeat by construction.

Auto-stabilisation is therefore **off** whenever any of: the player is
holding a turn key, `hasControl` is false, or `IsOnSurface` is true. It
is damped to 10% in water.

`get_IsOnSurface` @189641 — worth knowing because it gates the above:

```csharp
Collider2D[] contacts = new Collider2D[5];               // fixed size 5
rb2d.GetContacts(contacts);
return contacts.Any(<>c.b__84_0);
```

The buffer is **hard-capped at 5 contacts** and the return count is
discarded (`pop`). The array is not cleared between calls — it is a
fresh `newarr` each call, so stale entries are not a risk, but a craft
with more than 5 simultaneous contacts only sees the first 5.

### B1.4 `GetRotation()` — heading, with a three-level fallback [CONFIRMED]

`GetRotation` @187766 returns **degrees**, and picks its reference in
this priority order:

1. Sum of `transform.TransformVector(thrustNormal.Value * thrust.Value)`
   over engines with `engineOn.Value == true`. If nonzero →
   `Atan2(y, x) * 57.29578f`.
2. Else the same sum over engines with `engineOn == false`. If nonzero →
   same `Atan2`.
3. Else the **first** `ControlModule`'s `transform.eulerAngles.z + 90f`.
4. Else `transform.eulerAngles.z` (no `+90`).

Two traps. The `+90f` in case 3 and its absence in case 4 mean the
fallbacks are **not on the same angular convention** — a craft with a
control module and one without report headings 90° apart. And cases 1/2
are a thrust-weighted vector sum, so on a craft with opposed engines
the "heading" can swing wildly or fall to case 3 as engines toggle. For
an agent, `GetRotation()` is a UI convenience; derive heading from
`transform.eulerAngles.z` (or the velocity vector) instead.

### B1.5 `Inject_*` — how modules get their inputs [CONFIRMED]

Eleven private methods (`Inject_Rocket`, `_IsPlayer`, `_HasControl`,
`_ThrottleOn`, `_Throttle`, `_TurnAxisTorque`, `_TurnAxisWheels`,
`_DirectionalAxis`, `_Location`, `_Physics`) plus
`InjectPartDependencies` @189026, `Start_RocketInjector` @188683 and
`OnDestroy_RocketInjector` @188767.

Each pairs with a **nested interface** on `Rocket`: `Rocket/INJ_Rocket`,
`Rocket/INJ_IsPlayer`, and so on, each declaring a single setter
property. A part module opts in by implementing the interface; the
injector finds implementors and pushes the value in. This is how
`EngineModule.throttle_Out` gets populated without the module holding a
`Rocket` reference.

Only `Inject_Location()` runs from `FixedUpdate`. The rest run from
`Start_RocketInjector` / `SetParts`, i.e. on craft-structure change.

**Extractor note:** `INJ_Rocket`'s `set_Rocket` is `abstract`, and an
earlier pass of `sig.sh` attributed it to `Rocket` itself. See §A2 — an
`abstract` member on a concrete class is always an extractor overrun.

### B1.6 `I_Physics` — explicitly implemented, and reflection-hostile [CONFIRMED]

All seven `I_Physics` members are **explicit interface implementations**,
emitted as `private final virtual ... SFS.World.I_Physics.get_PhysicsMode`
with an `.override`. Consequences for the probe:

- `typeof(Rocket).GetProperty("PhysicsMode")` returns **null**.
- The member's real reflected name contains dots:
  `"SFS.World.I_Physics.PhysicsMode"`, and it is non-public.
- The clean route is the interface: cast to `I_Physics`, or
  `typeof(I_Physics).GetProperty("PhysicsMode").GetValue(rocket)`, which
  dispatches through the interface map correctly.

Bodies:

```csharp
bool    PhysicsMode  => rb2d != null && rb2d.simulated;
Vector2 LocalPosition => (Vector2)rb2d.transform.position
                       + (Vector2)transform.TransformVector(mass.GetCenterOfMass());
Vector2 LocalVelocity => rb2d.linearVelocity;
void    OnCrashIntoPlanet() => RocketManager.DestroyRocket(this, (DestructionReason)0);
```

```csharp
set_PhysicsMode(bool value) {
    rb2d.simulated = value;
    foreach (Collider2D c in partHolder.GetComponentsInChildren<Collider2D>(true))
        c.enabled = value;
    if (!rb2d.simulated) rb2d.angularVelocity = 0f;
}
```

**`LocalPosition` is the centre of mass, not the transform origin**, and
the setter subtracts the same offset before writing. So `Physics` /
`Trajectory` (D4) track the CoM. A position read from
`transform.position` and one read through `I_Physics` differ by the CoM
offset — for a tall rocket that is metres, not noise.

`set_PhysicsMode(false)` **disables every collider on the craft** and
zeroes angular velocity. This is exactly what the SOI-crossing branch in
`Physics.Update()` (§D4.3) triggers: crossing an SOI boundary in physics
mode silently drops the craft's colliders and stops its rotation.

### B1.7 `CanTimewarp` [CONFIRMED]

`CanTimewarp(I_MsgLogger logger, bool showSpeed, out bool isInWater)`
@188430. Returns false, with a localised message, on the first failing
check:

```csharp
isInWater = floating;
double minRadius = Planet.GetTimewarpRadius_AscendDescend(location.Value);
if (location.Value.Radius < minRadius) {
    if (!IsOnSurface && !floating)
        WorldTime.ShowCannotTimewarpBelowHeightMsg(
            minRadius - location.Value.planet.Value.Radius, logger, showSpeed);
    else if (location.Value.velocity.Value.Mag_MoreThan(floating ? 3.0 : 0.1))
        ... return false;                       // "moving on surface" / "in water"
}
if (engines.Any(e => e.throttle_Out.Value != 0f) ||
    boosters.Any(b => b.throttle_Out.Value != 0f)) { ... return false; }
return true;
```

The surface speed limit is **0.1 m/s on land, 3.0 m/s in water**
(`Double2.Mag_MoreThan`, so it is a squared-magnitude compare, no sqrt).
The accelerating check reads `throttle_Out`, not `engineOn` — an engine
that is on at zero throttle does not block timewarp.

`GetTimewarpRadius_AscendDescend` is `public static` on `Planet` and
takes a `Location`, so an agent can pre-compute the altitude at which
timewarp becomes legal without trial and error.

### B1.8 `GetSizeRadius()` — cached, 1-second granularity [CONFIRMED]

@188147, overriding `Player.GetSizeRadius()`:

```csharp
if (Time.time - lastUpdateTime < 1f) return sizeRadius;      // stale up to 1s
float maxSq = partHolder.parts.Max(p => /* b__0: dist² from centerOfMass */);
sizeRadius  = Mathf.Sqrt(maxSq) + 3f;
lastUpdateTime = Time.time;
return sizeRadius;
```

The `+ 3f` padding and the 1-second cache both matter if an agent uses
this for clearance checks: right after staging the value is up to a
second out of date, and it is inflated by 3 m by design.

### B1.9 Static helpers [CONFIRMED signature, PARTIAL body]

| Member | Access | Note |
|---|---|---|
| `UseParts(bool fromStaging, (Part, PolygonData)[] regions)` | `public static` | returns `UsePartData[]`; **the programmatic "click a part" entry point** |
| `SetPlayerToBestControllable(Rocket[] rockets)` | `public static` | picks the player craft after a split |
| `SetParts(Part[] newParts)` | `public` | rebuilds holder, joints, injections |
| `SetJointGroup(JointGroup)` | `public` | |
| `EnableCollisionImmunity(float duration)` | `public` | |

`UseParts` is the non-UI path to activating parts (staging, toggles,
docking) without synthesising touch input — `Rocket.ClickPart` /
`RaycastPart` / `CanUsePart` are the UI path and all take
`SFS.Input.TouchPosition`. **Body not read** — marked [PARTIAL];
`UsePartData` and `PolygonData` are unexamined and `CanUsePart` @188347
has an unread gate that likely rejects parts of unowned DLC.

### B1.10 Gimbal timing — the commanded-steering to angle chain [CONFIRMED, keyframe shape UNTESTED-LIVE]

Three methods, read together 2026-08-31, form a complete pipeline from
player/SAS steering input to the actual visual/physical gimbal angle.
None of the three needed Harmony or anything exotic — all three are
plain reflection reads once located.

**1. `EngineModule.RecalculateGimbal()`** — sets the *target*, every tick:

```csharp
if (!hasGimbal) return;
if (!gimbalOn.Value) return;
gimbal.targetTime.Value = (throttle_Out.Value > 0)
    ? turnAxis_Input.Value * Transform_Utility.RotationDirection(transform)
    : 0f;
```

`gimbal` is a public `MoveModule` field on `EngineModule` (there's also
a `gimbalOn : Bool_Reference` enable flag, both confirmed via the same
read as `hasGimbal`). `RotationDirection(transform)` is a sign flip
(almost certainly ±1 depending on which side of the rocket the engine
sits) — not yet read itself, but its effect is fully visible in the
live `gimbalinfo` output regardless of what it does internally.

**2. `MoveModule.Update()`** — chases that target, every tick:

```csharp
float dt = unscaledTime ? Time.unscaledDeltaTime : Time.deltaTime;
if (dt == 0f) return;
float speed = animationTime > 0f ? dt / animationTime : 10000f;
time.Value = Mathf.MoveTowards(time.Value, targetTime.Value, speed);
if (time.Value == targetTime.Value) this.enabled = false;
```

**Linear, not eased or spring-damped.** `Mathf.MoveTowards` moves by a
fixed max step per call, so `time` reaches `targetTime` in exactly
`animationTime` seconds flat (or effectively one frame if
`animationTime <= 0`, since `speed` becomes huge). This is a genuinely
different mechanism from player-commanded body rotation (§B1.3, which
writes `angularVelocity` directly and has no timing lag at all) — gimbal
response has a real, predictable, constant-rate lag baked in.

**3. `MoveModule.ApplyAnimation()`** — turns `time` into the real angle.
This method is actually a 14-case generic animation dispatcher keyed on
`MoveData.Type` (rotation, position, scale, sprite/UI color, audio
volume, arbitrary float/bool variables — cases 3 and 4 are dead,
fall through to a no-op). The 2D-gimbal-relevant case is index 0:

```csharp
transform.localEulerAngles = new Vector3(0f, 0f, X.Evaluate(time.Value - offset));
```

`X` is a `UnityEngine.AnimationCurve` (a keyframe/Hermite spline, not
necessarily linear), `offset` staggers the curve per animated element
(`MoveData` also carries `transform`, `Y`, `spriteRenderer`, `image`,
`gradient`, `audioSource`, `floatVariable`, `boolVariable` — all public
fields, all trivially reflectable if another `MoveData.Type` is ever
needed).

**The one thing this IL read cannot answer:** whether a real engine's
`X` curve is a plain 2-key linear ramp (angle directly proportional to
`time`) or has easing baked into the keyframe tangents. `AnimationCurve`
is a stock Unity type — `.keys` returns a `Keyframe[]`, each with
`time`/`value`/`inTangent`/`outTangent`, all public, all reflectable —
but nobody has read a real engine's curve yet.

**LIVE-CONFIRMED 2026-08-31/09-01, same session.** A real 3-engine
craft's rotate curve: two keyframes, `(t=-1, v=-3, in=3, out=3)` →
`(t=1, v=3, in=3, out=3)`. Both tangents (3) exactly equal the chord
slope `(3-(-3))/(1-(-1))=3` — a Hermite spline with matching in/out
tangents equal to its own chord slope degenerates to a straight line.
**Confirmed linear, no easing.** Gimbal range ±3°; `time` itself ranges
−1..1, not 0..1. Also visible in the same dump: `RotationDirection`
(the sign flip in `RecalculateGimbal`, body still unread) genuinely
differs per engine on this craft — one of the three engines showed a
negated `targetTime` relative to the other two's identical
`turnAxisInput`, consistent with that engine being mounted opposite the
other two so all three still steer the same rotational sense.

**Also confirmed and live-validated: where `turnAxis_Input` itself
comes from.** `EngineModule` implements `Rocket.INJ_TurnAxisTorque`;
`Rocket.Inject_TurnAxisTorque()` reads `output_TurnAxisTorque.Value`
**once** and broadcasts that exact value to every module implementing
the interface via `set_TurnAxis`. `EngineModule`'s implementation is a
bare passthrough — `turnAxis_Input.Value = value`, no scaling, no
clamp. So `EngineModule.turnAxis_Input` **is**
`Rocket.output_TurnAxisTorque`, exactly, every tick — the identical
signal that drives body rotation (§B1.3). This is *why* gimbal engines
visibly counter-steer the instant SAS engages (observed live
2026-09-01): SAS's saturated ±1 deadbeat correction and the gimbal
target are not two systems that happen to correlate, they're two
readers of one broadcast value. **Live-validated same session:** 6,513
samples, `gimbalTurnAxisInput` vs. `output_TurnAxisTorque` — **0.0000%
error, max absolute difference exactly 0**, spanning both manual-hold
saturation (±1.00, ~1,569 samples) and SAS's full proportional settling
curve down to 0 (~3,577 samples at rest, plus the full spread in
between as angular velocity decayed). Tighter than any formula-based
result elsewhere in this project, which tracks — it isn't a formula,
it's a literal value copy.

Probe support: `gimbalinfo` command (v0.50.0, one-shot, curve
keyframes) and `computed:gimbal` scoped-telemetry field (v0.51.0,
per-tick `gimbalOn`/`throttleOut`/`turnAxisInput`/`time`/`targetTime`).
The live validation above used `computed:gimbal` alongside the
already-existing `output_TurnAxisTorque` telemetry path — no new probe
code needed for the validation itself.

### B1.11 Status

| Item | Status |
|---|---|
| `Rocket : Player, I_Physics` | **[CONFIRMED]** |
| Full field layout, 21 fields | **[CONFIRMED]** |
| `floating` means in water | **[CONFIRMED]** — both call sites |
| `FixedUpdate` call order and contents | **[CONFIRMED]** |
| `UpdateMass` runs every tick | **[CONFIRMED]** |
| Rotation writes `angularVelocity`, ignores inertia | **[CONFIRMED]** |
| `mass^-0.35` penalty above 200 | **[CONFIRMED]** |
| SAS = deadbeat `clamp(ω / one-tick-authority, ±1)` | **[CONFIRMED]** |
| SAS gates: manual input / `hasControl` / `IsOnSurface` / water 10% | **[CONFIRMED]** |
| `IsOnSurface` 5-contact cap | **[CONFIRMED]** |
| `GetRotation` 4-level fallback, `+90` inconsistency | **[CONFIRMED]** |
| `I_Physics` members are explicit implementations | **[CONFIRMED]** |
| `LocalPosition` is centre of mass | **[CONFIRMED]** |
| `set_PhysicsMode(false)` disables all colliders | **[CONFIRMED]** |
| Timewarp limits 0.1 / 3.0 m/s | **[CONFIRMED]** |
| `GetSizeRadius` 1 s cache, `+3` pad | **[CONFIRMED]** |
| `Inject_*` ↔ nested `INJ_*` interface mechanism | **[CONFIRMED]** |
| Gimbal: `RecalculateGimbal` target-setting | **[CONFIRMED]** |
| Gimbal: `MoveModule.Update` timing (linear `MoveTowards`) | **[CONFIRMED]** |
| Gimbal: `ApplyAnimation` angle from `AnimationCurve` | **[CONFIRMED]** |
| Gimbal: real curve keyframe shape (linear vs. eased) | **[CONFIRMED LIVE]** — linear, tangents = chord slope |
| Gimbal: `turnAxis_Input` == `output_TurnAxisTorque` | **[CONFIRMED LIVE]** — 0.0000% error, 6,513 samples |
| `UseParts` / `SetParts` bodies | **[PARTIAL]** — signatures only |
| `CanUsePart` gate | **[OPEN]** |
| Rotation model verified against live flight | **[UNTESTED-LIVE]** |

---

## B2. `Location`, `WorldLocation`, `Double2` — the world coordinate system

Three types, easy to confuse, with different mutability and different
traps. Everything below is read from IL.

### B2.1 `SFS.World.Location` — an immutable-by-convention snapshot [CONFIRMED]

```
.class public auto ansi serializable beforefieldinit Location   @160698
```

Four public fields, no properties backing them:

| Field | Type |
|---|---|
| `time` | `double` |
| `planet` | `SFS.WorldBase.Planet` |
| `position` | `Double2` |
| `velocity` | `Double2` |

`position` and `velocity` are **planet-relative**, in metres and m/s,
with the planet's centre at the origin. They are not solar-system
coordinates — see `GetSolarSystemPosition`.

Computed members, all bodies read:

```csharp
double Radius           => position.magnitude;
double Height           => Radius - planet.Radius;
double VerticalVelocity => velocity.Rotate(-(position.AngleRadians - π/2)).y;

double GetTerrainHeight(bool clampToWater)
    => Height - planet.GetTerrainHeightAtAngle(position.AngleRadians, clampToWater);

Double2 GetSolarSystemPosition(double time)
    => position + planet.GetSolarSystemPosition(time);
```

`Height` is **altitude above the datum radius**, not above terrain.
`GetTerrainHeight` is the above-ground-level figure, and it takes a
`clampToWater` flag that is passed straight through to
`Planet.GetTerrainHeightAtAngle` — pass `true` to treat sea level as the
floor over water. This resolves what §D4.4 left half-open: per-angle
terrain is reachable from a plain `Location` with no extra plumbing.

`VerticalVelocity` is the **radial** component: rotating by `π/2 − θ`
maps the outward radial direction onto `+y`, so `.y` is the climb rate.
It is signed, positive outward.

Both constructors run every component through `CheckNaN` @160874, which
is `double.IsNaN(a) ? 0.0 : a`. **NaN silently becomes zero** — a
craft whose physics blew up reports a valid-looking position at the
planet's centre rather than propagating NaN. Do not treat a
`Location` as evidence that the numbers upstream were sane.

The two-argument constructor sets `time = -1.0`, so a `Location` built
that way is not usable for anything time-dependent (`GetSolarSystemPosition`
would evaluate at t = −1).

`op_Addition(Location a, Location b)` @160891 exists and is public
static, but composes `b.time`/`b.planet` with summed positions — read
the body before using it; it is not a symmetric operation.

### B2.2 `SFS.World.WorldLocation` — the live, observable one [CONFIRMED]

```
.class public auto ansi beforefieldinit WorldLocation   @160568
```

| Field | Type |
|---|---|
| `planet` | `SFS.Variables.Planet_Local` |
| `position` | `SFS.Variables.Double2_Local` |
| `velocity` | `SFS.Variables.Double2_Local` |

This is what `Player.location` holds, and it is the *observable* form:
each field is an `Obs<T>` you can subscribe to. **There is no `time`
field.** `get_Value()` @160599 synthesises one:

```csharp
Location get_Value() => new Location(
    WorldTime.main != null ? WorldTime.main.worldTime : 0.0,
    planet, position, velocity);          // via Obs<T>.op_Implicit
```

So a `Location` obtained from a `WorldLocation` is stamped with the
current world time at the moment of the read, and **is a copy** —
mutating it does nothing to the craft.

`set_Value(Location value)` @160629 has a silent guard:

```csharp
if (value == null || value.planet == null) return;   // no-op, no throw
planet.Value = value.planet;
position.Value = value.position;
velocity.Value = value.velocity;
```

**A teleport with a null planet fails silently.** If an agent sets a
craft's location and nothing moves, this guard is the first thing to
check — there is no exception and no log line.

`get_Height()` @160576 duplicates `Location.Height` against the live
values, so you can read altitude without allocating a `Location`.

### B2.3 `Double2` — the double-precision vector [CONFIRMED]

```
.class public sequential ansi sealed serializable beforefieldinit Double2   @180
```

Global namespace — **not** under `SFS.`. `Type.GetType("Double2")` on
the Assembly-CSharp assembly is the correct lookup; a `SFS.Double2`
probe returns null.

Two public `double` fields, `x` and `y`. It is a `struct`
(`sequential ... sealed`), so reflection `GetValue` boxes a **copy** —
writing `x` on the boxed result changes nothing. To move a craft you
must construct a new `Double2` and assign the whole value.

Bodies read and confirmed:

```csharp
double AngleRadians => Math.Atan2(y, x);
double AngleDegrees => Math.Atan2(y, x) / 6.283185307179586 * 360.0;
double magnitude, sqrMagnitude          // the obvious ones
bool Mag_MoreThan(double a) => sqrMagnitude >  a * a;
bool Mag_LessThan(double a) => sqrMagnitude <  a * a;

Double2 Rotate(double angleRadians) {    // standard CCW rotation
    double c = Math.Cos(angleRadians), s = Math.Sin(angleRadians);
    return new Double2(x * c - y * s, x * s + y * c);
}
```

`Mag_MoreThan` / `Mag_LessThan` avoid the square root — and note both
are **strict** (`cgt` / `clt`), so a speed exactly at the threshold
passes the timewarp check in §B1.7. `AngleRadians` is `Atan2(y, x)`,
i.e. **0 is +x, increasing counter-clockwise** — the same convention
`AeroModule` subtracts π/2 from to get "up-relative" angles (§C1).

`op_Equality` @783 is **exact `double` comparison** on both components,
with no epsilon. Two positions computed by different routes will
essentially never compare equal; use `Mag_LessThan` on the difference.

Statics worth knowing: `Dot`, `Angle`, `SignedAngle`, `Reflect`,
`Lerp(a, b, t)`, `CosSin(angleRadians)` and `CosSin(angleRadians, radius)`
— the last is the direct polar→cartesian constructor, which is what you
want for "put the craft at angle θ, radius r".

Conversions: implicit `Double2 → Vector2` and `Double2 → Vector3`;
explicit `Vector2 → Double2` and `Double3 → Double2`; plus the
properties `ToVector2` / `ToVector3` and the statics
`ToDouble2(Vector2)` / `ToDouble2(Vector3)`. **Prefer the properties**
— the two `op_Implicit` overloads differ only in return type and are
unresolvable through `GetMethod` (see §A1.1).

**`ToParsableString()` and `Parse()` do not round-trip.** [CONFIRMED]

```csharp
string ToParsableString() => string.Format("{0}:{1}", x, y);   // 2 fields

static Double2 Parse(string text) {                            // reads [1] and [2]
    var p = text.Split(':', StringSplitOptions.None);
    return new Double2(double.Parse(p[1]), double.Parse(p[2]));
}
```

`Parse` indexes elements **1 and 2**, so it needs a three-part string,
while `ToParsableString` emits two. `Double2.Parse(v.ToParsableString())`
throws `IndexOutOfRangeException`. Neither method is called anywhere in
`Assembly-CSharp` (`grep` finds only their own `end of method` lines),
so this is dead code the game never exercises — but do not reach for it
as a serialisation helper. The save format uses Newtonsoft on the fields
directly (§D5), not these.

### B2.4 Which one to read, in practice

| You want | Read |
|---|---|
| live altitude | `rocket.location.Height` (no allocation) |
| a consistent snapshot to compute against | `rocket.location.Value` — copies, stamps `time` |
| altitude above ground | `location.Value.GetTerrainHeight(clampToWater)` |
| climb rate | `location.Value.VerticalVelocity` |
| to move the craft | `rocket.location.Value = new Location(...)` — **planet must be non-null** |
| to react to a change | subscribe to `rocket.location.position` (`Obs<Double2>`) |
| centre-of-mass position in Unity space | `((I_Physics)rocket).LocalPosition` (§B1.6) — a different quantity |

**Two frame/clock traps carried over from the earlier
`sfs_source_reference.md`, both still true:**

- **`rb2d.linearVelocity` is not world velocity.** It is expressed in the
  floating *velocity* frame (§E5.2), so comparing it to
  `location.velocity` without `WorldView.ToGlobalVelocity` is wrong.
  Use `location.Value.velocity` (a `Double2`) for anything world-frame.
- **`Location.time` and Unity's `Time.timeSinceLevelLoad` are different
  clocks.** `Location.time` comes from `WorldTime.main.worldTime`
  (§E5.1), which advances at the timewarp rate and persists across
  saves. Never cross-reference the two.

### B2.5 Status

| Item | Status |
|---|---|
| `Location` field layout, planet-relative | **[CONFIRMED]** |
| `Radius` / `Height` / `VerticalVelocity` / `GetTerrainHeight` bodies | **[CONFIRMED]** |
| `Height` is above datum, not terrain | **[CONFIRMED]** |
| Constructors coerce NaN → 0 | **[CONFIRMED]** |
| 2-arg ctor sets `time = -1` | **[CONFIRMED]** |
| `WorldLocation` has no `time`; synthesises from `WorldTime.main` | **[CONFIRMED]** |
| `set_Value` silently no-ops on null planet | **[CONFIRMED]** |
| `Double2` is a global-namespace struct | **[CONFIRMED]** |
| `Rotate`, `Mag_MoreThan/LessThan` (strict) bodies | **[CONFIRMED]** |
| `AngleRadians` = `Atan2(y, x)`, 0 = +x, CCW | **[CONFIRMED]** |
| `op_Equality` is exact, no epsilon | **[CONFIRMED]** |
| `op_Implicit` unresolvable by parameter types | **[CONFIRMED]** |
| `ToParsableString` / `Parse` mismatch; both uncalled | **[CONFIRMED]** |
| `Location.op_Addition` semantics | **[OPEN]** — body not read |
| Teleport via `set_Value` | **[UNTESTED-LIVE]** |

---

## B3. `SFS.Parts.Part`

```
.class public auto ansi beforefieldinit Part          @236080
    extends SFS.World.Drag.HeatModuleBase
    implements SFS.World.Rocket/INJ_Rocket
```

**[CONFIRMED]** `Part : HeatModuleBase`. This is why the heat chain in
§D1 can treat a bare `Part` and a `HeatModule` interchangeably — they
share the base. And `Part` implements the injection interface
`Rocket/INJ_Rocket` (§B1.5), which is how `part.Rocket` gets set.

### B3.1 Field layout [CONFIRMED]

| Field | Type | Note |
|---|---|---|
| `displayName`, `pickCategoryName`, `description` | `TranslationVariable` | localised |
| `mass` | `Composed_Float` | **parametric** — see §E4 |
| `centerOfMass` | `Composed_Vector2` | parametric, part-local |
| `density` | `Float_Local` | |
| `orientation` | `OrientationModule` | |
| `variablesModule` | `VariablesModule` | the binding for `mass`'s expression |
| `variants` | `Variants[]` | |
| `onPartUsed` | `UsePartUnityEvent` | |
| `burnMark` *(notserialized)* | `BurnMark` | |
| `frameIndex_WaterDamage` *(notserialized)* | `int` | |
| `temperature` | `float` | **public field**, °C |
| `aboutToDestroy`, `onPartDestroyed` | `Action<Part>` | |
| `modules` *(private)* | `Dictionary<string, object>` | query memo — see B3.2 |
| `moduleCount` *(private)* | `Dictionary<string, int>` | ditto |
| `<Rocket>k__BackingField` *(private)* | `Rocket` | |
| `<LastAppliedIndex>k__BackingField` *(private)* | `int` | |
| `<ExposedSurface>k__BackingField` *(private)* | `float` | drag/heat coupling |

`mass` and `centerOfMass` are `Composed_*`, i.e. **expression-backed**.
Reading `.Value` evaluates against `variablesModule`. This is the §E4
mechanism, and it is why a part's mass cannot be read from the asset
file — a scaled tank's mass literally is the string `"size * …"` until
evaluated.

### B3.2 `GetModules<T>()` — a memo, not a registry [CONFIRMED]

This resolves the "walking `Part.modules` is unreliable" problem noted
in the project's own notes. The body @236536:

```csharp
public T[] GetModules<T>() {
    string key = typeof(T).Name;                       // SHORT name
    if (!modules.ContainsKey(key))
        modules.Add(key, GetComponentsInChildren<T>(true));   // includeInactive
    return (T[])modules[key];
}

public int GetModuleCount<T>() { /* same shape, moduleCount, .Length */ }
public bool HasModule<T>()  => GetModuleCount<T>() > 0;
```

Four consequences, all load-bearing:

1. **`modules` is a lazy cache of queries already made**, not an
   inventory. A part nobody has asked about `EngineModule` has no
   `"EngineModule"` key. **Enumerating the dictionary tells you what has
   been queried, not what the part has.** Any probe that walks `modules`
   to list a part's modules under-reports, non-deterministically,
   depending on what the game happened to ask for first.
2. The correct route is to *call* the method. Via reflection:
   ```csharp
   MethodInfo gm = typeof(Part).GetMethod("GetModules")
                               .MakeGenericMethod(moduleType);
   Array mods = (Array)gm.Invoke(part, null);
   ```
   Or skip `Part` entirely and call
   `part.GetComponentsInChildren(moduleType, true)` — the Unity
   non-generic overload — which is what the cache wraps anyway and needs
   no `MakeGenericMethod`.
3. **The key is `typeof(T).Name`, the short name.** Two types sharing a
   short name across namespaces collide in one cache slot, and the
   second caller gets a `castclass` on the wrong array type →
   `InvalidCastException`. A mod that defines its own `EngineModule` in
   its own namespace can break the base game's lookup on any part it
   touches. Not observed; the mechanism is confirmed from the opcodes.
4. **The cache is never invalidated.** `Part::modules` is written only
   in the constructor (@237369) and read only in these two methods —
   `grep` on `Part::modules` returns exactly those sites, no `Clear`.
   Harmless in practice, because a part's component set is fixed after
   `InitializePart`, but it means a module added at runtime is invisible
   to every later `GetModules<T>()` on that part.

`InitializePart()` @236871 collects `I_InitializePartModule` via
`GetComponentsInChildren(true)`, **sorts** them with a comparison
lambda, then invokes each — so module initialisation has a defined
order, set by whatever `b__31_0` compares (not read; likely a priority
field). [PARTIAL]

### B3.3 Heat members — and what `Part` actually contributes [CONFIRMED]

All `virtual`, i.e. overridable by `HeatModule`:

```csharp
virtual string Name             => (string)GetDisplayName();
virtual bool   IsHeatShield     => false;
virtual float  Temperature      { get => temperature;            set => temperature = value; }
virtual int    LastAppliedIndex { get; set; }                    // plain auto-property
virtual float  ExposedSurface   { get; set; }                    // plain auto-property
virtual float  HeatTolerance    => AeroModule.GetHeatTolerance(HeatTolerance.Low);
```

**`Part.HeatTolerance` is hardcoded to `Low`** — `ldc.i4.0` straight
into `GetHeatTolerance`. It reads no part config at all. With §D1's
`Low => 400f` and the `× 1.03` destruction threshold, this is the direct
confirmation that a plain part breaks at **412.0 °C**, and that the
figure is not configurable per part on `Part` itself; a
heat-shield-style tolerance must come from a `HeatModule` override.

**Refinement to the §D1 probe finding.** `Part.get_Temperature` returns
exactly the `temperature` field, so on a `Part` the property and the
field agree and the probe's field read is correct there. The mismatch
only arises when the object in hand is a *different* `HeatModuleBase`
subclass whose override reads a `Float_Reference`. So the fix is not
"the property beats the field on `Part`" — it is **hold the
`HeatModuleBase` reference (e.g. `Surface.owner`) and read
`Temperature` virtually**, which dispatches to whichever subclass is
actually there. Reading `Part.temperature` off a part whose heat is
owned by a module is what under-reports.

`OnOverheat(bool breakup)` @237163 is a one-line forward to
`OnOverheat(this, breakup)` — the two-argument form documented in §D1
(destroy `joints[0]` and cool 20% rather than exploding). Both exist,
same name, different arity: **`GetMethod("OnOverheat")` is ambiguous.**

### B3.4 `DestroyPart` [CONFIRMED]

```csharp
public void DestroyPart(bool createExplosion, bool updateJoints, DestructionReason reason) {
    if (createExplosion)
        EffectManager.CreateExplosion(
            transform.TransformPoint(centerOfMass.Value),
            mass.Value * 2f + 0.5f);                 // explosion size from mass
    Action<Part> cb = onPartDestroyed;
    onPartDestroyed = null;                          // cleared BEFORE invoke
    cb?.Invoke(this);
    if (updateJoints)
        JointGroup.OnPartDestroyed(this, Rocket, reason);
    Object.Destroy(gameObject);
}
```

Explosion radius is `mass * 2 + 0.5`. `onPartDestroyed` is nulled before
being invoked, so a handler that re-subscribes during the callback is
**not** cleared — and re-entrancy cannot loop. Note `aboutToDestroy` is
*not* invoked here; it must fire from a caller upstream. [OPEN] — its
call sites are unread.

`Object.Destroy` is deferred to end of frame, so the part is still
alive and readable for the remainder of the current tick.

### B3.5 `GetOwnershipState()` [CONFIRMED] — the DLC/career gate

@236807, returning `SFS.Parts.Modules.OwnershipState`
(`NotOwned = 0`, `NotUnlocked = 1`, `OwnedAndUnlocked = 2`):

```csharp
if (!GetModules<OwnModule>().All(m => m.IsOwned || !m.IsPremium))
    return OwnershipState.NotOwned;
if (!CareerState.main.HasPart(this))
    return OwnershipState.NotUnlocked;
return OwnershipState.OwnedAndUnlocked;
```

The predicate is `IsOwned || !IsPremium` — a non-premium part passes
regardless of ownership. This is the gate behind the `OnPartNotOwned`
parameter on `PartsLoader.CreateParts` and behind
`BuildState.SpawnBlueprint`'s filtering (§D5), and it is the most
likely content of the unread `Rocket.CanUsePart` check flagged in §B1.9.
An agent generating blueprints should call this per part before
spawning, rather than discovering the rejection downstream.

**`CareerState.main` is dereferenced without a null check** — calling
this outside a loaded career context is an NRE, not a `NotUnlocked`.

### B3.6 Other confirmed members

| Member | Signature | Note |
|---|---|---|
| `Rocket` | `Rocket { get; set; }` | `set_Rocket` is the `INJ_Rocket` impl — `final virtual`, but **public**, so unlike §B1.6 it reflects normally |
| `Position` | `Vector2 { get; set; }` | wraps `transform.position` |
| `GetClickPolygons()` | `List<PolygonData>` | feeds `Rocket.UseParts` (§B1.9) |
| `GetBuildColliderPolygons(bool forAttach = …)` | `(ConvexPolygon[], bool)` | build-time geometry |
| `GetAttachmentSurfacesWorld()` | `Line2[]` | **world-space attach lines** — the geometry an auto-assembler needs |
| `IsFront()` | `bool` | |
| `RegenerateMesh()` | `void` | call after changing variables to refresh visuals |
| `SetSortingLayer(string)` | `void` | forwards to every `BaseMesh` |
| `DrawPartStats(Part[], StatsMenu, PartDrawSettings)` | `void` | UI |

Bodies for `GetClickPolygons`, `GetBuildColliderPolygons`,
`GetAttachmentSurfacesWorld` and `IsFront` are **not read** —
[PARTIAL], signatures only.

### B3.7 Status

| Item | Status |
|---|---|
| `Part : HeatModuleBase, INJ_Rocket` | **[CONFIRMED]** |
| Full field layout, 20 fields | **[CONFIRMED]** |
| `mass` / `centerOfMass` are `Composed_*` (parametric) | **[CONFIRMED]** |
| `GetModules<T>` is a lazy memo keyed by short type name | **[CONFIRMED]** |
| Walking `modules` under-reports | **[CONFIRMED]** |
| Short-name key collision → `InvalidCastException` | **[CONFIRMED]** (mechanism) / **[OPEN]** (never observed) |
| `Part.modules` never cleared | **[CONFIRMED]** — grep-exhaustive |
| `Part.HeatTolerance` hardcoded `Low` → 412 °C break | **[CONFIRMED]** |
| `Part.Temperature` == `temperature` field | **[CONFIRMED]** — refines §D1 |
| `OnOverheat` is an ambiguous 2-overload name | **[CONFIRMED]** |
| `DestroyPart` body, explosion size `mass*2+0.5` | **[CONFIRMED]** |
| `GetOwnershipState` body + enum values | **[CONFIRMED]** |
| `CareerState.main` unguarded | **[CONFIRMED]** |
| `InitializePart` ordering comparison | **[PARTIAL]** — lambda unread |
| `aboutToDestroy` call sites | **[OPEN]** |
| Geometry method bodies | **[PARTIAL]** — signatures only |

---

## B4. `SFS.Parts.PartHolder`

```
.class public auto ansi beforefieldinit PartHolder    @238276
    extends UnityEngine.MonoBehaviour
```

The craft's part collection, and the **correct** place to ask "what
modules does this rocket have".

### B4.1 Fields [CONFIRMED]

| Field | Type |
|---|---|
| `parts` | `List<Part>` *(public)* |
| `partsSet` | `HashSet<Part>` *(public)* |
| `onPartsAdded`, `onPartsRemoved` | `Action<Part[]>` *(public)* |
| `onPartsChanged` | `Action` *(public)* |
| `cachedArray` *(private)* | `Part[]` |
| `modules`, `moduleCount` *(private)* | `Dictionary<string, object>` / `<string, int>` |

`parts` and `partsSet` are parallel containers — `parts` for order,
`partsSet` for `ContainsPart` in O(1). Mutating `parts` directly desyncs
them; use the mutators.

### B4.2 The module cache — same shape as `Part`, but invalidated [CONFIRMED]

```csharp
public T[] GetModules<T>() {
    string key = typeof(T).Name;
    if (!modules.ContainsKey(key)) modules.Add(key, CollectModules<T>());
    return (T[])modules[key];
}

private T[] CollectModules<T>() {
    var list = new List<T>();
    foreach (Part p in parts) {
        var m = p.GetModules<T>();               // delegates to §B3.2
        if (m.Any()) list.AddRange(m);
    }
    return list.ToArray();
}
```

Same short-name key, same `castclass`, same collision risk as §B3.2.
**The difference that matters: `PartHolder` clears its cache.**
`ResetModules()` @238795 (`modules.Clear(); moduleCount.Clear();`) is
called from all six mutators — `AddParts` @238332, `AddPartAtIndex`
@238375, `RemoveParts` @238450, `RemovePartAtIndex` @238499, `SetParts`
@238553, `ClearParts` @238607. So after staging or a collision the
holder's answer is fresh, while the surviving parts' own caches are not
(harmless, since a part's own components don't change).

`GetArray()` @238289 memoises `parts.ToArray()` into `cachedArray`.
`ResetModules` does not touch it — but each of the six mutators nulls it
itself, on the instruction immediately preceding its `ResetModules()`
call (`ldnull; stfld cachedArray` at @238330, @238373, @238448, @238497,
@238551, @238605). `grep` on `PartHolder::cachedArray` returns exactly
nine sites: three in `GetArray` and those six. **`GetArray()` is
correctly invalidated on every structure change** and is safe to use.

### B4.3 Subscriptions [CONFIRMED signature, PARTIAL body]

```csharp
void TrackParts(Action<Part> onPartAdded, Action<Part> onPartRemoved,
                Action onPartRemoved_After);
void TrackModules<T>(Action<T> onModuleAdded, Action<T> onModuleRemoved,
                     Action onModulesRemoved_After);
```

`TrackModules<T>` is the clean way for an agent to react to engines
appearing or disappearing (staging, docking) without polling — it is
what `Rocket.Awake` uses for `ControlModule` (§B1.5, `b__17_0`/`b__17_1`).
Bodies not read.

### B4.4 How to enumerate a craft's modules, correctly

```csharp
// PREFERRED — fresh, cache-invalidated, whole craft:
MethodInfo gm = partHolder.GetType().GetMethod("GetModules")
                          .MakeGenericMethod(moduleType);
Array mods = (Array)gm.Invoke(partHolder, null);

// Cache-free alternative, bypasses the short-name key entirely:
Component[] mods = partHolder.GetComponentsInChildren(moduleType, true);
```

Do **not** enumerate either `modules` dictionary. Do not assume
`GetArray()` is current.

### B4.5 Status

| Item | Status |
|---|---|
| `PartHolder : MonoBehaviour`, field layout | **[CONFIRMED]** |
| `GetModules<T>` / `CollectModules<T>` bodies | **[CONFIRMED]** |
| `ResetModules` called by all six mutators | **[CONFIRMED]** — grep-exhaustive |
| Short-name key collision risk (inherited from §B3.2) | **[CONFIRMED]** (mechanism) |
| `GetArray()` caches; all six mutators null it themselves | **[CONFIRMED]** — grep-exhaustive |
| `TrackParts` / `TrackModules<T>` bodies | **[PARTIAL]** — signatures only |

---

## B5. `Physics`, `Trajectory`, `Orbit` — and the `Kepler` library

§D4 covered SOI crossing from the `Physics` side. This section covers
the orbital model itself, and the single most useful discovery in the
B-tier: **the game ships a complete, public, static orbital-mechanics
library.** An agent planning burns does not need to reimplement Kepler.

### B5.1 `SFS.World.Physics` [CONFIRMED]

```
.class public auto ansi beforefieldinit Physics    @159119
```

| Field | Type |
|---|---|
| `location` | `WorldLocation` *(public)* |
| `loader` | `WorldLoader` *(public)* |
| `trajectory` | `Trajectory` *(public)* |
| `savedObject` *(private)* | `I_Physics` |
| `lastTrajectory_Input` *(private)* | `(Double2, Double2, double)` |
| `lastTrajectory` *(private)* | `Trajectory` |

`PhysicsObject` / `PhysicsMode` are public properties here — **use these
rather than `Rocket`'s explicit `I_Physics` implementations** (§B1.6),
which reflect badly. `rocket.physics.PhysicsMode` is the clean read.

`SetLocationAndState(Location newLocation, bool physicsMode)` @159246 is
**the teleport entry point** — public, and the physics-mode branch is:

```csharp
location.Value = newLocation;                                   // §B2.2 guard applies
PhysicsObject.LocalPosition = WorldView.ToLocalPosition(location.position);
PhysicsObject.LocalVelocity = WorldView.ToLocalVelocity(location.velocity);
PhysicsObject.PhysicsMode   = true;
trajectory = null;                                              // forces recompute
```

Note the `WorldView.ToLocalPosition` / `ToLocalVelocity` conversions:
world (`Double2`, planet-relative, metres) and Unity-local (`Vector2`)
are **different frames**, and this is the sanctioned bridge. The
`location.Value` write goes through `WorldLocation.set_Value`, so **a
`Location` with a null planet silently does nothing here too** — the
teleport appears to succeed and the craft does not move.

`InOrbit()` @159595 is a useful one-liner:

```csharp
Orbit o = Orbit.TryCreateOrbit(location.Value, false, false, out bool success);
return success && o.periapsis > o.Planet.OrbitRadius;
```

"In orbit" means **periapsis above the planet's `OrbitRadius`**, not
above the surface and not "eccentricity < 1". `OrbitRadius` is a
`Planet` property (see §D4) distinct from `Radius`.

`GetTrajectory()` @159766 memoises on a `(position, velocity, time)`
tuple and — note — back-projects position by one frame
(`position - LocalVelocity * Time.deltaTime`) before hashing. So
successive calls in one frame are cheap, and the trajectory is computed
from a position one `deltaTime` behind the current one. The full shape:

```csharp
Trajectory GetTrajectory() {
    if (PhysicsObject.PhysicsMode) {
        var key = (location.Value.position - PhysicsObject.LocalVelocity * Time.deltaTime,
                   location.Value.velocity, location.Value.time);
        if (key != lastTrajectory_Input) {
            lastTrajectory_Input = key;
            lastTrajectory = Trajectory.CreateTrajectory(location.Value);
        }
        return lastTrajectory;          // physics mode
    }
    return trajectory;                  // rails only
}
```

**The public `trajectory` field is maintained only on rails.** In physics
mode the live answer is the private `lastTrajectory`, and `trajectory`
holds whatever was last written by `set_PhysicsMode` / `SetLocationAndState`
— which `SetLocationAndState` sets to `null` outright (§B5.1 above).
**Always call `GetTrajectory()`; never read the `trajectory` field.**
This confirms, from IL, a gotcha recorded empirically in the earlier
`sfs_source_reference.md` ("`.trajectory` field is STALE except on rails").

Note also `set_PhysicsMode(true)` @159169 **rebases the craft from the
trajectory before enabling physics**:
`location.Value = trajectory.GetLocation(WorldTime.main.worldTime)`, then
pushes position and velocity through `WorldView.ToLocalPosition` /
`ToLocalVelocity` (§E5.2). So leaving rails snaps the craft onto the
analytic path — a small discontinuity an agent measuring position across
that transition will see.

### B5.2 `SFS.World.Trajectory` [CONFIRMED]

```
.class public auto ansi serializable beforefieldinit Trajectory   @195673
```

One public field: `List<I_Path> paths`. Almost every instance method is
a **forward to `paths[0]`** — `GetLocation(time)`, `GetPathEndTime()`,
`GetStopTimewarpTime(old, new)` all index element 0 with no bounds
check. An empty `Trajectory` (`Trajectory.Empty`) throws
`ArgumentOutOfRangeException` on any of them.

Statics: `Empty`, `CreateTrajectory(Location)`,
`CreateStationaryTrajectory(StaticWorldObject)`, `CreatePath(Location)`
— all public. `CreatePath(Location)` is the direct "what orbit would I
be on from this state vector" call.

`EnterNextPath()` @195863 is what §D4.3's SOI-crossing branch calls.

#### B5.2.1 Path transitions — bodies read [CONFIRMED]

*(Depth pass. This subsection replaces the earlier [PARTIAL] placeholder.)*

```csharp
public void CheckPathTransition(double time) {          // @195828
    if (time > GetPathEndTime()) EnterNextPath();
}

public void EnterNextPath() {                           // @195863
    if (paths.Count == 1) return;                       // never empties the list
    paths.RemoveAt(0);
    CalculatePaths();
}

public void CheckEncounters() {                         // @195845
    if (paths.Last().UpdateEncounters()) CalculatePaths();
}

private int ConicSectionsCount =>                       // @195886
    VideoSettingsPC.main.settings.orbitLinesCount;

private void CalculatePaths() {                         // @195899
    while (paths.Count < ConicSectionsCount) {
        if (!GetNextPath(out I_Path next)) return;
        paths.Add(next);
    }
}
```

Four things worth having in writing:

- **`EnterNextPath` cannot empty `paths`.** The `paths.Count == 1` guard
  returns early, so `paths[0]` is always valid — which is what makes
  `Trajectory`'s unchecked `paths[0]` forwarding (above) safe in
  practice, on a trajectory the game built. A hand-constructed
  `Trajectory.Empty` still throws.
- **`CheckPathTransition` uses a strict `>`.** Exactly at
  `GetPathEndTime()` the transition does not fire.
- **How far ahead the game predicts is a *video setting*.**
  `ConicSectionsCount` reads
  `VideoSettingsPC.main.settings.orbitLinesCount`. So the number of
  future conic sections computed — and therefore how many SOI
  transitions ahead a trajectory extends — **depends on the player's
  graphics options**, not on physics. An agent that plans against
  `trajectory.paths` is planning against a user-configurable horizon and
  must not assume a fixed depth. This is the single least obvious thing
  in this section.
- `CalculatePaths` stops early and silently whenever `GetNextPath`
  returns false, so a short `paths` list is normal, not an error.

#### B5.2.2 `GetNextPath` — the frame changes [CONFIRMED]

`private bool GetNextPath(out I_Path nextPath)` @195932. Transcribed:

```csharp
I_Path last = paths[paths.Count - 1];
if (!(last is Orbit) || last.NextPlanet == null) { nextPath = null; return false; }

if (last.PathType == PathType.Escape) {                 // leaving this SOI
    // bail-out: don't chain a third section after Encounter → Escape
    if (paths.Count > 1
        && paths[paths.Count - 2].PathType == PathType.Encounter
        && ConicSectionsCount == 3) { nextPath = null; return false; }

    Location craft  = last.GetLocation(last.PathEndTime);
    Location parent = last.Planet.orbit.GetLocation(last.PathEndTime);
    nextPath = CreatePath(craft + parent);              // Location.op_Addition
    return true;
}

if (last.PathType == PathType.Encounter) {              // entering a satellite's SOI
    Location craft  = last.GetLocation(last.PathEndTime);
    Location target = last.NextPlanet.orbit.GetLocation(last.PathEndTime);
    nextPath = CreatePath(new Location(
        last.PathEndTime, last.NextPlanet,
        craft.position - target.position,
        craft.velocity - target.velocity));
    return true;
}

nextPath = null; return false;
```

`PathType` values, confirmed from the enum's `literal` fields:
**`Eternal = 0`, `Escape = 1`, `Encounter = 2`.**

**The two branches are exact inverses, and together they are the game's
whole patched-conic frame algebra:**

- **Escape** *lifts* the state into the parent frame — add the craft's
  planet-relative state to the planet's own state in its parent's frame.
- **Encounter** *descends* into the satellite frame — subtract the
  target's state from the craft's.

**This resolves the `Location.op_Addition` [OPEN] left in §B2.1.**
@160891:

```csharp
public static Location operator +(Location a, Location b)
    => new Location(b.time, b.planet,
                    a.position + b.position,
                    a.velocity + b.velocity);
```

It takes **`time` and `planet` from the right operand** and sums the
vectors — so it is **not commutative**, and it is not "adding two
locations" in any general sense. It is precisely a *frame lift*:
`childRelativeState + frameState` = the same state expressed in the
frame's own planet. Use it only that way. The Encounter branch does the
inverse by hand rather than defining an operator for it.

The `ConicSectionsCount == 3` bail-out is a deliberate truncation: at
the lowest orbit-line setting the game refuses to compute a third
section after an encounter-then-escape chain. **Another place the
prediction horizon depends on a video setting.**

### B5.3 `SFS.World.Orbit` — elements from a state vector [CONFIRMED]

Implements `I_Path`. The interesting constructor is
`Orbit(Location location, bool calculateTimeParameters, bool calculateEncounters)`
@192871, and `TryCreateOrbit(location, …, out bool success)` @192777 is
the non-throwing wrapper. The body, transcribed:

```csharp
orbitStartTime = location.time;
Double3 h = Double3.Cross(location.position, location.velocity);      // angular momentum
Double2 eVec = (Double2)(Double3.Cross((Double3)location.velocity, h)
                         / location.planet.mass)
             - location.position.normalized;                          // eccentricity vector
ecc = eVec.magnitude;
sma = location.planet.mass
    / -(2.0 * (Math.Pow(location.velocity.magnitude, 2.0) / 2.0
               - location.planet.mass / location.Radius));            // vis-viva
semiMinorAxis = Kepler.GetSemiMinorAxis(sma, ecc);
periapsis     = Kepler.GetPeriapsis(sma, ecc);
apoapsis      = Kepler.GetApoapsis(sma, ecc);
arg           = eVec.AngleRadians;
arg_Matrix    = Matrix2x2_Double.Angle(arg);
slr           = Kepler.GetSemiLatusRectum(periapsis, ecc);            // NB: from periapsis
direction     = Math.Sign(h.z);
bool escapes  = apoapsis >= location.planet.SOI;
trueAnomaly_Out = Kepler.NormalizeAngle(location.position.AngleRadians - arg);
location_Out    = location;
if (calculateTimeParameters) {
    period     = escapes ? 0.0 : Kepler.GetPeriod(sma, location.planet.mass);
    meanMotion = Kepler.GetMeanMotion(sma, location.planet.mass);
    ...
}
```

**`Planet.mass` is the standard gravitational parameter μ = GM, not a
mass in kilograms.** This is confirmed three independent ways: the
vis-viva expression above divides it by radius to get a specific energy;
`Kepler.GetPeriod(sma, mass) = τ·√(sma³/mass)`; and
`Kepler.GetMass(g, r) = g·r²`. Treating `Planet.mass` as kilograms — or
multiplying it by G — is wrong by ~10¹⁰.

This is **not** a new finding: `sfs_physics_reference.md` §2.1 already
states "μ is read directly from `Planet.mass`", validated to 0.008–0.13%
against live gravity. The three IL derivations above are independent
confirmation of that, from code rather than measurement, and extend it
to the orbital-element path. The trap is worth restating only because
the field's *name* invites the wrong reading.

Two more traps in the same body:

- **`period` is `0.0` for any orbit whose apoapsis reaches the SOI**,
  including every hyperbolic and every escape trajectory. It is not
  `Infinity` and not a small number — code that divides by `period`
  gets a division by zero.
- `slr` is computed from **periapsis**, not from `sma`
  (`GetSemiLatusRectum(p, e) = p·(1 + e)`). Passing `sma` there is a
  silent error.

Position and velocity sampling, all public:

```csharp
Double2 GetPositionAtAngle(double angleRadians);
Double2 GetPositionAtTrueAnomaly(double trueAnomaly);
Double2 GetVelocityAtAngle(double angleRadians);      // => GetVelocityAtTrueAnomaly(angle - arg)
Double2 GetVelocityAtTrueAnomaly(double trueAnomaly);
Double2 GetPositionFromEccentricAnomaly(double E);    // branches on ecc < 1: cos/sin vs cosh/sinh
Location GetLocation(double time);                    // I_Path
double   GetTrueAnomaly(double time);
double   GetNextAnglePassTime(double time, double angleRadians);
double   GetLastAnglePassTime(double time, double angleRadians);
double   GetNextTrueAnomalyPassTime(double time, double trueAnomaly);
double   GetLastTrueAnomalyPassTime(double time, double trueAnomaly);
```

`GetVelocityAtTrueAnomaly` @194559 composes the library directly:

```csharp
double r = Kepler.GetRadiusAtTrueAnomaly(slr, ecc, trueAnomaly);
double E = Kepler.GetEccentricAnomalyFromTrueAnomaly(trueAnomaly, ecc);
return Kepler.GetVelocity(sma, r, meanMotion, E, ecc, arg, direction);
```

`GetPositionFromEccentricAnomaly` @194453 **handles hyperbolic orbits**
— `ecc < 1` uses `(cos E − e)·sma, sin E·semiMinorAxis`; otherwise the
`cosh`/`sinh` branch with negated axes. So escape trajectories are
first-class, not an error case.

`GetNextAnglePassTime` / `GetLastAnglePassTime` are the **direct answer
to "when will I be at this point in the orbit"** — the primitive a
maneuver planner needs, already written and already correct for the
game's own model.

`Orbit` also carries `orbitStartTime` / `orbitEndTime`, `pathType`
(`SFS.World.PathType` — `Eternal=0, Escape=1, Encounter=2`),
`periapsisPassageTime`, and an `encounterText` `Func<string>`.
`private static Dictionary<int, Vector3[]> ellipseCache` and the
`GetPoints*` family are map rendering, not physics.

#### B5.3.1 Encounter search — bodies read [CONFIRMED]

*(Depth pass. Replaces the earlier [PARTIAL] placeholder.)*

Four methods, outermost first.

```csharp
public bool UpdateEncounters() {                        // @194999
    if (pathType != PathType.Eternal) return false;     // already resolved
    double start = Math.Max(orbitStartTime, WorldTime.main.worldTime);
    double end   = start + period * 0.9;
    return FindEncounters(start, end);
}
```

**Only `Eternal` orbits are searched** — one already carrying an
`Escape` or `Encounter` is left alone. The window is **0.9 of one
period**, not a full period, so a search never wraps past its own start.
Note `period` is `0.0` for SOI-escaping orbits (§B5.3), but those are
never `Eternal`, so the degenerate zero-length window is unreachable —
the two facts are consistent, not a latent bug.

```csharp
private bool FindEncounters(double window_Start, double window_End) {   // @195035
    foreach (Planet sat in location_Out.planet.satellites) {
        if (apoapsis  > sat.orbit.periapsis - sat.SOI + 0.1 &&
            periapsis < sat.orbit.apoapsis  + sat.SOI - 0.1) {
            if (ProcessEncounters(sat, window_Start,
                                  Math.Min(window_End, orbitEndTime))) return true;
        }
    }
    return false;
}
```

A **radial-overlap pre-filter**: unless the craft's annulus
(`periapsis`…`apoapsis`) overlaps the satellite's swept band
(`sat.orbit.periapsis − SOI` … `sat.orbit.apoapsis + SOI`), the
satellite is skipped without any iteration. The `± 0.1` is the class's
`private const double Margin = 0.1` used as a shrink, i.e. a
**conservative** filter that can reject a grazing case. First hit wins —
satellites are tested in array order, and the search returns on the
first success rather than picking the earliest encounter.

```csharp
private bool ProcessEncounters(Planet satellite,                        // @195112
                               double window_Start, double window_End) {
    double maxAcceleration = 2.0 * location_Out.planet.GetGravity(
                                       satellite.orbit.periapsis - satellite.SOI);
    double time = window_Start;
    for (int i = 0; i < 100; i++) {
        if (time >= window_End) return false;
        if (GetFastestPossibleArrivalTime(ref time, satellite, maxAcceleration)) {
            SetEncounter(satellite, time, <>c.b__56_0);   // encounterText
            return true;
        }
    }
    return false;
}
```

**A bounded iterative advance, capped at 100 steps** (`ldc.i4.s 0x64`).
`maxAcceleration` is **twice** the parent's gravity at the satellite's
closest approach radius — a deliberate over-estimate, which is what
makes each step a *safe lower bound* on arrival time rather than a
guess. On success it calls the public `SetEncounter`, which sets
`pathType`, `orbitEndTime` and `encounterText`.

Two failure modes are silent and indistinguishable from "no encounter":
running past `window_End`, and exhausting the 100 iterations. An agent
cannot tell "no encounter exists" from "the search gave up" from the
return value alone.

```csharp
private bool GetFastestPossibleArrivalTime(ref double time,             // @195183
                                           Planet satellite,
                                           double maxAcceleration) {
    Double2 craftPos = GetLocation(time).position;

    // (a) inside the satellite's inner exclusion radius -> skip ahead by orbit geometry
    if (craftPos.Mag_LessThan(satellite.orbit.periapsis - satellite.SOI + 0.1)) {
        double t = GetNextTrueAnomalyPassTime(time,
            Kepler.GetTrueAnomalyAtRadius(this, satellite.orbit.periapsis - satellite.SOI)
            * direction);
        if (t == time) t += 1.0;                    // guard against a stuck step
        time = t; return false;
    }
    // (b) outside the outer radius -> symmetric skip (same shape, apoapsis + SOI)
    ...
    // (c) in the band: measure the real approach
    Double2 rel      = satellite.GetLocation(time).position - craftPos;
    Double2 relVel   = satellite.GetLocation(time).velocity - GetLocation(time).velocity;
    double  closing  = relVel.Rotate(-rel.AngleRadians).x;   // component along the line
    double  gap      = rel.magnitude - satellite.SOI;

    if (gap < 0.1 && closing < 0.0) return true;             // arrived, and approaching
    time += GetFallTime(closing, gap, maxAcceleration);
    ...
    return false;
}
```

`closing` is obtained by rotating the relative velocity by minus the
relative-position angle and taking `.x` — i.e. the component **along the
line joining the two bodies** (§B2.3's `Rotate`). Negative means closing.

```csharp
private double GetFallTime(double verticalVelocity,                     // @195410
                           double startHeight, double gravity)
    => Math.Sqrt((startHeight + verticalVelocity * verticalVelocity / (2.0 * gravity))
                 * 2.0 / gravity)
     + verticalVelocity / gravity;
```

Constant-acceleration time-to-close from `startHeight` with initial
separation rate `verticalVelocity`. With `gravity` deliberately
**over**-estimated in `ProcessEncounters`, this returns a time no later
than the true arrival — so advancing by it can never step past an
encounter. That is the invariant the whole search rests on.

**For an agent:** the search is a conservative forward stepper over one
0.9-period window per `Eternal` orbit, per satellite, capped at 100
steps, returning the first satellite that works. It is cheap enough to
call, but it answers "is there an encounter on this conic" — **not**
"what is the best transfer". Do not mistake `UpdateEncounters` for a
maneuver planner.

The bail-outs marked `...` above (branch (b), and the tail after the
`GetFallTime` advance) were **not transcribed instruction-by-instruction**
— structure and constants confirmed, exact bounds arithmetic on the
outer-radius branch is **[PARTIAL]**.

### B5.4 `Kepler` — the public static orbital library [CONFIRMED]

```
.class public auto ansi abstract sealed beforefieldinit Kepler   @26996
```

`abstract sealed` = C# `static class`, global namespace. Constants:
`Tau = 6.283185307179586`, `Tolerance = 1e-7`, `MaxIterations = 50`
(`0x32`).

Every method is `public static`. Confirmed formulas (bodies read):

| Method | Body |
|---|---|
| `GetPeriapsis(sma, e)` | `sma * (1 - e)` |
| `GetApoapsis(sma, e)` | `e < 1 ? sma * (1 + e) : double.PositiveInfinity` |
| `GetSemiMajorAxis(peri, e)` | — |
| `GetSemiMinorAxis(sma, e)` | `e < 1 ? sma*√(1-e²)` ; `e > 1` branch uses `e²-1` |
| `GetMass(g, r)` | `g * r * r` — **μ from surface gravity and radius** |
| `GetSemiLatusRectum(p, e)` | `p * (1 + e)`, `p` = **periapsis** |
| `GetPeriapsisFromSemiLatusRectum(l, e)` | — |
| `GetPeriod(sma, mass)` | `τ * √(sma³ / mass)` |
| `GetMeanMotion(sma, mass)` | uses `\|sma\|` — safe for hyperbolic |
| `GetSphereOfInfluence(sma, mass, parentMass, multiplier)` | `sma * (mass/parentMass)^0.4 * multiplier` |
| `GetEscapeVelocity(planet, radius)` | `√(2 * planet.mass / radius)` |
| `NormalizeAngle(a)` | wraps to **(−π, π]** by repeated ±τ |
| `PositiveAngle(a)` | wraps to **[0, τ)** |

Also public, bodies **not read** but signatures confirmed:
`GetAngleDiff(from, to, direction)`, `ToTauRange(a)`,
`GetTrueAnomalyFromEccentricAnomaly(E, e)`,
`GetEccentricAnomalyFromTrueAnomaly(v, e)`,
`GetRadiusAtAngle(Orbit, angleRadians)`,
`GetRadiusAtTrueAnomaly(l, e, v)`,
`GetTrueAnomalyAtRadius(r, l, e)` **and** `GetTrueAnomalyAtRadius(Orbit, r)`
(**ambiguous pair**), `GetVelocity(sma, r, n, E, e, arg, direction)`,
`GetVelocityNormal(E, e, arg)`, `GetMeanAnomaly(e, v)`,
`GetTimeToPeriapsis(r, e, l, meanMotion)` **and**
`GetTimeToPeriapsis(trueAnomaly, e, meanMotion, direction)`
(**ambiguous pair**), `GetPosition(r, trueAnomaly, arg)`,
`GetEccentricAnomaly(M, e)`.

`GetEccentricAnomaly(M, e)` dispatches to three private solvers —
`GetEccentricAnomalyElliptical`, `…ExtremeEccentricity`, `…Hyperbolic`
— iterating to `Tolerance = 1e-7` in at most 50 steps. **The elliptical,
near-parabolic and hyperbolic cases are all handled**; there is no
regime where the game silently returns garbage.

**For the agent this means:** maneuver planning should call `Kepler`
and `Orbit` through reflection rather than reimplementing them in
Python. The game's answers are the ones the game will act on, including
its own difficulty scaling (§D4.2) and its own definition of "in orbit"
(§B5.1). A Python reimplementation would be a second model to keep in
sync, and §1.2's data-trust rule applies with full force.

### B5.5 Status

| Item | Status |
|---|---|
| `Physics` field layout; public `PhysicsMode` / `PhysicsObject` | **[CONFIRMED]** |
| `SetLocationAndState` body (teleport) | **[CONFIRMED]** |
| Null-planet teleport silently no-ops | **[CONFIRMED]** — via §B2.2 |
| `InOrbit()` = `periapsis > Planet.OrbitRadius` | **[CONFIRMED]** |
| `GetTrajectory` memo + one-frame back-projection | **[CONFIRMED]** |
| `Trajectory` forwards to `paths[0]`, unchecked | **[CONFIRMED]** |
| `Orbit(Location, …)` element derivation | **[CONFIRMED]** |
| **`Planet.mass` is μ = GM, not kilograms** | **[CONFIRMED]** — three ways |
| `period == 0.0` for SOI-escaping orbits | **[CONFIRMED]** |
| `slr` derives from periapsis, not sma | **[CONFIRMED]** |
| Hyperbolic orbits handled (`cosh`/`sinh` branch) | **[CONFIRMED]** |
| `Kepler` is a public static library, 30 methods | **[CONFIRMED]** |
| The 13 formulas tabulated above | **[CONFIRMED]** |
| `GetEccentricAnomaly` 3-solver dispatch, 1e-7 / 50 iter | **[CONFIRMED]** |
| `Kepler` methods not tabulated | **[PARTIAL]** — signatures only |
| Encounter search (`FindEncounters` etc.) | **[PARTIAL]** |
| `Trajectory` path-transition machinery | **[PARTIAL]** |
| Calling `Kepler`/`Orbit` from the probe | **[UNTESTED-LIVE]** |

---

## B6. `SFS.Parts.Mass_Calculator`

```
.class public auto ansi beforefieldinit Mass_Calculator    @235824
```

Small class, but it closes the loop between §E4's expression evaluator
and the rigidbody, and it has a timewarp gate worth knowing about.

| Field | Type | |
|---|---|---|
| `partHolder` | `PartHolder` | public |
| `dirty` | `bool` | private |
| `mass` | `float` | private |
| `centerOfMass` | `Vector2` | private |

### B6.1 The calculation [CONFIRMED]

`GetMass()` @235889 and `GetCenterOfMass()` @235903 both call
`Calculate()` first, so **they are always current** — no caller has to
remember to refresh. `Calculate()` @235917:

```csharp
if (!dirty) return;
mass = 0f;
centerOfMass = Vector2.zero;
foreach (Part p in partHolder.parts) {
    mass += p.mass.Value;
    centerOfMass += (p.Position + (p.centerOfMass.Value * p.orientation))
                  * p.mass.Value;
}
centerOfMass /= mass;
dirty = false;
```

A plain mass-weighted centroid. Two details:

- Each part's local `centerOfMass` is run through
  `OrientationModule.op_Multiply(Vector2, OrientationModule)` before
  being added to `Position` — **mirrored and rotated parts have their
  CoM offset transformed**, so an agent computing CoM itself must apply
  the orientation, not just the position.
- **`centerOfMass /= mass` is unguarded.** A craft with zero total mass
  yields NaN, and `Rocket.UpdateMass` (§B1.2) writes that straight into
  `rb2d.centerOfMass` every tick. Not reachable with real parts; worth
  knowing if an agent ever constructs a degenerate craft.

### B6.2 Invalidation — and why mass tracks fuel burn [CONFIRMED]

`Start()` @235833 wires three things:

```csharp
partHolder.TrackParts(b__1_0, b__1_1, MarkDirty);          // add / remove / after-remove
WorldTime.main.realtimePhysics.OnChange += MarkDirty;
```

and the per-part handlers @236016 / @236046 subscribe and unsubscribe
`MarkDirty` on **that part's `mass.OnChange` and `centerOfMass.OnChange`**
— the `Composed<T>` change events from §E4.

**This is the mechanism by which craft mass follows fuel burn.** A
`ResourceModule` write changes a variable → the part's `Composed_Float
mass` recomputes → its `OnChange` fires → `MarkDirty` → the next
`GetMass()` recalculates. Nothing polls. It also means an agent that
writes a part variable directly (§E4's `SetValue`) gets a correct
`rb2d.mass` on the next tick for free.

`MarkDirty()` @235867 has the gate:

```csharp
if (WorldTime.main != null && !WorldTime.main.realtimePhysics.Value) return;
dirty = true;
```

**Mass changes are ignored while `realtimePhysics` is false** — i.e. on
rails / during timewarp, the same flag that gates heating in §D1. The
`realtimePhysics.OnChange += MarkDirty` subscription is what repairs
this: when the flag goes false→true, `MarkDirty` runs *after* the flag
is already true, so it sets `dirty` and the first post-timewarp read
recalculates. Leaving timewarp is therefore safe; reading `GetMass()`
*during* timewarp can return a value that predates any mass change made
while warping.

### B6.3 Status

| Item | Status |
|---|---|
| Field layout; `GetMass`/`GetCenterOfMass` always call `Calculate` | **[CONFIRMED]** |
| Mass-weighted centroid formula, orientation-transformed CoM | **[CONFIRMED]** |
| `centerOfMass /= mass` unguarded → NaN at zero mass | **[CONFIRMED]** |
| Invalidation via per-part `Composed<T>.OnChange` | **[CONFIRMED]** |
| `MarkDirty` suppressed while `!realtimePhysics` | **[CONFIRMED]** |
| `realtimePhysics.OnChange` repairs it on timewarp exit | **[CONFIRMED]** |
| Stale mass during timewarp observed in game | **[UNTESTED-LIVE]** |

---

## B7. `SFS.World.Staging` and `SFS.World.Stage`

Signatures confirmed; **most bodies not read** — this section is
deliberately [PARTIAL] and says so per item.

### B7.1 `Staging` [CONFIRMED layout]

```
.class public auto ansi beforefieldinit Staging    @183261
```

| Field | Type |
|---|---|
| `rocket` | `Rocket` |
| `editMode` | `Bool_Local` |
| `stages` | `List<Stage>` |
| `onStageAdded` | `Action<Stage, int>` |
| `onStageRemoved` | `Action<Stage>` |

All public. `stages` is the ordered stage list; index 0 is the next to
fire (not verified — [OPEN]).

| Method | Access | Status |
|---|---|---|
| `ClearStages(bool record)` | public | signature |
| `InsertStage(Stage a, bool record, int index = …)` | public | signature |
| `RemoveStage(Stage a, bool record)` | public | signature |
| `ApplyReorder(Dictionary<Stage, int> order)` | public | signature |
| `Load(StageSave[] stageSaves, Part[] parts, bool record)` | public | signature |
| `CreateStages(StageSave[] stages, Part[] parts)` | **public static** | signature |
| `OnSplit(Rocket parentRocket, Rocket childRocket)` | **public static** | signature |
| `OnMerge(Rocket A, Rocket B)` | **public static** | signature |
| `GetPartGridType(Part part, out int index)` | **public static** | signature |
| `SetStages`, `RemoveEmptyStages`, `GetForUndo` | private | signature |

The `bool record` parameter throughout is **undo-system bookkeeping**
(`SFS.Builds.Undo/GridType` appears in `GetForUndo`), not persistence.
An agent manipulating stages programmatically should pass `false`
unless it wants entries in the editor's undo stack. **Not verified** —
the parameter's effect is inferred from `GetForUndo`'s return type,
which is exactly the kind of name-based inference this document is
meant to avoid. Marked **[OPEN]** until a body is read.

`OnSplit` / `OnMerge` are the hooks that redistribute stages when a
craft separates or docks — directly relevant to modelling what happens
to the staging plan after separation. Bodies **not read** — [PARTIAL].

`Load(StageSave[], Part[], bool)` and the static
`CreateStages(StageSave[], Part[])` are the bridge from the save format
(§D5) to live `Stage` objects, and both are public — the route for
building a staging plan programmatically alongside
`RocketManager.SpawnBlueprint`. Bodies **not read** — [PARTIAL].

### B7.2 `Stage` [CONFIRMED layout]

```
.class public auto ansi serializable beforefieldinit Stage    @184226
```

| Field | Type |
|---|---|
| `stageId` | `int` |
| `parts` | `List<Part>` |
| `usedToHaveParts` | `bool` |
| `onPartInserted` | `Action<Part, int>` |
| `onPartRemoved` | `Action<int>` |
| `useStageIdentifier` | `int` |

All public; the class is `[Serializable]`. `PartCount` is a property
over `parts`; `Contains(Part)` is a list search.

Mutators — `ToggleSelected(Part, bool crateNewStep)` *(sic, the
misspelling is in the shipped IL)*, `AddPart(Part, bool record, bool
createNewStep)`, `InsertPart(Part, int index, bool record)`,
`RemovePart(Part, bool record)`, `SetPartAtIndex(int, Part)` — plus a
private `OnPartDestroyed(Part)`. All **signatures only**, [PARTIAL].

`useStageIdentifier` and `usedToHaveParts` have no read call sites in
this section's work — [OPEN].

### B7.3 Status

| Item | Status |
|---|---|
| `Staging` and `Stage` field layouts | **[CONFIRMED]** |
| Full method signatures for both | **[CONFIRMED]** |
| `CreateStages` / `OnSplit` / `OnMerge` / `GetPartGridType` are public static | **[CONFIRMED]** |
| Every body in both classes | **[PARTIAL]** — not read |
| Meaning of the `record` parameter | **[OPEN]** — inferred only |
| Whether `stages[0]` is the next to fire | **[OPEN]** |
| `useStageIdentifier`, `usedToHaveParts` semantics | **[OPEN]** |

---

## E1. Resources and fuel flow

Five types cooperate: `ResourceType` (the substance), `ResourceModule`
(a tank or a *group* of tanks), `FlowModule` + its nested `Flow` (a
consumer's straw into those tanks), `FuelPipeModule` (cross-feed), and
`SFS.World.Resources` (the per-craft coordinator). §D2 covered how an
engine computes its mass flow; this section covers where the propellant
actually comes from.

### E1.1 `ResourceType` [CONFIRMED]

```
.class public auto ansi beforefieldinit ResourceType    @246649
```

| Field | Type |
|---|---|
| `displayName`, `resourceUnit` | `TranslationVariable` |
| `resourceMass` | `double` |
| `transferRate` | `double` |
| `density` | `float` |

A pure `ScriptableObject`-style data holder — no methods but the
constructor. **All five values are serialized Unity data, not IL
literals**, so per the project's data-trust rule they must be read
live; nothing in this document can tell you what `resourceMass` is for
liquid fuel.

Identity is by reference: `Resources.SetupResourceGroups` keys a
`Dictionary<ResourceType, …>` on the object itself, so two
`ResourceType` assets with identical fields are still distinct
resources.

### E1.2 `ResourceModule` — tanks, and the amount model [CONFIRMED]

```
.class public auto ansi beforefieldinit ResourceModule    @245548
```

| Field | Type | Note |
|---|---|---|
| `resourceType` | `ResourceType` | |
| `wetMass` | `Double_Reference` | full-tank mass |
| `dryMassPercent` | `Double_Reference` | fraction of `wetMass` that is structure |
| `resourcePercent` | `Double_Reference` | **fill fraction, 0–1 — this is the fuel gauge** |
| `mass` | `Double_Reference` | output, written by `RecalculateMass` |
| `setMass`, `setDensity` | `bool` | whether this module drives the part's mass/density |
| `parent` | `ResourceModule` | |
| `children` | `List<ResourceModule>` | |
| `flowModules` | `List<FlowModule.Flow>` | consumers attached to this module |
| `part` *(private)* | `Part` | |
| `showDescription` | `bool` | |

The quantity model, bodies read @245671–245763:

```csharp
double DryMassMultiplier {
    get {
        if (!Application.isPlaying || !Base.worldBase.insideWorld.Value) return 1.0;
        return Base.worldBase.settings.difficulty.DryMassMultiplier;
    }
}
double DryMassPercent        => dryMassPercent.Value * DryMassMultiplier;
double TotalResourceCapacity => (1.0 - DryMassPercent) * wetMass.Value;
double ResourceAmount        => TotalResourceCapacity * resourcePercent.Value;
double ResourceSpace         => TotalResourceCapacity * (1.0 - resourcePercent.Value);
```

**Fuel is stored as a fraction, never as an absolute quantity.**
`resourcePercent` is the only state; everything else is derived. An
agent reading "how much fuel is left" must multiply by
`TotalResourceCapacity`, and that capacity is **difficulty-scaled** —
`dryMassMultipliers = [1.0, 1.0, 0.25]` from §D1.5 means a Realistic
tank holds *more* propellant for the same `wetMass`, because less of it
is structure. The multiplier is bypassed (forced to 1.0) outside play
mode and outside a loaded world, which is exactly the condition under
which static asset parsing runs — another instance of the §E4 pattern
where offline reads are systematically wrong.

`RecalculateMass` @245831:

```csharp
mass.Value = DryMassPercent * wetMass.Value
           + ResourceAmount * resourceType.resourceMass;
if (setDensity)
    part.density.Value = Mathf.Lerp((float)DryMassPercent, 1f,
                                    (float)resourcePercent.Value)
                       * resourceType.density;
```

So a tank's mass is dry structure plus propellant, and `mass` is a
`Double_Reference` — writing into the variable system, which is what
propagates to `Part.mass` (a `Composed_Float`, §E4) and from there to
`Mass_Calculator` (§B6.2). **The full chain burn → mass loss is now
confirmed end to end**: `Flow.FlowNegative` → `TakeResource` →
`resourcePercent` write → `RecalculateMass` → `mass` variable →
`Part.mass` recompute → `Composed.onChange` → `MarkDirty` → `rb2d.mass`.

Withdrawal, `TakeResource(double takeAmount)` @245921:

```csharp
if (resourcePercent.Value == 0.0) return;              // exact compare
takeAmount = Math.Min(takeAmount, ResourceAmount);
TakeFromParent(takeAmount);
TakeFromChildren(1.0 - takeAmount / ResourceAmount);   // NB: re-reads ResourceAmount
resourcePercent.Value -= takeAmount / TotalResourceCapacity;
```

`TakeFromChildren` takes a **leftover fraction** and scales each child's
`resourcePercent` by it, so a group drains proportionally rather than
sequentially. `AddResource` @246040 mirrors this with
`AddToParent` / `AddToChildren`. The empty test is an exact `== 0.0`
comparison on a double that is repeatedly decremented — reaching exactly
zero is not guaranteed, which is a plausible source of a tank that reads
as non-empty at ~1e-17. **Not observed** — [OPEN].

`CreateGroup(List<ResourceModule>, GameObject)` @246190 is **public
static**: it builds a synthetic parent `ResourceModule` on a new
`GameObject` whose `children` are the real tanks. Group objects are
therefore `ResourceModule`s that own no part.

`ToggleTransfer()` @246172 is the public entry for the fuel-transfer UI.

`ResourceModule` implements `I_InitializePartModule` (with an explicit
`Priority`, feeding §B3.2's sorted `InitializePart`) and
`ResourceDrawer.I_Resource` — the latter **explicitly**, so
`ResourceType`, `WetMass` and `ResourcePercent` do not reflect off the
class by those names (same trap as §B1.6).

### E1.3 `FlowModule` and `FlowModule.Flow` — consumption [CONFIRMED]

`FlowModule` @243461 holds `Flow[] sources`, a private `massFlow`, and
an `onStateChange` event.

```csharp
void SetMassFlow(double newMassFlow) {
    if (newMassFlow == massFlow) return;               // exact compare
    massFlow = newMassFlow;
    double perUnit = GetMassFlowPerUnit();
    double unitRate = perUnit > 0.0 ? newMassFlow / perUnit : 1.0;
    foreach (Flow f in sources)
        f.flowRate.Value = unitRate * f.flowPercent;
    UpdateEnabled();
}

void FixedUpdate() { foreach (Flow f in sources) f.OnFixedUpdate(); }
```

**This is the seam between §D2 and E1.** An engine computes a mass flow
and calls `SetMassFlow`; the module splits it across its `Flow` entries
by `flowPercent`, normalised by `GetMassFlowPerUnit()`. A bicharge
engine (fuel + oxidiser) is two `Flow`s with different `resourceType`s
and different `flowPercent`s.

`Flow` (nested, @243876) fields: `resourceType`, `flowPercent`,
`sourceSearchMode` (`SourceMode`), `surface` (`SurfaceData`),
`flowType` (`FlowType`), `flowRate` (`Double_Reference`), `state`
(`State_Local`), `sources` (`ResourceModule[]`).

Two enums, values confirmed from the `literal` fields:

```
SourceMode : Global = 0, Surfaces = 1, Local = 2
FlowType   : Negative = 0, Positive = 1
```

`SourceMode` selects `GetGlobally` / `GetBySurfaces` / `GetLocally` —
i.e. draw from anywhere on the craft, only from tanks touching a named
surface, or only from this part. `FlowType` picks the direction:

```csharp
void OnFixedUpdate() {
    if (flowType == FlowType.Negative) { FlowNegative(); return; }   // consume
    if (flowType == FlowType.Positive) FlowPositive();               // fill
}
```

`FlowNegative` opens with the cheat check:

```csharp
if (SandboxSettings.main.settings.infiniteFuel) return;     // consumes nothing
double available = GetSourcesResourceAmount();
...
```

**Infinite fuel is implemented by skipping consumption entirely**, per
flow, per tick — not by refilling tanks. So with the cheat on,
`resourcePercent` never moves and craft mass never drops, which changes
the trajectory, not just the endurance. Anything the agent learns under
infinite fuel is learned on a different vehicle. This is the setting the
probe's `cheat` command touches.

`FlowPositive` @… is the symmetric fill path:

```csharp
double space = GetSourcesResourceSpace();
double frac  = Math.Min(flowRate.Value * Time.fixedDeltaTime / space, 1.0);
foreach (ResourceModule m in sources)
    m.AddResource(m.ResourceSpace * frac);
```

Note it divides by `space` with no zero guard — a full set of sources
gives `Infinity`, clamped to 1.0 by the `Math.Min`, so the degenerate
case happens to be safe.

`CanFlow(I_MsgLogger)` on `FlowModule` and
`Flow.CanFlow_ElseShowMsg(I_MsgLogger)` are the pre-flight checks that
produce "no fuel" style messages — useful to an agent as a *reason*
rather than a bare failure. Bodies **not read** — [PARTIAL].

### E1.4 `FuelPipeModule` — cross-feed [PARTIAL]

@244786. Fields `surface_In` / `surface_Out` (`SurfaceData`),
`previousPipes`, `resource_In`, `resource_Out`.

| Method | Access |
|---|---|
| `FindNeighbours(JointGroup group)` | public |
| `FindFlow()` → `(ResourceModule[], ResourceModule)?` | public |
| `FindFlowsForEngine(FlowModule.FlowType flowType)` → `List<ResourceModule>` | public |
| `FindFromTanks()` | private |
| `FixedUpdate_FuelPipeFlow(List<(ResourceModule[], ResourceModule)> flows)` | **public static** |

The static `FixedUpdate_FuelPipeFlow` is the one `Rocket.FixedUpdate`
calls with `Rocket.pipeFlows` (§B1.2) — pipes are driven from the craft,
not from the module's own `FixedUpdate`. Bodies **not read** —
[PARTIAL]. Cross-feed topology is therefore documented as structure
only.

### E1.5 `SFS.World.Resources` — per-craft coordination [CONFIRMED]

@182791. Fields: `groupsHolder` (`GameObject`), `localGroups`,
`globalGroups` (both `ResourceModule[]`), `boosters`
(`BoosterModule[]`), `transfers` (`List<Resources.Transfer>`),
`onGroupsSetup` (`Action`).

`SetupResourceGroups(Rocket rocket)` @182802:

```csharp
Destroy(globalGroups); Destroy(localGroups);            // old group GameObjects
foreach (List<ResourceModule> connected in rocket.jointsGroup.GetResourceGroups()) {
    ResourceModule group = ResourceModule.CreateGroup(connected, groupsHolder);
    localGroups.Add(group);
    byType[group.resourceType] ??= new List<ResourceModule>();
    byType[group.resourceType].Add(group);
}
boosters     = rocket.partHolder.GetModules<BoosterModule>();
globalGroups = byType.Values.Select(b__6_0).ToArray();   // one per resource type
onGroupsSetup?.Invoke();
```

**Fuel topology is derived from joint connectivity**, via
`JointGroup.GetResourceGroups()` (§E3) — not from part positions and not
from anything in the save file. `localGroups` is one group per connected
cluster per resource type; `globalGroups` is one group per resource
type across the whole craft. That is what `SourceMode.Global` vs
`SourceMode.Local` select between in §E1.3.

This runs on every structure change, and it **destroys and rebuilds the
group `GameObject`s**. Any reference an agent caches to a
`ResourceModule` group is invalidated by staging or docking; cache the
`Resources` component and re-read, or subscribe to `onGroupsSetup`.

`FixedUpdate` @182938 services `transfers`: each `Transfer` moves at
`resourceType.transferRate * WorldTime.FixedDeltaTime`, clamped by both
the source's `ResourceAmount` and the destination's capacity, with a
`1.000001` epsilon appearing in the completion test.
`ToggleTransfer(Part, ResourceModule)` @183033 and
`RemoveInvalidTransfers(PartHolder)` @183097 are the public mutators.
Bodies **partially read** — the clamping is confirmed, the exact
completion condition is [PARTIAL].

### E1.6 What an agent should read

| Question | Read |
|---|---|
| fuel fraction in one tank | `resourceModule.resourcePercent.Value` |
| fuel **quantity** in one tank | `resourceModule.ResourceAmount` (property — do not derive it yourself) |
| total per resource type on the craft | iterate `rocket.resources.globalGroups`, match `resourceType`, sum `ResourceAmount` |
| whether the craft is dry | `ResourceAmount == 0.0` on the relevant global group — **not** `resourcePercent`, which is per-tank |
| whether infinite fuel is on | `SandboxSettings.main.settings.infiniteFuel` |
| react to staging changing the fuel graph | subscribe `rocket.resources.onGroupsSetup` |

### E1.7 Status

| Item | Status |
|---|---|
| `ResourceType` field layout | **[CONFIRMED]** — values are live-only data |
| `ResourceModule` field layout | **[CONFIRMED]** |
| Capacity/amount/space formulas | **[CONFIRMED]** |
| Fuel stored as a fraction, not a quantity | **[CONFIRMED]** |
| `DryMassMultiplier` difficulty-scaled, bypassed offline | **[CONFIRMED]** |
| `RecalculateMass` body; burn → `rb2d.mass` chain end to end | **[CONFIRMED]** |
| `TakeResource` / proportional child draining | **[CONFIRMED]** |
| `CreateGroup` is public static | **[CONFIRMED]** |
| `SetMassFlow` splits by `flowPercent` | **[CONFIRMED]** |
| `SourceMode` and `FlowType` enum values | **[CONFIRMED]** |
| Infinite fuel skips consumption, does not refill | **[CONFIRMED]** |
| `FlowPositive` body | **[CONFIRMED]** |
| Fuel topology derives from `JointGroup.GetResourceGroups()` | **[CONFIRMED]** |
| Group `GameObject`s destroyed/rebuilt on every structure change | **[CONFIRMED]** |
| Exact `== 0.0` empty test may leave residue | **[OPEN]** — mechanism only |
| `FuelPipeModule` bodies | **[PARTIAL]** — signatures only |
| `CanFlow` / `CanFlow_ElseShowMsg` bodies | **[PARTIAL]** |
| `Resources.FixedUpdate` transfer completion condition | **[PARTIAL]** |
| `Flow.GetGlobally` / `GetBySurfaces` / `GetLocally` bodies | **[PARTIAL]** |

---

## E2. Control and input

Short section, one important finding: **the safety gates on control
input live in the UI layer, not in the model.** An agent that writes
the control variables directly is on a different code path from one
that simulates a keypress, and the two do not behave the same.

### E2.1 `SFS.World.Player` — the abstract base [CONFIRMED]

```
.class public auto ansi abstract beforefieldinit Player    @182697
```

| Field | Type |
|---|---|
| `location` | `WorldLocation` |
| `mapPlayer` | `MapPlayer` |
| `isPlayer` | `Bool_Local` |
| `hasControl` | `Bool_Local` |

Five abstract members, all overridden by `Rocket` (§B1):
`GetSizeRadius()`, `ClampTrackingOffset(ref Vector2, float)`,
`OnInputEnd_AsPlayer(OnInputEndData)`, `TryWorldSelect(TouchPosition)`,
`CanTimewarp(I_MsgLogger, bool, out bool)`.

`hasControl` and `isPlayer` are `Obs<bool>` (§A3.1), so an agent can
subscribe rather than poll. `Rocket` maintains `hasControl` from its
`ControlModule` set — `Rocket.Awake`'s `b__17_0` / `b__17_1` /
`g__UpdateControl|17_2` (§B1.5) recompute it as
`controlModules.Any(m => …)` whenever a `ControlModule` is added or
removed.

### E2.2 `SFS.World.Arrowkeys` — the input surface [CONFIRMED]

```
.class public auto ansi beforefieldinit Arrowkeys    @182636
```

Six fields, **all public `Obs<T>`, and the class has no methods at all**
beyond its constructor:

| Field | Type | Meaning |
|---|---|---|
| `rcs` | `Bool_Local` | RCS master toggle |
| `hasTurn` | `Bool_Local` | a turn key is held |
| `turnAxis` | `Float_Local` | rotation command, −1…+1 |
| `rawArrowkeysAxis` | `Vector2_Local` | undecomposed direction input |
| `horizontalAxis` | `Vector2_Local` | |
| `verticalAxis` | `Vector2_Local` | |

`Arrowkeys` is **pure state**. It validates nothing, clamps nothing, and
notifies nobody beyond the ordinary `Obs<T>` change events. Everything
that consumes it does so by reading:

- `Rocket.GetTurnAxis` reads `turnAxis` (§B1.3) — manual input
  overrides SAS whenever it is non-zero.
- `Rocket.FixedUpdate` reads `rcs`, `horizontalAxis`, `verticalAxis` to
  produce `output_DirectionalAxis` (§B1.2).
- `RcsModule.RCS_On` reads `rcs` (§D3).

### E2.3 The gates are in `ArrowkeysDrawer` [CONFIRMED] — the finding

`SFS.World.ArrowkeysDrawer` @161375 is the on-screen control pad: it
owns `SFS.UI.Button turnLeft/turnRight/left/right/up/down/rcsButton`,
three private `Float_Local` axes of its own, and two `MoveModule`
animations. It is the **only** thing in `Assembly-CSharp` that writes
`Arrowkeys.turnAxis`, `horizontalAxis`, `verticalAxis` or
`rawArrowkeysAxis` for a rocket. (`Astronaut_EVA.OnFixedUpdate` and
`OnJumpKeyDown` read them for EVA; `Rocket`, `RocketManager`,
`RocketSave` and `RcsModule` only read.)

`PushTurnAxis()` @161719 — the write path — is two guards and an assign:

```csharp
if (/* player lacks control */) {
    MsgDrawer.main.Log(Loc.main.No_Control_Msg);
    arrowkeys.Value.turnAxis.Value = 0f;
    return;
}
if (!WorldTime.main.realtimePhysics) {
    if (turn_Axis.Value != 0f)
        MsgDrawer.main.Log(Loc.main.Cannot_Turn_While_Timewarping);
    arrowkeys.Value.turnAxis.Value = 0f;
    return;
}
arrowkeys.Value.turnAxis.Value = turn_Axis.Value;
```

`PushDirectionalAxis()` @161791 is the equivalent for translation, with
its own local function `g__Reset|23_0`.

**Consequences for the agent, all following directly from where these
checks sit:**

1. **Writing `rocket.arrowkeys.turnAxis.Value` directly bypasses both
   gates.** Nothing between `Arrowkeys` and `Rocket.ApplyTorque`
   re-checks `hasControl` for the *manual* branch — §B1.3's
   `GetTurnAxis` consults `hasControl` only on the SAS path, and returns
   `arrowkeys.turnAxis` unconditionally when it is non-zero. So a direct
   write turns an uncontrolled craft.
2. **It also bypasses the timewarp block.** `ApplyTorque` gates only on
   `rb2d.simulated`, so a craft in physics mode during a low timewarp
   factor will respond to a directly-written `turnAxis`. Whether that is
   desirable is a design question, not a code question — but it is not
   the behaviour a human gets.
3. **Nothing clamps `turnAxis` to −1…+1.** The UI never writes outside
   that range, and `GetStopRotationTurnAxis` clamps its *own* output,
   but the manual branch is passed through raw into
   `angularVelocity -= torque·…·turnAxis·Δt`. A written value of 100
   scales rotational authority by 100. **Mechanism confirmed from the
   opcodes; never tested live** — and it is the kind of thing that
   would read as a physics discovery when it is really an unclamped
   input.

If the agent wants human-equivalent behaviour, it should replicate the
two guards itself, or drive `ArrowkeysDrawer`'s own `turn_Axis` /
`x_Axis` / `y_Axis` — but those are **private** fields, so the guards
would have to be re-implemented anyway. Recommendation: write
`Arrowkeys` directly and check `hasControl` and
`WorldTime.main.realtimePhysics` in the agent, so the bypass is a
deliberate choice rather than an accident.

`<Start>g__ToggleRCS|14_0` @161988 is `assembly static` — the RCS
toggle, reachable but not `public`.

### E2.4 `SFS.World.Throttle` [CONFIRMED]

```
.class public auto ansi beforefieldinit Throttle    @184675
```

| Field | Type |
|---|---|
| `throttleOn` | `Bool_Local` — input |
| `throttlePercent` | `Float_Local` — input, 0–1 |
| `output_Throttle` | `Float_Local` — **output** |

`Start()` @184683 subscribes `UpdateThrottle` to `throttleOn.OnChange`
**and** `throttlePercent.OnChange`. `UpdateThrottle()` @184711 is one
line:

```csharp
output_Throttle.Value = throttleOn.Value ? throttlePercent.Value : 0f;
```

So unlike `Arrowkeys`, throttle **is** event-driven and recomputes on
write — an agent writing `throttlePercent.Value` gets `output_Throttle`
updated synchronously inside the setter, before the write returns.
`output_Throttle` is what reaches `EngineModule.throttle_Out` through
the `INJ_Throttle` injection (§B1.5), and from there
`RecalculateMassFlow` (§D2.3).

**There is no gate here at all** — no `hasControl`, no timewarp check.
Throttle is symmetric between UI and direct write.

`throttlePercent` is not clamped in `UpdateThrottle`; whether the
`Obs<float>` carries a filter (§A3.1) that clamps it is **[OPEN]** —
`Float_Local`'s filter, if any, is set elsewhere and was not traced.

### E2.5 `SFS.Parts.Modules.ControlModule` [CONFIRMED]

```
.class public auto ansi beforefieldinit ControlModule    @273288
```

**One field, no methods**: `public Bool_Reference hasControl`. Being a
`Bool_Reference` (§A3.2) it may be locally valued or bound to a named
variable — so "does this capsule give control" can be a part variable,
not a constant. The craft-level `Player.hasControl` is derived from the
set of these by `Rocket`'s `UpdateControl` local function.

### E2.6 Status

| Item | Status |
|---|---|
| `Player` field layout and 5 abstract members | **[CONFIRMED]** |
| `Arrowkeys` is pure state, six `Obs<T>`, no methods | **[CONFIRMED]** |
| `ArrowkeysDrawer` is the sole writer for rockets | **[CONFIRMED]** — grep-exhaustive over the six fields |
| `PushTurnAxis` guards: `hasControl`, `realtimePhysics` | **[CONFIRMED]** |
| Direct writes bypass both guards | **[CONFIRMED]** — from where the checks sit |
| `turnAxis` is unclamped on the manual branch | **[CONFIRMED]** (opcodes) / **[UNTESTED-LIVE]** (effect) |
| `Throttle.UpdateThrottle` body; event-driven, ungated | **[CONFIRMED]** |
| `ControlModule` is a single `Bool_Reference` | **[CONFIRMED]** |
| Whether `throttlePercent` carries a clamping filter | **[OPEN]** |
| `PushDirectionalAxis` body | **[PARTIAL]** — guards confirmed, arithmetic not transcribed |
| Keyboard/gamepad binding path into `ArrowkeysDrawer` | **[OPEN]** |

---

## E3. Joints, splitting, and docking

`JointGroup` is the craft's connectivity graph. It is the authority for
three things an agent needs — what is attached to what, what happens
when a part is destroyed, and where the fuel groups come from (§E1.5).

### E3.1 `SFS.World.PartJoint` [CONFIRMED]

```
.class public auto ansi serializable beforefieldinit PartJoint    @186373
```

Three public fields — `Part a`, `Part b`, `Vector2 anchor` — and two
methods: `GetOtherPart(Part)` @186402 and `GetRelativeAnchor(Part)`
@186432. An **undirected edge with an attachment point**. There is no
strength, no break force, and no joint type: SFS joints are graph edges,
not Unity `Joint2D` components. Structural failure is therefore not
simulated as joint stress — it happens when a part is destroyed
(§E3.3).

### E3.2 `SFS.World.JointGroup` [CONFIRMED]

```
.class public auto ansi serializable beforefieldinit JointGroup    @186469
```

| Field | Type |
|---|---|
| `dictionary` | `Dictionary<Part, List<PartJoint>>` — the adjacency index |
| `joints` | `List<PartJoint>` |
| `parts` | `List<Part>` |

All public. The constructor takes `(List<PartJoint>, List<Part>)` and
builds `dictionary` via `AddJointToDictionary`. **`dictionary` is the
adjacency list** — given a part, its incident joints — and it is a real
index, not a memo, so unlike `Part.modules` (§B3.2) it can be
enumerated safely.

`RecreateGroups(out List<JointGroup> newGroups)` @186723 is a
**stack-based flood fill**, transcribed from the opcodes:

```csharp
var visited = new HashSet<Part>();
var groups  = new List<JointGroup>();
foreach (Part seed in parts) {
    if (visited.Contains(seed)) continue;
    var groupParts  = new List<Part>();
    var groupJoints = new HashSet<PartJoint>();
    var stack       = new Stack<Part>();
    visited.Add(seed); stack.Push(seed);
    while (stack.Count > 0) {
        Part p = stack.Pop();
        groupParts.Add(p);
        if (dictionary.TryGetValue(p, out List<PartJoint> incident))
            foreach (PartJoint j in incident) {
                if (!groupJoints.Contains(j)) groupJoints.Add(j);
                Part other = j.GetOtherPart(p);
                if (!visited.Contains(other)) { visited.Add(other); stack.Push(other); }
            }
    }
    groups.Add(new JointGroup(groupJoints.ToList(), groupParts));
}
```

So "did the craft split" is answered by connected-component count. This
is pure graph work — **no physics, no geometry, no distance test.**

`GetResourceGroups()` @187092 is the same flood fill, seeded from parts
that `HasModule<ResourceModule>()` and walking the same `dictionary`,
returning `List<List<ResourceModule>>`. That output is what
`Resources.SetupResourceGroups` (§E1.5) turns into fuel groups —
**confirming that fuel connectivity is exactly structural connectivity**,
with no separate plumbing graph. `GetConnectedFairings(Part,
SplitModule)` @187292 is a third traversal over the same index.

Other public members: `AddJoint(PartJoint)`,
`RemovePartAndItsJoints(Part)`, `RepositionParts()`,
`GetConnectedJoints(Part)` @187397 (a `dictionary` lookup).

### E3.3 Destruction and splitting [CONFIRMED structure]

Two **public static** entry points:

```csharp
static void OnPartDestroyed(Part part, Rocket rocket, DestructionReason reason);   // @186556
static void DestroyJoint(PartJoint joint, Rocket rocket,
                         out bool split, out Rocket newRocket);                     // @186603
static List<JointGroup> RecreateRockets(Rocket rocket, out List<Rocket> childRockets); // @186641
```

`OnPartDestroyed` is what `Part.DestroyPart` calls when
`updateJoints == true` (§B3.4), and it carries a local function
`g__SetFirstControllableChildAsPlayer|5_0` (`assembly static`) — so
**when the player's craft splits, control transfers to the first
controllable child**, matching `Rocket.SetPlayerToBestControllable`
(§B1.9).

`RecreateRockets` @186641, structure read:

```csharp
rocket.jointsGroup.RecreateGroups(out List<JointGroup> groups);
// groups[0] stays on the existing Rocket:
((I_Physics)rocket).LocalPosition =
    ((I_Physics)rocket).LocalPosition
    + (Vector2)partHolder.transform.TransformVector(groups[0].parts[0].Position);
rocket.SetJointGroup(groups[0]);
childRockets = new List<Rocket>();
for (int i = 1; i < groups.Count; i++) { /* RocketManager.CreateRocket_Child(...) */ }
```

**The surviving `Rocket` is re-anchored** — its `LocalPosition` (which
is the centre of mass, §B1.6) is shifted by the transformed position of
the first remaining part, because the CoM moves when mass is removed.
Each additional group becomes a new `Rocket` via
`RocketManager.CreateRocket_Child(JointGroup, Rocket parentRocket,
Vector2 offset)`, which is **public static** and takes an explicit
offset — the programmatic route to splitting a craft. Full body of the
child-creation loop **not read** — [PARTIAL].

### E3.4 `DetachModule` — separators [CONFIRMED layout]

```
.class public auto ansi beforefieldinit DetachModule    @260322
```

| Field | Type | Note |
|---|---|---|
| `separationSurface` | `SurfaceData` | which face separates |
| `separationForce` | `Composed_Vector2` | **parametric** (§E4) |
| `forceMultiplier` | `Float_Reference` | |
| `cannotDetachIfSurfaceCovered` | `bool` | |
| `surfaceForCover` | `SurfaceData` | |
| `activatedByLES` | `bool` | launch-escape-system trigger |
| `onDetach` | `UnityEvent` | |
| `showDescription`, `showForceMultiplier`, `useForceMultiplierEvenIfNotShown` | `bool` | UI |

`Detach(UsePartData data)` @260496 is **public** — the programmatic
separation call, and it takes the same `UsePartData` that
`Rocket.UseParts` produces (§B1.9). Private `Use` and `ForceMultiplier`
properties gate it. Bodies **not read** — [PARTIAL].

`separationForce` being a `Composed_Vector2` means separation impulse is
part-variable-dependent, so it scales with part size like mass does.

### E3.5 `DockingPortModule` [CONFIRMED]

```
.class public auto ansi beforefieldinit DockingPortModule    @248764
```

| Field | Type |
|---|---|
| `trigger` | `DockingPortTrigger` |
| `occupationSurface` | `SurfaceData` |
| `dockDistance`, `pullDistance`, `pullForce` | `float` |
| `forceMultiplier` | `Float_Reference` |
| `isOccupied`, `isOnCooldown`, `isDockable` | `Bool_Local` |
| `portsInRange` *(private)* | `List<DockingPortModule>` |

`FixedUpdate()` @249003, transcribed:

```csharp
if (!isDockable) return;
foreach (DockingPortModule other in portsInRange) {
    if (!other.isDockable) continue;
    if (Vector2.Distance(transform.position, other.transform.position) < dockDistance) {
        Dock(other);
    } else {
        Vector3 dir = (other.transform.position - transform.position).normalized;
        Rocket.rb2d.AddForceAtPosition(
            (Vector2)(pullForce * forceMultiplier.Value * 2f * dir),
            (Vector2)transform.position);
    }
}
```

Three things worth having written down:

- **Docking is a plain distance test** between port transforms against
  `dockDistance` — no alignment check, no relative-velocity check
  visible in this method. Approach angle and closing speed do not gate
  the dock here.
- Outside `dockDistance` the port applies a **magnetic pull**:
  `pullForce · forceMultiplier · 2` along the line between ports,
  applied at the port's own position, so it produces torque as well as
  translation. The `× 2` is a bare literal.
- The pull is applied to **every** dockable port in `portsInRange`, not
  just the nearest — a cluster of ports pulls cumulatively.

`portsInRange` is maintained by the public `AddPort` / `RemovePort`
@249259/@249284, driven by `DockingPortTrigger`, filtered by the private
`IsValidPort` @249310. `UpdateOccupied()` @248873 is public;
`isOnCooldown` + `EndCooldown` @248942 prevent immediate re-dock after
undocking. `Dock(DockingPortModule other)` @249100 is **private** —
there is no public "dock these two ports now" call; an agent must
achieve proximity.

#### E3.5.1 `Dock` — body read [CONFIRMED]

*(Depth pass. Replaces the earlier [PARTIAL] placeholder, and **corrects
one claim made above**.)*

```csharp
private void Dock(DockingPortModule otherPort) {                    // @249100
    if (otherPort.Rocket.isPlayer) return;                          // (1)

    Vector2 myUp    = Vector2.up * part.orientation;                // OrientationModule.op_Multiply
    Vector2 otherUp = Vector2.up * otherPort.part.orientation;

    Orientation rot = new Orientation(1f, 1f,
        (float)((int)(Mathf.Atan2(myUp.y,    myUp.x)    * 57.29578f
                    - Mathf.Atan2(otherUp.y, otherUp.x) * 57.29578f) + 180));
    rot.z = Mathf.RoundToInt(rot.z / 90f) * 90;                     // (2) SNAP

    foreach (Part p in otherPort.Rocket.partHolder.parts)           // (3)
        p.orientation.orientation.Value += rot;                     // Orientation.op_Addition
    foreach (PartJoint j in otherPort.Rocket.jointsGroup.joints)
        j.anchor = j.anchor * rot;                                  // Orientation.op_Multiply

    Vector2 comBefore = Rocket.rb2d.worldCenterOfMass;              // (4)
    RocketManager.MergeRockets(Rocket, part,
                               otherPort.Rocket, otherPort.part,
                               Vector2.zero);
    if (Rocket.isPlayer)
        PlayerController.main. /* camera shift by */
            (comBefore - Rocket.rb2d.worldCenterOfMass) /* , 1f */ ;
}
```

**(1) The player guard is what breaks the symmetry.** Both ports run
`FixedUpdate` and both would otherwise call `Dock` on each other in the
same tick. The early return means the dock is always performed by the
port whose **partner is not the player** — so exactly one side executes,
and if neither craft is the player, whichever port's `FixedUpdate` runs
first wins. It is a mutual-exclusion device, not a permission check.

**(2) CORRECTION to §E3.5 above.** That section said docking has "no
alignment check". More precisely: **the game does not *reject*
misalignment — it *forces* alignment.** The relative port heading is
computed, `+ 180°` applied (ports face each other), and then **snapped
to the nearest 90°** by `RoundToInt(z / 90f) * 90`. So SFS docking is
quantised to four orientations, and a craft arriving at 44° off is
rotated to 0° while one at 46° is rotated to 90°. There is still no
*closing-velocity* gate and no *approach-angle* rejection — the distance
test in `FixedUpdate` is the only precondition.

**(3) The entire other craft is rigidly rotated**, not just the port:
every `Part`'s `orientation` gets `rot` added, and every `PartJoint`'s
`anchor` is multiplied through it so attachment points follow. This
happens **instantaneously**, in one frame, with no interpolation — an
agent watching part positions across a dock will see a discontinuous
jump of up to 45°.

**(4) The merge itself is
`RocketManager.MergeRockets(Rocket rocket_A, Part part_A, Rocket
rocket_B, Part part_B, Vector2 anchor)` @191331 — `public static`**,
called here with `Vector2.zero` as the anchor. This is the programmatic
docking entry point, and it is the counterpart to
`RocketManager.CreateRocket_Child` for splitting (§E3.3). Its body is
**not read** — [PARTIAL] — so how it reconciles the two `JointGroup`s,
and whether it invokes `Staging.OnMerge` / `StatsRecorder.OnMerge`
(§B7.1, §E7.2), is still unconfirmed. The three `OnMerge` methods
existing across staging, stats and resources strongly suggests it does,
but that is inference and is marked as such.

The trailing `PlayerController` call compensates the camera for the
centre-of-mass shift the merge causes — `comBefore` is captured **before**
`MergeRockets` precisely for that. It confirms that a merge moves the
craft's CoM (§B1.6's `LocalPosition`), so an agent tracking position
across a dock must expect a step change there too.

`Orientation` @272510 is a small serialisable class — `public float x,
y, z` plus `InversedAxis()`, `op_Multiply(Vector2, Orientation)`,
`op_Addition(Orientation, Orientation)` and `GetCopy()`. The `x`/`y`
components passed as `1f, 1f` here are mirror/scale factors, left
unchanged by a dock.

### E3.6 Status

| Item | Status |
|---|---|
| `PartJoint` is an undirected edge, no strength/type | **[CONFIRMED]** |
| `JointGroup` field layout; `dictionary` is a real adjacency index | **[CONFIRMED]** |
| `RecreateGroups` is a stack-based flood fill | **[CONFIRMED]** |
| Splitting is connected-component counting, no physics | **[CONFIRMED]** |
| `GetResourceGroups` uses the same traversal → fuel = structural connectivity | **[CONFIRMED]** |
| `OnPartDestroyed` / `DestroyJoint` / `RecreateRockets` are public static | **[CONFIRMED]** |
| Surviving rocket's `LocalPosition` is re-anchored on split | **[CONFIRMED]** |
| Control transfers to first controllable child | **[CONFIRMED]** — from the local function's name and `SetPlayerToBestControllable`; body not read |
| `DetachModule` layout; `Detach(UsePartData)` is public | **[CONFIRMED]** |
| `separationForce` is parametric | **[CONFIRMED]** |
| `DockingPortModule` layout | **[CONFIRMED]** |
| Docking's only precondition is the distance test; no closing-velocity gate | **[CONFIRMED]** |
| Alignment is **forced, not checked** — snapped to nearest 90° (§E3.5.1) | **[CONFIRMED]** — corrects the looser claim above |
| Magnetic pull `pullForce · forceMultiplier · 2`, applied per port in range | **[CONFIRMED]** |
| `Dock` is private, but `RocketManager.MergeRockets` is public static | **[CONFIRMED]** |
| `Dock` body incl. the player-guard mutual exclusion | **[CONFIRMED]** |
| Whole other craft rigidly rotated in one frame | **[CONFIRMED]** |
| `MergeRockets` body — joint reconciliation, whether it fires `OnMerge` | **[PARTIAL]** / **[OPEN]** (the `OnMerge` link is inference) |
| `RecreateRockets` child-creation loop | **[PARTIAL]** |
| `DetachModule.Detach` body and its gates | **[PARTIAL]** |
| Whether `IsValidPort` enforces alignment | **[OPEN]** — body not read |
| `DestroyJoint` body | **[PARTIAL]** |

---

## E5. World, scenes, and timewarp

### E5.1 `SFS.World.WorldTime` [CONFIRMED]

```
.class public auto ansi beforefieldinit WorldTime    @198504
```

| Field | Type | |
|---|---|---|
| `main` | `WorldTime` | **public static** singleton |
| `timewarpIndex` | `int` | |
| `worldTime` | `double` | the simulation clock, seconds |
| `timewarpSpeed` | `double` | |
| `realtimePhysics` | `Bool_Local` | **false ⇒ on rails** |

`realtimePhysics` is the flag that gates heating (§D1), mass
recalculation (§B6.2) and manual rotation input (§E2.3), and it is the
one `Physics.Update` clears on an SOI crossing (§D4.3). `worldTime` is
what `WorldLocation.get_Value` stamps into a `Location` (§B2.2).

**Two timewarp ladders, decoded from the `.data` blobs:**

`GetTimewarpSpeed_Physics(int i)` @198909 — blob `D_00140030`,
`01 00 00 00 02 00 00 00 03 00 00 00 05 00 00 00`:

```
physics = [1, 2, 3, 5]
speed   = physics[i]
```

`GetTimewarpSpeed_Rails(int i)` @198927 — blob `D_00140008`,
`01 00 00 00 05 00 00 00 19 00 00 00`:

```csharp
int[] rails = { 1, 5, 25 };
speed = rails[i % 3] * Math.Pow(100.0, (int)((float)i / 3f));
```

which expands to **1, 5, 25, 100, 500, 2 500, 10 000, 50 000,
250 000, …** — a repeating 1/5/25 pattern stepped by ×100 every three
indices, unbounded in principle and capped by `MaxIndex` (private).
`maxPhysicsTimewarpIndex = [2, 2, 3]` by difficulty (§D1.5) bounds the
physics ladder.

**The two modes work in opposite directions**, which is the part worth
having written down:

```csharp
float TimeScale       => realtimePhysics ?  (float)timewarpSpeed : 1f;
static float FixedDeltaTime =>
    main.realtimePhysics ? Time.fixedDeltaTime
                         : (float)main.timewarpSpeed * Time.fixedDeltaTime;
```

- **Physics timewarp** (`realtimePhysics == true`) raises Unity's
  `Time.timeScale`; the simulation runs *faster in real time* with an
  unchanged step. Everything is still simulated.
- **Rails timewarp** (`realtimePhysics == false`) leaves `timeScale` at
  1 and instead multiplies `WorldTime.FixedDeltaTime`; the world steps
  analytically in large chunks.

So `WorldTime.FixedDeltaTime` and `Time.fixedDeltaTime` are **not
interchangeable** — §D1's `HeatManager` uses the former, §B1.3's
`ApplyTorque` uses the latter. Code that swaps them silently changes
behaviour under warp only.

`SetState(double timewarpSpeed, bool realtimePhysics, bool showMsg)`
@199281 is **public** and is the direct control point:

```csharp
this.timewarpSpeed = timewarpSpeed;
this.realtimePhysics.Value = realtimePhysics;
Time.timeScale = TimeScale;
if (showMsg) MsgDrawer.main.Log(Loc.main.Msg_Timewarp_Speed.Inject(...));
```

**No validation** — no `CanTimewarp` check, no clamp against `MaxIndex`,
no difficulty bound. An agent can set an arbitrary speed and mode
directly, bypassing every gate that `AccelerateTime` applies. It also
does not update `timewarpIndex`, so the UI and the actual speed can
disagree after a direct call.

The gated path is `AccelerateTime()` @198689 → `Accelerate_Rails()` /
`Accelerate_Physics()` → `ApplyState(bool)`, with
`DecelerateTime()`, `StopTimewarp(bool)` @199040,
`CheckStopTimewarp_ForChangedPlayer()` @199014 and the private
`ExitAutomaticTimewarp` / `CheckStopTimewarp_ForUpdate(timeOld, timeNew)`
@199114 — the last is what consults `Trajectory.GetStopTimewarpTime`
(§B5.2) to drop out of warp at an encounter. Bodies **not read** —
[PARTIAL].

`static bool CanTimewarp(bool showMsg, bool showSpeed, out bool isInWater)`
@198526 is public and delegates to the player's
`Player.CanTimewarp` (§B1.7). `SetTimewarpIndex_ForLoad(int)` @198673 is
public. `MaxTimewarpSpeed` is a public static property; `MaxIndex` and
`MaxPhysicsIndex` are **private**.

### E5.2 `SFS.World.WorldView` — the floating origin [CONFIRMED]

```
.class public auto ansi beforefieldinit WorldView    @199446
```

Two literals: `public const float ScaledSpaceScale = 10000f` and
`private const float ScaledSpaceThreshold = 50000f`.

Key fields: `main` (static), `positionOffset` and `velocityOffset`
(`Double2_Local`), `framing`, `viewDistance`, `scaledSpace`,
`canVelocityOffset` (all `Obs<T>`), plus `ViewLocation` (a private-set
`Location` property) and four public events —
`onViewLocationChange_Before/_After`, `onPositionOffset`,
`onVelocityOffset`.

The four conversions are **public static** and are the sanctioned bridge
between world coordinates (`Double2`, planet-relative, metres) and Unity
scene coordinates (`Vector2`):

```csharp
static Vector2 ToLocalPosition(Double2 globalPosition)
    => (Vector2)(globalPosition - main.positionOffset);
static Vector2 ToLocalVelocity(Double2 globalVelocity)
    => (Vector2)(globalVelocity - main.velocityOffset);
static Double2 ToGlobalPosition(Vector2 localPosition);     // the inverse
static Double2 ToGlobalVelocity(Vector2 localVelocity);
```

**SFS uses both a floating origin *and* a floating velocity frame.**
`positionOffset` is the usual origin-rebasing trick; `velocityOffset` is
less common — the Unity rigidbody's velocity is *relative to a moving
reference*, which is why `Rocket`'s `I_Physics.LocalVelocity`
(`rb2d.linearVelocity`, §B1.6) is **not** the craft's world velocity.
Anything comparing a `Vector2` velocity to a `Double2` one must convert.
`Physics.SetLocationAndState` (§B5.1) uses exactly these calls.

`positionOffset` and `velocityOffset` are recomputed by the private
`CalculatePositionOffset` @199818 and `CalculateVelocityOffset` @199862,
with `Physics.OnPositionOffset` / `OnVelocityOffset` (§B5.1) subscribing
to the two events so tracked objects are shifted in step. **An agent
caching a Unity-space position across frames must re-base it** or
subscribe to `onPositionOffset`. Bodies of the offset calculators
**not read** — [PARTIAL], so the trigger threshold for a rebase is
unconfirmed (`ScaledSpaceThreshold = 50000f` is a *rendering* switch,
used by `UpdateIsScaledSpace` @199656, and should not be assumed to be
the rebase threshold).

`GetOffset(Double2 a, double b)` @199952 is public static — [PARTIAL],
body not read.

### E5.3 `SFS.World.GameManager` — the world scene [CONFIRMED layout]

```
.class public auto ansi beforefieldinit GameManager    @178293
```

| Field | Type |
|---|---|
| `main` | `GameManager` — static singleton |
| `environment` | `WorldEnvironment` |
| `world_Input`, `map_Input` | `Screen_Game` |
| `aeroData` | `AeroData` — **the serialized `AeroFormula` coefficients §D1 needs** |
| `rockets` | `List<Rocket>` — **every craft in the world** |
| `particles` | `List<WorldParticle>` |
| `fuelManager` | `GameObject` |
| `timeSinceLastSave` *(private)* | `float` |

`GameManager.main.rockets` is the craft enumeration point — the probe's
`world` command territory. `GameManager.main.aeroData` is where the
`velPow` / `densityPow` / `tempOffset` / `m` coefficients that §D1
marked **[OPEN]** actually live; reading it live closes that gap. The
`AeroData` type's own layout was **not read** — [PARTIAL].

Public methods, signatures confirmed:

| Method | Note |
|---|---|
| `RevertToLaunch(bool skipConfirmation)` | @178885 |
| `RevertToBuild(bool skipConfirmation)` | @178958 |
| `ExitToBuild()`, `ExitToHub()`, `ExitToMainMenu()` | scene transitions |
| `OpenMenu()`, `OpenSave()`, `OpenLoad()` | UI |
| `LoadSave(WorldSave save, bool forLaunch, I_MsgLogger logger)` | @179389 — **the programmatic world-load entry** |

`RevertToLaunch` reads a revert point through
`SavingCache.TryLoadRevertToLaunch(out WorldSave)`, compares
`WorldTime.main.worldTime` against `revertSave.state.worldTime`, and —
unless `skipConfirmation` — routes through
`MenuGenerator.OpenConfirmation`, gated by a one-time notification
keyed `"Revert_Functionality"` via `FileLocations.GetOneTimeNotification`.
**`skipConfirmation: true` is the headless path**, which is what the
probe's `revert` command needs. Private helpers: `CreateWorldSave()`
@179164, `UpdatePersistent(bool, bool, bool)` @179146,
`LoadPersistentAndLaunch()` @179239, `ClearWorld()` @179712,
`static IsOnLaunchpad(string planet, Double2 position)` @179870.

### E5.4 `SFS.SceneLoader` and `SceneHelper` [CONFIRMED]

Scene names, read from the `ldstr` literals @46185–46229:
**`"Base"`, `"Home"`, `"Hub"`, `"Build"`, `"World"`** — five scenes,
with `Base` persistent.

`SceneLoader` public methods: `LoadHomeScene(string openShop)`,
`LoadHubScene()`, `LoadBuildScene(bool askBuildNew)`,
`LoadWorldScene(bool launch = …)`, and **`static ExitToMainMenu()`**.
Loading is async (`LoadSceneAsync`, an `IEnumerator` coroutine), so a
scene change does not complete within the calling frame — an agent must
wait on an event, not assume.

`SceneHelper` @44364 is a `static class` of ten
`OptionalDelegate<Scene>` hooks — `OnHomeSceneLoaded/Unloaded`,
`OnHubScene…`, `OnBuildScene…`, `OnWorldScene…`, plus generic
`OnSceneLoaded` / `OnSceneUnloaded`. **These are the clean subscription
points for "the world is ready"** and require no Harmony. `SFS.Base`
@46080 is the static service locator holding `sceneLoader`, `worldBase`,
`planetLoader`, `partsLoader`, `inputManager`, `language`, `sound`,
`screenTracker`, `saver`.

### E5.5 Status

| Item | Status |
|---|---|
| `WorldTime` field layout; `realtimePhysics` = not-on-rails | **[CONFIRMED]** |
| Physics ladder `[1, 2, 3, 5]` | **[CONFIRMED]** — blob decoded |
| Rails ladder `rails[i%3] · 100^(i/3)` from `[1, 5, 25]` | **[CONFIRMED]** — blob decoded |
| `TimeScale` and `FixedDeltaTime` scale in opposite modes | **[CONFIRMED]** |
| `SetState` is public and validates nothing | **[CONFIRMED]** |
| `SetState` does not update `timewarpIndex` | **[CONFIRMED]** |
| `WorldView` conversions; floating origin **and** velocity frame | **[CONFIRMED]** |
| `ScaledSpaceScale = 10000`, `ScaledSpaceThreshold = 50000` | **[CONFIRMED]** — literals |
| `GameManager` field layout; `rockets`, `aeroData` | **[CONFIRMED]** |
| `aeroData` is where §D1's [OPEN] coefficients live | **[CONFIRMED]** — location; values still live-only |
| `RevertToLaunch` confirmation path and `skipConfirmation` | **[CONFIRMED]** |
| Five scene names | **[CONFIRMED]** — string literals |
| `SceneHelper`'s ten scene hooks | **[CONFIRMED]** |
| Whether `ScaledSpaceThreshold` also triggers origin rebase | **[OPEN]** — do not assume |
| `CalculatePositionOffset` / `CalculateVelocityOffset` bodies | **[PARTIAL]** |
| `AccelerateTime` / `ApplyState` / `CheckStopTimewarp_ForUpdate` bodies | **[PARTIAL]** |
| `AeroData` layout | **[PARTIAL]** |
| `LoadSave` body | **[PARTIAL]** |
| Direct `SetState` timewarp control | **[UNTESTED-LIVE]** |

---

## E7. Stats, challenges, and logging

Relevant to an agent for two reasons: `StatsRecorder` is the game's own
answer to "what has this flight achieved", which is a ready-made reward
signal; and `I_MsgLogger` is the interface every gate in the codebase
uses to explain *why* it refused.

### E7.1 `SFS.I_MsgLogger` and `SFS.UI.MsgDrawer` [CONFIRMED]

```
.class interface public auto ansi abstract I_MsgLogger    @64110
    void Log(string msg)
```

**A single-method interface.** It is the `logger` parameter threaded
through `Rocket.CanTimewarp` (§B1.7), `WorldTime.CanTimewarp` (§E5.1),
`FlowModule.CanFlow` (§E1.3), `GameManager.LoadSave` (§E5.3) and
`Flow.CanFlow_ElseShowMsg`. **This is the highest-value integration
point in this section**: an agent that passes its own `I_MsgLogger`
implementation into those calls receives the game's own localised
explanation of a refusal — "cannot timewarp while moving on surface",
"no control" — instead of a bare `false`. That is a diagnosis channel
the probe does not currently use, and it requires no Harmony and no
patching, only an object implementing one method.

`SFS.UI.MsgDrawer` @122379 is the game's implementation: a static
`main`, `Log(string)` (the explicit interface method, `final virtual`)
and `Log(string msg, bool big)` @122416 — **two overloads, ambiguous
under naive `GetMethod("Log")`**.

### E7.2 `SFS.Stats.StatsRecorder` [CONFIRMED layout]

```
.class public auto ansi beforefieldinit StatsRecorder    @70185
```

`private const float RecordTime = 1f` — the sampling period.

| Field | Type |
|---|---|
| `location` | `WorldLocation` |
| `player` | `Player` |
| `branch` | `int` |
| `location_Old` *(private)* | `Location` |
| `tracker` | `StatsRecorder.Tracker` |
| `challengeRecorder` | `ChallengeRecorder` |

`Rocket.stats` (§B1.1) points here. `Record()` @70722 runs on the
1-second cadence and calls four tracker methods in order:

```csharp
Location l = location.Value;
tracker.Record_Landed(l);
tracker.Record_Height(l);
tracker.Record_Orbit(l);
tracker.Record_Atmosphere(l);
```

So the game continuously classifies the craft's state into **landed /
height band / orbit state / atmosphere state**, each with its own
`Log_*` formatter (`Log_Landed`, `Log_Height`, `Log_Orbit`,
`Log_Atmosphere`, `Log_Reentry`, `Log_Planet`, `Log_LeftCapsule`,
`Log_Flag`, `Log_CollectRock` — all `private static`, returning
`List<string>`). `Tracker` exposes the nested value types
`State_Orbit` and `State_Atmosphere`, visible in `Initialize`'s
signature @70660.

Public event hooks: `OnLeaveCapsule(string astronautName)`,
`OnPlantFlag(double angleDegrees)`, `OnCollectRock(double angleDegrees)`,
`OnCrash(float impactVelocity)`, plus **public static**
`OnSplit(StatsRecorder A, StatsRecorder B)` @70385 and
`OnMerge(StatsRecorder A, StatsRecorder B)` @70472 — the stats-side
counterparts to `Staging.OnSplit`/`OnMerge` (§B7.1) and
`JointGroup.RecreateRockets` (§E3.3).

`HasFlown()` @70885 is public and walks `LogManager.branches`
(a `Dictionary<int, Branch>`, each `Branch` having `parentA`) with a
**hard iteration cap of 1000** and a user-visible message on overrun —
i.e. the flight history is a linked branch tree, guarded against
cycles. `LogManager` was **not read** — [PARTIAL].

**Mission history is per-branch and survives splits and merges**, which
means an agent can ask the game "has this vehicle flown" rather than
tracking it itself.

### E7.3 `SFS.Logs.Challenge` and `ChallengeRecorder` [CONFIRMED layout]

```
.class public auto ansi serializable beforefieldinit Challenge    @73480
```

| Field | Type |
|---|---|
| `displayPriority` | `int` |
| `id` | `string` |
| `owner` | `Planet` |
| `icon` | `Sprite` |
| `title`, `description` | `Func<string>` |
| `difficulty` | `SFS.Logs.Difficulty` |
| `steps` | `List<ChallengeStep>` |
| `returnSafely` | `bool` |

`static List<Challenge> CollectChallenges()` @73561 is **public** — the
full challenge catalogue is enumerable at runtime, with `id`, `owner`
planet, `difficulty`, ordered `steps` and the `returnSafely` flag. The
earlier `sfs_source_reference.md` also records a second, already-built
catalogue at **`SFS.Base.worldBase.challengesArray`** (`Challenge[]`,
static), which is what the probe's `achievements` command uses. Both
reach the same data; `challengesArray` avoids re-running the collection.
That path is **[UNTESTED-LIVE]** and the field was not re-verified
against IL in this pass — marked **[PARTIAL]**.

These are **not** Steamworks achievements — pure in-game state, fully
reflectable. `title` and `description` are `Func<string>`; cast and
invoke to get the text.
`ChallengeStep` @74974 is an abstract base; its subclasses were
**not enumerated** — [PARTIAL], so what a step actually tests is
unconfirmed.

`ChallengeRecorder` @72460 holds private `eligibleSteps`, `progress`
(`Dictionary<Challenge, (int, string)>`), `complete`
(`HashSet<Challenge>`) and `owner`. Public API:

| Method | Note |
|---|---|
| `UpdateEligibleSteps()` | @72504 |
| `TryCompleteSteps(Location location)` | @72642 — **the evaluation call, takes a `Location`** |
| `OnCrash(float impactVelocity)` | @72807 |
| `Merge(ChallengeRecorder b)` | @73046 |
| `Split(out Dictionary<…> progress, out HashSet<Challenge> complete)` | @73181 |
| `GetCompleteChallenges()` → `HashSet<Challenge>` | @73226 |

`TryCompleteSteps(Location)` taking a plain `Location` (§B2.1) rather
than a live craft is notable: **challenge progress is evaluated against
a state vector**, so in principle an agent could ask "would this
trajectory complete a step" — though `CompleteStep` has side effects
(rewards, messages), so speculative evaluation is **not** safe without
reading its body. [OPEN].

`GetCompleteChallenges()` is the clean per-craft achievement read, and
`progress`/`complete` are serialised into the save (§D5) — which is why
`StatsRecorder.Initialize` @70660 takes them as parameters.

### E7.4 `ErrorLogger` [CONFIRMED]

```
.class public auto ansi beforefieldinit ErrorLogger    @13341
```

Static `main`; `List<string> lastLogs` (public); private `logs`
(a `Queue<(string condition, string stackTrace, LogType)>`),
`logLocation` (`IFile`), `logBuilder`.

`Awake()` @13351 reads `FileLocations.LogsFolder/counter.txt`, parses a
`long`, and rotates — a **numbered log rotation with a small retention
count** (`ldc.i4.5` appears in the rotation arithmetic; the exact
retention semantics were not transcribed — [PARTIAL]).
`LogMessage(string condition, string stackTrace, LogType)` @13600 is the
Unity log callback; `LogLoop()` @13571 drains the queue.

`GetLogsDumpBase64Gzip()` @13474 is **public** and returns the log dump
as a base64 gzip string — a ready-made way to pull the game's own log
tail out through the probe's existing text channel without touching the
filesystem.

`ErrorLogger.main.lastLogs` is a public `List<string>` — the simplest
possible read for "what did the game just complain about", and directly
useful against §D2's swallowed-exception problem: the bare `catch { }`
blocks in `SFSProbe.cs` log nothing, but a Unity exception thrown
*inside* game code does land here.

### E7.5 Status

| Item | Status |
|---|---|
| `I_MsgLogger` is a one-method interface | **[CONFIRMED]** |
| It is the refusal-reason channel across timewarp/control/fuel/load gates | **[CONFIRMED]** |
| `MsgDrawer.Log` has two overloads (ambiguous) | **[CONFIRMED]** |
| `StatsRecorder` layout; `RecordTime = 1f` | **[CONFIRMED]** |
| `Record()` calls four `Tracker.Record_*` classifiers | **[CONFIRMED]** |
| Public event hooks + static `OnSplit`/`OnMerge` | **[CONFIRMED]** |
| `HasFlown()` walks a branch tree with a 1000-iteration cap | **[CONFIRMED]** |
| `Challenge` layout; `CollectChallenges()` is public static | **[CONFIRMED]** |
| `ChallengeRecorder` public API | **[CONFIRMED]** |
| `TryCompleteSteps` takes a `Location` | **[CONFIRMED]** |
| `ErrorLogger` layout; `lastLogs` public; `GetLogsDumpBase64Gzip()` public | **[CONFIRMED]** |
| Log rotation retention semantics | **[PARTIAL]** |
| `ChallengeStep` subclasses — what a step tests | **[PARTIAL]** |
| `Tracker` internals (`State_Orbit`, `State_Atmosphere`) | **[PARTIAL]** |
| `LogManager` / `Branch` | **[PARTIAL]** |
| Whether `TryCompleteSteps` is side-effect-free enough to use speculatively | **[OPEN]** — `CompleteStep` body not read |
| Passing a custom `I_MsgLogger` into the game's gates | **[UNTESTED-LIVE]** |

---

## E6. Parachutes, wheels, and toggles

Deprioritised by agreement and written last. Structure and the
load-bearing constants only; several bodies are deliberately left
[PARTIAL].

### E6.1 `ParachuteModule` [CONFIRMED layout, PARTIAL bodies]

```
.class public auto ansi beforefieldinit ParachuteModule    @262464
```

| Field | Type | Note |
|---|---|---|
| `maxDeployHeight` | `double` | compared against **terrain-relative** height |
| `maxDeployVelocity` | `double` | |
| `drag` | `AnimationCurve` | **serialized Unity data — live-only** |
| `parachute` | `Transform` | the force application point |
| `state` | `Float_Reference` | current deployment, 0–1 |
| `targetState` | `Float_Reference` | commanded deployment |
| `onDeploy` | `UnityEvent` | |
| `deploySound_Partial`, `deploySound_Fully` | `AudioModule` | |
| `oldPosition` *(private)* | `Double2` | |

`DeployParachute(UsePartData data)` @262542 is **public**. Its gates,
read from the opcodes in order:

- `Location.planet.HasAtmospherePhysics` — refuses in vacuum with
  `Msg_Cannot_Deploy_Parachute_In_Vacuum`
- `planet.data.atmospherePhysics.parachuteMultiplier` — a **per-planet
  parachute effectiveness scalar**, on `Atmosphere_Physics` (§D4).
  Not previously recorded in this document.
- `Location.Height` vs `planet.AtmosphereHeightPhysics * 0.9` — deploy
  is only allowed below **90% of the physics atmosphere height**
- `Location.GetTerrainHeight(bool)` vs `maxDeployHeight` — the deploy
  ceiling is measured **above terrain**, not above the datum (§B2.1),
  so it behaves differently over mountains
- `targetState` / `state` compared against `0f`

The full branch structure and which check produces which message was
**not fully transcribed** — [PARTIAL]. `UpdateEnabled` @262847,
`LateUpdate` @262873 and `AngleToOldPosition` @262997 (the visual
weathervaning) are **not read**.

**`Aero_Rocket.ApplyParachuteDrag(ref float force, ref Vector2
centerOfDrag_World)`** @220368 — the method §C1 flagged as mutating both
arguments and bypassing the 0.2 lerp damping. Structure now read:

```csharp
foreach (ParachuteModule p in rocket.partHolder.GetModules<ParachuteModule>()) {
    // gated on p.targetState.Value against 1f and 2f
    Vector2 pointVel = rocket.rb2d.GetPointVelocity(p.parachute.position);
    double  v2       = WorldView.ToGlobalVelocity(pointVel).sqrMagnitude;
    float   f        = (float)v2 * p.drag.Evaluate(p.state.Value);
    // accumulate f, and a force-weighted sum of p.parachute.position
}
// force += Σf ; centerOfDrag_World = weighted centroid
```

Two things worth noting. It uses **`rb2d.GetPointVelocity` at the
parachute's own position**, so a spinning craft gives each chute a
different airspeed — parachute drag is the one place in §C1's chain that
is rotation-aware. And the coefficient is an `AnimationCurve` evaluated
at the deployment `state`, i.e. **partial deployment is a curve lookup,
not a linear ramp**, and the curve is serialized data that must be read
live. Exact accumulation arithmetic **not fully transcribed** —
[PARTIAL].

### E6.2 `SFS.Parts.WheelModule` [CONFIRMED layout]

```
.class public auto ansi beforefieldinit WheelModule    @235157
```

| Field | Type |
|---|---|
| `power`, `traction`, `maxAngularVelocity`, `wheelSize` | `float` |
| `angularVelocity` | `float` — live state, public |
| `on` | `Bool_Reference` |
| `<TurnAxis>k__BackingField`, `<Rb2d>k__BackingField` | injected |

`TurnAxis` and `Rb2d` are `final virtual` public setters — injection
targets (§B1.5); `TurnAxis` is fed from `Rocket.output_TurnAxisWheels`,
which is the **raw, undamped** `arrowkeys.turnAxis` (§B1.3), *not* the
SAS-processed one. So wheels steer on manual input only and are
unaffected by rotation damping.

`Update()` @235511, the spin-up/spin-down arithmetic:

```csharp
if (on.Value && TurnAxis != 0f)
    angularVelocity += Time.deltaTime * power * ...;            // driven
else
    angularVelocity = Mathf.Clamp(angularVelocity, on.Value ? -0.05f : -0.25f,
                                                   on.Value ?  0.05f :  0.25f);
angularVelocity = Mathf.Clamp(angularVelocity, -maxAngularVelocity, maxAngularVelocity);
```

The four literals **−0.05 / 0.05 (powered) and −0.25 / 0.25
(unpowered)** are the idle-roll clamps: a powered wheel with no steering
input is held near-stationary (braking), an unpowered one is allowed to
free-roll five times faster. Exact placement of `power`/`deltaTime` in
the driven branch was not fully transcribed — [PARTIAL].

`OnCollisionStay2D(Collision2D)` @235315 is where `traction` is applied
— **not read**, [PARTIAL]. `ToggleEnabled()` @235227 is public.

### E6.3 `ToggleModule` and `MoveModule` [CONFIRMED]

`ToggleModule` @275143 is trivially small: `TranslationVariable label`
and `MoveModule state`. All behaviour lives in `MoveModule`.

`MoveModule` @273975 is the **generic animation/state driver** used for
toggles, and also for the control-pad animations in `ArrowkeysDrawer`
(§E2.3):

| Field | Type |
|---|---|
| `time`, `targetTime` | `Float_Reference` |
| `animationTime` | `float` |
| `unscaledTime` | `bool` |
| `animationElements` | `MoveData[]` |

Public API — **the programmatic route for every toggleable part**:

```csharp
void Toggle();                       // @274442
void Activate();                     // @274466
void SetTargetTime(float newTargetTime);   // @274480
void SetTime(float newTime);               // @274494
```

`time` and `targetTime` being `Float_Reference` (§A3.2) means a toggle's
position is part of the variable system and therefore **serialised and
parametric-capable**, not transient UI state. `MoveModule` implements
`I_InitializePartModule` with an explicit `Priority`. `Update` @274049
and `ApplyAnimation` @274111 **not read** — [PARTIAL].

`unscaledTime` is worth flagging: a `MoveModule` with it set animates on
real time rather than world time, so its behaviour under timewarp
(§E5.1) differs from the rest of the simulation. Which parts set it is
**[OPEN]** — it is serialized data.

### E6.4 Status

| Item | Status |
|---|---|
| `ParachuteModule` field layout | **[CONFIRMED]** |
| `DeployParachute` is public; gate *set* identified | **[CONFIRMED]** |
| Deploy ceiling is terrain-relative, not datum-relative | **[CONFIRMED]** |
| 90% of `AtmosphereHeightPhysics` deploy limit | **[CONFIRMED]** |
| `Atmosphere_Physics.parachuteMultiplier` exists | **[CONFIRMED]** — new to this doc |
| `ApplyParachuteDrag` uses per-chute `GetPointVelocity` | **[CONFIRMED]** |
| Drag coefficient is an `AnimationCurve` of `state` | **[CONFIRMED]** — curve is live-only data |
| `DeployParachute` full branch structure | **[PARTIAL]** |
| `ApplyParachuteDrag` exact accumulation | **[PARTIAL]** |
| `WheelModule` field layout | **[CONFIRMED]** |
| Wheels driven by raw `output_TurnAxisWheels`, no SAS | **[CONFIRMED]** |
| Idle clamps ±0.05 powered / ±0.25 unpowered | **[CONFIRMED]** |
| `WheelModule.Update` driven-branch arithmetic | **[PARTIAL]** |
| `OnCollisionStay2D` / traction model | **[PARTIAL]** |
| `ToggleModule` delegates entirely to `MoveModule` | **[CONFIRMED]** |
| `MoveModule` public API (`Toggle`/`Activate`/`SetTime`/`SetTargetTime`) | **[CONFIRMED]** |
| Toggle state lives in the variable system | **[CONFIRMED]** |
| `MoveModule.Update` / `ApplyAnimation` | **[PARTIAL]** |
| Which parts set `unscaledTime` | **[OPEN]** |

---

## E8. Blueprint construction — surface-mount attachment (`HoldGrid`)

### E8.1 `HoldGrid.CollectSurfaceSnaps` / `ProcessSurfaceSnap` [CONFIRMED mechanism, PARTIAL branch-sign detail]

IL-read 2026-09-02, resolving the "surface-mount positioning formula — NOT
solved" gap flagged in `docs/high_level_checklist.md`'s blueprint section.
The magnet-chain formula (§ elsewhere, confirmed 2026-08-29) only covers
parts with a `MagnetModule` (stack parts: tanks, engines, capsules).
`Parachute`, `Parachute Side`, and `Side Separator` have no `MagnetModule`
at all (`magnetPoints: null`) — they attach via a genuinely different,
edge-to-edge mechanism, confirmed here.

**`CollectSurfaceSnaps(moves)`** — for the part being placed ("build"
side) and the existing structure ("hold" side), pulls each side's
`SurfaceData` modules, converts each into world-space edge segments
(`Surfaces.GetSurfacesWorld()` → `Line2[]`), and uses a spatial-hash grid
(`GetCollisionsDictionary`, cell size 2, tolerance 1.4/2.0) to find
candidate hold-side edges near each build-side edge (checking both the
edge and its `Flip()`), deduplicated per build-edge index
(`GridPointData.checkIndex`). Each candidate pair is passed to
`ProcessSurfaceSnap`.

**`ProcessSurfaceSnap(moves, line_Build, line_Hold)`** — for one build
edge vs. one candidate hold edge:

1. **Parallel gate**: `Dot(line_Build.dir.normalized, line_Hold.dir.normalized) ≥ 0.9`
   (~26° max angle) — abort (no snap) if the edges aren't nearly parallel.
2. **Overlap gate**: project `line_Hold`'s two endpoints onto
   `line_Build`'s own parametric axis via `Math_Utility.GetClosestPointOnLine`
   (returns 0-1 param, scaled by `line_Build`'s length) to get a 1D range
   `hold = Line(t0, t1)` in build-local coordinates; intersect with
   `build = Line(0, len)` to get `overlap`. Abort if `overlap.Size ≤ 0.125`.
3. **Proximity gate**: at `overlap.Center`, compute the real world position
   on both edges (`GetPosOnBuildLine`/`GetPosOnHoldLine`, see below) and
   abort if they're more than 0.7 units apart
   (`(buildPos - holdPos).sqrMagnitude > 0.49`).
4. **Offset + quantization**: `centerDelta = overlap.Center - hold.Center`
   (sign determines which side of the hold edge the overlap sits on);
   combined with a check of whether the hold or build edge is longer, this
   picks which end of the *unclamped* hold-projection (`hold.start` or
   `hold.end`) to measure from, producing a raw offset that gets
   **quantized to the nearest 0.25-unit step** via `Math_Utility.Round(x, 0.25)`.
   **[PARTIAL]** — the exact sign/side branch selecting which end is used
   as the anchor was traced through the IL but not independently
   cross-checked against a live placement; treat the quantization step
   size (0.25) and the overall shape of the algorithm as CONFIRMED, but
   verify the anchor-end choice with a real test placement before trusting
   it blind.
5. **Local helper functions** (all confirmed, simple):
   - `GetPosOnBuildLine(x) = line_Build.start + line_Build.Size.normalized * x`
     — world position at build-local parameter `x`.
   - `GetPosOnHoldLine(x) = Line2.LerpUnclamped(InverseLerpUnclamped(hold.start, hold.end, x), line_Hold)`
     — maps a build-local parameter back onto the real world-space hold
     edge via the same (start,end) range used for the projection.
   - `GetAngle() = AngleDegrees(line_Build.Size) - AngleDegrees(line_Hold.Size)`
     — the rotation delta to apply to the part being placed so its edge
     direction matches the existing edge's direction.
6. **Result**: `Data(buildAnchorPoint, holdAnchorPoint, angleOffset)` is
   appended to `moves` — the placement is "rotate the new part by
   `angleOffset`, then translate so `buildAnchorPoint` on the new part's
   edge coincides with `holdAnchorPoint` on the existing structure's edge."

**Practical implication for `python/blueprint_builder.py` v2 (surface-mount
parts)**: this is NOT a fixed per-part-type offset (which is why the
earlier attempt to fit one to the reference build's separator positions
failed) — it depends on both parts' real edge geometry (`surfacesFast`,
gated behind `Part.InitializePart()` on placed instances, per the existing
geometry-capture gotcha) and how their edges overlap. A v2 implementation
needs real edge data for both parts, not a lookup table.

| Claim | Status |
|---|---|
| Surface-mount uses `HoldGrid.CollectSurfaceSnaps`/`ProcessSurfaceSnap`, not magnet chaining | **[CONFIRMED]** |
| Parallel-edge gate (dot ≥ 0.9) | **[CONFIRMED]** |
| Overlap gate (> 0.125 units) | **[CONFIRMED]** |
| Proximity gate (≤ 0.7 units) | **[CONFIRMED]** |
| Offset quantized to 0.25-unit steps | **[CONFIRMED]** |
| `GetPosOnBuildLine`/`GetPosOnHoldLine`/`GetAngle` formulas | **[CONFIRMED]** |
| Exact anchor-end (start vs. end) branch selection | **[PARTIAL]** — needs live cross-check |

---
