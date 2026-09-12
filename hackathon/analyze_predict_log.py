import json
import statistics

ticks = []
comps = []
with open('hackathon/manual_flight_log.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r['type'] == 'tick':
            ticks.append(r)
        else:
            comps.append(r)

print(f"ticks: {len(ticks)}  comparisons: {len(comps)}")
print()

alt_min = min(t['altitude_m'] for t in ticks)
alt_max = max(t['altitude_m'] for t in ticks)
print(f"altitude range: {alt_min:.1f}m to {alt_max:.1f}m")
t_max = max(t['t'] for t in ticks)
print(f"flight duration: {t_max:.1f}s")
print()

pos_errs = [c['position_error_m'] for c in comps]
spd_errs = [c['speed_error_mps'] for c in comps]
print("position_error_m: mean={:.1f} median={:.1f} min={:.1f} max={:.1f} stdev={:.1f}".format(
    statistics.mean(pos_errs), statistics.median(pos_errs), min(pos_errs), max(pos_errs), statistics.stdev(pos_errs)))
print("speed_error_mps:  mean={:.1f} median={:.1f} min={:.1f} max={:.1f} stdev={:.1f}".format(
    statistics.mean(spd_errs), statistics.median(spd_errs), min(spd_errs), max(spd_errs), statistics.stdev(spd_errs)))
print()

conf_errs = {}
for c in comps:
    conf_errs.setdefault(c['confidence'], []).append(c['position_error_m'])

print("by confidence:")
for conf, errs in conf_errs.items():
    print(f"  {conf}: n={len(errs)} mean_pos_err={statistics.mean(errs):.1f}m median={statistics.median(errs):.1f}m max={max(errs):.1f}m")
print()

def nearest_alt(t):
    best = min(ticks, key=lambda tk: abs(tk['t'] - t))
    return best['altitude_m']

buckets = {}
for c in comps:
    alt = nearest_alt(c['issued_t'])
    bucket = int(alt // 2000) * 2000
    buckets.setdefault(bucket, []).append(c['position_error_m'])

print("position_error_m by altitude bucket (2km bins):")
for b in sorted(buckets.keys()):
    errs = buckets[b]
    print(f"  {b:6d}-{b+2000:6d}m: n={len(errs):3d}  mean={statistics.mean(errs):7.1f}m  max={max(errs):7.1f}m")

print()
worst = sorted(comps, key=lambda c: -c['position_error_m'])[:5]
print("5 worst comparisons:")
for c in worst:
    print(f"  issued_t={c['issued_t']:.1f}s pos_err={c['position_error_m']:.1f}m spd_err={c['speed_error_mps']:.1f}m/s conf={c['confidence']} throttle_used={c['default_throttle_used']:.2f}")
