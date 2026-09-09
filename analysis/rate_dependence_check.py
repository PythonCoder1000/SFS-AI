import sys, json, gzip
sys.path.insert(0, 'analysis')
from forward_sim import (build_position_independent_aoa_table, _aero_torque_diagnostic,
                          load_craft_config_from_getforwardstartinfo, PLANET_CONSTANTS)
import sfs_telemetry as st
from pathlib import Path

craft_path = '/Users/christianjin/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe/sfs_probe_forwardstartinfo.json'
craft_config = load_craft_config_from_getforwardstartinfo(craft_path)
body = PLANET_CONSTANTS["Earth"]

flights = [
    ('A2 (+1)', 'analysis/telemetry_flat_2026-09-08_15-03-13_A2_compat.jsonl',
     'analysis/aoa_dragarea_table_direction_sign_matched_pair_2026-09-08_A2.json'),
    ('B (-1)', 'analysis/telemetry_flat_2026-09-08_14-58-04_B_compat.jsonl',
     'analysis/aoa_dragarea_table_direction_sign_matched_pair_2026-09-08_B.json'),
]

rows_out = []
for label, flight_path, aoa_path in flights:
    raw_table = json.loads(Path(aoa_path).read_text())
    aoa_table = build_position_independent_aoa_table(raw_table, craft_config["com_local"], craft_config["rotation_deg"])
    rows = st.load_samples(Path(flight_path))
    for r in rows:
        omega = r.get('rb2d.angularVelocity')
        theta = r.get('rb2d.rotation')
        vx, vy = r.get('location.velocity.x'), r.get('location.velocity.y')
        h = r.get('location.Height')
        comx, comy = r.get('comX'), r.get('comY')
        inertia = r.get('rbInertia')
        real_alpha = r.get('aeroAlphaDeg')
        real_torque = r.get('aeroTorque')
        if None in (omega, theta, vx, vy, h, comx, comy, inertia, real_alpha) or inertia <= 0:
            continue
        v = (vx**2 + vy**2) ** 0.5
        if v < 50.0:
            continue
        diag = _aero_torque_diagnostic(theta, vx, vy, omega, h, aoa_table, (comx, comy),
                                        None, body, inertia, True, False)
        pred_alpha = diag['alpha_torqz_over_inertia_x57']
        if pred_alpha is None:
            continue
        residual = pred_alpha - real_alpha
        rows_out.append({'label': label, 'omega': omega, 'residual': residual,
                          'real_alpha': real_alpha, 'pred_alpha': pred_alpha,
                          'real_torque': real_torque})

print(f"total in-flight samples with full data: {len(rows_out)}")

# correlation of residual vs omega
import statistics
omegas = [r['omega'] for r in rows_out]
residuals = [r['residual'] for r in rows_out]
n = len(omegas)
mean_o = statistics.mean(omegas)
mean_r = statistics.mean(residuals)
cov = sum((o-mean_o)*(res-mean_r) for o,res in zip(omegas,residuals)) / n
sd_o = statistics.pstdev(omegas)
sd_r = statistics.pstdev(residuals)
corr = cov / (sd_o*sd_r) if sd_o>0 and sd_r>0 else None
print(f"corr(residual, omega) = {corr}")

abs_omegas = [abs(o) for o in omegas]
mean_ao = statistics.mean(abs_omegas)
cov2 = sum((ao-mean_ao)*(res-mean_r) for ao,res in zip(abs_omegas,residuals)) / n
sd_ao = statistics.pstdev(abs_omegas)
corr2 = cov2 / (sd_ao*sd_r) if sd_ao>0 and sd_r>0 else None
print(f"corr(residual, |omega|) = {corr2}")

# bucket by omega magnitude
buckets = [(0,10),(10,30),(30,60),(60,100),(100,1000)]
for lo,hi in buckets:
    sel = [r['residual'] for r in rows_out if lo <= abs(r['omega']) < hi]
    if sel:
        print(f"|omega| in [{lo},{hi}): n={len(sel)} mean_residual={statistics.mean(sel):.4f} median={statistics.median(sel):.4f} stdev={statistics.pstdev(sel):.4f}")

print()
print("--- outlier-robust view (median + IQR trimmed, since a few near-zero-crossing samples dominate the raw mean) ---")
abs_res = sorted(abs(r['residual']) for r in rows_out)
p50 = abs_res[len(abs_res)//2]
p90 = abs_res[int(len(abs_res)*0.9)]
p99 = abs_res[int(len(abs_res)*0.99)]
print(f"abs(residual) median={p50:.3f} p90={p90:.3f} p99={p99:.3f} max={abs_res[-1]:.1f}")

# decile split by |omega|, median residual per decile (robust to outliers)
sorted_by_o = sorted(rows_out, key=lambda r: abs(r['omega']))
n = len(sorted_by_o)
dec = n // 10
for i in range(10):
    chunk = sorted_by_o[i*dec: (i+1)*dec if i < 9 else n]
    os_ = [abs(r['omega']) for r in chunk]
    res_ = [r['residual'] for r in chunk]
    abs_res_ = sorted(abs(x) for x in res_)
    med_abs_res = abs_res_[len(abs_res_)//2]
    print(f"decile {i}: |omega| range [{min(os_):.2f},{max(os_):.2f}]  n={len(chunk)}  median(residual)={statistics.median(res_):.3f}  median(|residual|)={med_abs_res:.3f}")

print()
print("--- checking what actually drives the huge-residual outliers (not omega, it turns out) ---")
big = [r for r in rows_out if abs(r['residual']) > 100]
small = [r for r in rows_out if abs(r['residual']) <= 100]
print(f"big-residual samples: {len(big)} / {len(rows_out)}")
if big:
    print("sample of big-residual rows (label, omega, residual, pred_alpha, real_alpha, real_torque):")
    for r in big[:8]:
        print(f"  {r['label']:8s} omega={r['omega']:8.3f} residual={r['residual']:12.2f} pred={r['pred_alpha']:12.2f} real={r['real_alpha']:8.3f} real_torque={r['real_torque']}")

print()
print("--- checking velocity/height for the big-residual near-zero-omega outliers ---")
zero_omega_big = [r for r in rows_out if abs(r['omega']) < 0.1 and abs(r['residual']) > 50]
print(f"count: {len(zero_omega_big)}")
