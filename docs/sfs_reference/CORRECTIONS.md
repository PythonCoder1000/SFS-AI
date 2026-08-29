# Corrections ledger

Every claim in an earlier project document that this reference overturned,
collected so regressions stay visible rather than being silently
overwritten. Standing rule: **document corrections, never overwrite them.**

Migrated from `docs/sfs_source_reference.md` §"Corrections to earlier
documents" during Phase 1 Step 1 (2026-08-28), content unchanged. The
`Section` column still uses the old file's section IDs (§A4.2, §C1.0, …);
the mapping from those IDs to the new per-class files is in
[`INDEX.md`](INDEX.md) under "Old-file section map".

**This is not a per-class file** and so does not follow the per-class
template.

---

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
