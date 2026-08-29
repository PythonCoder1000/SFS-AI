# Reflection toolkit and ambiguous-overload catalogue

The nine helpers every per-class file's "Reflection recipe" assumes by
name, plus the catalogue of methods where plain
`GetMethod(name, flags)` throws `AmbiguousMatchException`.

The helpers themselves come from `sfsprobe/SFSProbe.cs` (this project's
mod) rather than from the game, but they are the "when/how/where is it
accessible" half of every class entry here, so they live alongside the
reference rather than inside the mod's own docs. **The ambiguous-overload
catalogue is a fact about the game**, not about the probe.

Migrated from `docs/sfs_source_reference.md` §A1 and §A1.1 during Phase 1
Step 1 (2026-08-28), content unchanged.

**This is not a per-class file** and so does not follow the per-class
template.

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

