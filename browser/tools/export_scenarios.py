"""Exporta cenários resolvidos pelo simulador Python para o protótipo no navegador.

Cada cenário vira um JSON com o MJCF já montado, os parâmetros da corda, o lançamento e o vento,
para que o código JavaScript porte apenas o laço dinâmico (protótipo: a resolução da configuração e
a geração do MJCF ainda ficam no Python).

Uso (no container de desenvolvimento): ./dev.sh python browser/tools/export_scenarios.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from spinjump.config import load_config  # noqa: E402
from spinjump.sim import Simulation  # noqa: E402

OUT = ROOT / "browser" / "public" / "scenarios"

# nome → (preset, overrides, descrição em inglês)
SCENARIOS = {
    "default": (None, [], "Default demo: sliding coils, unwinding from the bottom coil, 4 m/s tangential launch."),
    "locked": (None, ["rope.coil_sliding=false"], "Default demo with locked coils (faster rope model)."),
    "rewind": ("rewind", [], "Launch toward the winding direction (azimuth -60°, 6 m/s): rewinds and hits the tower."),
    "away": (None, ["launch.azimuth_deg=0"], "Launch straight away from the chimney: swings back into the wall."),
    "strong_wind": ("strong_wind", [], "Strong wind (10 m/s) with gusts and a vertical profile."),
}
# variantes determinísticas para comparação Python × JS (sem rajadas aleatórias)
COMPARE = {
    "cmp_sliding": (None, ["wind.gust_std_ms=0"]),
    "cmp_locked": (None, ["wind.gust_std_ms=0", "rope.coil_sliding=false"]),
    "cmp_rewind": ("rewind", ["wind.gust_std_ms=0"]),
}


def export(name: str, preset, sets, description: str = "") -> dict:
    cfg = load_config(preset=preset, sets=sets)
    sim = Simulation(cfg)
    c, rp, lay = sim.cfg, sim.rp, sim.layout
    w = sim.wind
    scen = dict(
        name=name, description=description, preset=preset, overrides=sets,
        xml=sim.b.xml,
        dt=sim.dt, max_time_s=c.solver.max_time_s, output_hz=c.solver.output_hz,
        rope=dict(R_wall=rp.R_wall, rope_d=rp.rope_d, pitch=rp.pitch, handedness=rp.handedness,
                  z_anchor=rp.z_anchor, length=rp.length, EA=rp.EA, zeta=rp.zeta,
                  lin_density=rp.lin_density, mu_wall=rp.mu_wall, cd_normal=rp.cd_normal,
                  cd_tangent=rp.cd_tangent, element_length=rp.element_length, m_eff=rp.m_eff,
                  tower_height=rp.tower_height, vertical=rp.vertical,
                  coil_sliding=bool(c.rope.coil_sliding), pretension=c.rope.winding_pretension_N,
                  window_turns=c.rope.coil_window_turns, update_every=c.rope.coil_update_every_steps,
                  mass_scale=c.rope.coil_mass_scale, breaking_load=c.rope.breaking_load_N),
        rho_A=float(abs(complex(*lay["A0"][:2]))),
        layout=dict(u0=lay["u0"], free0=lay["free0"], A0=[float(v) for v in lay["A0"]],
                    phi_anchor=lay["phi_anchor"]),
        launch=dict(J=sim.launch_J, T=sim.launch_T, dir=[float(v) for v in sim.launch_dir]),
        mass=sim.mass,
        air=dict(rho=sim.air_rho, cda=sim._cda),
        edge=sim._edge,
        geoms=[dict(p0=[float(v) for v in p0], p1=[float(v) for v in p1], r=float(r)) for p0, p1, r in sim.geom_local],
        wind=dict(enabled=w.enabled, U=w.U, dir=[float(w.dir[0]), float(w.dir[1])], sigma=w.sigma, tau=w.tau,
                  alpha=w.alpha, zref=w.zref, seed=int(c.wind.seed), g0=[float(w.g[0]), float(w.g[1])]),
        solver=dict(rest_speed=c.solver.rest_speed_ms, rest_hold=c.solver.rest_hold_s,
                    rewind_threshold_turns=c.solver.rewind_threshold_turns,
                    stop_on_structure_hit=bool(c.solver.stop_on_structure_hit)),
        impact=dict(structure_hit_speed=c.impact.structure_hit_speed_ms, merge_gap_ms=c.impact.merge_gap_ms,
                    filter_window_ms=c.impact.filter_window_ms, damage_threshold_g=c.impact.damage_threshold_g,
                    damage_threshold_N=c.impact.damage_threshold_N, warn_fraction=c.impact.warn_fraction),
        tower=dict(R=c.tower.diameter_m / 2, H=c.tower.height_m),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(scen, indent=1))
    return scen


if __name__ == "__main__":
    index = []
    for name, (preset, sets, desc) in SCENARIOS.items():
        export(name, preset, sets, desc)
        index.append(dict(name=name, description=desc))
    for name, (preset, sets) in COMPARE.items():
        export(name, preset, sets, "comparison (deterministic wind)")
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print(f"{len(SCENARIOS) + len(COMPARE)} cenários em {OUT}")
