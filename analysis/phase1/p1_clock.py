import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
import tc_real
cap = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'psr-skyview', 'GNSS_Data.hostclean.txt')
bins, epochs, anchor, t_first = tc_real.load_capture(cap, 'x')
series, stats = tc_real.common_mode(epochs, anchor, nco_hz=-47421.0)
print('CLOCK as-is common_mode:', {k: round(v, 3) if isinstance(v, float) else v for k, v in stats.items()}, flush=True)
anchor_ecef = np.array(anchor[3]); M = 299792458.0 * 1e-3
prev = {}; adm_f = []; adm_r = []; idxs = []
for i, ep in enumerate(epochs):
    cur = {}
    for satid, psr, sv_ecef, cn0 in ep['svs']:
        cur[satid] = float(np.linalg.norm(np.array(sv_ecef) - anchor_ecef)) - psr
    df = []; dr = []
    for s, v in cur.items():
        if s in prev:
            d = v - prev[s]; dr.append(d); df.append(d - M * round(d / M))
    if len(df) >= 4:
        adm_f.append(float(np.median(df))); adm_r.append(float(np.median(dr))); idxs.append(i)
    prev = cur
for tag, rv in (('folded', np.array(adm_f)), ('raw-nofold', np.array(adm_r))):
    print('CLOCK %s all-admitted: median %.2f IQR %.2f n %d' % (tag, np.median(rv), np.percentile(rv, 75) - np.percentile(rv, 25), len(rv)), flush=True)
idx = np.array(idxs); rv = np.array(adm_f)
best = cur = [0]
for j in range(1, len(idx)):
    cur = cur + [j] if idx[j] - idx[j-1] <= 2 else [j]
    if len(cur) > len(best): best = cur
seg = np.array(best); rvs = rv[seg]
print('CLOCK folded longest-run: median %.2f IQR %.2f n %d' % (np.median(rvs), np.percentile(rvs, 75) - np.percentile(rvs, 25), len(rvs)), flush=True)
