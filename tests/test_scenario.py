"""Cenário demonstrativo (9) e convergência (6)."""
import numpy as np

from spinjump.convergence import TOLERANCE, study
from spinjump.metrics import summarize

from conftest import col, samples


def test_9_demonstrative_scenario(default_run):
    sim = default_run
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
    assert s["energy"]["flight_balance_residual_max_J"] < 0.005 * s["energy"]["initial_J"]


def test_6_convergence(default_run):
    tr = default_run.tr
    base = dict(outcome=default_run.outcome, arrival_speed_ms=tr.first_ground_speed, slide_path_m=tr.slide_path,
                tension_max_N=tr.t_max, timestep_s=default_run.cfg.solver.timestep_s,
                element_length_m=default_run.cfg.rope.element_length_m)
    cv = study(default_run.cfg, base=base)
    print("convergência:", cv["rel_change"])
    assert cv["tolerance"] == TOLERANCE == 0.10
    assert cv["reliable"], cv
