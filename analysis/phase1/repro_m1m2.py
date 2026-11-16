import numpy as np, sim_instr as sim
print('M1/M2: bias-only TC-EKF, forest, 100 seeds', flush=True)
rows = {}; faith = []; rec1 = 0; end5 = 0; rec1_10 = 0
for seed in range(100):
    acc, gyro, *_ = sim.gen_imu(seed)
    eps = sim.gen_epochs('forest', seed)
    sim.TC_LOG.clear()
    est = sim.run_tc('forest', acc, gyro, eps, seed, clock_drift=False)
    err = np.linalg.norm(est - sim.TRUTH['pos'], axis=1)
    faith.append(sim.metrics(est, sim.challenge_mask('forest', eps))['chal'])
    log = {k: (a, v) for k, a, v in sim.TC_LOG}
    if seed < 5:
        rows[seed] = [(t, log[t*10][0], log[t*10][1], round(float(err[t*10]), 1)) for t in (171, 200, 239)]
    if err[1700:2400].min() < 5.0: rec1 += 1
    if err[1700:2400].min() < 10.0: rec1_10 += 1
    if err[-1] < 5.0: end5 += 1
faith = np.array(faith)
print('faithfulness: mean challenge RMSE = %.3f (archived 175.913)' % faith.mean())
print('challenge RMSE median %.2f  p25 %.2f  p75 %.2f' % (np.median(faith), *np.percentile(faith, [25, 75])))
for s, r in rows.items():
    print('seed', s, ' '.join('t=%d acc=%d/%d err=%.1f' % (t, a, v, e) for t, a, v, e in r))
print('recovered after outage 1 (min err t=170..240 < 5 m): %d/100' % rec1)
print('recovered after outage 1 (< 10 m): %d/100' % rec1_10)
print('final err < 5 m: %d/100' % end5)
