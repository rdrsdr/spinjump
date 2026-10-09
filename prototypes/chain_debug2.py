import math, sys
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    for every in (1, 4):
        s = Simulation(load_config(sets=[f"rope.coil_update_every_steps={every}"]))
        r = s.rope
        worst = 0.0
        for i in range(8000):
            F = 1000.0 * (1 + 0.5 * math.sin(i * 0.25e-3 * 20))   # 2 s com força oscilando
            ang = -0.6  # vão inclinado para baixo
            r._step_chain(F * math.cos(ang) * r.sw, F * math.sin(ang), 9.81)
            v = np.hypot(r.vx[:r.k+1], r.vz[:r.k+1]).max()
            worst = max(worst, v)
        print(f"every={every}: vmax pior={worst:.3f} m/s  drop={r.coil_drop():.3f} m  T_anc={r._T_anchor:.1f}")
