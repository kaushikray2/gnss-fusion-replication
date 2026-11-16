#!/usr/bin/env python3
"""Monte Carlo comparison of GNSS/INS estimator families.

Implements the design in DESIGN.md. All estimators in a run share identical
IMU and pseudorange data (paired comparison). Usage:
    python3 sim.py --out results [--seeds 16] [--quick]
Writes results.json, summary.csv and PNG figures into --out.
"""
import argparse, json, time
import numpy as np

DT = 0.1            # IMU step (10 Hz)
T_END = 300.0
N = int(T_END / DT) + 1
EPOCH = int(1.0 / DT)          # GNSS epoch = 1 s
SIG_A = 0.10                   # accel white noise / sample (m/s^2)
SIG_G = 0.005                  # gyro white noise / sample (rad/s)
BA_SD = 0.08                   # accel bias draw sd (m/s^2)
BG_SD = 0.008                  # gyro bias draw sd (rad/s)

# ---------------- truth trajectory ----------------
_SEG = [(20,1.3,0.0),(8,1.3,0.35),(14,1.3,0.0),(6,0.0,0.0),
        (16,1.4,-0.25),(10,1.4,0.0),(6,0.0,0.0),(12,1.2,0.30),
        (18,1.2,0.0),(6,0.0,0.0),(10,1.35,-0.35),(16,1.35,0.0),(6,0.0,0.0)]

def build_truth():
    """Return dict of truth arrays (len N): pos(2), vel(2), psi, omega, acc_body(2)."""
    tgt_v = np.zeros(N); tgt_w = np.zeros(N)
    k = 0; pat = _SEG * 3
    for dur, spd, trn in pat:
        steps = int(round(dur / DT))
        tgt_v[k:k+steps] = spd; tgt_w[k:k+steps] = trn
        k += steps
        if k >= N: break
    if 0 < k < N:
        tgt_v[k:] = tgt_v[k-1]; tgt_w[k:] = tgt_w[k-1]
    # first-order lag (tau=0.8 s) so speed/turn changes are smooth, accel finite
    a = DT / (0.8 + DT)
    spd = np.zeros(N); w = np.zeros(N)
    for i in range(1, N):
        spd[i] = spd[i-1] + a * (tgt_v[i] - spd[i-1])
        w[i]   = w[i-1]   + a * (tgt_w[i] - w[i-1])
    psi = np.zeros(N); pos = np.zeros((N, 2)); vel = np.zeros((N, 2))
    for i in range(N - 1):
        psi[i+1] = psi[i] + w[i] * DT
        pm = psi[i] + 0.5 * w[i] * DT
        vel[i] = spd[i] * np.array([np.cos(psi[i]), np.sin(psi[i])])
        pos[i+1] = pos[i] + spd[i] * np.array([np.cos(pm), np.sin(pm)]) * DT
    vel[-1] = spd[-1] * np.array([np.cos(psi[-1]), np.sin(psi[-1])])
    acc_b = np.zeros((N, 2))
    acc_w = np.gradient(vel, DT, axis=0)
    for i in range(N):
        c, s = np.cos(psi[i]), np.sin(psi[i])
        acc_b[i] = [c * acc_w[i,0] + s * acc_w[i,1], -s * acc_w[i,0] + c * acc_w[i,1]]
    return dict(pos=pos, vel=vel, psi=psi, omega=w, acc_body=acc_b, speed=spd)

TRUTH = build_truth()

# ---------------- satellites ----------------
_AZ = np.deg2rad([15, 60, 110, 160, 205, 250, 295, 340, 85])
_EL = np.deg2rad([35, 55, 70, 30, 50, 65, 40, 60, 45])
SAT_U = np.stack([np.cos(_EL)*np.cos(_AZ), np.cos(_EL)*np.sin(_AZ), np.sin(_EL)], axis=1)
SAT_P = SAT_U * 2.02e7
NSAT = len(SAT_P)

