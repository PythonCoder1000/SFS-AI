# `SFS.Variables` — the three wrapper bases

**Group file.** `Obs<T>`, `ReferenceVariable<T>` and `Composed<T>` are
documented together because they are the same problem seen three ways:
nearly every interesting value on a `Rocket`, `Part` or module is wrapped
in one of them, all three expose a public `Value`, and **they are not
related by inheritance** — a helper that handles one does not handle the
others. Getting the unwrapping right is a prerequisite for reading
anything else in this reference.

`SFS.Variables` has 36 types in the inventory (the old file said 37).
The other 33 are still [OPEN] — see `../INVENTORY.md`.
The expression evaluator behind `Composed_*` is in
[`../08-parametric-expressions/Compute.md`](../08-parametric-expressions/Compute.md).

**Migrated** from `docs/sfs_source_reference.md` §A3 (2026-08-28). Field
and method signatures re-read from IL during migration; two refinements
noted inline.

## The three families [CONFIRMED]

| Base | Concrete types | What it is |
|---|---|---|
| `Obs<T>` | `Float_Local`, `Double_Local`, `Int_Local`, `Bool_Local`, `String_Local`, `Vector2_Local`, `Double2_Local`, `Double3_Local`, `Planet_Local`, `Event_Local` | a plain observable value |
| `ReferenceVariable<T>` | `Float_Reference`, `Double_Reference`, `Bool_Reference`, `String_Reference` | a value that may be **local** or **bound to a named shared variable** |
| `Composed<T>` | `Composed_Float`, `Composed_Double`, `Composed_Vector2`, `Composed_Rect`, `Composed_Pipe`, `Composed_PipePoint` | an **expression** evaluated against a `VariablesModule` |

Plus `Obs_Destroyable<T>` (constrained to `I_ObservableMonoBehaviour`),
the `VariableList<T>` storage family (`DoubleVariableList`,
`BoolVariableList`, `StringVariableList`), `VariablesModule`,
`VariableSave`, and the value helpers `MinMaxRange`, `SizeRange`,
`Local_GenericTarget`. All [OPEN].

**All three bases expose a public `Value` property**, which is why a
single "unwrap anything with a `Value`" helper works across all of them.
But the three `Value` getters do materially different things, and two of
them have side effects.

---

## Obs&lt;T&gt;

**Namespace:** SFS.Variables
**Kind:** abstract class (generic, arity 1)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @279139 · 22 methods / 6 fields

A plain observable value: a backing field, an optional filter, and three
change-notification delegates.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `value` | `T` | private | no | the backing value | [CONFIRMED] |
| `hasFilter` | `bool` | private | no | set by the `Filter` setter; gates the filter call in `set_Value` | [CONFIRMED] |
| `filter` | `Func<T,T,T>` | private | no | `(old, new) -> effective`; may rewrite what a caller wrote | [CONFIRMED] |
| `onChange` | `Action` | private | no | fired after a real change | [CONFIRMED] |
| `onChangeNew` | `Action<T>` | private | no | fired after a real change, with the new value | [CONFIRMED] |
| `onChangeOldNew` | `Action<T,T>` | private | no | fired after a real change, with `(old, new)` | [CONFIRMED] |

### Methods

#### get_Value() -> T

- **Access:** public instance (`Value` property getter)
- **Returns:** the backing field
- **Behavior:** a plain field read.
- **Side effects:** none — unlike `Composed<T>.get_Value`.
- **Status:** [CONFIRMED]

#### set_Value(T value) -> void

- **Access:** public instance (`Value` property setter) · IL @279388
- **Parameters:** `value` — the requested new value; **not necessarily the value that lands**
- **Behavior:**
  ```csharp
  if (hasFilter) value = filter(this.value, value);   // filter may CHANGE what you wrote
  if (IsEqual(this.value, value)) return;             // no-op, no events, if unchanged
  T old = this.value;
  this.value = value;
  onChange?.Invoke();
  onChangeNew?.Invoke(value);
  onChangeOldNew?.Invoke(old, value);
  ```
