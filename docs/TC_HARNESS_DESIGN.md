# Experiment 4 phase B - TC harness design (2026-11-07)

> Editorial note (public release, 2026-11-16): this is the contemporaneous design record, addenda included; its later addenda already revise the early "lockout" framing. The final manuscript's mechanism is partial gating plus clock-to-position aliasing on absolute pseudoranges, and clock-rate continuity on delta ranges (paper Sections IV-C and V-C).

Status: DESIGN. Build follows this note; the synthetic
self-test gate in section 5 must pass before the harness
touches real data.

## 1. The question, unchanged from the paper

On real $PSTMTS pseudoranges from the Teseo-LIV3F, through a
real 60-120 s total blockage: does the bias-only-clock TC-EKF
gate-lock on reacquisition (the paper's clock lockout), while
the two-state-clock TC-EKF-CD recovers? Evidence: per-variant
gate-rejection counts after the blockage, time to recovery
(first epoch with >= 4 accepted SVs), and position error
against the known static position.

## 2. What phase A forces

The sky-view verdict (no shared grid; per-SV residues scatter
~100 km with no common 200 ms / 20 ms quantisation) rules out
absolute PsR against a shared clock alone. The harness
therefore carries **per-SV ambiguity states** (the
pre-registered fallback):

    PsR_sv = range(rx, SV) + clock_bias + N_sv + noise

N_sv is a per-channel constant (random-walk sigma 0.01 m per
epoch - stiff, not free). It absorbs whatever offset that
channel carries, on either grid or none; GLONASS channels
absorb their system-time frame offset the same way, so no
constellation special-casing is needed. Ambiguity states are
shared by both clock variants - the ONLY difference between
the two runners remains the clock model, exactly as in
sim.py's run_tc (bias-only: Q_bb = 2.0^2 * DT; two-state:
bias + drift, Q as in run_tc). Sequential per-SV scalar
updates, 4-sigma gating, sigma_pr = 2.0 m baseline.

## 3. The gauge problem, and the convention that fixes it

Clock bias and the mean of the N_sv are degenerate by one
dimension: adding a constant to the clock and subtracting it
from every N changes nothing observable. Left alone, the
N inits would silently absorb the clock - including the
post-blockage clock jump the experiment exists to expose.

Convention: when an SV is (re)initialised, its N is set
from that epoch's residual MINUS the cross-SV median
residual of the epoch:

    N_sv := resid_sv - median_sv(resid)

The common part of every epoch's residuals is never absorbed
per-SV; it stays where the filter must explain it - the
clock state. At the capture's start the clock is seeded from
the GGA-anchored least-squares solution, and the N's start
zero-mean by construction. During a blockage the N's do not
move (no measurements, stiff RW), the clock free-runs per
its model, and on reacquisition the innovations carry the
common clock error just as they do in the simulation.
Reacquired SVs re-initialise by the same median rule, so a
changed per-channel offset after the gap cannot masquerade
as clock error either - the median split is what keeps the
two apart.

## 4. Why the blockage must be physical, not masked

A tempting shortcut - take the sky capture and withhold a
60-120 s window in post - does NOT reproduce the sim's
condition. In the sim the truth clock ramps exogenously
(2.0 m/s) whether or not the filter observes it. On the
real module, the $PSTMTS stream is produced by a receiver
that was tracking throughout any post-hoc mask: its
internal clock discipline never lapsed, so the post-mask
pseudoranges contain no accumulated clock error to gate
against. Masked data would test a fiction.

The blockage is therefore physical: rig static under sky,
logging continuously; the antenna is covered (metal
container) or disconnected for 60-120 s at a noted time,
then uncovered for >= 5 min. During the blockage the module
emits no usable TS lines - the honest gap - and its
oscillator runs undisciplined, so the reacquisition epochs
carry the real accumulated error.

## 5. Leg 1 - measure the real clock first (no new capture)

Before the blockage run, extract from the existing
sky-view capture the quantity the sim models as cb(t):
the per-epoch common-mode residue, median over SVs of
(geo_range - PsR) after removing each SV's own median over
the capture. Output: the series (CSV) and its summary -
drift rate (m/s, robust fit), wander (residual std after
detrending), and behaviour across the capture's 100 min.
This calibrates what the harness's clock process noise
should be on this hardware and is a result in its own
right for the paper's experimental section: it prices the
sim's 2.0 m/s ramp assumption against the real oscillator
as the module reports it. (Caveat it will carry: the series
is the module's post-discipline clock, not a free-running
one - that is precisely the quantity a TC filter fed
$PSTMTS would face between blockages.)

