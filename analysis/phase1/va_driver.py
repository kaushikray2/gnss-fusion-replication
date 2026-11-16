import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
import numpy as np
import sim
sim.SIG_A = 1.8066e-3; sim.SIG_G = 1.4688e-4; sim.BA_SD = 5.149e-4; sim.BG_SD = 3.506e-5
DT = sim.DT
sim.QD = np.diag([(sim.SIG_A * DT**2 / 2)**2] * 2 + [(sim.SIG_A * DT)**2] * 2 +
                 [(sim.SIG_G * DT)**2, (1e-4 * np.sqrt(DT))**2] + [(5e-3 * np.sqrt(DT))**2] * 2)
out = {}
t0 = time.time()
for scn in ['open', 'canyon', 'forest', 'stress']:
    agg = {m: [] for m in sim.METHODS}
    for seed in range(100):
        o, tim, eps = sim.run_one(scn, seed)
        mask = sim.challenge_mask(scn, eps)
        for m in sim.METHODS:
            agg[m].append(sim.metrics(o[m], mask)['chal'])
    out[scn] = {m: {'chal_mean': float(np.mean(v)), 'chal_sd': float(np.std(v, ddof=1))} for m, v in agg.items()}
    print(scn, 'done', round(time.time() - t0), 's', flush=True)
json.dump(out, open('/tmp/ci/va_measured.json', 'w'), indent=1)
print('LC forest %.3f (expect 6.420)  ZUPT forest %.3f (expect 4.760)  LC open %.3f (expect 0.835)' % (out['forest']['LC-EKF']['chal_mean'], out['forest']['ZUPT-EKF']['chal_mean'], out['open']['LC-EKF']['chal_mean']))
print('VA-DONE')
