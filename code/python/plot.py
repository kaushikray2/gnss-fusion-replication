#!/usr/bin/env python3
"""Figures from results/results.json -> results/fig_*.png"""
import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "results/results.json"))
S, ex = d["summary"], d["example"]
DT5 = 0.5  # error series stored every 5 steps of 0.1 s

# Fig 1: forest trajectory (seed 0)
fig, ax = plt.subplots(figsize=(6.5, 5))
tr = np.array(ex["truth"])
ax.plot(tr[:, 0], tr[:, 1], "k-", lw=1.6, label="truth")
for m, st in [("GNSS", "--"), ("LC-EKF", "-"), ("TC-EKF-CD", "-"),
              ("LC-UKF", "-."), ("ZUPT-EKF", ":")]:
    e = np.array(ex["est"][m])
    ax.plot(e[:, 0], e[:, 1], st, lw=1.0, label=m)
ax.set_xlabel("East (m)"); ax.set_ylabel("North (m)")
ax.legend(fontsize=8); ax.set_aspect("equal"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("results/fig_traj.png", dpi=200)

# Fig 2: forest error time series (seed 0)
fig, ax = plt.subplots(figsize=(6.5, 3.2))
t = np.arange(len(next(iter(ex["err"].values())))) * DT5
for m in ["GNSS", "INS", "LC-EKF", "TC-EKF", "TC-EKF-CD", "ZUPT-EKF"]:
    ax.plot(t, ex["err"][m], lw=0.9, label=m)
for a, b in [(100, 170), (240, 290)]:
    ax.axvspan(a, b, color="grey", alpha=0.18)
ax.set_xlabel("time (s)"); ax.set_ylabel("position error (m)")
ax.legend(fontsize=8, ncol=3); ax.grid(alpha=0.3); ax.set_ylim(0, 80)
fig.tight_layout(); fig.savefig("results/fig_err.png", dpi=200)

# Fig 3: challenge-window RMSE by scenario
scns = ["open", "canyon", "forest", "stress"]
methods = ["GNSS", "INS", "LC-EKF", "TC-EKF", "TC-EKF-CD", "LC-UKF",
           "ZUPT-EKF", "ADAPT-EKF", "RTS-SMOOTH"]
x = np.arange(len(methods)); w = 0.2
fig, ax = plt.subplots(figsize=(7.5, 3.6))
for i, scn in enumerate(scns):
    vals = [S[scn][m]["chal_mean"] for m in methods]
    errs = [S[scn][m]["chal_std"] for m in methods]
    ax.bar(x + (i - 1.5) * w, vals, w, yerr=errs, capsize=2, label=scn)
ax.set_xticks(x); ax.set_xticklabels(methods, rotation=30, ha="right", fontsize=8)
ax.set_ylabel("challenge-window RMSE (m)")
ax.set_yscale("log"); ax.legend(fontsize=8); ax.grid(alpha=0.3, axis="y")
fig.tight_layout(); fig.savefig("results/fig_bar.png", dpi=200)
print("figures written")