## 6. Harness structure (hardware/tc_real.py)

- Loader: import parse_ts / parse_gga / geodetic_to_ecef
  from psr_residue.py (single source of truth for the
  $PSTMTS field order); group TS lines into 1 Hz epochs by
  logger time as load_capture does; epochs carry per-SV
  (PsR, SV ECEF, CN0).
- Frames: anchor = median valid GGA of the capture. SV
  ECEF rotated into ENU about the anchor; ranges computed
  in 3-D, position state 2-D horizontal at anchor height -
  the sim's geometry convention.
- Navigation core: sim.py's mech / jac_F / QD and the
  measured IMU parameters (Stage 2 set) at 10 Hz, IMU rows
  decimated exactly as replay.py does (0.1 s bin average,
  rig carried flat, axis map option shared with replay).
- State: [8 nav][clock block: 1 or 2][N_sv slots: fixed
  pool of 32, SV-to-slot map; a slot frees when its SV has
  been unseen for > 10 s, and re-sighting re-initialises
  by the section-3 rule]. Sequential scalar updates in
  CN0-descending order, 4-sigma gate, rejections counted
  per SV and per epoch.
- Modes: --common-mode (leg 1) and the filter run
  (both variants in one pass, same measurements).
- Outputs (into the dataset folder): per-variant summary
  (gate rejections pre/post blockage, recovery time,
  position RMSE vs the static anchor), the per-epoch
  accept/reject trace (CSV), and the run's config echo.

## 7. Verification gate - synthetic self-test first

The harness does not touch real data until it reproduces
the known answer on synthetic data: generate a capture
through sim.py's own machinery (truth clock ramp 2.0 m/s,
per-SV ambiguity constants added, a 70 s total measurement
gap, static receiver) in the logger's file format, and
require: bias-only variant gate-locks after the gap
(recovery never, or > 120 s), two-state variant recovers
(first >= 4-accept epoch within a few seconds of
reacquisition), both sane before the gap. If the harness
cannot reproduce the sim's verdict on data whose truth is
known, the harness is wrong - fix it there, not on real
data.

## 8. The run (owner's physical step, ~15 min)

Rig #2 static, open sky, logger running, recorder attached.
Five minutes clean; cover the antenna with a metal
container (or disconnect it) for 90 s by the recorder's
clock; uncover; five more minutes. Note the cover/uncover
times in the dataset manifest. Then one command produces
the section-1 evidence for both clock variants.

## Addendum (2026-11-07) - what the self-test taught

The section-7 gate did its job: the first harness build
FAILED it, twice, for reasons that change the design.
Findings, in the order they were root-caused:

1. **The section-3 median-split is gauge-unsafe as first
   written.** Re-initialising a subset of SVs against
   that subset's own median residual shifts the gauge by
   the subset's N-median sampling spread (tens of km for
   U(-100, +100) km constants), poisoning the clock for
   every later epoch. Amended rules, now implemented:
   the gauge is anchored ONCE (first epoch, via the
   clock seed); later inits split against the LIVE
   innovations' median; slots are freed on TRACKED-time
   staleness (absence while other SVs were tracked), so
   a total outage frees nothing and post-outage SVs keep
   the ambiguity states they had - the experiment then
   also measures whether the module's per-channel
   offsets themselves survive a blockage.
2. **On static data the paper's heading / gyro-bias mode
   is unobservable and wanders.** Self-test gap-exit
   state (sim-matched profile): heading -98 deg with a
   formal sigma of ~1 deg, position sigma honestly grown
   to ~86 m, velocity error ~0.8 m/s. The sim never
   shows this (its receiver walks; heading is observable
   there). It is a property of the paper's filter on
   static data, not a harness bug - and phase B's real
   rig is static, so the real run will show it too.
