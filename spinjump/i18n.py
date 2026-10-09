"""Textos visíveis ao usuário em português (pt) e inglês (en).

O idioma vale para o processo inteiro: a CLI usa ``pt`` (padrão) e o servidor web usa ``en``
(``serve --lang`` ou variável ``SPINJUMP_LANG``). Códigos de dados (desfechos, classes de impacto,
nomes de campos) não são traduzidos; apenas os rótulos exibidos.
"""
from __future__ import annotations

import os

LANGS = ("pt", "en")
_lang = os.environ.get("SPINJUMP_LANG", "pt") if os.environ.get("SPINJUMP_LANG", "pt") in LANGS else "pt"


def set_lang(lang: str) -> None:
    global _lang
    if lang not in LANGS:
        raise ValueError(f"idioma não suportado / unsupported language: {lang}")
    _lang = lang


def get_lang() -> str:
    return _lang


def t(key: str, **kw) -> str:
    entry = TEXTS[key]
    s = entry.get(_lang) or entry["pt"]
    return s.format(**kw) if kw else s


TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------- geral
    "safety": {
        "pt": "Resultados qualitativos e exploratórios de um modelo simplificado. NÃO constituem validação "
              "de segurança humana; limiares de dano são ilustrativos, não clínicos.",
        "en": "Qualitative, exploratory results from a simplified model. They are NOT a human-safety "
              "validation; damage thresholds are illustrative, not clinical.",
    },
    "phase.0": {"pt": "lançamento", "en": "launch"},
    "phase.1": {"pt": "no ar", "en": "airborne"},
    "phase.2": {"pt": "no solo", "en": "on ground"},
    "phase.3": {"pt": "repouso", "en": "at rest"},
    "class.OK": {"pt": "OK", "en": "OK"},
    "class.ATENÇÃO": {"pt": "ATENÇÃO", "en": "WARNING"},
    "class.DANO": {"pt": "DANO", "en": "DAMAGE"},
    "surface.ground": {"pt": "solo", "en": "ground"},
    "surface.tower": {"pt": "torre", "en": "tower"},
    "outcome.AT_REST_CLEAN": {"pt": "repouso no solo sem colisão estrutural nem reenrolamento",
                              "en": "at rest on the ground, no structure hit, no rewinding"},
    "outcome.HIT_STRUCTURE": {"pt": "colisão com a torre acima do limiar de velocidade normal",
                              "en": "hit the tower above the normal-speed threshold"},
    "outcome.REWOUND": {"pt": "a corda reenrolou além do limiar configurado",
                        "en": "the rope rewound beyond the configured threshold"},
    "outcome.TIMEOUT": {"pt": "tempo máximo atingido sem repouso (ou execução encerrada)",
                        "en": "maximum time reached without coming to rest (or run stopped)"},
    "outcome.NUMERICAL_FAILURE": {"pt": "instabilidade numérica detectada", "en": "numerical instability detected"},
    # ------------------------------------------------------------- simulação
    "err.helix_too_tall": {
        "pt": "a hélice inicial ({turns:.2f} voltas, altura {height:.3f} m) ultrapassa o topo; aumente "
              "rope.anchor_below_top_m",
        "en": "the initial helix ({turns:.2f} turns, height {height:.3f} m) goes above the top; increase "
              "rope.anchor_below_top_m"},
    "warn.short_rope": {
        "pt": "rope.length_m={L:.2f} m é menor que o necessário para alcançar o solo ({Lmin:.2f} m da âncora "
              "ao objeto deitado junto à base): o objeto ficará suspenso",
        "en": "rope.length_m={L:.2f} m is shorter than needed to reach the ground ({Lmin:.2f} m from the anchor "
              "to the object lying at the base): the object will stay suspended"},
    "warn.stiff": {"pt": "rigidez axial alta para o passo: ω·dt = {w:.3f} > 0.2; reduza o timestep",
                   "en": "axial stiffness too high for the time step: ω·dt = {w:.3f} > 0.2; reduce the timestep"},
    "warn.elevation": {
        "pt": "elevação de lançamento > 60°: o objeto pode subir acima do topo da torre, onde o contato "
              "corda–borda do topo não é modelado",
        "en": "launch elevation > 60°: the object may rise above the tower top, where rope–rim contact is "
              "not modelled"},
    "warn.unreliable": {"pt": "estudo de convergência acima da tolerância: resultado NÃO CONFIÁVEL",
                        "en": "convergence study above tolerance: result NOT RELIABLE"},
    "fail.numerical": {"pt": "instabilidade numérica em t={t:.4f} s", "en": "numerical instability at t={t:.4f} s"},
    "stopped_by_user": {"pt": "encerrada pelo usuário", "en": "stopped by the user"},
    "stopped_disconnected": {"pt": "encerrada: visitante desconectado", "en": "stopped: visitor disconnected"},
    "err.attach_inside": {"pt": "ponto de fixação inicial dentro do raio da corda",
                          "en": "initial attachment point inside the rope radius"},
    "err.rope_too_short_start": {
        "pt": "rope.length_m={L:.2f} m não alcança o objeto na posição inicial (vão livre inicial {lh:.2f} m)",
        "en": "rope.length_m={L:.2f} m does not reach the object at its start position (initial free span "
              "{lh:.2f} m)"},
    # ------------------------------------------------------------- configuração
    "cfg.chain": {"pt": "rope.model 'chain' (corrente de cápsulas) foi excluído pela especificação",
                  "en": "rope.model 'chain' (capsule chain) is excluded by the specification"},
    "cfg.cable": {
        "pt": "rope.model 'cable_plugin' foi reprovado nos ensaios da fase 2 (custo, penetração, liberação de "
              "voltas); ver NOTES.md e prototypes/. Use 'wrap_tether'.",
        "en": "rope.model 'cable_plugin' failed the phase-2 tests (cost, wall penetration, unwinding); see "
              "NOTES.md and prototypes/. Use 'wrap_tether'."},
    "cfg.model_unknown": {"pt": "rope.model desconhecido: {v!r}; único modelo validado: 'wrap_tether'",
                          "en": "unknown rope.model: {v!r}; the only validated model is 'wrap_tether'"},
    "cfg.length_range": {"pt": "rope.length_m deve ser 'auto' ou estar entre 1 e 2000 m",
                         "en": "rope.length_m must be 'auto' or between 1 and 2000 m"},
    "cfg.ea_null": {
        "pt": "rope.axial_EA_N: null (inextensível) não é suportado de modo estável pelo modelo wrap_tether, "
              "cuja tração é uma lei elástica unilateral explícita; informe EA finito",
        "en": "rope.axial_EA_N: null (inextensible) is not stably supported by the wrap_tether model, whose "
              "tension is an explicit one-sided elastic law; give a finite EA"},
    "cfg.ea_range": {"pt": "rope.axial_EA_N fora da faixa [1e2, 1e8] N", "en": "rope.axial_EA_N outside [1e2, 1e8] N"},
    "cfg.need_speed": {"pt": "launch.mode=velocity exige launch.speed_ms",
                       "en": "launch.mode=velocity requires launch.speed_ms"},
    "cfg.need_impulse": {"pt": "launch.mode=impulse exige launch.impulse_Ns (N·s)",
                         "en": "launch.mode=impulse requires launch.impulse_Ns (N·s)"},
    "cfg.need_threshold": {"pt": "impact: informe damage_threshold_g ou damage_threshold_N",
                           "en": "impact: set damage_threshold_g or damage_threshold_N"},
    "cfg.anchor": {"pt": "rope.anchor_below_top_m deve ser menor que tower.height_m",
                   "en": "rope.anchor_below_top_m must be smaller than tower.height_m"},
    "cfg.wind_preset": {"pt": "wind.preset {v!r} não existe em wind.presets",
                        "en": "wind.preset {v!r} is not in wind.presets"},
    "cfg.ground_preset": {"pt": "ground.preset {v!r} não existe em ground.presets",
                          "en": "ground.preset {v!r} is not in ground.presets"},
    "cfg.len_auto_note": {"pt": "auto (estimativa simplificada; não garante órbita nem corda tensa)",
                          "en": "auto (simplified estimate; does not guarantee orbiting or a taut rope)"},
    "cfg.len_manual": {"pt": "manual", "en": "manual"},
    "inap.bend": {"pt": "o trecho livre do modelo wrap_tether não tem rigidez à flexão",
                  "en": "the free span of the wrap_tether model has no bending stiffness"},
    "inap.twist": {"pt": "o modelo wrap_tether não representa torção da corda",
                   "en": "the wrap_tether model does not represent rope torsion"},
    "inap.self": {"pt": "a hélice tem passo >= diâmetro e as espiras não se tocam; o trecho livre é um único vão "
                        "e não pode colidir consigo",
                  "en": "the helix pitch is >= the diameter so coils never touch; the free span is a single "
                        "segment and cannot self-collide"},
    "inap.ground": {"pt": "o trecho livre parte da hélice no alto e só alcança o solo na ponta presa ao objeto; "
                          "contato corda-solo não é modelado",
                    "en": "the free span leaves the helix near the top and only reaches the ground at the "
                          "object end; rope–ground contact is not modelled"},
    "inap.locked": {"pt": "só se aplica com rope.coil_sliding: true (espiras travadas não deslizam)",
                    "en": "only applies with rope.coil_sliding: true (locked coils do not slide)"},
    # ------------------------------------------------------------- métricas/notas
    "note.reach_short": {"pt": "comprimento insuficiente: o objeto fica suspenso mesmo com a corda totalmente "
                               "desenrolada",
                         "en": "rope too short: the object stays suspended even with the rope fully unwound"},
    "note.reach_ok": {"pt": "comprimento permite alcançar o solo", "en": "the length allows reaching the ground"},
    "note.reach_margin": {
        "pt": "margem = L_rep·T_máx_solo/EA − max(caminho − L_rep) no solo; ≥ 0 indica que a corda tensa limitou "
              "o alcance ao comprimento elástico",
        "en": "margin = L_rest·T_max_ground/EA − max(path − L_rest) on the ground; ≥ 0 means the taut rope "
              "limited the reach to its elastic length"},
    "note.anchor": {"pt": "estimativa de cabrestante com atrito mobilizado: T·exp(-μ·u_armazenado)",
                    "en": "capstan estimate with fully mobilised friction: T·exp(-μ·u_stored)"},
    "note.coil_slip": {
        "pt": "razão = |componente vertical do vão em P1| / (1 - exp(-μ u_armazenado)); > 1 indica que a hipótese "
              "de espiras travadas exigiria mais atrito que o disponível (o modelo não simula o escorregamento "
              "das espiras)",
        "en": "ratio = |vertical component of the span at P1| / (1 - exp(-μ u_stored)); > 1 means the locked-coil "
              "assumption would need more friction than available (coil slipping is not simulated)"},
    "note.impacts": {
        "pt": "picos dependem de contact.solref, contact.solimp e do passo de tempo; o limiar em g é ilustrativo "
              "e não é critério de lesão validado",
        "en": "peaks depend on contact.solref, contact.solimp and the time step; the g threshold is illustrative "
              "and is not a validated injury criterion"},
    "note.azimuth": {
        "pt": "azimute 0 = ao longo do vão livre inicial, para longe da chaminé; positivo gira para o sentido de "
              "desenrolar (normal externa no ponto de saída)",
        "en": "azimuth 0 = along the initial free span, away from the chimney; positive turns toward the "
              "unwinding direction (outward normal at the departure point)"},
    "criterion": {"pt": "{metric} vs limiar {thr:g} {unit}, aviso em {wf:g}×",
                  "en": "{metric} vs threshold {thr:g} {unit}, warning at {wf:g}×"},
    "criterion.g": {"pt": "desaceleração (g)", "en": "deceleration (g)"},
    "criterion.N": {"pt": "força filtrada (N)", "en": "filtered force (N)"},
    "conv.base": {"pt": "base", "en": "baseline"},
    "conv.space": {"pt": "resolução espacial ×2", "en": "spatial resolution ×2"},
    "conv.time": {"pt": "timestep ÷2", "en": "timestep ÷2"},
    "conv.note": {"pt": "se alguma métrica variar mais que a tolerância, o resultado é marcado como não confiável",
                  "en": "if any metric changes more than the tolerance, the result is flagged as unreliable"},
    # ------------------------------------------------------------- relatório
    "r.yes": {"pt": "Sim", "en": "Yes"},
    "r.no": {"pt": "Não", "en": "No"},
    "r.turns": {"pt": "voltas", "en": "turns"},
    "r.none": {"pt": "nenhum", "en": "none"},
    "r.q_spiral": {"pt": "Houve espiral?", "en": "Did it spiral?"},
    "r.a_spiral": {"pt": "{yn}: {turns} do objeto em torno da torre antes do solo; a hélice liberou {unw} ({s0} → {s1}).",
                   "en": "{yn}: {turns} of the object around the tower before the ground; the helix released "
                         "{unw} ({s0} → {s1})."},
    "r.q_hit": {"pt": "Houve colisão com a estrutura?", "en": "Did it hit the structure?"},
    "r.a_hit": {"pt": "{yn} (contatos com a torre: {n}; acima de {thr} m/s normal: {nh}). Distância mínima à parede: {wd}.",
                "en": "{yn} (tower contacts: {n}; above {thr} m/s normal speed: {nh}). Minimum wall distance: {wd}."},
    "r.q_ground": {"pt": "Velocidade/força de chegada ao solo", "en": "Ground arrival speed/force"},
    "r.a_ground": {"pt": "{v} (normal {vn}, tangencial {vt}) em t = {t}; 1º evento: {ev}.",
                   "en": "{v} (normal {vn}, tangential {vt}) at t = {t}; first event: {ev}."},
    "r.first_ev": {"pt": "pico filtrado {f}, {g} ({cls})", "en": "filtered peak {f}, {g} ({cls})"},
    "r.q_struct": {"pt": "Chegada à estrutura", "en": "Structure arrival"},
    "r.a_struct": {"pt": "{v} (normal {vn}) em t = {t}.", "en": "{v} (normal {vn}) at t = {t}."},
    "r.no_tower": {"pt": "sem contato com a torre.", "en": "no tower contact."},
    "r.q_slide": {"pt": "Quanto deslizou?", "en": "How far did it slide?"},
    "r.a_slide": {"pt": "Percurso horizontal após o 1º toque {path}; deslocamento líquido {net}; varredura angular em "
                        "torno da torre {ang}; saltos/tombos {hops} (maior altura do ponto mais baixo {lift}); "
                        "repouso após {rest}.",
                  "en": "Horizontal path after first touchdown {path}; net displacement {net}; angle swept around "
                        "the tower {ang}; hops/tumbles {hops} (highest lowest-point lift {lift}); at rest after {rest}."},
    "r.q_slack": {"pt": "A corda afrouxou ou reenrolou?", "en": "Did the rope go slack or rewind?"},
    "r.a_slack": {"pt": "Folga total {tot} (ar {air}, solo {gr}, {n} episódios, máx. {mx}); reenrolamento máximo {rw}.",
                  "en": "Total slack {tot} (air {air}, ground {gr}, {n} episodes, max {mx}); maximum rewind {rw}."},
    "r.q_tension": {"pt": "Tração máxima", "en": "Maximum tension"},
    "r.a_tension": {"pt": "{T} no objeto (t = {t}); na âncora {Ta} (cabrestante); ruptura {Tb}; alerta {w}.",
                    "en": "{T} at the object (t = {t}); at the anchor {Ta} (capstan); breaking load {Tb}; "
                          "warning {w}."},
    "r.alert_on": {"pt": "ATIVADO", "en": "ON"},
    "r.alert_off": {"pt": "não", "en": "off"},
    "r.q_impact": {"pt": "Maior impacto", "en": "Largest impact"},
    "r.a_impact": {"pt": "{surf} em t = {t}: {g}, pico bruto {f} — {cls}.",
                   "en": "{surf} at t = {t}: {g}, raw peak {f} — {cls}."},
    "r.title": {"pt": "Simulação", "en": "Simulation"},
    "r.notice": {"pt": "Aviso", "en": "Notice"},
    "r.outcome": {"pt": "Desfecho", "en": "Outcome"},
    "r.meta": {"pt": "Modelo de corda `{model}`, MuJoCo {mj}, dt = {dt} s, t simulado = {ts} s, relógio = {tw} s, "
                     "config `{h}`, seed {seed}.",
               "en": "Rope model `{model}`, MuJoCo {mj}, dt = {dt} s, simulated t = {ts} s, wall clock = {tw} s, "
                     "config `{h}`, seed {seed}."},
    "r.answers": {"pt": "Respostas", "en": "Answers"},
    "r.length": {"pt": "Comprimento da corda", "en": "Rope length"},
    "r.len_line": {"pt": "L = {L} m ({src}).", "en": "L = {L} m ({src})."},
    "r.len_est": {"pt": "Estimativa original: {f} → v = {v} m/s, r_min = {r} m, L = {L} m (ponto de partida "
                        "simplificado; não garante órbita nem corda tensa).",
                  "en": "Original estimate: {f} → v = {v} m/s, r_min = {r} m, L = {L} m (simplified starting point; "
                        "does not guarantee orbiting or a taut rope)."},
    "r.reach": {"pt": "Alcance do solo: {note} (mínimo {m} m).", "en": "Ground reach: {note} (minimum {m} m)."},
    "r.energy": {"pt": "Energia", "en": "Energy"},
    "r.term": {"pt": "termo", "en": "term"},
    "r.convergence": {"pt": "Convergência", "en": "Convergence"},
    "r.variant": {"pt": "variante", "en": "variant"},
    "r.v_arr": {"pt": "v chegada (m/s)", "en": "arrival v (m/s)"},
    "r.slide": {"pt": "deslizamento (m)", "en": "slide (m)"},
    "r.tmax": {"pt": "tração máx (N)", "en": "max tension (N)"},
    "r.conv_line": {"pt": "Variação máxima {c} (limite {tol}): {verdict}.", "en": "Maximum change {c} (limit {tol}): {verdict}."},
    "r.reliable": {"pt": "confiável", "en": "reliable"},
    "r.unreliable": {"pt": "NÃO CONFIÁVEL", "en": "NOT RELIABLE"},
    "r.impacts": {"pt": "Impactos", "en": "Impacts"},
    "r.criterion": {"pt": "Critério", "en": "Criterion"},
    "r.warnings": {"pt": "Avisos", "en": "Warnings"},
    "r.inapplicable": {"pt": "Parâmetros inaplicáveis ao modelo", "en": "Parameters not applicable to the model"},
    "r.plots": {"pt": "Gráficos", "en": "Plots"},
    "r.ev_cols": {"pt": "superfície|t (s)|duração (s)|v (m/s)|v normal|F bruta (N)|F filtrada (N)|impulso (N·s)|g|classe|geoms",
                  "en": "surface|t (s)|duration (s)|v (m/s)|normal v|raw F (N)|filtered F (N)|impulse (N·s)|g|class|geoms"},
    "e.initial_J": {"pt": "energia mecânica inicial", "en": "initial mechanical energy"},
    "e.final_J": {"pt": "energia mecânica final", "en": "final mechanical energy"},
    "e.drag_object_work_J": {"pt": "trabalho do arrasto sobre o objeto", "en": "drag work on the object"},
    "e.wind_input_J": {"pt": "aporte do vento (parcela do arrasto)", "en": "wind input (part of drag)"},
    "e.rope_distributed_work_J": {"pt": "trabalho de peso/arrasto distribuídos da corda",
                                  "en": "work of distributed rope weight/drag"},
    "e.rope_axial_damping_J": {"pt": "dissipado no amortecimento axial", "en": "dissipated by axial damping"},
    "e.rope_peel_kink_J": {"pt": "dissipado na dobra de saída e na inserção de material",
                           "en": "dissipated at the departure kink and material insertion"},
    "e.coil_wall_friction_J": {"pt": "dissipado por atrito das espiras na parede", "en": "dissipated by coil–wall friction"},
    "e.coil_mass_transfer_J": {"pt": "energia levada pelo material que passou da parede ao vão (contábil)",
                               "en": "energy carried by material moving from the wall to the span (bookkeeping)"},
    "e.launch_force_work_J": {"pt": "trabalho da força de lançamento (com duração)",
                              "en": "launch force work (with duration)"},
    "e.contact_and_residual_J": {"pt": "contato/atrito (resíduo do balanço)",
                                 "en": "contact/friction (balance residual)"},
    "e.flight_balance_residual_max_J": {"pt": "resíduo máximo do balanço em voo (erro numérico)",
                                        "en": "max in-flight balance residual (numerical error)"},
    # ------------------------------------------------------------- gráficos
    "p.traj3d": {"pt": "Trajetória 3D", "en": "3D trajectory"},
    "p.com": {"pt": "centro de massa", "en": "centre of mass"},
    "p.depart": {"pt": "ponto de saída da corda", "en": "rope departure point"},
    "p.first_ground": {"pt": "1º toque no solo", "en": "first touchdown"},
    "p.top": {"pt": "Vista superior (torre em cinza)", "en": "Top view (tower in grey)"},
    "p.on_ground": {"pt": "no solo (após 1º toque)", "en": "on the ground (after touchdown)"},
    "p.touch": {"pt": "1º toque", "en": "touchdown"},
    "p.start": {"pt": "início", "en": "start"},
    "p.end": {"pt": "final", "en": "end"},
    "p.ground": {"pt": "solo", "en": "ground"},
    "p.time": {"pt": "tempo (s)", "en": "time (s)"},
    "p.height": {"pt": "Altura", "en": "Height"},
    "p.lowest": {"pt": "ponto mais baixo", "en": "lowest point"},
    "p.speed": {"pt": "Velocidade do centro de massa", "en": "Centre-of-mass speed"},
    "p.speed_l": {"pt": "velocidade", "en": "speed"},
    "p.wall": {"pt": "Distância objeto–parede", "en": "Object–wall distance"},
    "p.wall_l": {"pt": "distância", "en": "distance"},
    "p.wall_line": {"pt": "parede", "en": "wall"},
    "p.tension": {"pt": "Tração na corda", "en": "Rope tension"},
    "p.t_obj": {"pt": "no objeto", "en": "at the object"},
    "p.t_anchor": {"pt": "na âncora (cabrestante)", "en": "at the anchor (capstan)"},
    "p.load_warn": {"pt": "alerta de carga", "en": "load warning"},
    "p.wound": {"pt": "Corda enrolada e livre", "en": "Wound and free rope"},
    "p.stored": {"pt": "hélice armazenada", "en": "stored helix"},
    "p.contact": {"pt": "em contato com a torre", "en": "in contact with the tower"},
    "p.free": {"pt": "vão livre (geométrico)", "en": "free span (geometric)"},
    "p.energy": {"pt": "Energia mecânica e perdas acumuladas", "en": "Mechanical energy and cumulative losses"},
    "p.e_total": {"pt": "energia mecânica (objeto + elástica)", "en": "mechanical energy (object + elastic)"},
    "p.e_peel": {"pt": "perda na dobra de saída", "en": "departure-kink loss"},
    "p.e_damp": {"pt": "amortecimento axial", "en": "axial damping"},
    "p.e_drag": {"pt": "arrasto do ar sobre o objeto", "en": "air drag on the object"},
    "p.impacts": {"pt": "Impactos (eventos agrupados)", "en": "Impacts (grouped events)"},
    "p.no_impacts": {"pt": "nenhum impacto", "en": "no impacts"},
    "p.peak_g": {"pt": "desaceleração de pico (g)", "en": "peak deceleration (g)"},
    "p.tower": {"pt": "torre", "en": "tower"},
    # ------------------------------------------------------------- servidor web
    "w.writing": {"pt": "gravando artefatos (CSV, JSON, HTML, gráficos)…", "en": "writing artifacts (CSV, JSON, HTML, plots)…"},
    "w.sim_fail": {"pt": "falha na simulação: {e}", "en": "simulation failed: {e}"},
    "w.render_fail": {"pt": "falha na renderização: {e}", "en": "rendering failed: {e}"},
    "w.bad_config": {"pt": "configuração inválida: {e}", "en": "invalid configuration: {e}"},
    "w.cant_start": {"pt": "não foi possível iniciar: {e}", "en": "could not start: {e}"},
    "w.no_session": {"pt": "nenhuma simulação ativa nesta sessão", "en": "no active simulation in this session"},
    "w.busy": {"pt": "servidor ocupado: {n} de {max} simulações simultâneas em uso; tente em instantes",
               "en": "server busy: {n} of {max} concurrent simulations in use; please try again shortly"},
}
