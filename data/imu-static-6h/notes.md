# Dataset manifest - imu-static-6h (Experiment 2: Allan calibration)

- File: `IMU_Calib_LOG.txt` - 312,358,625 bytes, sha256
  `773eda99e0425f829a7cac2ff3516a2ea70b23ad8bbb67243e542f1281047c44`
  (byte-identical copy of the owner's USB-drive original, verified
  by hash on ingest, 2026-11-07)
- Rig: rig #1 - Nucleo-H563ZI + X-NUCLEO-IKS01A3 (LSM6DSO @ 0x6B)
  + AEK-COM-GNSST31; firmware `hardware/firmware/logger` (verified
  build, commit 70c4e91 state); console 1000000 baud, captured on a
  laptop in the basement.
- Placement: basement floor, static, undisturbed. GNSS antenna
  unplugged (the module still streamed sentences; the IMU rows are
  the dataset - Allan analysis reads IMU rows only).
- Capture: started ~10:05 EST 2026-11-07, stopped ~21:12 EST.
  Owner's independent timer: 667 min 32 s = 40,052 s. Logger
  timestamp span: 40,041.41 s (the ~11 s difference is timer-start
  vs first-row offset).
- Integrity (verified on ingest): 4,106,166 IMU rows; mean rate
  102.548 Hz; dt median 9,678 us (batch-drain jitter, max dt
  29.1 ms); ZERO non-monotone timestamps; ZERO gaps > 50 ms;
  4,004 #STAT lines (exactly one per 10 s); 0 unparseable lines.
  1,285,321 NUL padding bytes from the capture application - no
  data loss, proven by the gap-free timestamp record.
- Static means: accel (0.017, -0.003, 1.0125) g (rig tilt ~1 deg);
  gyro bias (-0.57, +0.05, -1.51) dps, wandering ~0.03 dps over
  the 11.1 h (per-hour means in the ingest scan).
- Analysis: `hardware/allan.py` (--rate 102.55, --sim-rate 10) on
  (a) the 6 h protocol window, t <= 21,600 s from the first IMU
  row, and (b) the full 40,041 s record. Outputs: `allan-6h.txt`,
  `allan-full.txt` in this folder.
- **GNSS content of this capture is NOT data (owner, 2026-11-07):**
  the antenna was unplugged and the module sat in a basement; its
  GLL/GSA/GSV/TG lines are void / last-known artefacts (the GLL in
  the tail reads status V). No GNSS value from this file is to be
  used as position, ground truth, or calibration input for any
  purpose. This dataset calibrates the IMU only.
- Stage 2 outcome (2026-11-07): measured parameters (full record,
  axis-matched) SIG_A 0.00181 m/s^2, SIG_G 0.000147 rad/s,
  BA_SD 0.000515 m/s^2, BG_SD 0.0000351 rad/s - 34-228x below the
  paper's assumed set. Monte Carlo re-run in `mc-measured/`;
  calibration note at `hardware/CALIBRATION_NOTE.md`: headline
  rankings survive in canyon/forest; the TC clock lockout is
  parameter-robust; ZUPT-EKF open-sky regression flagged,
  mechanism unresolved.
