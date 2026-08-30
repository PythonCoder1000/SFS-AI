"""
blueprint_builder.py -- builds SFS blueprints from a part list using
REAL, empirically-confirmed magnet-point data, not guessed positions.

Confirmed 2026-08-29 (see docs/high_level_checklist.md, "Blueprint
construction"): SFS's part-connection system is SFS.Builds.HoldGrid +
MagnetModule, NOT a coordinate-snap grid. A part's own position
("pivot") in a blueprint is NOT its geometric center --
MagnetModule.points are local-space offsets FROM that pivot (e.g.
Fuel Tank's pivot sits at its bottom connector, not its middle). The
magnet-chain formula below is confirmed EXACT against a real hand-built,
connected 4-part rocket's dumpblueprint output -- not derived from
guessing, and not from centerOfMass/height heuristics (both of those
were tried first and produced a tiny-width tank and an overlapping
parachute -- see mod_changelog.md v0.30-0.35 for the full story).

LIMITATION, documented and deliberately not silently wrong: parts with
no MagnetModule (magnetPoints: null, confirmed for Parachute, Parachute
Side, Side Separator) use a different "surface-mount" attachment system
this module does NOT model yet. Calling build_stack_from_scout() with
such a part raises SurfaceMountPartError rather than guessing a
position -- see docs/high_level_checklist.md for what's still needed
(real part geometry via InitializePart() on placed instances, or
calling HoldGrid.CollectSurfaceSnaps directly).

This is inherently a TWO-PHASE, LIVE process, not a pure offline
calculation: a part's real local magnet-point offsets can only safely
be read from an ALREADY-PLACED instance (a bare catalog prefab returns
null -- confirmed empirically, same class of gotcha as surfaceGeometry
needing Part.InitializePart()). Phase 1 ("scout") places every part far
apart so nothing overlaps regardless of real size, just to make them
placed instances. Phase 2 reads their real magnet points and computes
the correct final stack. See sfsprobe_mcp's sfsprobe_build_stack_blueprint
tool for the live orchestration; this module holds the pure, testable
math and file I/O only -- no game interaction here.
"""

import json
from pathlib import Path
from typing import Optional


class SurfaceMountPartError(ValueError):
    """Raised when a part in the requested stack has no MagnetModule
    (confirmed null magnetPoints) -- this module doesn't know how to
    position surface-mount parts yet. See docs/high_level_checklist.md
    "Blueprint construction" for the real reason and what's needed."""


def scout_blueprint(part_names: list[str], spacing: float = 20.0) -> dict:
    """Builds a rough, guaranteed-non-overlapping blueprint for the
    FIRST placement pass -- just to get each part instantiated so its
    real magnet points become readable (getplacedmagnets returns null
    on unplaced catalog prefabs, confirmed 2026-08-29). Large fixed
    spacing, no attempt at correctness -- this blueprint is discarded
    after learning from it, never meant to be the final result.
    """
    if not part_names:
        raise ValueError("part_names must not be empty")
    parts = []
    for i, name in enumerate(part_names):
        parts.append({
            "n": name,
            "p": {"x": 0.0, "y": i * spacing},
            "o": {"x": 1.0, "y": 1.0, "z": 0.0},
        })
    return {
        "center": 0.0, "parts": parts, "stages": [],
        "rotation": 0.0, "offset": {"x": 0.0, "y": 0.0}, "interiorView": False,
    }


def _entry_exit_offsets(magnet_points: Optional[list[dict]]) -> tuple[float, float]:
    """Given a part's real local magnetPoints (from getplacedmagnets),
    returns (entry_offset_y, exit_offset_y): entry is the LOWEST local
    y (bottom connector), exit is the HIGHEST (top connector). For a
    single-point part these are the same point (a "cap" part -- an
    engine or capsule -- connects on one side only, confirmed for both
    in the reference rocket)."""
    if not magnet_points:
        raise SurfaceMountPartError(
            "part has no MagnetModule (magnetPoints is null/empty) -- this "
            "is a surface-mount part (confirmed for Parachute, Parachute "
            "Side, Side Separator), not modeled by this stacking function. "
            "See docs/high_level_checklist.md 'Blueprint construction' for "
            "what's still needed to support it."
        )
    ys = [pt["y"] for pt in magnet_points]
    return min(ys), max(ys)


