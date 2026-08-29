"""
sfsprobe_mcp -- MCP server wrapping sfsprobe's file-based command protocol.

sfsprobe (the SFS AI project's C# probe mod) communicates over a polled
file pair: a command is written to command.txt, the mod polls every 0.5s,
deletes the file after reading, executes, and appends a result line to
result.txt. Talking to it by hand meant: write command.txt, sleep a fixed
guess (too long or too short), read result.txt, hope nothing raced.

This server replaces that with real adaptive polling -- every tool
returns the instant a response actually appears, reports how long that
took, and fails with a clear, actionable message on timeout instead of
hanging or returning nothing.

It's an extension, not just a wrapper: beyond a generic pass-through
command tool, it includes purpose-built convenience tools (ping, dragarea,
telemetry start/stop) that parse structured results out of the mod's
JSON/text output, plus two read-only diagnostic tools (status, log/
telemetry tailing) that didn't exist before at all -- built specifically
to answer "is the game even running?" and "let me see recent samples
without sending a command" without guessing.

Transport: stdio (local, single-user, subprocess of the MCP client --
see mcp_best_practices.md). Never logs to stdout; all diagnostics go to
stderr via the `log` module or print(..., file=sys.stderr).
"""

import json
import os
import sys
import time
import asyncio
import csv
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

# python/ (this project's analysis code) lives alongside sfsprobe_mcp/,
# not inside it -- add it to sys.path so these tools call directly into
# sfs_telemetry.py (no subprocess). Keeps mac-terminal-mcp reserved for
# things that actually need a real shell (compiling the mod), per
# Christian's explicit ask.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "python"))
import sfs_telemetry as st  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Overridable via env var so this isn't hardcoded to one machine's Steam
# install path -- e.g. if the project ever moves off Steam or onto a
# different OS layout.
DEFAULT_MOD_DIR = (
    "~/Library/Application Support/Steam/steamapps/common/"
    "Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe"
)
MOD_DIR = Path(os.environ.get("SFSPROBE_MOD_DIR", DEFAULT_MOD_DIR)).expanduser()
CMD_FILE = MOD_DIR / "command.txt"
RESULT_FILE = MOD_DIR / "result.txt"
PROBE_LOG_FILE = MOD_DIR / "probe.log"
TRUTH_FILE = MOD_DIR / "truth.jsonl"
INPUTS_FILE = MOD_DIR / "inputs.jsonl"
DRAGAREA_JSON_FILE = MOD_DIR / "sfs_probe_dragarea.json"
SNAPSHOT_JSON_FILE = MOD_DIR / "sfs_probe_flight.json"
ARCHIVE_DIR = MOD_DIR / "archive"
FLIGHTS_LOG_FILE = _PROJECT_ROOT / "flights_log.jsonl"
BLUEPRINTS_RESEARCH_DIR = _PROJECT_ROOT / "blueprints" / "research"
BLUEPRINTS_LIVE_DIR = _PROJECT_ROOT / "blueprints" / "live"

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_POLL_INTERVAL_S = 0.15
# The mod's own PollCommands() only checks command.txt every 0.5s (see
# ProbeRunner.Update() in SFSProbe.cs) -- staler than this and a "recent
# activity" heuristic in sfsprobe_status stops trusting probe.log as a
# sign the game is currently alive vs. just left over from a past session.
STALE_LOG_THRESHOLD_S = 30.0

mcp = FastMCP("sfsprobe_mcp")


# ---------------------------------------------------------------------------
# Shared helpers -- every tool below is built on these two, nothing is
# duplicated between them.
# ---------------------------------------------------------------------------

class ProbeTimeoutError(Exception):
    """Raised when a command was sent but no new result.txt line appeared
    in time. Distinct from a missing mod folder / missing game install."""


# ---------------------------------------------------------------------------
# Error-code infrastructure. Every tool's error responses use one of these
# codes so a caller (or a future agent) can branch on WHAT went wrong
# without string-matching the human-readable message. Two tiers:
#   - HARD ERROR: response has 'error_code'/'error', no useful data.
#   - WARNING: response has real data PLUS a 'warnings' list (e.g. scope
#     fell back to the full flight) -- the call still succeeded, but the
#     caller should know the result isn't exactly what was asked for.
# ---------------------------------------------------------------------------

_EXCEPTION_ERROR_CODES = {
    "ProbeTimeoutError": "TIMEOUT",
    "FileNotFoundError": "FILE_NOT_FOUND",
    "ValueError": "INVALID_PARAM",
    "JSONDecodeError": "PARSE_ERROR",
    "OSError": "FILE_ERROR",
}


def _error_response(code: str, message: str, **extra) -> str:
    payload = {"error_code": code, "error": message}
    payload.update(extra)
    return json.dumps(payload, indent=2)


def _error_for_exception(e: Exception, **extra) -> str:
    code = _EXCEPTION_ERROR_CODES.get(type(e).__name__, "UNKNOWN_ERROR")
    return _error_response(code, str(e), **extra)


def _log(msg: str) -> None:
    print(f"[sfsprobe_mcp] {msg}", file=sys.stderr)


def _require_mod_dir() -> None:
    if not MOD_DIR.is_dir():
        raise FileNotFoundError(
            f"sfsprobe mod folder not found at: {MOD_DIR}\n"
            "Is Spaceflight Simulator installed at the expected Steam path? "
            "Override with the SFSPROBE_MOD_DIR environment variable if your "
            "install lives somewhere else."
        )


def send_command(command: str, timeout_s: float, poll_interval_s: float) -> tuple[str, float]:
    """Core adaptive-polling primitive. Writes `command` to command.txt,
    polls result.txt's byte size (not line count -- correct even if
    several result lines land in one poll window) until new content
    appears or timeout_s elapses.

    Returns (response_text, elapsed_seconds). Raises ProbeTimeoutError on
    timeout, FileNotFoundError if the mod folder itself is missing.
    """
    _require_mod_dir()

    if not RESULT_FILE.exists():
        RESULT_FILE.touch()
    start_size = RESULT_FILE.stat().st_size
    start_time = time.monotonic()

    # A leftover command.txt only exists if a previous write was never
    # picked up (mod not running) -- clear it so this call's command is
    # the one actually read next, not queued behind a stale one.
    try:
        CMD_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    CMD_FILE.write_text(command + "\n")

    deadline = start_time + timeout_s
    while time.monotonic() < deadline:
        cur_size = RESULT_FILE.stat().st_size
        if cur_size > start_size:
            with RESULT_FILE.open("r") as f:
                f.seek(start_size)
                new_text = f.read()
            elapsed = time.monotonic() - start_time
            return new_text.strip(), elapsed
        time.sleep(poll_interval_s)

    elapsed = time.monotonic() - start_time
    raise ProbeTimeoutError(
        f"No response to '{command}' after {elapsed:.2f}s (timeout={timeout_s}s). "
        "Most likely causes: the game isn't running, the SFS Probe mod isn't "
        "enabled in the Mod Loader, or (for rocket-scoped commands like "
        "'dragarea') there's no active rocket in the current scene. Use "
        "sfsprobe_status to check which of these it is."
    )


# Commands confirmed (by reading SFSProbe.cs's Command() switch directly)
# to NOT write a line to result.txt on success -- DumpWorld()/DumpMenu()
# only call Write()/Log() (probe.log), never ProbeMod.Result(). This is a
# real protocol asymmetry, not a guess: every other command handler calls
# Result() exactly once. Matched against the first whitespace-split,
# lowercased token, same as the mod's own `a[0].ToLowerInvariant()`
# parsing. If a future mod version changes this, this set needs updating.
SILENT_COMMANDS = {"world", "menu"}


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r") as f:
        return sum(1 for _ in f)


