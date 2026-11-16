#!/usr/bin/env python3
"""Compare two sim.py Monte Carlo results.json files (Stage 2).

Prints, per scenario, challenge-window and full-run RMSE for each
method under both parameter sets with ranks, and flags every rank
change. Usage: python3 compare_mc.py OLD.json NEW.json
"""
import json, sys

def ranks(vals):
    order = sorted(vals, key=lambda m: vals[m])
    return {m: i + 1 for i, m in enumerate(order)}

old = json.load(open(sys.argv[1]))['summary']
new = json.load(open(sys.argv[2]))['summary']
for scn in old:
    if scn not in new:
        continue
    print('== %s ==' % scn)
    for metric in ('chal_mean', 'rmse_mean'):
        ov = {m: old[scn][m][metric] for m in old[scn]}
        nv = {m: new[scn][m][metric] for m in new[scn] if m in ov}
        orr, nrr = ranks(ov), ranks(nv)
        print(' %s:' % ('challenge-window RMSE' if metric == 'chal_mean' else 'full-run RMSE'))
        for m in sorted(ov, key=lambda m: orr[m]):
            flag = '  <-- rank %d -> %d' % (orr[m], nrr[m]) if orr[m] != nrr.get(m) else ''
            print('   %-10s %9.3f -> %9.3f%s' % (m, ov[m], nv.get(m, float('nan')), flag))