3. **Consequently the sim's literal lockout (zero
   accepts, forever) does not transfer to static
   geometry.** Post-gap innovations are smeared across
   the gate by the position damage, so the bias-only
   variant admits a minority of SVs from the first epoch
   and wallows. The decisive static-geometry evidence,
   adopted as the phase B criteria, is: two-state -
   recovery at the first post-gap epoch, post-gap
   rejection rate < 5%, re-convergence to ~2 m; bias-
   only - sustained majority rejection (> 40%) and NO
   re-convergence (post RMSE > 3x the two-state's).
   Self-test outcome (both IMU profiles): bias-only
   post-gap rejection 55-63%, post RMSE 68-70 m;
   two-state rejection 0.0%, recovery 0.4 s, post
   RMSE 1.9-2.0 m. SELFTEST PASS.
4. Bookkeeping: the generator and the harness must take
   the anchor from the SAME GGA subset (the window's);
   a full-file vs window median differed by 4.8 m and
   masqueraded as filter RMSE until measured.

## Addendum 2 (2026-11-07, late) - leg 1 result: the
## module is a delta-range instrument

Leg 1 was run on the sky-view capture before any blockage
work, and it changes phase B's foundations. Measured
structure of $PSTMTS (5,982 epochs, 44,314 usable lines):

- Consecutive-epoch residues (geo - PsR) differ, per SV,
  by WHOLE 200 ms cells plus a common increment: the
  module re-aligns each channel's cell assignment epoch
  to epoch. Absolute PsR is therefore not merely
  un-gridded (phase A) - it is not a stable observable
  at all. **Time differences are**: after rounding each
  difference to the nearest cell, the cross-SV median is
  tight (IQR 3.2 m).
- The common increment is a steady ramp: median
  **-9,023.86 m per epoch** on (geo - PsR). The module's
  own $PSTMTG NCO (-47,421 Hz median) predicts
  -9,023.92 m per epoch for the same quantity. Two
  independent fields of the same capture agree to
  **0.06 m per epoch** - the ramp is the receiver's
  ~30 ppm oscillator offset, reported, not hidden.
- Estimator traps, recorded so they are not repeated:
  the differences accumulate over the MODULE's epochs,
  not the logger's jittered arrival times (dividing by
  logger dt destroyed the estimate); removing a nominal
  rate before cell-rounding pushes residues onto the
  rounding boundary and corrupts it; pairs need >= 4
  SVs in common for the median to hold.

Phase B therefore reformulates on **time-differenced
PsR** (the pre-registered fallback): per-SV delta ranges
with the cell integer resolved by rounding against the
filter's prediction (prediction error is metres; the
cell is 59,958,492 m - the resolution is exact), the
nominal NCO rate removed from TG, and the clock states
modelling the RESIDUAL common rate: variant 1 carries
the rate as a random walk only (the bias-only analogue),
variant 2 adds the rate's derivative (the two-state
analogue). Across a real blockage the residual rate is
what jumps; gate counts, recovery and re-convergence
remain the evidence, with the addendum-1 criteria. The
harness v1 in tc_real.py (absolute PsR + ambiguity
states) stands as the self-test-verified reference for
the sim's conditions; the differenced front end is
phase B's build from here. Whole-capture integration of
the residual clock wander (across pair-admission gaps)
remains open for the write-up.

## Addendum 3 (2026-11-07, late) - what the delta-range
## reformulation does to the clock experiment

Addendum 2 moved phase B to time-differenced PsR. Working
through the filter mathematics before building it surfaces
a second, deeper consequence, recorded here because it
changes the claim the experiment can make - it needs the
owner's eye before the differenced harness is built.

**The paper's lockout is an absolute-measurement
phenomenon.** In the sim, the gate judges the absolute
phase error accumulated across the outage (~140 m) against
a gate that grows only as sqrt(T). A delta-range filter
never sees absolute phase: its per-epoch innovation
carries the RATE error, not the integral. An unmodelled
rate step of size D is rejected only while D exceeds the
gate (~4 sqrt(P + R)); P grows linearly under rejection,
so the gate catches up in ~(D/4)^2 / Q epochs - a delayed
recovery, not a permanent lockout, and the two-state
clock's sim advantage (predicting the integral forward
through the outage) has no analogue, because through a
total outage neither variant observes anything and the
rate itself is the persistent quantity both carry.

**What survives translation is the model-order lesson,
in rate space.** Three clock treatments for the delta
harness, sharing the nav core and the cell-rounded
delta front end:

- v0: NO clock state - delta-PsR treated as pure geometry
  after nominal NCO removal. The naive design a real
  integrator would write first.
