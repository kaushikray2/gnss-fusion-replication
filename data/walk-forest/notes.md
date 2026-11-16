# Dataset: walk-forest - Experiment 1 (forest leg) + Experiment 3

**When/where:** 2026-11-14, ~14:56-15:43 EST. Stanton Woods,
LaSalle ON - a leaf-off deciduous woodlot loop behind the
owner's house. Rig #2 (logger_h745 v8), carried flat;
recorder = walk_monitor.py on the owner's laptop.

**Delivered file:** `capture-20261114-145632.txt` (the monitor
appends to one file, so both segments are in it),
16,898,484 bytes, sha256
4602c4fd35a3c4fb714b05667ea23c75db909d47e1d1e5214e31bac361e41e27.
Original on the owner's laptop; a copy was uploaded by the author
on 2026-11-14. The file holds two captures:

- **Segment 1 (aborted):** 15:09:27-15:14:28 EST. The owner
  stopped the experiment in the middle (1 checkpoint reached).
  Hostclean (host prefixes/NULs stripped): 40,184 lines,
  sha256 f47cc27f7d4eb6675ea2f3c581b529ba29a8c6ba1120e9e0b0b5afc19e83de92.
- **Segment 2 (the scored walk):** 15:24:12-15:42:56 EST;
  WALK START 15:24:15, WALK END 15:42:30 (18.3 min, ~800 m
  loop, start = finish). 13 CHECKPOINT marks -> 10 distinct
  stops after clustering a 4-mark burst at one stop (marks
  4-7 within 0.8 s are one physical stop). Hostclean:
  149,694 lines, sha256
  4368404d6a25d55fffac0a35a4cce1c486f74baf7879842660c9e63273326214.

The raw capture and the derived hostclean segment files are identified by the sha256 hashes above; see `data/README.md` for how the bulk capture files accompany this release.

**Mark quirks (field notes, both fixed in the tool):**
- Every space-bar checkpoint in this capture is accompanied
  by a phantom WALK START mark at the same instant: the
  space press re-activated the still-focused WALK START
  button. Scoring ignores all but the first WALK START.
  Fixed by takefocus=0 on all monitor buttons
  (6506553 + 23ed7eb, the latter covering ttk buttons).
- Checkpoint numbering continued across the two segments
  (app-session state), so segment 2's stops are marks 2-14.

**Signal environment:** CN0 median 37 dB-Hz overall (30 s
bin medians 34-40) vs 40-42 on the open-sky captures - a
real but mild leaf-off depression. GGA quality was 1 or 2
at every epoch of both segments: **the fix never dropped**.
HDOP ~0.6. This is a degraded-but-continuous dataset, not
an outage dataset - as expected for November leaf-off.

**Scoring** (`simulation/score_walk.py`, results in
`walk_seg2_scores.json`): estimators via replay.py/sim.py
unchanged, Stage-2 measured noise parameters. Truth is
protocol-only: loop closure (start = finish point; the raw
fixes' own start/end medians sit 3.41 m apart, ordinary
fix noise) and the marked 10 s stops. No phone waypoints
were recorded, so each stop's reference position is the
receiver's median fix during that stop - GNSS stop errors
are therefore the reference floor by construction, and
filter rankings share one reference.

Loop-closure error (m): LC-UKF 2.52, LC-EKF 2.61,
ZUPT-EKF 2.72, GNSS raw fixes 3.41, RTS-SMOOTH 3.74,
ADAPT-EKF 5.00, INS diverged (real biases, no aiding).
Stop-position error, median over the 10 stops (m):
RTS-SMOOTH 2.54, ZUPT-EKF 4.08, LC-UKF 6.00, LC-EKF 6.08,
ADAPT-EKF 9.68.

**Experiment 3 result:** the paper's ZUPT detector, scored
against the protocol's stationary intervals, fires on
**80.2%** of stationary samples and false-fires on
**2.38%** of walking samples - the false fires inject
zero-velocity updates mid-stride on real data, a concrete
candidate mechanism for the Stage-2 open-sky ZUPT
regression (measured-parameter Monte Carlo).

**Status:** Experiment 1 forest leg SCORED; Experiment 3
SCORED on this dataset. The canyon (downtown) leg of
Experiment 1 is complete (canyon leg scored 2026-11-15; see `data/walk-canyon/`).
