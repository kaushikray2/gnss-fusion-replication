import numpy as np, sim_instr as sim
CHI2_999 = {3:16.27, 4:18.47, 5:20.52, 6:22.46, 7:24.32, 8:26.12, 9:27.88}
def run_tc2(scn, acc_m, gyro_m, eps, seed, mode):
    rng = np.random.default_rng(9000 + seed)
    x8, P8 = sim.init_state(scn, eps[0]["fix"], rng)
    ns = 9
    x = np.zeros(ns); x[:8] = x8
    P = np.zeros((ns, ns)); P[:8, :8] = P8; P[8, 8] = 30.0**2
    Q = np.zeros((ns, ns)); Q[:8, :8] = sim.QD; Q[8, 8] = 2.0**2 * sim.DT
    ep = {e["k"]: e for e in eps}
    est = np.zeros((sim.N, 2)); rej_streak = 0
    for k in range(sim.N):
        if k > 0:
            F = np.eye(ns); F[:8, :8] = sim.jac_F(x[:8], acc_m[k-1])
            xn = x.copy(); xn[:8] = sim.mech(x[:8], acc_m[k-1], gyro_m[k-1])
            x = xn; P = F @ P @ F.T + Q
        if k in ep:
            e = ep[k]; vis = list(np.where(e["vis"])[0])
            if mode == 'reseed' and rej_streak >= 3 and vis:
                res = [e["pr"][i] - np.linalg.norm(sim.SAT_P[i] - np.array([x[0], x[1], 0.0])) for i in vis]
                x[8] = float(np.median(res)); P[8, 8] = 30.0**2; P[8, :8] = 0.0; P[:8, 8] = 0.0; rej_streak = 0
            if mode == 'rand':
                np.random.default_rng(4242 + seed*100000 + k).shuffle(vis)
            if mode == 'joint' and vis:
                H = np.zeros((len(vis), ns)); innov = np.zeros(len(vis))
                for j, i in enumerate(vis):
                    d = sim.SAT_P[i] - np.array([x[0], x[1], 0.0]); r = np.linalg.norm(d)
                    H[j, 0] = -d[0]/r; H[j, 1] = -d[1]/r; H[j, 8] = 1.0
                    innov[j] = e["pr"][i] - (r + x[8])
                S = H @ P @ H.T + np.eye(len(vis)) * e["sig"]**2
                nis = float(innov @ np.linalg.solve(S, innov))
                if nis <= CHI2_999[len(vis)]:
                    for i in vis:
                        d = sim.SAT_P[i] - np.array([x[0], x[1], 0.0]); r = np.linalg.norm(d)
                        H1 = np.zeros((1, ns)); H1[0, 0] = -d[0]/r; H1[0, 1] = -d[1]/r; H1[0, 8] = 1.0
                        x, P = sim._scalar_update(x, P, e["pr"][i] - (r + x[8]), H1, e["sig"]**2)
                    rej_streak = 0
                else: rej_streak += 1
            else:
                acc_n = 0
                for i in vis:
                    d = sim.SAT_P[i] - np.array([x[0], x[1], 0.0]); r = np.linalg.norm(d)
                    H = np.zeros((1, ns)); H[0, 0] = -d[0]/r; H[0, 1] = -d[1]/r; H[0, 8] = 1.0
                    innov = e["pr"][i] - (r + x[8])
                    S = float((H @ P @ H.T)[0, 0]) + e["sig"]**2
                    if abs(innov) <= 4.0*np.sqrt(S):
                        x, P = sim._scalar_update(x, P, innov, H, e["sig"]**2); acc_n += 1
                rej_streak = rej_streak + 1 if (vis and acc_n == 0) else 0
        est[k] = x[0:2]
    return est
for mode in ('seq', 'joint', 'rand', 'reseed'):
    chal = []; rec = 0; fin = 0
    for seed in range(100):
        acc, gyro, *_ = sim.gen_imu(seed); eps = sim.gen_epochs('forest', seed)
        est = run_tc2('forest', acc, gyro, eps, seed, mode)
        err = np.linalg.norm(est - sim.TRUTH['pos'], axis=1)
        chal.append(sim.metrics(est, sim.challenge_mask('forest', eps))['chal'])
        rec += err[1700:2400].min() < 5.0; fin += err[-1] < 5.0
    chal = np.array(chal)
    print('M1 mode=%s chal mean %.3f median %.2f p25 %.2f p75 %.2f | recovered %d/100 | final<5m %d/100' % (mode, chal.mean(), np.median(chal), *np.percentile(chal, [25, 75]), rec, fin), flush=True)
