"""Ensaios da corda wrap_tether: involuta (4), cabrestante (5), azimute/determinismo (7),
contabilidade de comprimento, unilateralidade e alcance (8)."""
import math

import numpy as np
import pytest

from spinjump.config import load_config
from spinjump.sim import Simulation

from conftest import col, samples


def _involute_sim(t_end=12.0):
    cfg = load_config(sets=[
        "object.type=sandbag", "object.height_m=1.0", "object.radius_m=0.2", "object.attach_height_fraction=0.5",
        "rope.length_m=60", "rope.axial_EA_N=5.0e6", "rope.linear_density_kg_m=0", "rope.wall_friction=0",
        "air.enabled=false", "wind.enabled=false", "launch.mode=velocity", "launch.speed_ms=4",
        "launch.azimuth_deg=90", "launch.elevation_deg=0", f"solver.max_time_s={t_end}"])
    sim = Simulation(cfg)
    sim.m.opt.gravity[:] = 0.0          # sem gravidade
    return sim.run()


def test_4_involute_matches_analytic():
    """Sem atrito/gravidade/arrasto: trajetória ≈ involuta analítica e ΔKE < 2%."""
    sim = _involute_sim()
    S = samples(sim)
    t = col(S, "t")
    rc = sim.rp.rc
    v = float(np.linalg.norm(sim.launch_J / sim.mass * sim.launch_dir))
    l0 = sim.layout["free0"]
    D0 = sim.layout["D0"]
    phi0 = math.atan2(D0[1], D0[0])
    h = sim.rp.handedness
    # ℓ² = ℓ0² + 2 rc v t; o ponto de saída recua (desenrola) de (ℓ - ℓ0)/rc
    ell = np.sqrt(l0 ** 2 + 2 * rc * v * t)
    phi = phi0 - h * (ell - l0) / rc
    rhat = np.stack([np.cos(phi), np.sin(phi)], 1)
    that = h * np.stack([-np.sin(phi), np.cos(phi)], 1)
    A_ana = rc * rhat + ell[:, None] * that
    A_sim = np.stack([col(S, "x"), col(S, "y")], 1)
    err = np.linalg.norm(A_sim - A_ana, axis=1)
    ke = col(S, "ke")
    dke = np.max(np.abs(ke - ke[0])) / ke[0]
    turns = sim.layout["turns0"] - col(S, "stored_turns")[-1]
    print(f"involuta: erro espacial máx {err.max()*1000:.2f} mm (ℓ final {ell[-1]:.2f} m), ΔKE {dke:.3%}, "
          f"voltas liberadas {turns:.2f}")
    assert turns > 0.5
    assert dke < 0.02
    assert err.max() < 0.01 * ell[-1], f"erro espacial {err.max():.4f} m"


def test_5_capstan_force_balance_and_model_ratio(default_run):
    """Cabrestante: (a) equilíbrio de forças discretizado de um trecho enrolado em deslizamento
    iminente converge para exp(-μθ); (b) a razão T_âncora/T_objeto reportada pelo modelo é
    exp(-μ·θ_armazenado) em todas as amostras (tolerância numérica: o modelo aplica a lei
    analiticamente porque a hélice armazenada está ancorada e não escorrega)."""
    mu, theta = 0.4, 2 * math.pi * 1.5
    for n in (200, 2000, 20000):
        dth = theta / n
        T = 1.0
        for _ in range(n):
            N = 2 * T * math.sin(dth / 2)       # normal da curvatura sob tração
            T -= mu * N                          # atrito limite
        err = abs(T / math.exp(-mu * theta) - 1)
        print(f"cabrestante discretizado N={n}: erro {err:.2e} vs exp(-μθ)")
    assert err < 1e-3, err
    S = samples(default_run)
    tens, ta, st = col(S, "tension"), col(S, "tension_anchor"), col(S, "stored_turns")
    m = tens > 1.0
    ratio = ta[m] / tens[m]
    expected = np.exp(-default_run.rp.mu_wall * 2 * math.pi * st[m])
    assert np.allclose(ratio, expected, rtol=1e-6)


def _short(sets, t=4.0):
    return Simulation(load_config(sets=[*sets, f"solver.max_time_s={t}"])).run()


def test_7_azimuth_sign_convention():
    pos = _short(["launch.azimuth_deg=90", "launch.speed_ms=6"])
    neg = _short(["launch.azimuth_deg=-90", "launch.speed_ms=6"])
    Sp, Sn = samples(pos), samples(neg)
    unwound_p = pos.layout["turns0"] - col(Sp, "stored_turns")[-1]
    # positivo: libera corda e o objeto gira no sentido de desenrolar
    assert unwound_p > 0.1 and col(Sp, "theta_turns")[-1] > 0.1
    # negativo: o objeto começa girando no sentido de enrolar e a corda reenrola (trecho geodésico cresce)
    t = col(Sn, "t")
    assert col(Sn, "theta_turns")[np.searchsorted(t, 0.3)] < 0.0
    assert col(Sp, "theta_turns")[np.searchsorted(col(Sp, "t"), 0.3)] > 0.0
    assert neg.tr.rewind_max_turns > 0.05
    assert neg.tr.rewind_max_turns > pos.tr.rewind_max_turns


