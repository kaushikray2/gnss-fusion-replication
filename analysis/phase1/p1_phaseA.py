import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
import tc_real
cap = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'psr-skyview', 'GNSS_Data.hostclean.txt')
bins, epochs, anchor, t_first = tc_real.load_capture(cap, 'x')
anchor_ecef = np.array(anchor[3], dtype=float)
dis = []; clks = []
for i, ep in enumerate(epochs):
    if i % 25 or len(ep['svs']) < 5: continue
    svs = ep['svs']; x = anchor_ecef.copy(); cb = 0.0; ok = True
    for _ in range(5):
        H = []; r = []
        for satid, psr, sv_ecef, cn0 in svs:
            sv = np.array(sv_ecef, dtype=float); d = sv - x; rng = np.linalg.norm(d)
            if rng < 2.0e7 or rng > 3.2e7: ok = False; break
            H.append(np.concatenate([-d / rng, [1.0]])); r.append(psr - (rng + cb))
        if not ok: break
        H = np.array(H); r = np.array(r)
        try: dx, *_ = np.linalg.lstsq(H, r, rcond=None)
        except Exception: ok = False; break
        x = x + dx[:3]; cb += dx[3]
        if np.linalg.norm(dx[:3]) < 0.01: break
    if ok:
        dis.append(float(np.linalg.norm(x - anchor_ecef))); clks.append(cb)
dis = np.array(dis); clks = np.array(clks)
print('PHASEA single-epoch LS: n %d | 3D discrepancy median %.1f m p90 %.1f m max %.1f m | clock est median %.0f m' % (len(dis), np.median(dis), np.percentile(dis, 90), dis.max(), np.median(clks)), flush=True)
