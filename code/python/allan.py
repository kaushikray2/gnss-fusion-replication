#!/usr/bin/env python3
"""Allan-deviation calibration for the fusion bake-off (Stage 2 tooling).

Reads a Stage 1 logger CSV (IMU rows: t_us,ax,ay,az,gx,gy,gz in g and
dps) from a STATIC recording and estimates, per axis:
  * white-noise density from the tau^-1/2 branch,
  * bias instability (floor of the Allan deviation, /0.664),
and maps them onto the simulator's parameters (simulation/sim.py):
  SIG_G, SIG_A  per-sample white sigma at the sim's IMU rate
                = density * sqrt(rate_hz)
  BG_SD, BA_SD  sim draws a static per-run bias ~ N(0, SD); the honest
                static-log estimate of that magnitude is the bias
                instability (labelled as such in the output).

Usage:  python3 allan.py LOG.csv [--rate 100] [--sim-rate 10]
        python3 allan.py --selftest
"""
import argparse, sys
import numpy as np

def load_imu(path):
    ts, rows = [], []
    with open(path) as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) != 7:
                continue  # GNSS/SAT/comment rows are not IMU samples
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                continue
            ts.append(vals[0]); rows.append(vals[1:])
    if len(rows) < 1000:
        raise SystemExit('only %d IMU rows - not a usable static log' % len(rows))
    return np.array(ts), np.array(rows)

def oadev(x, fs):
    """Overlapping Allan deviation of a rate series x sampled at fs."""
    n = len(x)
    max_m = max(1, n // 4)
    cs = np.concatenate(([0.0], np.cumsum(x)))
    taus, devs = [], []
    m = 1
    while m <= max_m:
        k = n - 2 * m + 1
        if k <= 10:
            break
        a1 = (cs[m:m + k] - cs[0:k]) / m
        a2 = (cs[2 * m:2 * m + k] - cs[m:m + k]) / m
        var = float(np.sum((a2 - a1) ** 2) / (2 * k))
        taus.append(m / fs); devs.append(np.sqrt(var))
        m = int(m * 1.5) + 1
    return np.array(taus), np.array(devs)

def estimate(x, fs):
    """Return (noise_density_per_sqrt_hz, bias_instability) for one axis."""
    taus, devs = oadev(x, fs)
    head = min(5, len(devs))
    density = float(np.median(devs[:head] * np.sqrt(taus[:head])))
    bias_inst = float(np.min(devs) / 0.664)
    return density, bias_inst, taus, devs

def analyse(ts, imu, rate, sim_rate):
    dt = np.diff(ts) / 1e6
    print('samples: %d, span %.1f s, dt median %.4f s (nominal %.4f)'
          % (len(ts), (ts[-1] - ts[0]) / 1e6, float(np.median(dt)), 1.0 / rate))
    gyr = imu[:, 3:6] * (np.pi / 180.0)      # dps -> rad/s
    acc = imu[:, 0:3] * 9.80665              # g -> m/s^2
    out = {}
    for name, arr in (('gyro', gyr), ('accel', acc)):
        dens, binst = [], []
        for ax in range(3):
            d, b, taus, devs = estimate(arr[:, ax], rate)
            dens.append(d); binst.append(b)
            print('%s axis %d: density %.3e /sqrt(Hz), bias instability %.3e'
                  % (name, ax, d, b))
        out[name] = (float(np.mean(dens)), float(np.mean(binst)))
    gd, gb = out['gyro']; ad, ab = out['accel']
    print()
    print('Suggested simulator parameters (per-sample sigma at %.0f Hz):' % sim_rate)
    print('  SIG_G = %.4f rad/s   (density %.3e * sqrt(rate))' % (gd * np.sqrt(sim_rate), gd))
    print('  SIG_A = %.4f m/s^2   (density %.3e * sqrt(rate))' % (ad * np.sqrt(sim_rate), ad))
    print('  BG_SD ~ %.4f rad/s   (bias instability, static-log estimate)' % gb)
    print('  BA_SD ~ %.4f m/s^2   (bias instability, static-log estimate)' % ab)

def selftest():
    rng = np.random.default_rng(7)
    fs, dur = 100.0, 2000
    n = int(fs * dur)
    sig_sample = 0.30                      # dps per-sample white sigma at 100 Hz
    true_density = sig_sample / np.sqrt(fs)
    walk = np.cumsum(rng.normal(0, 0.0006, n))   # slow bias random walk, dps
    gz = rng.normal(0, sig_sample, n) + 1.2 + walk
    d, b, taus, devs = estimate(gz, fs)
    print('selftest gyro-z: true density %.4f dps/sqrt(Hz), recovered %.4f (%.0f%%)'
          % (true_density, d, 100.0 * d / true_density))
    assert abs(d / true_density - 1.0) < 0.25, 'density recovery outside 25%'
    print('selftest bias floor: %.4f dps (walk-driven, report only)' % b)
    # CSV round-trip with interleaved non-IMU rows
    import io, os, tempfile
    fd, path = tempfile.mkstemp(suffix='.csv'); os.close(fd)
    with open(path, 'w') as f:
        for i in range(5000):
            f.write('%d,0.01,-0.01,1.00,0.1,0.1,1.2\n' % (i * 10000))
            if i % 100 == 0:
                f.write('%d,GNSS,43.0,-83.0,200.0,1.0,9,1\n' % (i * 10000))
    ts, imu = load_imu(path); os.unlink(path)
    assert len(ts) == 5000 and imu.shape == (5000, 6), 'CSV parse failed'
    print('selftest CSV round-trip: 5000 IMU rows recovered, GNSS rows skipped')
    print('SELFTEST PASS')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log', nargs='?')
    ap.add_argument('--rate', type=float, default=100.0, help='logger IMU rate Hz')
    ap.add_argument('--sim-rate', type=float, default=10.0, help='simulator IMU rate Hz')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if not a.log:
        ap.error('a log file is required (or --selftest)')
    ts, imu = load_imu(a.log)
    analyse(ts, imu, a.rate, a.sim_rate)

if __name__ == '__main__':
    main()
