#!/usr/bin/env python3
"""Regenerate the full-capture differenced clock-rate series for
Section V-C (revision item F20a) and plot it as a vector PDF.

Estimator: the repository's leg-1 estimator exactly as in
hardware/tc_real.py:common_mode -- per consecutive epoch pair,
per-satellite differences of (geometric range - PsR) folded
modulo 1 ms of range, cross-satellite median, pair admitted
only with >= 4 satellites in common. The only extensions
here are bookkeeping the banked common_mode.csv lacks
(it holds only the 37-epoch longest contiguous run): every
admitted pair is kept, with its logger time, and the nominal
NCO ramp is removed per pair using tc_delta's rule (nearest
$PSTMTG within 2 s, else the capture median; NCO-implied rate
on this (geo - PsR) quantity is NCO*c/f_L1, cf.
tc_real.common_mode stats). No filter is run.

Run with the patent venv python (system matplotlib is broken
against the user-site numpy):
  MPLCONFIGDIR=/tmp/mpl <venv>/python make_fig_clockrate.py
Writes fig_clockrate.pdf next to this file and prints the
caption statistics as JSON.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'hardware'))
sys.path.insert(0, os.path.join(ROOT, 'simulation'))
import tc_delta as td  # noqa: E402  (load_tg; imports tc_real)
import tc_real as tr  # noqa: E402

CAPTURE = os.path.join(ROOT, 'data', 'psr-skyview',
                       'GNSS_Data.hostclean.txt')
C = 299792458.0
F_L1 = 1575.42e6
M1 = C * 1e-3


def main():
    bins, epochs, anchor, t_first = tr.load_capture(CAPTURE)
    tg = td.load_tg(CAPTURE)
    tg_t = np.array([t for t, _ in tg], dtype=float)
    tg_n = np.array([n for _, n in tg], dtype=float)
    nco_med = float(np.median(tg_n))

    def nco_at(t_us):
        i = int(np.argmin(np.abs(tg_t - t_us)))
        return float(tg_n[i]) if abs(tg_t[i] - t_us) <= 2e6 else nco_med

    # --- leg-1 admission, verbatim logic from tc_real.common_mode
    anchor_ecef = np.array(anchor[3])
    prev = {}
    t_min, raw, resid = [], [], []
    t0 = epochs[0]['t_us']
    for ep in epochs:
        cur = {}
        for satid, psr, sv_ecef, cn0 in ep['svs']:
            geo = float(np.linalg.norm(np.array(sv_ecef) - anchor_ecef))
            cur[satid] = geo - psr
        ds = []
        for s, v in cur.items():
            if s in prev:
                d = v - prev[s]
                ds.append(d - M1 * round(d / M1))
        if len(ds) >= 4:
            rate = float(np.median(ds))
            t_min.append((ep['t_us'] - t0) / 60e6)
            raw.append(rate)
            resid.append(rate - nco_at(ep['t_us']) * C / F_L1)
        prev = cur

    t_min = np.array(t_min)
    raw = np.array(raw)
    resid = np.array(resid)
    stats = {
        'capture': os.path.relpath(CAPTURE, ROOT),
        'epochs_loaded': len(epochs),
        'n_admitted_pairs': int(len(resid)),
        'span_min': float(t_min.max() - t_min.min()),
        'raw_rate_median_m_per_epoch': float(np.median(raw)),
        'raw_rate_iqr_m': float(np.percentile(raw, 75)
                                - np.percentile(raw, 25)),
        'resid_median_m_per_epoch': float(np.median(resid)),
        'resid_iqr_m': float(np.percentile(resid, 75)
                             - np.percentile(resid, 25)),
        'resid_p5_p95_m': [float(np.percentile(resid, 5)),
                           float(np.percentile(resid, 95))],
        'nco_median_hz': nco_med,
    }
    print(json.dumps(stats, indent=1))

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 8, 'axes.labelsize': 8,
                         'xtick.labelsize': 7, 'ytick.labelsize': 7})
    fig, ax = plt.subplots(figsize=(3.5, 2.4))
    ax.plot(t_min, resid, ',', color='0.45', alpha=0.7, rasterized=True)
    # 5-minute rolling median for legibility (display only)
    edges = np.arange(0, t_min.max() + 5.0, 5.0)
    ctr, med = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (t_min >= a) & (t_min < b)
        if m.sum() >= 10:
            ctr.append(0.5 * (a + b))
            med.append(float(np.median(resid[m])))
    ax.plot(ctr, med, '-', color='black', lw=1.0)
    ax.axhline(0.0, color='black', lw=0.5, ls=':')
    lo, hi = np.percentile(resid, [0.5, 99.5])
    pad = 0.15 * (hi - lo)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(0, t_min.max())
    ax.set_xlabel('Time into sky capture (min)')
    ax.set_ylabel('Residual differenced rate\n(m/epoch)')
    ax.grid(True, lw=0.3, alpha=0.5)
    fig.tight_layout(pad=0.4)
    out = os.path.join(HERE, 'fig_clockrate.pdf')
    fig.savefig(out)
    print('wrote', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