- **Side effects:** fires up to three delegates, in the order above.
- **Gotchas:** two, both load-bearing for an agent writing control state.
  **(1)** `set_Filter` is public and the filter can rewrite the value — a
  write is not guaranteed to stick as given; read back after writing if
  it matters. **(2)** Writing an equal value fires *nothing*. `IsEqual`
  is `protected abstract`, so each concrete type defines equality; for
  the float types that is presumably exact comparison, but the per-type
  overrides were not surveyed — [OPEN].
- **Status:** [CONFIRMED]

#### set_Filter(Func&lt;T,T,T&gt; value) -> void

- **Access:** public instance (setter only — there is no `get_Filter`)
- **Behavior:** stores `filter` and sets `hasFilter`.
- **Status:** [CONFIRMED]

#### IsEqual(T a, T b) -> bool

- **Access:** `protected abstract` instance
- **Behavior:** defined by each concrete type; the equality test that
  decides whether `set_Value` is a no-op.
- **Status:** [CONFIRMED] signature · [OPEN] per-type overrides

#### get_OnChange() / set_OnChange(Obs&lt;T&gt;) -> Obs&lt;T&gt;

- **Access:** public instance
- **Behavior:** the getter returns **`this`**. Subscription is not `+=`
  on an event — it is `obs.OnChange += SomeMethod;` desugaring to
  `set_OnChange(op_Addition(get_OnChange(), method))`.
- **Gotchas:** in reflection this reads as a property whose getter and
  setter are both typed `Obs<T>`, which looks nonsensical until you see
  the operator overloads below.
- **Status:** [CONFIRMED]

#### op_Addition / op_Subtraction (Obs&lt;T&gt;, delegate) -> Obs&lt;T&gt;

- **Access:** public static
- **Overloads:** **three each**, differing only in delegate type —
  `Action`, `Action<T>`, `Action<T,T>` — routing to `onChange`,
  `onChangeNew`, `onChangeOldNew` respectively.
- **Gotchas:** ambiguous under naive `GetMethod(name, flags)`. Always
  pass explicit parameter types. See
  [`../REFLECTION_TOOLKIT.md`](../REFLECTION_TOOLKIT.md) §A1.1.
- **Status:** [CONFIRMED]

#### op_Implicit(Obs&lt;T&gt;) -> T

- **Access:** public static
- **Behavior:** implicit conversion to the wrapped value. This is why
  call sites read `arrowkeys.turnAxis` directly with no `.Value` — see
  [`../01-core-flight/Rocket.md`](../01-core-flight/Rocket.md).
- **Status:** [CONFIRMED]

#### op_Equality / op_Inequality (Obs&lt;T&gt;, Obs&lt;T&gt;) -> bool

- **Access:** public static
- **Status:** [CONFIRMED] signature · [OPEN] body

---

## ReferenceVariable&lt;T&gt;

**Namespace:** SFS.Variables
**Kind:** abstract class (generic, arity 1)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @280084 · 22 methods / 8 fields

A value that is either held locally or bound by name to a shared variable
on a `VariablesModule`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `variableName` | `string` | private | no | empty string means "unbound" | [CONFIRMED] |
| `referenceToVariables` | `VariablesModule` | **public** | no | the module the name resolves against; null means unbound | [CONFIRMED] |
| `localValue` | `T` | **public** | no | the local fallback — readable without invoking anything | [CONFIRMED] |
| `onLocalValueChange` | `Action` | private | no | change delegate | [CONFIRMED] |
| `onLocalValueChangeNew` | `Action<T>` | private | no | change delegate | [CONFIRMED] |
| `onLocalValueChangeOldNew` | `Action<T,T>` | private | no | change delegate | [CONFIRMED] |
| `initialized` | `bool` | private | no | set by `get_Variable` once resolution has been attempted | [CONFIRMED] |
| `variable` | `VariableList<T>.Variable<T>` | private | no | cached resolved variable | [CONFIRMED] |

> **Refinement during migration.** The old file called these "the three
> change delegates" by analogy with `Obs<T>`. The IL names them
> `onLocalValueChange` / `…New` / `…OldNew` — the `onChange*` names do
> **not** exist on this type. Anything reflecting on them by name must
> use the `onLocalValue*` form.

### Methods

#### get_Local() -> bool

- **Access:** public instance (`Local` property)
- **Returns:** true when the variable is **not bound to a shared
  variable**
