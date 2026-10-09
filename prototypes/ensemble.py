"""Sensibilidade a perturbações mínimas (caos) vs. erro de discretização."""
import sys, json, statistics as st
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation

def one(sets):
    s = Simulation(load_config(sets=sets)).run(); tr = s.tr
    return dict(sets=sets, v=round(tr.first_ground_speed or 0, 3), tg=round(tr.first_ground_t or 0, 2),
                slide=round(tr.slide_path, 2), turns=round(tr.first_ground_theta or 0, 3), Tmax=round(tr.t_max),
                drop=round(tr.coil_drop_max, 2))

if __name__ == "__main__":
    extra = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    jobs = []
    for dt in ("0.00025", "0.000125"):
        for dv in (0.0, 0.001, 0.002, 0.003, 0.004, 0.005):
            jobs.append(extra + [f"solver.timestep_s={dt}", f"launch.speed_ms={4.0 + dv}"])
    with ProcessPoolExecutor(12) as ex:
        res = list(ex.map(one, jobs))
    for dt in ("0.00025", "0.000125"):
        rs = [r for r in res if f"solver.timestep_s={dt}" in r["sets"]]
        for k in ("v", "tg", "slide", "turns", "Tmax", "drop"):
            vals = [r[k] for r in rs]
            print(f"dt={dt} {k:6s} média {st.mean(vals):8.3f}  desvio {st.pstdev(vals):7.3f}  min {min(vals):8.3f} max {max(vals):8.3f}")
        print()
