#!/usr/bin/env python3
"""Phase 1 / M6: walk-replay sensitivity - heading-init rotation,
init-draw seed spread, QD sweep, unmarked-stop scan.
Usage: p1_m6.py SEG2_HOSTCLEAN WINDOWS_JSON TAG
Run with cwd containing sim.py + replay.py (code/simulation)."""
import json, sys
import numpy as np
sys.path.insert(0, '.')
import sim, replay

SEG2, WINJ, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
W = json.load(open(WINJ))
start_win = tuple(W['start']); end_win = tuple(W['end'])
stop_wins = [tuple(s) for s in W['stops']]
walk_start = start_win[1] - 28.0

imu, fixes = replay.parse_capture(SEG2)
acc0, gyro0, eps0, meta = replay.adapt(imu, fixes, fwd='x', uere=2.5)
n = meta['n']
print('M6 %s: N=%d, %d stops' % (TAG, n, len(stop_wins)), flush=True)

def fix_median(eps, t0, t1):
    fa = {e['k']: e['fix'] for e in eps}
    ks = [k for k in fa if t0 <= k * sim.DT <= t1]
    return np.median([fa[k] for k in ks], axis=0) if len(ks) >= 3 else None

def med_in(est, t0, t1):
    return np.median(est[int(t0 / sim.DT):min(n, int(t1 / sim.DT))], axis=0)

def run_variant(seed=0, qscale=1.0, rotate=False, methods=('LC-EKF', 'LC-UKF', 'ZUPT-EKF', 'RTS-SMOOTH')):
    acc_m = acc0.copy(); gyro_m = gyro0.copy()
    eps = [dict(e) for e in eps0]
    if rotate:
        pa = fix_median(eps0, *start_win)
        pb = fix_median(eps0, walk_start + 15.0, walk_start + 30.0)
        th = np.arctan2(*(pb - pa)[::-1])
        c, s = np.cos(-th), np.sin(-th)
        R = np.array([[c, -s], [s, c]])
        for e in eps:
            if e['fix'] is not None:
                e['fix'] = R @ e['fix']
        acc_m[:, :2] = acc_m[:, :2] @ R.T
    dt = sim.DT
    sim.SIG_A, sim.SIG_G = 1.8066e-3, 1.4688e-4
    sim.QD = np.diag([(sim.SIG_A * dt ** 2 / 2) ** 2] * 2 +
                     [(sim.SIG_A * dt) ** 2] * 2 +
                     [(sim.SIG_G * dt) ** 2, (1e-4 * np.sqrt(dt)) ** 2] +
                     [(5e-3 * np.sqrt(dt)) ** 2] * 2) * qscale
    sim.N = n
    sim.TRUTH = dict(pos=np.zeros((n, 2)))
    start_pos = fix_median(eps, *start_win)
    stop_pos = [fix_median(eps, a, b) for a, b in stop_wins]
    out = {}
    if 'LC-EKF' in methods:
        out['LC-EKF'] = sim.run_lc('replay', acc_m, gyro_m, eps, seed)[0]
    if 'LC-UKF' in methods:
        out['LC-UKF'] = sim.run_ukf('replay', acc_m, gyro_m, eps, seed)
    if 'ZUPT-EKF' in methods:
        out['ZUPT-EKF'] = sim.run_lc('replay', acc_m, gyro_m, eps, seed, zupt=True)[0]
    if 'RTS-SMOOTH' in methods:
        _, st = sim.run_lc('replay', acc_m, gyro_m, eps, seed, store=True)
        out['RTS-SMOOTH'] = sim.rts_smooth(st)
    res = {}
    for name, est in out.items():
        se = med_in(est, *start_win); ee = med_in(est, *end_win)
        errs = [float(np.linalg.norm(med_in(est, a, b) - p))
                for (a, b), p in zip(stop_wins, stop_pos) if p is not None]
        res[name] = (float(np.linalg.norm(ee - se)),
                     float(np.median(errs)), float(np.max(errs)))
    return res

def show(tag, res):
    for name, (cl, sm, sx) in res.items():
        print('M6 %s %-10s closure %6.2f stopMed %6.2f stopMax %6.2f'
              % (tag, name, cl, sm, sx), flush=True)

show(TAG + ' baseline', run_variant())
show(TAG + ' rotate', run_variant(rotate=True))
show(TAG + ' q10', run_variant(qscale=10.0))
show(TAG + ' q100', run_variant(qscale=100.0))
for s in range(1, 10):
    r = run_variant(seed=s, methods=('LC-EKF', 'ZUPT-EKF'))
    show(TAG + ' seed%d' % s, r)

# unmarked-stop scan: detector fire runs >= 5 s outside protocol still
win_a, win_g, fire = [], [], np.zeros(n, bool)
for k in range(n):
    win_a.append(acc0[k]); win_g.append(gyro0[k])
    if len(win_a) > 10:
        win_a.pop(0); win_g.pop(0)
    if len(win_a) == 10:
        wa, wg = np.array(win_a), np.array(win_g)
        fire[k] = (wa.std(axis=0).max() < 0.20 and np.abs(wg).std() < 0.01
                   and np.abs(wg).mean() < 0.03)
still = np.zeros(n, bool)
for a, b in [start_win, end_win] + stop_wins:
    still[int(a / sim.DT):int(b / sim.DT)] = True
guard = np.zeros(n, bool)
for i in np.where(np.diff(still.astype(int)) != 0)[0]:
    guard[max(0, i - 20):i + 20] = True
walkmask = ~still & ~guard
runs = []
k = 0
while k < n:
    if fire[k] and walkmask[k]:
        j = k
        while j < n and fire[j] and walkmask[j]:
            j += 1
        if j - k >= 50:
            runs.append((k * sim.DT, (j - k) * sim.DT))
        k = j
    else:
        k += 1
print('M6 %s unmarked still episodes >=5 s while walking: %d, total %.0f s %s'
      % (TAG, len(runs), sum(d for _, d in runs),
         [('%.0f' % t, '%.0f' % d) for t, d in runs]), flush=True)
print('M6 %s DONE' % TAG, flush=True)
