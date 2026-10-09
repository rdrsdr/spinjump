"""Estudo de convergência: resolução espacial dobrada e passo de tempo pela metade."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

from .config import SimConfig, to_plain
from .sim import Simulation
from .i18n import t

TOLERANCE = 0.10
METRICS = ("arrival_speed_ms", "slide_path_m", "tension_max_N")


def _variant(args):
    plain, label = args
    cfg = SimConfig.model_validate(plain)
    s = Simulation(cfg, resolved=True).run()
    tr = s.tr
    return dict(label=label, outcome=s.outcome, arrival_speed_ms=round(tr.first_ground_speed or 0.0, 4),
                slide_path_m=round(tr.slide_path, 4), tension_max_N=round(tr.t_max, 2),
                timestep_s=cfg.solver.timestep_s, element_length_m=cfg.rope.element_length_m)


def study(cfg: SimConfig, base: dict | None = None, workers: int = 3) -> dict:
    """``cfg`` deve estar resolvido. ``base`` (opcional) reaproveita as métricas da execução base."""
    plain = to_plain(cfg)
    fine_space = to_plain(cfg)
    fine_space["rope"]["element_length_m"] = cfg.rope.element_length_m / 2
    fine_time = to_plain(cfg)
    fine_time["solver"]["timestep_s"] = cfg.solver.timestep_s / 2
    jobs = [(fine_space, t("conv.space")), (fine_time, t("conv.time"))]
    if base is None:
        jobs.insert(0, (plain, t("conv.base")))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        runs = list(ex.map(_variant, jobs))
    if base is not None:
        runs.insert(0, dict(label=t("conv.base"), **base))
    b = runs[0]
    changes = {}
    for k in METRICS:
        ref = abs(b[k])
        changes[k] = round(max((abs(r[k] - b[k]) / ref if ref > 1e-9 else abs(r[k] - b[k])) for r in runs[1:]), 4)
    worst = max(changes.values())
    return dict(runs=runs, rel_change=changes, max_rel_change=worst, tolerance=TOLERANCE,
                reliable=worst <= TOLERANCE,
                note=t("conv.note"))
