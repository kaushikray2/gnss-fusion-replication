import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
import numpy as np
import sim

out = {}
t0 = time.time()
for scn in ['open', 'canyon', 'forest', 'stress']:
    per = {m: [] for m in sim.METHODS}
    for seed in range(100):
        o, tim, eps = sim.run_one(scn, seed)
        mask = sim.challenge_mask(scn, eps)
        for m in sim.METHODS:
            per[m].append(sim.metrics(o[m], mask)['chal'])
    out[scn] = per
    print(scn, 'done', round(time.time() - t0), 's', flush=True)
json.dump(out, open('/tmp/ci/ci_perseed.json', 'w'))

ref = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'simulation-100seed', 'results.json')))['summary']
print('FAITHFULNESS (re-run mean vs archived chal_mean):')
bad = 0
for scn in out:
    for m in sim.METHODS:
        mine = float(np.mean(out[scn][m])); refv = ref[scn][m]['chal_mean']
        if abs(mine - refv) > 0.01 * max(1.0, refv):
            bad += 1; print('  MISMATCH', scn, m, round(mine, 3), 'vs', round(refv, 3))
print('  mismatches:', bad)

pairs = [('ZUPT-EKF', 'LC-EKF'), ('LC-UKF', 'LC-EKF'), ('RTS-SMOOTH', 'LC-EKF'), ('TC-EKF-CD', 'LC-EKF'), ('ZUPT-EKF', 'RTS-SMOOTH')]
res = {}
for scn in out:
    res[scn] = {}
    for a, b in pairs:
        d = np.array(out[scn][a]) - np.array(out[scn][b])
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        res[scn][a + ' - ' + b] = {'mean_diff': float(d.mean()), 'se': se, 'ci95': [float(d.mean() - 1.984 * se), float(d.mean() + 1.984 * se)]}
        print(scn, a, '-', b, ': mean %+.3f  se %.3f  CI [%+.3f, %+.3f]' % (d.mean(), se, d.mean() - 1.984 * se, d.mean() + 1.984 * se), flush=True)
json.dump(res, open('/tmp/ci/ci_pairs.json', 'w'))
print('CI-DONE')
