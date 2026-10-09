"""Sensibilidade do modelo de espiras deslizantes (10 s de voo)."""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation

def one(sets):
    s = Simulation(load_config(sets=sets + ["solver.max_time_s=10"]))
    t0 = time.perf_counter(); s.run(); w = time.perf_counter() - t0
    tr = s.tr
    return dict(sets=sets, us=round(w / s.step_count * 1e6), turns=round(s.object_turns(), 3),
                wound=round(s.rope.wound_turns, 3), drop=round(tr.coil_drop_max, 3), fric=round(tr.w_coil_fric),
                peel=round(tr.w_peel), Tmax=round(tr.t_max), z=round(float(s.d.xipos[1][2]), 2),
                resid=round(tr.e_flight_residual_max), out=round(tr.w_chain_out))

if __name__ == "__main__":
    variants = [json.loads(a) for a in sys.argv[1:]]
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(one, variants):
            print(json.dumps(r), flush=True)