- **Behavior:**
  ```csharp
  if (variableName.Length == 0) return true;
  if (referenceToVariables == null) return true;
  return Variable == null;
  ```
- **Gotchas:** **`Local` means "not bound", not "has a local
  override".** This is exactly the distinction `Rocket.GetTorque`
  exploits with `t.enabled.Local || t.enabled.Value` — treat an unbound
  torque module as enabled. Reading it as "overridden" inverts the
  meaning.
- **Status:** [CONFIRMED]

#### get_Value() / set_Value(T) -> T

- **Access:** public **virtual** instance (`newslot` — a concrete type
  may override)
- **Behavior:** `get => Local ? localValue : Variable.Value;` — the
  setter mirrors it, and short-circuits on `IsEqual` in the local branch
  exactly as `Obs<T>` does.
- **Gotchas:** `virtual`, and the per-type overrides were not surveyed —
  [OPEN]. A reflective read that resolves the base declaration rather
  than the runtime type could get the wrong body.
- **Status:** [CONFIRMED] base body · [OPEN] overrides

#### get_Variable() -> VariableList&lt;T&gt;.Variable&lt;T&gt;

- **Access:** public instance
- **Behavior:** lazily resolves via `GetVariable(variableName)`, caches
  into `variable`, sets `initialized = true`.
- **Side effects:** mutates `variable` and `initialized` on first read.
- **Status:** [CONFIRMED]

#### GetVariable(string variableName) -> VariableList&lt;T&gt;.Variable&lt;T&gt;

#### GetVariableList() -> VariableList&lt;T&gt;

- **Access:** `public abstract` instance
- **Behavior:** each concrete type knows which list on the
  `VariablesModule` it belongs to.
- **Status:** [CONFIRMED] signature · [OPEN] per-type bodies

#### IsEqual(T a, T b) -> bool

- **Access:** `protected abstract` instance — same role as on `Obs<T>`.
- **Status:** [CONFIRMED] signature · [OPEN] overrides

#### get_OnChange / set_OnChange / op_Addition / op_Subtraction

- Same shape as `Obs<T>`: getter returns `this`, and **three**
  `op_Addition` and **three** `op_Subtraction` overloads by delegate
  type. Ambiguous under naive lookup.
- **Status:** [CONFIRMED]

---

## Composed&lt;T&gt;

**Namespace:** SFS.Variables
**Kind:** abstract class (generic, arity 1)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @278513 · 18 methods / 5 fields

An expression evaluated against a `VariablesModule`. **The only one of
the three whose getter has side effects.** Base for `Part.mass` and
`Part.centerOfMass`.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `variables` | `VariablesModule` | **protected** | no | the module the expression is evaluated against | [CONFIRMED] |
| `initialized` | `bool` | private | no | latches only in play mode — see `CheckInitialize` | [CONFIRMED] |
| `value` | `T` | private | no | the cached result | [CONFIRMED] |
| `onChange` | `Action` | private | no | fired on a real change | [CONFIRMED] |
| `onChangeOldNew` | `Action<T,T>` | private | no | fired on a real change, with `(old, new)` | [CONFIRMED] |

Note there is **no `onChangeNew`** here — hence only two `op_Addition`
overloads instead of three.

### Methods

#### get_Value() -> T

- **Access:** public instance
- **Behavior:** `{ CheckInitialize(); return value; }`
- **Side effects:** **reading `.Value` can compile an expression and
  register callbacks.** On the first play-mode read, `GetResult(true)` on
  `Composed_Float` compiles the `input` string and subscribes
  `Recalculate` to every variable the expression uses.
- **Gotchas:** a probe that walks every field and unwraps everything with
  a `Value` is triggering expression compilation as a side effect of
  introspection. Harmless in practice — but worth knowing before blaming
  a first-frame stall on something else.
- **Status:** [CONFIRMED]

#### set_Value(T v) -> void

- **Access:** public instance
- **Behavior:**
  ```csharp
  initialized = Application.isPlaying;
  if (Equals(this.value, v)) return;            // no-op if unchanged
  T old = this.value; this.value = v;
  onChange?.Invoke();
  onChangeOldNew?.Invoke(old, v);
  ```
