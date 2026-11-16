# psr-outage dataset - Experiment 4 phase B blockage captures

## Run 1 (2026-11-08) - attenuation control: no outage occurred

- Rig #2 (Nucleo-H745ZI-Q + AEK/Teseo-LIV3F), owner's
  property, LaSalle ON. Sky: patches of white cloud,
  mostly blue and sunny, and windy (owner's notes).
- File as delivered: `Experiment_4_Phaze_2.txt`,
  13,422,568 bytes, sha256
  d2a2ef027c636ebf8c3bfaa0f5411f0de0342b12c576436c614a358c91e2e0a1
  (drive and repo copies hash-identical). Recorder
  prepended per-line local-time stamps; derived
  `Experiment_4_Phaze_2.hostclean.txt` via
  ../psr-skyview/strip_host_prefix.py (untracked,
  regenerable).
- Window (recorder clock): 11:38:31 -> 11:58:34 EST.
  Owner's time sheet: logger start 11:38; covers /
  uncovers 11:43/11:45, 11:50/11:51, 11:56/11:58.
- FINDING: the metal tin attenuated but did NOT block.
  CN0 medians (30 s bins) fell from the 42-45 dB-Hz
  baseline to ~35-37 (cycle 1), ~37-39 (cycle 2) and
  ~29-31 (cycle 3) - 5 to 14 dB - but the module held
  14-15 SVs and a GGA fix continuously; $PSTMTS never
  stopped (no gap > 3 s in TS lines or fixes). The
  tracking loops never unlocked, the clock was never
  undisciplined, so NO rate step is measurable and the
  phase B question is not addressed by this run. It is
  retained as the shielding-effectiveness record.
  Probable cause: the tin's cable slot / lid seam
  leaked at L1; a slot leak limits a metal enclosure
  to ~10 dB class shielding regardless of wall material.
- Re-run requirement (design addendum 7): a REAL
  outage - GGA fix lost and TS silent within seconds
  of covering - via a foil-sealed tin or by
  disconnecting the antenna for the covered interval.

## Run 2 (2026-11-08) - VALID: Phase B complete

- Same rig/site. Captured on the owner's laptop with
  hardware/tools/serial_monitor.py. Method: ANTENNA
  DISCONNECT (the tin attenuated only - run 1; a 3-4
  layer foil wrap also failed, consistent with the
  coax braid carrying the signal past the wrap).
  File: `Experiment_4_Phaze_2_run2.txt`, 13,737,706
  bytes, sha256 58238bf1dc6d1beeb82cf20ce36c5e57eaf38
  c3495123fa0a451fdc87bf07c15. Window (recorder
  clock): 13:51:12 -> 14:12:01 EST. NOTE: the drive
  copy of run 1's file was overwritten by this file
  (same name) during the owner's copy; the committed
  repo copy of run 1 (sha d2a2ef02...) is intact and
  authoritative.
- Outages in the data (loaded seconds; #MARK times
  agree within handling seconds): cycle 1: 304.9 ->
  415.2 (110.3 s); cycle 2: 758.1 -> 832.6 (74.5 s).
  Cycle 3 was disconnected at ~1148 s but the capture
  stopped 2 s after reconnect - no post-window, not
  scored. Cycles 1-2 each carry ~5 min pre and post.
- RATE STEP (leg-1 estimator, local windows; sky-
  capture fake-gap controls: -0.28 / +0.23 m/epoch):
  cycle 1: pre +0.20 -> post +0.52, STEP +0.32
  m/epoch. Cycle 2: pre +0.51 -> post -4.92, STEP
  -5.43 m/epoch (post window n=30, IQR 8.5 - the
  noisiest window; the filters' own rate estimates
  for cycle 2 read -0.43 / -0.31 post, i.e. ~0).
- tc_delta gates: NO variant separation. Cycle 1
  post-gap accepts ~90-91% for v0/v1/v2 alike,
  recovery 2.4 s for all; cycle 2 the same (recovery
  10.4 s). The self-test's v0 signature (96% post-gap
  rejection, no recovery) is entirely absent.
  Rate tracking: v2's rate IQR is tighter than v1's
  in every window (post: 2.09 vs 3.38 cycle 1;
  1.90 vs 5.25 cycle 2) - Addendum 6 grading.
- VERDICT: across a real ~90 s total outage the
  delta-range clock rate returns within ~0-5 m/epoch
  of its pre-outage value. There is no accumulated
  clock error for a gate to choke on: the paper's
  lockout is an absolute-measurement phenomenon and
  does NOT transfer to delta-range coupling on real
  hardware - the structural-mitigation finding
  (design addendum 8). Data-quality caveat: this
  capture's usable SVs/epoch (median 5) are sparser
  than the sky capture's (7); 113 admitted leg-1
  pairs vs 2461 - the step bound is set accordingly.
