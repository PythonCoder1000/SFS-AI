# TCP rewrite — session log

## Checkpoint 1 — status: COMPLETE, live-validated

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

**2026-09-13 LATER SAME DAY — live smoke test done, Christian's
go-ahead.** `sfsprobe/build.sh` run for real, DLL installed into the
live game's `Mods/SFSProbe/` folder (same 3 pre-existing `CS1718`
warnings, no new ones), game restarted, mod re-enabled. Both real
results, back to back, in the same live game session:
- File-protocol `ping` (`command.txt`/`result.txt`, via the existing
  MCP `sfsprobe_ping` tool): real `pong` with live scene/version info.
- Raw TCP `ping` (`nc 127.0.0.1 47821`, command `"ping\n"`): identical
  real `pong` response, same content/format as the file path.
- File-protocol `ping` again immediately after: still clean, no
  interference or state corruption between the two paths.

Checkpoint 1's exit condition (SFSProbe_SPEC.md §3, Checkpoint 1) is
fully met: both paths alive simultaneously, mod loaded cleanly, no
regressions to the existing file-protocol path.

Next: checkpoints 2-5 as written in `TCP_REWRITE_SPEC.md` -- Python
client round-trip validation (2), batching + latency measurement (3),
agent_interface.py wiring + live pilot_loop dry run (4), wrap-up (5).

Local-only note: `sfsprobe/lib/harmonyx_2.16.0/` was copied into this
worktree from the main checkout to make local `mcs` compilation possible
(it's git-ignored/untracked in both places, not a repo change).

## Checkpoint 2 — status: COMPLETE

Ran `analysis/sfsprobe_tcp_client.py` for real against the live mod
(same game session as Checkpoint 1's smoke test, port 47821 already
confirmed open before running). 10/10 `ping` round trips succeeded, no
reconnects triggered (each call hit the `try` branch, not the
except/reconnect fallback), game and mod stayed up throughout and
after (`nc -z 127.0.0.1 47821` still open post-test).

Real numbers: **min=7.7ms mean=12.6ms max=13.6ms** for 10x `ping` over
the persistent TCP connection — all 10 calls returned the same live
`pong  scene=World_PC  rockets=1  fixedDelta=0.0166666675
gameVersion=1.6.00.16  modVersion=0.69.0`, matching the file-protocol
`ping` content/format from Checkpoint 1.

For reference, this is already far below the ~0.055s (55ms)
file-protocol mean noted in the spec for `poll_s=0.01` — expected, since
this is a single persistent socket paying zero reconnect or poll-interval
cost per call. Real head-to-head latency methodology (batching +
`act`-equivalent commands, not just `ping`) is Checkpoint 3's job, not
claimed as final here.

Exit condition met (SFSProbe_SPEC.md/TCP_REWRITE_SPEC.md §3, Checkpoint
2). Next: Checkpoint 3 (batching + latency).
