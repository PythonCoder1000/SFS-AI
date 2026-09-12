"""Offline closed-loop harness: runs hackathon/controller.py's PD logic
against forward_sim.py instead of the live game.

Same control cadence, same act() throttle clamp, same gains. Lets gain
tuning happen in seconds instead of costing a live flight.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import forward_sim as fsim  # noqa: E402

R = fsim.PLANET_CONSTANTS["Earth"]["radius_m"]

CFG = fsim.load_craft_config_from_getforwardstartinfo(
    str(ROOT / "analysis/sfs_probe_forwardstartinfo_prediction_test.json"),
    firing_snapshot_path=str(ROOT / "analysis/sfs_probe_forwardstartinfo_firing.json"))
AOA = json.load(open(ROOT / "analysis/aoa_dragarea_table_prediction_test_flight.json"))

MAX_THROTTLE_STEP = 0.3   # mirrors agent_interface.act()
DRY_MASS_T = 8.0          # not in the dump; keeps fuel finite


def clamp_throttle(prev, want, enabled=True):
    if not enabled:
        return want
    d = max(-MAX_THROTTLE_STEP, min(MAX_THROTTLE_STEP, want - prev))
    return prev + d


def pd(target, alt, vsp, kp, kd, smoothed_vsp=None, alpha=0.3, deadband=0.0, last_thr=0.0):
    """Same math as hackathon/controller.py's AltitudePD, including the
    EMA smoothing + deadband anti-chatter fix, so the offline harness
    reflects what actually ships, not a stripped-down version of it."""
    if smoothed_vsp is None:
        smoothed_vsp = vsp
    else:
        smoothed_vsp = alpha * vsp + (1 - alpha) * smoothed_vsp
    raw = kp * (target - alt) - kd * smoothed_vsp
    clamped = max(0.0, min(1.0, raw))
    if deadband > 0 and abs(clamped - last_thr) < deadband:
        return last_thr, smoothed_vsp
    return clamped, smoothed_vsp


def run(kp=0.0012, kd=0.3, target=20000.0, tol=250.0, poll_hz=5.0,
        max_t=600.0, clamp=True, deadband=0.05, alpha=0.3, label=""):
    craft = dict(CFG)
    craft["dry_mass_t"] = DRY_MASS_T

    state = {"px": 0.0, "py": R + 2.0, "vx": 0.0, "vy": 0.0,
             "m": craft["mass"], "rot": 0.0, "angv": 0.0}
    dt = 1.0 / poll_hz
    thr = 0.0
    smoothed_vsp = None
    t = 0.0
    peak = 0.0
    hit = None
    fuel_out_t = None
    trace = []

    while t < max_t:
        r = math.hypot(state["px"], state["py"])
        alt = r - R
        vsp = (state["px"] * state["vx"] + state["py"] * state["vy"]) / r
        peak = max(peak, alt)

        dry_kg = DRY_MASS_T * 1000.0
        if fuel_out_t is None and state["m"] <= dry_kg * 1.001:
            fuel_out_t = t

        if abs(target - alt) <= tol:
            if hit is None:
                hit = (t, alt, vsp, thr)
            want, smoothed_vsp = 0.0, smoothed_vsp
            thr = clamp_throttle(thr, want, False)  # cut works instantly once in band
            sched = fsim.HypotheticalControlSchedule([], default_throttle=thr)
        else:
            want, smoothed_vsp = pd(target, alt, vsp, kp, kd, smoothed_vsp, alpha, deadband, thr)
            thr = clamp_throttle(thr, want, clamp)
            sched = fsim.HypotheticalControlSchedule([], default_throttle=thr)

        traj = fsim.forward_simulate(
            state, dt, dt=dt / 2, body_name="Earth", aoa_table=AOA,
            craft_config=craft, control_schedule=sched,
            flags={"aero_torque_aoa_gate_deg": 2.0},
        )
        f = traj[-1]
        if f.get("collided") and t > 1.0:
            trace.append((t, alt, vsp, thr, state["m"], "COLLIDED"))
            break
        state = {"px": f["px"], "py": f["py"], "vx": f["vx"], "vy": f["vy"],
                 "m": f["m"], "rot": f["theta_deg"], "angv": f["omega_degs"]}
        trace.append((t, alt, vsp, thr, state["m"], ""))
        t += dt

    return {"label": label, "peak_m": peak, "hit": hit, "final_alt": alt,
            "final_vsp": vsp, "t_end": t, "trace": trace,
            "fuel_out_t": fuel_out_t, "final_mass": state["m"],
            "dry_mass_kg": DRY_MASS_T * 1000.0}


def summarize(r):
    h = r["hit"]
    hs = f"t={h[0]:.1f}s alt={h[1]:.0f}m vsp={h[2]:.0f}m/s thr={h[3]:.2f}" if h else "NEVER"
    fuel = f"fuel_out@t={r['fuel_out_t']:.1f}s" if r["fuel_out_t"] else \
           f"fuel_left={(r['final_mass'] - r['dry_mass_kg'])/1000:.1f}t"
    print(f"{r['label']:<34} peak={r['peak_m']:9.0f}m  reached: {hs:<38} {fuel}")


if __name__ == "__main__":
    print("=== fuel/thrust ceiling check (longer run, shipped gains) ===")
    summarize(run(kp=0.0012, kd=0.3, max_t=600.0, label="shipped gains, max_t=600"))

    print("\n=== gain sweep (kp x kd/kp ratio), max_t=400 ===")
    results = []
    for kp in (0.0008, 0.0012, 0.002, 0.003):
        for ratio in (50, 100, 150, 250):
            kd = kp * ratio
            lbl = f"kp={kp} kd/kp={ratio}"
            res = run(kp=kp, kd=kd, max_t=400.0, label=lbl)
            results.append(res)
            summarize(res)

    print("\n=== best candidates (reached band, sorted by time) ===")
    reached = [r for r in results if r["hit"] is not None]
    reached.sort(key=lambda r: r["hit"][0])
    for r in reached[:5]:
        summarize(r)
    if not reached:
        print("none reached the tolerance band in 400s")
