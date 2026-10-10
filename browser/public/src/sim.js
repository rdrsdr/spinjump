// Porte do laço dinâmico de spinjump/sim.py. A cada passo: mj_step1 → forças da corda, arrasto e
// lançamento em xfrc_applied → mj_step2 → impactos e acompanhamento. Funciona no navegador (Web
// Worker) e no Node (comparação e medição de desempenho).
import { WrapTether, SurfaceRope, TWO_PI } from './rope.js';
import { Wind } from './wind.js';
import { ImpactTracker, G } from './impacts.js';

export const SAMPLE_FIELDS = ['t', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'speed', 'theta_turns', 'wall_dist',
  'wound_turns', 'free_len', 'tension', 'coil_drop', 'e_total', 'phase', 'floor', 'tension_anchor'];

export class Simulation {
  constructor(mj, scen) {
    this.mj = mj;
    this.scen = scen;
    this.dt = scen.dt;
    this.R = scen.tower.R;
    this.H = scen.tower.H;
    const m = mj.MjModel.from_xml_string(scen.xml);
    const d = new mj.MjData(m);
    this.m = m; this.d = d;
    m.opt.enableflags |= mj.mjtEnableBit.mjENBL_ENERGY.value;
    const O = mj.mjtObj;
    this.bid = mj.mj_name2id(m, O.mjOBJ_BODY.value, 'object');
    this.sid = mj.mj_name2id(m, O.mjOBJ_SITE.value, 'attach');
    this.groundGid = mj.mj_name2id(m, O.mjOBJ_GEOM.value, 'ground');
    this.towerGid = mj.mj_name2id(m, O.mjOBJ_GEOM.value, 'tower');
    const bodyid = m.geom_bodyid;
    this.objGids = [];
    for (let i = 0; i < m.ngeom; i++) if (bodyid[i] === this.bid) this.objGids.push(i);
    this.mass = m.body_mass[this.bid];
    const p = scen.rope;
    this.rope = p.coil_sliding ? new SurfaceRope(p, this.dt) : new WrapTether(p);
    this.layout = this.rope.initialLayout(scen.rho_A, 0);
    this.wind = new Wind(scen.wind, this.dt);
    this.impacts = new ImpactTracker(mj, m, this.objGids, this.groundGid, this.towerGid, this.mass, this.dt,
                                     scen.impact);
    this.airRho = scen.air.rho;
    this.cda = scen.air.cda;
    this.edge = scen.edge;
    this.launchJ = scen.launch.J;
    this.launchT = scen.launch.T;
    this.launchDir = scen.launch.dir;
    this.geomLocal = scen.geoms;
    if (this.launchT <= 0 && this.launchJ > 0) {
      const qv = d.qvel, k = this.launchJ / this.mass;
      for (let i = 0; i < 3; i++) qv[i] += k * this.launchDir[i];
    }
    mj.mj_forward(m, d);
    this.buf6 = new mj.DoubleBuffer(6); this.v6 = this.buf6.GetView();
    this.sbuf6 = new mj.DoubleBuffer(6); this.sv6 = this.sbuf6.GetView();
    this.rope.reset(this.sitePos());
    this.theta0 = this.rope.s.theta_u;
    this.stepCount = 0;
    this.sampleEvery = Math.max(1, Math.round(1 / (scen.output_hz * this.dt)));
    this.samples = [];
    this.status = 'running';
    this.outcome = null;
    this.failure = null;
    this.phase = 0;
    this.cpuMs = 0;
    this.tr = {
      firstGroundT: null, firstGroundSpeed: null, firstGroundTurns: null, firstTowerT: null, firstTowerVn: null,
      tMax: 0, tMaxTime: 0, slackTime: 0, woundMin: 1e9, rewindMax: 0, wallDistMin: 1e9, wallDistMinT: 0,
      slidePath: 0, restHold: 0, restT: null, coilDropMax: 0, wDrag: 0, wPeel: 0, wDamp: 0, wFric: 0,
      loadWarn: false, loadBreak: false,
    };
    this.rope.update(this.sitePos(), this.siteVel(), this.wind, this.airRho, G);
    this.energy0 = this.energy();
    this.sample();
  }

  sitePos() { const s = this.d.site_xpos, i = 3 * this.sid; return [s[i], s[i + 1], s[i + 2]]; }

