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
import shutil
import time
import asyncio
import csv
import difflib
import re
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

# analysis/ (this project's analysis code, renamed from python/ 2026-08-30)
# lives alongside sfsprobe_mcp/, not inside it -- add it to sys.path so
# these tools call directly into sfs_telemetry.py (no subprocess). Keeps
# mac-terminal-mcp reserved for things that actually need a real shell
# (compiling the mod), per Christian's explicit ask.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "analysis"))
import sfs_telemetry as st  # noqa: E402
import blueprint_builder as bpb  # noqa: E402
import il_inventory  # noqa: E402  -- deep_search's type/member parser, MCP overhaul Checkpoint 5
import forward_sim as fsim  # noqa: E402  -- test_against_run(), wrapped as sfsprobe_test_against_run below.
                             # Guarded by `if __name__ == "__main__":` in forward_sim.py itself, so
                             # importing it here never touches sys.argv or runs its CLI block.

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
# The mod's real C# source -- light_search's static_fallback path parses
# this live, every call, so the command/field list it returns can never
# drift out of sync with whatever version of the mod is actually
# installed/built.
SFSPROBE_CS_PATH = _PROJECT_ROOT / "sfsprobe" / "SFSProbe.cs"
# Reference docs indexed by light_search's domain="doc" (MCP overhaul
# Checkpoint 4) -- re-parsed from disk on a short TTL (DOC_CACHE_TTL_S)
# rather than at import time, so edits to either file show up without
# restarting the MCP server.
DOC_PATHS = [
    _PROJECT_ROOT / "docs" / "sfs_physics_reference.md",
    _PROJECT_ROOT / "docs" / "sfs_source_reference.md",
]
# deep_search (MCP overhaul Checkpoint 5) -- the real decompiled game
# assembly, for when light_search's doc coverage is missing or its
# hand-written prose can't be trusted over ground truth. Env-var-overridable
# following the same SFSPROBE_MOD_DIR pattern, since this is also a
# machine-specific Steam install path.
DEFAULT_ASSEMBLY_PATH = (
    "~/Library/Application Support/Steam/steamapps/common/"
    "Spaceflight Simulator/SpaceflightSimulatorGame.app/Contents/Resources/"
    "Data/Managed/Assembly-CSharp.dll"
)
ASSEMBLY_PATH = Path(
    os.environ.get("SFSPROBE_ASSEMBLY_PATH", DEFAULT_ASSEMBLY_PATH)
).expanduser()
MONODIS_BIN = os.environ.get("SFSPROBE_MONODIS", "monodis")
# deep_search's own cache -- deliberately NOT scratch/full_il.txt, which is
# Christian's manual-research scratch file (see docs/sfs_source_reference.md
# §A2). A repeatable tool call must never clobber work he's mid-way through.
DEEP_SEARCH_CACHE_DIR = _PROJECT_ROOT / "scratch" / ".deep_search_cache"
DEEP_SEARCH_IL_CACHE = DEEP_SEARCH_CACHE_DIR / "assembly_full_il.txt"
DEEP_SEARCH_IL_META = DEEP_SEARCH_CACHE_DIR / "assembly_full_il.meta.json"
CMD_FILE = MOD_DIR / "command.txt"
RESULT_FILE = MOD_DIR / "result.txt"
PROBE_LOG_FILE = MOD_DIR / "probe.log"
# v0.60.0: truth.jsonl/inputs.jsonl merged into one live file (SFSProbe.cs's
# unified archive lifecycle) -- SAMPLE_FILE replaces the old TRUTH_FILE/
# INPUTS_FILE pair. ROCKETSTATE_FILE is the separate ~1Hz per-part JSON
# recorder's live file ("parts" mode), never previously referenced from this
# side since no parts-mode analysis tooling existed until this pass.
SAMPLE_FILE = MOD_DIR / "sample.jsonl"
ROCKETSTATE_FILE = MOD_DIR / "rocketstate.jsonl"
DRAGAREA_JSON_FILE = MOD_DIR / "sfs_probe_dragarea.json"
# Written by the mod's 'describe' command (v0.57.0+, MCP overhaul Checkpoint
# 1) -- the live CommandRegistry/FieldRegistry dump that light_search
# (Checkpoint 2) prefers over the regex-parsed SFSProbe.cs fallback below.
DESCRIBE_JSON_FILE = MOD_DIR / "sfs_probe_describe.json"
SNAPSHOT_JSON_FILE = MOD_DIR / "sfs_probe_flight.json"
PLACED_MAGNETS_JSON_FILE = MOD_DIR / "sfs_probe_placed_magnets.json"
ARCHIVE_DIR = MOD_DIR / "archive"
# v0.60.0: the only path off the archive lifecycle's auto-delete-on-next-run
# policy -- sfsprobe_tag_flight copies a .gz here so DeletePreviousArchive
# (SFSProbe.cs) can never remove it.
KEPT_DIR = ARCHIVE_DIR / "kept"
FLIGHTS_LOG_FILE = _PROJECT_ROOT / "bookkeeping" / "flights_log.jsonl"
BLUEPRINTS_RESEARCH_DIR = _PROJECT_ROOT / "blueprints" / "research"
BLUEPRINTS_LIVE_DIR = _PROJECT_ROOT / "blueprints" / "live"

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_POLL_INTERVAL_S = 0.15
# The mod's own PollCommands() only checks command.txt every 0.5s (see
# ProbeRunner.Update() in SFSProbe.cs) -- staler than this and a "recent
# activity" heuristic in sfsprobe_status stops trusting probe.log as a
# sign the game is currently alive vs. just left over from a past session.
STALE_LOG_THRESHOLD_S = 30.0
# How long a fetched 'describe' registry is trusted before light_search
# re-fetches it -- short enough that a mod rebuilt+relaunched mid-session is
# picked up quickly, long enough that a rapid sequence of searches doesn't
# each pay a real game round-trip.
REGISTRY_CACHE_TTL_S = 5.0
DESCRIBE_TIMEOUT_S = 3.0
# How long a parsed doc-chunk index (DOC_PATHS) is cached before re-reading
# the files -- same rationale as REGISTRY_CACHE_TTL_S, just for disk reads
# instead of a game round-trip.
DOC_CACHE_TTL_S = 5.0
# deep_search: max IL lines returned per matched type (a class summary can
# run 900+ lines for a large class like EngineModule; this keeps a response
# reasonable while the returned line_range tells a caller exactly where to
# look in the cache file for more).
DEEP_SEARCH_MAX_LINES = 250

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

    Fast-fails (MCP overhaul Checkpoint 3) if the command's leading word
    isn't a known sfsprobe command -- no game round-trip at all, just a
    known-command-set lookup (milliseconds), returning close-match
    suggestions via difflib instead of a multi-second wait for the mod's
    own 'unknown command: ...' response. If the command set itself can't
    be resolved (game unreachable AND SFSProbe.cs unreadable), this check
    is skipped entirely -- it fails open, never blocking a real command.

    Args:
        params (SendCommandInput): command, timeout_s, poll_interval_s

    Returns:
        str: JSON with keys: command, response (the new result.txt text),
        elapsed_seconds (float, how long the wait actually took), timed_out
        (always false on success -- a timeout raises instead of returning).
        On a fast-fail: error_code 'UNKNOWN_COMMAND', error, suggestions
        (list), source ('live_registry' or 'static_fallback').
    """
    invalid = await _validate_command_line(params.command)
    if invalid is not None:
        return json.dumps(invalid, indent=2)
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
# Tool: command search -- parses SFSProbe.cs's real Command() switch
# directly, every call, so command syntax/usage is looked up instead of
# guessed from memory (which is exactly how the 'telemetry snapshot' vs
# 'telemetrysnapshot' mixup happened -- a real command that just doesn't
# exist). Scoped to the Command() method's brace range specifically (not
# the whole file) so it doesn't also pick up cases from GetScriptFieldValue's
# short-name switch or AppendComputedField's computed-field registry --
# those are real, but they're a different lookup (telemetry field names,
# not command.txt commands) and mixing them in was more confusing than
# helpful during prototyping.
# ---------------------------------------------------------------------------

_COMMAND_METHOD_RE = re.compile(r'static\s+void\s+Command\s*\(\s*string\s+line\s*\)')
_CASE_RE = re.compile(r'case\s+"([a-zA-Z0-9_]+)"\s*:')
_MAX_COMMENT_LINES = 20  # cap per-command description length; some blocks (telemetry) run 25+ lines


def _find_command_method_bounds(lines: List[str]) -> Optional[tuple[int, int]]:
    """Locate Command(string line)'s body via brace counting -- returns
    (start_line_idx, end_line_idx), both inclusive, 0-indexed. None if the
    method signature isn't found (e.g. it gets renamed someday)."""
    start = None
    for i, line in enumerate(lines):
        if _COMMAND_METHOD_RE.search(line):
            start = i
            break
    if start is None:
        return None
    i = start
    while "{" not in lines[i]:
        i += 1
    depth = 0
    for j in range(i, len(lines)):
        depth += lines[j].count("{") - lines[j].count("}")
        if depth == 0:
            return start, j
    return None


def _parse_probe_commands(cs_path: Path) -> List[Dict[str, Any]]:
    """Parse every 'case "xxx":' inside Command()'s switch, paired with
    whatever comment block sits immediately after it in the source --
    that's where this codebase's own command-syntax documentation
    actually lives (e.g. 'telemetry on <fields>' is explained in a
    comment block right after `case "telemetry":`, not in a docstring
    anywhere). Re-read from disk every call -- deliberately not cached,
    so a rebuilt/edited mod is reflected immediately, same principle as
    this project's data-trust rule for live game values."""
    lines = cs_path.read_text().splitlines()
    bounds = _find_command_method_bounds(lines)
    if bounds is None:
        return []
    start, end = bounds

    commands = []
    seen = set()
    for i in range(start, end + 1):
        line = lines[i]
        m = _CASE_RE.search(line)
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            continue  # duplicate/fallthrough case label -- keep the first
        seen.add(name)

        j = i + 1
        if j < len(lines) and lines[j].strip() == "{":
            j += 1
        comment_lines: List[str] = []
        truncated = False
        while j < len(lines):
            stripped = lines[j].strip()
            if stripped.startswith("//"):
                if len(comment_lines) >= _MAX_COMMENT_LINES:
                    truncated = True
                    break
                comment_lines.append(stripped.lstrip("/ "))
                j += 1
            elif stripped == "":
                # allow a single blank line inside a comment block before giving up
                if j + 1 < len(lines) and lines[j + 1].strip().startswith("//"):
                    j += 1
                    continue
                break
            else:
                break
        description = " ".join(comment_lines).strip()
        if truncated:
            description += " [...]"

        after_colon = line.split(":", 1)[1].strip() if ":" in line else ""
        commands.append({
            "command": name,
            "description": description or None,
            "inline_body": after_colon or None,  # for one-liner cases like 'snapshot', 'world', 'menu'
            "source_line": i + 1,
        })
    return commands


