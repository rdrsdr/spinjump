"""Série da fase no solo (velocidade, rotação, folga do ponto mais baixo)."""
import sys
import numpy as np
from spinjump.config import load_config
from spinjump.sim import Simulation, TELEMETRY_FIELDS
sets = [a for a in sys.argv[1].split(";") if a]
every = float(sys.argv[2])
s = Simulation(load_config(sets=sets)).run()
S = np.array(s.samples); F = {k: i for i, k in enumerate(TELEMETRY_FIELDS)}
tg = s.tr.first_ground_t
cols = ["t","x","y","z","speed","omega","lowest_z","theta_turns","wound_turns","tension","elongation","slack","ground_fn","phase"]
print(" ".join(f"{c:>9s}" for c in cols)); last=-1e9
for r in S:
    if r[0] >= tg - 0.1 and r[0]-last >= every:
        last=r[0]; print(" ".join(f"{r[F[c]]:9.3f}" for c in cols))
print(s.outcome, "rest_hold", s.tr.rest_hold, "lift", s.tr.max_lift_after_ground)
