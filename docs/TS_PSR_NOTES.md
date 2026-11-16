# $PSTMTS pseudorange - what the live data actually shows

Status: field map PINNED, ambiguity structure PARTIALLY pinned
(2026-11-07, from /tmp/logger-run8.log, rig #1's verified 42 s
Stage 1 capture; receiver at 42.246046, -83.067599, ~190 m).

## Field map (UM2229 Rev 5, Table 142 - verified against live values)

$dsp-dat, SatID, PsR, Freq, plf, CN0, ttim, Satdat, SatX, SatY,
SatZ, VelX, VelY, VelZ, Src, Ac, Difdat, Drc, Drrc, pred*
Live cross-checks: CN0 plausible (30-32 dB), |SatPos| ~26.5e6 m,
|Vel| ~2.8 km/s, Ac ~5.6 m. NOTE: some lines carry invalid
positions (|r| far from orbital radius, e.g. SatY=-23351) while
Satdat=1 - the harness MUST sanity-filter |SatPos| to
[24e6, 29.5e6] m. 155 of 412 TS lines passed all filters.

## Confirmed structure

1. **200 ms ambiguity quantum is real.** One SV's PsR series sits
   in families separated by exactly c*0.2 s = 59,958,492 m
   (observed 26.59e6 / 86.56e6 / 146.50e6 families, steps
   59.97e6 and 59.94e6). This matches the UM3397 note that the
   PsR reference is modulo 200 ms.
2. **A large common receiver-clock term rides on PsR and Freq.**
   PsR drifted ~+8.9 km/s while the true range rate was
   +0.155 km/s; Freq read ~-48.5 kHz on every channel, and
   $PSTMTG carried the same common offset (-47753.0000). Both
   imply a ~30 ppm reference error at capture time (module
   ~30 s from boot, clock discipline still settling). A TC
   filter's two-state clock (bias + drift) is the right absorber
   IF the term is common across SVs at an epoch - see open item.
3. Src (satellite range correction) reaches ~1.05e5 m on some
   SVs (SV clock term scale); Ac is metres-scale as documented.

## $PSTMTG field map (UM2229 Table 140 - decoded from live data)

Week, TOW, TotSat, CPUTime, Timevalid, NCO, kf_config_status
(hex), constellation_mask, then best/master/aux time-satellite
triples (type, week, TOW, validity). Live decode: NCO =
-47753.0000 is the receiver clock frequency offset in Hz (the
same ~-48 kHz seen per-channel in TS Freq); constellation_mask
3 = GPS + GLONASS; the aux TOW exceeds the master TOW by
exactly 10782.0000 s = 10800 - 18, i.e. the aux frame is
GLONASS time (UTC+3h vs GPS at UTC+18 s) - the map is
consistent end to end.

## Residue tests run on this capture - all cross-SV tests FAIL

- (geo - PsR): no constant offset (spread tens of millions of m).
- mod (c*200 ms), TG-grouped epochs: max deviations ~30-36e6 m.
- Split GPS (SatID <= 32) vs GLONASS (>= 65): still no agreement
  (note both system-time offsets, 18 s and 10782 s, are exact
  multiples of 200 ms, so constellation mixing alone cannot
  explain it on the 200 ms grid).
- mod (c*20 ms) with circular statistics: deviations shrink to
  ~280-710 km on several epochs but never cluster; a robust
  largest-cluster test (+/-10 km) finds no epoch with all or
  all-but-one lines in one cluster.
- Residual scatter quanta look like ~1 ms steps (c*1 ms =
  299,792 m): per-channel integer-ms ambiguity is implicated,
  but not on a grid shared cleanly across channels in this data.

## Working conclusion (2026-11-07)

This capture was taken ~30 s after module boot with the
receiver clock at ~30 ppm and still settling (NCO ~-48 kHz) -
the worst possible dataset for pinning a measurement
convention. The single-SV structure (200 ms families, smooth
drift segments) is real; the cross-SV rule is NOT determinable
from this capture. Before designing the TC replay, take a
WARM capture: module running >= 30 min with sky view, NCO
settled, then repeat the residue tests. If the residues then
cluster on the 20 ms (or 200 ms) grid, PsR is harness-ready
with per-line k resolved against the GGA fix; if they still
scatter at ~1 ms, plan on per-channel ambiguity states or
time-differenced PsR in the experiment 4 design. Do NOT design
around single-epoch absolute PsR until one of those lands.

## Retest tooling (added 2026-11-07)

