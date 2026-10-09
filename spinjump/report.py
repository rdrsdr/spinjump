"""Artefatos de uma execução em ``out/<data>_<nome>/`` (sem vídeo, GIF ou replay)."""
from __future__ import annotations

import csv
import datetime as _dt
import html
import json
import os
import re
from pathlib import Path

import numpy as np
import yaml

from .config import REPO_DIR, to_plain
from .metrics import summarize
from .plots import STATUS, make_all
from .i18n import get_lang, t
from .sim import TELEMETRY_FIELDS, Simulation, safety_notice

OUT_DIR = Path(os.environ.get("SPINJUMP_OUT", REPO_DIR / "out"))


def run_dir(name: str, base: Path | None = None) -> Path:
    base = Path(base) if base else OUT_DIR
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name)[:60] or "run"
    d = base / f"{stamp}_{safe}"
    k = 1
    while d.exists():
        k += 1
        d = base / f"{stamp}_{safe}-{k}"
    d.mkdir(parents=True)
    return d


RUN_DIR_RE = re.compile(r"^\d{8}-\d{6}_")


def prune_runs(keep: int, base: Path | None = None) -> int:
    """Mantém só as ``keep`` execuções mais recentes em ``base`` (pastas ``<data>_<nome>``).

    Usado em implantações públicas (variável SPINJUMP_KEEP_RUNS); localmente nada é apagado.
    """
    import shutil
    base = Path(base) if base else OUT_DIR
    runs = sorted(p for p in base.iterdir() if p.is_dir() and RUN_DIR_RE.match(p.name))
    old = runs[:-keep] if keep > 0 else []
    for p in old:
        shutil.rmtree(p, ignore_errors=True)
    return len(old)


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


def write_artifacts(sim: Simulation, outdir: Path, extra: dict | None = None) -> dict:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = summarize(sim)
    if extra:
        summary.update(extra)
    resolved = to_plain(sim.cfg)
    lay = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in sim.layout.items()}
    resolved["_resolution"] = json.loads(json.dumps(dict(notes=sim.notes, initial_layout=lay,
                                                          launch_frame=sim.launch_frame),
                                                     default=_json_default))
    (outdir / "config_resolved.yaml").write_text(
        "# Configuração resolvida (presets, comprimento 'auto' e impulso aplicados).\n"
        f"# {safety_notice()}\n" + yaml.safe_dump(resolved, sort_keys=False, allow_unicode=True))
    with open(outdir / "timeseries.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(TELEMETRY_FIELDS)
        for row in sim.samples:
            w.writerow([f"{x:.6g}" if isinstance(x, float) else x for x in row])
    (outdir / "events.json").write_text(json.dumps(
        dict(events=sim.impacts.events, criterion=summary["impacts"]["criterion"],
             note=summary["impacts"]["note"]), indent=1, ensure_ascii=False, default=_json_default))
    plots = make_all(sim, summary, outdir)
    summary["artifacts"] = ["config_resolved.yaml", "timeseries.csv", "events.json", "summary.json",
                            "summary.md", "summary.html"] + plots
    (outdir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False,
                                                    default=_json_default))
    (outdir / "summary.md").write_text(render_md(summary, plots))
    (outdir / "summary.html").write_text(render_html(dict(summary, _events_for_html=sim.impacts.events), plots))
    return summary


# ------------------------------------------------------------------ texto

ENERGY_KEYS = ("initial_J", "final_J", "drag_object_work_J", "wind_input_J", "rope_distributed_work_J",
               "rope_axial_damping_J", "rope_peel_kink_J", "launch_force_work_J", "contact_and_residual_J",
               "flight_balance_residual_max_J")


def energy_label(k: str) -> str:
    return t(f"e.{k}") if k in ENERGY_KEYS else k


def class_label(code: str) -> str:
    return t(f"class.{code}") if code in ("OK", "ATENÇÃO", "DANO") else str(code)


