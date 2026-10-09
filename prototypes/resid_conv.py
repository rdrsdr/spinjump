import sys, json
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation
def one(sets):
    s = Simulation(load_config(sets=sets + ["solver.max_time_s=20"])); s.run()
    return dict(sets=sets, resid=round(s.tr.e_flight_residual_max), E0=round(s.tr.energy0), numeric=round(s.rope.e_numeric),
                fric=round(s.tr.w_coil_fric), out=round(s.tr.w_chain_out), damp=round(s.tr.w_rope_damp), peel=round(s.tr.w_peel))
if __name__ == "__main__":
    vs = [json.loads(a) for a in sys.argv[1:]]
    with ProcessPoolExecutor(6) as ex:
        for r in ex.map(one, vs): print(json.dumps(r), flush=True)