  siteVel() {
    this.mj.mj_objectVelocity(this.m, this.d, this.mj.mjtObj.mjOBJ_SITE.value, this.sid, this.sbuf6, 0);
    const v = this.sv6; return [v[3], v[4], v[5]];
  }

  bodyVel() {
    this.mj.mj_objectVelocity(this.m, this.d, this.mj.mjtObj.mjOBJ_BODY.value, this.bid, this.buf6, 0);
    const v = this.v6; return [[v[3], v[4], v[5]], [v[0], v[1], v[2]]];
  }

  com() { const x = this.d.xipos, i = 3 * this.bid; return [x[i], x[i + 1], x[i + 2]]; }

  energy() {
    const e = this.d.energy, rs = this.rope.s;
    return e[0] + e[1] + rs.elastic_energy + rs.chain_energy;
  }

  *worldSegments() {
    const xp = this.d.xpos, xm = this.d.xmat, b = this.bid;
    const px = xp[3 * b], py = xp[3 * b + 1], pz = xp[3 * b + 2];
    const M = xm.subarray(9 * b, 9 * b + 9);
    const tf = (q) => [px + M[0] * q[0] + M[1] * q[1] + M[2] * q[2],
                       py + M[3] * q[0] + M[4] * q[1] + M[5] * q[2],
                       pz + M[6] * q[0] + M[7] * q[1] + M[8] * q[2]];
    for (const g of this.geomLocal) yield [tf(g.p0), tf(g.p1), g.r];
  }

  wallDistance() {
    let best = 1e9;
    for (const [p0, p1, r] of this.worldSegments()) {
      const ax = p0[0], ay = p0[1], bx = p1[0] - p0[0], by = p1[1] - p0[1];
      const bb = bx * bx + by * by;
      const t = bb < 1e-12 ? 0 : Math.min(1, Math.max(0, -(ax * bx + ay * by) / bb));
      best = Math.min(best, Math.hypot(ax + t * bx, ay + t * by) - this.R - r);
    }
    return best;
  }

  lowestPoint() {
    let low = 1e9;
    for (const [p0, p1, r] of this.worldSegments()) low = Math.min(low, p0[2] - r, p1[2] - r);
    return low;
  }

  objectTurns() { return -this.scen.rope.handedness * (this.rope.s.theta_u - this.theta0) / TWO_PI; }

  step() {
    if (this.status !== 'running') return false;
    const { mj, m, d, dt } = this;
    const tPre = d.time;
    mj.mj_step1(m, d);
    const com = this.com();
    const [vCom, wCom] = this.bodyVel();
    const A = this.sitePos();
    const vA = this.siteVel();
    const rs = this.rope.update(A, vA, this.airRho > 0 ? this.wind : null, this.airRho, G);
    const Fr = rs.force_on_obj;
    const F = [Fr[0], Fr[1], Fr[2]];
    const rx = A[0] - com[0], ry = A[1] - com[1], rz = A[2] - com[2];
    const tq = [ry * Fr[2] - rz * Fr[1], rz * Fr[0] - rx * Fr[2], rx * Fr[1] - ry * Fr[0]];
    const tr = this.tr;
    tr.wDamp += rs.p_damp * dt;
    tr.wPeel += rs.p_peel * dt;
    tr.wFric += rs.e_fric;
    if (this.airRho > 0 && this.cda > 0) {
      const w = this.wind.at(com[2]);
      const vrx = vCom[0] - w[0], vry = vCom[1] - w[1], vrz = vCom[2] - w[2];
      const q = -0.5 * this.airRho * this.cda * Math.sqrt(vrx * vrx + vry * vry + vrz * vrz);
      F[0] += q * vrx; F[1] += q * vry; F[2] += q * vrz;
      tr.wDrag += (q * vrx * vCom[0] + q * vry * vCom[1] + q * vrz * vCom[2]) * dt;
    }
    if (this.launchT > 0 && tPre < this.launchT - 1e-12) {
      const k = this.launchJ / this.launchT;
      for (let i = 0; i < 3; i++) F[i] += k * this.launchDir[i];
    }
    const xf = d.xfrc_applied, o = 6 * this.bid;
    xf[o] = F[0]; xf[o + 1] = F[1]; xf[o + 2] = F[2];
    xf[o + 3] = tq[0]; xf[o + 4] = tq[1]; xf[o + 5] = tq[2];
    this.wind.advance();
    mj.mj_step2(m, d);
    this.stepCount++;
    const qv = d.qvel, qp = d.qpos;
    if (!(qv[0] * qv[0] + qv[1] * qv[1] + qv[2] * qv[2] < 250000) || !Number.isFinite(qp[0] + qp[1] + qp[2])) {
      this.status = 'finished';
      this.outcome = 'NUMERICAL_FAILURE';
      this.failure = `numerical failure at t=${tPre.toFixed(3)} s`;
      return false;
    }
    this.impacts.step(d, tPre, vCom);
    this.track(tPre, com, vCom, wCom, rs);
    if (this.stepCount % this.sampleEvery === 0) this.sample();
    return this.status === 'running';
  }

