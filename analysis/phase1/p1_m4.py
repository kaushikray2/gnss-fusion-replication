import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'code', 'python'))
import sim
sim.SIG_A = 1.8066e-3; sim.SIG_G = 1.4688e-4; sim.BA_SD = 0.17; sim.BG_SD = 0.026
DT = sim.DT
sim.QD = np.diag([(sim.SIG_A*DT**2/2)**2]*2 + [(sim.SIG_A*DT)**2]*2 + [(sim.SIG_G*DT)**2, (1e-4*np.sqrt(DT))**2] + [(5e-3*np.sqrt(DT))**2]*2)
print('M4 turn-on-bias sensitivity: BA_SD=0.17 BG_SD=0.026, measured noise densities', flush=True)
sys.argv = ['sim.py', '--seeds', '100', '--out', '/tmp/phase1/m4_out']
sim.main()
import json
s = json.load(open('/tmp/phase1/m4_out/summary.json')) if False else None
