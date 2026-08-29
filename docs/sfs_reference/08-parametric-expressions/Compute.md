# `SFS.Parsers.Constructed.Compute` — the part-variable expression compiler

**Group file.** The compiler, its AST, and the `Composed_Float` /
`VariablesModule` machinery that drives it — documented together because
none of them is usable without the others.

**This section replaces the claim "no Python-side evaluator exists" with
the real evaluator, and explains *why* live reads have always worked
while static asset parsing has always failed.** That is the mechanism
behind the data-trust rule in `CLAUDE.md`.

**Migrated** from `docs/sfs_source_reference.md` §E4 (2026-08-28).

The wrapper base: [`../00-infrastructure/variables-wrapper-family.md`](../00-infrastructure/variables-wrapper-family.md).
The save side: [`../07-saveload/save-records.md`](../07-saveload/save-records.md).

## The mechanism, end to end

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

---

## Composed_Float

**Namespace:** SFS.Variables
**Kind:** class
**Extends:** SFS.Variables.Composed&lt;float&gt;
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @278208

Exactly two fields.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `input` | `string` | public | no | **the expression text**, e.g. `"size * 0.05"` — readable symbolically | [CONFIRMED] |
| `compiled` | `Compute.I_Node` | private | no | the compiled AST, built lazily | [CONFIRMED] |

### Methods

#### GetResult(bool initialize) -> float

- **Access:** `protected override` instance · IL @278215, body read
- **Behavior:**
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
- **Side effects:** on the `initialize` path it **compiles the expression
  and registers `Recalculate` against every variable the expression
  uses.**
- **Gotchas:** two consequences that explain the project's whole
  experience with part constants.
  1. **Reading `.Value` already returns the fully-resolved parametric
     number.** The probe's existing `GetWrapped2(Get(part, "mass"))` has
     been evaluating the expression all along — nothing extra is needed
     to get correct masses from a placed part.
  2. **The expression is only meaningful against a bound
     `VariablesModule`.** A `Composed_Float` read off an **unplaced
     catalog prefab** has no variables bound, which is exactly why static
     asset parsing produced the wrong Titan mass and wrong Hawk
     thrust/ISP that `sfs_physics_reference.md` §1.2 records. **The
     data-trust rule is now explained, not just observed.**
- **Status:** [CONFIRMED]

#### Offset(float offset) -> void

- **Access:** public instance · IL @278339
- **Behavior:** calls `Compute.Compile` again — so **offsets are applied
  to the expression layer, not to a cached number**.
- **Status:** [CONFIRMED] role · [OPEN] body

`Composed_Double` @278415 works identically for `double`-typed values.

---

## Compute

**Namespace:** SFS.Parsers.Constructed
**Kind:** static class (`public abstract sealed`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED] entry points · [OPEN] parser body
**Depth:** FULL
**IL:** `scratch/full_il.txt` @115724 · 4 methods

### Methods

#### Compile(string code, VariablesModule variables, out List&lt;string&gt; usedVariables) -> I_Node

- **Access:** **public static** · IL @115729
- **Parameters:** `code` — any expression string, not just ones the game
  authored; `variables` — the module to resolve names against;
  `usedVariables` — filled with the variable names the expression
  references
- **Returns:** a `Compute/I_Node` whose `Value` property evaluates the
  tree
