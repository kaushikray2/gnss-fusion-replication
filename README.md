# Replication package: "Tight Coupling Is Not Enough"

Replication package for the GNSS/INS fusion study reported in the journal manuscript "Tight Coupling Is Not Enough." This package is the public, self-contained release of the study's hardware, code, datasets and protocols. The
paper's current results are a 100-seed Monte Carlo comparison of nine
estimators in a synthetic walking world, and the paper itself states
the caveat this package exists to answer: *"Rankings, not absolute
metres, are the output we trust: the world is synthetic and
uncalibrated."* This package contains the rigs, firmware, analysis
code, protocols and (as they are collected) datasets that test the
paper's claims on real hardware and real signals. All four experiments are now complete, and their results are written into the manuscript as Section V (Experimental Validation, added 2026-11-15).

Developed by **SiliconBrane Inc** (author: Kaushik Ray).

Status: assembled 2026-11-07; finalized for public release 2026-11-16. License: see the `LICENSE` file in this repository. Dataset status is tracked in `data/README.md`.

## Quick start

Install the two dependencies (Python 3.12; everything else is the
standard library):

```
pip install -r requirements.txt
```

Regenerate the paper's figures from the committed data:

```
# Figures 1-3 (simulation) - byte-identical to data/simulation-100seed/
cd code/python
mkdir -p results && cp ../../data/simulation-100seed/results.json results/
python3 plot.py

# Figure 4 (clock-rate continuity, Section V-C)
cd ../..
python3 data/psr-skyview/strip_host_prefix.py data/psr-skyview/GNSS_Data.txt > data/psr-skyview/GNSS_Data.hostclean.txt
cd code/python
python3 make_fig_clockrate.py
```

Self-tests and the full re-run:

```
python3 tc_selftest.py
python3 tc_delta_selftest.py
python3 sim.py --seeds 100 --out results_full   # full 100-seed Monte Carlo (tens of minutes)
```

Section 8 below gives the same pipeline in context, and Section 1 maps
every figure and table to the script and dataset behind it.

## 1. Traceability: every claim maps to code and data

### 1a. What is already in the paper (simulation)

| Paper element | Produced by | Data |
|---|---|---|
| Method, simulation world (300 s walk; IMU noise 0.10 m/s^2 and 0.005 rad/s per sample at 10 Hz; bias draws N(0, 0.08 m/s^2), N(0, 0.008 rad/s); 9 satellites; scenarios Open / Canyon / Forest / Stress) | `code/python/sim.py` (constants at the top of the file) | - |
| Table II (full-run RMSE), Table III (challenge-window RMSE + compute/step), Results figures | `code/python/sim.py` + `code/python/plot.py`, 100 seeds, paired | `data/simulation-100seed/results.json`, `summary.csv`, `fig_*.png` |
| LC-UKF parity claim and the SO(2) circular-mean pitfall (abstract claim 2) | `code/python/ukf_sensitivity.py`; fixed implementation inside `sim.py` | `data/simulation-100seed/ukf_sensitivity_100.csv`, `ukf_fixed_100.csv` |
| Table IV (IMU parameters, assumed vs measured) | Experiment 2: `code/python/allan.py` on the static log; full record in `docs/CALIBRATION_NOTE.md` | `data/imu-static-6h/` |
| Table V (the two Section V-A re-runs: measured parameters; turn-on-scale bias draws) | `code/python/mc_measured.py` parameter patch, driven in-process by `analysis/phase1/va_driver.py`; turn-on run `analysis/phase1/p1_m4.py` | `analysis/phase1/va_measured.json`, `analysis/phase1/m4_results.json` |
| Table VI (field walks) and the Experiment 3 detector rates | `code/python/replay.py` + `code/python/score_walk.py` | `data/walk-forest/`, `data/walk-canyon/` (manifests + scores; bulk captures per `data/README.md`) |
| Fig. 4 (clock-rate continuity) and the Section V-C step statistics with bootstrap CIs | `code/python/make_fig_clockrate.py`; `analysis/phase1/step_bootstrap.py` | `data/psr-skyview/`, `data/psr-outage/`; outputs in `analysis/phase1/` |
| Paired-difference CIs (Sections IV-C/D/E and Threats) and the revision-programme ablations, oracle and sensitivity runs | `analysis/phase1/` (scripts + archived outputs, indexed by its README) | `analysis/phase1/ci_pairs.json`, `analysis/phase1/ci_perseed.json` |

