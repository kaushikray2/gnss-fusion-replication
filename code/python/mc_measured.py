#!/usr/bin/env python3
"""Monte Carlo re-run at MEASURED IMU parameters (Stage 2).

Patches simulation/sim.py's four noise constants with values from
an Allan calibration (hardware/allan.py) and rebuilds QD with
sim.py's own formula (the 1e-4 / 5e-3 bias random-walk terms are
the filters' process model and are NOT touched), then runs the
standard 100-seed sweep via sim.main(). The estimator code, the
truth generation and the scenarios are exactly the paper's; only
the IMU noise/bias parameters change. Parameter provenance is
recorded in the calibration note in the dataset folder.

Usage: python3 mc_measured.py --sig-a A --sig-g G --ba-sd B --bg-sd D \\
           --seeds 100 --out DIR
"""
import argparse, sys
import numpy as np
sys.path.insert(0, 'simulation')
import sim

ap = argparse.ArgumentParser()
ap.add_argument('--sig-a', type=float, required=True)
ap.add_argument('--sig-g', type=float, required=True)
ap.add_argument('--ba-sd', type=float, required=True)
ap.add_argument('--bg-sd', type=float, required=True)
ap.add_argument('--seeds', type=int, default=100)
ap.add_argument('--out', required=True)
a = ap.parse_args()

sim.SIG_A = a.sig_a
sim.SIG_G = a.sig_g
sim.BA_SD = a.ba_sd
sim.BG_SD = a.bg_sd
DT = sim.DT
sim.QD = np.diag([(sim.SIG_A * DT**2 / 2)**2] * 2 +
                 [(sim.SIG_A * DT)**2] * 2 +
                 [(sim.SIG_G * DT)**2, (1e-4 * np.sqrt(DT))**2] +
                 [(5e-3 * np.sqrt(DT))**2] * 2)
print('patched: SIG_A=%.4e SIG_G=%.4e BA_SD=%.4e BG_SD=%.4e'
      % (sim.SIG_A, sim.SIG_G, sim.BA_SD, sim.BG_SD))
sys.argv = ['sim.py', '--seeds', str(a.seeds), '--out', a.out]
sim.main()