def test_7_determinism_same_seed():
    a = samples(_short(["wind.seed=7", "wind.gust_std_ms=1.5"], 5.0))
    b = samples(_short(["wind.seed=7", "wind.gust_std_ms=1.5"], 5.0))
    c = samples(_short(["wind.seed=8", "wind.gust_std_ms=1.5"], 5.0))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_7_impulse_changes_trajectory():
    lo = _short(["launch.mode=impulse", "launch.impulse_Ns=160", "launch.speed_ms=null"], 3.0)
    hi = _short(["launch.mode=impulse", "launch.impulse_Ns=640", "launch.speed_ms=null"], 3.0)
    dl = np.linalg.norm(samples(lo)[-1, 1:4] - samples(hi)[-1, 1:4])
    assert dl > 0.5, dl
    assert hi.tr.t_max != lo.tr.t_max


def test_7_impulse_with_duration_equals_instantaneous_momentum():
    inst = Simulation(load_config(sets=["launch.mode=impulse", "launch.impulse_Ns=480", "launch.speed_ms=null",
                                        "solver.max_time_s=0.001", "air.enabled=false"]))
    dur = Simulation(load_config(sets=["launch.mode=impulse", "launch.impulse_Ns=480", "launch.speed_ms=null",
                                       "launch.duration_ms=100", "air.enabled=false", "solver.max_time_s=1"]))
    dur.m.opt.gravity[:] = 0.0
    dur.release_rope_at_ground = False
    # sem corda: isola a força de lançamento
    dur.rope.update = _no_rope(dur.rope)
    while dur.d.time < 0.1 - 1e-12:
        dur.step()
    p = dur.mass * dur.d.qvel[:3]
    assert np.linalg.norm(p) == pytest.approx(480.0, rel=1e-3)
    assert np.linalg.norm(inst.d.qvel[:3]) * inst.mass == pytest.approx(480.0, rel=1e-9)


def _no_rope(rope):
    orig = rope.update

    def upd(*a, **k):
        s = orig(*a, **k)
        s.force_on_obj = np.zeros(3)
        s.dist_load_on_obj = np.zeros(3)
        return s
    return upd


def test_8_length_bookkeeping_and_unilateral(default_run):
    S = samples(default_run)
    L = default_run.rp.length
    assert np.allclose(col(S, "stored_len") + col(S, "rest_len"), L, atol=1e-9)
    assert np.allclose(col(S, "path_len") - col(S, "rest_len"), col(S, "elongation") - col(S, "slack"), atol=1e-9)
    T = col(S, "tension")
    assert T.min() >= 0.0
    assert np.all(T[col(S, "slack") > 0] == 0.0)


def test_8_slack_gives_zero_tension():
    s = _short(["launch.azimuth_deg=0", "launch.speed_ms=6", "launch.elevation_deg=40"], 3.0)
    S = samples(s)
    sl = col(S, "slack") > 1e-3
    assert sl.any(), "este lançamento deve produzir folga"
    assert np.all(col(S, "tension")[sl] == 0.0)


def test_8_taut_rope_limits_reach_on_ground(default_run):
    S = samples(default_run)
    tg = default_run.tr.first_ground_t
    g = (col(S, "t") >= tg) & (col(S, "tension") > 0)
    excess = col(S, "path_len")[g] - col(S, "rest_len")[g]
    ea = default_run.rp.EA
    allowed = col(S, "rest_len")[g] * default_run.tr.t_max_ground / ea
    assert np.all(excess <= 1.2 * allowed + 1e-6)
    # contrafactual: soltando a corda no toque, o objeto escapa radialmente; com a corda tensa o raio
    # não passa do valor no toque e o percurso no solo é outro (corda condiciona a trajetória)
    free = Simulation(load_config())
    free.release_rope_at_ground = True
    free.run()
    Sf = samples(free)
    i = np.searchsorted(col(S, "t"), tg)
    j = np.searchsorted(col(Sf, "t"), free.tr.first_ground_t)
    r_rope = np.hypot(col(S, "x")[i:], col(S, "y")[i:])
    r_free = np.hypot(col(Sf, "x")[j:], col(Sf, "y")[j:])
    end_gap = np.hypot(col(S, "x")[-1] - col(Sf, "x")[-1], col(S, "y")[-1] - col(Sf, "y")[-1])
    print(f"raio: toque {r_rope[0]:.2f} → máx com corda {r_rope.max():.2f} / sem corda {r_free.max():.2f} m; "
          f"pontos finais a {end_gap:.2f} m")
    assert r_rope.max() <= r_rope[0] + 0.02
    assert r_free.max() > r_rope.max() + 0.2
    assert end_gap > 2.0
