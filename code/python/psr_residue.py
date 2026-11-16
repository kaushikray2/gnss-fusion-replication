#!/usr/bin/env python3
"""psr_residue.py - $PSTMTS pseudorange residue test battery.

Reads a Stage 1 logger capture (rig #1 logger or logger_h745
format: IMU rows, '# comments', and 'G,t_us,$SENTENCE' rows),
groups the $PSTMTS lines into 1 Hz epochs, computes geometric
ranges from the $GPGGA fix, and runs the cross-SV residue tests
recorded in hardware/TS_PSR_NOTES.md:

  A  raw residues (geo - PsR): is there a constant offset?
  B  residues mod (c * 200 ms), per epoch: circular spread
  C  test B split by constellation (GPS SatID<=32, GLO >=65)
  D  residues mod (c * 20 ms), per epoch: circular spread
  E  largest-cluster test: does any epoch put all (or all but
     one) of its residues inside one +/-10 km arc on a grid?

Filters (notes, verified on the cold capture): a TS line is
usable only if dsp==1, Satdat==1 and the SV position radius is
in [24e6, 29.5e6] m - some lines carry garbage positions with
Satdat=1. On the cold-start capture /tmp/logger-run8.log this
battery reproduces the recorded verdict: no epoch clusters on
either grid, NCO ~ -47753 Hz. Bookkeeping on that file: 412 raw
TS lines, 283 parse cleanly (79 short module sentences and 50
spliced/corrupt console rows are dropped), 150 pass the filters
- the notes' ad hoc pass recorded 155; the 5-line delta sits in
the corrupt-line handling and changes no result.

Verdict rule (from the notes): if test E finds a clustering
epoch on the 20 ms or 200 ms grid, PsR is harness-ready with
per-line k resolved against the GGA fix. If residues still
scatter at ~1 ms, experiment 4 must plan on per-channel
ambiguity states or time-differenced PsR. Do not design around
single-epoch absolute PsR until a grid lands.

Usage: python3 psr_residue.py <capture.log>
Pure stdlib (no numpy) so it runs anywhere.
"""
import math
import sys

C = 299792458.0
M200 = C * 0.2          # 59,958,491.6 m - the 200 ms quantum
M20 = C * 0.02          # 5,995,849.16 m - the 20 ms grid
CLUSTER_HALF_M = 10000.0  # +/-10 km cluster window (notes)
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563


def parse_gga(fields):
    """fields = $GPGGA body split by ',' (checksum stripped)."""
    try:
        lat = float(fields[2])
        lon = float(fields[4])
        qual = int(fields[6])
        alt = float(fields[9])
    except (ValueError, IndexError):
        return None
    lat_deg = int(lat / 100) + (lat - 100 * int(lat / 100)) / 60.0
    if fields[3] == 'S':
        lat_deg = -lat_deg
    lon_deg = int(lon / 100) + (lon - 100 * int(lon / 100)) / 60.0
    if fields[5] == 'W':
        lon_deg = -lon_deg
    return {'lat': lat_deg, 'lon': lon_deg, 'alt': alt, 'qual': qual}


def geodetic_to_ecef(lat_deg, lon_deg, h):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    e2 = WGS84_F * (2.0 - WGS84_F)
    n = WGS84_A / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return ((n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - e2) + h) * math.sin(lat))


# $PSTMTS field order (UM2229 Table 142, pinned in the notes):
# dsp, SatID, PsR, Freq, plf, CN0, ttim, Satdat, SatX, SatY,
# SatZ, VelX, VelY, VelZ, Src, Ac, Difdat, Drc, Drrc, pred*
TS_FIELDS = ('dsp', 'satid', 'psr', 'freq', 'plf', 'cn0', 'ttim',
             'satdat', 'sx', 'sy', 'sz', 'vx', 'vy', 'vz', 'src',
             'ac', 'difdat', 'drc', 'drrc')


def parse_ts(fields):
    rec = {}
    try:
        for name, raw in zip(TS_FIELDS, fields[1:20]):
            rec[name] = float(raw)
    except ValueError:
        return None
    if len(rec) < len(TS_FIELDS):
        return None  # truncated line (capture edges)
    rec['satid'] = int(rec['satid'])
    rec['dsp'] = int(rec['dsp'])
    rec['satdat'] = int(rec['satdat'])
    rec['radius'] = math.sqrt(rec['sx'] ** 2 + rec['sy'] ** 2 +
                              rec['sz'] ** 2)
    return rec


