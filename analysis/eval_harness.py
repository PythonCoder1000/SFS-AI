"""
30s-ahead prediction error evaluation harness. See module docstring
notes below for metric definition and data-limitation caveats.
"""
import sys, json, math, statistics
sys.path.insert(0, 'analysis')
from forward_sim import test_against_run_trajectory
import sfs_telemetry as st
from pathlib import Path

FLIGHT_30S = 'analysis/telemetry_flat_2026-09-08_12-18-10_compat.jsonl'
AOA_30S = 'analysis/aoa_dragarea_table_atmosphere_scripted_turns_2026-09-08.json'
CRAFT_CONFIG = '/Users/christianjin/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/SpaceflightSimulatorGame.app/Mods/SFSProbe/sfs_probe_forwardstartinfo.json'

_ROWS_CACHE = {}
def _rows(flight):
    if flight not in _ROWS_CACHE:
        _ROWS_CACHE[flight] = st.load_samples(Path(flight))
    return _ROWS_CACHE[flight]

def real_displacement(flight, start_t, horizon):
    rows = _rows(flight)
    t0 = rows[0]['t']
    i0 = min(range(len(rows)), key=lambda i: abs(rows[i]['t'] - t0 - start_t))
    i1 = min(range(len(rows)), key=lambda i: abs(rows[i]['t'] - t0 - start_t - horizon))
    r0, r1 = rows[i0], rows[i1]
    return math.hypot(r1['location.position.x']-r0['location.position.x'],
                       r1['location.position.y']-r0['location.position.y'])

def eval_config(start_t, horizon, dt=0.25, flags=None, integrator='rk4',
                 sas_order='before', use_real_aero=False, flight=None, aoa=None,
                 stride=None, throttle_field='throttleOut'):
    flight = flight or FLIGHT_30S
    aoa = aoa or AOA_30S
    if stride is None:
        stride = max(1, int(round((horizon / dt) / 40)))
    result = test_against_run_trajectory(
        flight, CRAFT_CONFIG, start_t, horizon, dt=dt, aoa_table_path=aoa,
        throttle_field=throttle_field, flags=flags, stride=stride,
        integrator=integrator, use_real_aero=use_real_aero, sas_order=sas_order)
    final = result['steps'][-1]
    disp = real_displacement(flight, start_t, horizon)
    pos_err_pct = (final['position_offset_m'] / disp * 100) if disp > 1e-6 else None
    return {
        'pos_err_m': final['position_offset_m'],
        'real_disp_m': disp,
        'pos_err_pct': pos_err_pct,
        'rot_err_deg': final['rotation_error_deg'],
        'angv_err_degs': final['angular_velocity_error_degs'],
        'summary': result['summary'],
    }

if __name__ == '__main__':
    r = eval_config(2.0, 30.0, dt=0.25)
    print(json.dumps(r, indent=2, default=str))
