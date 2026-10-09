"""Cenário demonstrativo (9) e convergência (6)."""
import numpy as np

from spinjump.convergence import TOLERANCE, study
from spinjump.metrics import summarize

import pytest

from conftest import col, samples

# resíduo admissível do balanço de energia em voo (fração de E0): espiras travadas fecham a ~0,01%;
# espiras deslizantes têm erro de 1ª ordem no acoplamento corda encostada–vão (1,7% com dt e 1,0%
# com dt/2 no voo completo; ver NOTES)
ENERGY_TOL = {"locked": 0.005, "surface": 0.025}


@pytest.mark.parametrize("model", ["sliding", "locked"])
def test_9_demonstrative_scenario(model, default_run, locked_run):
    sim = default_run if model == "sliding" else locked_run
    s = summarize(sim)
    S = samples(sim)
    tg = sim.tr.first_ground_t
    air = col(S, "t") < tg
    # pelo menos uma volta física antes do solo
    assert s["spiral"]["object_turns_before_ground"] >= 1.0
    # redução sincronizada do comprimento enrolado: voltas liberadas acompanham as voltas do objeto
    unwound = sim.layout["turns0"] - col(S, "stored_turns")
    obj = col(S, "theta_turns")
    assert s["spiral"]["unwound_turns_before_ground"] >= 1.0
    assert abs(unwound[air][-1] - obj[air][-1]) < 0.35
    assert np.corrcoef(unwound[air], obj[air])[0, 1] > 0.99
    # chega ao solo, desliza e só então para (sem parada instantânea)
    assert sim.outcome == "AT_REST_CLEAN"
    gp = s["ground_phase"]
    assert gp["slide_path_m"] > 2.0
    assert gp["time_ground_to_rest_s"] > 1.0
    # trajetória pós-solo condicionada pela corda (tensa na maior parte do tempo, curva em torno da torre)
    assert gp["rope_taut_fraction_on_ground"] > 0.5
    assert gp["angle_swept_after_ground_deg"] > 10.0
    # sem quique numérico: após o toque, a energia mecânica não aumenta além do aporte do vento
    after = ~air
    e = col(S, "e_total")[after]
    w_in = col(S, "w_wind_in")[after]
    e_adj = e - (w_in - w_in[0])
    rise = np.max(e_adj - np.minimum.accumulate(e_adj))
    assert rise < 0.01 * e_adj[0] + 5.0, f"energia aumentou {rise:.1f} J após o toque"
    # sem colisão estrutural, corda abaixo do alerta, balanço de energia em voo fechado
    assert not s["outcome"]["flags"]["structure_hit"]
    assert not s["outcome"]["flags"]["load_warning"]
    tol = ENERGY_TOL[sim.rope.model_name]
    assert s["energy"]["flight_balance_residual_max_J"] < tol * s["energy"]["initial_J"]


def _study(run):
    tr = run.tr
    base = dict(outcome=run.outcome, arrival_speed_ms=tr.first_ground_speed, slide_path_m=tr.slide_path,
                tension_max_N=tr.t_max, timestep_s=run.cfg.solver.timestep_s,
                element_length_m=run.cfg.rope.element_length_m)
    return study(run.cfg, base=base)


def test_6_convergence_locked(locked_run):
    """Espiras travadas: chegada, deslizamento e tração máxima variam ≤ 10%."""
    cv = _study(locked_run)
    print("convergência (travado):", cv["rel_change"])
    assert cv["tolerance"] == TOLERANCE == 0.10
    assert cv["reliable"], cv


def test_6_convergence_sliding(default_run):
    """Espiras deslizantes: as grandezas do voo convergem (≤ 10%). O deslizamento no solo é
    caótico neste modelo (perturbar a velocidade de lançamento em 1 mm/s muda-o de 9,7 para
    27,7 m; ver NOTES), então o estudo pode reprová-lo; nesse caso o resultado tem de sair marcado
    como NÃO CONFIÁVEL — é o comportamento exigido pela especificação."""
    cv = _study(default_run)
    print("convergência (deslizante):", cv["rel_change"])
    assert cv["rel_change"]["arrival_speed_ms"] <= TOLERANCE
    assert cv["rel_change"]["tension_max_N"] <= TOLERANCE
    assert cv["reliable"] == (cv["max_rel_change"] <= TOLERANCE)


@pytest.mark.parametrize("model", ["sliding", "locked"])
def test_summary_is_plain_json(model, default_run, locked_run):
    """O resumo (enviado à interface ao fim) serializa com json puro: nada de tipos NumPy."""
    import json
    run = default_run if model == "sliding" else locked_run
    s = summarize(run)
    json.dumps(s)
    assert all(type(v) is bool for v in s["outcome"]["flags"].values())
