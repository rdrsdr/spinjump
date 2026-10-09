import sys, json, time
import numpy as np
import spinjump.surface_rope as sr
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "nostack":
        sr.SurfaceRope._stack = lambda self, PX, PZ, b: None
    s = Simulation(load_config(sets=["solver.max_time_s=10"] + sys.argv[2:]))
    r = s.rope; nxt = 0
    while s.step():
        if s.d.time >= nxt:
            nxt += 1.0
            kend = r.k
            v = np.hypot(r.vx[:kend+1], r.vz[:kend+1])
            print(f"t={s.d.time:5.2f} T={r.s.tension:7.0f} drop={r.s.coil_drop:6.3f} vmax={v.max():8.3f} fric={s.tr.w_coil_fric:9.0f} k={r.k} kink={r.s.kink_deg:5.1f} z={s.d.xipos[1][2]:6.2f}", flush=True)
