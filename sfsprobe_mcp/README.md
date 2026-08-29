# sfsprobe_mcp

MCP server wrapping sfsprobe's file-based command protocol (write
`command.txt`, poll `result.txt`) with real adaptive polling instead of a
fixed sleep. Every tool reports `elapsed_seconds`. Built 2026-08-28.

## Why this exists

Talking to the sfsprobe mod by hand meant: write `command.txt`, sleep a
fixed guess (too long or too short), read `result.txt`, hope nothing
raced. This server replaces that with a proper adaptive-polling primitive
and a set of purpose-built tools on top of it.

## Tools

**Live game interaction:**
- **`sfsprobe_send_command`** -- generic escape hatch, send any raw
  command (`throttle 0.8`, `master on`, `ignite`, `revert`,
  `achievements`, `geometry`, `snapshot`, `diag`, `autostop`, `cheat`, ...).
- **`sfsprobe_send_batch`** -- send up to 100 commands in ONE call,
  executed together in a single game tick (uses the mod's own
  multi-line `command.txt` support, not a loop of separate calls).
  Built for startup sequences, e.g. `['throttle 1', 'ignite',
  'telemetry on', 'master on']` -- order `master on` last so telemetry
  is already recording before liftoff actually fires. Handles the
  `world`/`menu` silent-command gotcha automatically (see below) and
  returns partial results on timeout rather than discarding them.
- **`sfsprobe_ping`** -- structured scene/rocket-count/fixedDelta check.
- **`sfsprobe_get_dragarea`** -- runs `dragarea`, returns the parsed
  drag/CoP numbers directly (reads `sfs_probe_dragarea.json` for you).
- **`sfsprobe_telemetry_start`** / **`sfsprobe_telemetry_stop`** -- full
  or scoped-mode recording (v0.29+ field specs, e.g.
  `["h", "vv", "computed:dragArea"]`).
- **`sfsprobe_status`** -- is the game even running / is the mod loaded,
  without guessing from a timeout. Checks mod folder existence,
  `probe.log` staleness, and a real short-timeout ping.
- **`sfsprobe_tail_file`** -- read-only tail of
  `probe.log` / `truth.jsonl` / `inputs.jsonl`, with optional JSON
  parsing for the telemetry files. Sends no command at all.
- **`sfsprobe_rocket_summary`** / **`sfsprobe_part_lookup`** -- runs
  `snapshot` live and reads the active rocket's real part list
  (mass always available; thrust/ISP best-effort, honestly reported as
  not-found rather than guessed if not recognizable in the dump).
- **`sfsprobe_run_flight_script`** -- run an ordered sequence of
  command batches, fixed delays, and **live-telemetry-condition waits**
  (`{'wait_until': {'field':'h','op':'>','value':2000}}`) in one call --
  enables condition-based flight profiles ("cut engine once altitude
  exceeds X") that are repeatable across different rocket designs.
- **`sfsprobe_run_and_analyze`** -- runs a flight script, then
  auto-finds the newly-archived flight and runs `flight_summary` +
  gravity/drag validation on it, optionally tagging the result. Closes
  the test -> analyze loop into one call.

**Telemetry analysis** (works on the live flight or any archived file --
omit `path` for live, or pass an `archive/*_truth_*.jsonl` path):
- **`sfsprobe_field_stats`** -- min/max/mean/median/stddev for any
  field(s), with optional `scope` (see below).
- **`sfsprobe_field_search`** -- find samples matching a condition
  (`h > 10000`, `vv < 0`).
- **`sfsprobe_downsample`** -- reduce thousands of samples to N
  evenly-spaced ones, for quick eyeballing or charting.
- **`sfsprobe_field_at_time`** -- the sample nearest a given game time.
- **`sfsprobe_flight_summary`** -- duration, altitude/velocity range,
  mass, part count, max temp, body -- the "what happened" tool.
- **`sfsprobe_phase_detect`** -- segments a flight into named phases
  (prelaunch/powered_ascent/coast_ascent/coast_descent/powered_descent)
  from mass-trend + vertical-velocity sign. **Heuristic**, not a read of
  the game's own internal state -- treat boundaries as approximate.
- **`sfsprobe_find_events`** -- locates named, indexable events
  (engine_start/cutoff, apoapsis, periapsis, max_velocity,
  max_dynamic_pressure, part_count_drop, impact).
- **`sfsprobe_validate_gravity_drag`** -- the generalized
  `analyze_dragarea.py` check: predicted (gravity+drag) vs measured
  acceleration over clean coasting pairs, with optional `scope`.
- **`sfsprobe_noise_floor`** -- the determinism check from the original
  architecture doc: compare two nominally-identical flights' divergence.
- **`sfsprobe_clean_segments`** -- exposes the coasting/burning segment
  finder standalone.
- **`sfsprobe_apoapsis_periapsis`** -- observed (from real position
  extrema) vs the game's own live `predApo`/`predPeri` prediction.
- **`sfsprobe_delta_v`** -- Tsiolkovsky rocket-equation estimate from
  mass loss; requires an explicit `isp` (not reliably in telemetry) or
  returns an honest note instead of a fabricated number.
- **`sfsprobe_divergence_check`** -- compares the flight's final sample
  against target field values -- the observer-gate primitive from the
  architecture doc.
- **`sfsprobe_compare_flights`** -- two flights side by side on chosen
  fields.
- **`sfsprobe_regression_check`** -- re-checks an OLD archived flight
  against the CURRENT formula code with a pass/fail verdict -- the
  literal "does our mod still work" check, for after an SFS update.

**Scoping (Stage 3):** `field_stats`, `downsample`, and
`validate_gravity_drag` all accept an optional `scope` dict to restrict
analysis to part of a flight: `{'phase': 'ascent'}`,
`{'time_range': [t1, t2]}`, `{'before_event': 'impact', 'window_s': 10}`,
`{'after_event': 'engine_cutoff'}`, `{'around_event': 'apoapsis',
'window_s': 5}`. If no matching phase/event is found, scope silently
falls back to the full flight range -- worth double-checking
`scoped_range` in the response if the numbers look unexpectedly broad.

**Bookkeeping:**
- **`sfsprobe_list_flights`** / **`sfsprobe_tag_flight`** -- so results
  accumulate across sessions instead of evaporating. `tag_flight` writes
  to `flights_log.jsonl` at the project root.
- **`sfsprobe_flight_to_csv`** -- export for spreadsheet/external tools.
- **`sfsprobe_checklist_status`** -- parses `docs/high_level_checklist.md`
  and reports confirmed vs open items per section.

**Blueprint loading (Stage 12):**
- **`sfsprobe_load_blueprint`** -- loads a rocket design directly,
  bypassing the editor UI's file picker. Resolves by `name` (looked up
  in `blueprints/research/<name>/Blueprint.txt`) or an explicit `path`.
  Two modes via `target`: **`'build'` (default, SAFE, routinely
  repeatable)** -- the real "Load Blueprint" button mechanism
  (`BuildState.LoadBlueprint`), REPLACES the current editor design,
  requires `Build_PC`, **not yet live-tested**; **`'world'` (DO NOT USE
  DURING A LIVE FLIGHT)** -- spawns an additional rocket into an active
  flight (`RocketManager.SpawnBlueprint`), requires `World_PC`.
  **Confirmed working live** (single-part blueprint spawned a real,
  visually-confirmed part, 2026-08-29) -- but that only proves the
  reflection mechanism works, not that using it mid-flight is safe or
  intended. Its first action moves the camera to the launch pad, the
  signature of a one-time internal Launch-transition primitive, not a
  general spawn tool; materializes a fully-fueled part outside any
  normal game state, functionally cheating. Reserve for one-off
  research only. Maps the mod's distinct `reason=` failure tokens to
  proper `error_code` values: `NOT_IN_BUILD` / `NOT_IN_WORLD`,
  `FILE_NOT_FOUND`, `FILE_ERROR`, `TYPE_RESOLUTION_FAILED`,
  `PARSE_ERROR`, `SPAWN_FAILED`. Multi-part blueprints and a documented
  possible DLC/ownership gate remain untested for both targets.