def parse_tg(fields):
    """$PSTMTG: Week, TOW, TotSat, CPUTime, Timevalid, NCO, ..."""
    try:
        return {'tow': float(fields[2]), 'nco': float(fields[6])}
    except (ValueError, IndexError):
        return None


def load_capture(path):
    """Return (epochs, tg_ncos, n_ts_total).

    epochs: list of dicts {t_us, rx_ecef, lines:[ts rec + geo]}
    TS lines are clustered into epochs by logger time (a gap of
    more than 0.5 s starts a new epoch); each epoch takes the
    nearest valid (qual>=1) GGA position within 2 s, falling
    back to the median of all valid GGA positions in the file.
    """
    gga = []          # (t_us, parse_gga dict)
    tg_ncos = []
    ts_lines = []     # (t_us, ts rec)
    n_ts_raw = 0
    with open(path, errors='replace') as fh:
        for raw in fh:
            if not raw.startswith('G,'):
                continue
            try:
                t_us = int(raw[2:raw.index(',', 2)])
            except ValueError:
                continue
            if '$' not in raw:
                continue  # G-row whose sentence was spliced away
            body = raw[raw.index('$'):].split('*')[0].strip()
            fields = body.split(',')
            tag = fields[0]
            if tag in ('$GPGGA', '$GNGGA'):
                g = parse_gga(fields)
                if g:
                    gga.append((t_us, g))
            elif tag == '$PSTMTG':
                tg = parse_tg(fields)
                if tg:
                    tg_ncos.append(tg['nco'])
            elif tag == '$PSTMTS':
                n_ts_raw += 1
                rec = parse_ts(fields)
                if rec:
                    ts_lines.append((t_us, rec))
    valid = [g for _, g in gga if g['qual'] >= 1]
    fallback = None
    if valid:
        mid = valid[len(valid) // 2]
        fallback = geodetic_to_ecef(mid['lat'], mid['lon'],
                                      mid['alt'])
    epochs = []
    for t_us, rec in ts_lines:
        if epochs and t_us - epochs[-1]['t_last'] <= 500000:
            epochs[-1]['lines'].append(rec)
            epochs[-1]['t_last'] = t_us
        else:
            epochs.append({'t_us': t_us, 't_last': t_us,
                           'lines': [rec], 'rx': None})
    for ep in epochs:
        rx = None
        best_dt = None
        for t_g, g in gga:
            if g['qual'] < 1:
                continue
            dt = abs(t_g - ep['t_us'])
            if dt <= 2000000 and (best_dt is None or dt < best_dt):
                best_dt = dt
                rx = geodetic_to_ecef(g['lat'], g['lon'], g['alt'])
        ep['rx'] = rx if rx is not None else fallback
        for rec in ep['lines']:
            if ep['rx'] is not None:
                dx = rec['sx'] - ep['rx'][0]
                dy = rec['sy'] - ep['rx'][1]
                dz = rec['sz'] - ep['rx'][2]
                rec['geo'] = math.sqrt(dx * dx + dy * dy + dz * dz)
                rec['resid'] = rec['geo'] - rec['psr']
    return epochs, tg_ncos, len(ts_lines), n_ts_raw


def ts_usable(rec):
    return (rec['dsp'] == 1 and rec['satdat'] == 1
            and 24e6 <= rec['radius'] <= 29.5e6
            and 'resid' in rec)


def circ_devs(residues, modulus):
    """Per-line circular deviation (m) from the epoch's circular
    mean direction, on the given modulus grid."""
    angs = [2.0 * math.pi * (r % modulus) / modulus
            for r in residues]
    ms = sum(math.sin(a) for a in angs) / len(angs)
    mc = sum(math.cos(a) for a in angs) / len(angs)
    mean_ang = math.atan2(ms, mc)
    devs = []
    for a in angs:
        d = (a - mean_ang + math.pi) % (2.0 * math.pi) - math.pi
        devs.append(abs(d) * modulus / (2.0 * math.pi))
    return devs


def largest_cluster(residues, modulus):
    """Largest number of residues inside one arc of width
    2*CLUSTER_HALF_M on the modulus circle."""
    pts = sorted(r % modulus for r in residues)
    n = len(pts)
    if n == 0:
        return 0
    ext = pts + [p + modulus for p in pts]
    width = 2.0 * CLUSTER_HALF_M
    best = 0
    j = 0
    for i in range(n):
        while j < i + n and ext[j] - ext[i] <= width:
            j += 1
        best = max(best, j - i)
    return best


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float('nan')
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] +
                                            xs[n // 2])


def grid_report(label, epoch_lines, modulus):
    """epoch_lines: list of residue lists (epochs with >=4)."""
    max_devs = []
    best_cluster = (0, 0)  # (count, epoch size)
    for res in epoch_lines:
        max_devs.append(max(circ_devs(res, modulus)))
        k = largest_cluster(res, modulus)
        if k > best_cluster[0]:
            best_cluster = (k, len(res))
    if not max_devs:
        print('  %s: no epochs with >=4 usable lines' % label)
        return best_cluster
    print('  %s: epochs=%d  per-epoch max deviation  min=%.0f m  '
          'median=%.0f m  max=%.0f m'
          % (label, len(max_devs), min(max_devs),
             median(max_devs), max(max_devs)))
    print('  %s: largest +/-10 km cluster: %d of %d lines'
          % (label, best_cluster[0], best_cluster[1]))
    return best_cluster


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    epochs, tg_ncos, n_total, n_raw = load_capture(argv[1])
    usable = [[r for r in ep['lines'] if ts_usable(r)]
              for ep in epochs]
    n_usable = sum(len(u) for u in usable)
    print('capture: %s' % argv[1])
    print('epochs: %d | $PSTMTS lines: %d raw, %d parsed '
          '(short/spliced rows dropped) | usable after filters '
          '(dsp=1, Satdat=1, |SatPos| in [24e6,29.5e6]): %d'
          % (len(epochs), n_raw, n_total, n_usable))
    if tg_ncos:
        print('TG NCO median: %.1f Hz (both bench modules sit '
              'at ~-48 kHz indefinitely - a steady-state property '
              'of this module family, NOT a settling transient; '
              'it is common-mode and cancels in the circular '
              'statistics below)' % median(tg_ncos))
    all_res = [r['resid'] for u in usable for r in u]
    if not all_res:
        print('VERDICT: no usable lines - cannot test.')
        return 1
    spread = max(all_res) - min(all_res)
    mean = sum(all_res) / len(all_res)
    var = sum((x - mean) ** 2 for x in all_res) / len(all_res)
    print('Test A (raw residues geo-PsR): spread=%.0f m  '
          'std=%.0f m -> %s'
          % (spread, math.sqrt(var),
             'no constant offset' if spread > 1e6 else
             'possible constant offset - investigate'))
    big = [[r['resid'] for r in u] for u in usable if len(u) >= 4]
    print('Test B (mod c*200 ms, all SVs):')
    cl200 = grid_report('  200 ms grid', big, M200)
    print('Test C (mod c*200 ms, split):')
    for name, pred in (('GPS', lambda s: s <= 32),
                       ('GLONASS', lambda s: s >= 65)):
        sub = [[r['resid'] for r in u if pred(r['satid'])]
               for u in usable]
        sub = [x for x in sub if len(x) >= 4]
        grid_report('  200 ms ' + name, sub, M200)
    print('Test D (mod c*20 ms, all SVs):')
    cl20 = grid_report('  20 ms grid', big, M20)
    print('Test E (largest-cluster, +/-%d km): best 200 ms = %d/'
          '%d lines, best 20 ms = %d/%d lines'
          % (CLUSTER_HALF_M // 1000, cl200[0], cl200[1],
             cl20[0], cl20[1]))
    clustered = ((cl200[1] > 0 and cl200[0] >= cl200[1] - 1) or
                 (cl20[1] > 0 and cl20[0] >= cl20[1] - 1))
    if clustered:
        print('VERDICT: residues CLUSTER on a shared grid - PsR '
              'is harness-ready with per-line k resolved against '
              'the GGA fix.')
    else:
        print('VERDICT: no shared grid - cross-SV ambiguity rule '
              'NOT established. Per the notes: plan experiment 4 '
              'on per-channel ambiguity states or time-'
              'differenced PsR; do not design around single-'
              'epoch absolute PsR.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
