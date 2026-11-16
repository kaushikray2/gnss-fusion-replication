#!/usr/bin/env python3
"""tc_delta_selftest.py - the verification gate for
tc_delta.py (design addenda 1 + 5 discipline: synthetic
known truth first, criteria fixed before the run).

Synthetic capture in logger format, built on SV geometry
harvested from the real sky-view capture (same 600 s
window as tc_selftest). Pseudoranges are generated in
DIFFERENCES, as the module presents them:
  dPsR = dGeo + (NOMINAL + rho_true(t)) + noise(5 m)
with a persistent per-SV ambiguity seed on (re)acquisition,
whole-1 ms common jumps on ~30% of epochs, per-SV 200 ms
cell hops (2%) and 1 ms hops (1%) - all of which the
M1 fold must absorb. NOMINAL = 9023.92 m/epoch and the
synthetic $PSTMTG carries the matching NCO -47421 Hz, so
the residual the variants fight over is exactly rho_true:
  rho_true = 0.5 m/epoch until t = 150 s, then slews
  +1.0 m/epoch per epoch to a cap of 150.5 (reached at
  t = 300 s), then holds. The slew is a standing property
  of the truth oscillator, present before, during and
  after the gap - the faithful analogue of the sim's
  cb = 30 + 2.0 t, whose drift is learnable pre-outage.
  (First version started the slew AT the gap: v2's
  derivative state then had nothing learned to
  extrapolate and its smaller Q strictly handicapped
  it - a test-design flaw, identified from the run's
  own numbers, not a harness bug. v2's rate tracking
  was already the best of the three in that run.)
Gap: no GNSS rows at t = 200-290 s; IMU continues.
IMU is the sim-matched profile of tc_selftest.

PASS criteria (fixed a priori; position RMSE is REPORTED
but not gated - delta ranges constrain velocity and the
clock, position only weakly, which is a property of the
observable, not of the clock comparison):
  v1, v2: pre-gap accept rate >= 0.95 (v0's is reported:
  with a slewing truth rate it degrades pre-gap too,
  which is itself the v0 signature)
  v1, v2: median |rate - 0.5| over t = 100-140 s < 2.0
  v0: post-gap rejection rate > 0.80
  v1, v2: both recover (first post-gap epoch, >= 4 acc)
  v2 recovery <= v1 recovery; v2 post rej <= v1 post rej
  v1, v2: median |rate - 150.5| over t >= 500 s < 10
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psr_residue as pr  # noqa: E402

SKY = sys.argv[1] if len(sys.argv) > 1 else (
    os.path.join(HERE, '..', '..', 'data', 'psr-skyview',
                 'GNSS_Data.hostclean.txt'))
WIN_START_S = 1800.0
WIN_LEN_S = 600.0
GAP = (200.0, 290.0)
NOMINAL = 9023.92
NCO = -47421.0
C = 299792458.0
M1 = C * 1e-3
M200 = C * 0.2
SIG_D = 5.0


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f'{c:02X}'


def rho_true(t):
    if t < 150.0:
        return 0.5
    return min(0.5 + 1.0 * (t - 150.0), 150.5)


def build(path):
    rng = np.random.default_rng(7)
    ggas, tg_tpl, rows = [], None, []
    with open(SKY, errors='replace') as fh:
        for raw in fh:
            if not raw.startswith('G,') or '$' not in raw:
                continue
            try:
                t_us = int(raw[2:raw.index(',', 2)])
            except ValueError:
                continue
            body = raw[raw.index('$'):].split('*')[0].strip()
            fields = body.split(',')
            if fields[0] in ('$GPGGA', '$GNGGA'):
                g = pr.parse_gga(fields)
                if g and g['qual'] >= 1:
                    ggas.append(g)
                    rows.append((t_us, 'GGA', body))
            elif fields[0] == '$PSTMTG':
                if tg_tpl is None:
                    tg_tpl = fields
                rows.append((t_us, 'TG', None))
            elif fields[0] == '$PSTMTS':
                rows.append((t_us, 'TS', fields))
    t_start = rows[0][0] + int(WIN_START_S * 1e6)
    t_end = t_start + int(WIN_LEN_S * 1e6)
    win_ggas = []
    gi = 0
    for (t_us, kind, payload) in rows:
        if kind == 'GGA':
            if t_start <= t_us < t_end:
                win_ggas.append(ggas[gi])
            gi += 1
    mid = win_ggas[len(win_ggas) // 2]
    anchor = np.array(pr.geodetic_to_ecef(mid['lat'], mid['lon'],
                                          mid['alt']))
    tow0 = float(tg_tpl[2])
    out = []
    psr_clean, jump_lvl, prev_geo = {}, {}, {}
    prev_lt, common_lvl = None, 0.0
    ep_open = False
    for (t_us, kind, payload) in rows:
        if not (t_start <= t_us < t_end):
            continue
        lt = (t_us - t_start) / 1e6
        if GAP[0] <= lt < GAP[1]:
            continue
        t_new = int(lt * 1e6)
        if kind == 'GGA':
            out.append(f'G,{t_new},' + payload + '*00')
        elif kind == 'TG':
            f = list(tg_tpl)
            f[2] = f'{tow0 + lt:.4f}'
            f[6] = f'{NCO:.0f}'
            body = ','.join(f)
            out.append(f'G,{t_new},' + body + '*'
                       + checksum(body[1:]))
            ep_open = True
        else:
            f = list(payload)
            try:
                satid = int(float(f[2]))
                sv = np.array([float(f[9]), float(f[10]),
                               float(f[11])])
            except (ValueError, IndexError):
                continue
            if not (24e6 <= np.linalg.norm(sv) <= 29.5e6):
                continue
            geo = float(np.linalg.norm(sv - anchor))
            contiguous = (prev_lt is not None
                          and abs(lt - prev_lt) <= 1.5)
            if satid not in psr_clean or not contiguous:
                psr_clean[satid] = geo + rng.uniform(-150e3, 150e3)
                jump_lvl[satid] = 0.0
            else:
                dpsr = ((geo - prev_geo[satid]) + NOMINAL
                        + rho_true(lt) + rng.normal(0, SIG_D))
                psr_clean[satid] += dpsr
            if ep_open and rng.random() < 0.30:
                common_lvl += rng.choice([-1.0, 1.0]) * M1
                ep_open = False
            if rng.random() < 0.02:
                jump_lvl[satid] += rng.choice([-1.0, 1.0]) * M200
            if rng.random() < 0.01:
                jump_lvl[satid] += rng.choice([-1.0, 1.0]) * M1
            f[3] = f'{psr_clean[satid] + jump_lvl[satid] + common_lvl:.2f}'
            body = ','.join(f)
            out.append(f'G,{t_new},' + body + '*'
                       + checksum(body[1:]))
            prev_geo[satid] = geo
            prev_lt = lt
    imu = []
    for k in range(int(WIN_LEN_S * 104)):
        t_us = int(k * (1e6 / 104.0))
        ax = rng.normal(0, 0.000545)
        ay = rng.normal(0, 0.000545)
        az = 1.0 + rng.normal(0, 0.000545)
        gx = rng.normal(0, 0.0254)
        gy = rng.normal(0, 0.0254)
        gz = rng.normal(0, 0.0254)
        imu.append(f'{t_us},{ax:.6f},{ay:.6f},{az:.6f},'
                   f'{gx:.5f},{gy:.5f},{gz:.5f}')
    with open(path, 'w') as fh:
        fh.write('\n'.join(imu + out) + '\n')


def read_trace(out_dir, name):
    rows = []
    with open(os.path.join(out_dir, f'trace_{name}.csv')) as fh:
        hdr = fh.readline()
        for line in fh:
            v = line.strip().split(',')
            rows.append({'t': float(v[0]), 'acc': int(v[1]),
                         'rej': int(v[2]), 'x': float(v[3]),
                         'y': float(v[4]), 'rate': float(v[5])})
    return rows


def main():
    log = '/tmp/tc_delta_selftest.log'
    out_dir = '/tmp/tc-delta-selftest'
    build(log)
    subprocess.run([sys.executable,
                    os.path.join(HERE, 'tc_delta.py'), log,
                    '--gap', f'{GAP[0]:.0f}:{GAP[1]:.0f}',
                    '--out', out_dir], check=True)
    s = json.load(open(os.path.join(out_dir,
                                    'tc_delta_summary.json')))
    names = ('DELTA-v0-noclock', 'DELTA-v1-rateRW',
             'DELTA-v2-rateRD')
    tr = {n: read_trace(out_dir, n) for n in names}
    ok = True

    def check(label, passed):
        nonlocal ok
        print(('  PASS' if passed else '  FAIL'), '-', label)
        ok = ok and passed

    for n in names:
        v = s['variants'][n]
        pa = v['pre_acc'] / max(1, v['pre_acc'] + v['pre_rej'])
        prate = v['post_rej'] / max(1, v['post_acc'] + v['post_rej'])
        rmse = math.sqrt(np.mean([r['x'] ** 2 + r['y'] ** 2
                                  for r in tr[n] if r['t'] > 10]))
        print(f"  {n}: pre_acc_rate={pa:.3f} "
              f"recovery={v['recovery_s']} "
              f"post_rej_rate={prate:.3f} "
              f"pos_rmse_all={rmse:.2f} (reported)")
        if n != 'DELTA-v0-noclock':
            check(f'{n} pre-gap accept >= 0.95', pa >= 0.95)
    for n in ('DELTA-v1-rateRW', 'DELTA-v2-rateRD'):
        pre_rate = np.median([abs(r['rate'] - 0.5) for r in tr[n]
                              if 100 <= r['t'] <= 140])
        late_rate = np.median([abs(r['rate'] - 150.5)
                               for r in tr[n] if r['t'] >= 500])
        print(f'  {n}: pre rate err={pre_rate:.2f} '
              f'late rate err={late_rate:.2f}')
        check(f'{n} tracks pre-gap rate', pre_rate < 2.0)
        check(f'{n} re-converges in rate', late_rate < 10.0)
        check(f'{n} recovers',
              s['variants'][n]['recovery_s'] is not None)
    v0 = s['variants']['DELTA-v0-noclock']
    v1 = s['variants']['DELTA-v1-rateRW']
    v2 = s['variants']['DELTA-v2-rateRD']
    pr0 = v0['post_rej'] / max(1, v0['post_acc'] + v0['post_rej'])
    pr1 = v1['post_rej'] / max(1, v1['post_acc'] + v1['post_rej'])
    pr2 = v2['post_rej'] / max(1, v2['post_acc'] + v2['post_rej'])
    check('v0 post-gap rejection > 0.80', pr0 > 0.80)
    check('v2 recovers no later than v1',
          v2['recovery_s'] is not None and v1['recovery_s'] is not None
          and v2['recovery_s'] <= v1['recovery_s'])
    check('v2 post rejection <= v1', pr2 <= pr1)
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
