#!/usr/bin/env python3
"""tc_delta.py - experiment 4 phase B, differenced harness
(design addenda 2-5): the paper's clock question on
time-differenced $PSTMTS pseudoranges, the only form in
which this module's ranges are a stable observable.

Front end (per consecutive ~1 s epoch pair, per SV):
  y = fold_1ms(PsR_t - PsR_{t-1}) - dC_nominal
where dC_nominal = -NCO * c / f_L1 from $PSTMTG removes
the module's ~30 ppm oscillator ramp, and the 1 ms fold
removes both the 200 ms cell hops and the whole-ms grid
jumps (review #9: ~30% of epoch pairs carry one).
Delta observations NEVER span an outage: pairs form only
between consecutive epochs 0.5-1.5 s apart, so the first
post-blockage pair is the first two post-blockage epochs;
the outage enters through the clock states' coasted
covariance and the post-blockage rate itself.

The three runners share sim.py's navigation core at the
Stage 2 measured IMU parameters (via tc_real) and differ
ONLY in the clock block - the model-order ladder of
addendum 3, one derivative below the paper's:
  v0  no clock state (residual rate assumed zero)
  v1  residual rate as a random walk
      (Q = 2.0^2 per epoch - run_tc's bias RW, translated)
  v2  rate + rate derivative
      (Q = 0.1^2 / 0.02^2 per epoch - run_tc's CD values)
The previous epoch's ranges are frozen at their
post-update values (the standard delta-range aiding
approximation); the current range is recomputed per SV
during the sequential update, as in tc_real. 4-sigma
gating, CN0-descending, sim._scalar_update throughout.

Truth for phase B is the static median-GGA anchor, as in
tc_real. Scoring reuses tc_real.score unchanged.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'simulation'))
import psr_residue as pr  # noqa: E402
import sim  # noqa: E402
import tc_real as tr  # noqa: E402  loader, scorer, sim patch

C = 299792458.0
F_L1 = 1575.42e6
M1 = C * 1e-3            # 1 ms fold grid (divides 200 ms)
SIG_D = 5.0              # m, per-SV delta-range noise:
# leg-1 pair-median IQR ~3.2-5.5 m over >= 4 SVs implies
# a per-SV sigma of ~5 m; the self-test generates with it
Q_RHO = 2.0 ** 2         # per epoch, v1 rate RW
Q_RHO2 = 0.1 ** 2        # per epoch, v2 rate RW part
Q_RDOT = 0.02 ** 2       # per epoch, v2 derivative RW
RATE_PRIOR = 30.0        # m/epoch, residual-rate prior sd
RDOT_PRIOR = 1.0         # m/epoch^2 prior sd


def load_tg(path):
    """(t_us, nco_hz) series from $PSTMTG rows."""
    out = []
    with open(path, errors='replace') as fh:
        for raw in fh:
            if raw.startswith('G,') and '$PSTMTG' in raw:
                try:
                    t_us = int(raw[2:raw.index(',', 2)])
                except ValueError:
                    continue
                tg = pr.parse_tg(raw[raw.index('$'):]
                                 .split('*')[0].strip().split(','))
                if tg:
                    out.append((t_us, tg['nco']))
    return out


class TcDelta:
    """One clock variant of the differenced harness."""

    NC = {'v0': 0, 'v1': 1, 'v2': 2}

    def __init__(self, variant, anchor_ecef, rot):
        self.variant = variant
        self.nc = self.NC[variant]
        self.ns = 8 + self.nc
        self.anchor = np.array(anchor_ecef)
        self.rot = rot
        rng = np.random.default_rng(9000)  # sim's runner seed
        x8, P8 = sim.init_state('open', np.zeros(2), rng)
        self.x = np.zeros(self.ns)
        self.x[:8] = x8
        self.P = np.zeros((self.ns, self.ns))
        self.P[:8, :8] = P8
        if self.nc >= 1:
            self.P[8, 8] = RATE_PRIOR ** 2
        if self.nc >= 2:
            self.P[9, 9] = RDOT_PRIOR ** 2
        self.prev = None       # (t_s, {satid: (psr, sv_enu)})
        self.prev_rng = {}     # satid -> range at prev epoch
        self.last_obs_t = None
        self.n_acc = 0
        self.n_rej = 0

    def sv_enu(self, sv_ecef):
        return self.rot @ (np.array(sv_ecef) - self.anchor)

    def predict(self, acc, gyro):
        # nav block only; the clock block advances at delta
        # epochs (its dynamics are per-epoch, not per-DT)
        ns = self.ns
        F = np.eye(ns)
        F[:8, :8] = sim.jac_F(self.x[:8], acc)
        xn = self.x.copy()
        xn[:8] = sim.mech(self.x[:8], acc, gyro)
        Q = np.zeros((ns, ns))
        Q[:8, :8] = sim.QD
        self.x = xn
        self.P = F @ self.P @ F.T + Q

    def _clock_coast(self, elapsed_epochs):
        """Advance the clock block over elapsed_epochs
        (1 for adjacent epochs; ~gap length for the first
        pair after an outage)."""
        e = max(1, int(round(elapsed_epochs)))
        if self.nc == 1:
            self.P[8, 8] += Q_RHO * e
        elif self.nc == 2:
            self.x[8] = self.x[8] + self.x[9] * e
            F = np.array([[1.0, float(e)], [0.0, 1.0]])
            blk = F @ self.P[8:10, 8:10] @ F.T
            blk[0, 0] += Q_RHO2 * e
            blk[1, 1] += Q_RDOT * e
            self.P[8:10, 8:10] = blk

    def epoch(self, ep, t_s, nco_hz):
        """Process one 1 Hz epoch; form delta observations
        against the previous epoch when it is 0.5-1.5 s
        back. Returns (n_accepted, n_rejected)."""
        cur = {}
        for satid, psr, sv_ecef, cn0 in ep['svs']:
            cur[satid] = (psr, self.sv_enu(sv_ecef), cn0)
        acc_e = rej_e = 0
        if self.prev is not None:
            pt, prev = self.prev
            dt = t_s - pt
            if 0.5 <= dt <= 1.5:
                elapsed = (t_s - self.last_obs_t
                           if self.last_obs_t is not None else 1.0)
                self._clock_coast(elapsed)
                dC_nom = -nco_hz * C / F_L1
                rows = []
                for satid, (psr, sv, cn0) in cur.items():
                    if satid in prev and satid in self.prev_rng:
                        d = psr - prev[satid][0]
                        d -= M1 * round(d / M1)
                        rows.append((satid, d - dC_nom, sv, cn0))
                for satid, y, sv, cn0 in sorted(
                        rows, key=lambda r: -r[3]):
                    dvec = sv - np.array(
                        [self.x[0], self.x[1], 0.0])
                    r_now = float(np.linalg.norm(dvec))
                    pred = r_now - self.prev_rng[satid]
                    if self.nc >= 1:
                        pred += self.x[8]
                    innov = y - pred
                    H = np.zeros((1, self.ns))
                    H[0, 0] = -dvec[0] / r_now
                    H[0, 1] = -dvec[1] / r_now
                    if self.nc >= 1:
                        H[0, 8] = 1.0
                    S = float((H @ self.P @ H.T)[0, 0]) + SIG_D ** 2
                    if abs(innov) <= 4.0 * math.sqrt(S):
                        self.x, self.P = sim._scalar_update(
                            self.x, self.P, innov, H, SIG_D ** 2)
                        acc_e += 1
                    else:
                        rej_e += 1
                if rows:
                    self.last_obs_t = t_s
        # freeze this epoch's ranges at post-update position
        p = np.array([self.x[0], self.x[1], 0.0])
        self.prev_rng = {
            satid: float(np.linalg.norm(sv - p))
            for satid, (psr, sv, cn0) in cur.items()}
        self.prev = (t_s, {s: (v[0], v[1]) for s, v in cur.items()})
        self.n_acc += acc_e
        self.n_rej += rej_e
        return (acc_e, rej_e)


def run_variant(variant, bins, epochs, anchor, t_first, tg):
    rot = tr.enu_rotation(anchor[0], anchor[1])
    f = TcDelta(variant, anchor[3], rot)
    dt_us = int(sim.DT * 1e6)
    ep_at = {}
    for ep in epochs:
        k = int(round((ep['t_us'] - t_first) / dt_us))
        ep_at.setdefault(k, []).append(ep)
    tg_t = [t for t, _ in tg]
    tg_n = [n for _, n in tg]
    nco_med = float(np.median(tg_n)) if tg_n else -47421.0

    def nco_at(t_us):
        if not tg_t:
            return nco_med
        i = int(np.argmin([abs(t - t_us) for t in tg_t]))
        return tg_n[i] if abs(tg_t[i] - t_us) <= 2e6 else nco_med

    last_bin = max(bins) if bins else 0
    last_step = max([last_bin] + list(ep_at))
    trace = []
    last = (0.0, 0.0, 0.0)
    for k in range(last_step + 1):
        if k > 0:
            sample = bins.get(k - 1, last)
            last = sample
            f.predict(np.array(sample[:2]), sample[2])
        for ep in ep_at.get(k, []):
            a, r = f.epoch(ep, k * sim.DT, nco_at(ep['t_us']))
            trace.append({'t_s': k * sim.DT, 'acc': a, 'rej': r,
                          'x': float(f.x[0]), 'y': float(f.x[1]),
                          'clk': float(f.x[8]) if f.nc >= 1 else 0.0})
    return f, trace


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('capture')
    ap.add_argument('--out', default=None)
    ap.add_argument('--gap', default=None,
                    help='blockage window T0:T1 in logger seconds')
    ap.add_argument('--fwd', default='x', choices=('x', 'y'))
    a = ap.parse_args(argv)
    out_dir = a.out or os.path.dirname(os.path.abspath(a.capture))
    os.makedirs(out_dir, exist_ok=True)
    bins, epochs, anchor, t_first = tr.load_capture(a.capture, a.fwd)
    tg = load_tg(a.capture)
    print(f'capture: {a.capture}')
    print(f'epochs: {len(epochs)}  imu bins: {len(bins)}  TG: {len(tg)}  '
          f'anchor: {anchor[0]:.6f}, {anchor[1]:.6f}')
    gap = None
    if a.gap:
        g0, g1 = a.gap.split(':')
        gap = (float(g0), float(g1))
    summary = {'capture': a.capture, 'gap': gap, 'sig_d': SIG_D,
               'variants': {}}
    for name, var in (('DELTA-v0-noclock', 'v0'),
                      ('DELTA-v1-rateRW', 'v1'),
                      ('DELTA-v2-rateRD', 'v2')):
        f, trace = run_variant(var, bins, epochs, anchor,
                               t_first, tg)
        sc = tr.score(trace, gap)
        sc['total_acc'] = f.n_acc
        sc['total_rej'] = f.n_rej
        summary['variants'][name] = sc
        with open(os.path.join(out_dir, f'trace_{name}.csv'), 'w') as fh:
            fh.write('t_s,acc,rej,x,y,rate\n')
            for t in trace:
                fh.write(f"{t['t_s']:.1f},{t['acc']},{t['rej']},"
                         f"{t['x']:.3f},{t['y']:.3f},{t['clk']:.3f}\n")
        print(name, json.dumps(sc))
    with open(os.path.join(out_dir, 'tc_delta_summary.json'), 'w') as fh:
        json.dump(summary, fh, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