def build_stack_from_scout(
    part_names: list[str],
    scouted_magnet_points: list[Optional[list[dict]]],
    center_the_stack: bool = True,
) -> dict:
    """Given the part list (bottom to top) and each part's REAL local
    magnetPoints (learned from a scout placement + getplacedmagnets, in
    the SAME order as part_names), computes the correct final
    y-positions via the confirmed magnet-chain formula:

        next_pivot = prev_pivot + prev_exit_offset - next_entry_offset

    and returns a real blueprint dict, ready to write/load. All parts
    share x=0 -- a straight vertical stack, matching what was actually
    asked for (a single stack, not a general multi-branch rocket).

    Raises SurfaceMountPartError if any part has no MagnetModule --
    deliberately, rather than silently guessing a position for a part
    type this module doesn't understand yet.
    """
    if len(part_names) != len(scouted_magnet_points):
        raise ValueError("part_names and scouted_magnet_points must be the same length")
    if len(part_names) == 0:
        raise ValueError("part_names must not be empty")

    entry_exit = [_entry_exit_offsets(mp) for mp in scouted_magnet_points]

    pivots = [0.0] * len(part_names)
    # First part's pivot is the reference origin, shifted so its own
    # entry connector lands at y=0 -- an arbitrary but consistent choice,
    # corrected by center_the_stack below regardless.
    pivots[0] = -entry_exit[0][0]
    for i in range(1, len(part_names)):
        prev_pivot = pivots[i - 1]
        prev_exit = entry_exit[i - 1][1]
        this_entry = entry_exit[i][0]
        pivots[i] = prev_pivot + prev_exit - this_entry

    if center_the_stack:
        # Center on the TRUE vertical extent of the whole stack (the
        # lowest entry point of the bottom part to the highest exit
        # point of the top part) -- not just the pivot list, which would
        # under-count by each end part's own extent beyond its pivot.
        # This is the actual fix for the "blueprints end up off to the
        # side" bug flagged 2026-08-29.
        bottom = pivots[0] + entry_exit[0][0]
        top = pivots[-1] + entry_exit[-1][1]
        mid = (bottom + top) / 2.0
        pivots = [p - mid for p in pivots]

    parts = []
    for name, y in zip(part_names, pivots):
        parts.append({
            "n": name,
            "p": {"x": 0.0, "y": round(y, 6)},
            "o": {"x": 1.0, "y": 1.0, "z": 0.0},
        })

    return {
        "center": 0.0, "parts": parts,
        "stages": [{"stageId": 0, "partIndexes": list(range(len(parts)))}],
        "rotation": 0.0, "offset": {"x": 0.0, "y": 0.0}, "interiorView": False,
    }


def write_blueprint(blueprint: dict, folder: Path, version: str = "1.6.00.16") -> None:
    """Writes a blueprint dict to <folder>/Blueprint.txt + Version.txt,
    matching the real on-disk SFS.Builds.Blueprint.Save format
    (confirmed via a real saved blueprint file, see blueprints/README.md)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Version.txt").write_text(version)
    (folder / "Blueprint.txt").write_text(json.dumps(blueprint, separators=(",", ":")))


def check_connectivity(
    part_names: list[str],
    placed_magnet_points: list[Optional[list[dict]]],
) -> list[dict]:
    """Given a list of parts (stack order) and their REAL magnetPoints
    AFTER a real placement (from getplacedmagnets, post-load), checks
    whether each expected connector shows occupied:true. This is the
    "did it actually connect, not just overlap" check -- occupied is
    the game's OWN live connectivity signal (confirmed: true only when
    genuinely connected, false when merely placed nearby), not geometry
    this module would otherwise have to reimplement. Surface-mount
    parts (null magnetPoints) are skipped, not flagged as problems --
    this function doesn't know their real connectivity rule yet either.
    Returns a list of problems found; empty means every connector this
    function CAN check looks genuinely connected.
    """
    problems = []
    for i, mp in enumerate(placed_magnet_points):
        name = part_names[i] if i < len(part_names) else f"part[{i}]"
        if not mp:
            continue
        if i > 0:
            entry_y, _ = _entry_exit_offsets(mp)
            entry_point = next((p for p in mp if p["y"] == entry_y), None)
            if entry_point is not None and not entry_point.get("occupied", False):
                problems.append({"part": name, "index": i, "issue": "entry connector not occupied"})
        if i < len(placed_magnet_points) - 1:
            _, exit_y = _entry_exit_offsets(mp)
            exit_point = next((p for p in mp if p["y"] == exit_y), None)
            if exit_point is not None and not exit_point.get("occupied", False):
                problems.append({"part": name, "index": i, "issue": "exit connector not occupied"})
    return problems
