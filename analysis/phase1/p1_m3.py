import numpy as np, sim_instr as sim
QD0 = sim.QD.copy(); DEF = (sim.SIG_A, sim.SIG_G, sim.BA_SD, sim.BG_SD)
def set_params(p):
    sim.SIG_A, sim.SIG_G, sim.BA_SD, sim.BG_SD = p; DT = sim.DT
    sim.QD = np.diag([(p[0]*DT**2/2)**2]*2 + [(p[0]*DT)**2]*2 + [(p[1]*DT)**2, (1e-4*np.sqrt(DT))**2] + [(5e-3*np.sqrt(DT))**2]*2)
def run_set(tag, p):
    set_params(p)
    for scn in ('open', 'forest'):
        out = {m: [] for m in ('LC', 'ZUPT', 'ORACLE')}; TP=FP=FN=TN=0
        for seed in range(100):
            acc, gyro, *_ = sim.gen_imu(seed); eps = sim.gen_epochs(scn, seed); mask = sim.challenge_mask(scn, eps)
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
        print('M3 %s %s LC %.3f ZUPT %.3f ORACLE %.3f | det recall %.3f falsefire %.4f precision %.3f' % (tag, scn, *[np.mean(out[m]) for m in ('LC','ZUPT','ORACLE')], TP/max(TP+FN,1), FP/max(FP+TN,1), TP/max(TP+FP,1)), flush=True)
run_set('assumed', DEF)
run_set('measured', (1.8066e-3, 1.4688e-4, 5.149e-4, 3.506e-5))
