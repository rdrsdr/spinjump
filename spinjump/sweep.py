"""Varredura de parâmetros e seeds sem display: CSV + mapas de calor."""
from __future__ import annotations

import csv
import itertools
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .config import SimConfig, apply_overrides, parse_scalar, resolve, to_plain
from .plots import heatmap
from .report import run_dir
from .sim import Simulation, safety_notice

METRICS = {
    "turns_before_ground": "voltas antes do solo",
    "arrival_speed_ms": "velocidade de chegada (m/s)",
    "slide_path_m": "deslizamento (m)",
    "tension_max_N": "tração máxima (N)",
    "min_wall_distance_m": "distância mínima à parede (m)",
    "max_impact_g": "maior impacto (g)",
}
OUTCOME_CODE = {"AT_REST_CLEAN": 0, "REWOUND": 1, "TIMEOUT": 2, "HIT_STRUCTURE": 3, "NUMERICAL_FAILURE": 4}


def _one(job):
    plain, combo = job
    try:
        cfg, _ = resolve(SimConfig.model_validate(plain))
        s = Simulation(cfg, resolved=True).run()
    except Exception as e:  # configuração inválida para esta combinação
        return dict(combo, outcome="CONFIG_ERROR", error=str(e))
    tr = s.tr
    ev = s.impacts.events
    return dict(combo, outcome=s.outcome,
                turns_before_ground=round(tr.first_ground_theta, 4) if tr.first_ground_theta is not None else None,
                arrival_speed_ms=round(tr.first_ground_speed, 4) if tr.first_ground_speed is not None else None,
                slide_path_m=round(tr.slide_path, 4), tension_max_N=round(tr.t_max, 2),
                min_wall_distance_m=round(tr.wall_dist_min, 4),
                max_impact_g=round(max((e["decel_peak_g"] for e in ev), default=0.0), 3),
                structure_hit=bool(s.structure_hits()), slack_time_s=round(tr.slack_time, 3),
                rewind_max_turns=round(tr.rewind_max_turns, 4), t_end_s=round(s.d.time, 3),
                rope_length_m=float(s.cfg.rope.length_m))


def parse_param(spec: str) -> tuple[str, list]:
    path, vals = spec.split("=", 1)
    return path.strip(), [parse_scalar(v) for v in vals.split(",") if v.strip() != ""]


def run_sweep(cfg: SimConfig, params: list[str], seeds: str, out: str | None, workers: int = 0,
              metrics: list[str] | None = None) -> dict:
    if not 1 <= len(params) <= 2:
        raise ValueError("sweep aceita 1 ou 2 parâmetros (--param)")
    axes = [parse_param(p) for p in params]
    seed_list = [int(x) for x in seeds.split(",") if x.strip()] or [cfg.wind.seed]
    base = to_plain(cfg)
    jobs = []
    for values in itertools.product(*[v for _, v in axes]):
        for seed in seed_list:
            sets = [f"{p}={v}" for (p, _), v in zip(axes, values)] + [f"wind.seed={seed}"]
            plain = apply_overrides(base, sets)
            combo = {p: v for (p, _), v in zip(axes, values)}
            combo["seed"] = seed
            jobs.append((plain, combo))
    workers = workers or max(1, min(len(jobs), (os.cpu_count() or 2) - 1))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_one, jobs))
    d = run_dir(f"sweep_{cfg.name}", out)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(d / "sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    heat = []
    mlist = metrics or ["turns_before_ground", "arrival_speed_ms", "slide_path_m", "tension_max_N"]
    (px, xs) = axes[0]
    (py, ys) = axes[1] if len(axes) == 2 else ("seed", seed_list)
    for mname in mlist + ["outcome_code"]:
        grid = np.full((len(ys), len(xs)), np.nan)
        for j, xv in enumerate(xs):
            for i, yv in enumerate(ys):
                sel = [r for r in rows if r.get(px) == xv and r.get(py) == yv]
                if mname == "outcome_code":
                    vals = [OUTCOME_CODE.get(r["outcome"], 5) for r in sel]
                    grid[i, j] = max(vals) if vals else np.nan
                else:
                    vals = [r.get(mname) for r in sel if r.get(mname) is not None]
                    grid[i, j] = float(np.mean(vals)) if vals else np.nan
        title = METRICS.get(mname, "desfecho (0 repouso, 1 reenrolou, 2 tempo, 3 torre, 4 falha)")
        fname = f"heatmap_{mname}.png"
        heatmap(grid, xs, ys, px, py, title + (" — média das seeds" if len(axes) == 2 and len(seed_list) > 1 else ""),
                mname, d / fname, fmt="{:.0f}" if mname in ("tension_max_N", "outcome_code") else "{:.2f}")
        heat.append(str(d / fname))
    (d / "sweep.md").write_text(
        f"# Varredura {cfg.name}\n\n> {safety_notice()}\n\nParâmetros: {', '.join(p for p, _ in axes)}; "
        f"seeds: {seed_list}; {len(rows)} execuções.\n\n" + "\n".join(f"![{Path(h).name}]({Path(h).name})" for h in heat)
        + "\n")
    return dict(n_runs=len(rows), csv=str(d / "sweep.csv"), heatmaps=heat, dir=str(d), rows=rows)
