# Dataset: walk-canyon - Experiment 1 (canyon leg) + Experiment 3, 2nd environment

**When/where:** 2026-11-15, 16:40-17:12 EST. Downtown
Windsor loop (Riverside / Ouellette / University /
McDougall, per the owner's route). Rig #2 (logger_h745
v8), carried flat; recorder = walk_monitor.py on the
owner's laptop (the pre-takefocus build - checkpoint
marks arrive doubled ~0.1 s apart; the scorer's 3 s
clustering resolves them, as with the forest capture).

**Delivered file:** `capture-20261115-163638.txt`,
20,851,507 bytes, sha256
a2aa0375f27f22f7d77635fc5ddbbdf41e65e1e41f6efbfc1c35ac7b17e15ddb
Release asset (v1.0.0): `walk-canyon-raw-capture-2026-11-15.txt`.
(original on the owner's laptop; copy uploaded by the author
2026-11-15). Two captures in one appended file:

- **Segment 1 (partial, archived unscored):**
  16:40:28-16:50:15 EST; walk from 16:40:54, 5 distinct
  stops. **At +437 s the entire logger stream stops -
  IMU and GNSS together - while the monitor kept
  writing its marks.** That is a serial/USB/power break
  in the logging chain, NOT a GNSS blackout (a blackout
  leaves the IMU streaming at full rate; here the IMU
  count matches exactly 437 s of streaming). The owner
  stopped, reconnected and restarted. Hostclean:
  59,385 lines, sha256
  9d1b791a72cc082267a7cdabf7038ea6b41a82b68524b617f5d6d8c9d82d3d0f.
- **Segment 2 (the scored walk):** 16:50:33-17:12:23
  EST; WALK START 16:50:51, WALK END 17:12:18
  (21.5 min). 30 checkpoint marks -> 15 distinct stops.
  Hostclean: 175,698 lines, sha256
  15ccb449c12f0b0138f0b59c05988a28bf50d5ac7ce171ccdd40abab69573c24.

The raw capture and the derived hostclean segment files are identified by the sha256 hashes above; see `data/README.md` for how the bulk capture files accompany this release.

**Signal environment:** the fix stayed continuous
(1,308 fix epochs over 1,317 s; GGA quality 1/2 only),
but the canyon degraded it measurably more than the
forest did: CN0 median 36 dB-Hz (30 s bins 29-42, vs
forest 34-40), raw-fix loop closure 4.48 m (forest
3.41), raw stop wander 3.58 m (forest 2.38). Multipath
noise, no outages - the same "too good receiver"
pattern as the forest leg, one notch harsher.

**Scoring** (`simulation/score_walk.py`, results in
`walk_seg2_scores.json`): identical protocol and
parameters to the forest leg; loop physically closed
(raw start/end fix medians 4.55 m apart). Loop-closure
error (m): LC-EKF 1.37, ZUPT-EKF 2.61, RTS-SMOOTH 4.40,
GNSS raw 4.48, ADAPT-EKF 5.04, LC-UKF 5.10, INS
diverged (4.0 km). Stop-position error, median over
15 stops (m): RTS-SMOOTH 3.97, LC-EKF 4.44, LC-UKF
5.06, ADAPT-EKF 5.24, **ZUPT-EKF 7.21 (worst fused;
max 17.16)**.

**Experiment 3, second environment:** the ZUPT detector
fires on **70.6%** of stationary samples and
false-fires on **6.10%** of walking samples - versus
80.2% / 2.38% in the forest. The detector is markedly
dirtier downtown, and ZUPT-EKF correspondingly falls
from second-best at forest stops to worst fused method
here: **ZUPT's field value is detector-limited.**

**Status: Experiment 1 COMPLETE (both legs).**
Experiment 3 scored in both environments. The owner's
phone GnssLogger log (planned second dataset) failed:
the app stopped mid-walk (owner's report, 2026-11-15)
and no usable phone log exists. The canyon dataset is
the rig capture only.