def visible_mask(scn, t, rng):
    if scn == "forest" and ((100 <= t <= 170) or (240 <= t <= 290)):
        return np.zeros(NSAT, bool)
    if scn in ("open", "stress"):
        return np.ones(NSAT, bool)
    if scn == "forest":
        m = np.ones(NSAT, bool)
        if rng.random() < 0.3: m[rng.integers(NSAT)] = False
        return m
    # canyon: rotating blocked sector 160 deg wide
    cen = np.deg2rad((t * 2.25) % 360.0)
    d = np.angle(np.exp(1j * (_AZ - cen)))
    m = np.abs(d) > np.deg2rad(80.0)
    if m.sum() < 3:  # keep the 3 highest-elevation unblocked-ish sats
        order = np.argsort(-_EL)
        m[:] = False; m[order[:3]] = True
    if m.sum() > 6:
        idx = np.where(m)[0]; m[idx[6:]] = False
    return m

def gen_epochs(scn, seed):
    """GNSS epochs: list per epoch of dict(t_idx, vis, pr, sigma_pr, fix, fix_R)."""
    rng = np.random.default_rng(1000 + seed)
    cb0 = rng.normal(0, 30.0)                       # receiver clock bias (m)
    sig = {"open": 1.5, "stress": 1.5, "canyon": 4.0, "forest": 2.0}[scn]
    eps = []
    for e in range(0, N, EPOCH):
        t = e * DT
        cb = cb0 + 2.0 * t + 5.0 * np.sin(2 * np.pi * t / 300.0)
        vis = visible_mask(scn, t, rng)
        pr = np.full(NSAT, np.nan)
        for i in np.where(vis)[0]:
            r = np.linalg.norm(SAT_P[i] - [TRUTH["pos"][e,0], TRUTH["pos"][e,1], 0.0])
            v = r + cb + rng.normal(0, sig)
            if scn == "canyon" and rng.random() < 0.35:
                v += rng.uniform(5.0, 25.0)         # NLOS bias
            pr[i] = v
        fix, fix_R = ls_fix(pr, vis, sig)
        eps.append(dict(k=e, vis=vis, pr=pr, sig=sig, fix=fix, fix_R=fix_R))
    return eps

def ls_fix(pr, vis, sig):
    """Least-squares 2-D + clock fix from pseudoranges; None if <4 sats."""
    idx = np.where(vis)[0]
    if len(idx) < 4: return None, None
    x = np.zeros(3)
    for _ in range(8):
        J, res = [], []
        for i in idx:
            d = SAT_P[i] - [x[0], x[1], 0.0]; r = np.linalg.norm(d)
            J.append([-d[0]/r, -d[1]/r, 1.0]); res.append(pr[i] - (r + x[2]))
        J = np.array(J); res = np.array(res)
        try: dx = np.linalg.solve(J.T @ J, J.T @ res)
        except np.linalg.LinAlgError: return None, None
        x += dx
        if np.linalg.norm(dx[:2]) < 1e-6: break
    try: cov = sig**2 * np.linalg.inv(J.T @ J)
    except np.linalg.LinAlgError: return None, None
    return x[:2].copy(), cov[:2, :2].copy()

# ---------------- IMU data ----------------
def gen_imu(seed):
    rng = np.random.default_rng(5000 + seed)
    bg_t = rng.normal(0, BG_SD)
    ba_t = rng.normal(0, BA_SD, 2)
    t = np.arange(N) * DT
    gait = 0.6 * np.sin(2 * np.pi * 1.7 * t) * np.clip(TRUTH["speed"] / 1.3, 0, 1)
    acc_m = TRUTH["acc_body"] + ba_t + rng.normal(0, SIG_A, (N, 2))
    acc_m[:, 1] += gait                       # lateral gait sway while walking
    gyro_m = TRUTH["omega"] + bg_t + rng.normal(0, SIG_G, N)
    return acc_m, gyro_m, ba_t, bg_t

# ---------------- mechanisation + EKF core ----------------
def mech(x, a_m, g_m, dt=DT):
    psi = x[4] + (g_m - x[5]) * dt
    ab = a_m - x[6:8]
    c, s = np.cos(x[4]), np.sin(x[4])
    aw = np.array([c * ab[0] - s * ab[1], s * ab[0] + c * ab[1]])
    xn = x.copy()
    xn[0:2] = x[0:2] + x[2:4] * dt + 0.5 * aw * dt * dt
    xn[2:4] = x[2:4] + aw * dt
    xn[4] = (psi + np.pi) % (2 * np.pi) - np.pi
    return xn

