# SFS Probe — TCP IPC Rewrite: Build Spec
### Self-contained. Machine-readable. Written for an executing Claude agent.

Read this entire document before writing any code. Every checkpoint has an
explicit exit condition — do not proceed past a failed checkpoint. If a
checkpoint fails, stop and report which one and why; do not improvise past it.

Repo root: `/Users/christianjin/Documents/VSCode/SFS AI`
Remote: `https://github.com/PythonCoder1000/SFS-AI.git`
**Branch: `tcp-rewrite`, already created and pushed. Work only on this
branch.** It shares history with `worktree-optionA-build` as of this
spec's writing but is a SEPARATE worktree
(`.claude/worktrees/tcp-rewrite`) — Christian is actively working in
parallel on `worktree-optionA-build` in a different session. Do not touch
files outside what this spec covers, and do not merge/rebase onto the
other branch without being asked.

Commit after every checkpoint, not just at the end. Push after every
commit — this is the only way progress is visible from the other session.

---

## 0. Why this exists — read before touching anything

`sfsprobe` (the C# mod, `sfsprobe/SFSProbe.cs`) currently talks to Python
via a **file-polling protocol**: Python writes a command to
`command.txt`, the mod's `ProbeRunner.Update()` polls for that file every
`0.05f` seconds (`PollCommands()`, ~line 108), runs it through
`Probe.Command(line)` (~line 1160), and appends the result to
`result.txt` via `ProbeMod.Result(msg)`. Python (`agent_interface.py`'s
`_send_command()`, and the standalone `sfsprobe/probe_cmd.py`) polls
`result.txt` for new bytes at its own interval.

**Real, measured finding that motivated this (2026-09-13, tonight's
session):** the Option A pilot loop's achieved cycle rate was bottlenecked
by IPC latency more than by tsAI's own network round-trip. Direct A/B
testing found `observe()`/`act()` round-trips were a suspiciously uniform
~0.105s at Python's old `poll_s=0.1` — nearly all of it was Python's own
polling *interval*, not real game or file-system latency. Lowering
`poll_s` to `0.01` cut it to ~0.055s immediately, with zero mod changes
(that fix is already merged on `worktree-optionA-build`, not part of this
task). This rewrite is the next tier: replace polling entirely with a
real socket so neither side waits on a sleep interval, and each `act()`
call becomes a genuine event-driven push instead of a race against a
timer.

**This is explicitly a "not attempted, real future work" item already
named in `sfsprobe/mod_changelog.md`'s MCP-overhaul entry** — you are not
inventing this idea from scratch, you're picking up planned work.

**Goal:** replace the `command.txt`/`result.txt` file-polling protocol
with a persistent TCP socket, on both the C# (mod) and Python (client)
sides, while keeping the file-based protocol **fully intact and working**
as a fallback — this is an ADDITION, not a replacement of working
infrastructure, until proven solid.

---

## 1. What already exists (do not rebuild)

- **`Probe.Command(string line)`** (`SFSProbe.cs` ~line 1160) — the real
  command dispatcher. Every command (`ping`, `throttle 0.5`, `turn -0.2`,
  `telemetrysnapshot ...`, all ~47 registered commands) already funnels
  through this one function. **This is your integration point** — a TCP
  handler should parse incoming text into lines and call
  `Probe.Command(line)` for each, exactly like `PollCommands()` does
  today. Do not duplicate or reimplement command parsing/dispatch.
- **`ProbeMod.Result(string msg)`** (~line 128) — writes a timestamped
  result line to `result.txt` AND to `probe.log`. For the new TCP path,
  results need to also (or instead, see Checkpoint 2) go back over the
  socket to the specific client that sent the command.
- **`CommandRegistry`** (~line 802) — the live self-describing registry
  `light_search` already reads. No changes needed here unless you add a
  genuinely new command (you shouldn't need to).
- **Python side**: `analysis/agent_interface.py`'s `_send_command()`
  (file-based, already has the `poll_s=0.01` fix — do not touch that
  file's file-based path, only ADD a TCP path alongside it) and
  `sfsprobe/probe_cmd.py` (standalone CLI, same protocol).
- **Build process**: `sfsprobe/build.sh` — compiles `SFSProbe.cs` with
  `mcs`, copies the DLL + HarmonyX dependencies into the game's `Mods/`
  folder. **Every C# change needs this rerun**, then the game restarted
  and the mod re-enabled in the in-game Mod Loader (~10s wait on the
  main menu after enabling). This is NOT a hot-reload — say so clearly
  in your own logging/commit messages when a change requires it.

---

## 2. Design

### 2.1 Protocol shape

Plain-text, newline-delimited, over a persistent TCP connection —
deliberately as close to the existing file protocol's semantics as
possible so `Probe.Command()` needs zero changes and the wire format is
trivial to eyeball/debug with `nc`/`telnet`.

```
Client -> Mod:  "throttle 0.5\n"
Mod -> Client:  "10:31:08  RESULT_TEXT_HERE\n"
```

- One command per line in, one (or more, see below) result line(s) out,
  same content `Probe.Command()`/`ProbeMod.Result()` already produce
  today via the file path — do not change result FORMAT, only transport.
- **Multiple commands per write ARE already supported by
  `Probe.Command()`'s caller today** (`PollCommands()` splits on `\n` and
  calls `Command()` per line) — preserve this: a client writing
  `"throttle 1.0\nturn 0.0\n"` in one socket write should produce two
  result lines back, processed in the same game tick if received in the
  same read, same as the file path's batching behavior. This is the
  direct fix for the "two separate round-trips for throttle+turn every
  cycle" cost identified tonight — confirm this actually works with a
  real two-command batch test in Checkpoint 3, don't just assume it from
  reading the file-path code.

### 2.2 Where the listener lives

Add a `TcpListener` inside `ProbeRunner` (the existing `MonoBehaviour`
that already owns `PollCommands()`) or a new sibling `MonoBehaviour` —
your call, but it must run on Unity's main thread for anything touching
game state (`Probe.Command()` ultimately reads/writes live rocket state,
which is not thread-safe to touch from a raw `.NET` socket callback
thread). The standard, safe pattern: accept connections and read bytes on
a background `Thread` or via `NetworkStream.BeginRead`, but **queue
completed command lines and drain/execute them on the main thread inside
`Update()`** (or `FixedUpdate()`, matching where `PollCommands()` is
called today) — do not call `Probe.Command()` directly from a
non-Unity thread.

### 2.3 Port and lifecycle

- Pick a fixed local port (e.g. `47821` — anything unlikely to collide;
  note your actual choice in the changelog and this doc if you change
  it). Bind to `127.0.0.1` only — this is a local dev tool, not something
  that should ever accept remote connections.
- Start the listener in `ProbeMod.Load()` or `ProbeRunner`'s `Start()`,
  alongside (not instead of) the existing file-polling setup.
- Handle the game closing/mod unloading cleanly — close the socket, don't
  leave an orphaned listener holding the port across a game restart
  (confirm this by actually restarting the game once during testing, not
  just assuming `OnDestroy`/`OnApplicationQuit` covers it).
- **Multiple simultaneous clients**: not required to support this
  robustly, but don't crash if the Python client reconnects (e.g. after
  a crash) while an old socket is still technically open on the mod
  side — accept a new connection and let the old one time out /
  fail on next use, rather than the mod itself throwing.

### 2.4 Python client

New file: `analysis/sfsprobe_tcp_client.py` (or add a TCP path to
`agent_interface.py` directly behind a flag — your call, but keep the
existing file-based `_send_command()` fully intact and the DEFAULT
behavior unless a caller explicitly opts into TCP, until Checkpoint 4's
live validation passes). Needs:
- Connect once, keep the socket open across many commands (this is the
  whole point — no reconnect-per-command).
- Send a command, read until a newline-terminated response arrives,
  return it — same return shape `_send_command()` gives today (a
  stripped string) so `agent_interface.observe()`/`act()` can switch
  transports without their own signatures changing.
- A real timeout (socket-level, e.g. `settimeout()`), not a busy-poll —
  this is supposed to be the fix for polling overhead, don't reintroduce
  it on the Python side.
- Reconnect-on-failure: if the socket errors (mod restarted, game
  crashed), attempt one reconnect before raising, rather than being
  permanently dead for the rest of the process.

---

## 3. Build checkpoints — commit and push after each one

### Checkpoint 1 — TCP listener in the mod, manual smoke test
- [ ] `TcpListener` added, bound to `127.0.0.1:<port>`, started alongside
      existing file-polling (both active simultaneously).
- [ ] Incoming lines queued thread-safely, drained and passed to
      `Probe.Command()` on the main thread (`Update()`/`FixedUpdate()`).
- [ ] Results written back over the SAME socket connection that sent the
      command (not broadcast to all connections, not only to
      `result.txt`).
- **Exit:** `sfsprobe/build.sh` compiles clean, mod loads in-game (check
  `probe.log` for a clean load message), and a raw manual test — `nc
  127.0.0.1 <port>` then typing `ping` — gets a real `pong ...` response
  with live scene/version info, matching what the file-protocol `ping`
  already returns. The file-protocol path (`command.txt`/`result.txt`)
  must ALSO still work unchanged during this same session — verify both
  side by side, don't just assume the old path survived untouched.
- **Commit message:** `tcp-rewrite checkpoint 1: TCP listener + main-thread command dispatch`

### Checkpoint 2 — Python client, single-command round trip
- [ ] `analysis/sfsprobe_tcp_client.py` (or equivalent) with a persistent
      connection, `send(command) -> str` matching `_send_command()`'s
      return contract.
- [ ] Reconnect-on-failure logic, real socket timeout.
- **Exit:** a standalone script sends `ping` via the new TCP client and
  gets back a correctly-parsed response, 10 times in a row with no
  reconnects needed, while the game keeps running normally throughout
  (not restarted between calls).
- **Commit message:** `tcp-rewrite checkpoint 2: Python TCP client`

### Checkpoint 3 — Batching, latency measurement
- [ ] Confirm multi-command batching (`"throttle 0.5\nturn 0.0\n"` in one
      write) produces two correct result lines, same-tick, via the new
      TCP path — real test, not inferred from the file-path code.
- [ ] Measure real round-trip latency for `ping`/`observe`-equivalent/
      `act`-equivalent commands over TCP, same methodology as tonight's
      file-protocol measurement (10+ calls, report min/mean/max) —
      compare directly against the `poll_s=0.01` file-protocol numbers
      already in `bookkeeping/active_state.md` (~0.055s mean). This
      needs to show a REAL improvement to justify switching pilot_loop.py
      over in Checkpoint 4 — if it doesn't, stop and report that
      honestly rather than proceeding on the assumption TCP must be
      faster.
- **Exit:** documented before/after latency numbers, batching confirmed
  working.
- **Commit message:** `tcp-rewrite checkpoint 3: batching + latency validation`

### Checkpoint 4 — Wire into `agent_interface.py`, live dry run
- [ ] `agent_interface.py`'s `observe()`/`act()` can use the TCP client
      instead of `_send_command()`, behind an explicit flag/parameter —
      default stays on the file-protocol path until this checkpoint
      fully passes, so `worktree-optionA-build`'s in-progress work is
      never put at risk by a default-on switch mid-rewrite.
- **Exit:** a short live flight (or a bounded number of live
  `pilot_loop.py`-style observe/act cycles — doesn't need to be a full
  mission) run against the TCP path end to end, with real measured
  achieved-Hz logged the same way `pilot_loop.py` already does
  (`achieved rate: N cycles in Ts = X Hz`), compared against the
  2.48 Hz already measured on the file-protocol path tonight. **Requires
  a human present and watching, per this project's standing safety
  convention (`sfsprobe/mod_changelog.md`, `OPTION_A_BUILD_SPEC.md` §1)
  — do not run an unattended live flight test.**
- **Commit message:** `tcp-rewrite checkpoint 4: agent_interface.py TCP path, live-validated`

### Checkpoint 5 — Wrap-up
- [ ] Update `sfsprobe/mod_changelog.md` with the new TCP capability
      (version bump, what changed, the checkpoint 3 latency numbers).
- [ ] Clear note in this repo (README or changelog) on how to flip
      `pilot_loop.py`/`agent_interface.py` over to the TCP path once
      Christian decides to make it the default — do NOT make that
      decision yourself; leave the file-protocol path as default until
      explicitly told otherwise.
- [ ] Final commit and push.
- **Commit message:** `tcp-rewrite checkpoint 5: wrap-up, TCP path validated and documented`

---

## 4. Safety / revert plan — read this before Checkpoint 1

- **This entire rewrite lives on `tcp-rewrite`, isolated from
  `worktree-optionA-build`.** If anything goes wrong — mod won't load,
  game crashes, file-protocol path breaks — the fix is simply: don't
  merge this branch. `worktree-optionA-build` is unaffected regardless
  of what happens here.
- **Never remove or weaken the file-polling path.** Every checkpoint
  above explicitly requires the old path to keep working. This rewrite
  is additive until Christian explicitly decides to cut over.
- **The mod DLL is shared game state** — installing a broken build
  (crashes on load, hangs `Update()`, etc.) affects the live game
  Christian may also be using from the other session. Before installing
  any build via `build.sh`, check with Christian if a live flight might
  be in progress (ask him directly rather than guessing) — a bad mod
  load could interrupt work happening on the other branch.
- If a checkpoint's exit condition can't be met after real attempts,
  stop, write exactly what's blocking you to a `TCP_REWRITE_LOG.md` in
  this branch, commit, push, and end the session rather than guessing
  further or leaving the mod in a half-working state.
