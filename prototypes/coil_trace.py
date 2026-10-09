import sys, json, math
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    sets = json.loads(sys.argv[1]); every = float(sys.argv[2]); tmax = float(sys.argv[3])
    s = Simulation(load_config(sets=sets + [f"solver.max_time_s={tmax}"]))
    nxt = 0.0
    print(" t      T     Tanc   drop   fric   peel   resid   k    kink  z_obj  maxv_chain")
    while s.step():
        t = s.d.time
        if t >= nxt:
            nxt += every
            r, tr = s.rope, s.tr
            e_obj = float(s.d.energy[0] + s.d.energy[1]); rs = r.s
            pred = (tr.energy0 + tr.w_drag + tr.w_rope_dist + tr.w_launch - tr.w_rope_damp - tr.w_peel - tr.w_coil_fric - tr.w_chain_out - rs.elastic_energy - rs.chain_energy)
            kend = r.k + 1
            mv = float(np.max(np.hypot(r.vx[:kend+1], r.vz[:kend+1])))
            print(f"{t:5.2f} {rs.tension:7.0f} {rs.tension_anchor:6.1f} {rs.coil_drop:6.3f} {tr.w_coil_fric:7.0f} {tr.w_peel:6.0f} {e_obj-pred:7.0f} {r.k:4d} {rs.kink_deg:5.1f} {s.d.xipos[1][2]:6.2f} {mv:7.3f}")
