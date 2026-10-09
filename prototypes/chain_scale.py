import math, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation

def one(args):
    every, scale = args
    s = Simulation(load_config(sets=[f"rope.coil_update_every_steps={every}"]))
    r = s.rope; r.mass_scale = scale
    worst = 0.0; ef = 0.0
    for i in range(8000):
        F = 1000.0 * (1 + 0.5 * math.sin(i * 0.25e-3 * 20))
        ang = -0.6
        e, _, _ = r._step_chain(F * math.cos(ang) * r.sw, F * math.sin(ang), 9.81)
        ef += e
        worst = max(worst, float(np.hypot(r.vx[:r.k+1], r.vz[:r.k+1]).max()))
    return f"every={every} escala={scale:5.0f}: vmax={worst:8.3f} m/s drop={r.coil_drop():.3f} m atrito={ef:8.1f} J"

if __name__ == "__main__":
    jobs = [(e, sc) for e in (1, 4) for sc in (1, 30, 100, 300, 1000)]
    with ProcessPoolExecutor(10) as ex:
        for line in ex.map(one, jobs): print(line, flush=True)