def jac_F(x, a_m):
    ab = a_m - x[6:8]
    c, s = np.cos(x[4]), np.sin(x[4])
    aw = np.array([c * ab[0] - s * ab[1], s * ab[0] + c * ab[1]])
    Phi = np.zeros((8, 8))
    Phi[0, 2] = 1.0; Phi[1, 3] = 1.0
    Phi[2, 4] = -aw[1]; Phi[2, 6] = -c; Phi[2, 7] = s
    Phi[3, 4] =  aw[0]; Phi[3, 6] = -s; Phi[3, 7] = -c
    Phi[4, 5] = -1.0
    return np.eye(8) + Phi * DT

QD = np.diag([(SIG_A * DT**2 / 2)**2] * 2 + [(SIG_A * DT)**2] * 2 +
             [(SIG_G * DT)**2, (1e-4 * np.sqrt(DT))**2] +
             [(5e-3 * np.sqrt(DT))**2] * 2)

def ekf_update(x, P, z, H, R):
    S = H @ P @ H.T + R
    K = np.linalg.solve(S.T, (P @ H.T).T).T
    x = x + K @ (z - H @ x)
    P = (np.eye(len(x)) - K @ H) @ P
    return x, 0.5 * (P + P.T)

H_POS = np.zeros((2, 8)); H_POS[0, 0] = 1.0; H_POS[1, 1] = 1.0
H_VEL = np.zeros((2, 8)); H_VEL[0, 2] = 1.0; H_VEL[1, 3] = 1.0

def init_state(scn, fix0, rng):
    if scn == "stress":
        pe = rng.normal(0, 1, 2); pe = pe / np.linalg.norm(pe) * 15.0
        p_sd, h_err, h_sd = 15.0, np.deg2rad(25.0), np.deg2rad(30.0)
    else:
        pe = rng.normal(0, 3.0, 2); p_sd = 5.0
        h_err = rng.normal(0, np.deg2rad(5.0)); h_sd = np.deg2rad(10.0)
    x = np.zeros(8)
    x[0:2] = fix0 + pe
    x[4] = h_err
    P = np.diag([p_sd**2, p_sd**2, 0.5**2, 0.5**2, h_sd**2,
                 0.01**2, 0.1**2, 0.1**2])
    return x, P

def run_lc(scn, acc_m, gyro_m, eps, seed, zupt=False, adapt=False, store=False):
    """Loosely-coupled EKF family. Returns (pos_est, store_dict_or_None)."""
    rng = np.random.default_rng(9000 + seed)
    x, P = init_state(scn, eps[0]["fix"], rng)
    ep = {e["k"]: e for e in eps}
    est = np.zeros((N, 2)); lam = 1.0
    Xs = Ps = Fs = Xp = Pp = None
    if store:
        Xs = np.zeros((N, 8)); Ps = np.zeros((N, 8, 8)); Fs = np.zeros((N, 8, 8))
        Xp = np.zeros((N, 8)); Pp = np.zeros((N, 8, 8))
        Fs[0] = np.eye(8); Xp[0] = x; Pp[0] = P
    win_a, win_g = [], []
    for k in range(N):
        if k > 0:
            F = jac_F(x, acc_m[k-1])
            x = mech(x, acc_m[k-1], gyro_m[k-1])
            P = F @ P @ F.T + QD
            if store: Fs[k] = F; Xp[k] = x; Pp[k] = P
        if zupt:
            win_a.append(acc_m[k]); win_g.append(gyro_m[k])
            if len(win_a) > 10: win_a.pop(0); win_g.pop(0)
            if len(win_a) == 10:
                wa = np.array(win_a); wg = np.array(win_g)
                _fire = (wa.std(axis=0).max() < 0.20 and np.abs(wg).std() < 0.01
                        and np.abs(wg).mean() < 0.03)
                if ORACLE_ZUPT: _fire = bool(TRUTH["speed"][k] < 0.01)
                LC_LOG.append((k, bool(_fire)))
                if _fire:
                    x, P = ekf_update(x, P, np.zeros(2), H_VEL, np.eye(2) * 0.02**2)
                    Hg = np.zeros((1, 8)); Hg[0, 5] = 1.0
                    x, P = ekf_update(x, P, np.array([gyro_m[k]]), Hg,
                                      np.array([[SIG_G**2]]))
        if k in ep and ep[k]["fix"] is not None:
            R = ep[k]["fix_R"] * lam
            S = H_POS @ P @ H_POS.T + R
            innov = ep[k]["fix"] - x[0:2]
            x, P = ekf_update(x, P, ep[k]["fix"], H_POS, R)
            if adapt:
                emp = np.outer(innov, innov) / max(S[0, 0] + S[1, 1], 1e-9)
                lam = float(np.clip(0.9 * lam + 0.1 * (emp[0, 0] + emp[1, 1]), 0.5, 8.0))
        est[k] = x[0:2]
        if store: Xs[k] = x; Ps[k] = P
    return est, (dict(X=Xs, P=Ps, F=Fs, Xp=Xp, Pp=Pp) if store else None)

