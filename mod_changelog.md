# sfsprobe — Mod Changelog

Tracks changes to `sfsprobe/SFSProbe.cs`, the C# probe mod. One entry per
build that ships a real behavior change. Target build stays pinned to
Spaceflight Simulator **1.6.00.16** (Steam, macOS) — see README.md.

Format: newest first. `[reconstructed]` marks entries written after the
fact from session notes rather than logged at the time.

---

## v0.24 — 2026-08-26

- Added `achievements` command. Confirmed via IL that in-game
  "achievements" are internally `SFS.Logs.Challenge` — not Steamworks
  achievements (SFS has none registered). Reads the full catalog from
  the static `SFS.Base.worldBase.challengesArray`, and per-rocket
  completion from the real public method
  `Rocket.stats.challengeRecorder.GetCompleteChallenges()`. Writes
  `sfs_probe_achievements.json` (id, title, description, planet,
  difficulty, step count, completed flag per challenge). Built and
  installed clean; not yet run live against the game.

## v0.23 — 2026-08-26 `[reconstructed]`

- Separation-event capture now records **both** resulting rocket
  objects at the instant of a split (position, velocity, rotation,
  angular velocity, mass, part count) — not just whichever piece the
  game's camera happens to keep following.

## v0.14 → v0.23 — 2026-08-26, GPU Session #1 `[reconstructed]`

One overnight session, iterated live against the running game. Net
result: gravity, thrust, throttle response, fuel-flow rate,
player-commanded rotation, and staging momentum conservation all
empirically confirmed, most to well under 0.1% error. Aerodynamic
torque confirmed to exist as a real, isolated effect (magnitude still
open — see `sfs_physics_reference.md` §7.1).

Notable changes made along the way (not individually versioned at the
time):
- Split the old combined `throttle` command (which had a hidden
  side-effect of setting master ignition) into three independent,
  explicit steps: `throttle <0..1>` → `ignite` → `master on`.
- Switched command loop to a polled file pair (`command.txt`/
  `result.txt`), not a socket — avoids macOS firewall prompts.
- Fixed `Part.modules` walking to unwrap arrays and dedup by reference
  identity, not type name (was 6x-overcounting a single real engine).
- Split telemetry into `inputs.jsonl` (control signals) and
  `truth.jsonl` (actual outcomes), kept separate so a simulator built
  from one can be checked against the other without circularity.
- Added `forceInit` as an explicit opt-in reflection flag, applied only
  to already-placed flying parts, never bare catalog prefabs — calling
  it on a bare prefab was confirmed to hang the game
  (`EXC_BAD_ACCESS`, stack-guard/recursion signature).
- Confirmed (and left unfixed, tracked as open bugs) that
  `thrustDirX`/`thrustDirY`/`gimbalOn`/`throttleOut` never populate,
  and that `thrOn` doesn't reliably indicate actual thrust — use mass
  flatness instead.

## v0.14 — pre-2026-08-26 `[reconstructed]`

- Added `ignite` command: sets `EngineModule.engineOn` per engine.
  Needed because staging normally does this automatically, but
  `throttle` alone does not.
- Telemetry pipeline operational: per-tick `inputs.jsonl`/`truth.jsonl`
  streams, on-demand snapshots, remote command interface.
- Key physics formulas verified against the live assembly: drag force
  law, atmosphere density curve, gravity, thrust, rotational dynamics.

---

## Earlier history

Not individually logged — this file starts tracking from v0.14 onward.
Earlier versions (v0.1–v0.13) covered basic scaffolding: hooking the
update loop, reflection helpers for wrapped value types, initial
telemetry streaming. See `sfs_physics_reference.md` for what's
currently confirmed vs. open, regardless of which version confirmed it.