  track(t, com, v, w, rs) {
    const tr = this.tr, sc = this.scen, dt = this.dt;
    const gOn = this.impacts.inContact('ground'), tOn = this.impacts.inContact('tower');
    if (rs.tension > tr.tMax) { tr.tMax = rs.tension; tr.tMaxTime = t; }
    if (rs.tension >= sc.rope.breaking_load) tr.loadBreak = true;
    if (rs.tension >= (sc.load_warn_fraction ?? 0.5) * sc.rope.breaking_load) tr.loadWarn = true;
    if (rs.slack) tr.slackTime += dt;
    const wt = this.rope.woundTurns;
    tr.woundMin = Math.min(tr.woundMin, wt);
    tr.rewindMax = Math.max(tr.rewindMax, wt - tr.woundMin);
    if (rs.coil_drop > tr.coilDropMax) tr.coilDropMax = rs.coil_drop;
    const speed = Math.hypot(v[0], v[1], v[2]);
    if (gOn && tr.firstGroundT === null) {
      tr.firstGroundT = t; tr.firstGroundSpeed = speed; tr.firstGroundTurns = this.objectTurns();
    }
    if (tOn && tr.firstTowerT === null) {
      tr.firstTowerT = t;
      const rho = Math.hypot(com[0], com[1]);
      tr.firstTowerVn = -(v[0] * com[0] + v[1] * com[1]) / Math.max(rho, 1e-9);
      if (sc.solver.stop_on_structure_hit && tr.firstTowerVn >= sc.impact.structure_hit_speed) {
        this.status = 'finished'; this.outcome = 'HIT_STRUCTURE';
      }
    }
    if (tr.firstGroundT !== null) tr.slidePath += Math.hypot(v[0], v[1]) * dt;
    const omegaEdge = Math.hypot(w[0], w[1], w[2]) * this.edge;
    if (gOn) {
      this.phase = 2;
      if (speed < sc.solver.rest_speed && omegaEdge < sc.solver.rest_speed) tr.restHold += dt;
      else tr.restHold = 0;
      if (tr.restHold >= sc.solver.rest_hold && this.status === 'running') {
        this.phase = 3; tr.restT = t; this.status = 'finished';
      }
    } else {
      tr.restHold = 0;
      this.phase = t > 0 ? 1 : 0;
    }
    if (this.status === 'running' && this.d.time >= sc.max_time_s - 1e-12) this.status = 'finished';
  }

  sample() {
    const tr = this.tr, rs = this.rope.s, d = this.d;
    const com = this.com(), [v] = this.bodyVel();
    const wd = this.wallDistance();
    if (wd < tr.wallDistMin) { tr.wallDistMin = wd; tr.wallDistMinT = d.time; }
    this.samples.push([d.time, com[0], com[1], com[2], v[0], v[1], v[2], Math.hypot(v[0], v[1], v[2]),
      this.objectTurns(), wd, this.rope.woundTurns, rs.l_free, rs.tension, rs.coil_drop,
      d.energy[0] + d.energy[1] + rs.elastic_energy + rs.chain_energy, this.phase,
      Math.max(this.lowestPoint(), 0), rs.tension_anchor]);
  }