def rts_smooth(st):
    """RTS backward pass. Store holds posterior X/P, predicted Xp/Pp, and
    Fs[k] = Jacobian of the transition from step k-1 to step k."""
    X, P, F, Xp, Pp = st["X"], st["P"], st["F"], st["Xp"], st["Pp"]
    Xs = X.copy(); Ps = P.copy()
    for k in range(N - 2, -1, -1):
        G = np.linalg.solve(Pp[k+1].T, (P[k] @ F[k+1].T).T).T
        diff = Xs[k+1] - Xp[k+1]
        diff[4] = (diff[4] + np.pi) % (2 * np.pi) - np.pi  # heading is circular
        Xs[k] = X[k] + G @ diff
        Ps[k] = P[k] + G @ (Ps[k+1] - Pp[k+1]) @ G.T
    return Xs[:, 0:2]

# ---------------- UKF (sigma-point, Crassidis-style) ----------------
def _sqrtm(M):
    M = 0.5 * (M + M.T)
    try: return np.linalg.cholesky(M)
    except np.linalg.LinAlgError:
        w, V = np.linalg.eigh(M)
        return V @ np.diag(np.sqrt(np.clip(w, 0, None)))

def run_ukf(scn, acc_m, gyro_m, eps, seed, alpha=0.5, beta=2.0, kappa=0.0):
    rng = np.random.default_rng(9000 + seed)
    x, P = init_state(scn, eps[0]["fix"], rng)
    ep = {e["k"]: e for e in eps}
    n = 8
    lam = alpha**2 * (n + kappa) - n
    wm = np.full(2 * n + 1, 1.0 / (2 * (n + lam))); wc = wm.copy()
    wm[0] = lam / (n + lam); wc[0] = wm[0] + (1 - alpha**2 + beta)
    def points(x, P):
        S = _sqrtm((n + lam) * P)
        X = np.tile(x, (2 * n + 1, 1))
        X[1:n+1] += S.T; X[n+1:] -= S.T
        return X
    est = np.zeros((N, 2))
    for k in range(N):
        if k > 0:
            X = points(x, P)
            Xp_ = np.array([mech(Xi, acc_m[k-1], gyro_m[k-1]) for Xi in X])
            x = wm @ Xp_
            # heading mean on the circle: linear averaging of wrapped
            # headings corrupts the mean whenever sigma points straddle
            # the +-pi cut (found by external review 2026-11-04; see
            # docs/audit-response-2026-11-04.md, fifth review)
            dpsi = (Xp_[:, 4] - Xp_[0, 4] + np.pi) % (2 * np.pi) - np.pi
            x[4] = (Xp_[0, 4] + wm @ dpsi + np.pi) % (2 * np.pi) - np.pi
            d = Xp_ - x; d[:, 4] = (d[:, 4] + np.pi) % (2 * np.pi) - np.pi
            P = (d * wc[:, None]).T @ d + QD
            P = 0.5 * (P + P.T)
        if k in ep and ep[k]["fix"] is not None:
            X = points(x, P)
            Z = X[:, 0:2]
            zm = wm @ Z
            dz = Z - zm; dx = X - x
            dx[:, 4] = (dx[:, 4] + np.pi) % (2 * np.pi) - np.pi
            Szz = (dz * wc[:, None]).T @ dz + ep[k]["fix_R"]
            Txz = (dx * wc[:, None]).T @ dz
            K = np.linalg.solve(Szz.T, Txz.T).T
            x = x + K @ (ep[k]["fix"] - zm)
            x[4] = (x[4] + np.pi) % (2 * np.pi) - np.pi
            P = P - K @ Szz @ K.T
            P = 0.5 * (P + P.T)
        est[k] = x[0:2]
    return est

TC_LOG = []
LC_LOG = []
ORACLE_ZUPT = False

