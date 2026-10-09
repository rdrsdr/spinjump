"""Linha de comando: ``python -m spinjump {run,sweep,report,rope-length,selftest,serve}``.

Não emite logs de progresso nem de impactos: os resultados vão para os
artefatos em ``out/`` e para um retorno curto no terminal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from .config import SimConfig, auto_rope_length, list_presets, load_config, resolve
from .i18n import set_lang, t
from .sim import safety_notice


def _cfg_args(p: argparse.ArgumentParser):
    p.add_argument("--config", "-c", help="arquivo YAML (mesclado sobre configs/default.yaml)")
    p.add_argument("--preset", "-p", help=f"preset em configs/presets ({', '.join(list_presets())})")
    p.add_argument("--set", "-s", action="append", default=[], metavar="caminho=valor",
                   help="override repetível, ex.: --set launch.impulse_Ns=400")
    p.add_argument("--name", help="nome da execução (pasta de saída)")
    p.add_argument("--out", help="diretório base de saída (padrão: out/)")


def _load(a) -> SimConfig:
    extra = {"name": a.name} if getattr(a, "name", None) else None
    return load_config(a.config, a.preset, a.set, extra)


def cmd_run(a) -> int:
    from .convergence import study
    from .report import run_dir, write_artifacts
    from .sim import Simulation
    cfg = _load(a)
    sim = Simulation(cfg).run()
    extra = {}
    if a.convergence:
        tr = sim.tr
        base = dict(outcome=sim.outcome, arrival_speed_ms=round(tr.first_ground_speed or 0.0, 4),
                    slide_path_m=round(tr.slide_path, 4), tension_max_N=round(tr.t_max, 2),
                    timestep_s=sim.cfg.solver.timestep_s, element_length_m=sim.cfg.rope.element_length_m)
        extra["convergence"] = study(sim.cfg, base=base)
        if not extra["convergence"]["reliable"]:
            sim.warnings.append(t("warn.unreliable"))
    out = run_dir(sim.cfg.name, a.out)
    s = write_artifacts(sim, out, extra)
    _print_brief(s, out)
    return 0 if sim.outcome != "NUMERICAL_FAILURE" else 2


def _print_brief(s: dict, out: Path):
    sp, ga, gp, ro, oc = s["spiral"], s["ground_arrival"], s["ground_phase"], s["rope"], s["outcome"]
    mx = s["impacts"]["max_event"]
    print(f"desfecho: {oc['code']}  ({oc['text']})")
    print(f"voltas antes do solo: {sp['object_turns_before_ground']}  | hélice: {sp['stored_turns_initial']} → "
          f"{sp['stored_turns_at_ground']} voltas  | distância mínima à parede: {sp['min_wall_distance_m']} m")
    print(f"chegada ao solo: {ga['speed_ms']} m/s em t={ga['t_s']} s  | deslizamento: {gp['slide_path_m']} m  | "
          f"varredura no solo: {gp['angle_swept_after_ground_deg']}°")
    print(f"tração máx: {ro['tension_max_N']} N  | folga: {ro['slack_time_total_s']} s  | reenrolamento: "
          f"{ro['rewind_max_turns']} voltas  | maior impacto: "
          + (f"{mx['decel_peak_g']} g {mx['classification']} ({mx['surface']})" if mx else "nenhum"))
    if "convergence" in s:
        cv = s["convergence"]
        print(f"convergência: variação máx {cv['max_rel_change']} → {'confiável' if cv['reliable'] else 'NÃO CONFIÁVEL'}")
    for w in s["warnings"]:
        print(f"aviso: {w}")
    print(f"artefatos: {out}")
    print(safety_notice())


def cmd_report(a) -> int:
    from .report import render_html, render_md
    d = Path(a.run_dir)
    s = json.loads((d / "summary.json").read_text())
    plots = [p for p in s.get("artifacts", []) if p.endswith(".png")]
    if a.rerun:
        from .metrics import summarize
        from .sim import Simulation
        raw = yaml.safe_load((d / "config_resolved.yaml").read_text())
        raw.pop("_resolution", None)
        sim = Simulation(SimConfig.model_validate(raw), resolved=True).run()
        s2 = summarize(sim)
        keys = [("spiral", "object_turns_before_ground"), ("ground_arrival", "speed_ms"),
                ("ground_phase", "slide_path_m"), ("rope", "tension_max_N")]
        same = all(s2[a_][b_] == s[a_][b_] for a_, b_ in keys)
        print("reexecução determinística: " + ("métricas idênticas" if same else "MÉTRICAS DIFERENTES"))
        for a_, b_ in keys:
            print(f"  {a_}.{b_}: {s[a_][b_]} → {s2[a_][b_]}")
        if not same:
            return 3
    events = json.loads((d / "events.json").read_text())["events"]
    (d / "summary.md").write_text(render_md(s, plots))
    (d / "summary.html").write_text(render_html(dict(s, _events_for_html=events), plots))
    _print_brief(s, d)
    return 0


def cmd_rope_length(a) -> int:
    cfg = _load(a)
    rc, notes = resolve(cfg)
    H = a.height if a.height is not None else rc.tower.height_m
    v0 = a.v0 if a.v0 is not None else notes["launch"]["speed_ms"]
    est = auto_rope_length(H, v0)
    print(f"fórmula: {est['formula']}")
    print(f"H = {H} m, v0 = {v0:.3f} m/s → v = {est['v_ms']:.3f} m/s, r_min = {est['r_min_m']:.3f} m, "
          f"L = {est['L_m']:.3f} m")
    if a.height is None and a.v0 is None:
        from .sim import Simulation
        sim = Simulation(cfg)
        lay = sim.layout
        print(f"comprimento resolvido: {rc.rope.length_m} m ({notes['rope_length_source']})")
        print(f"hélice inicial: {lay['turns0']:.3f} voltas ({lay['wound0']:.2f} m), altura {lay['helix_height']*100:.1f} cm; "
              f"vão livre inicial {lay['free0']:.3f} m")
        for w in sim.warnings:
            print(f"aviso: {w}")
    print("hipóteses: queda livre de H com v0, alcance horizontal r_min = v·sqrt(H/g); estimativa "
          "simplificada, não garante órbita, corda tensa nem ausência de levantamento no solo")
    return 0


def cmd_sweep(a) -> int:
    from .sweep import run_sweep
    cfg = _load(a)
    out = run_sweep(cfg, a.param, a.seeds, a.out, a.workers, a.metric)
    print(f"varredura: {out['n_runs']} execuções; CSV: {out['csv']}")
    for h in out["heatmaps"]:
        print(f"mapa de calor: {h}")
    print(safety_notice())
    return 0


def cmd_selftest(a) -> int:
    from .selftest import run_selftest
    ok = run_selftest(render=not a.no_render)
    return 0 if ok else 1


def cmd_serve(a) -> int:
    set_lang(a.lang)
    from .web.server import serve
    serve(a.host, a.port)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m spinjump", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="executa uma simulação e grava artefatos")
    _cfg_args(r)
    r.add_argument("--convergence", action="store_true",
                   help="repete com resolução espacial ×2 e timestep ÷2 e marca a confiabilidade")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("sweep", help="varredura de parâmetros/seeds (CSV + mapas de calor)")
    _cfg_args(s)
    s.add_argument("--param", action="append", required=True, metavar="caminho=v1,v2,...",
                   help="parâmetro a variar (1 ou 2 vezes)")
    s.add_argument("--seeds", default="", help="lista de seeds de vento, ex.: 1,2,3")
    s.add_argument("--workers", type=int, default=0, help="processos paralelos (0 = automático)")
    s.add_argument("--metric", action="append", default=[], help="métricas dos mapas de calor")
    s.set_defaults(fn=cmd_sweep)
    rp = sub.add_parser("report", help="regera summary.md/html de uma pasta de execução")
    rp.add_argument("run_dir")
    rp.add_argument("--rerun", action="store_true", help="reexecuta e confere determinismo")
    rp.set_defaults(fn=cmd_report)
    rl = sub.add_parser("rope-length", help="estimativa do comprimento da corda")
    _cfg_args(rl)
    rl.add_argument("--height", type=float)
    rl.add_argument("--v0", type=float)
    rl.set_defaults(fn=cmd_rope_length)
    st = sub.add_parser("selftest", help="verificações rápidas do ambiente e da física")
    st.add_argument("--no-render", action="store_true")
    st.set_defaults(fn=cmd_selftest)
    sv = sub.add_parser("serve", help="interface web ao vivo")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")),
                    help="porta (padrão: variável PORT ou 8000)")
    sv.add_argument("--lang", choices=["en", "pt"], default=os.environ.get("SPINJUMP_WEB_LANG", "en"),
                    help="idioma da interface e dos relatórios gerados por ela (padrão: en)")
    sv.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
