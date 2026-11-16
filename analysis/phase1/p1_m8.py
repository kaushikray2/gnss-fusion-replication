import numpy as np, sim_instr as sim
for scn in ('forest', 'canyon'):
    z = []; rz = []; rl = []
    for seed in range(100):
        acc, gyro, *_ = sim.gen_imu(seed); eps = sim.gen_epochs(scn, seed); mask = sim.challenge_mask(scn, eps)
        est, st = sim.run_lc(scn, acc, gyro, eps, seed, zupt=True, store=True)
        z.append(sim.metrics(est, mask)['chal']); rz.append(sim.metrics(sim.rts_smooth(st), mask)['chal'])
        est0, st0 = sim.run_lc(scn, acc, gyro, eps, seed, store=True)
        rl.append(sim.metrics(sim.rts_smooth(st0), mask)['chal'])
    print('M8 %s ZUPT %.3f RTS-ZUPT %.3f RTS-LC %.3f' % (scn, np.mean(z), np.mean(rz), np.mean(rl)), flush=True)
