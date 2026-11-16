#!/usr/bin/env python3
"""Stage 3 walk scoring: loop closure, checkpoint stops, ZUPT
detector characterisation (experiment 3). Estimators run through
replay.py/sim.py UNCHANGED; truth comes only from the protocol:
start=end point, marked 10 s checkpoint stops, initial/final
static windows. No phone waypoints were recorded, so stop truth
positions are the receiver's own median fix during each stop
(disclosed; GNSS stop errors are a reference floor, not a score).
"""
import json, math, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, replay

ORIG = sys.argv[1] if len(sys.argv) > 1 else 'capture-20261114-145632.txt'
SEG2 = sys.argv[2] if len(sys.argv) > 2 else 'walk_seg2_forest_loop.hostclean.txt'

# ---- one pass over the original: seg-2 marks + first fix, host seconds
hp = re.compile(r'^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) (.*)$')
seg, marks, firstfix = 0, [], None
for raw in open(ORIG, errors='replace'):
    m = hp.match(raw.rstrip('\n'))
    if not m:
        continue
    t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
         + int(m.group(3)) + int(m.group(4)) / 1000.0)
    line = m.group(5)
    if line.startswith('#MARK,CAPTURE START'):
        seg += 1
        continue
    if seg != 2:
        continue
    if line.startswith('#MARK,'):
        marks.append((t, line.split(',')[1].strip()))
    if firstfix is None and 'GGA,' in line and '$' in line:
        f = line.split('$')[1].split('*')[0].split(',')
        if f[0] in ('GPGGA', 'GNGGA'):
            try:
                if int(f[6]) >= 1:
                    firstfix = t
            except (ValueError, IndexError):
                pass
assert firstfix and marks, 'seg2 marks/firstfix not found'
T0 = firstfix
rel = [(t - T0, n) for t, n in marks]
walk_start = next(t for t, n in rel if n == 'WALK START')
walk_end = next(t for t, n in rel if n == 'WALK END')
cps_raw = [t for t, n in rel if n.startswith('CHECKPOINT')]
cps = []
for t in cps_raw:  # cluster bursts (<3 s apart) into one stop
    if not cps or t - cps[-1] > 3.0:
        cps.append(t)
print(f'seg2: first fix at rel 0; WALK START {walk_start:.1f} s, '
      f'WALK END {walk_end:.1f} s, {len(cps_raw)} checkpoint marks '
      f'-> {len(cps)} distinct stops')

# ---- load + adapt (replay machinery, estimators untouched)
imu, fixes = replay.parse_capture(SEG2)
acc_m, gyro_m, eps, meta = replay.adapt(imu, fixes, fwd='x', uere=2.5)
n = meta['n']
print(f'adapted: N={n} ({meta["duration_s"]:.0f} s), {meta["n_fixes"]} fix epochs')
fix_at = {}
for e in eps:
    fix_at[e['k']] = e['fix']

def fix_median(t0, t1):
    ks = [k for k in fix_at if t0 <= k * sim.DT <= t1]
    if len(ks) < 3:
        return None
    return np.median([fix_at[k] for k in ks], axis=0)

# ---- protocol truth windows (replay seconds)
start_win = (0.0, walk_start + 28.0)          # incl. 30 s hold
end_win = (walk_end, meta['duration_s'])      # stood at end point
stop_wins = [(c, c + 10.0) for c in cps]
start_pos = fix_median(*start_win)
end_pos = fix_median(*end_win)
stop_pos = [fix_median(a, b) for a, b in stop_wins]
print(f'loop check: |median fix start - end| = '
      f'{np.linalg.norm(start_pos - end_pos):.2f} m '
      f'(must be small: same physical point)')
for i, (w, p) in enumerate(zip(stop_wins, stop_pos)):
    print(f'  stop {i+1}: t={w[0]:.0f}-{w[1]:.0f} s  fix median '
          f'{None if p is None else np.round(p, 1)}')

