"""Estudo de sensibilidade do pouso a dt e solref (artefato de contato vs física)."""
import sys, json, math
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation

def one(sets):
    s = Simulation(load_config(sets=sets)).run()
    tr = s.tr
    g = [e for e in s.impacts.events if e["surface"] == "ground"]
    return dict(sets=sets, outcome=s.outcome, t_end=round(s.d.time, 2), n_ground=len(g),
                lift_max=round(tr.max_lift_after_ground, 3), hops=tr.ground_hops, eres=round(tr.e_flight_residual_max,1), slip=round(tr.coil_slip_ratio_max,2),
                gmax=round(max([e["decel_peak_g"] for e in g], default=0), 1),
                imp1=g[0]["impulse_normal_impact_Ns"] if g else None, v_ground=round(tr.first_ground_speed or 0, 2),
                slide=round(tr.slide_path, 2), t_ground=round(tr.first_ground_t or 0, 2),
                rest_after=round(s.d.time - (tr.first_ground_t or 0), 2), Tmax=round(tr.t_max))

if __name__ == "__main__":
    variants = [json.loads(a) for a in sys.argv[1:]]
    with ProcessPoolExecutor(max_workers=8) as ex:
        for r in ex.map(one, variants):
            print(json.dumps(r), flush=True)
