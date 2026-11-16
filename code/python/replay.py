#!/usr/bin/env python3
"""replay.py - Stage 3 replay harness: real logger captures
through the paper's estimators, UNCHANGED.

Reads a Stage 1 logger capture (IMU rows 't_us,ax,ay,az,gx,gy,
gz' in g and dps at ~104 Hz; 'G,t_us,$...' GNSS rows), adapts
it to the exact inputs sim.py's estimators consume, and runs
the loosely-coupled family: GNSS, INS, LC-EKF, LC-UKF,
ZUPT-EKF, ADAPT-EKF, RTS-SMOOTH. The estimator code is not
modified; replay patches only the module globals that describe
the dataset (N, TRUTH) and, on request, the noise constants
(SIG_A / SIG_G / QD) so Stage 2's measured values can flow in.

TC-EKF / TC-EKF-CD are NOT replayed: they consume pseudoranges
against sim.py's synthetic constellation. Real tight coupling
is experiment 4, on $PSTMTS, with its own harness.

Adapter contract (all documented choices, no silent magic):
- Replay t=0 is the first valid (qual>=1) GGA fix; earlier IMU
  samples are dropped (the filters initialise from eps[0].fix).
- IMU is decimated 104 Hz -> 10 Hz by bin-averaging (0.1 s bins
  on the logger clock). Accelerations g -> m/s^2, gyro dps ->
  rad/s. No de-meaning: the real biases are the filters' job,
  exactly as the synthetic biases are.
- Axis map: the sim wants [forward, lateral] accel + yaw rate.
  Default --fwd x: forward = shield +X, lateral = +Y, yaw = gz.
  --fwd y: forward = +Y, lateral = -X, yaw = gz. Either way the
  rig must be carried FLAT (the sim's accel is gravity-free
  horizontal specific force; a flat rig's horizontal axes are).
  The walk protocol fixes the carry to match --fwd.
- Fixes: GGA lat/lon -> local ENU about the first fix
  (equirectangular, cm-class at walk scale). fix_R is an
  HDOP proxy: (max(HDOP,0.5) * UERE)^2 * I, UERE default 2.5 m
  (--uere). Epochs with no valid fix simply have no entry -
  the filters coast, as in the synthetic outages.
- --mask-out T0:T1 (seconds from replay t=0, repeatable) drops
  real fixes in the window from ALL methods: the Stage 3
  in-replay outage masking.
- Truth: --static asserts the rig never moved (truth = median
  fix position, constant). Walk truth (loop closure +
  checkpoints) plugs into build_truth_for() when Stage 3 runs.

Usage:
  python3 replay.py CAPTURE --static [--fwd x|y] [--seed 0]
          [--sig-a A] [--sig-g G] [--uere M]
          [--mask-out T0:T1 ...] [--out results.json]
"""
import argparse
import json
import math
import sys

import numpy as np

import sim

G0 = 9.80665
R_EARTH = 6378137.0


def parse_capture(path):
    """Return (imu, fixes): imu = list of (t_us, ax, ay, az, gx,
    gy, gz) raw logger units; fixes = list of (t_us, lat, lon,
    hdop) for qual>=1 GGA rows."""
    imu = []
    fixes = []
    with open(path, errors='replace') as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('G,'):
                if '$' not in line:
                    continue  # spliced/fragment row, no sentence
                try:
                    t_us = int(line[2:line.index(',', 2)])
                except ValueError:
                    continue
                body = line[line.index('$'):].split('*')[0]
                f = body.split(',')
                if f[0] in ('$GPGGA', '$GNGGA'):
                    try:
                        lat = float(f[2]); lon = float(f[4])
                        qual = int(f[6]); hdop = float(f[8])
                    except (ValueError, IndexError):
                        continue
                    if qual < 1:
                        continue
                    la = int(lat / 100) + (lat % 100) / 60.0
                    if f[3] == 'S':
                        la = -la
                    lo = int(lon / 100) + (lon % 100) / 60.0
                    if f[5] == 'W':
                        lo = -lo
                    fixes.append((t_us, la, lo, hdop))
                continue
            parts = line.split(',')
            if len(parts) == 7:
                try:
                    vals = [float(p) for p in parts]
                except ValueError:
                    continue
                imu.append((int(vals[0]),) + tuple(vals[1:]))
    return imu, fixes


