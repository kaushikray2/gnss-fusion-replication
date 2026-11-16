import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
import tc_real
cap = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'psr-skyview', 'GNSS_Data.hostclean.txt')
bins, epochs, anchor, t_first = tc_real.load_capture(cap, 'x')
anchor_ecef = np.array(anchor[3], dtype=float)
from collections import Counter
why = Counter(); dis = []
for i, ep in enumerate(epochs):
    if len(ep['svs']) < 5: why['lt5sv'] += 1; continue
    svs = ep['svs']; x = anchor_ecef.copy(); cb = 0.0; fail = None
    for it in range(6):
        H = []; r = []
        for satid, psr, sv_ecef, cn0 in svs:
            sv = np.array(sv_ecef, dtype=float); d = sv - x; rng = np.linalg.norm(d)
            H.append(np.concatenate([-d / rng, [1.0]])); r.append(psr - (rng + cb))
        H = np.array(H); r = np.array(r)
        try: dx, *_ = np.linalg.lstsq(H, r, rcond=None)
        except Exception: fail = 'lstsq'; break
        if not np.isfinite(dx).all() or np.linalg.norm(dx[:3]) > 3e6: fail = 'diverge@%d' % it; break
        x = x + dx[:3]; cb += dx[3]
        if np.linalg.norm(dx[:3]) < 0.01: break
    if fail: why[fail] += 1
    else: dis.append(float(np.linalg.norm(x - anchor_ecef)))
dis = np.array(dis)
print('PHASEA2 epochs %d | outcomes %s' % (len(epochs), dict(why)), flush=True)
if len(dis): print('PHASEA2 solved %d | discrepancy median %.0f m p10 %.0f p90 %.0f min %.0f max %.0f' % (len(dis), np.median(dis), np.percentile(dis, 10), np.percentile(dis, 90), dis.min(), dis.max()), flush=True)
