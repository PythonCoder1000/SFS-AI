"""
convert_flight_compat_keys.py -- renames a full-mode recorded flight's
literal telemetry keys into the flat/nested key names
test_against_run_trajectory (and test_against_run) actually require,
per the field-renaming gotcha discovered 2026-09-07 (see
bookkeeping/active_state.md / docs/high_level_checklist.md's forward
integrator section): full-mode telemetry records turnAxis,
directionalAxisX/Y, px/py, m, rot, angv -- the tool wants
output_TurnAxisTorque, output_DirectionalAxis.x/y, location.position.x/y,
rb2d.mass, rb2d.rotation, rb2d.angularVelocity instead. Also flattens
engines[0].throttleOut into a top-level 'throttleOut' key, since a
bracket-index throttle_field string silently resolves to None/0.0 with
no error (documented gotcha #2, same session).

CONFIRMED 2026-09-07 (this session): the loader wants LITERAL flat keys
with dots IN the key string itself (e.g. the key "output_DirectionalAxis.x"),
NOT nested JSON objects. A first attempt using nested dicts
({"output_DirectionalAxis": {"x":...}}) was rejected with "missing
output_TurnAxisTorque / output_DirectionalAxis.x" even though
output_TurnAxisTorque WAS present flat -- meaning the check is an
all-or-nothing style validation across both names, and it does a flat
dotted-string key lookup (matching the same dotted-reflection-path
convention used elsewhere in this project for scoped telemetry field
requests), not a nested-object walk.

Promoted into a real script (was a one-off scratch pass last time) so
future flights don't need this re-derived from scratch.

Usage:
    python3 convert_flight_compat_keys.py <in.jsonl[.gz]> <out.jsonl> [end_idx_exclusive]

end_idx_exclusive: optional, drops any sample at or past this index
(e.g. to cut off a post-breakup tail) while keeping everything before
it, so 't'-based "seconds since flight start" math in the caller still
lines up with idx 0 of the ORIGINAL file.
"""

import gzip
import json
import sys
from pathlib import Path


def _open_any(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt")
    return open(path, "r")


def convert(in_path: str, out_path: str, end_idx_exclusive: int | None = None) -> dict:
    n_in = 0
    n_out = 0
    with _open_any(in_path) as fin, open(out_path, "w") as fout:
        for idx, line in enumerate(fin):
            line = line.strip()
            if not line:
                continue
            n_in += 1
            if end_idx_exclusive is not None and idx >= end_idx_exclusive:
                continue
            r = json.loads(line)

            out = dict(r)  # keep all original keys too, harmless extras

            # PREFER the REAL resolved output_TurnAxisTorque (v0.64.0+ mod,
            # camelCase "outputTurnAxisTorque" in raw telemetry) over the old
            # turnAxis-based reconstruction whenever it's actually present --
            # confirmed 2026-09-07 (H1/SAS investigation) that raw turnAxis
            # reads exactly 0 the instant a player releases the stick even
            # while the real value is fully saturated from SAS auto-engaging.
            # Falls back to the old (known-incomplete) turnAxis mapping only
            # for flights recorded before v0.64.0, which never captured the
            # real field at all -- see python_changelog.md's H1 entries.
            if "outputTurnAxisTorque" in r:
                out["output_TurnAxisTorque"] = r["outputTurnAxisTorque"]
            elif "turnAxis" in r:
                out["output_TurnAxisTorque"] = r["turnAxis"]
            if "directionalAxisX" in r:
                out["output_DirectionalAxis.x"] = r["directionalAxisX"]
            if "directionalAxisY" in r:
                out["output_DirectionalAxis.y"] = r["directionalAxisY"]
            if "px" in r:
                out["location.position.x"] = r["px"]
            if "py" in r:
                out["location.position.y"] = r["py"]
            if "vx" in r:
                out["location.velocity.x"] = r["vx"]
            if "vy" in r:
                out["location.velocity.y"] = r["vy"]
            if "m" in r:
                out["rb2d.mass"] = r["m"]
            if "rot" in r:
                out["rb2d.rotation"] = r["rot"]
            if "angv" in r:
                out["rb2d.angularVelocity"] = r["angv"]

            engines = r.get("engines") or []
            if engines:
                out["throttleOut"] = engines[0].get("throttleOut")
                out["engineOn"] = engines[0].get("engineOn")

            fout.write(json.dumps(out) + "\n")
            n_out += 1

    return {"source_samples": n_in, "written_samples": n_out}


if __name__ == "__main__":
    in_path = sys.argv[1]
    out_path = sys.argv[2]
    end_idx = int(sys.argv[3]) if len(sys.argv) > 3 else None
    stats = convert(in_path, out_path, end_idx)
    print(f"wrote {out_path}")
    print(f"source samples: {stats['source_samples']}, written: {stats['written_samples']}")
