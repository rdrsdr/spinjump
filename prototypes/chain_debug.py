"""Cadeia isolada: estabilidade sem carga e com puxão na ponta."""
import math, sys
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation

if __name__ == "__main__":
    s = Simulation(load_config(sets=["rope.coil_update_every_steps=1"]))
    r = s.rope
    print("k", r.k, "x0", r.x[0], "z", r.z[:3], "m", r.m, "ds", r.ds, "window", r.window_nodes)
    for F in (0.0, 300.0, 1000.0):
        z0 = r.z[:r.k + 1].copy()
        for i in range(400):
            ef, E, Ta = r._step_chain(F * r.lay[0], F * r.lay[1] - F * 0.0, 9.81)
        dz = r.z[:r.k + 1] - z0
        v = np.hypot(r.vx[:r.k + 1], r.vz[:r.k + 1])
        print(f"F={F}: max|dz|={np.abs(dz).max():.3e} vmax={v.max():.3e} E={E:.1f} Tanc={Ta:.2f} fric={ef:.3e}")
