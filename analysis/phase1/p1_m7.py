import numpy as np, sim_h as sim
def conv_time(err):
    ok = err < 2.0
    for t in range(50, len(err) - 100):
        if ok[t:t+100].all(): return t / 10.0
    return float('inf')
for herr in (0.0, 25.0, 60.0, 90.0, 135.0, 180.0):
    sim.HERR_DEG = herr
    for name, fn in (('LC-EKF', lambda a,g,e,s: sim.run_lc('stress', a, g, e, s)[0]), ('LC-UKF', lambda a,g,e,s: sim.run_ukf('stress', a, g, e, s))):
        chal = []; ct = []
        for seed in range(30):
            acc, gyro, *_ = sim.gen_imu(seed); eps = sim.gen_epochs('stress', seed)
            est = fn(acc, gyro, eps, seed)
            err = np.linalg.norm(est - sim.TRUTH['pos'], axis=1)
            chal.append(sim.metrics(est, sim.challenge_mask('stress', eps))['chal']); ct.append(conv_time(err))
        ctf = [c for c in ct if np.isfinite(c)]
        print('M7 herr=%5.1f %s chal %.3f | converged %d/30, median conv %s s' % (herr, name, np.mean(chal), len(ctf), ('%.1f' % np.median(ctf)) if ctf else 'n/a'), flush=True)
