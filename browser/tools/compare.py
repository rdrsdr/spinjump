"""Compara o porte JavaScript com o simulador Python no mesmo cenário (vento sem rajadas).

Uso (no container de desenvolvimento), depois de ``node tools/bench.mjs <cenário> --csv ...``:
    ./dev.sh python browser/tools/compare.py cmp_sliding out/browser/cmp_sliding_js.csv
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from spinjump.config import load_config  # noqa: E402
from spinjump.metrics import summarize  # noqa: E402
from spinjump.sim import TELEMETRY_FIELDS, Simulation  # noqa: E402

FIELDS = ["t", "x", "y", "z", "vx", "vy", "vz", "speed", "theta_turns", "wall_dist", "wound_turns", "free_len",
          "tension", "coil_drop"]


def main(name: str, js_csv: str):
    scen = json.loads((ROOT / "browser/public/scenarios" / f"{name}.json").read_text())
    cfg = load_config(preset=scen["preset"], sets=scen["overrides"])
    sim = Simulation(cfg)
    sim.run()
    idx = [TELEMETRY_FIELDS.index(f) for f in FIELDS]
    py = [[row[i] for i in idx] for row in sim.samples]
    with open(js_csv) as fh:
        rd = csv.DictReader(fh)
        js = [[float(r[f]) for f in FIELDS] for r in rd]
    n = min(len(py), len(js))
    t_ground = sim.tr.first_ground_t or 1e9
    # divergência de posição ao longo do tempo
    marks = [1, 2, 5, 10, 15, 20, t_ground - 0.01, t_ground + 1, t_ground + 3]
    rows = []
    for tm in marks:
        k = min(range(n), key=lambda i: abs(py[i][0] - tm))
        dp = math.dist(py[k][1:4], js[k][1:4])
        rows.append((py[k][0], dp, py[k][3], js[k][3], py[k][12], js[k][12], py[k][10], js[k][10]))
    flight = [i for i in range(n) if py[i][0] < t_ground]
    max_dp = max(math.dist(py[i][1:4], js[i][1:4]) for i in flight)
    max_dT = max(abs(py[i][12] - js[i][12]) for i in flight)
    summ = summarize(sim)
    print(json.dumps(dict(
        scenario=name,
        python=dict(outcome=sim.outcome, turns_before_ground=summ["spiral"]["object_turns_before_ground"],
                    ground_t=sim.tr.first_ground_t, ground_speed=sim.tr.first_ground_speed,
                    slide_path=sim.tr.slide_path, tension_max=sim.tr.t_max, coil_drop=sim.tr.coil_drop_max,
                    coil_friction=sim.tr.w_coil_fric, strongest_g=max((e["decel_peak_g"] for e in sim.impacts.events),
                                                                      default=None),
                    rest_t=sim.tr.rest_t, sim_time=sim.d.time,
                    us_per_step=sim.wall_clock / max(sim.step_count, 1) * 1e6),
        flight_max_position_diff_m=max_dp, flight_max_tension_diff_N=max_dT,
    ), indent=1, default=float))
    print("   t      |Δpos| m   z_py     z_js     T_py     T_js   wound_py wound_js")
    for r in rows:
        print(" ".join(f"{v:8.3f}" for v in r))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
