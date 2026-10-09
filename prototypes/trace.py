"""Imprime uma série resumida (z, voltas, tração...) para inspeção."""
import sys, math
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation, TELEMETRY_FIELDS
sets = [a for a in sys.argv[1].split(";") if a]
every = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
s = Simulation(load_config(sets=sets)).run()
S = np.array(s.samples, dtype=float)
F = {k: i for i, k in enumerate(TELEMETRY_FIELDS)}
cols = ["t", "z", "rho", "speed", "theta_turns", "wound_turns", "stored_turns", "geodesic_turns", "rest_len", "path_len", "tension", "kink_deg", "wall_dist", "e_total", "w_drag", "w_rope_damp", "w_peel"]
print(" ".join(f"{c:>10s}" for c in cols))
last = -1e9
for r in S:
    if r[0] - last >= every - 1e-9:
        last = r[0]
        print(" ".join(f"{r[F[c]]:10.3f}" for c in cols))
print("outcome", s.outcome, "events", [(e["surface"], e["t_start"], e["v_normal_in_ms"], e["decel_peak_g"]) for e in s.impacts.events][:12])