- **Side effects:** fires `onChange` and `onChangeOldNew`. This is the
  hop that drives mass updates — see
  [`../01-core-flight/Mass_Calculator.md`](../01-core-flight/Mass_Calculator.md).
- **Status:** [CONFIRMED]

#### CheckInitialize() -> void

- **Access:** private instance
- **Behavior:**
  ```csharp
  if (initialized) return;
  initialized = Application.isPlaying;          // false outside play mode
  Value = GetResult(initialized);               // note: passes the NEW flag
  ```
- **Gotchas:** **outside play mode `initialized` never latches**, so
  every `.Value` read re-runs `GetResult(false)` — a full recompile per
  read. Irrelevant for a running game; relevant if any tooling ever
  evaluates these headless.
- **Status:** [CONFIRMED]

#### Recalculate() -> void

- **Access:** `protected` instance
- **Behavior:** `Value = GetResult(false);`
- **Gotchas:** passes `initialize: false`, so a recalculation does
  **not** re-register callbacks — registration happens exactly once.
- **Status:** [CONFIRMED]

#### GetResult(bool initialize) -> T

#### Equals(T a, T b) -> bool

#### Overwrite(T a) -> void

- **Access:** `protected abstract` instance
- **Behavior:** `GetResult` is where the concrete type evaluates its
  expression; `initialize: true` additionally registers `Recalculate`
  against the variables used. `Equals` is the change test in `set_Value`.
  `Overwrite` call sites are [OPEN].
- **Status:** [CONFIRMED] signatures · [OPEN] `Overwrite` usage

#### get_OnChange / set_OnChange / op_Addition / op_Subtraction

- Same `this`-returning-getter shape. **Two** overloads each here
  (`Action`, `Action<T,T>`) — no `Action<T>` form, since there is no
  `onChangeNew`.
- **Status:** [CONFIRMED]

---

## Reflection notes (all three)

- The single `Value` property lookup works for all three families, but on
  `Composed<T>` it is **not** a pure read. See `get_Value` above.
- Each base declares `op_Addition` / `op_Subtraction` multiple times
  (three on `Obs<T>` and `ReferenceVariable<T>`, two on `Composed<T>`).
  Always pass explicit parameter types.
- `Composed_Vector2` has real `public Composed_Float x, y` fields — it is
  **not** a wrapper around a `Vector2` field. Confirmed while
  investigating the probe's `thrustDirX/Y` bug
  ([`../04-engines/EngineModule.md`](../04-engines/EngineModule.md)),
  where it ruled out the obvious explanation.
- `ReferenceVariable<T>.localValue` and `referenceToVariables` are
  **public fields**, so a bound value's local fallback can be read
  without invoking anything.
- The chain **variable write → `Composed.Recalculate` → `set_Value` →
  `onChange` → `MarkDirty` → `rb2d.mass`** is confirmed end to end.

## Status summary

| Item | Status |
|---|---|
| Three unrelated abstract bases | [CONFIRMED] |
| All three expose public `Value` | [CONFIRMED] |
| `Obs<T>` field layout and `set_Value` body | [CONFIRMED] |
| Filter can rewrite a written value | [CONFIRMED] |
| Equal writes fire no events | [CONFIRMED] |
| `ReferenceVariable<T>.Local` semantics and `Value` body | [CONFIRMED] |
| `ReferenceVariable<T>` delegates are named `onLocalValue*` | [CONFIRMED] |
| `Composed<T>.Value` compiles + registers on first play-mode read | [CONFIRMED] |
| `Composed<T>` recompiles every read outside play mode | [CONFIRMED] |
| `Recalculate` does not re-register | [CONFIRMED] |
| Multiple `op_Addition` / `op_Subtraction` ambiguity | [CONFIRMED] |
| Per-type `IsEqual` / `Equals` overrides | [OPEN] — not surveyed |
| Per-type `Value` overrides on `ReferenceVariable<T>` | [OPEN] — not surveyed |
| `Overwrite(T)` call sites | [OPEN] |
| `Obs_Destroyable<T>`, `MinMaxRange`, `SizeRange`, `Local_GenericTarget` | [OPEN] — named only |
| The other 33 `SFS.Variables` types | [OPEN] — Step 2 |
