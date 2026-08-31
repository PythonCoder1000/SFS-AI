#!/usr/bin/env python3
"""Add / update entries in docs/sfs_reference/manifest.json incrementally.

Reads a JSON array of entries on stdin and merges them into manifest.json
by fully-qualified name, then rebuilds INDEX.md. Namespace, kind, IL line
and member counts are filled in from inventory.json so they cannot drift
from the assembly.

    echo '[{"fq":"SFS.World.Rocket","file":"01-core-flight/Rocket.md",
             "summary":"The craft object","status":"CONFIRMED","depth":"FULL"}]' \
      | python3 python/reference_add.py

Also accepts {"section_map": [["§B1", "01-core-flight/Rocket.md"], ...]}
as an object instead of an array, to extend the old-file section map.
"""
import json
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "docs", "sfs_reference")
MANIFEST = os.path.join(REF, "manifest.json")
INVENTORY = os.path.join(REF, "inventory.json")

REQUIRED = {"fq", "file", "summary", "status", "depth"}
VALID_STATUS = {"CONFIRMED", "PARTIAL", "OPEN"}
VALID_DEPTH = {"FULL", "LIGHT"}


def main():
    payload = json.load(sys.stdin)
    manifest = json.load(open(MANIFEST))
    inv = {t["fq"]: t for t in json.load(open(INVENTORY))}

    if isinstance(payload, dict):
        existing = {tuple(p) for p in manifest["section_map"]}
        for pair in payload.get("section_map", []):
            if tuple(pair) not in existing:
                manifest["section_map"].append(list(pair))
        manifest["section_map"].sort()
    else:
        by_fq = {e["fq"]: e for e in manifest["types"]}
        for e in payload:
            missing = REQUIRED - set(e)
            if missing:
                sys.exit(f"entry {e.get('fq')} missing keys: {sorted(missing)}")
            if e["status"] not in VALID_STATUS:
                sys.exit(f"{e['fq']}: bad status {e['status']}")
            if e["depth"] not in VALID_DEPTH:
                sys.exit(f"{e['fq']}: bad depth {e['depth']}")
            t = inv.get(e["fq"])
            if t is None:
                sys.exit(f"{e['fq']}: not in inventory.json")
            if not os.path.exists(os.path.join(REF, e["file"])):
                sys.exit(f"{e['fq']}: file does not exist: {e['file']}")
            by_fq[e["fq"]] = {
                "fq": e["fq"],
                "name": t["name"],
                "namespace": t["ns"],
                "kind": t["kind"],
                "nested": t["nested"],
                "parent": t["parent"],
                "il_line": t["line"],
                "methods": t["methods"],
                "fields": t["fields"],
                "file": e["file"],
                "summary": e["summary"],
                "status": e["status"],
                "depth": e["depth"],
            }
        manifest["types"] = sorted(by_fq.values(), key=lambda x: (x["file"], x["fq"]))

    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    subprocess.check_call(
        [sys.executable, os.path.join(ROOT, "python", "reference_index.py")]
    )


if __name__ == "__main__":
    main()
