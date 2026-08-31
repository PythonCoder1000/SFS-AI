"""
prep_prediction_demo.py -- prepares a downsampled, enriched JSON payload
for the no-graph predicted-vs-actual demo (numeric only, two sliders).

For every REAL sample kept in the downsample, computes:
  - actual acceleration (ax, ay): central finite-difference of vx,vy
    over real t, using the ORIGINAL (undownsampled) neighbors so it's
    not distorted by the downsample stride.
  - actual drag (accel magnitude, m/s^2): the CONFIRMED drag law
    (1.5 * dragArea * v^2 * density(h)) / m, evaluated with that
    sample's own REAL recorded dragArea/v/h -- i.e. "what the confirmed
    physics law says drag should be, fed the real per-sample inputs",
    as distinct from the predicted value below (constant starting
    dragArea, simulated v/h).

Run on the FULL (undownsampled) file for the finite-difference step,
then strided down for the embed payload.
"""
import json
import math
import sys

PLANET = {
    "radius_m": 314970.0,
    "mu": 972219788820.0,
    "atmosphere_height_m": 30000.0,
    "rho0": 0.005,
    "curve": 10.0,
}


def density(h):
    H = PLANET["atmosphere_height_m"]
    if h < 0 or h > H:
        return 0.0
    return (math.exp(-PLANET["curve"] * h / H) - math.exp(-PLANET["curve"])) * PLANET["rho0"]


def drag_accel_mag(v, h, drag_area, m):
    rho = density(h)
    if rho <= 0 or v <= 0 or m <= 0:
        return 0.0
    return (1.5 * drag_area * v * v * rho) / m


def load(path):
    samples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            samples.append(s)
    return samples


def main(src, out, target_n=2500):
    samples = load(src)
    n = len(samples)
    t0 = samples[0]["t"]

    # central finite-difference actual acceleration, full resolution
    ax = [0.0] * n
    ay = [0.0] * n
    for i in range(1, n - 1):
        dt = samples[i + 1]["t"] - samples[i - 1]["t"]
        if dt <= 0:
            continue
        ax[i] = (samples[i + 1]["vx"] - samples[i - 1]["vx"]) / dt
        ay[i] = (samples[i + 1]["vy"] - samples[i - 1]["vy"]) / dt
    ax[0], ay[0] = ax[1], ay[1]
    ax[-1], ay[-1] = ax[-2], ay[-2]

    step = max(1, n // target_n)
    out_samples = []
    for i in range(0, n, step):
        s = samples[i]
        v = math.hypot(s["vx"], s["vy"])
        da = s.get("dragArea") or 0.0
        out_samples.append({
            "t": round(s["t"] - t0, 3),
            "h": s.get("h"),
            "px": s.get("px"), "py": s.get("py"),
            "vx": s.get("vx"), "vy": s.get("vy"),
            "m": s.get("m"),
            "dragArea": da,
            "ax": ax[i], "ay": ay[i],
            "drag": drag_accel_mag(v, s.get("h", 0.0), da, s.get("m", 1.0)),
        })
    # always include the true last sample so "predict to the very end" has a target
    if out_samples[-1]["t"] != round(samples[-1]["t"] - t0, 3):
        s = samples[-1]
        v = math.hypot(s["vx"], s["vy"])
        da = s.get("dragArea") or 0.0
        out_samples.append({
            "t": round(s["t"] - t0, 3),
            "h": s.get("h"), "px": s.get("px"), "py": s.get("py"),
            "vx": s.get("vx"), "vy": s.get("vy"), "m": s.get("m"),
            "dragArea": da, "ax": ax[-1], "ay": ay[-1],
            "drag": drag_accel_mag(v, s.get("h", 0.0), da, s.get("m", 1.0)),
        })

    duration = out_samples[-1]["t"]
    payload = {
        "meta": {
            "total_real_samples": n,
            "downsampled_count": len(out_samples),
            "duration_s": duration,
            "planet": PLANET,
        },
        "samples": out_samples,
    }
    with open(out, "w") as f:
        json.dump(payload, f)
    print(f"wrote {out}: {len(out_samples)} points from {n} real samples, duration={duration:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2500)