- **Gotchas:** **overloaded** — the public
  `(string, VariablesModule, out List<string>)` and a private
  `(ref int, ref string, VariablesModule, out List<string>)` @115748.
  Plain name lookup throws `AmbiguousMatchException`; resolve by explicit
  parameter types, using `MakeByRefType()` for the `out` parameter.
  Catalogued in
  [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
- **Status:** [CONFIRMED] signature · **[OPEN] parser body** (@115748,
  the recursive-descent core) and `<Compile>g__Operator|1_0` @116391 —
  so **operator precedence and the exact accepted grammar are
  unconfirmed**

#### GetVariablesUsed(string valueString) -> List&lt;string&gt;

- **Access:** **public static** · IL @116287
- **Parameters:** takes **only a string** — no game object needed
- **Returns:** which variables an arbitrary expression depends on
- **Status:** [CONFIRMED] signature · [OPEN] body

### The AST

**[CONFIRMED]** — all nested inside `Compute`, all `private` except the
interface. Reaching them by name needs the **slash** form
(`SFS.Parsers.Constructed.Compute/I_Node`) and `NonPublic` binding flags.

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

> **Everything evaluates in `float32`.** `Compute.Variable` holds its
> source value as `double` and its `modifier` as `double`, but
> `get_Value()` converts **both to `float32` before multiplying**
> (`conv.r4`, `conv.r4`, `mul`). Precision matches the game only if a
> reimplementation does the same.

**[OPEN]** — whether `modifier` is a parser constant-folding artifact.
The field's presence *suggests* the parser folds a constant factor into a
variable reference, but that is inference, not IL.

---

## VariablesModule and VariableList&lt;T&gt;

**[CONFIRMED]** — `VariablesModule` @281584.

```csharp
class SFS.Variables.VariablesModule {
    public DoubleVariableList doubleVariables;
    public BoolVariableList   boolVariables;
    public StringVariableList stringVariables;
}
```

Each list is a `VariableList<T>` @~280700:

| Signature | IL |
|---|---|
| `public List<VariableSave> saves` | |
| `private List<VariableList<T>.Variable> _variables` | |
| `T GetValue(string variableName)` | @280782 |
| `Variable GetVariable(string variableName)` | @280807 |
| `void SetValue(string variableName, T newValue, ValueTuple<bool,bool> addMissingVariables = ...)` | @280870 |
| `bool Has(string variableName)` | @280907 |
| `void RegisterOnVariableChange(Action onChange, string name)` | @280954 |
| `List<string> GetVariableNameList()` | @280973 |
| `Dictionary<string,T> GetSaveDictionary()` | @280997 |
| `void LoadDictionary(Dictionary<string,T> inputs, ValueTuple<bool,bool> addMissingVariables)` | @281050 |
| `void AddVariable() / RemoveVariable(...) / RemoveVariableByIndex(int)` | |
| `bool SyncVariables(List<Variable> variables)` | @281141 |

`GetVariableNameList()` and `GetSaveDictionary()` are the two useful
enumeration entry points — the second is the same call `PartSave` uses,
so **the part's saved variable dictionary and its live variable state are
literally the same data**.

`SetValue` + `LoadDictionary` are the write side, and
`Composed_Float.GetResult` registers `Recalculate` against every variable
its expression uses — so **writing a variable propagates to every
dependent `Composed_*` automatically**. That is the mechanism a design
agent would use to resize a part and have mass, thrust and geometry all
follow.

**Status:** [CONFIRMED] API surface · [OPEN] all bodies. `VariableList<T>`
and its concrete subclasses get their own entries in Step 2.

---

## What this unblocks

- **Symbolic inspection.** `Composed_Float.input` exposes the raw
  expression text for any parametric field. A probe dump can record
  `"size * 0.05"` alongside the evaluated `0.1`, making part behaviour
  legible instead of a black-box number.
- **Dependency analysis without the game.**
  `Compute.GetVariablesUsed(string)` needs only a string.
- **A faithful Python evaluator is now cheap.** Four operators, literals,
  variables-with-modifier, `float32` arithmetic.
  `sfs_physics_reference.md` §1.2's "no Python-side evaluator exists" is
  a gap that can be closed deliberately rather than a blocker — **though
  it is still only worth doing if game-free evaluation is actually
  needed**; live reads already return correct values.
- **Parametric what-if.** `SetValue` on a variable then re-read the
  dependent `Composed_*.Value` gives the resized part's real numbers,
  computed by the game. **[UNTESTED-LIVE]**, and it **mutates live game
  state** — not something to do casually mid-flight.

## Reflection recipe

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

**Gotchas:**

- **`Compile` is overloaded** — resolve by explicit parameter types,
  using `MakeByRefType()` for the `out` parameter.
- The AST types are **nested and private** — `Compute/I_Node` with a
  slash, and `NonPublic` flags. `Get(node, "Value")` works because the
  probe's `Get` reads non-public properties.
- **Everything is `float32`.** Do not compare against `double` maths.
- `Composed_Float.input` on an **unplaced prefab** is still readable, but
  its `.Value` is **not** trustworthy — no bound variables.
- Setting a variable triggers registered `Recalculate` callbacks —
  intended, but it is a live mutation.

## Status summary

| Item | Status |
|---|---|
| `Composed_Float` holds `input` (expression) + `compiled` (AST) | [CONFIRMED] |
| `.Value` compiles and evaluates; live reads are already correct | [CONFIRMED] — explains §1.2 |
| Why static asset parsing gave wrong constants | [CONFIRMED] — no bound `VariablesModule` |
| `Compute.Compile` is public static | [CONFIRMED] |
| `Compute.GetVariablesUsed(string)` needs no game object | [CONFIRMED] |
| AST: `Number`, `Variable(modifier)`, `Add/Subtract/Multiply/Divide` | [CONFIRMED] |
| All arithmetic is `float32` | [CONFIRMED] |
| `VariablesModule` / `VariableList<T>` read + write API | [CONFIRMED] |
| Variable writes auto-propagate via `RegisterOnVariableChange` | [CONFIRMED] |
| `Compile` parser body — precedence, exact grammar | [OPEN] |
| Whether `modifier` is a parser constant-folding artifact | [OPEN] — inference, not IL |
| `GetVariablesUsed` body | [OPEN] |
| Parametric what-if via `SetValue` | [UNTESTED-LIVE] |
