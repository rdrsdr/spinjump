import sys, json, math
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    extra = json.loads(sys.argv[1])
    cfg = load_config(sets=["object.type=sandbag", "object.height_m=1.0", "object.radius_m=0.2", "object.attach_height_fraction=0.5",
        "rope.length_m=60", "air.enabled=false", "wind.enabled=false", "launch.speed_ms=4", "launch.azimuth_deg=90",
        "launch.elevation_deg=0", "solver.max_time_s=4"] + extra)
    s = Simulation(cfg); s.m.opt.gravity[:] = 0
    nxt = 0
    while s.step():
        if s.d.time >= nxt:
            nxt += 0.5; r = s.rope
            print(f"t={s.d.time:4.2f} ke={s.d.energy[1]:9.1f} T={r.s.tension:9.1f} chainE={r.s.chain_energy:9.2f} k={r.k} vmax={np.hypot(r.vx, r.vz).max():8.3f} drop={r.s.coil_drop:.4f}", flush=True)
