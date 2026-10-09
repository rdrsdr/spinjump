import sys, json
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation

def one(sets):
    s = Simulation(load_config(sets=sets + ["solver.max_time_s=6"]))
    E0 = s.tr.energy0; r = s.rope
    s.run()
    tr, rs = s.tr, r.s
    e_obj = float(s.d.energy[0] + s.d.energy[1])
    terms = dict(E0=E0, e_obj=e_obj, el=rs.elastic_energy, chain=rs.chain_energy, drag=tr.w_drag, dist=tr.w_rope_dist,
                 damp=tr.w_rope_damp, peel=tr.w_peel, fric=tr.w_coil_fric, out=tr.w_chain_out, numeric=getattr(r, "e_numeric", 0))
    resid = e_obj + rs.elastic_energy + rs.chain_energy - (E0 + tr.w_drag + tr.w_rope_dist - tr.w_rope_damp - tr.w_peel - tr.w_coil_fric - tr.w_chain_out)
    return dict(sets=sets, resid=round(resid), **{k: round(v) for k, v in terms.items()})

if __name__ == "__main__":
    vs = [json.loads(a) for a in sys.argv[1:]]
    with ProcessPoolExecutor(6) as ex:
        for r in ex.map(one, vs): print(json.dumps(r), flush=True)