- v1: residual common rate as a random-walk state.
- v2: rate + rate derivative (the two-state analogue).

Across a real blockage the module's residual rate (after
TG/NCO removal) steps by whatever its undisciplined
oscillator does. v0 has no state to absorb any of it;
v1 chases a step with random-walk lag; v2 tracks a
ramping rate. Gate-rejection rates and re-convergence
after the blockage separate them - IF the real rate step
is big enough to separate anything.

**Therefore: measure the step before claiming the
separation.** The blockage capture answers this with no
filter at all: leg 1's difference machinery on the
pre- and post-blockage segments gives the residual rate
on both sides (TG is present on both sides), and the
difference IS the step the experiment turns on. If it is
~0, the honest phase B result is that this module's
clock discipline makes the rate-step failure unreachable
in a 90 s blockage - a finding, not a failure. If it is
tens of m/epoch, the three-variant run decides the
model-order question on real data.

**Run design, updated.** (1) The static blockage capture
(owner, ~15 min, as before) - now dual-purpose: the
rate-step measurement plus the three-variant filter run.
(2) The Stage 3 canyon walk doubles as phase B's second
leg: real fix dropouts with delta-PsR still flowing are
the closest hardware analogue of the sim's forest that
this module offers. The differenced harness's self-test
(addendum 1 discipline) uses a synthetic persistent
post-gap rate step, with addendum 1's evidence criteria
(rejection rates and re-convergence, not a literal
zero-accept lockout).

## Addendum 4 (2026-11-07, late) - review #9 disposition;
## the 1 ms fold is adopted

An external review endorsed addenda 2-3 and contributed
one material catch, verified against the sky capture
(full disposition in docs/audit-response-2026-11-04.md,
review #9):

- **Whole-ms common jumps are real and frequent.** After
  200 ms folding, 744 of 2,461 admitted epoch pairs
  (30%) still sit ~299,792 m off the rate cluster;
  folding differences mod 1 ms (which divides the
  200 ms cell) collapses pairs with |residual| > 100 m
  from ~750 to 15, median unchanged (9,024.00 vs
  9,023.86 m/epoch). The differenced front end and the
  leg-1 estimator therefore fold mod 1 ms. The review's
  mechanism story (a steering tick every ~33 s) is NOT
  supported - anomalous dTOW steps occur in 1,788 of
  5,982 TG epochs - but the prescription is right.
- **The clock rate is not constant across a capture.**
  At TOW 8700 (capture start) the rate is +9,074.5 m/s
  (NCO -47,693 Hz, drifting +23 Hz in 33 s); the
  whole-capture median is +9,023.86 (NCO -47,421).
  Pre/post blockage comparisons must use local windows,
  which is how the rate-step diagnostic is built.
- The review's framing for the manuscript - a near-zero
  rate step would be a STRUCTURAL MITIGATION finding
  (delta-range coupling is immune to phase-accumulation
  lockout), not merely an unreachable failure - is
  recorded for the experimental section, pending the
  owner's ratification of addendum 3 itself.

## Addendum 5 (2026-11-08) - addendum 3 RATIFIED;
## differenced harness build

The owner ratified addendum 3 on 2026-11-08 (his tap on
the ratification option, followed by his message
"Ratify Addendum 3 - build the differenced harness").
The build proceeds as specified in addenda 2-4:
tc_delta.py, three clock variants (v0 no rate state,
v1 rate random walk, v2 rate + derivative) on the
M1-folded delta front end with the nominal NCO rate
removed from TG; delta observations never span an
outage (pairs form only between consecutive ~1 s
epochs; the outage enters through the clock states'
coasted covariance and the post-gap rate itself).
The self-test gate (addendum 1 discipline) uses a
synthetic rate slew through and after the gap - the
faithful delta-space analogue of the sim's drifting
bias - with rejection-rate and re-convergence criteria.

## Addendum 6 (2026-11-08) - differenced harness built;
## self-test PASS; sky-run cross-validation

tc_delta.py is built as specified (addendum 5) and
tc_delta_selftest.py gates it. Findings, from the runs'
own numbers:

- SELF-TEST PASS. v0 (no clock state) is decisively
  separated: pre-gap accept degrades to 0.810 once the
  truth rate slews, post-gap rejection 0.960, no
  recovery. v1 and v2 both recover 4.6 s after the gap
  with 4.5% post-gap rejections and re-converge in rate.
- v1 vs v2 do NOT separate on gate counts, in the
  self-test or on real data. After a 90 s IMU coast the
  navigation covariance (frozen-prev-range coupling puts
  position sigma ~100 m into every S) swamps the ~90 m
  clock-model difference at re-acquisition. They DO
  separate on rate-tracking accuracy: self-test rate
  errors v2 0.65 / 0.57 m/epoch (pre-gap slew / late
  hold) against v1 1.70 / 1.06; on the sky capture the
  rate series IQR is 1.25 (v2) against 2.37 (v1). The
  real blockage run therefore grades v0-vs-clock-state
  on gates and v1-vs-v2 on rate error - recorded here
  BEFORE the run, so the criteria are not fitted to it.
- Position in a delta-only filter is a random walk
  (self-test ~110 m pre-gap for all variants; sky
  capture 759-907 m over 100 min). Delta ranging aids
  velocity and the clock; it is not positioning. Phase
  B's evidence is gate counts and the rate series.
- SKY-RUN CROSS-VALIDATION: on the open-sky capture
  (no blockage) all three variants accept ~91% of
  19.7k delta observations, and the v1/v2 rate states
  converge to +0.06 / +0.12 m/epoch median residual -
  the leg-1 zero-filter estimator's independent
  measurement of the same quantity was +0.06 to
  +0.08 m/epoch. The harness end-to-end recovers the
  module's residual clock rate on real data.

Remaining: the owner's blockage capture, then the
rate-step diagnostic (leg 1, local windows) and the
three-variant run on it.

## Addendum 7 (2026-11-08) - first blockage run INVALID:
## attenuation is not an outage

The owner's first blockage capture (dataset
replication/data/psr-outage/, run 1) followed the
protocol's timing exactly, but the data show the metal
tin only attenuated: CN0 medians fell 5-14 dB across
the three covered windows while the module held 14-15
SVs and a continuous fix; $PSTMTS never stopped. No
tracking-loop unlock, no undisciplined interval, hence
no rate step exists to measure - and a "near-zero step"
verdict from this file would be an artefact of the
shield, not the structural-mitigation finding, which
requires a real outage. The run is recorded INVALID
for phase B, not failed-by-the-hypothesis.

