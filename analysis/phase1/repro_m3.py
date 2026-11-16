import numpy as np, sim_instr as sim
QD0 = sim.QD.copy(); DEF = (sim.SIG_A, sim.SIG_G, sim.BA_SD, sim.BG_SD)
def set_params(sa, sg, ba, bg):
    sim.SIG_A, sim.SIG_G, sim.BA_SD, sim.BG_SD = sa, sg, ba, bg
    DT = sim.DT
    sim.QD = np.diag([(sa*DT**2/2)**2]*2 + [(sa*DT)**2]*2 + [(sg*DT)**2, (1e-4*np.sqrt(DT))**2] + [(5e-3*np.sqrt(DT))**2]*2)
def run_set(tag):
    print('== param set:', tag, flush=True)
    for scn in ('open', 'forest'):
        out = {m: [] for m in ('LC', 'ZUPT', 'ORACLE')}
        TP=FP=FN=TN=0
        for seed in range(30):
            acc, gyro, *_ = sim.gen_imu(seed)
            eps = sim.gen_epochs(scn, seed)
            mask = sim.challenge_mask(scn, eps)
            est, _ = sim.run_lc(scn, acc, gyro, eps, seed, zupt=False); out['LC'].append(sim.metrics(est, mask)['chal'])
            sim.ORACLE_ZUPT = False; sim.LC_LOG.clear()
            est, _ = sim.run_lc(scn, acc, gyro, eps, seed, zupt=True); out['ZUPT'].append(sim.metrics(est, mask)['chal'])
            still = sim.TRUTH['speed'] < 0.01
            for k, f in sim.LC_LOG:
                if f and still[k]: TP += 1
                elif f: FP += 1
                elif still[k]: FN += 1
                else: TN += 1
            sim.ORACLE_ZUPT = True
            est, _ = sim.run_lc(scn, acc, gyro, eps, seed, zupt=True); out['ORACLE'].append(sim.metrics(est, mask)['chal'])
            sim.ORACLE_ZUPT = False
        for m, v in out.items(): print(scn, m, 'challenge RMSE mean %.3f' % np.mean(v), flush=True)
        print(scn, 'detector: recall %.3f  false-fire-on-moving %.4f  precision %.3f' % (TP/max(TP+FN,1), FP/max(FP+TN,1), TP/max(TP+FP,1)), flush=True)
run_set('measured')
set_params(1.8066e-3, 1.4688e-4, 5.149e-4, 3.506e-5)
run_set('measured')
sim.QD = QD0; set_params(*DEF); sim.QD = QD0
run_set('assumed')
