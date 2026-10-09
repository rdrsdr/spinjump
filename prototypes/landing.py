"""Inspeção detalhada do pouso: velocidade, rotação, forças e eventos."""
import sys, math
import numpy as np
import mujoco
from spinjump.config import load_config
from spinjump.sim import Simulation
sets = [a for a in sys.argv[1].split(";") if a]
s = Simulation(load_config(sets=sets))
t_g = None
rows = []
while s.step():
    if s.tr.first_ground_t is not None and t_g is None:
        t_g = s.d.time
    if t_g is not None and s.step_count % 20 == 0:
        v, w = s._body_velocity()
        com = s.d.xipos[s.b.body_id]
        zax = s.d.xmat[s.b.body_id].reshape(3,3)[:,2]
        rows.append((s.d.time, com[2], np.linalg.norm(v[:2]), v[2], np.linalg.norm(w), zax[2], s.impacts.current_fn['ground'], s.rope.s.tension, s.rope.s.slack))
    if t_g is not None and s.d.time > t_g + float(sys.argv[2] if len(sys.argv)>2 else 3):
        break
s.finish()
print("    t      zcom   vh     vz    |w|   bodyz_up   Fn_ground   T   slack")
for r in rows[::int(sys.argv[3]) if len(sys.argv)>3 else 5]:
    print(" ".join(f"{x:8.3f}" for x in r))
for e in s.impacts.events[:20]:
    print(e["surface"], e["t_start"], e["duration_s"], e["geoms"], e["v_normal_in_ms"], e["speed_in_ms"], e["force_normal_peak_raw_N"], e["decel_peak_g"], e["impulse_normal_impact_Ns"])