### 1b. The four hardware experiments (what this package adds)

| # | Experiment | Paper claim under test | Dataset | Analysis |
|---|---|---|---|---|
| 2 | Allan calibration from a 6 h static log | Method: the IMU parameters above are assumed, not measured | `data/imu-static-6h/` | `code/python/allan.py`, then a Monte Carlo re-run at the measured parameters |
| 1 | Real-data replay: forest loop + downtown canyon walks | Results: the estimator rankings (Tables II-III) in degraded environments | `data/walk-forest/`, `data/walk-canyon/` | `code/python/replay.py` adaptation + `code/python/score_walk.py` scoring (drives the paper's own estimator code, unmodified) |
| 3 | ZUPT detector characterisation | Results: ZUPT-EKF is the best causal filter in the forest outages; the detector is IMU-only (Method, Estimators) | scored from the Experiment 1 walk datasets | the ZUPT path inside `sim.py`, scored by `code/python/score_walk.py` against the noted stop segments |
| 4 | Tight coupling on real pseudoranges through a real blockage | Results: on absolute pseudoranges the bias-only TC-EKF fails by partial gating and clock-to-position aliasing; on this receiver's delta ranges the clock rate stays continuous across a real blockage, so the failure does not transfer to differenced coupling | `data/psr-skyview/` (phase A), `data/psr-outage/` (phase B; per-cycle rate-window statistics in `rate_step_run2.json`) | `code/python/psr_residue.py` (phase A); `code/python/tc_real.py` + `tc_delta.py` with their self-tests (phase B; window statistics from the `tc_delta` run-2 analysis in `data/psr-outage/rate_step_run2.json`) |

Execution order: Experiment 2's capture first, Experiment 4 phase A
early (it fixes phase B's design), then the Experiment 1 + 3 walks,
then Experiment 4 phase B, then the write-up into the paper.

## 2. Hardware

Two identical rigs (either can run any experiment):

| Part | Role |
|---|---|
| ST Nucleo-H563ZI (rig 1) or Nucleo-H745ZI-Q (rig 2) | Logger MCU |
| ST X-NUCLEO-IKS01A3 shield | IMU: LSM6DSO (I2C 0x6B, WHO_AM_I 0x6C), used at 104 Hz FIFO |
| ST AEK-COM-GNSST31 | GNSS: Teseo-LIV3F module (Teseo III, L1-only) with SMA antenna |
| Laptop or Android phone with a serial terminal | Console capture (the logger streams; it has no local storage) |

The Teseo-LIV3F is the key enabler for Experiment 4: its $PSTMTS
sentence carries per-satellite pseudorange plus the satellite's ECEF
position, and $PSTMTG carries the receiver clock state - enabled via
configuration bits 8/9 of CDB-ID 201 (see the firmware section).
Both sentences are off by default. (ST's FAQ statement that the part
has "no raw data" refers to the absence of a binary raw mode; the
NMEA-formatted $PSTMTS output is documented in UM2229 Rev 5.)

## 3. Assembly

1. Stack the IKS01A3 on the Nucleo, then the AEK-COM-GNSST31 on top.
2. AEK UART jumpers: move the shunts from the factory J3/J4 positions
   to **J2/J5**, routing the module UART to Arduino D0/D1
   (USART1, PB7/PB6). The factory positions dead-end the UART.
3. AEK control jumpers: **J13** connects D7 to SYS_RESETn; the wake
   line reaches D4 via J7 on our boards (the schematic's alternative
   is J9/D13). Power shunts **J14/J15** fitted (module VCC and
   battery backup from +VCC_IO, 3.3 V).
4. IKS01A3: I2C jumpers JP7/JP8 stay in **Mode 1** (shunts 1-2, 3-4);
   LSM6DSO power shunt JP11 fitted; its address is 0x6B (SB15).
5. Connect the GNSS antenna for sky-view work; it may be left off for
   the static IMU baseline (Experiment 2 reads IMU rows only).

## 4. Firmware and module configuration

Toolchain: Arduino IDE or arduino-cli with the STM32duino core
**2.11.0** (board-manager URL:
`https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json`).
No third-party libraries are used. Flashing:

- **H563ZI**: board `Nucleo-144 / NUCLEO_H563ZI`;
  `arduino-cli upload -p <ST-LINK VCP> --fqbn STMicroelectronics:stm32:Nucleo_144:pnum=NUCLEO_H563ZI`
- **H745ZI-Q**: the core has no Nucleo-H745 target; use
  `Generic STM32H7 / GENERIC_H745XIHX`, compile, and copy the
  resulting `.bin` onto the ST-LINK mass-storage disk
  (`NOD_H745ZIQ`). arduino-cli upload does not work for this target
  (it requires STM32CubeProgrammer).

Configure a fresh Teseo module once, in this order (the loggers keep
working without it, but Experiment 4 needs the raw sentences):

1. Flash `code/firmware/gnss_baud/` (H563) or `gnss_baud_h745/`
   (H745) and run it: raises the module UART from its factory 9600
   to **921600** baud (CDB-ID 102 = 0xD, the module maximum) and
   persists it. Note: a newly saved baud takes effect from the
   *following* boot - the saving run's own probe still reports the
   old rate; run it once more to see "already at 921600".
2. Flash `code/firmware/gnss_config_h745/`, or simply boot the
   logger (step 3), which asserts the same setting: the CDB-ID 201
   message mask gets bits 8/9 OR-ed in (factory 0x00980056 ->
   0x00980356), enabling $PSTMTG/$PSTMTS, persisted with $PSTMSAVEPAR.
   **$PSTMSETPAR syntax is `<id>,0x<value>,<mode>` - hex value
   second, mode last.** The swapped form is silently accepted and
   overwrites the mask (the recovery command is in the gnss_config_h745 header).
3. Flash the logger: `code/firmware/logger/` (H563) or
   `code/firmware/logger_h745/` (H745).

## 5. Logger operation and capture discipline

- Console: ST-LINK virtual COM port at **exactly 1000000 baud**,
  captured raw to a file by the laptop/phone terminal. A wrong baud
  produces a garbage file and a wasted run.
- Output: one text stream - `#` headers/status, IMU rows
  `t_us,ax,ay,az,gx,gy,gz` (g, deg/s, ~104 rows/s), GNSS sentences
  prefixed `G,<t_us>,`. `#STAT` lines every 10 s report counters.
- Before walking away from any run, verify: the header reports
  `LSM6DSO found at 0x6B`, the GNSS boot check passed, and the
  `#STAT` imu counter climbs by ~1040 per interval.
- Parsers must tolerate spliced rows: at 921600 + 1000000 baud the
  console stream occasionally interleaves; every consumer in
  `code/python/` already filters malformed lines.

## 6. Critical gotchas

1. **D4 must be driven LOW, hard, from boot.** On the IKS01A3, D4 is
   the LSM6DSO's INT1 pin; the AEK's SYS_WAKEUP net shares that
   header pin and idles high. Per the LSM6DSO datasheet (interface
   selection at power-up), INT1 high puts the IMU in I3C-only mode
   with I2C disabled - the IMU vanishes from the bus and no register
   write brings it back. Internal pull-downs lose to the AEK net;
   only an actively driven LOW wins. The GNSS module streams fine
   with D4 low. Both loggers implement this; it is the single most
   important line in the firmware.
2. **Pulse D7 (SYS_RESETn) LOW 100 ms, then HIGH at every boot**, or
   the module may never start.
3. **The module sometimes boots silent** for reasons not observable
   from the MCU side (identical firmware both passed and failed on
   different boots during bring-up). The H745 logger therefore uses
   a *checked bring-up*: pulse reset, drain 4 s, count framed
   bytes; re-pulse up to 3 attempts and log the outcome in the
   capture header. Do not remove the retry logic - it is the fix,
   not a workaround.
4. **Probe by sentence structure, not byte count.** A held-low reset
   yields a long stream of 0x00 bytes, and a live module at the
   wrong baud decodes as printable garbage; both false-positive a
   naive probe. The firmware counts `$`-framed sentences.
5. **The H745 generic target's `Serial` is not on the ST-LINK VCP**
   (it is silent). The H745 sketches use an explicit
   `HardwareSerial(PD_9, PD_8)` console, and Arduino pin numbers are
   meaningless on that variant - pins are named (`PB_7`, `PE_14`,
   `PG_12`, ...).
6. **This STM32duino core's printf has no `%llu` and no `%f`** (float
   fields print empty). The loggers format timestamps and values
   manually, in exact integer fixed point.
7. **Long FIFO drains starve the 921600-baud UART.** The loggers run
   I2C at 400 kHz, cap FIFO batches, and drain the GNSS port inside
   the FIFO read loop.

## 7. Experiment protocols

### Experiment 2 - IMU noise baseline and calibration

1. Rig fully stacked, placed flat on a solid, thermally quiet
   surface (a basement floor is ideal). Antenna optional.
2. Power on; let it settle 10 min before starting the capture.
3. Capture the console (1000000 baud, raw to file) for **6 h**.
   Laptop on mains, sleep disabled, ~1 GB free (expect 150-200 MB).
4. Verify the four start-of-run checks (section 5) before leaving.
5. Analysis: integrity first (row count vs duration, median dt
   9615 us, monotone timestamps, gap scan - a run with dropouts is
   invalid), then `python3 code/python/allan.py <log>` gives
   per-axis Allan deviation: white-noise density and bias
   instability, converted into the paper's Method quantities
   (per-sample noise at 10 Hz; bias-draw standard deviations).
6. Re-run the Monte Carlo at the measured parameters and compare
   rankings with the assumed-parameter tables.
   Exit evidence: `docs/CALIBRATION_NOTE.md` states the measured vs assumed values and whether any ranking moved.

### Experiment 4 phase A - pseudorange convention capture

1. Rig outdoors with a clear sky view, logger running, 30+ min.
2. `python3 code/python/psr_residue.py <capture>`: tests whether
   the $PSTMTS pseudoranges, reduced modulo c*200 ms and c*20 ms,
   cluster on a shared grid (verdict rule: an epoch clustering
   all / all-but-one satellites within +/-10 km).
3. The verdict fixes phase B's harness design: clustered ->
   per-line ambiguity resolution against the GGA fix; scattered ->
   per-channel ambiguity states or time-differenced pseudoranges.
   Known properties the test already established (cold and indoor
   captures): a 200 ms ambiguity quantum, a ~30 ppm common
   receiver-clock term, and a steady-state ~-48 kHz clock frequency
   offset (it does not settle with warm-up; sky view is for clean
   geometry).

### Experiments 1 + 3 - the walks (forest and canyon)

1. Course: a loop, start and finish at the same marked point;
   forest = under canopy, canyon = downtown tall-building route.
2. Carry the rig **flat, shield +X axis pointing forward** (the
   replay adapter's default axis map), console captured by phone
   or laptop.
3. Walk at normal pace; at 4-6 marked checkpoints **stop dead
   still for 10 s** and note each stop's time; end with a final
   10 s stand at the start point.
4. Analysis: `python3 code/python/replay.py <log>` runs the
   paper's loose-coupling family (GNSS, INS, LC-EKF, LC-UKF,
   ZUPT-EKF, ADAPT-EKF, RTS-SMOOTH) on the real data. Forest:
   mask the under-canopy stretches with `--mask-out T0:T1` to
   mirror the paper's outage windows. Canyon: no masking - real
   correlated multipath is the point. Truth: loop closure plus
   the checkpoint stops.
   As executed (2026-11-14/15): neither walk produced an
   outage, so no `--mask-out` was applied on either leg;
   scoring ran through `code/python/score_walk.py`.
5. Experiment 3 is scored from the same logs: the paper's IMU-only
   ZUPT detector against the noted stop segments gives false-fire
   and missed-stop rates. (A GNSS-speed-assisted variant may be
   reported alongside, clearly marked as not the paper's detector.)
   Exit evidence: the per-walk score files (`data/walk-forest/walk_seg2_scores.json`, `data/walk-canyon/walk_seg2_scores.json`) with the manifests in the same folders.

### Experiment 4 phase B - tight coupling through a real blockage

1. Rig logging $PSTMTS with sky view; then a real blockage for a
   noted 60-120 s window (structure, garage, or antenna shielding);
   then open sky again.
2. First the zero-filter measurement: leg 1's difference
   machinery on the windows before and after the blockage
   gives the residual clock rate on both sides; the
   difference is the rate step the experiment turns on.
3. Then the differenced TC harness (tc_delta.py; shape fixed
   by phase A and the ratified addendum 3 reformulation -
   absolute PsR is not a stable observable on this module)
   with three clock variants on time-differenced PsR:
   v0 no clock state, v1 rate as random walk, v2 rate +
   derivative, 4-sigma sequential gating.
   Score: per-epoch gate-rejection counts (v0 against the
   clock-state variants) and the recovered rate series
   (v1 against v2). Position is reported, not scored -
   delta ranging does not position.
   Exit evidence: the rate step measured, and the
   model-order question decided on real data in whichever
   direction the step supports (a near-zero step is a
   structural-mitigation finding, not a failed run).

## 8. Reproducing the paper's current (simulation) results

```
cd code/python
python3 sim.py --seeds 100  # Monte Carlo, 100 seeds (= the committed dataset); writes results like data/simulation-100seed/
python3 plot.py         # figures from the results
python3 ukf_sensitivity.py
```

The committed dataset in `data/simulation-100seed/` is the exact record behind the manuscript's Tables II-III and Results figures; the seed protocol (100 seeds, paired - every estimator in a run sees identical data) is described in the paper's Method section. Section V's hardware numbers reproduce from the datasets under `data/` with the protocols of Section 7, and the revision analyses (mechanism reproductions, gating ablations, the oracle-detector runs, the Table V re-runs, and both CI computations) are archived with scripts and outputs under `analysis/phase1/`.

## 9. Code layout

```
code/firmware/  logger/, logger_h745/          the two verified loggers
                gnss_baud/, gnss_baud_h745/    one-time baud setup
                gnss_config_h745/              TG/TS mask setup + recovery notes
code/python/    sim.py, plot.py, ukf_sensitivity.py   the paper's simulation
                allan.py                       Experiment 2 analysis
                mc_measured.py, compare_mc.py  measured-parameter re-runs
                psr_residue.py                 Experiment 4 phase A
                replay.py, score_walk.py       Experiments 1 + 3 (replay imports
                                               sim.py's estimators unmodified)
                tc_real.py, tc_selftest.py     Experiment 4 phase B (absolute-PsR
                                               harness + leg 1; self-test gate)
                tc_delta.py,                   Experiment 4 phase B (differenced
                tc_delta_selftest.py           harness, 3 clock variants + gate)
                make_fig_clockrate.py          the paper's Fig. 4 + its statistics
code/tools/     serial_monitor.py, walk_monitor.py   console capture tools
                                               (the walks were recorded with these)
analysis/phase1/  the revision analyses: reproductions, ablations,
                oracle/sensitivity runs, both CI computations, the Table V
                re-runs - scripts + outputs, indexed by its README
docs/           CALIBRATION_NOTE.md (Experiment 2 record),
                TC_HARNESS_DESIGN.md (Experiment 4 design + addenda),
                TS_PSR_NOTES.md ($PSTMTS/$PSTMTG record)
data/           datasets, per data/README.md
```

The copies under `code/` began as snapshots of the development tree; at the 2026-11-16 public release this package became self-contained and canonical, with every snapshot re-verified byte-identical to its source (or updated) at finalization.

## 10. Status and open items

- Rigs: both verified end-to-end (IMU streaming + GNSS fix +
  $PSTMTG/$PSTMTS) on 2026-11-07.
- Experiment 2: COMPLETE 2026-11-07 - calibration note in `docs/CALIBRATION_NOTE.md`; the paper's degraded-scenario rankings survive at the measured parameters; ZUPT-EKF open-sky regression flagged there.
- Experiment 4 phase A: COMPLETE 2026-11-07 - sky-view residue verdict: NO shared grid (44,314 usable lines); phase B designs around time-differenced PsR / per-channel ambiguity states. Dataset: `data/psr-skyview/`.
- Experiment 4 phase B: harness BUILT and gated 2026-11-08 - addendum 3 reformulation; tc_delta self-test PASS (v0 signature decisive; v1/v2 graded on rate error, per design addendum 6, recorded before the run); sky-capture run cross-validates the recovered residual clock rate against leg 1 (+0.06/+0.12 vs +0.06-0.08 m/epoch). COMPLETE 2026-11-08: a first run under a metal enclosure attenuated the signal only (5-14 dB, no outage) and serves as a control; run 2 (antenna disconnect, two scored cycles) measured the residual clock-rate step across ~90 s outages at +0.32 and -5.43 m/epoch (bootstrap-bounded by ~8 m/epoch), with no v0 gate signature - the absolute-pseudorange failure does not transfer to delta-range coupling on real hardware (structural mitigation confirmed; design addendum 8 in `docs/TC_HARNESS_DESIGN.md`; dataset data/psr-outage/).
- Experiment 1 (forest leg): COMPLETE 2026-11-14 - Stanton Woods leaf-off loop walk (rig #2, 18.3 min, 10 checkpoint stops), scored with `simulation/score_walk.py` (estimators unchanged, Stage-2 measured parameters): loop closure LC-UKF 2.52 / LC-EKF 2.61 / ZUPT-EKF 2.72 / GNSS 3.41 / RTS-SMOOTH 3.74 / ADAPT-EKF 5.00 m, INS diverged; stop-error medians: RTS-SMOOTH 2.54 m best, ZUPT-EKF 4.08, LC family ~6.0, ADAPT-EKF 9.68. The fix never dropped (leaf-off canopy, CN0 median 37 vs 40-42 open sky): a degraded-accuracy dataset, not an outage dataset. Dataset: `data/walk-forest/`. Canyon leg completed 2026-11-15 (next bullet).
- Experiment 3: COMPLETE 2026-11-14 on the walk-forest dataset - the paper's ZUPT detector fires on 80.2% of stationary samples and false-fires on 2.38% of walking samples, a candidate mechanism for the Experiment 2 open-sky ZUPT regression. Second environment (canyon, 2026-11-15): 70.6% / 6.10%.
- Experiment 1 (canyon leg): COMPLETE 2026-11-15 - downtown Windsor loop (rig #2, 21.5 min, 15 checkpoint stops), scored with the same script/protocol: loop closure LC-EKF 1.37 / ZUPT-EKF 2.61 / RTS-SMOOTH 4.40 / GNSS 4.48 / ADAPT-EKF 5.04 / LC-UKF 5.10 m, INS diverged; stop-error medians RTS-SMOOTH 3.97 best, ZUPT-EKF 7.21 worst. Fix continuous (CN0 30 s bins down to 29): multipath-degraded, no outages. The capture's first segment ended at +437 s in a logging-stream failure (IMU and GNSS together - a serial break, not a blackout) and is archived unscored. Dataset: `data/walk-canyon/`.
- Manuscript: all four experiments are complete and written into the paper as Section V.
- All four experiments are complete and written into the manuscript as Section V; the supporting analyses are archived under `analysis/phase1/`, the design record under `docs/`.
- License: code MIT (`LICENSE`); datasets CC BY 4.0 (`data/LICENSE.md`).

## License

Code (everything under `code/` and `analysis/`) is released under the
MIT License - see `LICENSE`. The datasets under `data/` are released
under the Creative Commons Attribution 4.0 International license
(CC BY 4.0) - see `data/LICENSE.md`.
