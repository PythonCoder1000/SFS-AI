# SFS AI

LLM agent that designs rockets in Spaceflight Simulator, flies them, and
adapts mid-flight when the design underperforms. Successor to Geometry Dash AI.

**Everything SFS-related lives in this folder.**

## Target build — pinned

| | |
|---|---|
| Game | Spaceflight Simulator **1.6.00.16** (Steam, macOS) |
| Unity | 6000.1.17f1 |
| Bundle | `com.StefMorojna.SpaceflightSimulator` |
| Install | `~/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/` |
| Mods folder | `SpaceflightSimulatorGame.app/Contents/Resources/Mods` |

**Steam auto-update must stay off.** Every value and field offset derived so
far is tied to this exact build. An update doesn't just stale the numbers —
it makes measurements taken before and after incomparable.

## Layout

```
SFS AI/
  README.md      this file
  sfsprobe/      read-only mod that dumps live part + planet data to JSON
```

## sfsprobe

First mod for the project, and deliberately small. It walks game objects by
reflection rather than hardcoded field offsets, so it should survive most
game updates.

```bash
cd sfsprobe
brew install mono     # once
./build.sh
```

Then launch SFS, enable "SFS Probe" in the in-game Mod Loader, and wait ~10s
on the main menu. Output appears in `Contents/Resources/Mods/SFSProbe/`:

- `sfs_probe_dump.json` — the data
- `probe.log` — diagnostics; matters more than the dump on the first run

Beyond the values, a successful run settles four things nothing static could:
whether mods load at all on the macOS Steam build, whether the `Mod` contract
matches the metadata, what `Application.version` reports at runtime, and what
`Time.fixedDeltaTime` actually reads on this machine.

## Status

Research phase. No agent code written yet.

Key findings so far live in the chat history and the open-questions register;
**both still need consolidating into this folder.**
