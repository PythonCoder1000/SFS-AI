#!/usr/bin/env python3
"""Audit docs/sfs_reference/ for template compliance.

Currently checks one thing, the rule added to sfs_reference_plan.md on
2026-08-29: every `#### ` method entry under a FULL-depth type must carry a
`- **Preconditions:**` bullet. An absent field is indistinguishable from
"not checked yet", which is exactly the gap that shipped the loadblueprint
World_PC/Build_PC mixup, so this is checked mechanically rather than by
discipline.

Also reports FULL-depth types that document no methods at all -- not a
failure (plenty of types genuinely have none beyond a compiler-generated
constructor), but worth eyeballing, since a FULL-depth type with no method
entries may simply not have had its methods written up yet.

Usage:
    python3 python/reference_audit.py            # report
    python3 python/reference_audit.py --check    # silent on pass, exit 1 on fail
"""
import glob
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "docs", "sfs_reference")

# Standalone files that deliberately do not follow the per-class template.
SKIP = {"INVENTORY.md", "INDEX.md", "METHODOLOGY.md", "REFLECTION_TOOLKIT.md",
        "CORRECTIONS.md"}


def audit():
    missing, no_methods, checked = [], [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "**", "*.md"),
                                 recursive=True)):
        if os.path.basename(path) in SKIP:
            continue
        rel = os.path.relpath(path, ROOT)
        lines = open(path, encoding="utf-8").read().split("\n")
        depth = tname = None
        seen_method = False

        for i, line in enumerate(lines):
            if line.startswith("## "):
                if depth == "FULL" and tname and not seen_method:
                    no_methods.append(f"{rel} :: {tname}")
                tname, depth, seen_method = line[3:].strip(), None, False
            elif line.startswith("**Depth:**"):
                depth = "FULL" if "FULL" in line else "LIGHT"
            elif line.startswith("#### "):
                seen_method = True
                if depth != "FULL":
                    continue
                checked += 1
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith(("#### ", "## ")) or lines[j] == "---":
                        end = j
                        break
                if not any(x.startswith("- **Preconditions:**")
                           for x in lines[i + 1:end]):
                    missing.append(f"{rel}:{i + 1}  {line[5:]}")

        if depth == "FULL" and tname and not seen_method:
            no_methods.append(f"{rel} :: {tname}")

    return checked, missing, no_methods


def main():
    check_only = "--check" in sys.argv
    checked, missing, no_methods = audit()

    if check_only:
        if missing:
            print(f"FAIL: {len(missing)} of {checked} FULL-depth method "
                  f"entries are missing Preconditions")
            for m in missing:
                print(f"  {m}")
            sys.exit(1)
        sys.exit(0)

    print(f"FULL-depth method entries checked : {checked}")
    print(f"missing Preconditions             : {len(missing)}")
    for m in missing:
        print(f"  MISSING  {m}")
    print(f"\nFULL-depth types with no method entries: {len(no_methods)}")
    for t in no_methods:
        print(f"  {t}")


if __name__ == "__main__":
    main()
