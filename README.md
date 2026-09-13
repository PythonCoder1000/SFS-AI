# SFS AI

LLM agent that designs rockets in Spaceflight Simulator, flies them, and
adapts mid-flight when the design underperforms. Built from scratch --
unlike prior projects in this space (KSP has kRPC, an existing mature
community API), SFS had no mod-loader RPC layer, no existing probe, and
no reliable community data on part physics. Every piece of tooling here
-- the probe mod, the reflection toolkit, the analysis/orchestration
layer, and the source-code documentation -- was built from a blank
editor and a decompiler.

**Everything SFS-related lives in this folder.**

## Target build -- pinned

| | |
|---|---|
| Game | Spaceflight Simulator **1.6.00.16** (Steam, macOS) |
| Unity | 6000.1.17f1 (Mono scripting backend, Apple Silicon ARM64) |
| Install | `~/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/` |
| Mods folder | `SpaceflightSimulatorGame.app/Mods/SFSProbe/` |

**Steam auto-update must stay off.** Every value and field offset derived
so far is tied to this exact build. An update doesn't just stale the
numbers -- it makes measurements taken before and after incomparable.
`analysis/il_inventory.py` and `sfsprobe_regression_check` exist specifically
to catch this if it ever happens.

## Layout

Organized by content theme, not file type. Reorganized 2026-08-30 --
CLAUDE.md now lives in Project knowledge, not this repo.

```
SFS AI/
  README.md              this file

  sfsprobe/               the C# probe mod (SFSProbe.cs, build.sh)
    mod_changelog.md        SFSProbe.cs version history (lives with the mod it documents)
    probe_cmd.py            standalone adaptive-polling CLI (superseded by sfsprobe_mcp, kept as a thin fallback)

  sfsprobe_mcp/           MCP server -- the primary way to talk to the mod
    server.py               ~30 tools: live game control, telemetry analysis,
                             flight orchestration, bookkeeping
    README.md                full tool reference

  analysis/               shared analysis engine + standalone scripts (renamed from python/)
    sfs_telemetry.py        the analysis logic sfsprobe_mcp's tools call into
    analyze_dragarea.py      standalone CLI validation script
    il_inventory.py          type/method/field inventory generator (re-runnable
                             after an SFS update as a "did anything change" diff)
    reference_index.py       docs/sfs_reference/'s manifest/INDEX.md generator
    reference_add.py         adds one class's docs into the reference set
    python_changelog.md      Python-side (analysis/tooling) history (lives with the code it documents)

  bookkeeping/            session/flight state, not research
    flights_log.jsonl       tagged flight bookkeeping (gitignored)
    active_state.md          lightweight "where we left off" state (gitignored)

  docs/                   research, physics reference, and the SFS Documentation
    sfs_reference/           per-class API reference of SFS's own decompiled
                             source (see below) -- generated, not hand-maintained
    sfs_physics_reference.md  confirmed physics formulas + constants
    high_level_checklist.md   Tier 1 research status tracker
    sfs_reference_plan.md     standing instructions for the SFS Documentation effort

  blueprints/             rocket designs (research/, live/)

  hackathon/              CoreWeave Hacks submission (Sept 2026) -- see
                          hackathon/README.md for full disclosure of what's
                          pre-existing (this repo) vs. built during the event

  scratch/                gitignored -- raw IL dumps, not our code

  unused_assets/          gitignored -- parked, not deleted: old session handoffs,
                          macOS .DS_Store cruft, stale __pycache__, the unused
                          harmonyx lib, and the superseded local CLAUDE.md
```

## sfsprobe (the mod)

Walks game objects by reflection rather than hardcoded field offsets, so
it survives most game updates. Confirmed working end-to-end: live physics
reads, drag/aero force computation (validated against real measured
flight deceleration), scoped telemetry recording with zero-rebuild field
selection, and batched multi-command execution in a single game tick.

```bash
cd sfsprobe
brew install mono     # once
./build.sh
```

Then launch SFS, enable "SFS Probe" in the in-game Mod Loader, wait ~10s
on the menu. See `sfsprobe_mcp/README.md` for the full command/tool set --
that's the intended interface now, not talking to the mod's files by hand.

## sfsprobe_mcp (the MCP server)

The primary interface to the mod and to flight analysis. Live game
control (send commands, batch commands, scripted flight profiles with
condition-based waits), telemetry analysis (stats, search, phase/event
detection, scoped analysis, formula validation, comparison/regression),
and bookkeeping (tagged flight log, CSV export). See its own README for
the complete tool reference.

## The SFS Documentation (`docs/sfs_reference/`)

A standalone, complete reference to SFS 1.6.00.16's own decompiled
source code -- not documentation of this project's mod, and not scoped
to only what this project currently needs. Built via a structured,
multi-session Claude Code effort: one file per class, a strict template
(signature/behavior/access/gotchas/status per member), generated
`INDEX.md`/`manifest.json` that can't drift from the real assembly since
they're built from `inventory.json`. In progress -- see
`docs/sfs_reference_plan.md` for the standing plan and current phase.

## Hackathon submission (CoreWeave Hacks, Sept 2026)

Everything in this repo outside `hackathon/` predates the event and is
infrastructure, not the submission -- see `hackathon/README.md` for the
full disclosure, architecture, demo script, and submission checklist.

## Status

Tier 1 physics research is substantially complete: gravity, thrust,
throttle, fuel-flow, rotation, staging, mass, and drag (force law +
`dragArea` computation) are all confirmed against live measurements, most
to well under 0.1% error. The SFS Documentation effort is in progress
(migration + full coverage of ~940 real types). Design/flight agent code
has not started yet -- current work is entirely research and tooling
infrastructure to make that phase reliable once it begins.