  /** Executa passos até o tempo simulado alvo ou o limite de passos; devolve o nº executado. */
  advanceTo(tTarget, maxSteps = Infinity) {
    const t0 = performance.now();
    let n = 0;
    while (this.status === 'running' && this.d.time < tTarget - 1e-12 && n < maxSteps) { this.step(); n++; }
    this.cpuMs += performance.now() - t0;
    if (this.status !== 'running' && this.outcome === null) this.finish();
    return n;
  }

  finish() {
    if (this.status === 'running') this.status = 'finished';
    this.impacts.finish();
    if (this.outcome === null) {
      const thr = this.scen.impact.structure_hit_speed;
      if (this.impacts.events.some((e) => e.surface === 'tower' && e.v_normal_in_ms >= thr)) this.outcome = 'HIT_STRUCTURE';
      else if (this.tr.rewindMax >= this.scen.solver.rewind_threshold_turns) this.outcome = 'REWOUND';
      else if (this.phase === 3) this.outcome = 'AT_REST_CLEAN';
      else this.outcome = 'TIMEOUT';
    }
  }

  summary() {
    const tr = this.tr, ev = this.impacts.events;
    let strongest = null;
    for (const e of ev) if (!strongest || e.decel_peak_g > strongest.decel_peak_g) strongest = e;
    return {
      outcome: this.outcome, failure: this.failure, sim_time_s: this.d.time, steps: this.stepCount,
      us_per_step: this.stepCount ? this.cpuMs * 1000 / this.stepCount : null,
      cpu_s_per_sim_s: this.d.time > 0 ? this.cpuMs / 1000 / this.d.time : null,
      turns_before_ground: tr.firstGroundTurns, ground_t: tr.firstGroundT, ground_speed: tr.firstGroundSpeed,
      slide_path_m: tr.slidePath, tension_max_N: tr.tMax, tension_max_t: tr.tMaxTime,
      wall_dist_min_m: tr.wallDistMin, rewind_max_turns: tr.rewindMax, coil_drop_max_m: tr.coilDropMax,
      coil_friction_J: tr.wFric, rest_t: tr.restT, impacts: ev.length,
      tower_hits: ev.filter((e) => e.surface === 'tower' && e.v_normal_in_ms >= this.scen.impact.structure_hit_speed).length,
      strongest_impact: strongest && { surface: strongest.surface, t: strongest.t_start, g: strongest.decel_peak_g,
                                       class: strongest.classification },
      energy0: this.energy0,
      slack_time_s: tr.slackTime, first_tower_t: tr.firstTowerT, first_tower_vn: tr.firstTowerVn,
      load_warning: tr.loadWarn, load_break: tr.loadBreak, wall_dist_min_t: tr.wallDistMinT,
      wound_turns_initial: this.samples.length ? this.samples[0][10] : null,
      energy: (() => {
        const e1 = this.energy();
        const diss = tr.wDrag - tr.wDamp - tr.wPeel - tr.wFric;
        return { initial_J: this.energy0, final_J: e1, drag_object_work_J: tr.wDrag, rope_axial_damping_J: -tr.wDamp,
                 rope_peel_kink_J: -tr.wPeel, coil_wall_friction_J: -tr.wFric,
                 contact_and_residual_J: e1 - this.energy0 - diss };
      })(),
    };
  }

  /** Estado para desenho: pose das geoms do objeto, corda e telemetria. */
  frame() {
    const d = this.d, rs = this.rope.s;
    const gx = d.geom_xpos, gm = d.geom_xmat;
    const geoms = this.objGids.map((g) => [...gx.subarray(3 * g, 3 * g + 3), ...gm.subarray(9 * g, 9 * g + 9)]);
    const wall = this.rope.wallPolyline(48);
    const [v] = this.bodyVel();
    return {
      t: d.time, geoms, wall, D: rs.D, A: rs.A, slack: rs.slack,
      tele: { t: d.time, speed: Math.hypot(v[0], v[1], v[2]), floor: Math.max(this.lowestPoint(), 0),
              wall: this.wallDistance(), turns: this.objectTurns(), wound: this.rope.woundTurns,
              tension: rs.tension, coil_drop: rs.coil_drop, phase: this.phase },
      events: this.impacts.liveEvents().slice(-50),
    };
  }

  dispose() {
    this.impacts.dispose(); this.buf6.delete(); this.sbuf6.delete(); this.d.delete(); this.m.delete();
  }
}
