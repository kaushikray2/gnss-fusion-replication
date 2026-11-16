# Dataset: psr-skyview

Experiment 4 phase A - the $PSTMTS pseudorange residue test
under a real sky. Raw capture as delivered, unmodified.

## Capture

- Rig: rig #2 - Nucleo-H745ZI-Q + X-NUCLEO-IKS01A3 +
  AEK-COM-GNSST31 (Teseo-LIV3F), `logger_h745` firmware.
- Placement: static, outdoors, open sky (owner's property,
  LaSalle ON). GGA: fix quality 1, 13 satellites, HDOP 0.8.
- Recorder: a capture host that prepends each received line
  with its local time (EST). The logger's own 'G,t_us,'
  framing is intact underneath.
- **Log window (from the RMC sentences in the data, per the
  owner's instruction): 2026-11-08 02:24:42 UTC to
  04:04:24 UTC = 21:24:42 to 23:04:24 EST, 2026-11-07.**
  First RMC is already a valid (A) fix. Logger span 6,019.4 s;
  the RMC span (5,982 s) starts at the first fix.
- Files:
  - `GNSS_Data.txt` - as delivered on the USB drive,
    73,004,719 bytes, sha256
    c43350d94004058cdfcc81b0edbfa174ffb0c1b1555684992ab99d67fbb8ac50
  - `GNSS_Data.hostclean.txt` - derived: host prefixes and
    NUL padding stripped by `strip_host_prefix.py` (in this
    folder); the analysed file. sha256 recorded in the
    commit that adds this manifest. Kept in the working
    tree, not in git (regenerable from the raw file);
    sha256 724052aa076c91f55c203b6f9f930c5c61d4943a67ec424b8288461fe053e08b
  - `psr_residue_output.txt` - the test battery's output.
- Bookkeeping: 813,504 lines; 613,366 IMU rows; 5,983 GGA
  epochs (1 Hz); 108,397 $PSTMTS rows counted by the tool,
  68,102 parsed, 44,314 usable after the dsp/Satdat/radius
  filters. TG NCO median -47,421 Hz (steady state).

## Verdict (pre-registered rule, hardware/TS_PSR_NOTES.md)

**No shared grid.** Test E: best epoch clusters 4 of 7 lines
(200 ms grid) and 5 of 9 lines (20 ms grid) inside a +/-10 km
arc - the rule needs all or all-but-one. Median per-epoch
maximum deviation: 18.0e6 m on the 200 ms grid, 204 km on the
20 ms grid. The ~100 km-scale cross-SV scatter seen in the
cold and indoor captures is NOT a cold-start or indoor
artefact: it persists under a clean sky with 44k usable
lines. GLONASS-only epochs scatter less (median max
deviation 109 km) than GPS-only (215 km) but do not cluster
either.

Consequence for experiment 4 phase B: the TC harness is
designed around time-differenced PsR and/or per-channel
ambiguity states. Single-epoch absolute PsR from $PSTMTS is
not a sound foundation on this module.
