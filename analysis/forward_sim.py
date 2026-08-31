"""
forward_sim.py -- forward-integrates the CONFIRMED gravity+drag formula
(reused verbatim from sfs_telemetry.py's predicted_gravity_drag_accel/
atmospheric_density, not reimplemented) starting from a real telemetry
sample, for a given duration. Built 2026-08-29 to power an interactive
predicted-vs-actual trajectory demo, using the physics validated that
same day at 0.098% median error across 70,858 pairs (see
docs/high_level_checklist.md, "Drag FORCE formula").

RK4 integration, not Euler -- accurate enough at a moderate timestep
(default dt=0.25s) to predict minutes ahead without needing to match
the real telemetry's own 60Hz sampling rate, which would be needlessly
slow for a multi-minute forward prediction.

dragArea is held CONSTANT at the starting sample's real recorded value
for the whole prediction window -- a deliberate simplification, not an
oversight: dragArea depends on the rocket's orientation relative to its
velocity vector, which stays roughly fixed during an unpowered coast
(the regime this demo is meant for). This assumption would need
revisiting for a prediction window that includes active
thrust/rotation/staging.
"""

import json
import math
import sys
from pathlib import Path

PLANET_CONSTANTS = {
    "Earth": {
        "radius_m": 314970.0,
        "mu": 972219788820.0,
        "atmosphere_height_m": 30000.0,
        "rho0": 0.005,
        "curve": 10.0,
    },
}


def atmospheric_density(h: float, body: dict) -> float:
    """Verbatim copy of sfs_telemetry.py's confirmed formula."""
    H = body["atmosphere_height_m"]
    if h < 0 or h > H:
        return 0.0
    curve = body["curve"]
    return (math.exp(-curve * h / H) - math.exp(-curve)) * body["rho0"]


def accel(px: float, py: float, vx: float, vy: float, m: float,
          drag_area: float, body: dict) -> tuple[float, float]:
    """Verbatim port of sfs_telemetry.py's predicted_gravity_drag_accel,
    restructured to take raw state instead of a sample dict (this
    function is called many times per RK4 step, on intermediate states
    that never existed as a real telemetry sample)."""
    r = math.hypot(px, py)
    if r == 0:
        return 0.0, 0.0
    g_mag = body["mu"] / (r * r)
    gx, gy = -g_mag * (px / r), -g_mag * (py / r)
    v_mag = math.hypot(vx, vy)
    h = r - body["radius_m"]
    density = atmospheric_density(h, body)
    if v_mag > 0 and density > 0:
        drag_force_mag = 1.5 * drag_area * v_mag * v_mag * density
        ax_drag = -(vx / v_mag) * drag_force_mag / m
        ay_drag = -(vy / v_mag) * drag_force_mag / m
    else:
        ax_drag = ay_drag = 0.0
    return gx + ax_drag, gy + ay_drag


def _rk4_step(px, py, vx, vy, m, drag_area, body, dt):
    def deriv(px, py, vx, vy):
        ax, ay = accel(px, py, vx, vy, m, drag_area, body)
        return vx, vy, ax, ay
    k1 = deriv(px, py, vx, vy)
    k2 = deriv(px + k1[0] * dt / 2, py + k1[1] * dt / 2, vx + k1[2] * dt / 2, vy + k1[3] * dt / 2)
    k3 = deriv(px + k2[0] * dt / 2, py + k2[1] * dt / 2, vx + k2[2] * dt / 2, vy + k2[3] * dt / 2)
    k4 = deriv(px + k3[0] * dt, py + k3[1] * dt, vx + k3[2] * dt, vy + k3[3] * dt)
    px2 = px + (dt / 6) * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
    py2 = py + (dt / 6) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
    vx2 = vx + (dt / 6) * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
    vy2 = vy + (dt / 6) * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3])
    return px2, py2, vx2, vy2


def forward_simulate(start: dict, duration_s: float, dt: float = 0.25,
                      body_name: str = "Earth") -> list[dict]:
    """Forward-integrates from a real telemetry sample's state (px, py,
    vx, vy, m, dragArea) for duration_s using RK4 + the confirmed
    gravity+drag formula. Returns a list of {t (relative, seconds from
    start), px, py, vx, vy, h, v} points, first entry being the
    (unmodified) starting state itself.
    """
    body = PLANET_CONSTANTS[body_name]
    px, py, vx, vy, m = start["px"], start["py"], start["vx"], start["vy"], start["m"]
    drag_area = start.get("dragArea") or 0.0
    points = [{"t": 0.0, "px": px, "py": py, "vx": vx, "vy": vy,
               "h": math.hypot(px, py) - body["radius_m"], "v": math.hypot(vx, vy)}]
    steps = int(duration_s / dt)
    for i in range(steps):
        px, py, vx, vy = _rk4_step(px, py, vx, vy, m, drag_area, body, dt)
        t = (i + 1) * dt
        points.append({"t": round(t, 3), "px": px, "py": py, "vx": vx, "vy": vy,
                        "h": math.hypot(px, py) - body["radius_m"], "v": math.hypot(vx, vy)})
    return points


def prep_demo_data(src_path: str, out_path: str, n_downsample: int = 2500) -> dict:
    """Loads a real archived flight, downsamples it for embedding in an
    interactive artifact, and runs a self-test (10s forward-sim from a
    mid-flight sample, compared against the REAL recorded trajectory at
    the matching later timestamp) so the demo ships with a known,
    reported accuracy figure rather than an unverified assumption that
    the port matches the original formula.
    """
    samples = []
    with open(src_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    n = len(samples)
    step = max(1, n // n_downsample)
    t0 = samples[0]["t"]
    downsampled = []
    for i in range(0, n, step):
        s = samples[i]
        downsampled.append({
            "idx": i, "t": round(s["t"] - t0, 3), "h": s.get("h"),
            "px": s.get("px"), "py": s.get("py"), "vx": s.get("vx"), "vy": s.get("vy"),
            "m": s.get("m"), "dragArea": s.get("dragArea"), "vv": s.get("vv"),
        })

    test_idx = n // 3
    test_start = samples[test_idx]
    sim = forward_simulate(test_start, 10.0, dt=0.1)
    target_t = test_start["t"] + 10.0
    real_at_target = min(samples, key=lambda s: abs(s["t"] - target_t))
    pred_final = sim[-1]
    h_error_pct = abs(pred_final["h"] - real_at_target["h"]) / max(abs(real_at_target["h"]), 1) * 100

    result = {
        "meta": {
            "total_real_samples": n,
            "downsampled_count": len(downsampled),
            "t0_absolute": t0,
            "planet_constants": PLANET_CONSTANTS["Earth"],
            "self_test": {
                "start_idx": test_idx, "start_t_rel": round(test_start["t"] - t0, 2),
                "duration_s": 10.0,
                "predicted_h": pred_final["h"], "real_h": real_at_target["h"],
                "h_error_pct": h_error_pct,
            },
        },
        "samples": downsampled,
    }
    Path(out_path).write_text(json.dumps(result))
    return result["meta"]


if __name__ == "__main__":
    meta = prep_demo_data(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2500)
    print(f"wrote {sys.argv[2]}: {meta['downsampled_count']} downsampled points "
          f"from {meta['total_real_samples']} real samples")
    print(f"self-test: 10s forward-sim from idx {meta['self_test']['start_idx']} -> "
          f"h_error_pct={meta['self_test']['h_error_pct']:.4f}%")
