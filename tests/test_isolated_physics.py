"""Ensaios isolados: queda livre (1), deslizamento (2) e impacto/impulso normal (3)."""
import math

import mujoco
import numpy as np
import pytest

from spinjump.config import G, load_config
from spinjump.impacts import ImpactTracker
from spinjump.model import build, pair_friction

from conftest import lying_sandbag


def test_1_free_fall_analytic():
    """Sem corda/ar: posição e velocidade com erro < 0,5% da solução analítica."""
    cfg = load_config()
    b = build(cfg, np.array([0.0, 0.0, 200.0]), with_tower=False)
    m, d = b.model, b.data
    z0 = d.xipos[b.body_id][2]
    errs_z, errs_v = [], []
    for k in range(1, int(round(3.0 / m.opt.timestep)) + 1):
        mujoco.mj_step(m, d)
        if k % 400 == 0:
            t = d.time
            dz_ana = 0.5 * G * t * t
            errs_z.append(abs((z0 - d.xipos[b.body_id][2]) - dz_ana) / dz_ana)
            errs_v.append(abs(-d.qvel[2] - G * t) / (G * t))
    print(f"queda livre: erro máx posição {max(errs_z):.2e}, velocidade {max(errs_v):.2e}")
    assert max(errs_v) < 0.005
    assert max(errs_z) < 0.005, f"erro máx. posição {max(errs_z):.2e}"


@pytest.mark.parametrize("mu_ground", [0.6, 0.3, 0.1])
def test_2_isolated_slide_distance(mu_ground):
    """Saco deitado deslizando ao longo do eixo: distância ≈ v²/(2 μ g) (erro < 5%)."""
    cfg, b = lying_sandbag([f"ground.friction_slide={mu_ground}"])
    m, d = b.model, b.data
    for _ in range(4000):                 # assentamento
        mujoco.mj_step(m, d)
    x0 = d.qpos[:2].copy()
    v0 = 5.0
    d.qvel[:] = 0.0
    d.qvel[0] = v0
    while d.time < 30 and np.linalg.norm(d.qvel[:3]) > 1e-4:
        mujoco.mj_step(m, d)
    mu = pair_friction(cfg.ground.friction_slide, cfg.object.geom_friction)
    expected = v0 ** 2 / (2 * mu * G)
    dist = float(np.linalg.norm(d.qpos[:2] - x0))
    print(f"deslizamento μ={mu}: {dist:.4f} m vs {expected:.4f} m (erro {dist / expected - 1:+.2%})")
    assert abs(dist / expected - 1) < 0.05, f"{dist:.3f} m vs {expected:.3f} m"


def _drop(gravity: bool, dampratio: float, v_in: float = 6.0):
    cfg, b = lying_sandbag([f"contact.solref=[0.02, {dampratio}]"], z_clear=0.002)
    m, d = b.model, b.data
    if not gravity:
        m.opt.gravity[:] = 0.0
    d.qvel[2] = -v_in
    trk = ImpactTracker(cfg, m, b.obj_gids, b.ground_gid, -1, b.mass, m.opt.timestep)
    v_hist = []
    for _ in range(int(0.6 / m.opt.timestep)):
        t = d.time
        mujoco.mj_step1(m, d)
        v = d.qvel[:3].copy()
        mujoco.mj_step2(m, d)
        trk.step(d, t, v)
        v_hist.append((t, v[2]))
    ev = trk.finish()
    return cfg, b, ev, np.array(v_hist)


@pytest.mark.parametrize("gravity", [False, True])
def test_3_impact_normal_impulse(gravity):
    """Impulso normal integrado ≈ m·Δv (erro < 3%). Com gravidade, soma-se m·g·duração."""
    cfg, b, ev, vh = _drop(gravity, dampratio=0.4)
    # com gravidade o saco quica de verdade e pousa de novo: o 2º evento só pode vir após voo real
    assert len(ev) == 1 or ev[1]["t_start"] - ev[0]["t_end"] > 0.1, ev
    e = ev[0]
    t0, t1 = e["t_start"], e["t_end"]
    v_before = vh[np.searchsorted(vh[:, 0], t0) - 1, 1]
    v_after = vh[min(np.searchsorted(vh[:, 0], t1) + 2, len(vh) - 1), 1]
    m = b.mass
    expected = m * (v_after - v_before) + (m * G * e["duration_s"] if gravity else 0.0)
    J = e["impulse_normal_event_Ns"]
    print(f"impacto (gravidade={gravity}): J={J:.3f} N·s vs {expected:.3f} (erro {J / expected - 1:+.2%})")
    assert abs(J / expected - 1) < 0.03, f"J={J:.2f} vs mΔv(+mgτ)={expected:.2f}"
    assert e["v_normal_in_ms"] == pytest.approx(6.0, rel=0.02)
    assert e["force_normal_peak_filtered_N"] <= e["force_normal_peak_raw_N"] + 1e-9


def test_3b_landing_and_rest_is_single_event():
    """Pouso seguido de repouso (sem quique): um único evento agrupado."""
    cfg, b, ev, vh = _drop(True, dampratio=load_config().contact.solref[1])
    assert len(ev) == 1
    assert ev[0]["impulse_normal_impact_Ns"] == pytest.approx(b.mass * 6.0, rel=0.08)
