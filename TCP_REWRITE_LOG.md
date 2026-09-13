# TCP rewrite — session log

## Checkpoint 1 — status: implemented + compiles clean, live smoke test BLOCKED

What's done:
- `sfsprobe/SFSProbe.cs`: `TcpListener` added to `ProbeRunner`, bound to
  `127.0.0.1:47821` (`ProbeMod.TcpPort`), started in `Start()` alongside
  the existing file-polling (`PollCommands()` untouched, still runs every
  frame via the same `poll > 0.05f` gate).
  - Accept loop + one reader thread per connected client, both background
    threads; each completed line is enqueued into a `ConcurrentQueue`.
  - `ProbeRunner.Update()` now calls `DrainTcpCommands()` first, which
    dequeues everything currently queued and calls `Probe.Command(line)`
    per line, on the main thread, exactly like `PollCommands()` does for
    the file path — `Probe.Command()` itself is unmodified.
  - `ProbeMod.Result(msg)` additionally writes the same result line to
    whichever TCP connection's command is currently being processed
    (`ProbeMod.ActiveTcpConn`, set/cleared around each `Probe.Command()`
    call in `DrainTcpCommands()`), so results route back to the client
    that sent the command — no changes needed to any of the ~47 command
    handlers, all of which already just call `ProbeMod.Result(...)`.
  - `OnDestroy()`/`OnApplicationQuit()` both call `StopTcp()`, which stops
    the listener and closes all live client sockets.
  - A dead/reconnecting client doesn't crash the mod: `AcceptTcpClient()`
    just accepts the next connection; a broken pipe on write only flips
    that one `TcpProbeConn.Alive` flag.
- `analysis/sfsprobe_tcp_client.py`: new standalone module,
  `SfsProbeTcpClient` — persistent connection, `send()`/`send_batch()`,
  socket-level `settimeout()` (no busy-poll), one reconnect attempt on
  socket failure before raising. Not wired into `agent_interface.py` yet
  (that's checkpoint 4, explicitly deferred).
- Compile-checked locally: `mcs` against the same references
  `sfsprobe/build.sh` uses, output to a scratch DLL (not installed)  —
  compiles clean, only 3 pre-existing unrelated warnings (`CS1718` at
  lines ~3177-3180, present before this change, not touched here).

What's BLOCKED and why:
- Checkpoint 1's actual exit condition needs `sfsprobe/build.sh` run for
  real (which installs `SFSProbe.dll` into the live game's `Mods/`
  folder) and the game restarted/mod re-enabled, then a manual `nc
  127.0.0.1 47821` / `ping` smoke test, run side-by-side with the
  existing file-protocol path to confirm both still work.
- Per this spec's own safety section (§4) and the standing project
  convention, I asked Christian before installing a build or touching
  the live game, since it's shared state and `worktree-optionA-build` may
  have a live flight in progress in the other session. He said **not
  right now**.
- Stopping here rather than proceeding past this — not treating "not
  right now" as a green light to install anyway, and not simulating or
  assuming the live test would pass.

Next step (when Christian gives the go-ahead): run `sfsprobe/build.sh`,
restart the game, enable the mod, run the `nc`/`ping` smoke test and the
side-by-side file-protocol check, then continue to checkpoints 2-5 as
written in `TCP_REWRITE_SPEC.md`.

Local-only note: `sfsprobe/lib/harmonyx_2.16.0/` was copied into this
worktree from the main checkout to make local `mcs` compilation possible
(it's git-ignored/untracked in both places, not a repo change).
