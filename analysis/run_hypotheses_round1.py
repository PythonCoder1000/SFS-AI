import sys, json
sys.path.insert(0, 'analysis')
from eval_harness import eval_config

configs = [
    ("BASELINE (dt=0.25,rk4,before,static-table)", dict(start_t=2.0, horizon=30.0, dt=0.25)),
    ("H1 use_real_aero=True (ceiling ref, not deployable)", dict(start_t=2.0, horizon=30.0, dt=0.25, use_real_aero=True)),
    ("H2 dt=1/60 fine step", dict(start_t=2.0, horizon=30.0, dt=1/60)),
    ("H3 integrator=symplectic_euler", dict(start_t=2.0, horizon=30.0, dt=0.25, integrator='symplectic_euler')),
    ("H4 sas_order=after", dict(start_t=2.0, horizon=30.0, dt=0.25, sas_order='after')),
    ("H5 box2d_rotation_clamp=False", dict(start_t=2.0, horizon=30.0, dt=0.25, flags={'box2d_rotation_clamp': False})),
    ("H6 live_inertia=False", dict(start_t=2.0, horizon=30.0, dt=0.25, flags={'live_inertia': False})),
    ("H7 coast-only window (post-turns, t=24,h=8)", dict(start_t=24.0, horizon=8.0, dt=0.25)),
    ("H7b pre-turn ascent window (t=0,h=5.5)", dict(start_t=0.1, horizon=5.5, dt=0.25)),
]

results = []
for label, kwargs in configs:
    try:
        r = eval_config(**kwargs)
        pct = r['pos_err_pct']
        print(f"{label:55s} pos_err%={pct:8.3f}  rot_err_final={r['rot_err_deg']:8.2f}  angv_err_final={r['angv_err_degs']:10.2f}")
        results.append((label, r))
    except Exception as e:
        print(f"{label:55s} FAILED: {e}")
        results.append((label, None))

json.dump({label: (r if r is None else {k:v for k,v in r.items() if k!='summary'}) for label,r in results},
          open('analysis/round1_results.json','w'), indent=2, default=str)