def _f(x, unit="", nd=2):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return t("r.yes") if x else t("r.no")
    if isinstance(x, (int, float)):
        return f"{x:.{nd}f}{(' ' + unit) if unit else ''}"
    return str(x)


def answers(s: dict) -> list[tuple[str, str]]:
    sp, ga, sa, gp, ro, im, fl = (s["spiral"], s["ground_arrival"], s["structure_arrival"], s["ground_phase"],
                                  s["rope"], s["impacts"], s["outcome"]["flags"])
    mx = im["max_event"]
    turns = t("r.turns")
    fe = ga["first_event"]
    first = (t("r.first_ev", f=_f(fe["force_normal_peak_filtered_N"], "N", 0), g=_f(fe["decel_peak_g"], "g", 1),
               cls=class_label(fe["classification"])) if fe else "—")
    return [
        (t("r.q_spiral"), t("r.a_spiral", yn=_f(bool(fl["spiral_before_ground"])),
                             turns=_f(sp["object_turns_before_ground"], turns),
                             unw=_f(sp["unwound_turns_before_ground"], turns), s0=_f(sp["stored_turns_initial"]),
                             s1=_f(sp["stored_turns_at_ground"]))),
        (t("r.q_hit"), t("r.a_hit", yn=_f(bool(fl["structure_hit"])), n=im["count_tower"],
                          thr=sa["threshold_v_normal_ms"], nh=sa["hits_above_threshold"],
                          wd=_f(sp["min_wall_distance_m"], "m", 3))),
        (t("r.q_ground"), t("r.a_ground", v=_f(ga["speed_ms"], "m/s"), vn=_f(ga["v_normal_ms"], "m/s"),
                             vt=_f(ga["v_tangential_ms"], "m/s"), t=_f(ga["t_s"], "s"), ev=first)),
        (t("r.q_struct"), t("r.a_struct", v=_f(sa["speed_ms"], "m/s"), vn=_f(sa["v_normal_ms"], "m/s"),
                             t=_f(sa["t_s"], "s")) if sa["t_s"] is not None else t("r.no_tower")),
        (t("r.q_slide"), t("r.a_slide", path=_f(gp["slide_path_m"], "m"), net=_f(gp["net_displacement_m"], "m"),
                            ang=_f(gp["angle_swept_after_ground_deg"], "°", 1), hops=gp["ground_hops"],
                            lift=_f(gp["max_lift_after_ground_m"], "m"), rest=_f(gp["time_ground_to_rest_s"], "s"))),
        (t("r.q_slack"), t("r.a_slack", tot=_f(ro["slack_time_total_s"], "s"), air=_f(ro["slack_time_air_s"], "s"),
                            gr=_f(ro["slack_time_ground_s"], "s"), n=ro["slack_episodes"],
                            mx=_f(ro["slack_max_m"], "m", 3), rw=_f(ro["rewind_max_turns"], turns))),
        (t("r.q_tension"), t("r.a_tension", T=_f(ro["tension_max_N"], "N", 0), t=_f(ro["tension_max_t_s"], "s"),
                              Ta=_f(ro["tension_anchor_max_N"], "N", 0), Tb=_f(ro["breaking_load_N"], "N", 0),
                              w=t("r.alert_on") if fl["load_warning"] else t("r.alert_off"))),
        (t("r.q_impact"), t("r.a_impact", surf=t(f"surface.{mx['surface']}"), t=_f(mx["t_start"], "s"),
                             g=_f(mx["decel_peak_g"], "g", 1), f=_f(mx["force_normal_peak_raw_N"], "N", 0),
                             cls=class_label(mx["classification"])) if mx else t("r.none") + "."),
    ]


def _meta_line(m: dict) -> str:
    return t("r.meta", model=m["rope_model"], mj=m["mujoco"], dt=m["timestep_s"], ts=m["sim_time_s"],
             tw=m["wall_clock_s"], h=m["config_hash"], seed=m["seed"])