# ---------------- TC-EKF (tightly coupled, Soloviev-style) ----------------
def run_tc(scn, acc_m, gyro_m, eps, seed, clock_drift=False):
    """Tightly-coupled EKF. clock_drift=False: receiver clock = bias state
    with random-walk model (the simplified textbook version).
    clock_drift=True: standard two-state clock (bias + drift)."""
    rng = np.random.default_rng(9000 + seed)
    x8, P8 = init_state(scn, eps[0]["fix"], rng)
    ns = 10 if clock_drift else 9
    x = np.zeros(ns); x[:8] = x8
    P = np.zeros((ns, ns)); P[:8, :8] = P8; P[8, 8] = 30.0**2
    Q = np.zeros((ns, ns)); Q[:8, :8] = QD
    if clock_drift:
        P[9, 9] = 1.0**2                       # drift sd 1 m/s prior
        Q[8, 8] = 0.1**2 * DT                  # bias: small RW, drift carries ramp
        Q[9, 9] = 0.02**2 * DT                 # drift random walk
    else:
        Q[8, 8] = 2.0**2 * DT                  # bias must random-walk the ramp
    ep = {e["k"]: e for e in eps}
    est = np.zeros((N, 2))
    for k in range(N):
        if k > 0:
            F = np.eye(ns); F[:8, :8] = jac_F(x[:8], acc_m[k-1])
            xn = x.copy(); xn[:8] = mech(x[:8], acc_m[k-1], gyro_m[k-1])
            if clock_drift: xn[8] = x[8] + x[9] * DT; F[8, 9] = DT
            x = xn; P = F @ P @ F.T + Q
        if k in ep:
            e = ep[k]
            _acc = [0]
            for i in np.where(e["vis"])[0]:
                d = SAT_P[i] - np.array([x[0], x[1], 0.0])
                r = np.linalg.norm(d)
                H = np.zeros((1, ns)); H[0, 0] = -d[0] / r; H[0, 1] = -d[1] / r
                H[0, 8] = 1.0
                innov = e["pr"][i] - (r + x[8])
                S = float((H @ P @ H.T)[0, 0]) + e["sig"]**2
                if abs(innov) <= 4.0 * np.sqrt(S):   # gating, as in practice
                    x, P = _scalar_update(x, P, innov, H, e["sig"]**2)
                    _acc[0] += 1
            TC_LOG.append((k, _acc[0], int(e["vis"].sum())))
        est[k] = x[0:2]
    return est

def _scalar_update(x, P, innov, H, R):
    S = float((H @ P @ H.T)[0, 0]) + R
    K = (P @ H.T) / S
    x = x + (K[:, 0] * innov)
    P = (np.eye(len(x)) - K @ H) @ P
    return x, 0.5 * (P + P.T)

# ---------------- baselines ----------------
def run_gnss(eps):
    est = np.zeros((N, 2)); last = np.zeros(2)
    ep = {e["k"]: e for e in eps}
    for k in range(N):
        if k in ep and ep[k]["fix"] is not None: last = ep[k]["fix"]
        est[k] = last
    return est

def run_ins(scn, acc_m, gyro_m, eps, seed):
    rng = np.random.default_rng(9000 + seed)
    x, _ = init_state(scn, eps[0]["fix"], rng)
    est = np.zeros((N, 2))
    for k in range(N):
        if k > 0: x = mech(x, acc_m[k-1], gyro_m[k-1])
        est[k] = x[0:2]
    return est

# ---------------- metrics + main ----------------
def challenge_mask(scn, eps):
    m = np.zeros(N, bool)
    if scn == "open": m[:] = True
    elif scn == "stress": m[:600] = True
    elif scn == "forest":
        t = np.arange(N) * DT
        m = ((t >= 100) & (t <= 170)) | ((t >= 240) & (t <= 290))
    elif scn == "canyon":
        for e in eps:
            if e["vis"].sum() < 5: m[e["k"]:e["k"] + EPOCH] = True
    return m

def metrics(est, mask):
    err = np.linalg.norm(est - TRUTH["pos"], axis=1)
    return dict(rmse=float(np.sqrt((err**2).mean())),
                chal=float(np.sqrt((err[mask]**2).mean())) if mask.any() else float("nan"),
                max=float(err.max()), final=float(err[-10:].mean()))

