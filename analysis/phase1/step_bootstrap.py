#!/usr/bin/env python3
"""Bootstrap CIs for the Section V-C clock-rate steps (review #13, R1.3).

Rebuilds the leg-1 admitted-pair series for the run-2 blockage capture
(hardware/tc_real.py estimator: per-satellite (geometric range - PsR)
differences folded modulo 1 ms, cross-satellite median, >= 4 satellites
in common), expresses each pair as a residual rate (raw rate minus the
capture-median NCO-implied rate), and resamples the archived pre/post
windows. The windows (290 s spans with 10 s / 5 s guard offsets at the
outage edges) reproduce replication/data/psr-outage/rate_step_run2.json
exactly (n, median, IQR for all four windows); the script asserts this
before bootstrapping. 10,000 resamples, percentile 95% CI of the
median difference, RNG seeded for reproducibility.

Result (2026-11-15): cycle 1 step +0.32 m/epoch, CI [-1.97, +2.70];
cycle 2 step -5.43 m/epoch, CI [-7.79, -1.03] (window-edge variants
bracket the cycle-2 CI within [-7.93, -0.93]).
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'code', 'python'))
import tc_real as tr  # noqa: E402
import tc_delta as td  # noqa: E402

CAP = os.path.join(ROOT, 'data', 'psr-outage',
                   'Experiment_4_Phaze_2_run2.hostclean.txt')
ARCH = os.path.join(ROOT, 'data', 'psr-outage',
                    'rate_step_run2.json')
C = 299792458.0
F_L1 = 1575.42e6
M1 = C * 1e-3
OUTAGES = [(304.9, 415.2), (758.1, 832.6)]


def main():
    bins, epochs, anchor, t_first = tr.load_capture(CAP)
    anchor_ecef = np.array(anchor[3])
    tg = td.load_tg(CAP)
    implied = float(np.median([n for _, n in tg])) * C / F_L1
    t0 = epochs[0]['t_us']
    prev, pairs = {}, []
    for ep in epochs:
        cur = {}
        for satid, psr, sv_ecef, cn0 in ep['svs']:
            cur[satid] = float(np.linalg.norm(
                np.array(sv_ecef) - anchor_ecef)) - psr
        ds = []
        for s, v in cur.items():
            if s in prev:
                d = v - prev[s]
                ds.append(d - M1 * round(d / M1))
        if len(ds) >= 4:
            pairs.append(((ep['t_us'] - t0) / 1e6,
                          float(np.median(ds)) - implied))
        prev = cur
    arch = json.load(open(ARCH))
    rng = np.random.default_rng(20261115)
    for i, (a, b) in enumerate(OUTAGES):
        key = 'cycle%d' % (i + 1)
        pre = np.array([v for t, v in pairs if a - 300 <= t < a - 10])
        if i == 0:
            post = np.array([v for t, v in pairs if b + 5 < t <= b + 290])
        else:  # archived cycle-2 post window: 315 s, no guard offset
            post = np.array([v for t, v in pairs if b < t <= b + 315])
        for name, vals in [('pre', pre), ('post', post)]:
            got = (len(vals), round(float(np.median(vals)), 2),
                   round(float(np.percentile(vals, 75)
                               - np.percentile(vals, 25)), 2))
            want = (arch[key][name]['n'], arch[key][name]['median'],
                    arch[key][name]['iqr'])
            assert got == want, (key, name, got, want)
        steps = np.array([
            np.median(rng.choice(post, len(post), replace=True))
            - np.median(rng.choice(pre, len(pre), replace=True))
            for _ in range(10000)])
        lo, hi = np.percentile(steps, [2.5, 97.5])
        print('%s: step %+.2f m/epoch, bootstrap 95%% CI [%+.2f, %+.2f]'
              % (key, float(np.median(post) - np.median(pre)), lo, hi))


if __name__ == '__main__':
    main()
