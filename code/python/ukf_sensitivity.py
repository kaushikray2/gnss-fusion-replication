"""UKF tuning sensitivity check (added 2026-11-04, post-publication audit).

The published LC-UKF used alpha=0.5, beta=2, kappa=0, which for n=8 gives
lambda=-6 and a centre mean weight wm[0]=-3.0. An external audit argued
this handicaps the UKF. This script re-runs the UKF with two standard
alternative tunings on identical data (same seeds, same generators) and
reports full-run and challenge-window RMSE per scenario:

  A: alpha=1.0, beta=2, kappa=0    -> lambda=0,  wm[0]=0,    wc[0]=2
  B: alpha=1.0, beta=2, kappa=3-n  -> lambda=-5, wm[0]=-1.67, wc[0]=0.33

Usage: python3 ukf_sensitivity.py [seeds]
Writes ukf_sensitivity.csv next to this file.
"""
import sys
import numpy as np
import sim

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 16
TUNINGS = {"A_a1k0": (1.0, 2.0, 0.0), "B_a1k3n": (1.0, 2.0, -5.0), "C_a1e3k3n": (1e-3, 2.0, -5.0)}

rows = []
for scn in ["open", "canyon", "forest", "stress"]:
    agg = {t: [] for t in TUNINGS}
    for seed in range(SEEDS):
        acc_m, gyro_m, _, _ = sim.gen_imu(seed)
        eps = sim.gen_epochs(scn, seed)
        mask = sim.challenge_mask(scn, eps)
        for name, (a, b, k) in TUNINGS.items():
            est = sim.run_ukf(scn, acc_m, gyro_m, eps, seed,
                              alpha=a, beta=b, kappa=k)
            agg[name].append(sim.metrics(est, mask))
    for name in TUNINGS:
        r = agg[name]
        rows.append((scn, name,
                     float(np.mean([x["rmse"] for x in r])),
                     float(np.std([x["rmse"] for x in r])),
                     float(np.mean([x["chal"] for x in r])),
                     float(np.std([x["chal"] for x in r]))))
        print(rows[-1], flush=True)

with open("ukf_sensitivity.csv", "w") as f:
    f.write("scenario,tuning,rmse_mean,rmse_std,chal_mean,chal_std\n")
    for scn, name, rm, rs, cm, cs in rows:
        f.write(f"{scn},{name},{rm:.3f},{rs:.3f},{cm:.3f},{cs:.3f}\n")
print("WROTE ukf_sensitivity.csv")
