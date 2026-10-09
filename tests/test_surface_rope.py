"""Corda com espiras deslizantes (rope.coil_sliding: true): validações próprias do modelo.

A cadeia encostada é exercitada diretamente (sem objeto) aplicando a força do vão na ponta.
"""
import math

import numpy as np
import pytest

from spinjump.config import load_config
from spinjump.sim import Simulation

from conftest import col, samples


def _rope(*sets):
    sim = Simulation(load_config(sets=["rope.coil_sliding=true", *sets]))
    return sim.rope


def _tensions(r):
    k = r.k
    L = np.hypot(np.diff(r.x[:k + 1]), np.diff(r.z[:k + 1]))
    return r.p.EA * np.maximum(L - r.ds, 0.0) / r.ds


def test_capstan_dynamic_exp_mu_theta():
    """Puxando a ponta tangencialmente (sem gravidade) com carga crescente, a tração na zona que
    escorrega decai como exp(-μθ) para dentro do enrolamento: inclinação de ln T por radiano = μ.
    Mede-se durante o escorregamento (lei de limite); parado, o atrito pode ficar abaixo do limite.
    Tolerância de 5%: o alongamento (até 2,5% perto da ponta) e a discretização (0,08 rad/nó)."""
    for mu in (0.2, 0.4):
        r = _rope(f"rope.wall_friction={mu}", "rope.winding_pretension_N=20")
        for i in range(8000):
            F = 1500.0 * i / 8000
            r._step_chain(F * r.sw, 0.0, 0.0)
        T = _tensions(r)
        theta = r.sw * r.x[1:r.k + 1] / r.p.rc          # posição angular de cada segmento (ponta = maior)
        zone = (T > 3 * 20.0) & (np.arange(T.size) < T.size - 3)
        assert zone.sum() > 10
        slope = np.polyfit(theta[zone], np.log(T[zone]), 1)[0]
        print(f"μ={mu}: inclinação ln T = {slope:.4f} rad⁻¹ (esperado {mu}), zona {zone.sum()} nós")
        assert abs(slope / mu - 1) < 0.05


def test_pretension_holds_coils_against_gravity():
    r = _rope("rope.winding_pretension_N=20")
    for _ in range(4000):                               # 1 s, ponta puxada na horizontal
        r._step_chain(200.0 * r.sw, 0.0, 9.81)
    assert r.coil_drop() < 0.002, r.coil_drop()
    r0 = _rope("rope.winding_pretension_N=0")
    for _ in range(4000):                               # sem pré-tensão nada segura as espiras
        r0._step_chain(0.0, 0.0, 9.81)
    assert r0.coil_drop() > 0.01, r0.coil_drop()


@pytest.mark.parametrize("vertical, slides", [("down", True), ("up", False)])
def test_steep_pull_slides_down_coils_but_stack_holds_up(vertical, slides):
    """Puxão inclinado 60° para baixo: com a hélice descendo (saída pela espira de baixo) a corda
    escorrega pela parede; com a hélice subindo (saída pela de cima) a espira puxada apoia-se nas de
    baixo (contato entre voltas) e o conjunto segura."""
    r = _rope(f"rope.helix_vertical={vertical}")
    a = math.radians(-60)
    for _ in range(4000):
        r._step_chain(800.0 * math.cos(a) * r.sw, 800.0 * math.sin(a), 9.81)
    drop = r.coil_drop()
    print(f"{vertical}: deslocamento máximo das espiras {drop:.3f} m")
    assert (drop > 0.3) if slides else (drop < 0.02)


@pytest.fixture(scope="module")
def flight10():
    return Simulation(load_config(sets=["solver.max_time_s=10"])).run()


def test_energy_balance_in_flight(flight10):
    """Resíduo do balanço de energia em voo < 2,5% da energia inicial (erro de 1ª ordem medido:
    1,7% com dt = 0,25 ms e 1,0% com dt/2; ver NOTES)."""
    tr = flight10.tr
    print(f"resíduo {tr.e_flight_residual_max:.0f} J de {tr.energy0:.0f} J; atrito {tr.w_coil_fric:.0f} J")
    assert tr.e_flight_residual_max < 0.025 * tr.energy0
    assert tr.w_coil_fric > 0.0


def test_sliding_vs_locked_same_global_motion(flight10):
    """O freio da descida muda de mecanismo (atrito das espiras em vez da dobra), mas a
    dissipação total é parecida: voltas e altura em 10 s ficam próximas do modelo travado."""
    locked = Simulation(load_config(sets=["solver.max_time_s=10", "rope.coil_sliding=false"])).run()
    a, b = flight10, locked
    turns_a, turns_b = a.object_turns(), b.object_turns()
    za, zb = float(a.d.xipos[a.b.body_id][2]), float(b.d.xipos[b.b.body_id][2])
    print(f"voltas {turns_a:.3f} (deslizante) vs {turns_b:.3f} (travado); z {za:.2f} vs {zb:.2f} m; "
          f"perdas {a.tr.w_coil_fric + a.tr.w_peel:.0f} vs {b.tr.w_peel:.0f} J")
    assert abs(turns_a / turns_b - 1) < 0.10
    assert abs(za - zb) < 5.0
    assert a.tr.coil_drop_max > 0.5 and b.tr.coil_drop_max == 0.0


def test_up_helix_sliding_matches_locked():
    """Saída pela espira de cima: o contato entre voltas segura a hélice e o resultado reproduz o
    modelo travado (mesma geometria de saída)."""
    up = Simulation(load_config(sets=["solver.max_time_s=6", "rope.helix_vertical=up"])).run()
    lk = Simulation(load_config(sets=["solver.max_time_s=6", "rope.helix_vertical=up",
                                      "rope.coil_sliding=false"])).run()
    assert up.tr.coil_drop_max < 0.02
    assert abs(up.object_turns() / lk.object_turns() - 1) < 0.03