METHODS = ["GNSS", "INS", "LC-EKF", "TC-EKF", "TC-EKF-CD", "LC-UKF",
           "ZUPT-EKF", "ADAPT-EKF", "RTS-SMOOTH"]

def run_one(scn, seed):
    acc_m, gyro_m, _, _ = gen_imu(seed)
    eps = gen_epochs(scn, seed)
    out = {}; tim = {}
    def timed(name, fn):
        t0 = time.perf_counter(); out[name] = fn(); tim[name] = time.perf_counter() - t0
    timed("GNSS", lambda: run_gnss(eps))
    timed("INS", lambda: run_ins(scn, acc_m, gyro_m, eps, seed))
    timed("LC-EKF", lambda: run_lc(scn, acc_m, gyro_m, eps, seed)[0])
    timed("TC-EKF", lambda: run_tc(scn, acc_m, gyro_m, eps, seed))
    timed("TC-EKF-CD", lambda: run_tc(scn, acc_m, gyro_m, eps, seed,
                                      clock_drift=True))
    timed("LC-UKF", lambda: run_ukf(scn, acc_m, gyro_m, eps, seed))
    timed("ZUPT-EKF", lambda: run_lc(scn, acc_m, gyro_m, eps, seed, zupt=True)[0])
    timed("ADAPT-EKF", lambda: run_lc(scn, acc_m, gyro_m, eps, seed, adapt=True)[0])
    def rts():
        est0, st = run_lc(scn, acc_m, gyro_m, eps, seed, store=True)
        return rts_smooth(st)
    timed("RTS-SMOOTH", rts)
    return out, tim, eps

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results")
    ap.add_argument("--seeds", type=int, default=16)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    seeds = 3 if a.quick else a.seeds
    import os; os.makedirs(a.out, exist_ok=True)
    summary = {}; example = None
    for scn in ["open", "canyon", "forest", "stress"]:
        agg = {m: [] for m in METHODS}; tms = {m: 0.0 for m in METHODS}
        for seed in range(seeds):
            out, tim, eps = run_one(scn, seed)
            mask = challenge_mask(scn, eps)
            for m in METHODS:
                agg[m].append(metrics(out[m], mask)); tms[m] += tim[m]
            if scn == "forest" and seed == 0:
                example = dict(
                    truth=TRUTH["pos"][::10].tolist(),
                    est={m: out[m][::10].tolist() for m in
                         ["GNSS", "LC-EKF", "TC-EKF-CD", "LC-UKF", "ZUPT-EKF"]},
                    err={m: np.linalg.norm(out[m] - TRUTH["pos"], axis=1)[::5].tolist()
                         for m in ["GNSS", "LC-EKF", "TC-EKF", "TC-EKF-CD",
                                   "ZUPT-EKF", "INS"]})
            print(f"{scn} seed {seed} done", flush=True)
        summary[scn] = {}
        for m in METHODS:
            rows = agg[m]
            summary[scn][m] = dict(
                rmse_mean=float(np.mean([r["rmse"] for r in rows])),
                rmse_std=float(np.std([r["rmse"] for r in rows])),
                chal_mean=float(np.mean([r["chal"] for r in rows])),
                chal_std=float(np.std([r["chal"] for r in rows])),
                max_mean=float(np.mean([r["max"] for r in rows])),
                final_mean=float(np.mean([r["final"] for r in rows])),
                ms_per_step=float(tms[m] / (seeds * N) * 1000.0))
    with open(f"{a.out}/results.json", "w") as f:
        json.dump(dict(summary=summary, example=example,
                       config=dict(seeds=seeds, dt=DT, t_end=T_END,
                                   sig_a=SIG_A, sig_g=SIG_G)), f, indent=1)
    with open(f"{a.out}/summary.csv", "w") as f:
        f.write("scenario,method,rmse_mean,rmse_std,chal_mean,chal_std,max_mean,final_mean,ms_per_step\n")
        for scn, ms in summary.items():
            for m, v in ms.items():
                f.write(f"{scn},{m},{v['rmse_mean']:.3f},{v['rmse_std']:.3f},"
                        f"{v['chal_mean']:.3f},{v['chal_std']:.3f},{v['max_mean']:.3f},"
                        f"{v['final_mean']:.3f},{v['ms_per_step']:.4f}\n")
    print("WROTE", a.out)

if __name__ == "__main__":
    main()
