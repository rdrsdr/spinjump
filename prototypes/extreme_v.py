import math, numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    cfg = load_config(sets=["object.type=sandbag", "object.height_m=1.0", "object.radius_m=0.2", "object.attach_height_fraction=0.5",
        "rope.length_m=60", "air.enabled=false", "wind.enabled=false", "launch.speed_ms=4", "launch.azimuth_deg=90",
        "launch.elevation_deg=0", "solver.max_time_s=4", "rope.wall_friction=0.0", "rope.axial_EA_N=5.0e6", "rope.linear_density_kg_m=0", "rope.helix_vertical=up"])
    s = Simulation(cfg); s.m.opt.gravity[:] = 0; r = s.rope
    for i in range(4000):
        ok = s.step()
        if i % 100 == 0 or not ok:
            print(i, round(s.d.time,4), "T", round(r.s.tension,1), "vmax", round(float(np.hypot(r.vx[:r.k+2], r.vz[:r.k+2]).max()),3), "k", r.k, "w", round(r.w,3), "ke", round(s.d.energy[1],1), s.status, s.failure, flush=True)
        if not ok: break