# ---------------------------------------------------------------------------
# Fallback field-index parser -- the parameter-name counterpart to
# _parse_probe_commands above, built for the exact same reason: this
# session independently mis-guessed telemetry field syntax three separate
# times (bare 'gimbalThrottleOut' instead of 'computed:gimbal'; requesting
# a field literally called 'parachuteDrag' that has never existed --
# 'computed:parachuteDrag' expands into six differently-named fields;
# misreading 'parachuteAlphaDeg' as an angle in degrees when it's actually
# an angular ACCELERATION in deg/s^2, per its own source name 'alphaPred').
# All three mistakes share one root cause: nobody -- neither Christian nor
# Claude -- has reliable knowledge of which of the four genuinely different
# field namespaces in this codebase a given name belongs to, or how it's
# actually requested vs. how it appears in output. This tool parses all
# four straight from SFSProbe.cs, every call, so that's looked up instead
# of guessed:
#   1. computed_group       -- 'computed:NAME' groups (AppendComputedField's
#                               switch). Request via 'computed:NAME'; expands
#                               into several OUTPUT keys, never named NAME
#                               itself except by coincidence (e.g. dragArea).
#   2. computed_output_key  -- one entry per OUTPUT key each group above
#                               actually writes (e.g. 'parachuteForceX').
#                               NOT independently requestable -- searching
#                               one explains which computed: group produces
#                               it, which is exactly the lookup that was
#                               missing tonight.
#   3. script_condition_field -- GetScriptFieldValue's short-name switch
#                               (h/vv/t/m/rot/angv/gimbaling/rcsfiring/v/
#                               partCount). Valid in SCRIPT/TRIGGER condition
#                               strings, NOT in a 'telemetry on <fields>' list
#                               (a real, separate mistake from the other two).
#   4. literal_telemetry_field -- bare names Sample()'s own scoped-telemetry
#                               loop special-cases directly (currently just
#                               'partCount', added 2026-09-03) -- valid
#                               DIRECTLY in a 'telemetry on <fields>' list,
#                               unlike #3's same-named script field.
# Plus a fifth, non-enumerable source: real 'telemetry on ...' example
# field-lists mined straight out of comments elsewhere in the file --
# working examples previous sessions already wrote down, not manufactured.
# ---------------------------------------------------------------------------

_COMPUTED_METHOD_RE = re.compile(r'static\s+bool\s+AppendComputedField\s*\(')
_SCRIPT_METHOD_RE = re.compile(r'static\s+double\s+GetScriptFieldValue\s*\(')
_SAMPLE_METHOD_RE = re.compile(r'public\s+static\s+void\s+Sample\s*\(')
_KEY_WRITE_RE = re.compile(r'Append\(",\\"([a-zA-Z0-9_]+)\\":')
_LITERAL_FIELD_RE = re.compile(r'f\s*==\s*"([a-zA-Z0-9_]+)"')
_EXAMPLE_RE = re.compile(r'telemetry on ([a-zA-Z0-9_.,:]+)')


def _find_method_bounds(lines: List[str], method_re: "re.Pattern[str]") -> Optional[tuple[int, int]]:
    """Generic version of _find_command_method_bounds above -- locates any
    method's body via brace counting given its own signature regex, since
    this tool needs to bound THREE different methods
    (AppendComputedField/GetScriptFieldValue/Sample), not just Command().
    Returns (start_line_idx, end_line_idx), both inclusive, 0-indexed."""
    start = None
    for i, line in enumerate(lines):
        if method_re.search(line):
            start = i
            break
    if start is None:
        return None
    i = start
    while "{" not in lines[i]:
        i += 1
    depth = 0
    for j in range(i, len(lines)):
        depth += lines[j].count("{") - lines[j].count("}")
        if depth == 0:
            return start, j
    return None


def _leading_block_comment(lines: List[str], case_line_idx: int) -> Optional[str]:
    """Comments in these switches sit AFTER the case label and its opening
    '{', not before -- same convention _parse_probe_commands relies on.
    Returns None for a single-line case (no attached comment below it --
    a naive forward scan would wrongly attribute the NEXT case's leading
    comment to this one, which happened once during prototyping)."""
    j = case_line_idx + 1
    if not (j < len(lines) and lines[j].strip() == "{"):
        return None
    j += 1
    out: List[str] = []
    truncated = False
    while j < len(lines):
        s = lines[j].strip()
        if s.startswith("//"):
            if len(out) >= _MAX_COMMENT_LINES:
                truncated = True
                break
            out.append(s.lstrip("/ "))
            j += 1
        else:
            break
    text = " ".join(out).strip()
    if truncated:
        text += " [...]"
    return text or None


def _case_block_bounds(lines: List[str], case_line_idx: int) -> tuple[int, int]:
    j = case_line_idx
    if j + 1 < len(lines) and lines[j + 1].strip() == "{":
        depth = 0
        for k in range(j + 1, len(lines)):
            depth += lines[k].count("{") - lines[k].count("}")
            if depth == 0:
                return j, k
    k = j
    while k < len(lines) and ";" not in lines[k]:
        k += 1
    return j, k


def _parse_computed_groups(lines: List[str]) -> List[Dict[str, Any]]:
    """Every 'computed:NAME' group from AppendComputedField's switch, with
    the real OUTPUT keys it writes (mined via _KEY_WRITE_RE over each
    case's own block, not guessed from the group name -- 'parachuteDrag'
    the group writes zero fields literally named 'parachuteDrag')."""
    bounds = _find_method_bounds(lines, _COMPUTED_METHOD_RE)
    if bounds is None:
        return []
    start, end = bounds
    groups, seen = [], set()
    for i in range(start, end + 1):
        m = _CASE_RE.search(lines[i])
        if not m or lines[i].strip().startswith("default"):
            continue
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        desc = _leading_block_comment(lines, i)
        cs, ce = _case_block_bounds(lines, i)
        keys = _KEY_WRITE_RE.findall("\n".join(lines[cs:ce + 1]))
        groups.append({"group": name, "description": desc, "output_keys": keys, "source_line": i + 1})
    return groups


def _parse_script_fields(lines: List[str]) -> List[Dict[str, Any]]:
    """Every short-name alias from GetScriptFieldValue's switch -- valid in
    script/trigger condition strings, explicitly NOT the same namespace as
    a scoped-telemetry field list (that distinction is the point)."""
    bounds = _find_method_bounds(lines, _SCRIPT_METHOD_RE)
    if bounds is None:
        return []
    start, end = bounds
    fields, seen = [], set()
    for i in range(start, end + 1):
        m = _CASE_RE.search(lines[i])
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        is_block = (i + 1 < len(lines) and lines[i + 1].strip() == "{")
        if is_block:
            desc = _leading_block_comment(lines, i)
        else:
            # single-line case, e.g. 'case "h": return ToD(Get(loc, "Height"));'
            # -- the return expression itself IS the description, no comment scan
            desc = lines[i].split(":", 1)[1].strip() if ":" in lines[i] else None
        fields.append({"name": name, "description": desc, "source_line": i + 1})
    return fields


def _parse_literal_telemetry_fields(lines: List[str]) -> List[Dict[str, Any]]:
    """Bare field names Sample()'s scoped-telemetry dispatch loop
    special-cases by literal string equality (currently just 'partCount',
    added 2026-09-03 -- see mod_changelog.md v0.55.0). Distinct from
    script fields of the same name: this list IS valid directly in a
    'telemetry on <fields>' list; #3 above is not."""
    bounds = _find_method_bounds(lines, _SAMPLE_METHOD_RE)
    if bounds is None:
        return []
    start, end = bounds
    fields, seen = [], set()
    for i in range(start, end + 1):
        m = _LITERAL_FIELD_RE.search(lines[i])
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        desc = _leading_block_comment(lines, i)
        fields.append({"name": name, "description": desc, "source_line": i + 1})
    return fields


def _mine_documented_examples(text: str) -> List[str]:
    """Real working 'telemetry on <fields>' example strings already
    written into comments elsewhere in the file -- previous sessions'
    own working usage, not manufactured."""
    return sorted(set(_EXAMPLE_RE.findall(text)))


def _build_field_index(cs_path: Path) -> List[Dict[str, Any]]:
    """Combine all five sources into one flat, taggable entry list. Kept
    as one function (rather than the four callers building the list
    separately) so the entry 'kind' tagging happens in exactly one place."""
    lines = cs_path.read_text().splitlines()
    text = "\n".join(lines)
    entries: List[Dict[str, Any]] = []

    for g in _parse_computed_groups(lines):
        entries.append({
            "kind": "computed_group",
            "request_as": "computed:" + g["group"],
            "produces_keys": g["output_keys"],
            "description": g["description"],
            "source_line": g["source_line"],
        })
        for key in g["output_keys"]:
            entries.append({
                "kind": "computed_output_key",
                "key": key,
                "request_as": "computed:" + g["group"],
                "note": f"'{key}' is an OUTPUT field only, produced by requesting "
                        f"'computed:{g['group']}' -- it is not itself a valid name "
                        f"in a 'telemetry on <fields>' list.",
                "source_line": g["source_line"],
            })

    for s in _parse_script_fields(lines):
        entries.append({
            "kind": "script_condition_field",
            "name": s["name"],
            "description": s["description"],
            "note": "valid in SCRIPT/TRIGGER condition strings (e.g. autostop rules) only -- "
                    "NOT a valid name in a 'telemetry on <fields>' list.",
            "source_line": s["source_line"],
        })

    for f in _parse_literal_telemetry_fields(lines):
        entries.append({
            "kind": "literal_telemetry_field",
            "name": f["name"],
            "description": f["description"],
            "note": "valid DIRECTLY in a 'telemetry on <fields>' list (special-cased in Sample()).",
            "source_line": f["source_line"],
        })

    for ex in _mine_documented_examples(text):
        entries.append({"kind": "documented_example", "example": ex})

    return entries


