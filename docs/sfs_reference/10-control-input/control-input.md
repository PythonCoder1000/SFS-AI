# Control and input — `Player`, `Arrowkeys`, `ArrowkeysDrawer`, `Throttle`, `ControlModule`

**Group file.** One important finding ties these five together: **the
safety gates on control input live in the UI layer, not in the model.**
An agent that writes the control variables directly is on a different
code path from one that simulates a keypress, and **the two do not
behave the same.**

**Migrated** from `docs/sfs_source_reference.md` §E2 (2026-08-28).

Consumers: [`../01-core-flight/Rocket.md`](../01-core-flight/Rocket.md),
[`../04-engines/EngineModule.md`](../04-engines/EngineModule.md),
[`../05-rcs/RcsModule.md`](../05-rcs/RcsModule.md).

---

## Player

**Namespace:** SFS.World
**Kind:** abstract class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @182697 · 6 methods / 4 fields

The base of `Rocket` (and of `Astronaut_EVA`). **Reading anything on a
`Rocket` that is declared here needs inherited lookup, not
`DeclaredOnly`.**

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `location` | `WorldLocation` | public | no | the live observable location | [CONFIRMED] |
| `mapPlayer` | `MapPlayer` | public | no | | [CONFIRMED] |
| `isPlayer` | `Bool_Local` | public | no | an `Obs<bool>` — **subscribable** | [CONFIRMED] |
| `hasControl` | `Bool_Local` | public | no | an `Obs<bool>` — **subscribable** | [CONFIRMED] |

### Abstract members

Five, all overridden by `Rocket`: `GetSizeRadius()`,
`ClampTrackingOffset(ref Vector2, float)`,
`OnInputEnd_AsPlayer(OnInputEndData)`, `TryWorldSelect(TouchPosition)`,
`CanTimewarp(I_MsgLogger, bool, out bool)`.

**Gotcha:** `hasControl` and `isPlayer` are `Obs<bool>`, so an agent can
**subscribe rather than poll**. `Rocket` maintains `hasControl` from its
`ControlModule` set — `Rocket.Awake`'s `b__17_0` / `b__17_1` /
`g__UpdateControl|17_2` recompute it as `controlModules.Any(m => …)`
whenever a `ControlModule` is added or removed.

---

## Arrowkeys

**Namespace:** SFS.World
**Kind:** class
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @182636 · 1 method / 6 fields

**Pure state.** Six fields, all public `Obs<T>`, and **the class has no
methods at all** beyond its constructor.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `rcs` | `Bool_Local` | public | no | RCS master toggle | [CONFIRMED] |
| `hasTurn` | `Bool_Local` | public | no | a turn key is held | [CONFIRMED] |
| `turnAxis` | `Float_Local` | public | no | rotation command, −1…+1 **by convention only** | [CONFIRMED] |
| `rawArrowkeysAxis` | `Vector2_Local` | public | no | undecomposed direction input | [CONFIRMED] |
| `horizontalAxis` | `Vector2_Local` | public | no | | [CONFIRMED] |
| `verticalAxis` | `Vector2_Local` | public | no | | [CONFIRMED] |

**It validates nothing, clamps nothing, and notifies nobody** beyond the
ordinary `Obs<T>` change events. Everything that consumes it does so by
reading:

- `Rocket.GetTurnAxis` reads `turnAxis` — **manual input overrides SAS
  whenever it is non-zero.**
- `Rocket.FixedUpdate` reads `rcs`, `horizontalAxis`, `verticalAxis` to
  produce `output_DirectionalAxis`.
- `RcsModule.RCS_On` reads `rcs`.

---

## ArrowkeysDrawer — where the gates actually are

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @161375 · 13 methods / 15 fields

The on-screen control pad: it owns
`SFS.UI.Button turnLeft/turnRight/left/right/up/down/rcsButton`, three
**private** `Float_Local` axes of its own, and two `MoveModule`
animations.

> **It is the *only* thing in `Assembly-CSharp` that writes
> `Arrowkeys.turnAxis`, `horizontalAxis`, `verticalAxis` or
> `rawArrowkeysAxis` for a rocket.** (`Astronaut_EVA.OnFixedUpdate` and
> `OnJumpKeyDown` read them for EVA; `Rocket`, `RocketManager`,
> `RocketSave` and `RcsModule` only read.) Grep-exhaustive over the six
> fields.

#### PushTurnAxis() -> void — the write path

- **Access:** instance · IL @161719, body read
- **Behavior:** two guards and an assign.
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
- **Status:** [CONFIRMED]

#### PushDirectionalAxis() -> void

- **Access:** instance · IL @161791 — the equivalent for translation,
  with its own local function `g__Reset|23_0`.
- **Status:** [PARTIAL] — guards confirmed, arithmetic not transcribed

### Consequences for the agent

All follow directly from **where** these checks sit.