def send_command_batch(
    commands: List[str], timeout_s: float, poll_interval_s: float
) -> tuple[list[Optional[str]], float, bool]:
    """Batching primitive. Writes ALL commands to command.txt as separate
    lines in ONE write -- the mod's own PollCommands() already splits on
    '\\n' and executes every line in the same Update() tick (see
    SFSProbe.cs), so this is not simulated batching (looping N separate
    calls), it's using the protocol's own real batching support directly.
    Every command handler is synchronous reflection/file work with no
    blocking, so a large batch still completes in one game tick.

    Waits for line-count growth rather than byte-size growth (unlike
    send_command) because with multiple commands in flight, only a line
    count lets this tell "got 3 of 5" from "got 5 of 5".

    Returns (results, elapsed_seconds, complete):
      - results: one entry per input command, in order. A command
        confirmed SILENT (see SILENT_COMMANDS) gets None immediately, no
        wait spent on it. Others get the matching result.txt line if it
        arrived before timeout, else None.
      - complete: True if every non-silent command got a matching line.
        False means a partial batch -- check `results` for which ones
        are still None; a timeout does not discard what did arrive.
    """
    _require_mod_dir()

    if not RESULT_FILE.exists():
        RESULT_FILE.touch()
    start_lines = _line_count(RESULT_FILE)
    start_time = time.monotonic()

    try:
        CMD_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    CMD_FILE.write_text("\n".join(commands) + "\n")

    non_silent_indices = [
        i for i, c in enumerate(commands)
        if c.strip().split(" ", 1)[0].lower() not in SILENT_COMMANDS
    ]
    need = len(non_silent_indices)

    new_lines: list[str] = []
    deadline = start_time + timeout_s
    while time.monotonic() < deadline:
        cur_lines = _line_count(RESULT_FILE)
        got = cur_lines - start_lines
        if got > 0:
            with RESULT_FILE.open("r") as f:
                all_lines = f.readlines()
            new_lines = [l.rstrip("\n") for l in all_lines[start_lines:]]
        if got >= need:
            break
        time.sleep(poll_interval_s)

    elapsed = time.monotonic() - start_time

    results: list[Optional[str]] = [None] * len(commands)
    line_iter = iter(new_lines)
    for i in range(len(commands)):
        if i in non_silent_indices:
            results[i] = next(line_iter, None)
    complete = all(results[i] is not None for i in non_silent_indices)

    return results, elapsed, complete


def _tail_file(path: Path, n: int) -> List[str]:
    if not path.exists():
        return []
    # Fine for these files -- telemetry archives on stop, so the live
    # file is at most one flight's worth, never unbounded.
    lines = path.read_text().splitlines()
    return lines[-n:] if n > 0 else lines


class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    JSON = "json"
    MARKDOWN = "markdown"


# ---------------------------------------------------------------------------
# Tool: generic command passthrough
# ---------------------------------------------------------------------------

class SendCommandInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    command: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "Raw sfsprobe command line, exactly as it would be written to "
            "command.txt. Examples: 'ping', 'dragarea', 'snapshot', "
            "'telemetry on', 'telemetry on h,vv,computed:dragArea', "
            "'throttle 0.8', 'master on', 'ignite', 'achievements'."
        ),
    )
    timeout_s: float = Field(
        default=DEFAULT_TIMEOUT_S, ge=0.5, le=60.0,
        description="Max seconds to wait for a response before giving up.",
    )
    poll_interval_s: float = Field(
        default=DEFAULT_POLL_INTERVAL_S, ge=0.02, le=2.0,
        description="Seconds between result.txt checks. Lower = snappier, more disk stat calls.",
    )


@mcp.tool(
    name="sfsprobe_send_command",
    annotations={
        "title": "Send a raw sfsprobe command",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sfsprobe_send_command(params: SendCommandInput) -> str:
    """Send any raw sfsprobe command and adaptively wait for its response.

    This is the general-purpose escape hatch -- every other tool in this
    server is a thin, structured wrapper around this same call. Use this
    directly for commands that don't have a dedicated tool yet (e.g.
    'throttle', 'master', 'ignite', 'revert', 'achievements', 'geometry',
    'snapshot', 'diag', 'autostop', 'cheat').

    Args:
        params (SendCommandInput): command, timeout_s, poll_interval_s

    Returns:
        str: JSON with keys: command, response (the new result.txt text),
        elapsed_seconds (float, how long the wait actually took), timed_out
        (always false on success -- a timeout raises instead of returning).
    """
    try:
        response, elapsed = await asyncio.to_thread(
            send_command, params.command, params.timeout_s, params.poll_interval_s
        )
        return json.dumps({
            "command": params.command,
            "response": response,
            "elapsed_seconds": round(elapsed, 3),
            "timed_out": False,
        }, indent=2)
    except ProbeTimeoutError as e:
        return json.dumps({
            "command": params.command,
            "error_code": "TIMEOUT",
            "error": str(e),
            "elapsed_seconds": round(params.timeout_s, 3),
            "timed_out": True,
        }, indent=2)
    except FileNotFoundError as e:
        return json.dumps({"command": params.command, "error_code": "FILE_NOT_FOUND", "error": str(e), "timed_out": False}, indent=2)


# ---------------------------------------------------------------------------
# Tool: batch -- send up to 100 commands in ONE call, executed together in
# a single game tick. This is what Christian specifically asked for:
# a real launch sequence (throttle/ignite/telemetry/master, or any large
# multi-step operation) without one tool call per command.
# ---------------------------------------------------------------------------

class SendBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commands: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "Raw sfsprobe command lines, executed together in one game "
            "tick -- e.g. a launch sequence: ['throttle 1', 'ignite', "
            "'telemetry on', 'master on']. Order matters: put 'master on' "
            "LAST if you want telemetry already recording before liftoff "
            "actually fires, since that's the real 'go' trigger. Each "
            "entry must not itself contain a newline."
        ),
    )
    timeout_s: float = Field(
        default=10.0, ge=0.5, le=120.0,
        description="Max seconds to wait for ALL commands to confirm. Scale up for large batches.",
    )
    poll_interval_s: float = Field(
        default=DEFAULT_POLL_INTERVAL_S, ge=0.02, le=2.0,
        description="Seconds between result.txt checks.",
    )

    @field_validator("commands")
    @classmethod
    def _no_embedded_newlines(cls, v: List[str]) -> List[str]:
        for c in v:
            if "\n" in c:
                raise ValueError(f"command must not contain a newline (send as separate list entries instead): {c!r}")
        return v


