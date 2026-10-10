// Porte do início de spinjump/sim.Simulation.__init__: da configuração validada e resolvida ao
// "cenário" (MJCF, parâmetros da corda, lançamento, vento, limites) que sim.js executa. Antes isso
// era exportado pelo Python (tools/export_scenarios.py, mantido como referência de comparação).
import { coerce, validate, resolve, launchImpulse } from './config.js';
import { objectGeoms, objectExtentRadius, buildXml } from './model.js';
import { WrapTether, SurfaceRope, ropeConsts } from './rope.js';

export class ConfigError extends Error {
  constructor(errors) { super(errors.join('; ')); this.errors = errors; }
}

const norm = (v) => { const n = Math.hypot(...v); return v.map((x) => x / n); };

/** cfg bruto (já mesclado) → { scen, cfg (resolvido), notes, warnings }; lança ConfigError se inválido. */
export function buildScenario(input, rules, { name = input.name || 'custom', description = '' } = {}) {
  const raw = coerce(input, rules);
  const errors = validate(raw, rules);
  if (errors.length) throw new ConfigError(errors);
  const { cfg: c, notes } = resolve(raw);
  const R = c.tower.diameter_m / 2, H = c.tower.height_m;
  const dt = c.solver.timestep_s;
  const extent = objectExtentRadius(c);
  const aH = c.object.attach_height_fraction * c.object.height_m;
  const rope = {
    R_wall: R, rope_d: c.rope.diameter_m, pitch: c.rope.winding_pitch_factor * c.rope.diameter_m,
    handedness: c.rope.winding_handedness === 'ccw' ? 1 : -1,
    z_anchor: H - c.rope.anchor_below_top_m, length: Number(c.rope.length_m),
    EA: Number(c.rope.axial_EA_N), zeta: c.rope.axial_damping_ratio, lin_density: c.rope.linear_density_kg_m,
    mu_wall: c.rope.wall_friction, cd_normal: c.rope.wind_drag_Cd_normal, cd_tangent: c.rope.wind_drag_Cd_tangent,
    element_length: c.rope.element_length_m, m_eff: c.object.mass_kg, tower_height: H,
    vertical: c.rope.helix_vertical === 'up' ? 1 : -1,
    coil_sliding: !!c.rope.coil_sliding, pretension: c.rope.winding_pretension_N,
    window_turns: c.rope.coil_window_turns, update_every: c.rope.coil_update_every_steps,
    mass_scale: c.rope.coil_mass_scale, breaking_load: c.rope.breaking_load_N,
  };
  const rhoA = R + c.object.start_clearance_m + extent;
  const tmp = rope.coil_sliding ? new SurfaceRope(rope, dt) : new WrapTether(rope);
  let lay;
  try { lay = tmp.initialLayout(rhoA, 0); } catch (e) { throw new ConfigError([`rope: ${e.message}`]); }
  const room = c.rope.helix_vertical === 'up' ? c.rope.anchor_below_top_m : rope.z_anchor;
  if (lay.helix_height + 1e-9 > room) {
    throw new ConfigError([`the initial helix (${lay.turns0.toFixed(2)} turns, height ${lay.helix_height.toFixed(3)} m) `
      + 'goes above the top; increase rope.anchor_below_top_m']);
  }
  const warnings = [];
  const { rc } = ropeConsts(rope);
  const Lmin = Math.hypot(rope.z_anchor - c.object.radius_m, Math.max(R + c.object.radius_m - rc, 0));
  if (rope.length < Lmin) {
    warnings.push(`rope.length_m=${rope.length.toFixed(2)} m is shorter than needed to reach the ground `
      + `(${Lmin.toFixed(2)} m): the object will stay suspended`);
  }
  const omega = Math.sqrt(rope.EA / (Math.max(lay.free0, 0.05) * c.object.mass_kg));
  if (omega * dt > 0.2) warnings.push(`axial stiffness too high for the time step: ω·dt = ${(omega * dt).toFixed(3)} > 0.2`);
  if (c.launch.elevation_deg > 60) {
    warnings.push('launch elevation > 60°: the object may rise above the tower top, where rope–rim contact is not modelled');
  }
  const A0 = lay.A0, D0 = lay.D0;
  const xml = buildXml(c, [A0[0], A0[1], A0[2] - aH]);
  // lançamento no referencial do vão livre inicial
  const uT = norm([A0[0] - D0[0], A0[1] - D0[1], 0]);
  const nD = norm([D0[0], D0[1], 0]);
  const az = c.launch.azimuth_deg * Math.PI / 180, el = c.launch.elevation_deg * Math.PI / 180;
  const vH = [0, 1, 2].map((i) => Math.cos(az) * uT[i] + Math.sin(az) * nD[i]);
  const dir = [Math.cos(el) * vH[0], Math.cos(el) * vH[1], Math.cos(el) * vH[2] + Math.sin(el)];
  const w = c.wind, ang = w.direction_deg * Math.PI / 180;
  const scen = {
    name, description, xml, dt, max_time_s: c.solver.max_time_s, output_hz: c.solver.output_hz,
    rope, rho_A: Math.hypot(A0[0], A0[1]),
    layout: { u0: lay.u0, free0: lay.free0, A0: [...A0], phi_anchor: lay.phi_anchor, turns0: lay.turns0 },
    launch: { J: launchImpulse(c), T: c.launch.duration_ms / 1000, dir },
    mass: null,   // definido pelo MuJoCo ao compilar (sim.js)
    air: { rho: c.air.enabled ? c.air.density_kg_m3 : 0, cda: c.object.drag_CdA_m2 },
    edge: Math.max(extent, c.object.height_m / 2),
    geoms: objectGeoms(c).map((g) => ({ p0: [...g.p0], p1: [...(g.p1 || g.p0)], r: g.radius })),
    wind: { enabled: !!w.enabled, U: Number(w.speed_mean_ms), dir: [Math.cos(ang), Math.sin(ang)], sigma: w.gust_std_ms,
            tau: w.correlation_time_s, alpha: w.shear_exponent, zref: w.reference_height_m, seed: w.seed },
    solver: { rest_speed: c.solver.rest_speed_ms, rest_hold: c.solver.rest_hold_s,
              rewind_threshold_turns: c.solver.rewind_threshold_turns, stop_on_structure_hit: !!c.solver.stop_on_structure_hit },
    impact: { structure_hit_speed: c.impact.structure_hit_speed_ms, merge_gap_ms: c.impact.merge_gap_ms,
              filter_window_ms: c.impact.filter_window_ms, damage_threshold_g: c.impact.damage_threshold_g,
              damage_threshold_N: c.impact.damage_threshold_N, warn_fraction: c.impact.warn_fraction },
    tower: { R, H },
    load_warn_fraction: c.rope.load_warn_fraction,
  };
  return { scen, cfg: c, notes, warnings };
}