The residue battery above is now codified as
`hardware/psr_residue.py` (pure stdlib): it parses a logger
capture, groups $PSTMTS into epochs, applies the pinned filters,
and runs tests A-E with the +/-10 km largest-cluster verdict
rule. On this cold capture it reproduces the recorded verdict
(no shared grid; best cluster 2/5 lines on both grids; TG NCO
median -47740 Hz). One command re-runs the whole battery on the
warm capture when it exists:
`python3 hardware/psr_residue.py <capture.log>`

## Bench dry-run (2026-11-07, rig #2, INDOOR, ~35 min powered)

The capture->retest chain was exercised end-to-end on 300 s of
rig #2 bench data (/tmp/rig2-benchwarm.log, 2,675 TS lines):
verdict unchanged - no shared grid (best cluster 2/5 on the
20 ms grid). Two findings that DO carry forward:

1. **The NCO does not settle.** TG NCO median -47,834 Hz after
   ~35 min powered, vs -47,753 Hz on rig #1's cold capture and
   ~-48.5 kHz per-channel Freq in both. Two modules, same
   ~-48 kHz: this is a steady-state property of the module
   family (or of the NCO field's reference), not a warm-up
   transient. The warm capture's purpose is therefore clean
   GEOMETRY (sky view, low multipath), not clock settling -
   and since the term is common-mode it cancels in the
   residue tests' circular statistics anyway. The earlier
   framing of this capture as "the worst dataset because the
   clock was settling" should be read with that correction.
2. **Indoor residues moved toward the grid but did not land:**
   20 ms per-epoch max deviation median 97 km (cold: 178 km),
   best epoch 42 km - still far outside the +/-10 km cluster
   window. Roof multipath is the expected smearer; only the
   sky-view capture arbitrates.

## Run 3 - sky view (2026-11-07): the arbitrating capture

Dataset `replication/data/psr-skyview/` (manifest there):
rig #2 outdoors, open sky, GGA quality 1 / 13 sats / HDOP 0.8,
RMC window 2026-11-08 02:24:42-04:04:24 UTC (100 min, 5,983
epochs). Bookkeeping: 108,397 raw TS rows, 68,102 parsed,
**44,314 usable** - two orders of magnitude beyond runs 1-2.
TG NCO median -47,421 Hz (steady state, as established).

**VERDICT: no shared grid.** Test E best epochs cluster 4/7
lines (200 ms) and 5/9 lines (20 ms) in a +/-10 km arc; the
rule needs all or all-but-one. Median per-epoch max deviation
18.0e6 m (200 ms grid) / 204 km (20 ms grid). Test A spread
156.5e6 m (multiple 200 ms cells). The ~100 km-scale cross-SV
scatter of runs 1-2 is NOT a cold-start or indoor artefact -
it is the module's steady behaviour under a clean sky.
GLONASS-only epochs scatter less than GPS-only (median max
deviation 109 km vs 215 km) but cluster no better.

Experiment 4 phase B therefore takes the pre-registered
fallback: time-differenced PsR and/or per-channel ambiguity
states. Single-epoch absolute $PSTMTS PsR is not a sound
foundation on this module.

Tool note: this capture exposed a loader crash in
psr_residue.py - a 'G,' row whose sentence was spliced away
by the capture app hit an unguarded index('$'). Fixed by
skipping '$'-less G-rows (the corrupt-row class the tool
already drops); results on runs 1-2 are unaffected.

## Constellation configuration (checked 2026-11-08)

Every capture in this programme is GPS + GLONASS only:
the $PSTMTG constellation mask reads 3 in all of them,
and the sky capture's $PSTMTS population is 14 GPS +
11 GLONASS distinct SVs (GSV talkers GP/GL only). The
Teseo-LIV3F is multi-constellation silicon (UM2229
p.11: GPS/Galileo/GLONASS/BeiDou/QZSS); the limit is
configuration, not hardware. Switch (UM2229 10.2.33):
$PSTMSETCONSTMASK,<mask> - bit0 GPS (1), bit1 GLONASS
(2), bit2 QZSS (4), bit3 Galileo (8), bit7 BeiDou
(128); all five = 143. $PSTMCFGCONST (10.3.24) sets
per-constellation 0=off / 1=tracked / 2=used in fix.
OWNER RULING 2026-11-08: keep GPS+GLONASS for this
programme - the remaining measurements are differ-
ential and not satellite-starved, and the banked
datasets share this configuration. Revisit only as a
future programme's starting configuration.