def render_md(s: dict, plots: list[str]) -> str:
    m, oc = s["meta"], s["outcome"]
    lines = [f"# {t('r.title')}: {m['name']}", "", f"> **{t('r.notice')}:** {m['safety_notice']}", "",
             f"**{t('r.outcome')}:** `{oc['code']}` — {oc['text']}" + (f" ({oc['failure']})" if oc["failure"] else ""),
             "", _meta_line(m), "", f"## {t('r.answers')}", ""]
    for q, a in answers(s):
        lines.append(f"- **{q}** {a}")
    ro = s["rope"]
    est = ro["length_estimate"]
    lines += ["", f"## {t('r.length')}", "",
              "- " + t("r.len_line", L=ro["length_m"], src=ro["length_source"]),
              "- " + t("r.len_est", f=est["formula"], v=est["v_ms"], r=est["r_min_m"], L=est["L_m"]),
              "- " + t("r.reach", note=ro["ground_reach"]["note"], m=ro["ground_reach"]["L_min_to_ground_m"]),
              "", f"## {t('r.energy')}", "", f"| {t('r.term')} | J |", "|---|---|"]
    for k, v in s["energy"].items():
        lines.append(f"| {energy_label(k)} | {v} |")
    if "convergence" in s:
        lines += ["", f"## {t('r.convergence')}", "", _conv_md(s["convergence"])]
    lines += ["", f"## {t('r.impacts')}", "", f"{t('r.criterion')}: {s['impacts']['criterion']}. "
              f"{s['impacts']['note']}.", ""]
    if s["warnings"]:
        lines += [f"## {t('r.warnings')}", ""] + [f"- {w}" for w in s["warnings"]] + [""]
    lines += [f"## {t('r.inapplicable')}", ""]
    for k, v in s["inapplicable_params"].items():
        lines.append(f"- `{k}`: {v}")
    lines += ["", f"## {t('r.plots')}", ""] + [f"![{p}]({p})" for p in plots]
    return "\n".join(lines) + "\n"


def _conv_verdict(cv: dict) -> str:
    return t("r.reliable") if cv["reliable"] else t("r.unreliable")


def _conv_md(cv: dict) -> str:
    rows = [f"| {t('r.variant')} | {t('r.v_arr')} | {t('r.slide')} | {t('r.tmax')} |", "|---|---|---|---|"]
    for r in cv["runs"]:
        rows.append(f"| {r['label']} | {r['arrival_speed_ms']} | {r['slide_path_m']} | {r['tension_max_N']} |")
    rows.append("")
    rows.append(t("r.conv_line", c=cv["max_rel_change"], tol=cv["tolerance"], verdict=_conv_verdict(cv)))
    return "\n".join(rows)