def _normalize_fallback_field(e: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback field-index entries have different shapes per 'kind'
    (computed_group/computed_output_key/script_condition_field/
    literal_telemetry_field/documented_example) with no single shared
    identity field. Give each a synthetic 'key' so _score_items (which is
    shape-agnostic) has one consistent thing to primary-match against."""
    e = dict(e)
    e.setdefault("key", e.get("name") or e.get("request_as") or e.get("example") or "")
    return e


def _score_items(terms: List[str], items: List[Dict[str, Any]], primary_key: str, limit: int) -> List[Dict[str, Any]]:
    """Shape-agnostic term-overlap scorer, shared by every light_search
    domain regardless of whether items came from the live 'describe'
    registry (commands: name/syntax/description/category; fields:
    key/namespace/group/unit/description/requestAs) or the regex-parsed
    fallback (different shape per domain/kind, see _normalize_fallback_field
    above) -- rather than maintaining a separate per-shape haystack
    function for each of the two sources, every value in the item dict is
    just stringified and searched. `primary_key` gets exact/prefix bonus
    scoring (the item's real command/field name), matching the intent of
    the old per-domain scorers this replaces without needing their
    per-kind special cases."""
    if not terms:
        return items[:limit]
    scored = []
    for it in items:
        primary = str(it.get(primary_key) or "").lower()
        hay = " ".join(str(v) for v in it.values() if v not in (None, "")).lower()
        score = 0
        for t in terms:
            if primary == t:
                score += 10
            elif primary.startswith(t):
                score += 5
            if t in hay:
                score += 1
        if score > 0:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]]


# ---------------------------------------------------------------------------
# Drift auditor -- MCP overhaul Checkpoint 7, architecture decision A. The
# CommandRegistry/FieldRegistry (Checkpoint 1) is meant to be the primary
# source of truth, but nothing stops it from silently rotting out of sync
# with the actual case blocks/switches if a future command or field is added
# to the code without a matching registry entry (exactly the "comments as
# the only documentation" failure mode this whole overhaul exists to fix).
# This diffs BOTH sides straight out of SFSProbe.cs: the registry array
# literals (ground truth for "what the mod claims to support") against the
# same case-block/switch parsers light_search's static_fallback path already
# uses (ground truth for "what the mod actually dispatches"). Pure static
# source analysis -- no live game or `describe` round-trip needed, so this
# can run even with SFS closed, and will still catch drift the moment new
# code is written, before it's ever rebuilt or reloaded.
# ---------------------------------------------------------------------------

_REGISTRY_COMMAND_NAME_RE = re.compile(r'new ProbeCommandInfo\s*\{\s*Name\s*=\s*"([a-zA-Z0-9_]+)"')
_REGISTRY_FIELD_ENTRY_RE = re.compile(
    r'new ProbeFieldInfo\s*\{\s*Key\s*=\s*"([a-zA-Z0-9_]+)"\s*,\s*Namespace\s*=\s*"([a-zA-Z-]+)"'
    r'(?:\s*,\s*Group\s*=\s*"([a-zA-Z0-9_]+)")?'
)


def _extract_named_array_block(text: str, array_name: str, element_type: str) -> str:
    """Both CommandRegistry and FieldRegistry are declared as
    'public static readonly ProbeXInfo[] ArrayName = new ProbeXInfo[] { ... };'
    -- grabs just the '{ ... }' body so the entry regexes below can't
    accidentally match an unrelated ProbeCommandInfo/ProbeFieldInfo literal
    elsewhere in the file (there are none today, but this keeps the audit
    correct if one is ever added for some other purpose)."""
    m = re.search(
        re.escape(array_name) + r"\s*=\s*new " + re.escape(element_type) + r"\[\]\s*\{(.*?)\n\s*\};",
        text, re.S,
    )
    if not m:
        raise ValueError(f"could not locate {array_name} array literal in {SFSPROBE_CS_PATH}")
    return m.group(1)


def _parse_registry_commands(text: str) -> set[str]:
    block = _extract_named_array_block(text, "CommandRegistry", "ProbeCommandInfo")
    return set(_REGISTRY_COMMAND_NAME_RE.findall(block))


def _parse_registry_fields(text: str) -> List[Dict[str, Optional[str]]]:
    block = _extract_named_array_block(text, "FieldRegistry", "ProbeFieldInfo")
    return [
        {"key": em.group(1), "namespace": em.group(2), "group": em.group(3)}
        for em in _REGISTRY_FIELD_ENTRY_RE.finditer(block)
    ]


def _run_registry_drift_audit(cs_path: Path) -> Dict[str, Any]:
    """Compares CommandRegistry/FieldRegistry against the real case-block/
    switch parsers. Returns a report dict; `clean` is True only if every
    section below found zero drift in both directions (code-has-it-
    registry-doesn't, and registry-has-it-code-doesn't -- the latter means
    a STALE entry describing something that no longer exists)."""
    lines = cs_path.read_text().splitlines()
    text = "\n".join(lines)

    reg_commands = _parse_registry_commands(text)
    case_commands = {c["command"] for c in _parse_probe_commands(cs_path)}

    reg_fields = _parse_registry_fields(text)
    computed_groups = _parse_computed_groups(lines)
    case_group_names = {g["group"] for g in computed_groups}
    case_output_keys: set[str] = set()
    for g in computed_groups:
        case_output_keys.update(g["output_keys"])
    script_fields = {f["name"] for f in _parse_script_fields(lines)}
    literal_fields = {f["name"] for f in _parse_literal_telemetry_fields(lines)}

    reg_group_names = {f["group"] for f in reg_fields if f["namespace"] == "computed" and f["group"]}
    reg_output_keys = {f["key"] for f in reg_fields if f["namespace"] == "computed"}
    reg_script_keys = {f["key"] for f in reg_fields if f["namespace"] == "script-condition"}
    reg_all_keys = {f["key"] for f in reg_fields}

    sections = {
        "commands": {
            "missing_from_registry": sorted(case_commands - reg_commands),
            "stale_in_registry": sorted(reg_commands - case_commands),
        },
        "computed_field_groups": {
            "missing_from_registry": sorted(case_group_names - reg_group_names),
            "stale_in_registry": sorted(reg_group_names - case_group_names),
        },
        "computed_output_keys": {
            "missing_from_registry": sorted(case_output_keys - reg_output_keys),
            "stale_in_registry": sorted(reg_output_keys - case_output_keys),
        },
        "script_condition_fields": {
            "missing_from_registry": sorted(script_fields - reg_script_keys),
            "stale_in_registry": sorted(reg_script_keys - script_fields),
        },
        "literal_telemetry_fields": {
            # No dedicated registry namespace exists for this kind (by design,
            # see mod_changelog.md v0.55.0 / the FieldRegistry 'partCount'
            # entries) -- a literal field is considered covered as long as
            # SOME registry entry documents that exact key under any
            # namespace, since its scoped-telemetry-list validity is meant to
            # be explained in that entry's Description/RequestAs prose, not a
            # separate tag. This only flags a literal field with ZERO
            # registry entries at all -- true blind spots, not a namespace
            # mismatch.
            "missing_from_registry": sorted(literal_fields - reg_all_keys),
        },
    }
    clean = all(not v for section in sections.values() for v in section.values())
    return {"clean": clean, "sections": sections}


class RegistryAuditInput(BaseModel):
    pass


@mcp.tool(
    name="sfsprobe_registry_audit",
    annotations={
        "title": "Audit CommandRegistry/FieldRegistry for drift against real case blocks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_registry_audit(params: RegistryAuditInput) -> str:
    """Static drift check between SFSProbe.cs's CommandRegistry/FieldRegistry
    (what light_search's live/static-fallback paths present as ground truth)
    and the real case blocks/switches those registries are supposed to
    describe. Flags any command or field present in the code but missing a
    registry entry (a documentation gap -- a future caller would have to
    guess), and any registry entry with no matching code (stale, describes
    something removed). Pure source-file parsing -- no running game needed.

    Run this after adding a new command or telemetry field, per the
    project's standing convention: a new case block or switch entry must
    ship WITH a matching registry entry in the same change, not after.

    Returns: {"clean": bool, "sections": {section_name: {"missing_from_registry": [...],
    "stale_in_registry": [...]}}}. `clean` is true only if every section is
    empty in both directions.
    """
    report = await asyncio.to_thread(_run_registry_drift_audit, SFSPROBE_CS_PATH)
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------
# Tool: light_search -- MCP overhaul Checkpoint 2. Unified retrieval tool
# superseding the old sfsprobe_command_search/sfsprobe_telemetry_field_search
# tools (removed; their regex-parsing internals live on above as the
# fallback path). Prefers the live 'describe' registry (Checkpoint 1's
# CommandRegistry/FieldRegistry, dumped fresh by the mod itself -- correct
# by construction, including units, since it's read from the actual running
# game rather than parsed back out of source comments) and falls back to
# the regex parsers only when the game isn't reachable (not running, mod
# too old to have 'describe', a timeout). Every response says which path
# served it via "source": "live_registry" or "static_fallback", so a
# caller knows whether to trust it as authoritative or double-check.
#
# domain="doc" -- MCP overhaul Checkpoint 4. Chunks docs/sfs_physics_
# reference.md and docs/sfs_source_reference.md by Markdown heading (##/
# ###/####) so an agent can search physics/IL findings the same way it
# searches commands/fields, without reading either file (or knowing they
# exist) directly.
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r'^(#{2,4})\s+(.*\S)\s*$', re.MULTILINE)
_DOC_TAG_RE = re.compile(r'\[(CONFIRMED|PARTIAL|OPEN)[^\]]*\]')
_doc_chunk_cache: Dict[str, Any] = {"data": None, "ts": 0.0}


def _chunk_doc_file(path: Path) -> List[Dict[str, Any]]:
    """Split one Markdown doc into (heading, body) chunks. Each chunk runs
    from one ##/###/#### heading to the next heading of any level (flat
    split, not a nested tree -- simplest thing that lets a search match a
    specific subsection like '2.5 Aerodynamic torque' on its own, per the
    checkpoint's spec). `tags` pulls any [CONFIRMED]/[PARTIAL]/[OPEN]
    markers found in the heading line or the first 500 chars of the body,
    since that's where this project's docs put them."""
    text = path.read_text()
    headings = list(_HEADING_RE.finditer(text))
    chunks = []
    for i, m in enumerate(headings):
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        heading = m.group(2).strip()
        body = text[start:end].strip()
        tag_source = heading + " " + body[:500]
        tags = sorted(set(_DOC_TAG_RE.findall(tag_source)))
        chunks.append({
            "heading": heading,
            "level": len(m.group(1)),
            "body": body,
            "source_file": path.name,
            "tags": tags,
        })
    return chunks


async def _resolve_docs() -> List[Dict[str, Any]]:
    """Cached (DOC_CACHE_TTL_S) chunk index across every file in DOC_PATHS.
    A missing file is skipped, not fatal -- docs are supplementary, and a
    caller should still get commands/fields even if a doc got moved."""
    now = time.monotonic()
    if _doc_chunk_cache["data"] is not None and (now - _doc_chunk_cache["ts"]) < DOC_CACHE_TTL_S:
        return _doc_chunk_cache["data"]
    chunks: List[Dict[str, Any]] = []
    for path in DOC_PATHS:
        if not path.exists():
            continue
        try:
            chunks.extend(await asyncio.to_thread(_chunk_doc_file, path))
        except OSError as e:
            _log(f"_resolve_docs: failed to read {path}: {e}")
    _doc_chunk_cache["data"] = chunks
    _doc_chunk_cache["ts"] = now
    return chunks


# ---------------------------------------------------------------------------

_registry_cache: Dict[str, Any] = {"data": None, "ts": 0.0}


async def _get_registry() -> tuple[Optional[Dict[str, Any]], str]:
    """Fetch the live 'describe' registry, cached for REGISTRY_CACHE_TTL_S.
    Returns (registry_or_None, source) -- source is "live_registry" on
    success (cached or fresh) or "static_fallback" if the game/mod isn't
    reachable or returned something unparseable. Never raises -- every
    failure mode here is a legitimate, expected reason to fall back, not
    a bug to surface as an error."""
    now = time.monotonic()
    if _registry_cache["data"] is not None and (now - _registry_cache["ts"]) < REGISTRY_CACHE_TTL_S:
        return _registry_cache["data"], "live_registry"
    try:
        await asyncio.to_thread(send_command, "describe", DESCRIBE_TIMEOUT_S, DEFAULT_POLL_INTERVAL_S)
        data = json.loads(DESCRIBE_JSON_FILE.read_text())
    except (ProbeTimeoutError, FileNotFoundError, OSError, json.JSONDecodeError):
        return None, "static_fallback"
    _registry_cache["data"] = data
    _registry_cache["ts"] = now
    return data, "live_registry"


async def _resolve_commands() -> tuple[List[Dict[str, Any]], str]:
    """Shared command-list resolution: live 'describe' registry preferred
    (via _get_registry above), regex-parsed SFSProbe.cs fallback
    otherwise. Used by both light_search's command domain and the
    fast-fail validator (Checkpoint 3, below) so the two can never
    disagree about what counts as a valid command. A fallback-parse
    OSError degrades to an empty list rather than raising -- callers
    (search: shows total_commands=0; validator: fails open, see
    _validate_command_line) treat 'couldn't resolve anything' as a
    known, handleable state, not a crash."""
    registry, source = await _get_registry()
    if registry is not None:
        return registry.get("commands", []), source
    if not SFSPROBE_CS_PATH.exists():
        return [], "static_fallback"
    try:
        raw = await asyncio.to_thread(_parse_probe_commands, SFSPROBE_CS_PATH)
    except OSError as e:
        _log(f"_resolve_commands: fallback parse failed: {e}")
        return [], "static_fallback"
    commands = [
        {
            "name": c["command"], "description": c["description"],
            "inline_body": c["inline_body"], "source_line": c["source_line"],
        }
        for c in raw
    ]
    return commands, "static_fallback"


# ---------------------------------------------------------------------------
# Fast-fail command validation -- MCP overhaul Checkpoint 3. Checks a
# command's leading word against the known command set (via
# _resolve_commands above) BEFORE it's ever written to command.txt, so a
# typo like 'telemetry snapshot' (the real command is 'telemetrysnapshot',
# one word) fails in milliseconds with a suggestion instead of burning a
# multi-second send_command timeout waiting for a result.txt line that,
# because the mod's own `default:` case in Command() DOES still write
# 'unknown command: ...' to result.txt, would actually have arrived --
# but only after the same adaptive-poll wait as a real command, and only
# distinguishable from a real response by reading the text. This check
# short-circuits before any of that.
# ---------------------------------------------------------------------------

async def _validate_command_line(cmd_line: str) -> Optional[Dict[str, Any]]:
    """Returns None if cmd_line's leading word is a known command (or if
    command-name resolution itself came up empty -- fails OPEN, not
    closed: an unresolvable command set must never silently block a real
    command from being sent). Otherwise returns an error-response dict
    with close-match suggestions, no game round-trip spent."""
    leading = cmd_line.strip().split(" ", 1)[0].lower()
    if not leading:
        return None
    commands, source = await _resolve_commands()
    known = {c["name"].lower() for c in commands if c.get("name")}
    if not known or leading in known:
        return None
    close = difflib.get_close_matches(leading, sorted(known), n=3, cutoff=0.5)
    suggestion = f" Did you mean: {', '.join(close)}?" if close else ""
    return {
        "error_code": "UNKNOWN_COMMAND",
        "error": f"'{leading}' is not a known sfsprobe command.{suggestion}",
        "command": cmd_line,
        "suggestions": close,
        "source": source,
        "timed_out": False,
    }


class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        default="",
        max_length=200,
        description=(
            "Keyword(s) to search for, e.g. 'telemetry', 'parachute', "
            "'gimbal throttle', 'part count'. Leave empty to list "
            "everything in the selected domain(s)."
        ),
    )
    domain: Literal["command", "field", "doc", "all"] = Field(
        default="all",
        description=(
            "'command': command.txt commands (name/syntax/description/category). "
            "'field': telemetry field/parameter names across all namespaces "
            "(script-condition/computed/truth/inputs when live; a broader "
            "regex-parsed set when falling back). 'doc': physics/source "
            "reference docs (docs/sfs_physics_reference.md, docs/"
            "sfs_source_reference.md), chunked by Markdown heading. "
            "'all': every domain at once."
        ),
    )
    top_k: int = Field(default=10, ge=1, le=50)


@mcp.tool(
    name="light_search",
    annotations={
        "title": "Search sfsprobe commands/fields/docs (live registry preferred, source-parsed fallback)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def light_search(params: SearchInput) -> str:
    """Search sfsprobe's real commands, telemetry fields, and (eventually)
    reference docs by keyword, instead of guessing syntax or field
    semantics from memory -- the tool that exists because of real
    mistakes made without it: sending 'telemetry snapshot' (not a real
    command; the real one is 'telemetrysnapshot'), requesting bare
    'gimbalThrottleOut' (an OUTPUT key, not a request name -- the real
    request is 'computed:gimbal'), and misreading 'parachuteAlphaDeg' as
    an angle in degrees when it's actually an angular ACCELERATION in
    deg/s^2.

    Tries the live 'describe' command first -- the mod's own
    CommandRegistry/FieldRegistry, correct by construction because it's
    read out of the actual running game, including each field's real
    unit. Falls back to parsing SFSProbe.cs's source directly (regex over
    the Command()/AppendComputedField/GetScriptFieldValue/Sample()
    switches) only when the game isn't reachable. Every response's
    "source" field says which path actually served it.

    Args:
        params (SearchInput): query, domain, top_k

    Returns:
        str: JSON with keys: query, domain, source ("live_registry" or
        "static_fallback"), and, per requested domain: commands/
        total_commands, fields/total_fields, docs/total_docs (docs are
        chunked docs/sfs_physics_reference.md + docs/sfs_source_
        reference.md sections, each carrying heading/body/source_file/tags).
    """
    registry, source = await _get_registry()
    terms = [t.lower() for t in params.query.split() if t.strip()]
    result: Dict[str, Any] = {"query": params.query, "domain": params.domain, "source": source}

    if params.domain in ("command", "all"):
        commands, _cmd_source = await _resolve_commands()
        result["total_commands"] = len(commands)
        result["commands"] = _score_items(terms, commands, "name", params.top_k)

    if params.domain in ("field", "all"):
        if registry is not None:
            fields = registry.get("fields", [])
        elif SFSPROBE_CS_PATH.exists():
            try:
                raw = await asyncio.to_thread(_build_field_index, SFSPROBE_CS_PATH)
            except OSError as e:
                return _error_for_exception(e)
            fields = [_normalize_fallback_field(e) for e in raw]
        else:
            fields = []
        result["total_fields"] = len(fields)
        result["fields"] = _score_items(terms, fields, "key", params.top_k)

    if params.domain in ("doc", "all"):
        docs = await _resolve_docs()
        result["total_docs"] = len(docs)
        result["docs"] = _score_items(terms, docs, "heading", params.top_k)

    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: deep_search -- MCP overhaul Checkpoint 5. light_search's "doc" domain
# is only as good as hand-written prose that can drift from ground truth
# (this project has already found a doc chunk containing its own
# `> **CORRECTION**` annotation). deep_search goes straight to the real
# decompiled game IL via `monodis` instead of a summary of it, for when
# light_search's doc coverage is missing or untrustworthy for a given
# question.
#
# IL HAS NO COMMENTS OR TAGS -- decompilation strips them entirely. Unlike
# light_search's doc domain (human prose plus [CONFIRMED]/[PARTIAL]/[OPEN]
# tags), deep_search can only ever match identifiers: type/method/field
# names. A query like "gimbal" needs to hit EngineModule's `gimbal` FIELD
# or its `RecalculateGimbal` METHOD -- not the type name "EngineModule",
# which doesn't contain "gimbal" at all. So this is a two-LEVEL index, not
# a single type-name lookup:
#   1. Type-level -- reused as-is from analysis/il_inventory.py (already
#      built for the docs/sfs_reference/ migration's own inventory), via
#      `il_inventory.parse_il()`.
#   2. Member-level (the real gap) -- `parse_il(capture_members=True)`
#      also collects each type's real method/field names, not just
#      counts, into that same per-type record.
# A query tries type names first, then falls through to member names
# across every type, surfacing which type(s) contain a matching member.
#
# Consequence worth documenting everywhere this tool is described: this
# makes deep_search far less forgiving of open-ended conceptual queries
# than light_search's doc domain. "why does thrust respond instantly with
# no ramp" hits nothing here -- no such literal identifiers exist -- but
# works fine against doc prose. deep_search is for "I roughly know the
# type/method/field name and want ground truth over a doc's prose," not
# "explain this concept" -- that job stays with light_search.
# ---------------------------------------------------------------------------

_CLASS_NESTED_RE = re.compile(r'^  \.class .*nested')
_member_inventory_cache: Dict[str, Any] = {"data": None, "mtime": None}


def _assembly_mtime() -> Optional[float]:
    try:
        return ASSEMBLY_PATH.stat().st_mtime
    except OSError:
        return None


def _run_monodis(args: List[str]) -> str:
    """Runs monodis, raising RuntimeError with its stderr on failure --
    never lets a subprocess error surface as an unhandled exception to an
    MCP caller."""
    try:
        proc = subprocess.run(
            [MONODIS_BIN, *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"could not run monodis ({MONODIS_BIN}): {e}") from e
    if proc.returncode != 0:
        raise RuntimeError(f"monodis exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


async def _get_member_inventory() -> List[Dict[str, Any]]:
    """Cached (keyed on the cached IL dump's mtime, so a rebuilt/updated
    assembly invalidates it automatically) two-level type+member inventory
    via `il_inventory.parse_il(capture_members=True)` against deep_search's
    own IL cache (never scratch/full_il.txt -- see DEEP_SEARCH_CACHE_DIR's
    comment). `il_inventory.is_compiler_generated` filters out closures/
    display classes/etc, same as that module's own CLI path does."""
    il_path = await _ensure_il_dump()
    mtime = await asyncio.to_thread(lambda: il_path.stat().st_mtime)
    if _member_inventory_cache["data"] is not None and _member_inventory_cache["mtime"] == mtime:
        return _member_inventory_cache["data"]
    types = await asyncio.to_thread(il_inventory.parse_il, str(il_path), True)
    real = [t for t in types if not il_inventory.is_compiler_generated(t)]
    _member_inventory_cache["data"] = real
    _member_inventory_cache["mtime"] = mtime
    return real


def _name_score(name_l: str, term: str) -> int:
    if name_l == term:
        return 100
    if name_l.startswith(term):
        return 60
    if term in name_l:
        return 30
    return 0


def _score_deep_matches(query: str, types: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Two-level identifier match (see the module comment above for why:
    IL has no prose to match against). Tries each type's own name first
    (exact/prefix/substring, then a tightened fuzzy fallback -- ratio
    >0.7 only, since 0.6 let unrelated short names like 'Part'/'PartHit'
    leak into a 'parachute' query at ratio ~0.62), then falls through to
    every method/field name across all types. Returns each matched type
    with `matched_via` ("type name" or "member name") and the specific
    `matched_members` list, so a caller can see *why* a type came back --
    important here since, unlike a doc chunk, an IL class summary doesn't
    explain itself.

    Multi-word queries use AND, not OR, across a single candidate name --
    e.g. a member must contain every term to count as a match. This is
    deliberate, not an optimization: without it, a conceptual sentence like
    "why does thrust ramp up slowly" would independently match any field
    named `thrust` and any field/method literally named `up`, returning
    noise that makes deep_search look like it (partially) answers
    conceptual questions when it fundamentally cannot -- IL has no
    identifier for "why" or "slowly" to fail to match against, only
    unrelated real names that happen to share a common short word. No
    single real identifier contains every term of an unrelated sentence,
    so AND naturally yields zero matches for that class of query while
    still matching legitimate multi-word identifier lookups."""
    terms = [t.lower() for t in query.split() if t.strip()]
    if not terms:
        return [{"type": t, "matched_via": "listing", "matched_members": []} for t in types[:top_k]]

    def name_matches_all(name_l: str) -> int:
        """AND across terms: every term must score >0 against name_l (each
        independently, e.g. exact/prefix/substring or a >0.7 fuzzy ratio
        for a single-term query only -- fuzzy typo-correction doesn't
        generalize to multi-term AND). Returns the summed per-term score,
        or 0 if any term fails to match at all."""
        total = 0
        for term in terms:
            s = _name_score(name_l, term)
            if s == 0 and len(terms) == 1:
                ratio = difflib.SequenceMatcher(None, term, name_l).ratio()
                s = int(ratio * 15) if ratio > 0.7 else 0
            if s == 0:
                return 0
            total += s
        return total

    scored = []
    for t in types:
        name_l = t["name"].lower()
        best, via = 0, None
        s = name_matches_all(name_l)
        if s > best:
            best, via = s, "type name"

        matched_members = []
        for kind, names in (("method", t.get("method_names") or []), ("field", t.get("field_names") or [])):
            for member in names:
                member_short = member.rsplit(".", 1)[-1].lower()
                member_score = name_matches_all(member_short)
                if member_score > 0:
                    matched_members.append({"kind": kind, "name": member, "score": member_score})
        if matched_members:
            matched_members.sort(key=lambda m: -m["score"])
            top_member_score = matched_members[0]["score"]
            if top_member_score > best:
                best, via = top_member_score, "member name"

        if best > 0:
            scored.append((best, t, via, matched_members[:10]))

    scored.sort(key=lambda x: -x[0])
    return [{"type": t, "matched_via": via, "matched_members": members} for _, t, via, members in scored[:top_k]]


async def _ensure_il_dump() -> Path:
    """Ensures a full `monodis` IL dump of ASSEMBLY_PATH exists at
    DEEP_SEARCH_IL_CACHE, re-dumping only if missing or the assembly's
    mtime has changed since the last dump (~0.3s for the real ~290k-line
    assembly -- worth caching, but cheap enough not to be precious about).
    Never touches scratch/full_il.txt -- see the module-level comment on
    DEEP_SEARCH_CACHE_DIR."""
    mtime = await asyncio.to_thread(_assembly_mtime)
    meta = None
    if DEEP_SEARCH_IL_META.exists():
        try:
            meta = json.loads(DEEP_SEARCH_IL_META.read_text())
        except (OSError, json.JSONDecodeError):
            meta = None
    if meta and meta.get("assembly_mtime") == mtime and DEEP_SEARCH_IL_CACHE.exists():
        return DEEP_SEARCH_IL_CACHE
    await asyncio.to_thread(DEEP_SEARCH_CACHE_DIR.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        _run_monodis, [f"--output={DEEP_SEARCH_IL_CACHE}", str(ASSEMBLY_PATH)]
    )
    await asyncio.to_thread(
        DEEP_SEARCH_IL_META.write_text,
        json.dumps({"assembly_mtime": mtime, "assembly_path": str(ASSEMBLY_PATH)}),
    )
    return DEEP_SEARCH_IL_CACHE


def _extract_class_summary(il_lines: List[str], short_name: str) -> Optional[Dict[str, Any]]:
    """Ports this project's manual `sig.sh` extraction convention (see
    docs/sfs_source_reference.md §A2) to Python: finds short_name's
    top-level `.class` line, then walks forward collecting field
    declarations and flattened method signatures (declaration spans two
    lines in monodis output -- gotcha #1 in that doc) until either the
    class's own closing brace or the first NESTED type, whichever comes
    first (gotcha #2 -- without this a closure/nested-interface type's
    members get misattributed to the outer class, a real false positive
    this project hit twice during manual research)."""
    class_re = re.compile(r'^  \.class .*[ .]' + re.escape(short_name) + r'$')
    start = next((i for i, l in enumerate(il_lines) if class_re.match(l.rstrip('\n'))), None)
    if start is None:
        return None
    out_lines = [f"CLASS@{start + 1}: {il_lines[start].strip()}"]
    end = len(il_lines) - 1
    truncated_nested = False
    i = start + 1
    while i < len(il_lines):
        stripped = il_lines[i].rstrip('\n')
        if stripped.startswith('  } // end of class'):
            end = i
            break
        if _CLASS_NESTED_RE.match(stripped):
            end = i - 1
            truncated_nested = True
            break
        if stripped.startswith('    .field'):
            out_lines.append(f"  FIELD: {stripped.strip()}")
        elif stripped.startswith('    .method'):
            sig_parts = [stripped.strip()]
            j = i + 1
            while j < len(il_lines) and j < i + 5:
                sig_parts.append(il_lines[j].strip())
                if ')' in il_lines[j]:
                    break
                j += 1
            sig = re.sub(r'\s+', ' ', ' '.join(sig_parts))
            out_lines.append(f"  METHOD@{i + 1}: {sig}")
        i += 1
    if truncated_nested:
        out_lines.append("  [truncated at first nested type -- nested members NOT shown]")
    return {"start_line": start + 1, "end_line": end + 1, "lines": out_lines}


class DeepSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "A type, method, or field name (exact or partial) -- an "
            "IDENTIFIER, e.g. 'EngineModule', 'gimbal', 'RecalculateGimbal'. "
            "deep_search matches real names in the decompiled assembly only "
            "(no prose/comments survive decompilation) -- it will NOT answer "
            "a conceptual question like 'why does thrust ramp up slowly' "
            "(use light_search's domain=\"doc\" for that instead)."
        ),
    )
    top_k: int = Field(default=3, ge=1, le=10, description="How many matched types to extract.")


@mcp.tool(
    name="deep_search",
    annotations={
        "title": "Search real decompiled game IL by type/method/field name (ground truth, no doc summary)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def deep_search(params: DeepSearchInput) -> str:
    """Look up a type, method, or field directly in the real decompiled
    game assembly via `monodis`, bypassing light_search's doc summaries
    entirely. Use this when light_search's `domain="doc"` doesn't cover
    something, or when a doc chunk's prose shouldn't be trusted over
    ground truth (this project has already found a doc chunk carrying its
    own correction annotation).

    IMPORTANT SCOPE LIMIT: decompiled IL has no comments or tags at all --
    it can only ever be matched by identifier (type/method/field name),
    never by concept or description. A query like "gimbal" matches
    EngineModule's `gimbal` field or a `RecalculateGimbal` method; a query
    like "why does thrust ramp up slowly" matches nothing here, because no
    such literal identifier exists, even though light_search's doc domain
    answers it fine from prose. Use deep_search when you roughly know the
    type/method/field name and want ground truth over a doc's summary of
    it -- not for open-ended "explain this" questions.

    Two-level index, reusing analysis/il_inventory.py's own type parser
    (built for the docs/sfs_reference/ migration) rather than
    reimplementing it: type names are tried first, then every method/field
    name across all types, since a query term is frequently a *member*
    name, not the type name itself. For each matched type, fields and
    method signatures are then extracted from a cached full IL dump using
    this project's established `sig.sh` extraction convention
    (docs/sfs_source_reference.md §A2) -- real field names/types and
    flattened method signatures, not full method bodies (which would be
    huge) and not a paraphrase.

    Args:
        params (DeepSearchInput): query, top_k

    Returns:
        str: JSON with keys: query, source ("monodis_live"), assembly
        (path), matches (list of {type_name, matched_via ("type name" or
        "member name"), matched_members, found_in_il, il_lines,
        line_range, truncated, note}). A `note` explains where to find
        more in the cache file when a class summary was too long to
        return in full.
    """
    if not ASSEMBLY_PATH.exists():
        return json.dumps({
            "error_code": "ASSEMBLY_NOT_FOUND",
            "error": f"Assembly not found at {ASSEMBLY_PATH}. Override with SFSPROBE_ASSEMBLY_PATH.",
        }, indent=2)
    try:
        types = await _get_member_inventory()
    except RuntimeError as e:
        return json.dumps({"error_code": "MONODIS_FAILED", "error": str(e)}, indent=2)

    matches = _score_deep_matches(params.query, types, params.top_k)
    if not matches:
        return json.dumps({
            "query": params.query,
            "source": "monodis_live",
            "matches": [],
            "note": (
                "No type, method, or field name matched. deep_search only "
                "matches real identifiers in the decompiled assembly, never "
                "concepts or prose -- try light_search's domain=\"doc\" for "
                "a conceptual question, or broaden/correct the identifier."
            ),
        }, indent=2)

    il_path = DEEP_SEARCH_IL_CACHE
    il_text = await asyncio.to_thread(il_path.read_text)
    il_lines = il_text.splitlines()

    results = []
    for m in matches:
        t = m["type"]
        summary = _extract_class_summary(il_lines, t["name"])
        if summary is None:
            results.append({
                "type_name": t["fq"], "matched_via": m["matched_via"],
                "matched_members": m["matched_members"], "found_in_il": False,
            })
            continue
        body_lines = summary["lines"]
        too_long = len(body_lines) > DEEP_SEARCH_MAX_LINES
        results.append({
            "type_name": t["fq"],
            "matched_via": m["matched_via"],
            "matched_members": m["matched_members"],
            "found_in_il": True,
            "il_lines": body_lines[:DEEP_SEARCH_MAX_LINES],
            "line_range": [summary["start_line"], summary["end_line"]],
            "truncated": too_long,
            "note": (
                f"Full extraction has {len(body_lines)} lines; showing first "
                f"{DEEP_SEARCH_MAX_LINES}. Real IL spans lines "
                f"{summary['start_line']}-{summary['end_line']} in the cached "
                f"dump at {DEEP_SEARCH_IL_CACHE}."
            ) if too_long else None,
        })

    return json.dumps({
        "query": params.query,
        "source": "monodis_live",
        "assembly": str(ASSEMBLY_PATH),
        "matches": results,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: onboarding -- MCP overhaul Checkpoint 6. A single orientation tool
# for an AI with zero prior context on this project. Deliberately short --
# the point is to point at light_search/deep_search, not to duplicate their
# content. Implemented as a @mcp.tool rather than an @mcp.resource: every
# other capability on this server is a tool, and a tool is guaranteed to
# show up in a caller's tool list and be callable proactively, whereas
# resource support/visibility varies by MCP client -- consistency and
# reachability won over resources' template-URI mechanism, which buys
# nothing here since there are no parameters.
# ---------------------------------------------------------------------------

class OnboardingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


_ONBOARDING_TEXT = """\
sfsprobe_mcp orientation -- read this first if you have no prior context.

WHAT THIS IS
sfsprobe_mcp lets you control and observe a live run of Spaceflight
Simulator (SFS) through a C# mod ("sfsprobe") running inside the game.
Under the hood, commands are written to command.txt, the mod polls for
it and executes it, then appends a result line to result.txt -- but you
never touch those files directly; every tool here already wraps that
round-trip in adaptive polling. This detail only matters for reading
error messages (e.g. a FILE_NOT_FOUND means the mod isn't running or
its working directory is misconfigured, not that you did anything wrong).

STANDING INSTRUCTION: SEARCH BEFORE YOU GUESS
Never guess a command name, a telemetry field name, or its unit. Call
light_search first, every time, before sending a command or requesting
a field you haven't confirmed. Guessing has caused real bugs in this
project's history (e.g. treating an angular-acceleration field as if it
were a plain angle because its name looked like one).

light_search vs. deep_search -- which to reach for:
- light_search(query, domain, top_k): your default. Fast, live-registry
  backed when the game is running (falls back to static parsing of the
  mod source otherwise -- check the "source" field in its response to
  see which). domain="command" for command syntax, domain="field" for
  telemetry field names + units, domain="doc" for physics/design docs,
  domain="all" for everything at once. Use this for "how do I..." and
  "what does X mean" questions -- it also covers open-ended conceptual
  queries doc prose can answer, which deep_search cannot.
- deep_search(query, top_k): a slower fallback for when light_search's
  doc coverage is missing something, or you don't trust a doc chunk's
  prose over ground truth. It reads the real decompiled game assembly
  (via monodis) instead of hand-written docs, so it can only match real
  identifiers (a type, method, or field name) -- not paraphrased
  concepts. Use it when you roughly know the name of the thing you're
  looking for but doc prose doesn't cover it or might be stale.

ERROR CODES YOU MAY SEE
- TIMEOUT: the mod didn't respond in time -- usually means the game is
  not running, is paused on a loading screen, or the command silently
  requires state that doesn't exist yet (e.g. no active rocket).
- FILE_NOT_FOUND: the command/result file pair isn't where expected --
  the mod isn't running or SFSPROBE_MOD_DIR points somewhere wrong.
- INVALID_PARAM: a tool argument failed validation before anything was
  sent to the game at all.
- UNKNOWN_COMMAND: the leading word of a command didn't match any known
  command (checked BEFORE any game round-trip, so this fails in
  milliseconds, not after a timeout) -- the response includes the
  closest real match(es), so check those before retrying.
- UNKNOWN_ERROR: an exception occurred that isn't one of the above --
  check the accompanying message text.
- ASSEMBLY_NOT_FOUND / MONODIS_FAILED: deep_search-specific -- the game
  assembly path is wrong, or monodis itself failed to run.
- NO_ACTIVE_ROCKET: a command needs a rocket to exist and none does.
- PARSE_ERROR / MISSING_FIELD: a downstream analysis tool (flight-log
  parsing, field lookups) couldn't find or parse what you asked for.
- WAIT_TIMEOUT: NOT the same thing as TIMEOUT above, and easy to
  confuse with it. This is a "warning_code" (not "error_code") emitted
  by a flight-script wait-for-condition step -- it means the condition
  you told the script to wait for (e.g. an altitude or velocity
  threshold) never became true before that step's own timeout elapsed.
  Nothing failed to respond; the script kept running and simply moved
  on. A handful of other tool-specific codes exist too (e.g.
  NOT_IN_BUILD/NOT_IN_WORLD/SPAWN_FAILED on sfsprobe_load_blueprint,
  NO_NEW_ARCHIVE/NO_SAMPLES on flight-analysis tools) -- those are
  documented in each tool's own description rather than repeated here.

THE FOUR TELEMETRY FIELD NAMESPACES -- these are NOT interchangeable
1. computed_group: a "computed:NAME" group you REQUEST (e.g.
   "computed:parachuteDrag") to make the mod compute and return a set
   of related values.
2. computed_output_key: a field WRITTEN by a computed_group (e.g.
   parachuteDrag's group writes fields that are NOT literally named
   "parachuteDrag"). An output key is never itself a valid thing to
   request -- you request the group, you read its output keys.
3. script_condition_field: short-name aliases valid only inside
   SCRIPT/TRIGGER condition strings (e.g. autostop rules). NOT valid in
   a "telemetry on <fields>" list.
4. literal_telemetry_field: bare names valid DIRECTLY in a
   "telemetry on <fields>" list (special-cased in the mod's Sample()).
(Separately, the live "describe" registry also tags plain state fields
with a "truth"/"inputs" namespace -- those are full-mode-only fields
read straight off game state, not derived through a computed group or
script condition. Don't confuse that registry tag with the four
namespaces above; light_search(query, domain="field") returns each
match's real kind/namespace so you don't have to guess.)
"""


@mcp.tool(
    name="sfsprobe_onboarding",
    annotations={
        "title": "Orientation for a new AI/agent session",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sfsprobe_onboarding(params: OnboardingInput) -> str:
    """Zero-context orientation: what this MCP is, what its error codes
    mean, the four telemetry field namespaces, and when to use
    light_search vs. deep_search. Call this once at the start of a
    session if you have no prior context on this project.

    Args:
        params (OnboardingInput): no fields, takes no arguments.

    Returns:
        str: plain-text orientation guide (not JSON -- meant to be read,
        not parsed).
    """
    return _ONBOARDING_TEXT


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

    Fast-fails the ENTIRE batch (MCP overhaul Checkpoint 3) if ANY command's
    leading word isn't known -- no commands in the batch are sent, not even
    the valid ones, since a typo'd step partway through a launch sequence
    (e.g. 'ignit' instead of 'ignite') is exactly the kind of mistake worth
    catching before anything fires. Skipped entirely (fails open) if the
    command set itself can't be resolved.

    Args:
        params (SendBatchInput): commands, timeout_s, poll_interval_s

    Returns:
        str: JSON with keys: results (array, one entry per command, in
        order: command, result [string or null], silent [bool, true for
        world/menu]), complete (bool -- true if every non-silent command
        got a confirmed result before timeout; false means check results
        for which ones are still null, partial results are NOT discarded
        on timeout), elapsed_seconds. On a fast-fail: error_code
        'UNKNOWN_COMMAND', error, invalid (array of {command, suggestions}),
        source -- no commands were sent.
    """
    commands_registry, cmd_source = await _resolve_commands()
    known = {c["name"].lower() for c in commands_registry if c.get("name")}
    if known:
        invalid = []
        for cmd in params.commands:
            leading = cmd.strip().split(" ", 1)[0].lower()
            if leading and leading not in known:
                close = difflib.get_close_matches(leading, sorted(known), n=3, cutoff=0.5)
                invalid.append({"command": cmd, "suggestions": close})
        if invalid:
            return json.dumps({
                "error_code": "UNKNOWN_COMMAND",
                "error": f"{len(invalid)} of {len(params.commands)} command(s) in this batch aren't "
                         "known sfsprobe commands -- no commands were sent.",
                "invalid": invalid,
                "source": cmd_source,
            }, indent=2)

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
# Tool: tail probe.log / sample.jsonl / rocketstate.jsonl -- read-only, sends NO
# command at all. New capability: inspect recent activity or telemetry
# samples without triggering anything in the game.
# ---------------------------------------------------------------------------

class TailFileTarget(str, Enum):
    PROBE_LOG = "probe_log"
    SAMPLE = "sample"
    PARTS = "parts"


class TailFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: TailFileTarget = Field(
        ...,
        description="Which live file to tail: 'probe_log' (probe.log, human-"
                     "readable events), 'sample' (sample.jsonl, per-tick physics "
                     "telemetry + control signals merged into one record -- v0.60.0, "
                     "was 'truth'/'inputs' as two separate targets before the truth/inputs "
                     "file split was removed), or 'parts' (rocketstate.jsonl, the "
                     "independent ~1Hz per-part structural snapshot recorder -- 'telemetry "
                     "json on', a separate lifecycle from 'sample').",
    )
    lines: int = Field(default=20, ge=1, le=1000, description="Number of most recent lines to return.")
    parse_json: bool = Field(
        default=False,
        description="For 'sample'/'parts': parse each line as JSON and return "
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
    recent telemetry samples (sample/parts) without disturbing a running
    flight or recording.

    Args:
        params (TailFileInput): target, lines, parse_json

    Returns:
        str: JSON with keys: target, path, line_count (lines actually
        found, may be less than requested), lines (array of strings, or
        array of parsed objects if parse_json and target is sample/parts),
        parse_errors (int, only present if parse_json hit malformed lines).
    """
    path = {
        TailFileTarget.PROBE_LOG: PROBE_LOG_FILE,
        TailFileTarget.SAMPLE: SAMPLE_FILE,
        TailFileTarget.PARTS: ROCKETSTATE_FILE,
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
# archived flight, or the live sample.jsonl if none given. Used by every
# analysis tool below (Stages 1-7).
# ---------------------------------------------------------------------------

def _resolve_flight_path(path: Optional[str]) -> Path:
    if path:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"telemetry file not found: {p}")
        return p
    if not SAMPLE_FILE.exists():
        raise FileNotFoundError(
            f"no path given and no live sample.jsonl found at {SAMPLE_FILE} -- "
            "either pass an archived flight's path, or start telemetry recording first."
        )
    return SAMPLE_FILE


# ===========================================================================
# STAGE 1 -- core stats & search
# ===========================================================================

class FieldStatsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: List[str] = Field(..., min_length=1, description="Telemetry field names, e.g. ['h','vv','dragArea'].")
    path: Optional[str] = Field(default=None, description="Archived flight file. Omit to use the live sample.jsonl.")
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
    scope: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Restrict the search to a portion of the flight, same forms as sfsprobe_field_stats: "
                     "{'phase':'ascent'}, {'time_range':[t1,t2]}, {'before_event':'impact','window_s':10}, "
                     "{'after_event':'engine_cutoff'}, {'around_event':'apoapsis','window_s':5}. "
                     "Omit to search the whole flight.",
    )


@mcp.tool(name="sfsprobe_field_search", annotations={"title": "Find samples matching a field condition",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_field_search(params: FieldSearchInput) -> str:
    """Find all samples where field <op> value holds, e.g. h > 10000 or
    vv < 0. Returns matching indices/times/values instead of requiring a
    manual scroll through raw telemetry. Optionally scoped to a phase/
    time-range/event-window, same as sfsprobe_field_stats -- e.g. "find
    engine cutoffs only during ascent" without a separate phase_detect
    call plus manual index intersection.

    Args:
        params (FieldSearchInput): field, op, value, path, limit, scope

    Returns:
        str: JSON with keys: path, scope_applied, scoped_range,
        match_count, matches (capped at limit).
    """
    try:
        path = _resolve_flight_path(params.path)
        samples = await asyncio.to_thread(st.load_samples, path)
        start, end, warning = st.resolve_scope(samples, params.scope)
        matches = st.search_field(samples, params.field, params.op, params.value,
                                   start=start, end=end + 1, limit=params.limit)
        result = {"path": str(path), "scope_applied": params.scope, "scoped_range": [start, end],
                  "match_count": len(matches), "matches": matches}
        if warning:
            result["warnings"] = [warning]
        return json.dumps(result, indent=2)
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


def _copy_to_kept(path: Path) -> Path:
    """Copies an archived flight into archive/kept/ -- the only thing that
    survives SFSProbe.cs's DeletePreviousArchive, which wipes the prior
    .gz for a mode (flat/parts) the instant the NEXT same-mode recording
    starts (v0.60.0's unified archive lifecycle: new runs overwrite
    previous results by design). Called by sfsprobe_tag_flight before
    logging, so a tag always points at something durable, not a file that
    might vanish the next time someone hits 'telemetry on'.

    A no-op copy (returns path unchanged) if the file is already under
    kept/ -- e.g. re-tagging, or an explicit path someone already rescued
    by hand.
    """
    if KEPT_DIR in path.resolve().parents:
        return path
    KEPT_DIR.mkdir(parents=True, exist_ok=True)
    dest = KEPT_DIR / path.name
    shutil.copy2(path, dest)
    return dest


class ListFlightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=20, ge=1, le=500)
    tag_substring: Optional[str] = Field(
        default=None,
        description="Case-insensitive filter on the tag field, e.g. 'drag_validation' -- applied before limit.",
    )
    mode: Optional[Literal["flat", "parts"]] = Field(
        default=None,
        description="Filter to only flights recorded in this telemetry mode ('flat' = normal per-tick physics "
                     "telemetry, 'parts' = the ~1Hz per-part structural recorder). Omit for either.",
    )


@mcp.tool(name="sfsprobe_list_flights", annotations={"title": "List logged/archived flights",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_list_flights(params: ListFlightsInput) -> str:
    """List flights that have been explicitly tagged (via sfsprobe_tag_flight
    or sfsprobe_run_and_analyze), newest first, plus a count of untagged
    files sitting in the archive folder. Without this, results only ever
    live in chat history and evaporate between sessions.

    Args:
        params (ListFlightsInput): limit, tag_substring, mode

    Returns:
        str: JSON with 'tagged_flights' (newest first, filtered, capped
        at limit) and 'untagged_archive_count' (unaffected by
        tag_substring/mode -- always the whole archive's untagged count).
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
    if params.tag_substring:
        needle = params.tag_substring.lower()
        tagged = [e for e in tagged if needle in (e.get("tag") or "").lower()]
    if params.mode:
        mode_marker = "telemetry_" + params.mode + "_"
        tagged = [e for e in tagged if mode_marker in (e.get("file") or "")]
    tagged.sort(key=lambda e: e.get("logged_at", 0), reverse=True)
    tagged_files = {e["file"] for e in tagged}
    untagged_count = 0
    if ARCHIVE_DIR.exists():
        # v0.60.0: archive naming is now telemetry_<mode>_<timestamp>.jsonl.gz
        # (mode is 'flat' or 'parts'), not the old flightNN_truth_*.jsonl --
        # glob only the top-level dir so kept/ (already-tagged, durable
        # copies) is never double-counted as "untagged".
        for f in ARCHIVE_DIR.glob("telemetry_*_*.jsonl.gz"):
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

    v0.60.0: FIRST copies the file into archive/kept/ (unless it's already
    there) -- the unified archive lifecycle deletes the previous .gz for a
    mode the instant the next same-mode recording starts, so tagging a
    file in place would let it get silently deleted later. The logged
    path always points at the durable kept/ copy, never the original
    transient archive location.

    Args:
        params (TagFlightInput): path, tag, notes

    Returns:
        str: JSON confirming what was logged, including whether a copy
        into archive/kept/ was made (kept_path, copied bool).
    """
    try:
        path = _resolve_flight_path(params.path)
        kept_path = await asyncio.to_thread(_copy_to_kept, path)
        samples = await asyncio.to_thread(st.load_samples, kept_path)
        summary = st.flight_summary(samples)
        await asyncio.to_thread(_append_flight_log, kept_path, params.tag, params.notes, summary)
        return json.dumps({"logged": True, "path": str(kept_path), "original_path": str(path),
                            "copied": kept_path != path, "tag": params.tag,
                            "flights_log_file": str(FLIGHTS_LOG_FILE)}, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class PartsTimelineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Optional[str] = Field(
        default=None,
        description="Archived parts-mode ('telemetry json') flight file (a telemetry_parts_*.jsonl.gz "
                     "archive, or a kept/ copy). Omit to use the live rocketstate.jsonl.",
    )
    name_substring: Optional[str] = Field(
        default=None,
        description="Case-insensitive filter on part name, e.g. 'Fuel Tank' -- applied BEFORE tracking, "
                     "so vanished_parts/most_resource_lost only reflect matching parts.",
    )


@mcp.tool(name="sfsprobe_parts_timeline", annotations={"title": "Track per-part state across a parts-mode recording",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_parts_timeline(params: PartsTimelineInput) -> str:
    """Tracks every part across a 'telemetry json' (parts-mode) recording's
    snapshots -- answers what the flat per-tick telemetry can't: which
    specific fuel tank lost the most resourcePercent, and which parts
    vanished (destroyed or staged away) partway through the flight. The
    schema has no explicit 'broken' flag -- disappearing from a later
    snapshot IS the signal, so this tool does that diffing for you.

    Args:
        params (PartsTimelineInput): path, name_substring

    Returns:
        str: JSON with path, sample_count, part_count_tracked, parts
        (every tracked part's first/last seen values), vanished_parts
        (subset that disappeared before the recording's final sample),
        most_resource_lost (top 10 by resourcePercent drop, resource-
        bearing parts only).
    """
    try:
        if params.path:
            p = Path(params.path).expanduser()
            if not p.exists():
                raise FileNotFoundError(f"telemetry file not found: {p}")
        else:
            if not ROCKETSTATE_FILE.exists():
                raise FileNotFoundError(
                    f"no path given and no live rocketstate.jsonl found at {ROCKETSTATE_FILE} -- "
                    "either pass an archived parts-mode flight's path, or start 'telemetry json on' first."
                )
            p = ROCKETSTATE_FILE
        samples = await asyncio.to_thread(st.load_samples, p)
        result = st.parts_timeline(samples, params.name_substring)
        result["path"] = str(p)
        result["sample_count"] = len(samples)
        return json.dumps(result, indent=2)
    except FileNotFoundError as e:
        return _error_for_exception(e)


class TestAgainstRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flight_jsonl_path: str = Field(
        ..., description="Real flight telemetry file (archived .gz or the live sample.jsonl) -- must "
                          "include output_TurnAxisTorque and output_DirectionalAxis.x/y for control-input replay."
    )
    craft_config_path: str = Field(
        ..., description="sfs_probe_forwardstartinfo.json from the 'getforwardstartinfo' command -- the "
                          "static craft-config snapshot the forward integrator starts from."
    )
    start_t: float = Field(..., description="Sim-relative start time (seconds since flight start) to begin from.")
    duration_s: float = Field(..., description="Prediction horizon in seconds.")
    dt: float = Field(default=0.25, description="RK4 step size, seconds.")
    body_name: str = Field(default="Earth")
    aoa_table_path: Optional[str] = Field(default=None, description="Optional aoa_dragarea.py table for drag/aero_torque.")
    throttle_field: Optional[str] = Field(
        default=None,
        description="Optional telemetry field for throttle replay, e.g. 'gimbalThrottleOut' -- see "
                     "forward_sim.py's load_control_schedule docstring for the single-engine-scoping caveat.",
    )


@mcp.tool(name="sfsprobe_test_against_run", annotations={"title": "Forward-simulate against a real flight and compare",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_test_against_run(params: TestAgainstRunInput) -> str:
    """Forward-simulates from a real flight sample at start_t, REPLAYING
    that flight's real control inputs (rotation, RCS, optionally
    throttle) rather than guessing them, then compares the prediction
    against what actually happened at start_t+duration_s in the SAME
    flight -- isolating "does the confirmed physics predict correctly"
    from "can this module guess pilot behavior". This wraps
    analysis/forward_sim.py's --test_against_run as an MCP tool: every
    other validation step (validate_gravity_drag, regression_check,
    noise_floor) already had one; the forward integrator's own
    end-to-end check didn't.

    Args:
        params (TestAgainstRunInput): flight_jsonl_path, craft_config_path,
        start_t, duration_s, dt, body_name, aoa_table_path, throttle_field

    Returns:
        str: JSON with start_t, duration_s, predicted (final predicted
        state), actual (real sample nearest start_t+duration_s), and
        errors (height/speed/position, percent and absolute).
    """
    try:
        result = await asyncio.to_thread(
            fsim.test_against_run,
            params.flight_jsonl_path, params.craft_config_path,
            params.start_t, params.duration_s,
            dt=params.dt, body_name=params.body_name,
            aoa_table_path=params.aoa_table_path,
            throttle_field=params.throttle_field,
        )
        return json.dumps(result, indent=2)
    except (FileNotFoundError, ValueError) as e:
        return _error_for_exception(e)


class TestAgainstRunTrajectoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flight_jsonl_path: str = Field(
        ..., description="Real flight telemetry file (archived .gz or the live sample.jsonl) -- must "
                          "include output_TurnAxisTorque and output_DirectionalAxis.x/y for control-input replay."
    )
    craft_config_path: str = Field(
        ..., description="sfs_probe_forwardstartinfo.json from the 'getforwardstartinfo' command."
    )
    start_t: float = Field(..., description="Sim-relative start time (seconds since flight start) to begin from.")
    duration_s: float = Field(..., description="Prediction horizon in seconds.")
    dt: float = Field(default=0.25, description="RK4 step size, seconds.")
    body_name: str = Field(default="Earth")
    aoa_table_path: Optional[str] = Field(default=None, description="Optional aoa_dragarea.py table for drag/aero_torque.")
    throttle_field: Optional[str] = Field(default=None, description="Optional telemetry field for throttle replay.")
    stride: int = Field(
        default=1, ge=1,
        description="Compare only every Nth predicted step (1 = every step) -- trades resolution for "
                     "response size on a long duration_s / small dt without changing the simulation's own step size.",
    )


@mcp.tool(name="sfsprobe_test_against_run_trajectory", annotations={"title": "Forward-simulate a full trajectory and compare step-by-step",
          "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def sfsprobe_test_against_run_trajectory(params: TestAgainstRunTrajectoryInput) -> str:
    """Like sfsprobe_test_against_run, but compares the ENTIRE predicted
    trajectory against the real flight step-by-step instead of only the
    final point -- built to characterize forward-integrator compounding
    error separately for position vs. rotation over time, the open
    question this project had no real per-step comparison data for.

    Args:
        params (TestAgainstRunTrajectoryInput): flight_jsonl_path,
        craft_config_path, start_t, duration_s, dt, body_name,
        aoa_table_path, throttle_field, stride

    Returns:
        str: JSON with start_t, duration_s, stride, step_count, steps
        (per-step sim_t/real_t/position_offset_m/rotation_error_deg/
        angular_velocity_error_degs), and summary (median/mean/max for
        position_offset_m and rotation_error_deg computed SEPARATELY).
    """
    try:
        result = await asyncio.to_thread(
            fsim.test_against_run_trajectory,
            params.flight_jsonl_path, params.craft_config_path,
            params.start_t, params.duration_s,
            dt=params.dt, body_name=params.body_name,
            aoa_table_path=params.aoa_table_path,
            throttle_field=params.throttle_field,
            stride=params.stride,
        )
        return json.dumps(result, indent=2)
    except (FileNotFoundError, ValueError) as e:
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
    """Poll the LIVE sample.jsonl's last line until field <op> value holds
    or timeout. Reads only the file's tail each poll -- cheap even on a
    large, actively-growing telemetry file. (v0.60.0: was truth.jsonl --
    the live file is never gzipped while still recording, only on stop,
    so this plain tail-read stays valid unmodified.)

    Tail size is 64KB, not a smaller round number -- confirmed via a real
    live test (2026-09-05) that full-mode samples (embedded heatParts/
    engines/fuelByStage arrays) can exceed 4KB per line on their own,
    which silently truncated the last line mid-object, made it fail to
    parse as JSON, and made every wait_until against full-mode telemetry
    time out reporting last_sample_value: null regardless of whether the
    condition was already true. Scoped-mode samples are much smaller, so
    64KB comfortably covers both.
    """
    if op not in st._OPS:
        raise ValueError(f"unknown op {op!r}, must be one of {list(st._OPS)}")
    fn = st._OPS[op]
    start = time.monotonic()
    deadline = start + timeout_s
    last = None
    TAIL_READ_BYTES = 65536
    while time.monotonic() < deadline:
        if SAMPLE_FILE.exists():
            try:
                with SAMPLE_FILE.open("rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    read_size = min(size, TAIL_READ_BYTES)
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
    the newly-archived flight (by mtime, created after this call
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
        # v0.60.0: archive naming is telemetry_<mode>_<timestamp>.jsonl.gz
        # (was *_truth_*.jsonl pre-refactor -- that pattern could never
        # match again, silently breaking this tool until caught 2026-09-05
        # by an explicit live test).
        candidates = [f for f in ARCHIVE_DIR.glob("telemetry_*_*.jsonl.gz") if f.stat().st_mtime >= script_start - 1]
    if not candidates:
        return json.dumps({"script_log": script_result, "archived_file": None,
                            "warning_code": "NO_NEW_ARCHIVE",
                            "note": "no newly-archived flight found -- did the script include a "
                                     "{'commands': ['telemetry off']} step?"}, indent=2)
    newest = max(candidates, key=lambda f: f.stat().st_mtime)
    samples = await asyncio.to_thread(st.load_samples, newest)
    summary = st.flight_summary(samples)
    validation = st.validate_gravity_drag(samples)
    logged_path = newest
    if params.tag:
        # Same protection sfsprobe_tag_flight gives -- copy into kept/
        # BEFORE logging, so this tag survives the next same-mode
        # recording's DeletePreviousArchive the same way a direct
        # sfsprobe_tag_flight call does. Previously logged 'newest'
        # directly, leaving run_and_analyze tags unprotected while
        # sfsprobe_tag_flight's were safe -- an inconsistency caught
        # 2026-09-05 alongside the glob-pattern bug above.
        logged_path = await asyncio.to_thread(_copy_to_kept, newest)
        await asyncio.to_thread(_append_flight_log, logged_path, params.tag, params.notes, summary)
    return json.dumps({
        "script_log": script_result, "archived_file": str(logged_path),
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
    "not_in_world": "NOT_IN_WORLD",
    "not_in_build": "NOT_IN_BUILD",
    "file_not_found": "FILE_NOT_FOUND",
    "read_error": "FILE_ERROR",
    "type_resolution": "TYPE_RESOLUTION_FAILED",
    "fromjson_method_not_found": "TYPE_RESOLUTION_FAILED",
    "deserialize_error": "PARSE_ERROR",
    "deserialize_null": "PARSE_ERROR",
    "spawn_method_not_found": "TYPE_RESOLUTION_FAILED",
    "spawn_exception": "SPAWN_FAILED",
    "buildstate_not_found": "TYPE_RESOLUTION_FAILED",
    "load_method_not_found": "TYPE_RESOLUTION_FAILED",
    "load_exception": "SPAWN_FAILED",
    "unknown_part_names": "INVALID_PARAM",
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


class LoadBlueprintTarget(str, Enum):
    BUILD = "build"    # BuildState.LoadBlueprint -- loads into the editor,
                        # REPLACING the current design. Requires Build_PC.
                        # This is the real mechanism behind the game's own
                        # "Load Blueprint" button -- a legitimate, routinely-
                        # repeatable operation. SAFE for normal use.
    WORLD = "world"     # RocketManager.SpawnBlueprint -- spawns an ADDITIONAL
                        # live physics rocket into an active flight. Requires
                        # World_PC.
                        #
                        # ** DO NOT USE THIS DURING A LIVE FLIGHT. **
                        # Confirmed 2026-08-29: the method's first action is
                        # WorldView.main.SetViewLocation(LaunchPadLocation) --
                        # moving the camera to the pad. That's the signature of
                        # a ONE-TIME Build-to-World launch-transition primitive
                        # (the internal "Launch" button mechanism), not a
                        # general-purpose spawn tool the game itself ever calls
                        # mid-flight or repeatedly. Calling it during an active
                        # flight materializes a fully-fueled part with none of
                        # a real launch's cost/sequence/achievement tracking --
                        # functionally cheating, and outside any state the game
                        # was designed to handle repeatedly. The one successful
                        # live test (2026-08-28) proved the reflection mechanism
                        # works; it is NOT a green light for routine use. Keep
                        # this option available for future one-off research
                        # only, never as a normal operation.


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
    target: LoadBlueprintTarget = Field(
        default=LoadBlueprintTarget.BUILD,
        description="'build' (default, SAFE): load into the editor, "
                     "replacing the current design -- the real 'Load "
                     "Blueprint' button mechanism, requires Build_PC, "
                     "routinely repeatable. 'world' (DO NOT USE DURING A "
                     "LIVE FLIGHT -- likely a one-time internal Launch-"
                     "transition primitive, not a real spawn tool; "
                     "materializes a fully-fueled part outside any normal "
                     "game state, functionally cheating): spawns an "
                     "additional rocket into an active flight, requires "
                     "World_PC. Reserve for one-off research only.",
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
    then dispatches to one of two real game mechanisms depending on
    `target`:

    - **target='build' (default, SAFE):** `BuildState.LoadBlueprint` --
      the actual mechanism behind the game's own "Load Blueprint" button.
      REPLACES the current editor design (calls BuildState.Clear() first).
      Requires the Build_PC scene. Confirmed 2026-08-29 by reading the
      real IL body: no dependency on WorldView/a live flight at all. A
      legitimate, routinely-repeatable operation -- this is what the UI
      itself does every time a player clicks "Load".
    - **target='world' -- DO NOT USE DURING A LIVE FLIGHT:**
      `RocketManager.SpawnBlueprint`. Its first action
      (`WorldView.main.SetViewLocation(LaunchPadLocation)`) is the
      signature of a ONE-TIME internal Build-to-World launch-transition
      primitive, not a general spawn tool the game itself ever calls
      mid-flight or repeatedly. Calling it during an active flight
      materializes a fully-fueled part with none of a real launch's
      cost/sequence/achievement tracking -- functionally cheating, and
      outside any state the game was designed to handle repeatedly. The
      one successful live test (2026-08-28) proved the reflection
      mechanism works; it is NOT a green light for routine use. Reserve
      for one-off future research only.

    Both targets: v0.33.0+. Distinct error codes so a caller can tell WHY
    it failed, not just that it did: NOT_IN_BUILD / NOT_IN_WORLD (wrong
    scene for the chosen target), FILE_NOT_FOUND, FILE_ERROR (couldn't
    read), TYPE_RESOLUTION_FAILED (a reflection lookup failed -- likely
    means the game's internals changed), PARSE_ERROR (bad/unparseable
    JSON), SPAWN_FAILED (the game itself threw during spawn/load -- the
    file was fine, check the error message for why).

    Multi-part blueprints (joint generation/connectivity) and a
    documented possible DLC/ownership gate for locked parts remain
    untested for both targets -- only a single free part has been
    confirmed end to end so far.

    Args:
        params (LoadBlueprintInput): name, path, target, timeout_s

    Returns:
        str: JSON with keys: success (bool), path (the file used),
        target (the mode used), and either 'response' (raw OK text) or
        'error_code'/'error'/'failure_reason' (the raw reason= token from
        the mod, in case the mapped error_code loses detail worth seeing).
    """
    try:
        blueprint_path = _resolve_blueprint_path(params.name, params.path)
    except (FileNotFoundError, ValueError) as e:
        return _error_for_exception(e)

    command_word = "loadblueprintbuild" if params.target == LoadBlueprintTarget.BUILD else "loadblueprint"
    try:
        response, elapsed = await asyncio.to_thread(
            send_command, f"{command_word} {blueprint_path}", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except ProbeTimeoutError as e:
        return _error_for_exception(e, elapsed_seconds=round(params.timeout_s, 3))
    except FileNotFoundError as e:
        return _error_for_exception(e)

    if f"{command_word}: OK" in response:
        return json.dumps({
            "success": True, "path": str(blueprint_path), "target": params.target.value,
            "response": response, "elapsed_seconds": round(elapsed, 3),
        }, indent=2)

    reason_match = re.search(r"reason=(\S+)", response)
    reason = reason_match.group(1) if reason_match else None
    error_code = _BLUEPRINT_FAILURE_CODES.get(reason, "UNKNOWN_ERROR")
    return json.dumps({
        "success": False, "path": str(blueprint_path), "target": params.target.value,
        "error_code": error_code, "failure_reason": reason,
        "error": response, "elapsed_seconds": round(elapsed, 3),
    }, indent=2)


# ---------------------------------------------------------------------------

# ===========================================================================
# STAGE 13 -- magnet-based blueprint construction (build a stack from real
# confirmed attachment-point data, not guessed positions)
# ===========================================================================

class BuildStackBlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parts: List[str] = Field(
        ..., min_length=1,
        description="Real part names, bottom to top, e.g. ['Engine Hawk', "
                     "'Fuel Tank', 'Capsule', 'Parachute']. Must match real "
                     "PartsLoader.parts catalog names exactly (see "
                     "sfsprobe_getparts, once wrapped). Surface-mount parts "
                     "(confirmed: Parachute, Parachute Side, Side Separator -- "
                     "no MagnetModule) are NOT supported yet and raise a clear "
                     "error rather than silently guessing a position.",
    )
    name: str = Field(..., min_length=1, description="Blueprint name -- final result written to blueprints/research/<name>/.")
    timeout_s: float = Field(default=10.0, ge=1.0, le=60.0)


@mcp.tool(
    name="sfsprobe_build_stack_blueprint",
    annotations={
        "title": "Build a vertically-stacked blueprint from real magnet-point data",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sfsprobe_build_stack_blueprint(params: BuildStackBlueprintInput) -> str:
    """Builds a correctly-connected vertical stack blueprint from a part
    list, using REAL magnet-point (attachment-point) data confirmed
    2026-08-29 -- not centerOfMass/height guessing, which was tried
    first and produced a too-narrow tank and an overlapping parachute
    (see mod_changelog.md v0.30-0.35, docs/high_level_checklist.md
    "Blueprint construction").

    Genuinely LIVE and two-phase, not a pure calculation -- REPLACES
    whatever is currently in the Build_PC editor, twice:

    1. SCOUT: places every part far apart (guaranteed non-overlapping)
       so each becomes a real placed instance -- real magnet-point local
       offsets can only be read from a placed part (a bare catalog
       prefab returns null, confirmed empirically).
    2. CORRECT: reads each part's real magnet points via
       'getplacedmagnets', computes the exact stacked positions via the
       confirmed magnet-chain formula (python/blueprint_builder.py),
       writes the real blueprint to blueprints/research/<name>/, and
       loads THAT as the final result.

    After the final load, re-queries magnet points once more and checks
    every expected connector's 'occupied' flag -- the game's own live
    connectivity signal -- reporting any that aren't genuinely connected
    rather than assuming success just because the load call succeeded.

    LIMITATION, deliberately not silently wrong: any part with no
    MagnetModule (confirmed for Parachute, Parachute Side, Side
    Separator -- likely all "surface-mount" parts) raises a clear error
    during the SCOUT phase (the CORRECT phase never runs in that case,
    so the previous editor design isn't touched a second time) rather
    than guessing a position for a part type this tool doesn't
    understand yet.

    Args:
        params (BuildStackBlueprintInput): parts, name, timeout_s

    Returns:
        str: JSON with keys: success (bool), blueprint_path (the final
        written file), positions (part name -> final y position),
        connectivity_problems (list, empty if every checked connector
        shows occupied=true), or error_code/error/failure_stage if
        something failed (scout_build, scout_load, magnet_read,
        position_compute, correct_load).
    """
    scout_folder = BLUEPRINTS_RESEARCH_DIR / f"_scout_{params.name}"
    final_folder = BLUEPRINTS_RESEARCH_DIR / params.name

    # Phase 1: scout placement -- far-apart, guaranteed non-overlapping,
    # just to turn every requested part into a real placed instance.
    try:
        scout_bp = bpb.scout_blueprint(params.parts)
    except ValueError as e:
        return _error_for_exception(e, failure_stage="scout_build")

    await asyncio.to_thread(bpb.write_blueprint, scout_bp, scout_folder)
    scout_result = await sfsprobe_load_blueprint(LoadBlueprintInput(
        path=str(scout_folder / "Blueprint.txt"), target=LoadBlueprintTarget.BUILD, timeout_s=params.timeout_s
    ))
    scout_result_d = json.loads(scout_result)
    if not scout_result_d.get("success"):
        scout_result_d["failure_stage"] = "scout_load"
        return json.dumps(scout_result_d, indent=2)

    # Phase 2: read REAL magnet points from the now-placed scout parts --
    # only safe/possible now that they're placed instances, not bare
    # catalog prefabs (confirmed empirically 2026-08-29).
    try:
        magnets_response, _ = await asyncio.to_thread(
            send_command, "getplacedmagnets", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
    except (ProbeTimeoutError, FileNotFoundError) as e:
        return _error_for_exception(e, failure_stage="magnet_read")

    if "getplacedmagnets: FAILED" in magnets_response:
        return _error_response("SPAWN_FAILED", magnets_response, failure_stage="magnet_read")

    try:
        magnets_data = json.loads(PLACED_MAGNETS_JSON_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return _error_response("PARSE_ERROR", f"couldn't read placed-magnets file: {e}", failure_stage="magnet_read")

    placed = magnets_data.get("placedParts", [])
    if len(placed) < len(params.parts):
        return _error_response(
            "SPAWN_FAILED",
            f"expected {len(params.parts)} placed parts after scout, found {len(placed)} -- "
            "scout load may have partially failed",
            failure_stage="magnet_read",
        )
    # Take the LAST len(parts) entries -- if anything else was already in
    # the editor before this call started, scout's own parts were
    # appended after it. Order within that tail is assumed to match
    # placement order (matches every observation so far, not
    # independently proven via IL -- flagged honestly, not asserted as
    # certain).
    scout_magnets = [p.get("magnetPoints") for p in placed[-len(params.parts):]]

    # Phase 3: compute the real corrected stack from real local offsets.
    try:
        final_bp = bpb.build_stack_from_scout(params.parts, scout_magnets, center_the_stack=True)
    except bpb.SurfaceMountPartError as e:
        return _error_response(
            "INVALID_PARAM", str(e), failure_stage="position_compute",
            note="the scout blueprint is still loaded in the editor -- the "
                 "CORRECT phase never ran, so nothing further was overwritten "
                 "by this failure",
        )

    await asyncio.to_thread(bpb.write_blueprint, final_bp, final_folder)
    final_result = await sfsprobe_load_blueprint(LoadBlueprintInput(
        path=str(final_folder / "Blueprint.txt"), target=LoadBlueprintTarget.BUILD, timeout_s=params.timeout_s
    ))
    final_result_d = json.loads(final_result)
    if not final_result_d.get("success"):
        final_result_d["failure_stage"] = "correct_load"
        return json.dumps(final_result_d, indent=2)

    # Phase 4: verify REAL connectivity, not just that the load call
    # succeeded -- occupied is the game's own live connectivity signal.
    # Best-effort: verification failing doesn't undo the successful build.
    connectivity_problems = []
    try:
        verify_response, _ = await asyncio.to_thread(
            send_command, "getplacedmagnets", params.timeout_s, DEFAULT_POLL_INTERVAL_S
        )
        if "getplacedmagnets: " in verify_response and "FAILED" not in verify_response:
            verify_data = json.loads(PLACED_MAGNETS_JSON_FILE.read_text())
            verify_placed = verify_data.get("placedParts", [])
            verify_magnets = [p.get("magnetPoints") for p in verify_placed[-len(params.parts):]]
            connectivity_problems = bpb.check_connectivity(params.parts, verify_magnets)
    except (ProbeTimeoutError, FileNotFoundError, OSError, json.JSONDecodeError):
        pass

    positions = {p["n"]: p["p"]["y"] for p in final_bp["parts"]}
    return json.dumps({
        "success": True,
        "blueprint_path": str(final_folder / "Blueprint.txt"),
        "positions": positions,
        "connectivity_problems": connectivity_problems,
    }, indent=2)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _log(f"starting, mod dir = {MOD_DIR}")
    mcp.run()
