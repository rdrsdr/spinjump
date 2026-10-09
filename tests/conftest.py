import math

import mujoco
import numpy as np
import pytest

from spinjump.config import load_config
from spinjump.model import build, lowest_geom_z
from spinjump.sim import TELEMETRY_FIELDS, Simulation

F = {k: i for i, k in enumerate(TELEMETRY_FIELDS)}


def samples(sim: Simulation) -> np.ndarray:
    return np.asarray(sim.samples, dtype=float)


def col(S: np.ndarray, name: str) -> np.ndarray:
    return S[:, F[name]]


def lying_sandbag(sets=(), z_clear=0.0005, with_tower=False):
    """Saco deitado (eixo ao longo de x) apoiado no solo."""
    cfg = load_config(sets=["object.type=sandbag", "object.height_m=1.0", "object.radius_m=0.2",
                            "object.mass_kg=80", *sets])
    q = (math.cos(math.pi / 4), 0.0, math.sin(math.pi / 4), 0.0)
    b = build(cfg, np.array([0.0, 0.0, 1.0]), q, with_tower=with_tower)
    b.data.qpos[2] -= lowest_geom_z(b.model, b.data, b.obj_gids) - z_clear
    mujoco.mj_forward(b.model, b.data)
    return cfg, b


@pytest.fixture(scope="session")
def default_run():
    """Cenário demonstrativo padrão completo (espiras deslizantes)."""
    return Simulation(load_config()).run()


@pytest.fixture(scope="session")
def locked_run():
    """Mesmo cenário com espiras travadas (rope.coil_sliding: false)."""
    return Simulation(load_config(sets=["rope.coil_sliding=false"])).run()