@mcp.tool(
    name="sfsprobe_send_batch",
    annotations={
        "title": "Send multiple sfsprobe commands in one game tick",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sfsprobe_send_batch(params: SendBatchInput) -> str:
    """Send up to 100 commands in a single call, executed together in one
    game Update() tick -- for startup sequences or any multi-step
    operation that would otherwise need one tool call per command.

    This uses the mod's own multi-line command.txt support directly (see
    PollCommands() in SFSProbe.cs splitting on newlines) rather than
    looping N separate sfsprobe_send_command calls -- one file write, one
    wait, real batching rather than simulated batching. Every command
    handler is synchronous with no blocking, so even a 100-command batch
    still executes in one game tick.

    Known protocol gotcha, handled automatically: 'world' and 'menu' are
    the only two commands that write NO result.txt line on success (they
    only write to probe.log) -- they're excluded from the completion
    wait so they can't cause a false timeout, and their result is always
    null (marked silent=true) rather than looking like a missing/failed
    value.

    Args:
        params (SendBatchInput): commands, timeout_s, poll_interval_s

    Returns:
        str: JSON with keys: results (array, one entry per command, in
        order: command, result [string or null], silent [bool, true for
        world/menu]), complete (bool -- true if every non-silent command
        got a confirmed result before timeout; false means check results
        for which ones are still null, partial results are NOT discarded
        on timeout), elapsed_seconds.
    """
    try:
        results, elapsed, complete = await asyncio.to_thread(
            send_command_batch, params.commands, params.timeout_s, params.poll_interval_s
        )
    except FileNotFoundError as e:
        return _error_for_exception(e)

    entries = []
    for cmd, result in zip(params.commands, results):
        is_silent = cmd.strip().split(" ", 1)[0].lower() in SILENT_COMMANDS
        entries.append({"command": cmd, "result": result, "silent": is_silent})

    return json.dumps({
        "results": entries,
        "complete": complete,
        "elapsed_seconds": round(elapsed, 3),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: ping (structured convenience wrapper)
# ---------------------------------------------------------------------------

class PingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, ge=0.5, le=60.0,
                              description="Max seconds to wait for a response.")


@mcp.tool(
    name="sfsprobe_ping",
    annotations={
        "title": "Ping sfsprobe",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_ping(params: PingInput) -> str:
    """Check whether the mod is alive and get the current scene/rocket count.

    Parses the mod's 'pong  scene=X  rockets=N  fixedDelta=Y  gameVersion=Z
    modVersion=W' response into structured fields rather than leaving the
    caller to parse text.

    Args:
        params (PingInput): timeout_s

    Returns:
        str: JSON with keys: scene (str), rockets (int, -1 if unavailable),
        fixed_delta (float), game_version (str, the SFS build, e.g.
        '1.6.00.16'), mod_version (str, sfsprobe's own version, e.g.
        '0.31.0'), elapsed_seconds (float), raw (the unparsed response
        text, in case parsing missed something).
    """
    try:
        response, elapsed = await asyncio.to_thread(
            send_command, "ping", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except ProbeTimeoutError as e:
        return _error_for_exception(e, elapsed_seconds=round(params.timeout_s, 3))
    except FileNotFoundError as e:
        return _error_for_exception(e)

    scene = rockets = fixed_delta = game_version = mod_version = None
    for token in response.split():
        if token.startswith("scene="):
            scene = token.split("=", 1)[1]
        elif token.startswith("rockets="):
            try:
                rockets = int(token.split("=", 1)[1])
            except ValueError:
                pass
        elif token.startswith("fixedDelta="):
            try:
                fixed_delta = float(token.split("=", 1)[1])
            except ValueError:
                pass
        elif token.startswith("gameVersion="):
            game_version = token.split("=", 1)[1]
        elif token.startswith("modVersion="):
            mod_version = token.split("=", 1)[1]

    return json.dumps({
        "scene": scene,
        "rockets": rockets,
        "fixed_delta": fixed_delta,
        "game_version": game_version,
        "mod_version": mod_version,
        "elapsed_seconds": round(elapsed, 3),
        "raw": response,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: dragarea (structured convenience wrapper)
# ---------------------------------------------------------------------------

class GetDragAreaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, ge=0.5, le=60.0,
                              description="Max seconds to wait for the command to complete.")


@mcp.tool(
    name="sfsprobe_get_dragarea",
    annotations={
        "title": "Get live dragArea / center-of-pressure",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_get_dragarea(params: GetDragAreaInput) -> str:
    """Run the 'dragarea' command and return the parsed result directly.

    Reads sfs_probe_dragarea.json after the command completes rather than
    leaving the caller to make a second file-read call. Requires an active
    rocket in the current scene (check with sfsprobe_ping first if unsure).

    Args:
        params (GetDragAreaInput): timeout_s

    Returns:
        str: JSON with keys: drag_area (float or null), center_of_drag
        ({x, y} or null), all_surface_count (int), exposed_surface_count
        (int), elapsed_seconds (float), error (str, only present on
        failure -- e.g. no active rocket).
    """
    try:
        response, elapsed = await asyncio.to_thread(
            send_command, "dragarea", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except ProbeTimeoutError as e:
        return _error_for_exception(e, elapsed_seconds=round(params.timeout_s, 3))
    except FileNotFoundError as e:
        return _error_for_exception(e)

    if "no active rocket" in response or "rocket.aero is null" in response:
        return json.dumps({
            "error_code": "NO_ACTIVE_ROCKET",
            "error": response,
            "elapsed_seconds": round(elapsed, 3),
        }, indent=2)

    try:
        data = json.loads(DRAGAREA_JSON_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return json.dumps({
            "error_code": "PARSE_ERROR",
            "error": f"command responded ({response!r}) but sfs_probe_dragarea.json "
                     f"couldn't be read/parsed: {e}",
            "elapsed_seconds": round(elapsed, 3),
        }, indent=2)

    calc = data.get("calculateDragForce")
    return json.dumps({
        "drag_area": calc.get("item1") if calc else None,
        "center_of_drag": {"x": calc["item2"][0], "y": calc["item2"][1]} if calc and "item2" in calc else None,
        "all_surface_count": data.get("allSurfaceCount"),
        "exposed_surface_count": data.get("exposedSurfaceCount"),
        "elapsed_seconds": round(elapsed, 3),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: telemetry start / stop
# ---------------------------------------------------------------------------

class TelemetryStartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: Optional[List[str]] = Field(
        default=None,
        max_length=50,
        description=(
            "Scoped-telemetry field list (v0.29+). Omit for full default "
            "recording (all built-in fields). Each entry is either a dotted "
            "reflection path (e.g. 'rb2d.mass', 'location.velocity.x') or "
            "'computed:NAME' for a registered computed field (currently just "
            "'computed:dragArea', expanding to dragArea/dragCopX/dragCopY/"
            "dragSurfaces/dragExposed). Example: ['h', 'vv', 'computed:dragArea']."
        ),
    )
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, ge=0.5, le=60.0,
                              description="Max seconds to wait for the start acknowledgement.")


@mcp.tool(
    name="sfsprobe_telemetry_start",
    annotations={
        "title": "Start telemetry recording",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sfsprobe_telemetry_start(params: TelemetryStartInput) -> str:
    """Start telemetry recording, in full or scoped mode.

    Equivalent to the 'telemetry on' / 'telemetry on <fieldspec>' commands.
    A no-op (returns quickly, mode unchanged) if recording is already active
    -- see StartRecording() in SFSProbe.cs.

    Args:
        params (TelemetryStartInput): fields, timeout_s

    Returns:
        str: JSON with keys: mode ('full' or 'scoped'), fields (the list
        sent, or null), response (raw ack text), elapsed_seconds.
    """
    command = "telemetry on"
    if params.fields:
        command += " " + ",".join(params.fields)

    try:
        response, elapsed = await asyncio.to_thread(
            send_command, command, params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except ProbeTimeoutError as e:
        return _error_for_exception(e, elapsed_seconds=round(params.timeout_s, 3))
    except FileNotFoundError as e:
        return _error_for_exception(e)

    return json.dumps({
        "mode": "scoped" if params.fields else "full",
        "fields": params.fields,
        "response": response,
        "elapsed_seconds": round(elapsed, 3),
    }, indent=2)


class TelemetryStopInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, ge=0.5, le=60.0,
                              description="Max seconds to wait for the stop acknowledgement.")


@mcp.tool(
    name="sfsprobe_telemetry_stop",
    annotations={
        "title": "Stop telemetry recording",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_telemetry_stop(params: TelemetryStopInput) -> str:
    """Stop telemetry recording and archive the flight's log files.

    Equivalent to the 'telemetry off' command / Backslash hotkey. Resets
    scoped-mode field selection back to full mode for the next recording.
    A no-op if nothing is currently recording.

    Args:
        params (TelemetryStopInput): timeout_s

    Returns:
        str: JSON with keys: response (raw ack text, includes sample count
        and archive file paths), elapsed_seconds.
    """
    try:
        response, elapsed = await asyncio.to_thread(
            send_command, "telemetry off", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except ProbeTimeoutError as e:
        return _error_for_exception(e, elapsed_seconds=round(params.timeout_s, 3))
    except FileNotFoundError as e:
        return _error_for_exception(e)

    return json.dumps({"response": response, "elapsed_seconds": round(elapsed, 3)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: status -- new capability, didn't exist before at all. Answers
# "is the game even running / is the mod loaded" without guessing from a
# timeout, which was ambiguous before this server existed.
# ---------------------------------------------------------------------------

class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ping_timeout_s: float = Field(
        default=2.0, ge=0.2, le=30.0,
        description="Short timeout for the live-ping check this tool performs.",
    )


@mcp.tool(
    name="sfsprobe_status",
    annotations={
        "title": "Check whether SFS + the probe mod are actually alive",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_status(params: StatusInput) -> str:
    """Diagnose whether the game/mod are reachable, without sending a
    command whose timeout could mean several different things.

    Checks, in order: does the mod folder exist; how stale is probe.log
    (a mod that's still running writes to it constantly); then attempts a
    real short-timeout ping to confirm liveness directly rather than only
    inferring it.

    Args:
        params (StatusInput): ping_timeout_s

    Returns:
        str: JSON with keys: mod_dir_exists (bool), mod_dir (str),
        probe_log_age_seconds (float or null), probe_log_likely_stale
        (bool), ping_succeeded (bool), scene/rockets (from the ping, if it
        succeeded), mod_version (str, sfsprobe's own version, e.g.
        '0.31.0' -- null if ping didn't succeed), elapsed_seconds, verdict
        (one-line human-readable summary of the most likely explanation).
    """
    start = time.monotonic()
    mod_dir_exists = MOD_DIR.is_dir()

    log_age = None
    log_stale = True
    if mod_dir_exists and PROBE_LOG_FILE.exists():
        log_age = time.time() - PROBE_LOG_FILE.stat().st_mtime
        log_stale = log_age > STALE_LOG_THRESHOLD_S

    ping_ok = False
    scene = rockets = mod_version = None
    if mod_dir_exists:
        try:
            response, _ = await asyncio.to_thread(
                send_command, "ping", params.ping_timeout_s, DEFAULT_POLL_INTERVAL_S
            )
            ping_ok = True
            for token in response.split():
                if token.startswith("scene="):
                    scene = token.split("=", 1)[1]
                elif token.startswith("rockets="):
                    try:
                        rockets = int(token.split("=", 1)[1])
                    except ValueError:
                        pass
                elif token.startswith("modVersion="):
                    mod_version = token.split("=", 1)[1]
        except (ProbeTimeoutError, FileNotFoundError):
            ping_ok = False

    if not mod_dir_exists:
        verdict = "Mod folder doesn't exist -- SFS may not be installed at the expected path, or SFSPROBE_MOD_DIR is wrong."
    elif ping_ok:
        verdict = f"Alive and responding. scene={scene}, rockets={rockets}, mod_version={mod_version}."
    elif not log_stale:
        verdict = "probe.log was written recently but ping didn't respond -- game may be mid-load, or a real bug. Try again shortly."
    else:
        verdict = "No response and probe.log is stale/missing -- the game likely isn't running, or the SFS Probe mod isn't enabled in the Mod Loader."

    return json.dumps({
        "mod_dir_exists": mod_dir_exists,
        "mod_dir": str(MOD_DIR),
        "probe_log_age_seconds": round(log_age, 1) if log_age is not None else None,
        "probe_log_likely_stale": log_stale,
        "ping_succeeded": ping_ok,
        "scene": scene,
        "rockets": rockets,
        "mod_version": mod_version,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "verdict": verdict,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: tail probe.log / truth.jsonl / inputs.jsonl -- read-only, sends NO
# command at all. New capability: inspect recent activity or telemetry
# samples without triggering anything in the game.
# ---------------------------------------------------------------------------

class TailFileTarget(str, Enum):
    PROBE_LOG = "probe_log"
    TRUTH = "truth"
    INPUTS = "inputs"


class TailFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: TailFileTarget = Field(
        ...,
        description="Which live file to tail: 'probe_log' (probe.log, human-"
                     "readable events), 'truth' (truth.jsonl, per-tick physics "
                     "telemetry), or 'inputs' (inputs.jsonl, per-tick control "
                     "signals -- only written in full telemetry mode).",
    )
    lines: int = Field(default=20, ge=1, le=1000, description="Number of most recent lines to return.")
    parse_json: bool = Field(
        default=False,
        description="For 'truth'/'inputs': parse each line as JSON and return "
                     "a structured array instead of raw text lines.",
    )


@mcp.tool(
    name="sfsprobe_tail_file",
    annotations={
        "title": "Tail a live sfsprobe output file",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_tail_file(params: TailFileInput) -> str:
    """Read the last N lines of a live sfsprobe output file, with no
    game interaction at all -- doesn't send a command or wait for anything.

    Useful for checking recent activity (probe_log) or inspecting the most
    recent telemetry samples (truth/inputs) without disturbing a running
    flight or recording.

    Args:
        params (TailFileInput): target, lines, parse_json

    Returns:
        str: JSON with keys: target, path, line_count (lines actually
        found, may be less than requested), lines (array of strings, or
        array of parsed objects if parse_json and target is truth/inputs),
        parse_errors (int, only present if parse_json hit malformed lines).
    """
    path = {
        TailFileTarget.PROBE_LOG: PROBE_LOG_FILE,
        TailFileTarget.TRUTH: TRUTH_FILE,
        TailFileTarget.INPUTS: INPUTS_FILE,
    }[params.target]

    raw_lines = _tail_file(path, params.lines)

    if not params.parse_json or params.target == TailFileTarget.PROBE_LOG:
        return json.dumps({
            "target": params.target.value,
            "path": str(path),
            "line_count": len(raw_lines),
            "lines": raw_lines,
        }, indent=2)

    parsed, errors = [], 0
    for line in raw_lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            errors += 1

    result = {
        "target": params.target.value,
        "path": str(path),
        "line_count": len(parsed),
        "lines": parsed,
    }
    if errors:
        result["parse_errors"] = errors
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Shared helper: resolve a telemetry file path -- either an explicit
# archived flight, or the live truth.jsonl if none given. Used by every
# analysis tool below (Stages 1-7).
# ---------------------------------------------------------------------------

def _resolve_flight_path(path: Optional[str]) -> Path:
    if path:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"telemetry file not found: {p}")
        return p
    if not TRUTH_FILE.exists():
        raise FileNotFoundError(
            f"no path given and no live truth.jsonl found at {TRUTH_FILE} -- "
            "either pass an archived flight's path, or start telemetry recording first."
        )
    return TRUTH_FILE


# ===========================================================================
# STAGE 1 -- core stats & search
# ===========================================================================

class FieldStatsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: List[str] = Field(..., min_length=1, description="Telemetry field names, e.g. ['h','vv','dragArea'].")
    path: Optional[str] = Field(default=None, description="Archived flight file. Omit to use the live truth.jsonl.")
    scope: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Restrict to a portion of the flight. Forms: {'phase':'ascent'}, "
                     "{'time_range':[t1,t2]}, {'before_event':'impact','window_s':10}, "
                     "{'after_event':'engine_cutoff'}, {'around_event':'apoapsis','window_s':5}. "
                     "Omit for the whole flight.",
    )


@mcp.tool(name="sfsprobe_field_stats", annotations={"title": "Min/max/mean/median/stddev for telemetry fields",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_field_stats(params: FieldStatsInput) -> str:
    """Compute min/max/mean/median/stddev for one or more telemetry fields
    across a flight (or a scoped portion of it). The generalized version
    of the ad-hoc stats this project used to compute by hand per script.

    Args:
        params (FieldStatsInput): fields, path, scope

    Returns:
        str: JSON with keys: path, sample_count, scope_applied, stats
        (one entry per field: count/min/max/mean/median/stddev, or a
        'note' if the field had no numeric values in range).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        start, end, warning = st.resolve_scope(samples, params.scope)
        stats = st.field_stats(samples, params.fields, start, end + 1)
        result = {"path": str(path), "sample_count": len(samples),
                  "scope_applied": params.scope, "scoped_range": [start, end],
                  "stats": stats}
        if warning:
            result["warnings"] = [warning]
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class FieldSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(...)
    op: str = Field(..., description="One of: <, <=, >, >=, ==, !=")
    value: float = Field(...)
    path: Optional[str] = Field(default=None)
    limit: Optional[int] = Field(default=50, ge=1, le=5000)


@mcp.tool(name="sfsprobe_field_search", annotations={"title": "Find samples matching a field condition",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_field_search(params: FieldSearchInput) -> str:
    """Find all samples where field <op> value holds, e.g. h > 10000 or
    vv < 0. Returns matching indices/times/values instead of requiring a
    manual scroll through raw telemetry.

    Args:
        params (FieldSearchInput): field, op, value, path, limit

    Returns:
        str: JSON with keys: path, match_count, matches (capped at limit).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        matches = st.search_field(samples, params.field, params.op, params.value, limit=params.limit)
        return json.dumps({"path": str(path), "match_count": len(matches), "matches": matches}, indent=2)
    except (FileNotFoundError, ValueError) as e:
        return _error_for_exception(e)


class DownsampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = Field(..., ge=1, le=2000, description="Number of evenly-spaced samples to return.")
    path: Optional[str] = Field(default=None)
    scope: Optional[Dict[str, Any]] = Field(default=None)
    fields: Optional[List[str]] = Field(default=None, description="Only include these fields per sample (omit for all fields).")


@mcp.tool(name="sfsprobe_downsample", annotations={"title": "Reduce a flight to N evenly-spaced samples",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_downsample(params: DownsampleInput) -> str:
    """Reduce a (possibly thousands-of-samples) flight to N evenly-spaced
    samples -- for quick eyeballing, or feeding a small dataset into a
    chart, without hauling the full telemetry file around.

    Args:
        params (DownsampleInput): n, path, scope, fields

    Returns:
        str: JSON with keys: path, original_count, returned_count, samples.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        start, end, warning = st.resolve_scope(samples, params.scope)
        result = st.downsample(samples, params.n, start, end + 1)
        if params.fields:
            result = [{k: s.get(k) for k in params.fields} for s in result]
        payload = {"path": str(path), "original_count": len(samples),
                   "returned_count": len(result), "samples": result}
        if warning:
            payload["warnings"] = [warning]
        return json.dumps(payload, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class FieldAtTimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: float = Field(..., description="Game time (the 't' field's value) to find the nearest sample to.")
    path: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_field_at_time", annotations={"title": "Get the sample nearest a given game time",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_field_at_time(params: FieldAtTimeInput) -> str:
    """Find the telemetry sample whose 't' is closest to the given time --
    "what was the state at T+X" instead of manually searching.

    Args:
        params (FieldAtTimeInput): t, path

    Returns:
        str: JSON with the matched sample (all its fields), or an error.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        result = st.field_at_time(samples, params.t)
        return json.dumps({"path": str(path), "sample": result}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


# ===========================================================================
# STAGE 2 -- flight structure & events
# ===========================================================================

class FlightSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_flight_summary", annotations={"title": "Summarize a flight",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_flight_summary(params: FlightSummaryInput) -> str:
    """Summarize a flight: duration, altitude/velocity range, mass
    start/end, part count, max temp, body. The "what happened" tool,
    replacing manual JSON eyeballing.

    Args:
        params (FlightSummaryInput): path

    Returns:
        str: JSON summary. Includes 'time_anomaly' (non-null) if 't' was
        found non-monotonic across the file -- a real, not-yet-root-caused
        gotcha first seen 2026-08-28 on a crashed flight.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        result = st.flight_summary(samples)
        result["path"] = str(path)
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class PhaseDetectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_phase_detect", annotations={"title": "Segment a flight into phases",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_phase_detect(params: PhaseDetectInput) -> str:
    """Segment a flight into named phases (prelaunch/powered_ascent/
    coast_ascent/coast_descent/powered_descent) from mass-trend + vv
    sign. HEURISTIC -- not a read of the game's own internal state (no
    such field is exposed), so treat boundaries as approximate. This is
    what 'scope':{'phase':'...'} on other tools resolves against.

    Args:
        params (PhaseDetectInput): path

    Returns:
        str: JSON with 'phases' (list of phase/start_idx/end_idx/start_t/end_t).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        phases = st.detect_phases(samples)
        return json.dumps({"path": str(path), "phases": phases}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class FindEventsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_find_events", annotations={"title": "Find named flight events",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_find_events(params: FindEventsInput) -> str:
    """Locate named, indexable events: engine_start, engine_cutoff,
    apoapsis, periapsis, max_velocity, max_dynamic_pressure,
    part_count_drop (heuristic likely_cause: destruction vs separation),
    impact. This is what 'scope':{'before_event'/'after_event'/
    'around_event':...} on other tools resolves against.

    Args:
        params (FindEventsInput): path

    Returns:
        str: JSON with 'events' (list of type/idx/t plus type-specific extras).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        events = st.find_events(samples)
        return json.dumps({"path": str(path), "event_count": len(events), "events": events}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


# ===========================================================================
# STAGE 4 -- physics validation, generalized
# ===========================================================================

class ValidateGravityDragInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)
    scope: Optional[Dict[str, Any]] = Field(default=None)
    stride: int = Field(default=1, ge=1, le=200)


@mcp.tool(name="sfsprobe_validate_gravity_drag", annotations={"title": "Validate gravity+drag prediction against measured acceleration",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_validate_gravity_drag(params: ValidateGravityDragInput) -> str:
    """Generalized version of analyze_dragarea.py: predicted (gravity +
    live dragArea) vs measured (finite-difference) acceleration over
    clean coasting pairs, with optional phase/event scoping (e.g. only
    the ascent, or only the last 10s before impact).

    Args:
        params (ValidateGravityDragInput): path, scope, stride

    Returns:
        str: JSON with 'summary' (pair_count, magnitude/direction error
        mean/median/max, suspect_count, comparison_bar) and
        'sample_results' (first 20 individual comparisons).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        start, end, warning = st.resolve_scope(samples, params.scope)
        result = st.validate_gravity_drag(samples, start, end, params.stride)
        result["path"] = str(path)
        if warning:
            result["warnings"] = [warning]
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class NoiseFloorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_a: str = Field(...)
    path_b: str = Field(...)
    fields: Optional[List[str]] = Field(default=None, description="Default: h, vx, vy, m.")


@mcp.tool(name="sfsprobe_noise_floor", annotations={"title": "Compare two nominally-identical flights for divergence",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_noise_floor(params: NoiseFloorInput) -> str:
    """The determinism check from the original architecture doc: compare
    two flights meant to be reproductions of each other (same rocket,
    same commanded inputs), sample-index-aligned, per-field divergence.

    Args:
        params (NoiseFloorInput): path_a, path_b, fields

    Returns:
        str: JSON with aligned_sample_count and per_field_divergence
        (mean/max absolute difference per field).
    """
    try:
        path_a = _resolve_flight_path(params.path_a)
        path_b = _resolve_flight_path(params.path_b)
        samples_a = await asyncio.to_thread(st.load_samples, path_a)
        samples_b = await asyncio.to_thread(st.load_samples, path_b)
        result = st.noise_floor(samples_a, samples_b, params.fields)
        result["path_a"], result["path_b"] = str(path_a), str(path_b)
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class CleanSegmentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)
    kind: str = Field(default="coast", description="'coast' (mass flat, no thrust) or 'burn' (mass decreasing).")
    stride: int = Field(default=1, ge=1, le=200)
    limit: int = Field(default=50, ge=1, le=2000)


@mcp.tool(name="sfsprobe_clean_segments", annotations={"title": "Find clean coasting or burning segments",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_clean_segments(params: CleanSegmentsInput) -> str:
    """Find index pairs that are clean coasting (mass flat, partCount
    stable, above 5m) or clean burning (mass strictly decreasing,
    partCount stable) segments -- the filter validate_gravity_drag uses
    internally, exposed standalone for other uses.

    Args:
        params (CleanSegmentsInput): path, kind, stride, limit

    Returns:
        str: JSON with 'segment_count' and 'segments' (capped at limit,
        each with start_idx/end_idx/start_t/end_t).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        pairs = list(st.find_clean_segments(samples, params.kind, params.stride))
        segs = [{"start_idx": i, "end_idx": j, "start_t": samples[i].get("t"), "end_t": samples[j].get("t")}
                for i, j in pairs[:params.limit]]
        return json.dumps({"path": str(path), "segment_count": len(pairs), "segments": segs}, indent=2)
    except (FileNotFoundError, ValueError) as e:
        return _error_for_exception(e)


# ===========================================================================
# STAGE 5 -- derived flight metrics
# ===========================================================================

class ApoapsisPeriapsisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_apoapsis_periapsis", annotations={"title": "Observed vs predicted apoapsis/periapsis",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_apoapsis_periapsis(params: ApoapsisPeriapsisInput) -> str:
    """Observed apoapsis/periapsis (from real position extrema) compared
    against the game's own live predApo/predPeri prediction.

    Args:
        params (ApoapsisPeriapsisInput): path

    Returns:
        str: JSON with observed_apoapsis_altitude_m, observed_periapsis_altitude_m,
        predicted_apoapsis_altitude_m, predicted_periapsis_altitude_m (if available).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        result = st.compute_apoapsis_periapsis(samples)
        result["path"] = str(path)
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class DeltaVInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)
    start_idx: int = Field(...)
    end_idx: int = Field(...)
    isp: Optional[float] = Field(default=None, description="Required for a real number -- see sfsprobe_rocket_summary for per-engine ISP.")


@mcp.tool(name="sfsprobe_delta_v", annotations={"title": "Estimate delta-v used over a mass-loss range",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_delta_v(params: DeltaVInput) -> str:
    """Tsiolkovsky rocket equation from mass loss between two sample
    indices. ISP is NOT reliably in telemetry (fuelByStage observed
    empty in real flights) -- pass isp explicitly or this returns a note
    instead of a fabricated number.

    Args:
        params (DeltaVInput): path, start_idx, end_idx, isp

    Returns:
        str: JSON with mass_start_t, mass_end_t, and either delta_v_ms
        (if isp given) or a 'note' explaining why not.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        result = st.estimate_delta_v(samples, params.start_idx, params.end_idx, params.isp)
        result["path"] = str(path)
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class DivergenceCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(default=None)
    targets: Dict[str, float] = Field(..., description="Field name -> expected value, e.g. {'h': 5000, 'vv': 0}.")
    tolerance_pct: float = Field(default=5.0, ge=0.0, description="Percent deviation allowed before flagging diverged.")


@mcp.tool(name="sfsprobe_divergence_check", annotations={"title": "Check the latest/final sample against target values",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_divergence_check(params: DivergenceCheckInput) -> str:
    """Compare the flight's final sample against a set of target field
    values, flagging which have diverged beyond tolerance_pct. This is
    the observer-gate primitive from the original architecture doc
    ("notice the flight has diverged from what was expected") -- early,
    but cheap to have now.

    Args:
        params (DivergenceCheckInput): path, targets, tolerance_pct

    Returns:
        str: JSON with per-target actual/expected/diff_pct/diverged, and
        an overall 'any_diverged' bool.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        if not samples:
            return _error_response("NO_SAMPLES", "no samples")
        latest = samples[-1]
        results = {}
        any_diverged = False
        for field, target in params.targets.items():
            actual = latest.get(field)
            if actual is None:
                results[field] = {"error_code": "MISSING_FIELD", "error": "field not present in latest sample"}
                continue
            diff_pct = abs(actual - target) / abs(target) * 100 if target != 0 else (0.0 if actual == 0 else float("inf"))
            diverged = diff_pct > params.tolerance_pct
            any_diverged = any_diverged or diverged
            results[field] = {"actual": actual, "target": target, "diff_pct": diff_pct, "diverged": diverged}
        return json.dumps({"path": str(path), "at_t": latest.get("t"), "any_diverged": any_diverged,
                            "targets": results}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


# ===========================================================================
# STAGE 6 -- comparison & regression
# ===========================================================================

class CompareFlightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_a: str = Field(...)
    path_b: str = Field(...)
    fields: List[str] = Field(..., min_length=1)


@mcp.tool(name="sfsprobe_compare_flights", annotations={"title": "Compare two flights field by field",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_compare_flights(params: CompareFlightsInput) -> str:
    """Compare two flights (e.g. rocket design A vs B) on chosen fields'
    stats, with the mean difference called out per field.

    Args:
        params (CompareFlightsInput): path_a, path_b, fields

    Returns:
        str: JSON, one entry per field with flight_a stats, flight_b
        stats, and mean_diff (b - a).
    """
    try:
        path_a = _resolve_flight_path(params.path_a)
        path_b = _resolve_flight_path(params.path_b)
        samples_a = await asyncio.to_thread(st.load_samples, path_a)
        samples_b = await asyncio.to_thread(st.load_samples, path_b)
        result = st.compare_flights(samples_a, samples_b, params.fields)
        return json.dumps({"path_a": str(path_a), "path_b": str(path_b), "comparison": result}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class RegressionCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., description="An archived flight file to re-check against the CURRENT gravity+drag formula.")
    max_median_error_pct: float = Field(default=1.0, ge=0.0, description="Pass/fail threshold on median magnitude error.")


@mcp.tool(name="sfsprobe_regression_check", annotations={"title": "Re-check an old flight against current formulas",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_regression_check(params: RegressionCheckInput) -> str:
    """Re-run gravity+drag validation on an OLD archived flight using the
    CURRENT formula code, with a clear pass/fail verdict. This is the
    literal "does our mod/model still work" check this documentation
    effort exists for -- run it after an SFS version update to see if
    anything silently changed.

    Args:
        params (RegressionCheckInput): path, max_median_error_pct

    Returns:
        str: JSON with 'passed' (bool), the median error found, and the
        threshold it was checked against.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        result = st.validate_gravity_drag(samples)
        median = (result["summary"]["magnitude_error_pct"] or {}).get("median")
        passed = median is not None and median <= params.max_median_error_pct
        return json.dumps({
            "path": str(path), "passed": passed, "median_magnitude_error_pct": median,
            "threshold_pct": params.max_median_error_pct, "full_summary": result["summary"],
        }, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


# ===========================================================================
# STAGE 7 -- data management / bookkeeping
# ===========================================================================

def _append_flight_log(path: Path, tag: Optional[str], notes: Optional[str], summary: Optional[dict] = None) -> None:
    entry = {"logged_at": time.time(), "file": str(path), "tag": tag, "notes": notes, "summary": summary}
    with FLIGHTS_LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


class ListFlightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=20, ge=1, le=500)


@mcp.tool(name="sfsprobe_list_flights", annotations={"title": "List logged/archived flights",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_list_flights(params: ListFlightsInput) -> str:
    """List flights that have been explicitly tagged (via sfsprobe_tag_flight
    or sfsprobe_run_and_analyze), newest first, plus a count of untagged
    files sitting in the archive folder. Without this, results only ever
    live in chat history and evaporate between sessions.

    Args:
        params (ListFlightsInput): limit

    Returns:
        str: JSON with 'tagged_flights' (newest first, capped at limit)
        and 'untagged_archive_count'.
    """
    tagged = []
    if FLIGHTS_LOG_FILE.exists():
        for line in FLIGHTS_LOG_FILE.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    tagged.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    tagged.sort(key=lambda e: e.get("logged_at", 0), reverse=True)
    tagged_files = {e["file"] for e in tagged}
    untagged_count = 0
    if ARCHIVE_DIR.exists():
        for f in ARCHIVE_DIR.glob("*_truth_*.jsonl"):
            if str(f) not in tagged_files:
                untagged_count += 1
    return json.dumps({"tagged_flights": tagged[:params.limit], "untagged_archive_count": untagged_count,
                        "flights_log_file": str(FLIGHTS_LOG_FILE)}, indent=2)


class FlightToCsvInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(...)
    fields: Optional[List[str]] = Field(default=None, description="Omit to export every field found in the first sample.")
    output_path: Optional[str] = Field(default=None, description="Omit to write next to the source file with a .csv extension.")


@mcp.tool(name="sfsprobe_flight_to_csv", annotations={"title": "Export a flight to CSV",
          "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_flight_to_csv(params: FlightToCsvInput) -> str:
    """Export a flight's telemetry to CSV, for spreadsheet/external-tool
    inspection.

    Args:
        params (FlightToCsvInput): path, fields, output_path

    Returns:
        str: JSON with output_path and row_count.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        if not samples:
            return _error_response("NO_SAMPLES", "no samples to export")
        fields = params.fields or list(samples[0].keys())
        out_path = Path(params.output_path).expanduser() if params.output_path else path.with_suffix(".csv")

        def _write():
            with out_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for s in samples:
                    writer.writerow(s)
        await asyncio.to_thread(_write)
        return json.dumps({"output_path": str(out_path), "row_count": len(samples), "fields": fields}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class TagFlightInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(...)
    tag: str = Field(..., min_length=1, description="Short label, e.g. rocket name or what was being tested.")
    notes: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_tag_flight", annotations={"title": "Attach a label/note to an archived flight",
          "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def sfsprobe_tag_flight(params: TagFlightInput) -> str:
    """Attach a tag and optional notes to an archived flight, appended to
    flights_log.jsonl at the project root, so sfsprobe_list_flights can
    find it later.

    Args:
        params (TagFlightInput): path, tag, notes

    Returns:
        str: JSON confirming what was logged.
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        summary = st.flight_summary(samples)
        await asyncio.to_thread(_append_flight_log, path, params.tag, params.notes, summary)
        return json.dumps({"logged": True, "path": str(path), "tag": params.tag,
                            "flights_log_file": str(FLIGHTS_LOG_FILE)}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


# ===========================================================================
# STAGE 8 -- pre-flight/design-time, from a live snapshot
# ===========================================================================

class RocketSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(default=8.0, ge=1.0, le=60.0)


@mcp.tool(name="sfsprobe_rocket_summary", annotations={"title": "Summarize the currently active rocket (live)",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_rocket_summary(params: RocketSummaryInput) -> str:
    """Run 'snapshot' against the live game and summarize the active
    rocket: total mass (real live-evaluated values, respecting this
    project's data-trust rule), part list, and best-effort engine
    thrust/ISP fields if recognizable in the dump.

    Args:
        params (RocketSummaryInput): timeout_s

    Returns:
        str: JSON with part_count, total_mass_t, parts, engine_fields_found,
        and a 'note' if no engine data could be extracted.
    """
    try:
        response, elapsed = await asyncio.to_thread(send_command, "snapshot", params.timeout_s, DEFAULT_POLL_INTERVAL_S)
    except ProbeTimeoutError as e:
        return _error_for_exception(e)
    except FileNotFoundError as e:
        return _error_for_exception(e)
    try:
        snap = json.loads(SNAPSHOT_JSON_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return json.dumps({"error_code": "PARSE_ERROR",
                            "error": f"snapshot responded ({response!r}) but {SNAPSHOT_JSON_FILE} "
                                     f"couldn't be read/parsed: {e}"}, indent=2)
    result = st.rocket_summary(snap)
    result["elapsed_seconds"] = round(elapsed, 3)
    return json.dumps(result, indent=2)


class PartLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_substring: str = Field(..., min_length=1)
    timeout_s: float = Field(default=8.0, ge=1.0, le=60.0)


@mcp.tool(name="sfsprobe_part_lookup", annotations={"title": "Look up parts by name on the active rocket (live)",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_part_lookup(params: PartLookupInput) -> str:
    """Run 'snapshot' live and find parts by (case-insensitive) name
    substring -- real live-read mass/temperature/heat-tolerance, not
    static/guessed data.

    Args:
        params (PartLookupInput): name_substring, timeout_s

    Returns:
        str: JSON with 'matches' (name, mass_t, temperature_c, heat_tolerance).
    """
    try:
        response, elapsed = await asyncio.to_thread(send_command, "snapshot", params.timeout_s, DEFAULT_POLL_INTERVAL_S)
    except ProbeTimeoutError as e:
        return _error_for_exception(e)
    except FileNotFoundError as e:
        return _error_for_exception(e)
    try:
        snap = json.loads(SNAPSHOT_JSON_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return json.dumps({"error_code": "PARSE_ERROR",
                            "error": f"snapshot responded ({response!r}) but {SNAPSHOT_JSON_FILE} "
                                     f"couldn't be read/parsed: {e}"}, indent=2)
    matches = st.part_lookup(snap, params.name_substring)
    return json.dumps({"match_count": len(matches), "matches": matches, "elapsed_seconds": round(elapsed, 3)}, indent=2)


# ===========================================================================
# STAGE 9 -- coverage tracking
# ===========================================================================

class ChecklistStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checklist_path: Optional[str] = Field(default=None, description="Omit to use docs/high_level_checklist.md.")


@mcp.tool(name="sfsprobe_checklist_status", annotations={"title": "Summarize high_level_checklist.md's confirmed/open items",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_checklist_status(params: ChecklistStatusInput) -> str:
    """Parse the project's high_level_checklist.md and report confirmed
    ([x]) vs open ([ ]) items per section, so "what's left" doesn't
    require re-reading the file by hand.

    Args:
        params (ChecklistStatusInput): checklist_path

    Returns:
        str: JSON with per-section confirmed/total counts and item text.
    """
    path = Path(params.checklist_path).expanduser() if params.checklist_path \
        else _PROJECT_ROOT / "docs" / "high_level_checklist.md"
    if not path.exists():
        return _error_response("FILE_NOT_FOUND", f"checklist not found: {path}")
    text = path.read_text()
    sections = []
    current_section = None
    current_items = []
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            if current_section is not None:
                sections.append({"section": current_section, "items": current_items,
                                  "confirmed": sum(1 for it in current_items if it["confirmed"]),
                                  "total": len(current_items)})
            current_section = heading.group(1).strip()
            current_items = []
            continue
        item = re.match(r"^-\s+\[([ xX])\]\s+(.+)$", line)
        if item and current_section is not None:
            current_items.append({"confirmed": item.group(1).lower() == "x", "text": item.group(2).strip()})
    if current_section is not None:
        sections.append({"section": current_section, "items": current_items,
                          "confirmed": sum(1 for it in current_items if it["confirmed"]),
                          "total": len(current_items)})
    total_confirmed = sum(s["confirmed"] for s in sections)
    total_items = sum(s["total"] for s in sections)
    return json.dumps({"path": str(path), "total_confirmed": total_confirmed, "total_items": total_items,
                        "sections": sections}, indent=2)


# ===========================================================================
# STAGE 10 -- scripted flight orchestration
# ===========================================================================

def _wait_until(field: str, op: str, value: float, timeout_s: float, poll_interval_s: float) -> tuple[bool, float, Optional[dict]]:
    """Poll the LIVE truth.jsonl's last line until field <op> value holds
    or timeout. Reads only the file's tail (last 4KB) each poll -- cheap
    even on a large, actively-growing telemetry file."""
    if op not in st._OPS:
        raise ValueError(f"unknown op {op!r}, must be one of {list(st._OPS)}")
    fn = st._OPS[op]
    start = time.monotonic()
    deadline = start + timeout_s
    last = None
    while time.monotonic() < deadline:
        if TRUTH_FILE.exists():
            try:
                with TRUTH_FILE.open("rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    read_size = min(size, 4096)
                    f.seek(size - read_size)
                    chunk = f.read().decode("utf-8", errors="ignore")
                lines = [l for l in chunk.splitlines() if l.strip()]
                if lines:
                    try:
                        last = json.loads(lines[-1])
                    except json.JSONDecodeError:
                        last = None
                    if last is not None:
                        v = last.get(field)
                        if v is not None and fn(v, value):
                            return True, time.monotonic() - start, last
            except OSError:
                pass
        time.sleep(poll_interval_s)
    return False, time.monotonic() - start, last


class RunFlightScriptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: List[Dict[str, Any]] = Field(
        ..., min_length=1,
        description=(
            "Ordered steps, each ONE of: "
            "{'commands': ['throttle 1','ignite'], 'timeout_s':10} (batched, one game tick); "
            "{'wait_s': 30} (fixed real-time delay); "
            "{'wait_until': {'field':'h','op':'>','value':2000,'timeout_s':60}} "
            "(poll live telemetry until a condition holds -- op is one of <,<=,>,>=,==,!=). "
            "Execution stops early if a wait_until condition times out, or a commands "
            "step's mod folder check fails."
        ),
    )


@mcp.tool(name="sfsprobe_run_flight_script", annotations={"title": "Run a scripted flight profile",
          "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
async def sfsprobe_run_flight_script(params: RunFlightScriptInput) -> str:
    """Run an ordered sequence of command batches, fixed waits, and
    live-telemetry-condition waits -- one call instead of manually
    driving each step. Enables condition-based flight profiles ("cut
    engine once altitude exceeds X") that are repeatable across
    different rocket designs, rather than fixed-time scripts that only
    work for one specific design.

    Args:
        params (RunFlightScriptInput): steps

    Returns:
        str: JSON with 'log' (one entry per step: type, result/matched/
        waited, elapsed_seconds) and total_elapsed_seconds. A wait_until
        that times out stops the script and is noted in the log.
    """
    log = []
    start = time.monotonic()
    for i, step in enumerate(params.steps):
        if "commands" in step:
            cmds = step["commands"]
            t_s = step.get("timeout_s", 10.0)
            p_s = step.get("poll_interval_s", DEFAULT_POLL_INTERVAL_S)
            try:
                results, elapsed, complete = await asyncio.to_thread(send_command_batch, cmds, t_s, p_s)
                log.append({"step": i, "type": "commands", "commands": cmds, "results": results,
                            "complete": complete, "elapsed_seconds": round(elapsed, 3)})
            except FileNotFoundError as e:
                log.append({"step": i, "type": "commands", "error_code": "FILE_NOT_FOUND", "error": str(e)})
                break
        elif "wait_s" in step:
            await asyncio.sleep(step["wait_s"])
            log.append({"step": i, "type": "wait_s", "waited_s": step["wait_s"]})
        elif "wait_until" in step:
            w = step["wait_until"]
            try:
                matched, elapsed, last = await asyncio.to_thread(
                    _wait_until, w["field"], w["op"], w["value"],
                    w.get("timeout_s", 30.0), w.get("poll_interval_s", 0.2),
                )
            except ValueError as e:
                log.append({"step": i, "type": "wait_until", "error_code": "INVALID_PARAM", "error": str(e)})
                break
            log.append({"step": i, "type": "wait_until", "matched": matched, "elapsed_seconds": round(elapsed, 3),
                        "field": w["field"], "op": w["op"], "target_value": w["value"],
                        "last_sample_value": last.get(w["field"]) if last else None})
            if not matched:
                log.append({"step": i, "warning_code": "WAIT_TIMEOUT",
                            "note": "condition not met before timeout -- stopping script here"})
                break
        else:
            log.append({"step": i, "error_code": "INVALID_PARAM",
                        "error": f"unrecognized step shape, expected one of "
                                 f"'commands'/'wait_s'/'wait_until', got keys: {list(step.keys())}"})
            break
    return json.dumps({"log": log, "total_elapsed_seconds": round(time.monotonic() - start, 3)}, indent=2)


# ===========================================================================
# STAGE 11 -- closing the loop: run + auto-analyze
# ===========================================================================

class RunAndAnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: List[Dict[str, Any]] = Field(..., min_length=1, description="Same format as sfsprobe_run_flight_script's steps.")
    tag: Optional[str] = Field(default=None, description="If given, the resulting archived flight is logged via sfsprobe_tag_flight.")
    notes: Optional[str] = Field(default=None)


@mcp.tool(name="sfsprobe_run_and_analyze", annotations={"title": "Run a flight script, then auto-analyze the result",
          "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
async def sfsprobe_run_and_analyze(params: RunAndAnalyzeInput) -> str:
    """Run a flight script (see sfsprobe_run_flight_script), then find
    the newly-archived truth.jsonl (by mtime, created after this call
    started) and automatically run flight_summary + gravity/drag
    validation on it. Optionally tags the result. Closes the test ->
    analyze loop into one call instead of two-plus-manual-lookup.

    Args:
        params (RunAndAnalyzeInput): steps, tag, notes

    Returns:
        str: JSON with script_log, archived_file (or a note if none was
        found -- e.g. the script didn't include a 'telemetry off' step),
        flight_summary, and drag_validation_summary.
    """
    script_start = time.time()
    script_result_str = await sfsprobe_run_flight_script(RunFlightScriptInput(steps=params.steps))
    script_result = json.loads(script_result_str)

    candidates = []
    if ARCHIVE_DIR.exists():
        candidates = [f for f in ARCHIVE_DIR.glob("*_truth_*.jsonl") if f.stat().st_mtime >= script_start - 1]
    if not candidates:
        return json.dumps({"script_log": script_result, "archived_file": None,
                            "warning_code": "NO_NEW_ARCHIVE",
                            "note": "no newly-archived truth.jsonl found -- did the script include a "
                                     "{'commands': ['telemetry off']} step?"}, indent=2)
    newest = max(candidates, key=lambda f: f.stat().st_mtime)
    samples = await asyncio.to_thread(st.load_samples, newest)
    summary = st.flight_summary(samples)
    validation = st.validate_gravity_drag(samples)
    if params.tag:
        await asyncio.to_thread(_append_flight_log, newest, params.tag, params.notes, summary)
    return json.dumps({
        "script_log": script_result, "archived_file": str(newest),
        "flight_summary": summary, "drag_validation_summary": validation["summary"],
        "tagged": bool(params.tag),
    }, indent=2)


# ---------------------------------------------------------------------------

# ===========================================================================
# STAGE 12 -- blueprint loading (bypasses the editor UI entirely)
# ===========================================================================

# Maps the mod's 'loadblueprint: FAILED reason=X' text to a distinct
# error_code, exactly as requested: a caller needs to be able to tell
# "wasn't loaded because the game isn't in design mode" from "wasn't
# loaded because the file/deserialize/spawn step failed" -- not just one
# generic failure.
_BLUEPRINT_FAILURE_CODES = {
    "no_path": "INVALID_PARAM",
    "not_in_design": "NOT_IN_DESIGN",
    "file_not_found": "FILE_NOT_FOUND",
    "read_error": "FILE_ERROR",
    "type_resolution": "TYPE_RESOLUTION_FAILED",
    "fromjson_method_not_found": "TYPE_RESOLUTION_FAILED",
    "deserialize_error": "PARSE_ERROR",
    "deserialize_null": "PARSE_ERROR",
    "spawn_method_not_found": "TYPE_RESOLUTION_FAILED",
    "spawn_exception": "SPAWN_FAILED",
}


def _resolve_blueprint_path(name: Optional[str], path: Optional[str]) -> Path:
    if path:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"blueprint file not found: {p}")
        return p
    if not name:
        raise ValueError("either 'name' (looked up in blueprints/research/) or an explicit 'path' must be given")
    p = BLUEPRINTS_RESEARCH_DIR / name / "Blueprint.txt"
    if not p.exists():
        raise FileNotFoundError(
            f"no blueprint named {name!r} found in {BLUEPRINTS_RESEARCH_DIR} (expected {p})"
        )
    return p


class LoadBlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(
        default=None,
        description="Blueprint name -- looked up as blueprints/research/<name>/Blueprint.txt. "
                     "Omit if passing an explicit 'path' instead.",
    )
    path: Optional[str] = Field(
        default=None,
        description="Explicit path to a Blueprint.txt-format file, if not using 'name'. "
                     "Can point anywhere, including blueprints/live/ once that's in use.",
    )
    timeout_s: float = Field(default=10.0, ge=1.0, le=60.0,
                              description="Max seconds to wait for the command to complete.")


@mcp.tool(
    name="sfsprobe_load_blueprint",
    annotations={
        "title": "Load a rocket blueprint into the game (bypasses the editor UI)",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sfsprobe_load_blueprint(params: LoadBlueprintInput) -> str:
    """Spawn a rocket design directly, without going through the game's
    editor UI at all. Reads a Blueprint.txt-format JSON file (either
    blueprints/research/<name>/Blueprint.txt, or an explicit path),
    deserializes it via the game's own JsonWrapper.FromJson<Blueprint>,
    and calls the confirmed public-static RocketManager.SpawnBlueprint --
    all through the mod's 'loadblueprint' command (v0.30.0+).

    GENUINELY UNTESTED-LIVE as of first build (2026-08-29) --
    SpawnBlueprint's own body was never read during the source-code
    documentation effort, and there's a documented possible DLC/
    ownership gate that could silently reject some parts. Treat early
    calls as an experiment.

    Distinct error codes so a caller can tell WHY it failed, not just
    that it did: NOT_IN_DESIGN (wrong scene -- must be in the build/
    design screen), FILE_NOT_FOUND, FILE_ERROR (couldn't read), 
    TYPE_RESOLUTION_FAILED (a reflection lookup failed -- likely means
    the game's internals changed), PARSE_ERROR (bad/unparseable JSON),
    SPAWN_FAILED (SpawnBlueprint itself threw -- the file was fine, the
    game rejected the design; check the error message for why).

    Args:
        params (LoadBlueprintInput): name, path, timeout_s

    Returns:
        str: JSON with keys: success (bool), path (the file used), and
        either 'response' (raw OK text) or 'error_code'/'error'/
        'failure_reason' (the raw reason= token from the mod, in case the
        mapped error_code loses detail worth seeing).
    """
    try:
        blueprint_path = _resolve_blueprint_path(params.name, params.path)
    except (FileNotFoundError, ValueError) as e:
        return _error_for_exception(e)

    try:
        response, elapsed = await asyncio.to_thread(
            send_command, f"loadblueprint {blueprint_path}", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except ProbeTimeoutError as e:
        return _error_for_exception(e, elapsed_seconds=round(params.timeout_s, 3))
    except FileNotFoundError as e:
        return _error_for_exception(e)

    if "loadblueprint: OK" in response:
        return json.dumps({
            "success": True, "path": str(blueprint_path),
            "response": response, "elapsed_seconds": round(elapsed, 3),
        }, indent=2)

    reason_match = re.search(r"reason=(\S+)", response)
    reason = reason_match.group(1) if reason_match else None
    error_code = _BLUEPRINT_FAILURE_CODES.get(reason, "UNKNOWN_ERROR")
    return json.dumps({
        "success": False, "path": str(blueprint_path),
        "error_code": error_code, "failure_reason": reason,
        "error": response, "elapsed_seconds": round(elapsed, 3),
    }, indent=2)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _log(f"starting, mod dir = {MOD_DIR}")
    mcp.run()
