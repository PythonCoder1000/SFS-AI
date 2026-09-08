"""
convert_forwardstartinfo_aoa_table.py -- converts the RAW synthetic AoA
sweep JSON auto-written by the 'getforwardstartinfo' probe command
(same format as a standalone 'dragareasweep' call: a flat
{"samples": [{"aoaDeg":..., "dragArea":..., "dragCopX":..., "dragCopY":...}, ...]}
list) into the "bins" dict format aoa_dragarea.py's build_table() /
lookup_field() expect.

Why this exists (see bookkeeping/active_state.md 2026-09-07 and
docs/high_level_checklist.md's forward-integrator entry): the raw sweep
is a direct, noise-free, complete-coverage read of the game's own real
CalculateDragForce at synthetic angles -- there is no need for the
median-per-bin statistical binning build_table() does for noisy
flight-derived data. This is a straight one-sample-per-bin remap, kept
as its own small script (rather than a scratch one-off) so it's
reusable for every future getforwardstartinfo/dragareasweep table.

Usage:
    python3 convert_forwardstartinfo_aoa_table.py <raw_sweep.json> <out_bins.json> [known_part_count]
"""

import json
import sys
from pathlib import Path

VALUE_FIELDS = ("dragArea", "dragCopX", "dragCopY")


def convert(raw_path: str, out_path: str, known_part_count: int | None = None) -> dict:
    raw = json.loads(Path(raw_path).read_text())
    samples = raw["samples"]
    step_deg = raw.get("stepDeg", 0.5)

    bins = []
    for s in samples:
        entry = {"aoa_center": round(s["aoaDeg"], 3), "count": 1}
        for f in VALUE_FIELDS:
            entry[f"median_{f}"] = s.get(f)
            entry[f"stddev_{f}"] = 0.0  # exact synthetic read, not a statistical sample
        bins.append(entry)

    table = {
        "bin_width_deg": step_deg,
        "value_fields": list(VALUE_FIELDS),
        "craft_signature": f"getforwardstartinfo:{raw.get('blueprintName', 'unknown')}",
        "part_count_consistent": True,
        "part_counts_seen": [known_part_count] if known_part_count is not None else [],
        "source_sample_count": len(samples),
        "skipped_samples_no_aoa": 0,
        "empty_bin_count": 0,
        "empty_bin_centers": [],
        "low_confidence_bin_count": 0,
        "bins": bins,
        "source_note": (
            "Converted from a raw getforwardstartinfo/dragareasweep synthetic "
            "sweep, NOT built via aoa_dragarea.py's build_table() from noisy "
            "flight telemetry -- every bin is a single exact game-engine read, "
            "not a statistical median. See convert_forwardstartinfo_aoa_table.py."
        ),
        "source_raw_file": str(Path(raw_path).name),
        "real_rotation_deg_at_capture": raw.get("realRotationDeg"),
    }

    Path(out_path).write_text(json.dumps(table, indent=None))
    return table


if __name__ == "__main__":
    raw_path = sys.argv[1]
    out_path = sys.argv[2]
    known_part_count = int(sys.argv[3]) if len(sys.argv) > 3 else None
    table = convert(raw_path, out_path, known_part_count)
    print(f"wrote {out_path}")
    print(f"bins: {len(table['bins'])} @ {table['bin_width_deg']} deg width "
          f"(source samples: {table['source_sample_count']})")
    print(f"craft_signature: {table['craft_signature']}")
