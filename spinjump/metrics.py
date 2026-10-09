"""Resumo físico de uma execução: responde às perguntas da especificação."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import platform

import mujoco
import numpy as np

from . import __version__
from .config import G, auto_rope_length, to_plain
from .impacts import classify
from .sim import TELEMETRY_FIELDS, Simulation, safety_notice
from .i18n import t

def outcome_text(code: str | None) -> str:
    return t(f"outcome.{code}") if code else ""

CLASS_COLORS = {"OK": "#0ca30c", "ATENÇÃO": "#fab219", "DANO": "#d03b3b"}


def config_hash(cfg) -> str:
    return hashlib.sha256(json.dumps(to_plain(cfg), sort_keys=True).encode()).hexdigest()[:12]


def ground_reach_check(sim: Simulation) -> dict:
    """Comprimento mínimo para o objeto alcançar o solo com a corda totalmente desenrolada."""
    c = sim.cfg
    z_a = sim.rp.z_anchor
    z_attach_lying = c.object.radius_m
    horiz = max(sim.R + c.object.radius_m - sim.rp.rc, 0.0)
    L_min = math.hypot(z_a - z_attach_lying, horiz)
    L = float(c.rope.length_m)
    return dict(L_m=L, L_min_to_ground_m=round(L_min, 3), can_reach_ground=L >= L_min,
                note=t("note.reach_short") if L < L_min else t("note.reach_ok"))


def summarize(sim: Simulation, name: str | None = None) -> dict:
    c, tr = sim.cfg, sim.tr
    S = np.asarray(sim.samples, dtype=float)
    F = {k: i for i, k in enumerate(TELEMETRY_FIELDS)}
    ev = sim.impacts.events
    tower = [e for e in ev if e["surface"] == "tower"]
    ground = [e for e in ev if e["surface"] == "ground"]
    hits = sim.structure_hits()
    two_pi = 2 * math.pi
    turns0 = sim.layout["turns0"]
    t_end = float(sim.d.time)
    final = S[-1]
    # deslizamento após o primeiro toque no solo
    if tr.first_ground_t is not None:
        ig = int(np.searchsorted(S[:, 0], tr.first_ground_t))
        p0 = S[ig, [F["x"], F["y"]]]
        p1 = final[[F["x"], F["y"]]]
        net = float(np.linalg.norm(p1 - p0))
        dtheta = float(final[F["theta_turns"]] - tr.first_ground_theta)
        tens_g = S[ig:, F["tension"]]
        taut_frac = float(np.mean(tens_g > 0)) if tens_g.size else 0.0
        # curvatura: razão deslocamento líquido / caminho percorrido
        straightness = net / tr.slide_path if tr.slide_path > 1e-6 else 1.0
        # margem de alcance: alongamento permitido pela maior tração no solo − maior excesso observado
        exc = S[ig:, F["path_len"]] - S[ig:, F["rest_len"]]
        reach_margin = float(np.min(S[ig:, F["rest_len"]] * tr.t_max_ground / sim.rp.EA - exc)) if exc.size else None
    else:
        net = dtheta = taut_frac = 0.0
        straightness = 1.0
        reach_margin = None
    max_imp = max(ev, key=lambda e: e["decel_peak_g"]) if ev else None
    first_ground_ev = ground[0] if ground else None
    first_tower_ev = tower[0] if tower else None
    spiral = (tr.first_ground_theta or 0.0) >= 1.0
    est = auto_rope_length(c.tower.height_m, sim.launch_J / sim.mass)
    energy_final = float(final[F["e_total"]])
    e0 = tr.energy0
    w_known = tr.w_drag + tr.w_rope_dist + tr.w_launch - tr.w_rope_damp - tr.w_peel
    contact_diss = e0 + w_known - energy_final
    reach = ground_reach_check(sim)
    summary = {
        "meta": {
            "name": name or c.name,
            "created": _dt.datetime.now().isoformat(timespec="seconds"),
            "version": __version__,
            "mujoco": mujoco.__version__,
            "python": platform.python_version(),
            "config_hash": config_hash(c),
            "seed": c.wind.seed,
            "rope_model": c.rope.model,
            "sim_time_s": round(t_end, 4),
            "steps": sim.step_count,
            "timestep_s": c.solver.timestep_s,
            "wall_clock_s": round(sim.wall_clock, 3),
            "cpu_s_per_sim_s": round(sim.wall_clock / max(t_end, 1e-9), 4),
            "safety_notice": safety_notice(),
        },
        "outcome": {
            "code": sim.outcome,
            "text": outcome_text(sim.outcome),
            "failure": sim.failure,
            "flags": {
                "spiral_before_ground": spiral,
                "structure_hit": bool(hits),
                "tower_contact_any": bool(tower),
                "rope_slack_any": tr.slack_time > 0,
                "rope_rewound": tr.rewind_max_turns >= c.solver.rewind_threshold_turns,
                "reached_ground": tr.first_ground_t is not None,
                "at_rest": tr.rest_t is not None,
                "load_warning": tr.load_warn,
                "load_exceeds_breaking": tr.load_break,
                "coil_slip_risk": tr.coil_slip_risk_time > 0,
                "object_above_tower_top": tr.above_top_time > 0,
            },
        },
        "spiral": {
            "object_turns_before_ground": _r(tr.first_ground_theta),
            "object_turns_total": _r(float(final[F["theta_turns"]])),
            "stored_turns_initial": _r(turns0),
            "stored_turns_at_ground": _r(tr.first_ground_stored_turns),
            "stored_turns_final": _r(float(final[F["stored_turns"]])),
            "wound_turns_final": _r(float(final[F["wound_turns"]])),
            "unwound_turns_before_ground": _r(turns0 - tr.first_ground_stored_turns
                                              if tr.first_ground_stored_turns is not None else None),
            "unwound_length_total_m": _r(sim.layout["wound0"] - float(final[F["stored_len"]])),
            "min_wall_distance_m": _r(tr.wall_dist_min),
            "min_wall_distance_t_s": _r(tr.wall_dist_min_t),
        },
        "ground_arrival": {
            "t_s": _r(tr.first_ground_t),
            "speed_ms": _r(tr.first_ground_speed),
            "v_normal_ms": _r(tr.first_ground_vn),
            "v_tangential_ms": _r(tr.first_ground_vt),
            "position_m": [_r(x) for x in tr.first_ground_pos] if tr.first_ground_pos else None,
            "first_event": _ev_brief(first_ground_ev),
        },
        "structure_arrival": {
            "t_s": _r(tr.first_tower_t),
            "speed_ms": _r(tr.first_tower_speed),
            "v_normal_ms": _r(tr.first_tower_vn),
            "first_event": _ev_brief(first_tower_ev),
            "hits_above_threshold": len(hits),
            "threshold_v_normal_ms": c.impact.structure_hit_speed_ms,
        },
        "ground_phase": {
            "slide_path_m": _r(tr.slide_path),
            "net_displacement_m": _r(net),
            "straightness_net_over_path": _r(straightness),
            "angle_swept_after_ground_deg": _r(dtheta * 360.0),
            "angle_swept_after_ground_turns": _r(dtheta),
            "rope_taut_fraction_on_ground": _r(taut_frac),
            "tension_max_on_ground_N": _r(tr.t_max_ground),
            "max_strain_on_ground": _r(tr.strain_max_ground, 5),
            "reach_margin_m": _r(reach_margin, 5),
            "reach_note": t("note.reach_margin"),
            "ground_hops": tr.ground_hops,
            "max_lift_after_ground_m": _r(tr.max_lift_after_ground),
            "rest_time_s": _r(tr.rest_t),
            "time_ground_to_rest_s": _r(tr.rest_t - tr.first_ground_t
                                        if tr.rest_t is not None and tr.first_ground_t is not None else None),
            "final_position_m": [_r(float(final[F[k]])) for k in ("x", "y", "z")],
        },
        "rope": {
            "model": c.rope.model,
            "length_m": float(c.rope.length_m),
            "length_source": sim.notes.get("rope_length_source", ""),
            "length_estimate": {k: (_r(v) if isinstance(v, float) else v) for k, v in est.items()},
            "ground_reach": reach,
            "tension_max_N": _r(tr.t_max),
            "tension_max_t_s": _r(tr.t_max_time),
            "tension_max_air_N": _r(tr.t_max_air),
            "tension_anchor_max_N": _r(tr.t_anchor_max),
            "tension_anchor_note": t("note.anchor"),
            "breaking_load_N": c.rope.breaking_load_N,
            "load_warn_threshold_N": c.rope.load_warn_fraction * c.rope.breaking_load_N,
            "slack_time_total_s": _r(tr.slack_time),
            "slack_time_air_s": _r(tr.slack_time_air),
            "slack_time_ground_s": _r(tr.slack_time_ground),
            "slack_episodes": tr.slack_episodes,
            "slack_max_m": _r(tr.slack_max),
            "rewind_max_turns": _r(tr.rewind_max_turns),
            "coil_slip_ratio_max": _r(tr.coil_slip_ratio_max),
            "coil_slip_risk_time_s": _r(tr.coil_slip_risk_time),
            "coil_slip_note": t("note.coil_slip"),
        },
        "impacts": {
            "count": len(ev),
            "count_ground": len(ground),
            "count_tower": len(tower),
            "max_event": _ev_brief(max_imp),
            "criterion": ev[0]["criterion"] if ev else None,
            "note": t("note.impacts"),
        },
        "energy": {
            "initial_J": _r(e0),
            "final_J": _r(energy_final),
            "drag_object_work_J": _r(tr.w_drag),
            "wind_input_J": _r(tr.w_wind_in),
            "rope_distributed_work_J": _r(tr.w_rope_dist),
            "rope_axial_damping_J": _r(tr.w_rope_damp),
            "rope_peel_kink_J": _r(tr.w_peel),
            "launch_force_work_J": _r(tr.w_launch),
            "contact_and_residual_J": _r(contact_diss),
            "flight_balance_residual_max_J": _r(tr.e_flight_residual_max),
        },
        "launch": {
            "mode": c.launch.mode,
            "speed_ms": _r(sim.launch_J / sim.mass),
            "impulse_Ns": _r(sim.launch_J),
            "azimuth_deg": c.launch.azimuth_deg,
            "elevation_deg": c.launch.elevation_deg,
            "duration_ms": c.launch.duration_ms,
            "direction_world": [_r(x) for x in sim.launch_dir],
            "convention": t("note.azimuth"),
        },
        "inapplicable_params": sim.notes.get("inapplicable_params", {}),
        "warnings": list(sim.warnings),
    }
    return summary


def _r(x, nd: int = 4):
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    if not math.isfinite(xf):
        return None
    return round(xf, nd)


def _ev_brief(e: dict | None) -> dict | None:
    if not e:
        return None
    keys = ("surface", "t_start", "duration_s", "speed_in_ms", "v_normal_in_ms", "v_tangential_in_ms",
            "force_normal_peak_raw_N", "force_normal_peak_filtered_N", "impulse_normal_impact_Ns",
            "decel_peak_g", "classification", "geoms", "location_m")
    return {k: e.get(k) for k in keys}