# ---- run the estimators (measured Stage-2 noise), keep traces
def run_all(sig_a=None, sig_g=None):
    if sig_a is not None:
        sim.SIG_A, sim.SIG_G = sig_a, sig_g
        dt = sim.DT
        sim.QD = np.diag([(sim.SIG_A * dt ** 2 / 2) ** 2] * 2 +
                         [(sim.SIG_A * dt) ** 2] * 2 +
                         [(sim.SIG_G * dt) ** 2, (1e-4 * np.sqrt(dt)) ** 2] +
                         [(5e-3 * np.sqrt(dt)) ** 2] * 2)
    sim.N = n
    sim.TRUTH = dict(pos=np.zeros((n, 2)))
    out = {}
    out['GNSS'] = sim.run_gnss(eps)
    out['INS'] = sim.run_ins('replay', acc_m, gyro_m, eps, 0)
    out['LC-EKF'] = sim.run_lc('replay', acc_m, gyro_m, eps, 0)[0]
    out['LC-UKF'] = sim.run_ukf('replay', acc_m, gyro_m, eps, 0)
    out['ZUPT-EKF'] = sim.run_lc('replay', acc_m, gyro_m, eps, 0, zupt=True)[0]
    out['ADAPT-EKF'] = sim.run_lc('replay', acc_m, gyro_m, eps, 0, adapt=True)[0]
    _, st = sim.run_lc('replay', acc_m, gyro_m, eps, 0, store=True)
    out['RTS-SMOOTH'] = sim.rts_smooth(st)
    return out

def med_in(est, t0, t1):
    k0, k1 = int(t0 / sim.DT), min(n, int(t1 / sim.DT))
    return np.median(est[k0:k1], axis=0)

def wander_in(est, t0, t1):
    k0, k1 = int(t0 / sim.DT), min(n, int(t1 / sim.DT))
    seg = est[k0:k1]
    return float(np.abs(seg - np.median(seg, axis=0)).max())

traces = run_all(1.8066e-3, 1.4688e-4)   # Stage-2 measured noise
report = {'windows': dict(start=start_win, end=end_win, stops=stop_wins),
          'loop_fix_gap_m': float(np.linalg.norm(start_pos - end_pos)),
          'methods': {}}
for name, est in traces.items():
    s = med_in(est, *start_win)
    e = med_in(est, *end_win)
    stop_err = []
    stop_wan = []
    for (a, b), p in zip(stop_wins, stop_pos):
        if p is None:
            continue
        stop_err.append(float(np.linalg.norm(med_in(est, a, b) - p)))
        stop_wan.append(wander_in(est, a, b))
    report['methods'][name] = dict(
        closure_m=float(np.linalg.norm(e - s)),
        end_vs_startfix_m=float(np.linalg.norm(e - start_pos)),
        stop_err_med_m=float(np.median(stop_err)),
        stop_err_max_m=float(np.max(stop_err)),
        stop_wander_med_m=float(np.median(stop_wan)),
        stop_errors_m=[round(x, 2) for x in stop_err])

# ---- experiment 3: the paper's ZUPT detector vs protocol truth
win_a, win_g, fire = [], [], np.zeros(n, bool)
for k in range(n):
    win_a.append(acc_m[k]); win_g.append(gyro_m[k])
    if len(win_a) > 10:
        win_a.pop(0); win_g.pop(0)
    if len(win_a) == 10:
        wa, wg = np.array(win_a), np.array(win_g)
        fire[k] = (wa.std(axis=0).max() < 0.20 and np.abs(wg).std() < 0.01
                   and np.abs(wg).mean() < 0.03)
still = np.zeros(n, bool)
for a, b in [start_win, end_win] + stop_wins:
    still[int(a / sim.DT):int(b / sim.DT)] = True
guard = np.zeros(n, bool)  # 2 s around every still/walk transition
idx = np.where(np.diff(still.astype(int)) != 0)[0]
for i in idx:
    guard[max(0, i - 20):i + 20] = True
scored = ~guard
in_stop = scored & still
in_walk = scored & ~still
report['zupt_detector'] = dict(
    fire_frac_in_stops=float(fire[in_stop].mean()),
    fire_frac_while_walking=float(fire[in_walk].mean()),
    n_stop_samples=int(in_stop.sum()), n_walk_samples=int(in_walk.sum()))
json.dump(report, open('walk_seg2_scores.json', 'w'), indent=1)

print('\n%-11s %8s %8s %9s %9s' % ('method', 'closure', 'stopMed', 'stopMax', 'wander'))
for name, r in report['methods'].items():
    print('%-11s %8.2f %8.2f %9.2f %9.2f' % (name, r['closure_m'],
          r['stop_err_med_m'], r['stop_err_max_m'], r['stop_wander_med_m']))
z = report['zupt_detector']
print(f"\nZUPT detector: fires on {z['fire_frac_in_stops']*100:.1f}% of "
      f"stationary samples, {z['fire_frac_while_walking']*100:.2f}% of "
      f"walking samples")
print('wrote walk_seg2_scores.json')
