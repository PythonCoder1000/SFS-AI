# Joints, splitting, and docking — `PartJoint`, `JointGroup`, `DetachModule`, `DockingPortModule`

**Group file.** `JointGroup` is the craft's connectivity graph. It is the
authority for three things an agent needs — **what is attached to what,
what happens when a part is destroyed, and where the fuel groups come
from.**

**Migrated** from `docs/sfs_source_reference.md` §E3 and §E3.5.1
(2026-08-28).

Fuel side:
[`../09-resources-fuel/resources-and-flow.md`](../09-resources-fuel/resources-and-flow.md).
Spawning/merging:
[`../07-saveload/RocketManager.md`](../07-saveload/RocketManager.md).

---

## PartJoint

**Namespace:** SFS.World
**Kind:** class (`serializable`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @186373 · 3 methods / 3 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `a` | `Part` | public | no | one end | [CONFIRMED] |
| `b` | `Part` | public | no | the other end | [CONFIRMED] |
| `anchor` | `Vector2` | public | no | attachment point | [CONFIRMED] |

### Methods

`GetOtherPart(Part)` @186402 and `GetRelativeAnchor(Part)` @186432.
**[PARTIAL]** — signatures confirmed.

> **An undirected edge with an attachment point.** There is **no
> strength, no break force, and no joint type**: SFS joints are **graph
> edges, not Unity `Joint2D` components.** Structural failure is
> therefore **not simulated as joint stress** — it happens when a part is
> destroyed.

---

## JointGroup

**Namespace:** SFS.World
**Kind:** class (`serializable`)
**Extends:** System.Object
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @186469 · 15 methods / 3 fields

### Fields

All public.

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `dictionary` | `Dictionary<Part, List<PartJoint>>` | public | no | **the adjacency index — a real index, not a memo, so it can be enumerated safely** | [CONFIRMED] |
| `joints` | `List<PartJoint>` | public | no | | [CONFIRMED] |
| `parts` | `List<Part>` | public | no | | [CONFIRMED] |

The constructor takes `(List<PartJoint>, List<Part>)` and builds
`dictionary` via `AddJointToDictionary`. **Unlike `Part.modules`, this is
a genuine index** — enumerating it is correct.

### Methods

#### RecreateGroups(out List&lt;JointGroup&gt; newGroups) -> void

- **Access:** public instance · IL @186723, transcribed from the opcodes
- **Behavior:** a **stack-based flood fill**.
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
- **Gotchas:** **"did the craft split" is answered by connected-component
  count.** This is pure graph work — **no physics, no geometry, no
  distance test.**
- **Status:** [CONFIRMED]

#### GetResourceGroups() -> List&lt;List&lt;ResourceModule&gt;&gt;

- **Access:** public instance · IL @187092
- **Behavior:** the same flood fill, seeded from parts that
  `HasModule<ResourceModule>()` and walking the same `dictionary`.
- **Gotchas:** its output is what `Resources.SetupResourceGroups` turns
  into fuel groups — **confirming that fuel connectivity is exactly
  structural connectivity**, with no separate plumbing graph.
- **Status:** [CONFIRMED]

`GetConnectedFairings(Part, SplitModule)` @187292 is a third traversal
over the same index. **[PARTIAL]**

Other public members: `AddJoint(PartJoint)`,
`RemovePartAndItsJoints(Part)`, `RepositionParts()`,
`GetConnectedJoints(Part)` @187397 (a `dictionary` lookup).
**[PARTIAL]** — signatures.

### Destruction and splitting

Three **public static** entry points:

```csharp
static void OnPartDestroyed(Part part, Rocket rocket, DestructionReason reason);       // @186556
static void DestroyJoint(PartJoint joint, Rocket rocket,
                         out bool split, out Rocket newRocket);                        // @186603
static List<JointGroup> RecreateRockets(Rocket rocket, out List<Rocket> childRockets); // @186641
```

`OnPartDestroyed` is what `Part.DestroyPart` calls when
`updateJoints == true`, and it carries a local function
`g__SetFirstControllableChildAsPlayer|5_0` (`assembly static`) — so
**when the player's craft splits, control transfers to the first
controllable child**, matching `Rocket.SetPlayerToBestControllable`.

#### RecreateRockets — structure read

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

**The surviving `Rocket` is re-anchored** — its `LocalPosition` (which is
the **centre of mass**) is shifted by the transformed position of the
first remaining part, **because the CoM moves when mass is removed.**

Each additional group becomes a new `Rocket` via
`RocketManager.CreateRocket_Child(JointGroup, Rocket parentRocket,
Vector2 offset)`, which is **public static** and takes an explicit
offset — **the programmatic route to splitting a craft.**

**Status:** [CONFIRMED] structure · **[PARTIAL]** — the child-creation
loop body was not read.

---

## DetachModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED] layout · [PARTIAL] bodies
**Depth:** FULL
**IL:** `scratch/full_il.txt` @260322 · 9 methods / 11 fields

Separators.

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `separationSurface` | `SurfaceData` | public | no | which face separates | [CONFIRMED] |
| `separationForce` | `Composed_Vector2` | public | no | **parametric** — scales with part size like mass does | [CONFIRMED] |
| `forceMultiplier` | `Float_Reference` | public | no | | [CONFIRMED] |
| `cannotDetachIfSurfaceCovered` | `bool` | public | no | | [CONFIRMED] |
| `surfaceForCover` | `SurfaceData` | public | no | | [CONFIRMED] |
| `activatedByLES` | `bool` | public | no | launch-escape-system trigger | [CONFIRMED] |
| `onDetach` | `UnityEvent` | public | no | | [CONFIRMED] |
| `showDescription`, `showForceMultiplier`, `useForceMultiplierEvenIfNotShown` | `bool` | public | no | UI | [CONFIRMED] |

### Methods

#### Detach(UsePartData data) -> void

- **Access:** **public** · IL @260496
- **Behavior:** **the programmatic separation call.** It takes the same
  `UsePartData` that `Rocket.UseParts` produces.
- **Gotchas:** private `Use` and `ForceMultiplier` properties gate it.
- **Status:** [PARTIAL] — body not read

---

## DockingPortModule

**Namespace:** SFS.Parts.Modules
**Kind:** class
**Extends:** UnityEngine.MonoBehaviour
**Implements:** —
**Status:** [CONFIRMED]
**Depth:** FULL
**IL:** `scratch/full_il.txt` @248764 · 17 methods / 12 fields

### Fields

| Name | Type | Access | Static | Description | Status |
|---|---|---|---|---|---|
| `trigger` | `DockingPortTrigger` | public | no | populates `portsInRange` | [CONFIRMED] |
| `occupationSurface` | `SurfaceData` | public | no | | [CONFIRMED] |
| `dockDistance` | `float` | public | no | **the only docking precondition** | [CONFIRMED] |
| `pullDistance` | `float` | public | no | | [CONFIRMED] |
| `pullForce` | `float` | public | no | | [CONFIRMED] |
| `forceMultiplier` | `Float_Reference` | public | no | | [CONFIRMED] |
| `isOccupied`, `isOnCooldown`, `isDockable` | `Bool_Local` | public | no | | [CONFIRMED] |
| `portsInRange` | `List<DockingPortModule>` | **private** | no | | [CONFIRMED] |

### Methods

#### FixedUpdate() -> void

- **Access:** private instance (Unity message) · IL @249003, transcribed
- **Behavior:**
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
- **Gotchas:** three.
  - **Docking is a plain distance test** between port transforms against
    `dockDistance` — **no closing-velocity check and no approach-angle
    rejection**. (See the correction under `Dock` below on alignment.)
  - Outside `dockDistance` the port applies a **magnetic pull**:
    `pullForce · forceMultiplier · 2` along the line between ports,
    applied at the **port's own position**, so it produces **torque as
    well as translation**. The `× 2` is a bare literal.
  - The pull is applied to **every** dockable port in `portsInRange`, not
    just the nearest — **a cluster of ports pulls cumulatively.**
- **Status:** [CONFIRMED]

`portsInRange` is maintained by the public `AddPort` / `RemovePort`
@249259 / @249284, driven by `DockingPortTrigger`, filtered by the
private `IsValidPort` @249310 — **[OPEN]**, so whether *it* enforces
alignment is unconfirmed. `UpdateOccupied()` @248873 is public;
`isOnCooldown` + `EndCooldown` @248942 prevent immediate re-dock after
undocking.

#### Dock(DockingPortModule otherPort) -> void

- **Access:** **private** · IL @249100, body read
- **Behavior:**
  ```csharp
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
  ```
- **Gotchas:** four.

  **(1) The player guard is what breaks the symmetry.** Both ports run
  `FixedUpdate` and both would otherwise call `Dock` on each other in the
  same tick. The early return means the dock is always performed by the
  port whose **partner is not the player** — so exactly one side
  executes, and if neither craft is the player, whichever port's
  `FixedUpdate` runs first wins. **It is a mutual-exclusion device, not a
  permission check.**

  **(2) CORRECTION to the "no alignment check" reading.** More precisely:
  **the game does not *reject* misalignment — it *forces* alignment.**
  The relative port heading is computed, `+ 180°` applied (ports face
  each other), and then **snapped to the nearest 90°** by
  `RoundToInt(z / 90f) * 90`. **So SFS docking is quantised to four
  orientations**, and a craft arriving at 44° off is rotated to 0° while
  one at 46° is rotated to 90°. There is still no *closing-velocity* gate
  and no *approach-angle* rejection — the distance test is the only
  precondition.

  **(3) The entire other craft is rigidly rotated**, not just the port:
  every `Part`'s `orientation` gets `rot` added, and every `PartJoint`'s
  `anchor` is multiplied through it so attachment points follow. This
  happens **instantaneously, in one frame, with no interpolation** — an
  agent watching part positions across a dock will see **a discontinuous
  jump of up to 45°.**

  **(4) The merge itself is
  `RocketManager.MergeRockets(Rocket rocket_A, Part part_A, Rocket
  rocket_B, Part part_B, Vector2 anchor)` @191331 — `public static`**,
  called here with `Vector2.zero` as the anchor. **This is the
  programmatic docking entry point**, the counterpart to
  `RocketManager.CreateRocket_Child` for splitting. Its body is **not
  read — [PARTIAL]** — so how it reconciles the two `JointGroup`s, and
  whether it invokes `Staging.OnMerge` / `StatsRecorder.OnMerge`, is
  still unconfirmed. The three `OnMerge` methods existing across staging,
  stats and resources strongly suggests it does, **but that is inference
  and is marked as such.**

  The trailing `PlayerController` call compensates the camera for the
  centre-of-mass shift the merge causes — `comBefore` is captured
  **before** `MergeRockets` precisely for that. It confirms that **a
  merge moves the craft's CoM**, so an agent tracking position across a
  dock must expect a step change there too.
- **Status:** [CONFIRMED]

### Orientation

`SFS.Parts.Modules.Orientation` @272510 is a small serialisable class —
`public float x, y, z` plus `InversedAxis()`,
`op_Multiply(Vector2, Orientation)`,
`op_Addition(Orientation, Orientation)` and `GetCopy()`. The `x`/`y`
components passed as `1f, 1f` in `Dock` are **mirror/scale factors**,
left unchanged by a dock. Own entry [OPEN] — Step 2.

## Status summary

| Item | Status |
|---|---|
| `PartJoint` is an undirected edge, no strength/type | [CONFIRMED] |
| `JointGroup` field layout; `dictionary` is a real adjacency index | [CONFIRMED] |
| `RecreateGroups` is a stack-based flood fill | [CONFIRMED] |
| Splitting is connected-component counting, no physics | [CONFIRMED] |
| `GetResourceGroups` uses the same traversal → fuel = structural connectivity | [CONFIRMED] |
| `OnPartDestroyed` / `DestroyJoint` / `RecreateRockets` are public static | [CONFIRMED] |
| Surviving rocket's `LocalPosition` is re-anchored on split | [CONFIRMED] |
| Control transfers to first controllable child | [CONFIRMED] — from the local function's name and `SetPlayerToBestControllable`; body not read |
| `DetachModule` layout; `Detach(UsePartData)` is public | [CONFIRMED] |
| `separationForce` is parametric | [CONFIRMED] |
| `DockingPortModule` layout | [CONFIRMED] |
| Docking's only precondition is the distance test; no closing-velocity gate | [CONFIRMED] |
| Alignment is **forced, not checked** — snapped to nearest 90° | [CONFIRMED] |
| Magnetic pull `pullForce · forceMultiplier · 2`, applied per port in range | [CONFIRMED] |
| `Dock` is private, but `RocketManager.MergeRockets` is public static | [CONFIRMED] |
| `Dock` body incl. the player-guard mutual exclusion | [CONFIRMED] |
| Whole other craft rigidly rotated in one frame | [CONFIRMED] |
| `MergeRockets` body — joint reconciliation, whether it fires `OnMerge` | [PARTIAL] / [OPEN] (the `OnMerge` link is inference) |
| `RecreateRockets` child-creation loop | [PARTIAL] |
| `DetachModule.Detach` body and its gates | [PARTIAL] |
| Whether `IsValidPort` enforces alignment | [OPEN] — body not read |
| `DestroyJoint` body | [PARTIAL] |
| `DockingPortTrigger`, `SplitModule`, `Orientation`, `UsePartData` own entries | [OPEN] — Step 2 |
