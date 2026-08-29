#!/usr/bin/env python3
"""Rebuild docs/sfs_reference/INDEX.md from manifest.json + inventory.json.

manifest.json is the source of truth for what has been documented; it is
edited incrementally as each class lands (see add_entry below or edit it
directly). INDEX.md is a rendering of it, so the two can never drift.

Usage:
    python3 python/reference_index.py            # rebuild INDEX.md
    python3 python/reference_index.py --check    # verify every manifest
                                                 # file path exists on disk
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "docs", "sfs_reference")
MANIFEST = os.path.join(REF, "manifest.json")
INVENTORY = os.path.join(REF, "inventory.json")
INDEX = os.path.join(REF, "INDEX.md")

FOLDERS = [
    ("00-infrastructure", "Math, variables, parsers, IO, mod loader, core utilities"),
    ("01-core-flight", "Rocket, Location, Physics, Orbit, Trajectory, Part, staging"),
    ("02-drag-aero", "SFS.World.Drag geometry and the dragArea pipeline"),
    ("03-heat-destruction", "Heating, temperature, overheat destruction, burn marks"),
    ("04-engines", "Engines, boosters, torque, thrust effects"),
    ("05-rcs", "RCS thrusters"),
    ("06-soi-terrain", "Planets, SOI, atmosphere, terrain, interplanetary"),
    ("07-saveload", "JSON/INI serialization, save records, sharing"),
    ("08-parametric-expressions", "The part-variable expression compiler and AST"),
    ("09-resources-fuel", "Resource types, tanks, flow, fuel transfer"),
    ("10-control-input", "SFS.Input, player control, arrowkeys, throttle"),
    ("11-joints-docking", "Part joints, joint groups, docking, separators, splitting"),
    ("12-world-scene-timewarp", "World time, floating origin, scenes, cameras"),
    ("13-challenges-logging", "Stats, challenges, logs, analytics, message logging"),
    ("14-misc-part-modules", "Remaining SFS.Parts.Modules: geometry, colour, behaviour"),
    ("15-ui", "SFS.UI"),
    ("16-builds", "SFS.Builds — the in-game editor"),
    ("17-modgui", "SFS.UI.ModGUI"),
    ("18-maps-navigation", "SFS.World.Maps, SFS.Navigation"),
    ("19-career-progression", "SFS.Career, SFS.Tutorials, space centre"),
    ("20-localization-audio", "SFS.Translations, SFS.Audio"),
    ("21-platform-rendering", "Platform glue, post-processing, stars, video settings"),
]

STANDALONE = [
    ("INVENTORY.md", "The full 969-type inventory — the scope definition"),
    ("METHODOLOGY.md", "Provenance, status tags, and how to re-verify any claim"),
    ("REFLECTION_TOOLKIT.md", "Live reflection helpers + ambiguous-overload catalogue"),
    ("CORRECTIONS.md", "Running ledger of overturned claims"),
]


def load():
    with open(MANIFEST) as f:
        manifest = json.load(f)
    with open(INVENTORY) as f:
        inventory = json.load(f)
    return manifest, inventory


def check(manifest):
    missing = []
    for e in manifest["types"]:
        p = os.path.join(REF, e["file"])
        if not os.path.exists(p):
            missing.append(e["file"])
    known = {t["fq"] for t in json.load(open(INVENTORY))}
    unknown = [e["fq"] for e in manifest["types"] if e["fq"] not in known]
    for f in sorted(set(missing)):
        print(f"MISSING FILE: {f}")
    for fq in unknown:
        print(f"NOT IN INVENTORY: {fq}")
    return not (missing or unknown)


def render(manifest, inventory):
    entries = manifest["types"]
    by_file = {}
    for e in entries:
        by_file.setdefault(e["file"], []).append(e)

    total = len(inventory)
    excluded = manifest.get("excluded_types", 0)
    in_scope = total - excluded
    done = len(entries)
    full = sum(1 for e in entries if e["depth"] == "FULL")
    light = sum(1 for e in entries if e["depth"] == "LIGHT")

    out = []
    w = out.append
    w("# SFS Documentation — index")
    w("")
    w("Master table of contents and coverage tracker for the complete")
    w("reference to Spaceflight Simulator **1.6.00.16**'s own decompiled")
    w("source. This documents *the game*, not this project's `sfsprobe` mod.")
    w("")
    w("Read [`../sfs_reference_plan.md`](../sfs_reference_plan.md) first if")
    w("you are picking this up fresh — it holds the settled scope decisions,")
    w("the per-class template, and the phase/session plan.")
    w("")
    w("**This file is generated.** `manifest.json` is the source of truth;")
    w("run `python3 python/reference_index.py` to rebuild this file after")
    w("editing it.")
    w("")
    w("## Coverage")
    w("")
    w("| | Count |")
    w("|---|---:|")
    w(f"| Real types in the assembly | {total} |")
    w(f"| Excluded (vendored third-party) | {excluded} |")
    w(f"| **In scope** | **{in_scope}** |")
    w(f"| Documented | {done} |")
    w(f"| — at FULL depth | {full} |")
    w(f"| — at LIGHT depth | {light} |")
    w(f"| **Remaining** | **{in_scope - done}** |")
    w(f"| Coverage | {100.0 * done / in_scope:.1f}% |")
    w("")
    w(f"**Phase:** {manifest.get('phase', 'unknown')}")
    w("")
    w("## Standalone files")
    w("")
    w("| File | What it is |")
    w("|---|---|")
    for name, desc in STANDALONE:
        w(f"| [`{name}`]({name}) | {desc} |")
    w("")
    w("## Documented types")
    w("")

    for folder, desc in FOLDERS:
        folder_entries = [e for e in entries if e["file"].startswith(folder + "/")]
        w(f"### `{folder}/`")
        w("")
        w(f"{desc}")
        w("")
        if not folder_entries:
            w("*Nothing migrated or written yet.*")
            w("")
            continue
        w("| Type | Namespace | Kind | File | Summary | Status | Depth |")
        w("|---|---|---|---|---|---|---|")
        for e in sorted(folder_entries, key=lambda x: (x["file"], x["name"])):
            w(
                f"| `{e['name']}` | `{e['namespace'] or '<global>'}` | {e['kind']} "
                f"| [{os.path.basename(e['file'])}]({e['file']}) | {e['summary']} "
                f"| {e['status']} | {e['depth']} |"
            )
        w("")

    w("## Old-file section map")
    w("")
    w("Where each section of the retired `docs/sfs_source_reference.md` went.")
    w("Kept so that cross-references written as `§B1`, `§C1.4` etc. — which")
    w("still appear inside migrated text — can be resolved.")
    w("")
    w("| Old section | New location |")
    w("|---|---|")
    for old, new in manifest.get("section_map", []):
        w(f"| {old} | {new} |")
    w("")

    with open(INDEX, "w") as f:
        f.write("\n".join(out))
    print(f"wrote {INDEX} — {done}/{in_scope} types ({100.0 * done / in_scope:.1f}%)")


def main():
    manifest, inventory = load()
    if "--check" in sys.argv:
        sys.exit(0 if check(manifest) else 1)
    render(manifest, inventory)


if __name__ == "__main__":
    main()
