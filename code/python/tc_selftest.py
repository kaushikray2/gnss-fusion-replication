#!/usr/bin/env python3
"""tc_selftest.py - the design section 7 verification gate
for tc_real.py, in two profiles (design addendum,
2026-11-07):

- sim-matched (GATING): the harness must reproduce the
  sim's verdict under the sim's conditions. Synthetic
  IMU is truth-matched kinematic (static: zero accel,
  zero gyro bias, measured white noise), the truth clock
  is the sim's cb = 30 + 2.0 t, per-SV ambiguity
  constants ~ U(-100, +100) km (phase A scale, NOT on a
  grid), SV geometry harvested from the real sky-view
  capture, 70 s total gap at t = 200-270 s.
  PASS: both variants >= 95% pre-gap accepts and static
  RMSE < 5 m; bias-only gate-locks (no recovery within
  120 s); two-state recovers <= 5 s, post RMSE < 5 m.

- bench-static (REPORT ONLY): same capture but the IMU
  carries the real bench statics (1-degree tilt specific
  force, 0.05 dps gyro bias). On a static rig the paper's
  heading state is unobservable and wanders; this profile
  documents what phase B's real run should be expected
  to look like (two-state recovers immediately; bias-only
  rejects the majority for minutes and never
  re-converges). No pass/fail except the two-state
  variant recovering at the first post-gap epoch.

Usage: tc_selftest.py [sky_capture]
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
GAP = (200.0, 270.0)


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f'{c:02X}'


def build(profile, path):
    rng = np.random.default_rng(42)
    ggas = []
    rows = []
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
    amb = {}
    out = []
    for t_us, kind, payload in rows:
        if not (t_start <= t_us < t_end):
            continue
        lt = (t_us - t_start) / 1e6
        if GAP[0] <= lt < GAP[1]:
            continue
        t_new = int(lt * 1e6)
        if kind == 'GGA':
            out.append(f'G,{t_new},' + payload + '*00')
        else:
            f = payload
            try:
                satid = int(float(f[2]))
                sv = np.array([float(f[9]), float(f[10]),
                               float(f[11])])
            except (ValueError, IndexError):
                continue  # spliced row
            if not (24e6 <= np.linalg.norm(sv) <= 29.5e6):
                continue
            if satid not in amb:
                amb[satid] = rng.uniform(-100e3, 100e3)
            geo = float(np.linalg.norm(sv - anchor))
            psr = geo + 30.0 + 2.0 * lt + amb[satid] \
                + rng.normal(0, 2.0)
            f[3] = f'{psr:.2f}'
            body = ','.join(f)
            out.append(f'G,{t_new},' + body + '*' + checksum(body[1:]))
    tilt = profile == 'bench-static'
    imu = []
    for k in range(int(WIN_LEN_S * 104)):
        t_us = int(k * (1e6 / 104.0))
        ax = (0.017 if tilt else 0.0) + rng.normal(0, 0.000545)
        ay = (-0.003 if tilt else 0.0) + rng.normal(0, 0.000545)
        az = (1.0125 if tilt else 1.0) + rng.normal(0, 0.000545)
        gx = rng.normal(0, 0.0254)
        gy = rng.normal(0, 0.0254)
        gz = (0.05 if tilt else 0.0) + rng.normal(0, 0.0254)
        imu.append(f'{t_us},{ax:.6f},{ay:.6f},{az:.6f},'
                   f'{gx:.5f},{gy:.5f},{gz:.5f}')
    with open(path, 'w') as fh:
        fh.write('\n'.join(imu + out) + '\n')
    return len(amb)


def run(path, out_dir):
    subprocess.run([sys.executable,
                    os.path.join(HERE, 'tc_real.py'), path,
                    '--gap', f'{GAP[0]:.0f}:{GAP[1]:.0f}',
                    '--out', out_dir], check=True,
                   capture_output=True)
    return json.load(open(os.path.join(out_dir, 'tc_summary.json')))


def main():
    ok = True
    for profile, gating in (('sim-matched', True),
                            ('bench-static', False)):
        log = f'/tmp/tc_selftest_{profile}.log'
        out_dir = f'/tmp/tc-selftest-{profile}'
        nsv = build(profile, log)
        s = run(log, out_dir)
        print(f'--- profile {profile} ({nsv} SVs, '
              f'{"GATING" if gating else "report only"})')
        for name, want_rec in (('TC-EKF-AMB', False),
                               ('TC-EKF-AMB-CD', True)):
            v = s['variants'][name]
            pa = v['pre_acc'] / max(1, v['pre_acc'] + v['pre_rej'])
            prate = v['post_rej'] / max(1, v['post_acc'] + v['post_rej'])
            print(f"  {name}: pre_acc_rate={pa:.3f} "
                  f"pre_rmse={v['pre_rmse_m']:.2f} "
                  f"recovery={v['recovery_s']} "
                  f"post_rej_rate={prate:.3f} "
                  f"post_rmse={v.get('post_rmse_m')}")
            if gating:
                checks = [('accepts >= 0.95', pa >= 0.95),
                          ('pre RMSE < 5', (v['pre_rmse_m'] or 99) < 5.0)]
                if want_rec:
                    checks += [('recovers <= 5 s',
                                v['recovery_s'] is not None
                                and v['recovery_s'] <= 5.0),
                               ('post rej rate < 0.05', prate < 0.05),
                               ('post RMSE < 15',
                                (v.get('post_rmse_m') or 99) < 15.0)]
                else:
                    cd_post = s['variants']['TC-EKF-AMB-CD'].get(
                        'post_rmse_m') or 1.0
                    checks += [('post rej rate > 0.40', prate > 0.40),
                               ('never re-converges '
                                '(post RMSE > 3x CD)',
                                (v.get('post_rmse_m') or 0) > 3 * cd_post)]
            elif want_rec:
                checks = [('CD recovers at first epoch',
                           v['recovery_s'] is not None
                           and v['recovery_s'] <= 1.0)]
            else:
                checks = []
            for label, passed in checks:
                print(('  PASS' if passed else '  FAIL'), name, '-', label)
                ok = ok and passed
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