## Known protocol gotcha (handled by `sfsprobe_send_batch`, worth knowing generally)

`world` and `menu` are the only two commands that write NO line to
`result.txt` on success -- they only write to `probe.log`
(`DumpWorld()`/`DumpMenu()` in `SFSProbe.cs` never call `ProbeMod.Result()`).
Every other command handler calls `Result()` exactly once. If you ever
call `sfsprobe_send_command` with `world` or `menu` directly, expect a
timeout -- there's nothing to wait for. Use `sfsprobe_tail_file` on
`probe_log` to confirm they ran instead.

## Analysis engine

All telemetry analysis logic lives in `python/sfs_telemetry.py` (at the
project root, not inside this folder) -- an importable module shared
between this MCP server and any standalone script. `analyze_dragarea.py`'s
original logic now lives there too, generalized; the standalone script
still works as a thin CLI if you don't want to go through the MCP server.

Known limitation from real testing (2026-08-28): `location.time` ('t' in
telemetry) has been observed NOT strictly monotonic across at least one
archived flight -- `flight_summary`'s `time_anomaly` field flags this
when it happens rather than silently returning a nonsensical negative
duration. Root cause not yet confirmed.

## Setup

```bash
cd sfsprobe_mcp
python3 -m venv venv
PYTHONPATH= venv/bin/pip install -r requirements.txt
```

**Important:** the `mac-terminal-mcp` Claude extension sets its own
`PYTHONPATH` pointing at its bundled `mcp` package (v2.0.0, which renamed
`FastMCP` to `MCPServer` and will break this server). Any terminal
session spawned through that extension inherits this. Always clear it
explicitly (`PYTHONPATH=` prefix) when installing or running inside a
`mac-terminal-mcp` session -- a plain Terminal.app window won't have this
problem.

## Registering with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sfsprobe": {
      "command": "/Users/christianjin/Documents/VSCode/SFS AI/sfsprobe_mcp/venv/bin/python3",
      "args": ["/Users/christianjin/Documents/VSCode/SFS AI/sfsprobe_mcp/server.py"]
    }
  }
}
```

Using the venv's own `python3` directly (not a wrapper script) sidesteps
the `PYTHONPATH` issue entirely, since Claude Desktop launches this
directly rather than through the `mac-terminal-mcp` shell.

## Configuration

Override the mod folder path with the `SFSPROBE_MOD_DIR` environment
variable if SFS isn't installed at the default Steam path.

## Status

Verified: compiles clean, imports resolve correctly in the venv, server
starts and initializes without error, exits gracefully on stdin EOF (no
real client attached during this test). **Not yet tested against a live
Claude Desktop connection or a running game** -- next step is registering
it and confirming tool calls actually round-trip.