def render_html(s: dict, plots: list[str]) -> str:
    m, oc = s["meta"], s["outcome"]
    esc = html.escape

    def badge(cls):
        col = STATUS.get(cls, "#898781")
        icon = {"OK": "✓", "ATENÇÃO": "!", "DANO": "✕"}.get(cls, "•")
        return (f'<span class="badge" style="border-color:{col}"><span class="dot" style="background:{col}">'
                f'{icon}</span>{esc(class_label(cls))}</span>')

    ev_rows = []
    for e in s.get("_events_for_html", []):
        ev_rows.append(
            f"<tr><td>{esc(t('surface.' + e['surface']))}</td><td>{e['t_start']}</td><td>{e['duration_s']}</td>"
            f"<td>{e['speed_in_ms']}</td><td>{e['v_normal_in_ms']}</td><td>{e['force_normal_peak_raw_N']}</td>"
            f"<td>{e['force_normal_peak_filtered_N']}</td><td>{e['impulse_normal_impact_Ns']}</td>"
            f"<td>{e['decel_peak_g']}</td><td>{badge(e['classification'])}</td>"
            f"<td>{esc(', '.join(e['geoms']))}</td></tr>")
    ev_head = "".join(f"<th>{esc(c)}</th>" for c in t("r.ev_cols").split("|"))
    ans = "".join(f"<dt>{esc(q)}</dt><dd>{esc(a)}</dd>" for q, a in answers(s))
    energy = "".join(f"<tr><td>{esc(energy_label(k))}</td><td class='num'>{v}</td></tr>"
                     for k, v in s["energy"].items())
    warns = "".join(f"<li>{esc(w)}</li>" for w in s["warnings"])
    inap = "".join(f"<li><code>{esc(k)}</code>: {esc(v)}</li>" for k, v in s["inapplicable_params"].items())
    conv = ""
    if "convergence" in s:
        cv = s["convergence"]
        rows = "".join(f"<tr><td>{esc(r['label'])}</td><td class='num'>{r['arrival_speed_ms']}</td>"
                       f"<td class='num'>{r['slide_path_m']}</td><td class='num'>{r['tension_max_N']}</td></tr>"
                       for r in cv["runs"])
        conv = (f"<h2>{t('r.convergence')}</h2><table><tr><th>{t('r.variant')}</th><th>{t('r.v_arr')}</th>"
                f"<th>{t('r.slide')}</th><th>{t('r.tmax')}</th></tr>{rows}</table>"
                f"<p>{badge('OK' if cv['reliable'] else 'DANO')} "
                f"{esc(t('r.conv_line', c=cv['max_rel_change'], tol=cv['tolerance'], verdict=_conv_verdict(cv)))}</p>")
    imgs = "".join(f'<figure><img src="{p}" alt="{esc(p)}"></figure>' for p in plots)
    oc_col = "#0ca30c" if oc["code"] == "AT_REST_CLEAN" else ("#d03b3b" if oc["code"] in (
        "HIT_STRUCTURE", "NUMERICAL_FAILURE") else "#fab219")
    lang = "pt-BR" if get_lang() == "pt" else "en"
    meta = esc(_meta_line(m)).replace("`", "")
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpinJump · {esc(t('r.title'))} {esc(m['name'])}</title>
<style>
:root{{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9}}
body{{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:16px}}
.warn{{border-left:4px solid #d03b3b;background:#fff;padding:10px 14px;margin:12px 0}}
.outcome{{border-left:6px solid {oc_col};background:#fff;padding:10px 14px;font-size:16px}}
table{{border-collapse:collapse;background:var(--surface);width:100%;margin:8px 0;font-size:13px}}
td,th{{border-bottom:1px solid var(--grid);padding:4px 8px;text-align:left}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
dt{{font-weight:600;margin-top:8px}} dd{{margin:2px 0 0 0;color:var(--ink2)}}
.badge{{display:inline-flex;gap:4px;align-items:center;border:1px solid;border-radius:10px;padding:0 6px 0 2px;font-size:12px}}
.dot{{display:inline-block;width:14px;height:14px;border-radius:7px;color:#fff;font-size:10px;text-align:center;line-height:14px}}
figure{{margin:12px 0;background:var(--surface)}} img{{max-width:100%;height:auto}}
.scroll{{overflow-x:auto}}
</style></head><body><main>
<h1>SpinJump · {esc(t('r.title'))}: {esc(m['name'])}</h1>
<div class="warn"><strong>{esc(t('r.notice'))}:</strong> {esc(m['safety_notice'])}</div>
<div class="outcome"><strong>{esc(oc['code'])}</strong> — {esc(oc['text'])} {esc(oc['failure'] or '')}</div>
<p>{meta}</p>
<h2>{esc(t('r.answers'))}</h2><dl>{ans}</dl>
{conv}
<h2>{esc(t('r.energy'))}</h2><table>{energy}</table>
<h2>{esc(t('r.impacts'))}</h2><p>{esc(str(s['impacts']['criterion']))}. {esc(s['impacts']['note'])}.</p>
<div class="scroll"><table><tr>{ev_head}</tr>
{''.join(ev_rows)}</table></div>
{'<h2>' + esc(t('r.warnings')) + '</h2><ul>' + warns + '</ul>' if warns else ''}
<h2>{esc(t('r.inapplicable'))}</h2><ul>{inap}</ul>
<h2>{esc(t('r.plots'))}</h2>{imgs}
</main></body></html>
"""