Re-run specification: the covered state must show
GGA fix lost and TS silent within ~10 s (watch the
recorder stream live; if the fix holds, the shield is
leaking). Two accepted methods: (a) tin with the lid
seam and cable slot sealed with aluminum foil;
(b) disconnect the antenna for the covered interval
(the protocol's standing alternative; foolproof).
Everything else in the protocol is unchanged.

## Addendum 8 (2026-11-08) - PHASE B COMPLETE:
## structural mitigation CONFIRMED on real hardware

Run 2 (dataset psr-outage; antenna disconnect, two
scored cycles of 110 s and 75 s) gives the decisive
pre-registered measurement. Residual clock rate in
local windows either side of each outage (leg-1
estimator; fake-gap controls on the sky capture:
-0.28 / +0.23 m/epoch): cycle 1 step +0.32 m/epoch;
cycle 2 step -5.43 m/epoch on the noisiest window
(IQR 8.5, n=30), with the filters' own post-gap rate
estimates at -0.43 (v1) / -0.31 (v2) - i.e. ~0. Bound:
any true step is <= ~5 m/epoch, against the ~140 m
accumulated absolute error that locks out the
paper's bias-only filter. The three-variant run
agrees: v0 (no clock state) shows NO post-gap gate
signature in either cycle (post-gap rejection ~9-11%,
same as pre-gap; recovery 2.4 s / 10.4 s for all
variants) - there is no step for a clock state to
absorb. On the Addendum 6 rate axis, v2 tracks
tighter than v1 in every window, as in simulation.

Phase B conclusion: the tight-coupling lockout is an
absolute-pseudorange phenomenon. Time-differenced
(delta-range) coupling is structurally immune on this
receiver, because its innovations carry only the
clock RATE error, and the Teseo-LIV3F's rate survives
a 90 s undisciplined interval essentially unchanged.
The model-order lesson survives in rate space only
as a tracking-precision preference (v2 > v1), not as
a divergence boundary. Phase B is closed; the canyon
walk remains as experiment 1/3 scope, not phase B.
