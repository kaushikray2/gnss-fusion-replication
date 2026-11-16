src = open('sim.py').read()
old = 'p_sd, h_err, h_sd = 15.0, np.deg2rad(25.0), np.deg2rad(30.0)'
assert src.count(old) == 1
src = src.replace(old, 'p_sd, h_err, h_sd = 15.0, np.deg2rad(HERR_DEG), np.deg2rad(30.0)')
src = src.replace('DT = 0.1', 'HERR_DEG = 25.0\nDT = 0.1', 1)
open('sim_h.py', 'w').write(src); print('sim_h.py written')