1. **Writing `rocket.arrowkeys.turnAxis.Value` directly bypasses both
   gates.** Nothing between `Arrowkeys` and `Rocket.ApplyTorque`
   re-checks `hasControl` for the *manual* branch — `GetTurnAxis`
   consults `hasControl` only on the SAS path, and returns
   `arrowkeys.turnAxis` unconditionally when it is non-zero. **So a
   direct write turns an uncontrolled craft.**
2. **It also bypasses the timewarp block.** `ApplyTorque` gates only on
   `rb2d.simulated`, so a craft in physics mode during a low timewarp
   factor **will** respond to a directly-written `turnAxis`. Whether that
   is desirable is a design question, not a code question — but **it is
   not the behaviour a human gets.**
3. **Nothing clamps `turnAxis` to −1…+1.** The UI never writes outside
   that range, and `GetStopRotationTurnAxis` clamps its *own* output, but
   **the manual branch is passed through raw** into
   `angularVelocity -= torque·…·turnAxis·Δt`. **A written value of 100
   scales rotational authority by 100.** Mechanism confirmed from the
   opcodes; **never tested live** — and it is the kind of thing that
   would read as a physics discovery when it is really an unclamped
   input.

**Recommendation:** if the agent wants human-equivalent behaviour, it
should replicate the two guards itself. Driving `ArrowkeysDrawer`'s own
`turn_Axis` / `x_Axis` / `y_Axis` is not an alternative — those are
**private**, so the guards would have to be re-implemented anyway. Write
`Arrowkeys` directly and check `hasControl` and
`WorldTime.main.realtimePhysics` in the agent, **so the bypass is a
deliberate choice rather than an accident.**

`<Start>g__ToggleRCS|14_0` @161988 is `assembly static` — the RCS
toggle, reachable but not `public`.

---

## Throttle

**Namespace:** SFS.World
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @184675 · 3 methods / 3 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `throttleOn` | `Bool_Local` | public | no | input | [CONFIRMED] |
| `throttlePercent` | `Float_Local` | public | no | input, 0–1 | [CONFIRMED] |
| `output_Throttle` | `Float_Local` | public | no | **output — the authoritative commanded throttle** | [CONFIRMED] |

### Methods

#### Start() -> void

- **Access:** private instance · IL @184683
- **Behavior:** subscribes `UpdateThrottle` to `throttleOn.OnChange`
  **and** `throttlePercent.OnChange`.
- **Status:** [CONFIRMED]

#### UpdateThrottle() -> void

- **Access:** instance · IL @184711
- **Behavior:** one line —
  `output_Throttle.Value = throttleOn.Value ? throttlePercent.Value : 0f;`
- **Gotchas:** unlike `Arrowkeys`, **throttle *is* event-driven and
  recomputes on write** — an agent writing `throttlePercent.Value` gets
  `output_Throttle` updated **synchronously inside the setter**, before
  the write returns. `output_Throttle` is what reaches
  `EngineModule.throttle_Out` through the `INJ_Throttle` injection.

  **There is no gate here at all** — no `hasControl`, no timewarp check.
  **Throttle is symmetric between UI and direct write.**

  `throttlePercent` is **not clamped** in `UpdateThrottle`; whether the
  `Obs<float>` carries a filter that clamps it is **[OPEN]** —
  `Float_Local`'s filter, if any, is set elsewhere and was not traced.
- **Status:** [CONFIRMED]

> **`output_Throttle` is the value the probe should be logging** and
> currently does not — it reads `throttlePercent` and `throttleOn`
> separately and reconstructs. Equivalent in principle, but
> `output_Throttle` is the single value the engines actually receive.

---

## ControlModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @273288 · 1 method / 1 field

**One field, no methods.**

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `hasControl` | `Bool_Reference` | public | no | may be locally valued **or bound to a named variable** | [CONFIRMED] |

Being a `Bool_Reference`, **"does this capsule give control" can be a
part variable, not a constant.** The craft-level `Player.hasControl` is
derived from the set of these by `Rocket`'s `UpdateControl` local
function.

## Status summary

| Item | Status |
|---|---|
| `Player` field layout and 5 abstract members | [CONFIRMED] |
| `Arrowkeys` is pure state, six `Obs<T>`, no methods | [CONFIRMED] |
| `ArrowkeysDrawer` is the sole writer for rockets | [CONFIRMED] — grep-exhaustive over the six fields |
| `PushTurnAxis` guards: `hasControl`, `realtimePhysics` | [CONFIRMED] |
| Direct writes bypass both guards | [CONFIRMED] — from where the checks sit |
| `turnAxis` is unclamped on the manual branch | [CONFIRMED] opcodes · [UNTESTED-LIVE] effect |
| `Throttle.UpdateThrottle` body; event-driven, ungated | [CONFIRMED] |
| `ControlModule` is a single `Bool_Reference` | [CONFIRMED] |
| Whether `throttlePercent` carries a clamping filter | [OPEN] |
| `PushDirectionalAxis` body | [PARTIAL] — guards confirmed, arithmetic not transcribed |
| Keyboard/gamepad binding path into `ArrowkeysDrawer` | [OPEN] |
| `SFS.Input` (27 types), `Astronaut_EVA`, `PlayerController` | [OPEN] — Step 2 |
