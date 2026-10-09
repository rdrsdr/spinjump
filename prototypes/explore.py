"""Exploração de parâmetros do wrap_tether (usada para escolher o cenário demonstrativo)."""
import json, math, sys, time
from spinjump.config import load_config
from spinjump.sim import Simulation

def run(sets, tmax=None):
    cfg = load_config(sets=sets + ([f"solver.max_time_s={tmax}"] if tmax else []))
    t0 = time.perf_counter()
    s = Simulation(cfg).run()
    tr = s.tr
    ev = s.impacts.events
    tower = [e for e in ev if e["surface"] == "tower"]
    ground = [e for e in ev if e["surface"] == "ground"]
    th0 = 0.0
    return dict(sets=sets, outcome=s.outcome, t_end=round(s.d.time, 2), wall=round(time.perf_counter()-t0, 1),
        L=s.cfg.rope.length_m, turns0=round(s.layout["turns0"], 2),
        t_ground=tr.first_ground_t and round(tr.first_ground_t, 2),
        obj_turns_before_ground=tr.first_ground_theta is not None and round(tr.first_ground_theta, 2),
        wound_at_ground=tr.first_ground_wound_turns and round(tr.first_ground_wound_turns, 2),
        v_ground=tr.first_ground_speed and round(tr.first_ground_speed, 2),
        t_tower=tr.first_tower_t and round(tr.first_tower_t, 2), v_tower=tr.first_tower_vn and round(tr.first_tower_vn, 2),
        n_tower=len(tower), tower_vn=[e["v_normal_in_ms"] for e in tower][:5],
        n_ground=len(ground), wall_min=round(tr.wall_dist_min, 3), Tmax=round(tr.t_max), slide=round(tr.slide_path, 1),
        rewind=round(tr.rewind_max_turns, 2), slack_t=round(tr.slack_time, 2), lifts=tr.airborne_after_ground,
        gmax=max([e["decel_peak_g"] for e in ev], default=0))

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(json.dumps(run([a for a in arg.split(";") if a])), flush=True)
