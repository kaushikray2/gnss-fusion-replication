# Supplementary analysis archive

Scripts and outputs behind the numbers added to the journal paper during revision: mechanism reproductions, gating ablations, detector-oracle runs, sensitivity sweeps, the Section V-A re-runs, and the confidence-interval computations. Every number in the paper traces to a file in this repository.

Supporting instrumented simulators (included in this folder): `sim_instr.py` (the stock simulator plus per-epoch
satellite-admission bookkeeping) and `sim_h.py` (the stock simulator
plus a HERR_DEG heading-error global). The scripts below import them,
or the stock `sim.py` / `replay.py`, with this folder and the package's `code/python/` directory on `sys.path`.

| File | What it produced |
|---|---|
| `repro_m1m2.py`, `repro_m3.py` | Mechanism reproductions: per-seed forest outcomes and mechanism (partial gating + clock-to-position aliasing); detector/oracle check at 30 seeds. Output: `repro_output.log`. |
| `p1_m1.py` | M1 ablations, forest, 100 seeds: joint chi-square gate (mean 38.07, recovered 8/100), randomized satellite order (164.95, 44/100), clock re-seed after 3 all-reject epochs (130.46, final <5 m 40/100). |
| `p1_m3.py` | M3 oracle ablation at 100 seeds, assumed and measured parameters (paper Sections IV-C and V-A); detector recall/false-fire/precision. |
| `p1_m4.py` | M4 turn-on-bias sensitivity: measured noise densities with BA_SD 0.17 m/s^2, BG_SD 0.026 rad/s, 100 seeds x 4 scenarios. Outputs: `m4_results.json`, `m4_summary.csv`. Headline: the forest TC failure survives (195.91 m); TC-CD vs LC in the forest separates (15.53 vs 9.09). |
| `p1_m6.py` + `forest_windows.json` + `canyon_windows.json` | M6 walk sensitivities: heading rotation, init-draw spread, Q_D sweep (x1/x10/x100), unmarked-stop scan. Outputs: `p1_m6_forest.log`, `p1_m6_canyon.log` (the forest log's trailing traceback is a preliminary invocation with a wrong windows file; the scored run precedes it). Runs against the walk captures in `data/` with `sim.py`/`replay.py` (package `code/python/`) on the path. |
| `p1_m7.py` (+ `make_simh.py`) | M7 heading-error sweep 0-180 deg, 30 seeds per angle, EKF vs UKF challenge RMSE and convergence medians. |
| `p1_m8.py` | M8: RTS smoothing of the ZUPT forward pass (forest 3.102, canyon 2.986) vs RTS(LC) and ZUPT-EKF. |
| `p1_phaseA.py`, `p1_phaseA2.py` | Minor-7 cross-check: single-epoch least squares over all 5,982 sky-capture epochs - 5,394/5,448 solvable epochs diverge; the 54 convergences land a median 650 km from the known position. |
| `p1_clock.py` | Clock-rate reconciliation: the archived `tc_real.common_mode` estimator reproduces `common_mode_summary.json` exactly (median -9,024.00, IQR 5.55, n=2,461); the paper's earlier -9,023.86 / IQR 3.24 came from a superseded pre-fold draft estimator that was not archived. |
| `phase1_output.log` | The batch log of the Phase 1 runs (M1, M3, M6 excluded - M6 ran in the walk-analysis workspace; its logs are above). |
| `step_bootstrap.py` | Bootstrap 95% CIs for the Section V-C clock-rate steps. Self-verifying - it asserts its windows reproduce `data/psr-outage/rate_step_run2.json` exactly before resampling. Cycle 1: +0.32 [-1.97, +2.70]; cycle 2: -5.42 [-7.79, -0.99] m/epoch. |
| `ci_paired.py` | Re-runs the 100-seed simulation saving per-seed challenge RMSE (`ci_perseed.json`), verifies the means reproduce `data/simulation-100seed/results.json`, and computes paired-difference 95% CIs (`ci_pairs.json`) for the headline comparisons quoted in Section IV. |
| `phaseA_ls_output.txt` | stdout of `p1_phaseA2.py` (archived output): single-epoch LS cross-check, 5,394/5,448 diverge, 54 converge at median 650 km |
| `step_bootstrap_output.txt`, `step_ci.json` | stdout + CI table of `step_bootstrap.py`: cycle steps +0.32 [-1.97, +2.70] and -5.42 [-7.79, -0.99] m/epoch |
| `fig_clockrate_stats.json` | statistics JSON printed by `code/python/make_fig_clockrate.py` (residual median +0.12, IQR 1.99; raw median -9,024.00, IQR 5.55; n = 2,461) |
| `va_driver.py`, `va_measured.json` | measured-parameter 100-seed re-run behind Table V (upper block), driven in-process with the `code/python/mc_measured.py` patch; cross-checks LC forest 6.420, ZUPT forest 4.760, LC open 0.835 reproduce the recorded values exactly |
