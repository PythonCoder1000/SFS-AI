# Python — Changelog

Tracks Python-side work for the SFS agent: physics models, solvers,
analysis scripts, and (later) the design/flight agent code itself.
Not version-numbered like the mod — dated entries, newest first.

---

## 2026-08-26

- **Two-body orbit solver**, built from scratch. Matches the game's own
  `Physics.GetTrajectory()` output to two decimal places at every
  sampled tick of a real coast, and matched the real eventual outcome
  of a 370km climb to 6.6m (0.0018%) — predicted *before* the rocket
  got there.
- **Lower-envelope / visible-surface solver**, built to eventually
  compute `dragArea` once real part geometry is available (see
  `sfs_physics_reference.md` §7.1 — geometry capture is still blocked
  on a Harmony patch, not yet written). Validated against synthetic
  test cases: 5/5 passed, including exact full-shielding and
  partial-shielding numbers, with the "pointed shape has lower drag"
  physical intuition falling out naturally from the formula. Not yet
  fed real geometry.

---

## Earlier history

No Python code existed before this date — the project was
research/planning only until the 2026-08-26 session (see
`SFS_Starting_point_Context` and `session-2026-08-26-gpu-session-1.md`
for the full narrative).
