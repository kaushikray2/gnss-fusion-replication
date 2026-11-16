# Stage 2 calibration note - measured IMU parameters (2026-11-07)

> Editorial note (public release, 2026-11-16): this is the contemporaneous calibration record. The final manuscript names the forest failure mechanism partial gating plus clock-to-position aliasing rather than a total "lockout"; the parameter-robustness verdict below stands unchanged (paper Sections IV-C and V-A).

Experiment 2 of the programme: replace the paper's assumed IMU
parameters with values measured from the actual part (LSM6DSO on
rig #1's X-NUCLEO-IKS01A3), and re-run the Monte Carlo to test
whether the paper's rankings survive.

## Dataset

`replication/data/imu-static-6h/` - 11.1 h static log, basement,
antenna unplugged; manifest (`notes.md`) carries the provenance.
**This dataset calibrates the IMU only** (owner, 2026-11-07): the
capture's GNSS lines are void artefacts and were used for nothing;
the Monte Carlo's GNSS model is the paper's, untouched. Integrity:
4,106,166 IMU rows, 40,041.41 s span, zero gaps, zero non-monotone
timestamps, zero unparseable lines.

## Method

`hardware/allan.py` (overlapping Allan deviation) on the 6 h
protocol window and on the full record; the two agree within ~7%
on every parameter. Primary values below are the FULL record's,
axis-matched to the simulator's 2-D IMU (accel x/y, gyro z). An
independent first-difference probe of the raw rows reproduces the
Allan densities within ~10%.

Mapping (allan.py's contract): per-sample sigma at the sim's
10 Hz = density x sqrt(10); the sim's per-run bias-draw SDs are
estimated by the Allan bias instability (the floor / 0.664) - a
static-log estimate of that magnitude, labelled as such.

## Measured parameters (vs the paper's assumed set)

| Param | Assumed (paper) | Measured (full) | Measured (6 h) | Factor |
|---|---|---|---|---|
| SIG_A | 0.10 m/s^2 | 0.00181 | 0.00177 | 55x lower |
| SIG_G | 0.005 rad/s | 0.000147 | 0.000151 | 34x lower |
| BA_SD | 0.08 m/s^2 | 0.000515 | 0.000517 | 155x lower |
| BG_SD | 0.008 rad/s | 0.0000351 | 0.0000343 | 228x lower |

Densities behind them (full record): accel (x,y) 5.71e-4
m/s^2/sqrt(Hz); gyro z 4.65e-5 rad/s/sqrt(Hz). The paper's set is a
generic literature-class phone IMU; the measured set is this part,
on this board, in situ. Both are reported from here on: ASSUMED
(the paper's sweep) and MEASURED (this note's sweep).

## Monte Carlo re-run

`hardware/mc_measured.py` patches only the four constants above
and rebuilds Q_D with sim.py's own formula (the 1e-4 / 5e-3 bias
random-walk terms are the filters' process model - untouched).
Estimators, scenarios, truth generation and the 100 seeds are the
paper's exactly; the ZUPT detector thresholds are the paper's
absolute constants, NOT retuned. Outputs:
`replication/data/imu-static-6h/mc-measured/`; comparison by
`hardware/compare_mc.py` against `data/simulation-100seed/`.

## Results - challenge-window RMSE, ASSUMED -> MEASURED (m)

| Scenario | RTS | ZUPT | LC-EKF | TC-CD | TC-EKF | GNSS | INS |
|---|---|---|---|---|---|---|---|
| open | 0.41->0.35 | 0.86->1.04 | 0.89->0.84 | 0.89->0.83 | 0.89->0.83 | 1.67 | 339->14.2 |
| canyon | 3.52->3.36 | 8.42->8.30 | 9.53->9.41 | 9.69->9.45 | 11.2->10.8 | 32.0 | 253->16.9 |
| forest | 2.76->1.93 | 4.53->4.76 | 11.3->6.42 | 11.3->6.42 | 176->193 | 17.0 | 399->16.4 |
| stress | 0.43->0.37 | 1.00->1.06 | 1.03->0.98 | 1.02->0.98 | 1.03->0.98 | 1.67 | 55.8->15.9 |

(LC-UKF and ADAPT-EKF track LC-EKF within a few percent in both
sweeps everywhere; full tables in the two results.json files.)

## Verdicts

1. **The paper's headline rankings survive calibration in the
   scenarios they are about.** In canyon and forest: RTS-SMOOTH
   best overall, ZUPT-EKF best causal, the LC ~ TC-CD tie, and
   UKF-EKF parity all hold under the measured parameters.
2. **The clock lockout is parameter-robust.** Bias-only TC-EKF
   still diverges catastrophically in the forest (193 m challenge-
   window) at the measured noise levels - the mechanism the paper
   names is not an artefact of pessimistic IMU parameters.
3. **Absolute errors shrink almost everywhere** (forest LC cluster
   11.3 -> 6.4 m; RTS forest 2.76 -> 1.93 m), as expected with a
   34-55x quieter IMU. INS improves ~20x (339 -> 14 m open) but
   remains the worst fused-adjacent method; the paper's verdict on
   unaided consumer-MEMS dead reckoning stands qualitatively.
4. **Two rank changes, both reported, neither hidden.** (a) INS is
   no longer last in canyon or forest - in the canyon it beats
   GNSS-only (16.9 vs 32.0 m) but not the bias-only TC (10.8 m);
   in the forest it beats both (16.4 m vs 17.0 m and 193 m).
   (b) ZUPT-EKF's forest margin
   over LC-EKF narrows from 2.5x to 1.35x.
5. **FLAGGED, mechanism unresolved: ZUPT-EKF regresses in open
   sky and stress** (0.86 -> 1.04 m and 1.00 -> 1.06 m; rank 2 -> 7
   in both), ending up WORSE than its own base LC-EKF where fixes
   are plentiful - while still winning in the degraded scenarios.
   The detector (sim.py run_lc) uses absolute thresholds (accel
   window std < 0.20 m/s^2; gyro std < 0.01, |mean| < 0.03 rad/s)
   set in the high-noise world and was deliberately not retuned.
   Whether the regression is false firing, the fixed ZUPT
   R = (0.02 m/s)^2 interacting with the much smaller covariances,
   or the SIG_G^2-scaled ZARU is NOT established by this run. The
   decisive diagnostic is fire-count instrumentation (fires
   inside vs outside true stops, both parameter sets) - follow-up
   work, and directly relevant to Experiment 3's detector scoring
   on real data.

## Consequence for the paper

The experimental data section reports both sweeps. The Method
section's parameter table gains the measured column, and the
assumed set is described for what it is: a literature-class IMU,
not the bench part. Finding (2)'s ZUPT claim is scoped to the
degraded scenarios, as the abstract already frames it; the
open-sky regression and its unresolved mechanism are reported
with it.
