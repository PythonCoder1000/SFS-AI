# Active state

_Last updated: 2026-08-30. Session context: closed out heat validation completely (found and fixed a real formula bug via live comparison), re-verified RCS against direct IL, and live-validated RCS's selection gate on a manual test flight._

## Current state
- `sfsprobe` version: **v0.44.0**, compiled and installed, confirmed live.
- Test rocket in use: Capsule / Parachute / Heat Shield / Separator / 4x Fuel Tank / 6x RCS Thruster (3-nozzle clusters, symmetry-placed) / 2x Aerodynamic Nose Cone / 3x Hawk Engine — 19 parts.
- Physics items status (of the original four "confirmed from code, untested live"):
  - **Heat: fully closed.** Formula confirmed exact against the game's own live computation (0.0001% mean error, 2,989 samples). Full accumulation model validated against a real destruction event (0.18% mean peak error, 7 parts).
  - **Multi-engine: fully closed** (0.14% median error, live-validated a prior session).
  - **RCS: partially validated.** Selection gate (`TorqueThrust`'s `|TurnAxis|≥0.95 OR |angv|≥2`) confirmed live at 99.63% (4081/4096 samples). Force magnitude/direction and the quadratic-scaling arithmetic NOT yet validated.
  - **Terrain: untouched.** No live validation attempted at all yet.
- `docs/sfs_reference/05-rcs/RcsModule.md` and `docs/high_level_checklist.md` both updated this session with the RCS live-validation result.

## Monitored hooks / variables
- `heatParts` (truth.jsonl, per tick): real per-part `{name, temperature, heatTolerance, isHeatShield, exposedSurface}`. `exposedSurface` correctly filtered through the real `RemoveHighSlopeSurfaces`/`ApplyProtectionZone` (confirmed via IL, v0.41.0).
- `realAirTemp` (truth.jsonl, per tick): the game's own live `AeroModule.GetTemperatureAndShockwave` output, called directly — used as ground truth to validate the Python air-temp formula. Diagnostic only; not needed for normal recording now that the formula is confirmed exact.
- `rcsOn`, `rcsFiring`, `directionalAxisX/Y`, `turnAxis` (inputs.jsonl, per tick): everything needed to reconstruct `TorqueThrust`/`DirectionThrust`'s firing decision. `rcsFiring` reads the real per-tick `targetTime` state the game itself sets — not a reimplementation.
- `rcsinfo` (on-demand command): live per-`RcsModule` dump of `directionAngleThreshold`, `torqueAngleThreshold`, `thrust`, `ISP`, `thrustPosition`, per-thruster local `thrustNormal`.

## Unresolved behaviors
- RCS force magnitude/direction: unvalidated. Blocked on (a) an engines-off test flight (the one just flown had main engines burning throughout, so RCS's own contribution to acceleration can't be isolated by finite-difference), and (b) per-part world orientation telemetry, which doesn't exist yet — needed to turn `rcsinfo`'s local `thrustNormal` values into real world-space vectors and reconstruct `sumNormal`.
- The confirmed "force scales with the *square* of firing-thruster count" arithmetic (read correctly from IL, `sumNormal · (thrust · count · 9.8)`) has never been checked against a real measurement. Still just a reading of the code.
- Terrain formulas: fully unread this session, not even a documentation pass done.

## Abandoned paths
- **Heat formula, multiplicative ascent-correction term** (`t += t * (tempOffset·X + 0.2)`) — this was the earlier, WRONG transcription of `AeroFormula.GetTemperature`. Confirmed wrong via direct IL re-read; the real formula is additive (`t += tempOffset · (X + 0.2)`). Do not reintroduce this form. The correct version is what's live in `python/sfs_telemetry.py`'s `predicted_reentry_temperature`.
- **`heatParts`'s `ExposedSurface` computed from the raw drag-path exposed-surfaces list** (pre-v0.41.0) — wrong; the real heating path filters that list through `RemoveHighSlopeSurfaces`+`ApplyProtectionZone` first, which the drag path does NOT apply. Fixed in v0.41.0 by calling those two real functions via reflection rather than reimplementing the geometry.
- **`telemetrysnapshot`'s first implementation** (early v0.42.0, since replaced) — copied the accumulated `truth.jsonl`/`inputs.jsonl` FILES without stopping recording. Wrong interpretation of what was wanted; the real ask was a one-tick read of current values, independent of recording state. Replaced same session by extracting `BuildInputsSample`/`BuildTruthSample` out of `Sample()` and calling them directly on demand.
- **Assuming `predApo`/`predPeri`/`predEcc` telemetry is reliable** — confirmed live 2026-08-30 that it can be wildly wrong even via the already-fixed `GetTrajectory()` call (reported ~369km apex for a flight whose real apex, confirmed two independent ways, was ~54km). Never trust these fields as ground truth; compute from real position/velocity with the confirmed gravity formula instead.
- **Trusting "[CONFIRMED]" status in this project's own docs without re-checking against real IL when something looks off** — the heat formula bug sat in the docs as "[CONFIRMED]" for a prior session's worth of time before being caught. The catch only happened because a live-vs-Python comparison tool (`realAirTemp`) was built and actually run — re-reading the same (wrong) documentation summary again would not have caught it.

## Immediate next experiment
Fly a clean, engines-off RCS test: on the pad or in a stable coast (no main-engine burn concurrent with RCS use, so mass and thrust stay constant and RCS's own contribution to angular acceleration can be isolated by finite-difference), exercise `TurnAxis` across a range that spans the 0.95 gate and test `angv`-triggered damping separately. Before that flight, add per-part world orientation to telemetry (new probe field — likely `transform.eulerAngles.z` or equivalent per part, needed to convert `rcsinfo`'s local `thrustNormal` into real world vectors) so `sumNormal` can actually be reconstructed and the quadratic force-scaling claim can finally be checked against a real number.
