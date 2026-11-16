#!/usr/bin/env python3
"""tc_real.py - experiment 4 phase B harness: the paper's two
tightly-coupled clock variants on real $PSTMTS pseudoranges.

Design: hardware/TC_HARNESS_DESIGN.md. In one paragraph:
both runners share sim.py's navigation core (mech, jac_F,
QD rebuilt at the Stage 2 MEASURED IMU parameters) and a
per-SV ambiguity-state front end (phase A's verdict: no
shared grid on this module). The ONLY difference between
the runners is the clock block, exactly as in sim.run_tc:
bias-only (random-walk bias) vs two-state (bias + drift).
Sequential per-SV scalar updates, 4-sigma gating, gate
rejections counted - the lockout evidence.

Ambiguity gauge convention (design section 3): a slot is
initialised from its epoch residual MINUS a common-mode
estimate (the median residual of that epoch's other
initialising SVs when >= 4 initialise together, else the
median innovation of the live SVs). The common part of any
epoch is never absorbed per-SV; it remains the clock
state's to explain.

Modes:
  (default)      run both variants; needs --gap T0:T1
                 (logger seconds) to score recovery
  --common-mode  leg 1: extract the per-epoch common-mode
                 clock series (median residue after per-SV
                 median removal) and its drift / wander

Input: a logger capture in native format (IMU rows,
'G,t_us,$SENTENCE' rows) - strip any recorder prefixes
first (see data/psr-skyview/strip_host_prefix.py).
The rig is static for phase B; truth is the median GGA
anchor. IMU decimation mirrors replay.py: 0.1 s bin
averages, rig flat, --fwd x (default) or y.
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
import psr_residue as pr  # noqa: E402  field order + parsers
import sim  # noqa: E402  the paper's estimator core

# Stage 2 measured IMU parameters (hardware/CALIBRATION_NOTE.md)
sim.SIG_A = 1.8066e-3
sim.SIG_G = 1.4688e-4
sim.BA_SD = 5.149e-4
sim.BG_SD = 3.506e-5
sim.QD = np.diag([(sim.SIG_A * sim.DT**2 / 2)**2] * 2 +
                 [(sim.SIG_A * sim.DT)**2] * 2 +
                 [(sim.SIG_G * sim.DT)**2, (1e-4 * np.sqrt(sim.DT))**2] +
                 [(5e-3 * np.sqrt(sim.DT))**2] * 2)  # sim.py 161-163

G0 = 9.80665
SIG_PR = 2.0          # m, sim forest pseudorange sigma
NSLOT = 32            # ambiguity slot pool
SIG_N0 = 10.0         # m, ambiguity init sd (value, not scatter)
RW_N = 0.01           # m per epoch, ambiguity random walk
SLOT_STALE_S = 10.0   # free a slot unseen this long


def load_capture(path, fwd='x'):
    """Return (bins, epochs, anchor) where bins maps 0.1 s bin
    index -> (ax, ay, gz) in SI, epochs is a list of dicts
    {t_us, svs: [(satid, psr, sv_ecef, cn0)]}, and anchor is
    (lat_deg, lon_deg, alt, ecef) from the median valid GGA."""
    dt_us = int(sim.DT * 1e6)
    sums = {}
    ggas = []
    ts_rows = []  # (t_us, rec)
    t_first = None
    with open(path, errors='replace') as fh:
        for raw in fh:
            if raw.startswith('G,'):
                try:
                    t_us = int(raw[2:raw.index(',', 2)])
                except ValueError:
                    continue
                if '$' not in raw:
                    continue
                body = raw[raw.index('$'):].split('*')[0].strip()
                fields = body.split(',')
                tag = fields[0]
                if tag in ('$GPGGA', '$GNGGA'):
                    g = pr.parse_gga(fields)
                    if g and g['qual'] >= 1:
                        ggas.append(g)
                elif tag == '$PSTMTS':
                    rec = pr.parse_ts(fields)
                    if rec:
                        ts_rows.append((t_us, rec))
            else:
                f7 = raw.strip().split(',')
                if len(f7) != 7:
                    continue
                try:
                    t_us = int(f7[0])
                    ax, ay, az, gx, gy, gz = (float(v) for v in f7[1:])
                except ValueError:
                    continue
                if t_first is None:
                    t_first = t_us
                b = (t_us - t_first) // dt_us
                if fwd == 'x':
                    a2 = (ax * G0, ay * G0)
                else:
                    a2 = (ay * G0, -ax * G0)
                gz_si = gz * math.pi / 180.0
                s = sums.setdefault(b, [0.0, 0.0, 0.0, 0])
                s[0] += a2[0]; s[1] += a2[1]; s[2] += gz_si; s[3] += 1
    bins = {b: (s[0] / s[3], s[1] / s[3], s[2] / s[3])
            for b, s in sums.items()}
    mid = ggas[len(ggas) // 2]
    anchor_ecef = pr.geodetic_to_ecef(mid['lat'], mid['lon'], mid['alt'])
    anchor = (mid['lat'], mid['lon'], mid['alt'], anchor_ecef)
    epochs = []
    for t_us, rec in ts_rows:
        if rec['dsp'] != 1 or rec['satdat'] != 1:
            continue
        sv = (rec['sx'], rec['sy'], rec['sz'])
        if not (24e6 <= math.sqrt(sv[0]**2 + sv[1]**2 + sv[2]**2)
                <= 29.5e6):
            continue
        item = (rec['satid'], rec['psr'], sv, rec['cn0'])
        if epochs and t_us - epochs[-1]['t_last'] <= 500000:
            epochs[-1]['svs'].append(item)
            epochs[-1]['t_last'] = t_us
        else:
            epochs.append({'t_us': t_us, 't_last': t_us, 'svs': [item]})
    return bins, epochs, anchor, t_first

def enu_rotation(lat_deg, lon_deg):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    return np.array([
        [-math.sin(lo), math.cos(lo), 0.0],
        [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo),
         math.cos(la)],
        [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
         math.sin(la)]])


class TcAmb:
    """One clock variant of the TC harness (design sections 2-3)."""

    def __init__(self, clock_drift, anchor_ecef, rot):
        self.cd = clock_drift
        self.nc = 2 if clock_drift else 1
        self.ns = 8 + self.nc + NSLOT
        self.anchor = np.array(anchor_ecef)
        self.rot = rot
        rng = np.random.default_rng(9000)  # sim's runner seed
        x8, P8 = sim.init_state('open', np.zeros(2), rng)
        self.x = np.zeros(self.ns)
        self.x[:8] = x8
        self.P = np.zeros((self.ns, self.ns))
        self.P[:8, :8] = P8
        self.P[8, 8] = 30.0 ** 2                    # run_tc clock prior
        if clock_drift:
            self.P[9, 9] = 1.0 ** 2                 # run_tc drift prior
        for i in range(NSLOT):
            self.P[8 + self.nc + i, 8 + self.nc + i] = (50e3) ** 2
        self.slots = {}        # satid -> slot index
        self.slot_sv = [None] * NSLOT
        self.slot_seen = [0.0] * NSLOT
        self.started = False
        self.n_acc = 0
        self.n_rej = 0
        self.n_def = 0
        self.tracked_s = 0.0   # epoch-stream time, gaps capped
        self.last_ep_t = None

    def sv_enu(self, sv_ecef):
        return self.rot @ (np.array(sv_ecef) - self.anchor)

    def predict(self, acc, gyro):
        ns = self.ns
        F = np.eye(ns)
        F[:8, :8] = sim.jac_F(self.x[:8], acc)
        xn = self.x.copy()
        xn[:8] = sim.mech(self.x[:8], acc, gyro)
        if self.cd:
            xn[8] = self.x[8] + self.x[9] * sim.DT
            F[8, 9] = sim.DT
        Q = np.zeros((ns, ns))
        Q[:8, :8] = sim.QD
        if self.cd:
            Q[8, 8] = 0.1 ** 2 * sim.DT             # run_tc values
            Q[9, 9] = 0.02 ** 2 * sim.DT
        else:
            Q[8, 8] = 2.0 ** 2 * sim.DT
        self.x = xn
        self.P = F @ self.P @ F.T + Q

    def _free_stale(self):
        # Staleness is measured in TRACKED time: an SV absent
        # while the receiver tracked others may have changed
        # channel; an SV absent across a total outage (no
        # epochs at all) keeps its slot - its ambiguity is a
        # property of the (SV, channel) pair, and re-deriving
        # it from a post-outage subset median would shift the
        # gauge by the subset's N-median (self-test finding,
        # design addendum 2026-11-07).
        for satid, sl in list(self.slots.items()):
            if self.tracked_s - self.slot_seen[sl] > SLOT_STALE_S:
                del self.slots[satid]
                self.slot_sv[sl] = None

    def _alloc(self, satid, t_s):
        for i in range(NSLOT):
            if self.slot_sv[i] is None:
                self.slots[satid] = i
                self.slot_sv[i] = satid
                self.slot_seen[i] = self.tracked_s
                return i
        return None

    def epoch(self, ep, t_s):
        """Process one 1 Hz pseudorange epoch. Returns
        (n_accepted, n_rejected) for this epoch."""
        if self.last_ep_t is not None:
            self.tracked_s += min(t_s - self.last_ep_t, 2.0)
        self.last_ep_t = t_s
        self._free_stale()
        for i in range(NSLOT):  # stiff ambiguity RW, per epoch
            j = 8 + self.nc + i
            self.P[j, j] += RW_N ** 2
        rows = []  # (satid, psr, sv_enu, cn0, range, raw_resid, slot)
        for satid, psr, sv_ecef, cn0 in ep['svs']:
            sv = self.sv_enu(sv_ecef)
            d = sv - np.array([self.x[0], self.x[1], 0.0])
            r = float(np.linalg.norm(d))
            raw = psr - (r + self.x[8])
            rows.append([satid, psr, sv, cn0, r, raw,
                         self.slots.get(satid)])
        fresh = not self.started
        if fresh:
            if len(rows) < 4:
                return (0, 0)
            self.x[8] = float(np.median([rw[5] for rw in rows]))
            self.started = True
        # --- initialise new ambiguity slots (design section 3
        # as amended by the self-test addendum: the gauge is
        # anchored ONCE, at the first epoch, via the clock
        # seed above. Later inits split against the LIVE
        # innovations' median, never against a candidate
        # subset's own median - a subset median differs from
        # the clock's carried gauge by the sampling spread
        # of the N's (~tens of km) and would poison it.
        cand = [rw for rw in rows if rw[6] is None]
        if cand:
            if fresh and len(cand) >= 4:
                # rows' residuals predate the seed, so the
                # candidate median IS the seeded clock value:
                # N := raw - median anchors the gauge once.
                common = float(np.median([rw[5] for rw in cand]))
            else:
                live_innov = [rw[5] - self.x[8 + self.nc + rw[6]]
                              for rw in rows if rw[6] is not None]
                common = (float(np.median(live_innov)) if live_innov
                          else None)
            if common is None:
                self.n_def += len(rows)
                return (0, len(rows))  # unanchored; defer epoch
            for rw in cand:
                sl = self._alloc(rw[0], t_s)
                if sl is None:
                    continue
                j = 8 + self.nc + sl
                self.x[j] = rw[5] - common
                self.P[j, :] = 0.0
                self.P[:, j] = 0.0
                self.P[j, j] = SIG_N0 ** 2
                rw[6] = sl
        # --- sequential gated updates, strongest signal first
        acc_e = rej_e = 0
        for rw in sorted(rows, key=lambda r: -r[3]):
            satid, psr, sv, cn0, r, raw, sl = rw
            if sl is None:
                continue
            self.slot_seen[sl] = self.tracked_s
            j = 8 + self.nc + sl
            d = sv - np.array([self.x[0], self.x[1], 0.0])
            r_now = float(np.linalg.norm(d))
            H = np.zeros((1, self.ns))
            H[0, 0] = -d[0] / r_now
            H[0, 1] = -d[1] / r_now
            H[0, 8] = 1.0
            H[0, j] = 1.0
            innov = psr - (r_now + self.x[8] + self.x[j])
            S = float((H @ self.P @ H.T)[0, 0]) + SIG_PR ** 2
            if abs(innov) <= 4.0 * math.sqrt(S):
                self.x, self.P = sim._scalar_update(
                    self.x, self.P, innov, H, SIG_PR ** 2)
                acc_e += 1
            else:
                rej_e += 1
        self.n_acc += acc_e
        self.n_rej += rej_e
        return (acc_e, rej_e)

def run_variant(clock_drift, bins, epochs, anchor, t_first):
    rot = enu_rotation(anchor[0], anchor[1])
    f = TcAmb(clock_drift, anchor[3], rot)
    dt_us = int(sim.DT * 1e6)
    ep_at = {}
    for ep in epochs:
        k = int(round((ep['t_us'] - t_first) / dt_us))
        ep_at.setdefault(k, []).append(ep)
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
            a, r = f.epoch(ep, k * sim.DT)
            trace.append({'t_s': k * sim.DT, 'acc': a, 'rej': r,
                          'x': float(f.x[0]), 'y': float(f.x[1]),
                          'clk': float(f.x[8])})
    return f, trace


def score(trace, gap):
    out = {}
    if gap is None:
        seg = [t for t in trace if t['t_s'] > 10.0]
        out['rmse_static_m'] = float(np.sqrt(np.mean(
            [t['x'] ** 2 + t['y'] ** 2 for t in seg]))) if seg else None
        return out
    t0, t1 = gap
    pre = [t for t in trace if 10.0 < t['t_s'] < t0]
    post = [t for t in trace if t['t_s'] >= t1]
    out['pre_rmse_m'] = float(np.sqrt(np.mean(
        [t['x'] ** 2 + t['y'] ** 2 for t in pre]))) if pre else None
    out['pre_rej'] = int(sum(t['rej'] for t in pre))
    out['pre_acc'] = int(sum(t['acc'] for t in pre))
    out['post_rej'] = int(sum(t['rej'] for t in post))
    out['post_acc'] = int(sum(t['acc'] for t in post))
    rec = next((t for t in post if t['acc'] >= 4), None)
    out['recovery_s'] = (float(rec['t_s'] - t1) if rec else None)
    if rec:
        after = [t for t in post if t['t_s'] >= rec['t_s'] + 30.0]
        out['post_rmse_m'] = float(np.sqrt(np.mean(
            [t['x'] ** 2 + t['y'] ** 2 for t in after]))) if after else None
    return out


def common_mode(epochs, anchor, nco_hz=None):
    """Leg 1 (design section 5, as amended 2026-11-07): the
    module's $PSTMTS common term, from consecutive-epoch
    residue differences. Three properties of the data drive
    the estimator (all measured, see the design addendum):
    per-SV residues hop by whole 200 ms cells between
    epochs (removed by rounding each difference to the
    nearest cell); the differences accumulate over the
    MODULE's 1 Hz epochs, not the logger's jittered
    arrival times (no dt division - dividing by logger dt
    was tried and injects the jitter as noise); and a
    pair is admitted only with >= 4 SVs in common, which
    keeps the cross-SV median on the agreeing majority.
    Returns (series, stats); series rows are
    (epoch_idx, rate_m_per_epoch, common_m, detrended_m)
    on the longest contiguous admitted run."""
    anchor_ecef = np.array(anchor[3])
    m200 = 299792458.0 * 1e-3  # 1 ms grid (divides 200 ms);
    # whole-ms common jumps ride on ~30% of epoch pairs in
    # the sky capture - folding mod 1 ms removes them and
    # the 200 ms cell hops alike (review #9, verified)
    prev = {}
    admitted = []  # (epoch_idx, median difference)
    for i, ep in enumerate(epochs):
        cur = {}
        for satid, psr, sv_ecef, cn0 in ep['svs']:
            geo = float(np.linalg.norm(np.array(sv_ecef) - anchor_ecef))
            cur[satid] = geo - psr
        ds = []
        for s, v in cur.items():
            if s in prev:
                d = v - prev[s]
                ds.append(d - m200 * round(d / m200))
        if len(ds) >= 4:
            admitted.append((i, float(np.median(ds))))
        prev = cur
    if not admitted:
        return [], {}
    rv = np.array([v for _, v in admitted])
    idx = np.array([i for i, _ in admitted])
    # longest contiguous run (epoch-index gaps <= 2)
    best = cur = [0]
    for j in range(1, len(idx)):
        cur = cur + [j] if idx[j] - idx[j - 1] <= 2 else [j]
        if len(cur) > len(best):
            best = cur
    seg = np.array(best)
    cseg = np.cumsum(rv[seg])
    tseg = (idx[seg] - idx[seg[0]]).astype(float)
    A2 = np.vstack([tseg, np.ones_like(tseg)]).T
    s2, i2 = np.linalg.lstsq(A2, cseg, rcond=None)[0]
    dseg = cseg - (s2 * tseg + i2)
    series = [(float(tseg[k]), float(rv[seg[k]]),
               float(cseg[k]), float(dseg[k]))
              for k in range(len(tseg))]
    stats = {'rate_median_m_per_epoch': float(np.median(rv)),
             'rate_iqr_m': float(np.percentile(rv, 75)
                                 - np.percentile(rv, 25)),
             'pairs_used': len(admitted),
             'longest_run_epochs': int(len(seg))}
    if nco_hz is not None:
        stats['nco_implied_rate_m_per_epoch'] = float(
            nco_hz * 299792458.0 / 1575.42e6)
        stats['rate_minus_nco_m_per_epoch'] = float(
            np.median(rv) - stats['nco_implied_rate_m_per_epoch'])
    return series, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('capture')
    ap.add_argument('--out', default=None)
    ap.add_argument('--gap', default=None,
                    help='blockage window T0:T1 in logger seconds')
    ap.add_argument('--common-mode', action='store_true')
    ap.add_argument('--fwd', default='x', choices=('x', 'y'))
    a = ap.parse_args(argv)
    out_dir = a.out or os.path.dirname(os.path.abspath(a.capture))
    os.makedirs(out_dir, exist_ok=True)
    bins, epochs, anchor, t_first = load_capture(a.capture, a.fwd)
    print(f'capture: {a.capture}')
    print(f'epochs: {len(epochs)}  imu bins: {len(bins)}  '
          f'anchor: {anchor[0]:.6f}, {anchor[1]:.6f}')
    if a.common_mode:
        import psr_residue as _pr
        ncos = []
        with open(a.capture, errors='replace') as fh:
            for raw in fh:
                if raw.startswith('G,') and '$PSTMTG' in raw:
                    tg = _pr.parse_tg(raw[raw.index('$'):]
                                      .split('*')[0].strip().split(','))
                    if tg:
                        ncos.append(tg['nco'])
        nco_med = float(np.median(ncos)) if ncos else None
        series, stats = common_mode(epochs, anchor, nco_med)
        with open(os.path.join(out_dir, 'common_mode.csv'), 'w') as fh:
            fh.write('t_s,rate_m_s,common_m,detrended_m\n')
            for row in series:
                fh.write(','.join(f'{v:.3f}' for v in row) + '\n')
        print(json.dumps(stats, indent=1))
        with open(os.path.join(out_dir, 'common_mode_summary.json'),
                  'w') as fh:
            json.dump(stats, fh, indent=1)
        return 0
    gap = None
    if a.gap:
        g0, g1 = a.gap.split(':')
        gap = (float(g0), float(g1))
    summary = {'capture': a.capture, 'gap': gap,
               'sig_pr': SIG_PR, 'variants': {}}
    for name, cd in (('TC-EKF-AMB', False), ('TC-EKF-AMB-CD', True)):
        f, trace = run_variant(cd, bins, epochs, anchor, t_first)
        sc = score(trace, gap)
        sc['total_acc'] = f.n_acc
        sc['total_rej'] = f.n_rej
        sc['total_def'] = f.n_def
        summary['variants'][name] = sc
        with open(os.path.join(out_dir, f'trace_{name}.csv'), 'w') as fh:
            fh.write('t_s,acc,rej,x,y,clk\n')
            for t in trace:
                fh.write(f"{t['t_s']:.1f},{t['acc']},{t['rej']},"
                         f"{t['x']:.3f},{t['y']:.3f},{t['clk']:.3f}\n")
        print(name, json.dumps(sc))
    with open(os.path.join(out_dir, 'tc_summary.json'), 'w') as fh:
        json.dump(summary, fh, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
