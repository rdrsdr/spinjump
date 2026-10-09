import sys, json, math
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    sets = json.loads(sys.argv[1])
    s = Simulation(load_config(sets=sets)); r = s.rope; nxt = None
    while s.step():
        tg = s.tr.first_ground_t
        if tg is not None:
            if nxt is None: nxt = tg
            if s.d.time >= nxt:
                nxt += 0.5
                com = s.d.xipos[1]; v, _ = s._body_velocity()
                print(f"t={s.d.time:6.2f} vh={math.hypot(v[0],v[1]):5.2f} rho={math.hypot(com[0],com[1]):6.2f} T={r.s.tension:6.0f} slack={max(-r.s.delta,0):6.3f} sigD={r.sig_D:6.2f} zD={r.s.D[2]:6.2f} drop={r.s.coil_drop:6.2f} path={s.tr.slide_path:6.2f}", flush=True)
    print("fim", s.outcome, round(s.d.time, 2), "slide", round(s.tr.slide_path, 2))
