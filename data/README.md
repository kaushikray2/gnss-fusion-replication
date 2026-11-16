# Datasets

Every number in the paper traces to a dataset in this folder or to an analysis archived in this package (`analysis/phase1/` - the review-revision programme: ablations, oracle and sensitivity runs, the Table V re-runs, and the confidence-interval computations, with their scripts and outputs). Status:
present = the data behind the current manuscript; pending = a hardware
dataset the experiment programme will add (folder name reserved).

| Folder | Status | Backs |
|---|---|---|
| `simulation-100seed/` | present | Tables II-III and the Results figures of the current paper: `results.json`, `summary.csv`, `ukf_fixed_100.csv`, `ukf_sensitivity_100.csv`, `fig_err.png`, `fig_traj.png`, `fig_bar.png` (100-seed Monte Carlo, `../code/python/sim.py`) |
| `imu-static-6h/` | present | Experiment 2 - Allan calibration of the Method-section IMU parameters: raw log `IMU_Calib_LOG.txt` (312 MB; sha256 in `notes.md`; accompanies the release as a downloadable asset rather than a git file), `notes.md` manifest, `allan-6h.txt` / `allan-full.txt`, `mc-measured/` (100-seed re-run at the measured parameters) |
| `psr-skyview/` | present | Experiment 4 phase A: 100 min open-sky capture (rig #2), RMC window 2026-11-08 02:24:42-04:04:24 UTC; raw `GNSS_Data.txt` as delivered + `notes.md` + `psr_residue_output.txt` + `strip_host_prefix.py`. Verdict: NO shared grid - experiment 4 designs around time-differenced PsR / per-channel ambiguity states |
| `walk-forest/` | present | Experiment 1 (forest replay) + Experiment 3 (ZUPT scoring): manifest + scores in this folder; the raw capture (17 MB) accompanies the release and is identified by sha256 in `notes.md` |
| `walk-canyon/` | present | Experiment 1 (canyon replay) + Experiment 3 (ZUPT scoring): manifest + scores in this folder; the raw capture (21 MB) accompanies the release and is identified by sha256 in `notes.md` |
| `psr-outage/` | present | Experiment 4 phase B - real tight-coupling outage test |

## Capture discipline

Each hardware dataset folder holds the raw logger capture file(s),
unmodified, plus a `notes.md` manifest:

- rig (which Nucleo + shield + GNSS board) and firmware commit
- module configuration (baud, TG/TS mask state)
- placement and conditions (sky view, canopy, indoors, antenna state)
- start/end time, local and UTC
- operator events with timestamps: checkpoint stops (walks) or the
  blockage window (outage test)
- sha256 of each capture file

Analysis outputs live next to the dataset they came from, so a result
can always be re-derived from its raw capture with the commands in
the package README. Derived `.hostclean.txt` files (host timestamp prefixes and NUL padding stripped) are not tracked: generate them from any raw capture with `data/psr-skyview/strip_host_prefix.py`; several analyses read the hostclean form. The 312 MB static-IMU raw log and the two walk captures likewise accompany the release as downloadable assets (sha256 in each folder's `notes.md`), not as git files.
