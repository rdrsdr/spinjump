import math, numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    for mu in (0.2, 0.4):
        r = Simulation(load_config(sets=[f"rope.wall_friction={mu}"])).rope
        for i in range(8000):
            F = 1500.0 * i / 8000            # rampa contínua: mede-se ainda escorregando
            r._step_chain(F * r.sw, 0.0, 0.0)
        k = r.k
        L = np.hypot(np.diff(r.x[:k + 1]), np.diff(r.z[:k + 1]))
        T = r.p.EA * np.maximum(L - r.ds, 0) / r.ds
        th = r.sw * r.x[1:k + 1] / r.p.rc
        # inclinação local por blocos de 20 segmentos a partir da ponta
        print(f"μ={mu} janela {r.window_nodes} nós; T ponta {T[-1]:.0f} N, nós com T>60: {(T>60).sum()}")
        for a in range(T.size - 1, max(T.size - 260, 20), -20):
            seg = slice(a - 20, a)
            if T[seg].min() > 25:
                sl = np.polyfit(th[seg], np.log(T[seg]), 1)[0]
                lz = np.diff(L[seg]).mean()
                print(f"   segs {a-20:4d}-{a:4d}: T {T[a-20]:7.1f}..{T[a-1]:7.1f}  inclinação {sl:.4f}  ε médio {np.mean(L[seg]/r.ds-1):.4f}")