def adapt(imu, fixes, fwd='x', uere=2.5, mask_out=()):
    """Build (acc_m, gyro_m, eps, meta) in sim.py's input shape.

    acc_m: (N,2) m/s^2 [forward, lateral]; gyro_m: (N,) rad/s;
    eps: epoch dicts with k/fix/fix_R (+ dummy vis/pr/sig that
    only the TC family reads - see module docstring)."""
    dt_us = int(sim.DT * 1e6)
    t0 = fixes[0][0]
    t_end = max(t for t, *_ in imu)
    n = int((t_end - t0) // dt_us) + 1
    if n < 100:
        raise ValueError('capture too short after first fix: '
                         '%d samples' % n)
    # --- decimate IMU into 0.1 s bins (bin-average) ---
    bins = {}
    for t, ax, ay, az, gx, gy, gz in imu:
        if t < t0:
            continue
        b = (t - t0) // dt_us
        if b >= n:
            continue
        if fwd == 'x':
            f0, f1, yaw = ax, ay, gz
        else:
            f0, f1, yaw = ay, -ax, gz
        acc = bins.setdefault(b, [0.0, 0.0, 0.0, 0])
        acc[0] += f0 * G0
        acc[1] += f1 * G0
        acc[2] += yaw * math.pi / 180.0
        acc[3] += 1
    acc_m = np.zeros((n, 2))
    gyro_m = np.zeros(n)
    last = (0.0, 0.0, 0.0)
    for b in range(n):
        if b in bins:
            s0, s1, s2, cnt = bins[b]
            last = (s0 / cnt, s1 / cnt, s2 / cnt)
        acc_m[b] = last[:2]
        gyro_m[b] = last[2]
    # --- fixes -> ENU epochs ---
    lat0, lon0 = fixes[0][1], fixes[0][2]
    cos0 = math.cos(math.radians(lat0))
    eps = []
    seen_k = set()
    n_masked = 0
    for t, la, lo, hdop in fixes:
        k = int(round((t - t0) / dt_us))
        if k < 0 or k >= n or k in seen_k:
            continue
        seen_k.add(k)
        t_sec = (t - t0) / 1e6
        if any(a <= t_sec <= b for a, b in mask_out):
            n_masked += 1
            continue
        enu = np.array([(math.radians(lo - lon0) * cos0 *
                         R_EARTH),
                        (math.radians(la - lat0) * R_EARTH)])
        sig_f = max(hdop, 0.5) * uere
        eps.append(dict(k=k, vis=np.zeros(sim.NSAT, bool),
                        pr=np.full(sim.NSAT, np.nan), sig=4.0,
                        fix=enu, fix_R=np.eye(2) * sig_f ** 2))
    eps.sort(key=lambda e: e['k'])
    if len(eps) < 2 or eps[0]['k'] != 0:
        raise ValueError('need >=2 fixes with the first at k=0 '
                         '(got %d, first k=%s)'
                         % (len(eps),
                            eps[0]['k'] if eps else None))
    meta = dict(n=n, duration_s=n * sim.DT, n_fixes=len(eps),
                n_masked=n_masked,
                enu_origin=(lat0, lon0))
    return acc_m, gyro_m, eps, meta


def build_truth_for(kind, eps, n):
    """Truth arrays in sim.TRUTH's shape. 'static': constant at
    the median fix. Walk kinds plug in here at Stage 3."""
    if kind == 'static':
        fixes = np.array([e['fix'] for e in eps])
        med = np.median(fixes, axis=0)
        pos = np.tile(med, (n, 1))
        scatter = float(np.sqrt(((fixes - med) ** 2)
                                .sum(axis=1)).max())
        return dict(pos=pos), scatter
    raise ValueError('unknown truth kind: %s' % kind)


def challenge_mask(n, eps, mask_out):
    """Samples scored as 'challenge': the --mask-out windows if
    given, else the no-fix gaps, else the whole run."""
    m = np.zeros(n, bool)
    if mask_out:
        t = np.arange(n) * sim.DT
        for a, b in mask_out:
            m |= (t >= a) & (t <= b)
        return m
    have = np.zeros(n, bool)
    for e in eps:
        have[e['k']] = True
    if (~have).sum() > n * 0.05:
        # expand each no-fix epoch sample to its whole second
        idx = np.where(~have)[0]
        m[idx] = True
        return m
    m[:] = True
    return m


LOOSE_METHODS = ['GNSS', 'INS', 'LC-EKF', 'LC-UKF', 'ZUPT-EKF',
                 'ADAPT-EKF', 'RTS-SMOOTH']


def run_replay(acc_m, gyro_m, eps, truth, mask, seed=0):
    sim.N = len(acc_m)
    sim.TRUTH = truth
    scn = 'replay'
    out = {}
    out['GNSS'] = sim.run_gnss(eps)
    out['INS'] = sim.run_ins(scn, acc_m, gyro_m, eps, seed)
    out['LC-EKF'] = sim.run_lc(scn, acc_m, gyro_m, eps, seed)[0]
    out['LC-UKF'] = sim.run_ukf(scn, acc_m, gyro_m, eps, seed)
    out['ZUPT-EKF'] = sim.run_lc(scn, acc_m, gyro_m, eps, seed,
                                 zupt=True)[0]
    out['ADAPT-EKF'] = sim.run_lc(scn, acc_m, gyro_m, eps, seed,
                                  adapt=True)[0]
    _, st = sim.run_lc(scn, acc_m, gyro_m, eps, seed, store=True)
    out['RTS-SMOOTH'] = sim.rts_smooth(st)
    return {m: sim.metrics(out[m], mask) for m in LOOSE_METHODS}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture')
    ap.add_argument('--static', action='store_true',
                    help='truth = median fix (rig never moved)')
    ap.add_argument('--fwd', choices=('x', 'y'), default='x')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--uere', type=float, default=2.5)
    ap.add_argument('--sig-a', type=float, default=None,
                    help='override sim SIG_A (Stage 2 measured)')
    ap.add_argument('--sig-g', type=float, default=None,
                    help='override sim SIG_G (Stage 2 measured)')
    ap.add_argument('--mask-out', action='append', default=[],
                    metavar='T0:T1',
                    help='drop fixes in this window (repeatable)')
    ap.add_argument('--out', default=None)
    a = ap.parse_args(argv)
    if not a.static:
        print('only --static truth is implemented until the '
              'Stage 3 walk protocol lands', file=sys.stderr)
        return 2
    mask_out = []
    for w in a.mask_out:
        lo, hi = w.split(':')
        mask_out.append((float(lo), float(hi)))
    imu, fixes = parse_capture(a.capture)
    if len(imu) < 1000 or len(fixes) < 2:
        print('capture lacks data: %d IMU rows, %d valid fixes'
              % (len(imu), len(fixes)), file=sys.stderr)
        return 1
    dts = [imu[i + 1][0] - imu[i][0]
           for i in range(min(len(imu) - 1, 2000))]
    dts.sort()
    print('capture: %d IMU rows (median dt %.0f us), %d valid '
          'fixes' % (len(imu), dts[len(dts) // 2], len(fixes)))
    acc_m, gyro_m, eps, meta = adapt(imu, fixes, fwd=a.fwd,
                                     uere=a.uere,
                                     mask_out=mask_out)
    truth, scatter = build_truth_for('static', eps, meta['n'])
    print('adapted: N=%d (%.0f s), %d fix epochs, %d masked out; '
          'static-truth fix scatter max=%.1f m'
          % (meta['n'], meta['duration_s'], meta['n_fixes'],
             meta['n_masked'], scatter))
    if a.sig_a is not None or a.sig_g is not None:
        if a.sig_a is not None:
            sim.SIG_A = a.sig_a
        if a.sig_g is not None:
            sim.SIG_G = a.sig_g
        dt = sim.DT
        sim.QD = np.diag(
            [(sim.SIG_A * dt ** 2 / 2) ** 2] * 2 +
            [(sim.SIG_A * dt) ** 2] * 2 +
            [(sim.SIG_G * dt) ** 2, (1e-4 * np.sqrt(dt)) ** 2] +
            [(5e-3 * np.sqrt(dt)) ** 2] * 2)
        print('noise override: SIG_A=%g SIG_G=%g (QD rebuilt)'
              % (sim.SIG_A, sim.SIG_G))
    mask = challenge_mask(meta['n'], eps, mask_out)
    res = run_replay(acc_m, gyro_m, eps, truth, mask, seed=a.seed)
    print('%-11s %8s %8s %8s %8s'
          % ('method', 'rmse', 'chal', 'max', 'final'))
    for m in LOOSE_METHODS:
        r = res[m]
        print('%-11s %8.3f %8.3f %8.3f %8.3f'
              % (m, r['rmse'], r['chal'], r['max'], r['final']))
    print('note: TC-EKF / TC-EKF-CD not replayed (they consume '
          'pseudoranges vs the synthetic constellation; real TC '
          'is experiment 4 on $PSTMTS).')
    if a.out:
        with open(a.out, 'w') as fh:
            json.dump(dict(capture=a.capture, meta=meta,
                           config=dict(fwd=a.fwd, seed=a.seed,
                                       uere=a.uere,
                                       sig_a=sim.SIG_A,
                                       sig_g=sim.SIG_G,
                                       mask_out=mask_out,
                                       fix_scatter_m=scatter),
                           results=res), fh, indent=1)
        print('wrote', a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
