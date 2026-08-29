#!/usr/bin/env python3
"""
probe_cmd.py -- fast, adaptive command/response helper for sfsprobe.

Replaces the write-command.txt / sleep-N-seconds / read-result.txt dance
with a single call that polls result.txt at a short interval and returns
the instant new output appears -- no fixed guess-and-wait, no silent hang.

Usage:
    python3 probe_cmd.py "<command>" [timeout_s] [poll_interval_s]

Examples:
    python3 probe_cmd.py "ping"
    python3 probe_cmd.py "dragarea" 8
    python3 probe_cmd.py "telemetry on h,vv,computed:dragArea"

Exit codes:
    0  -- got a new result.txt line, printed to stdout
    1  -- timed out waiting for a response (printed to stderr)
    2  -- bad usage

Notes:
    - Baseline is result.txt's byte size at call time, not line count --
      correct even if multiple result lines land in one poll window
      (all of them are printed, oldest first).
    - Clears any stale command.txt before writing, in case a previous
      call crashed mid-flight and left one behind (the mod deletes
      command.txt after each read, so a leftover one is always stale).
    - Default timeout is 5s (game's own poll loop runs every 0.5s, so
      this gives comfortable headroom); default poll interval is 0.15s.
    - This does NOT know whether the game is even running -- a timeout
      here just as often means "game not open" or "mod not loaded" as
      it means a real probe bug. Check probe.log if a timeout is a
      surprise.
"""
import sys
import os
import time

MOD_DIR = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/"
    "Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe"
)
CMD_FILE = os.path.join(MOD_DIR, "command.txt")
RESULT_FILE = os.path.join(MOD_DIR, "result.txt")


def main():
    if len(sys.argv) < 2:
        print("usage: probe_cmd.py <command> [timeout_s] [poll_interval_s]", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    poll = float(sys.argv[3]) if len(sys.argv) > 3 else 0.15

    if not os.path.isdir(MOD_DIR):
        print("ERROR: mod folder not found -- is SFS installed at the expected "
              "Steam path? " + MOD_DIR, file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(RESULT_FILE):
        open(RESULT_FILE, "a").close()
    start_size = os.path.getsize(RESULT_FILE)

    try:
        if os.path.exists(CMD_FILE):
            os.remove(CMD_FILE)
    except OSError:
        pass

    with open(CMD_FILE, "w") as f:
        f.write(command + "\n")

    deadline = time.time() + timeout
    while time.time() < deadline:
        cur_size = os.path.getsize(RESULT_FILE)
        if cur_size > start_size:
            with open(RESULT_FILE, "r") as f:
                f.seek(start_size)
                new_text = f.read()
            print(new_text.strip())
            sys.exit(0)
        time.sleep(poll)

    print(f"TIMEOUT after {timeout}s waiting for a response to: {command}", file=sys.stderr)
    print("(game may not be running, mod may not be loaded, or no active "
          "rocket for a rocket-scoped command -- check probe.log)", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
