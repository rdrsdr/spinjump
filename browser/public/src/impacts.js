// Porte de spinjump/impacts.py: eventos de contato com solo e torre, picos filtrados e classes.
const SURFACES = ['ground', 'tower'];
export const G = 9.81;

export function classify(value, threshold, warnFraction) {
  if (value >= threshold) return 'DAMAGE';
  if (value >= warnFraction * threshold) return 'WARNING';
  return 'OK';
}

function normalOf(surface, pos) {
  if (surface === 'ground') return [0, 0, 1];
  const rho = Math.hypot(pos[0], pos[1]);
  if (rho < 1e-9) return [1, 0, 0];
  return [pos[0] / rho, pos[1] / rho, 0];
}

const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => Math.sqrt(dot(a, a));

export class ImpactTracker {
  constructor(mj, model, objGids, groundGid, towerGid, mass, dt, imp) {
    this.mj = mj;
    this.m = model;
    this.obj = new Set(objGids);
    this.gid = { ground: groundGid, tower: towerGid };
    this.mass = mass;
    this.dt = dt;
    this.mergeGap = imp.merge_gap_ms / 1000;
    this.win = Math.max(1, Math.round(imp.filter_window_ms / 1000 / dt));
    this.warnFraction = imp.warn_fraction;
    if (imp.damage_threshold_N != null) { this.metric = 'N'; this.threshold = imp.damage_threshold_N; }
    else { this.metric = 'g'; this.threshold = imp.damage_threshold_g; }
    this.active = { ground: null, tower: null };
    this.events = [];
    this.currentFn = { ground: 0, tower: 0 };
    this.f6 = new mj.DoubleBuffer(6);
    this.f6v = this.f6.GetView();
  }

  geomName(gid) {
    return this.mj.mj_id2name(this.m, this.mj.mjtObj.mjOBJ_GEOM.value, gid) || String(gid);
  }

  step(d, t, vCom) {
    const fn = { ground: 0, tower: 0 };
    const geoms = { ground: new Set(), tower: new Set() };
    const best = { ground: [0, null], tower: [0, null] };
    const ncon = d.ncon;
    if (ncon > 0) {
      const cv = d.contact;
      for (let i = 0; i < ncon; i++) {
        const c = cv.get(i);
        const g1 = c.geom1, g2 = c.geom2;
        let og, other;
        if (this.obj.has(g1)) { og = g1; other = g2; }
        else if (this.obj.has(g2)) { og = g2; other = g1; }
        else { c.delete(); continue; }
        const s = other === this.gid.ground ? 'ground' : other === this.gid.tower ? 'tower' : null;
        if (!s) { c.delete(); continue; }
        this.mj.mj_contactForce(this.m, d, i, this.f6);
        const fN = this.f6v[0];
        if (fN <= 0 && c.dist > 0) { c.delete(); continue; }
        fn[s] += Math.max(fN, 0);
        geoms[s].add(og);
        if (fN >= best[s][0]) { const p = c.pos; best[s] = [fN, [p[0], p[1], p[2]]]; }
        c.delete();
      }
      cv.delete();
    }
    for (const s of SURFACES) {
      this.currentFn[s] = fn[s];
      let act = this.active[s];
      const inContact = geoms[s].size > 0;
      if (inContact) {
        const pos = best[s][1] || [0, 0, 0];
        const n = normalOf(s, pos);
        const vn = -dot(vCom, n);
        const vdn = dot(vCom, n);
        const vt = norm([vCom[0] - vdn * n[0], vCom[1] - vdn * n[1], vCom[2] - vdn * n[2]]);
        if (act === null || t - act.tLast > this.mergeGap + 1e-12) {
          if (act !== null) this.close(s);
          act = { surface: s, tStart: t, tLast: t, geoms: new Set(), t: [], fn: [], vn: [], posPeak: [0, 0, 0],
                  fnPeakStep: 0, vInN: vn, vInT: vt, speedIn: norm(vCom) };
          this.active[s] = act;
        }
        act.tLast = t;
        for (const g of geoms[s]) act.geoms.add(g);
        if (fn[s] >= act.fnPeakStep) { act.fnPeakStep = fn[s]; act.posPeak = pos; }
      }
      if (act !== null) {
        if (!inContact && t - act.tLast > this.mergeGap) { this.close(s); continue; }
        const n = normalOf(s, act.posPeak);
        act.t.push(t);
        act.fn.push(fn[s]);
        act.vn.push(-dot(vCom, n));
      }
    }
  }

  close(s) {
    const act = this.active[s];
    this.active[s] = null;
    if (!act || act.t.length === 0) return;
    let N = 0;
    while (N < act.t.length && act.t[N] <= act.tLast + 1e-12) N++;
    if (N === 0) return;
    const fnr = act.fn.slice(0, N), vn = act.vn.slice(0, N), t = act.t.slice(0, N);
    const M = this.win;
    let fnf = fnr;
    if (N >= M) {
      // np.convolve(..., mode="same") com média móvel de M amostras
      const sh = (M - 1) >> 1;
      fnf = new Array(N);
      for (let i = 0; i < N; i++) {
        let acc = 0;
        for (let j = i + sh - (M - 1); j <= i + sh; j++) if (j >= 0 && j < N) acc += fnr[j];
        fnf[i] = acc / M;
      }
    }
    let iPk = 0, iPkf = 0;
    for (let i = 1; i < N; i++) { if (fnr[i] > fnr[iPk]) iPk = i; if (fnf[i] > fnf[iPkf]) iPkf = i; }
    const peakRaw = fnr[iPk], peakF = fnf[iPkf];
    let iEnd = N - 1;
    for (let i = iPk; i < N; i++) if (fnr[i] <= 0.1 * peakRaw) { iEnd = i; break; }
    let impPhase = 0, impEvent = 0;
    for (let i = 0; i < N; i++) { impEvent += fnr[i]; if (i <= iEnd) impPhase += fnr[i]; }
    const decelG = peakF / (this.mass * G);
    const value = this.metric === 'g' ? decelG : peakF;
    this.events.push({
      surface: s, t_start: act.tStart, t_end: act.tLast, duration_s: act.tLast - act.tStart + this.dt,
      location_m: act.posPeak, geoms: [...act.geoms].map((g) => this.geomName(g)).sort(),
      force_normal_peak_raw_N: peakRaw, force_normal_peak_filtered_N: peakF,
      impulse_normal_impact_Ns: impPhase * this.dt, impulse_normal_event_Ns: impEvent * this.dt,
      delta_v_normal_impact_ms: vn[0] - vn[iEnd], decel_peak_g: decelG,
      v_normal_in_ms: act.vInN, v_tangential_in_ms: act.vInT, speed_in_ms: act.speedIn,
      classification: classify(value, this.threshold, this.warnFraction),
    });
    void t;
  }

  finish() {
    for (const s of SURFACES) if (this.active[s] !== null) this.close(s);
    this.events.sort((a, b) => a.t_start - b.t_start);
    return this.events;
  }

  inContact(s) { return this.currentFn[s] > 0; }

  liveEvents() {
    const out = [...this.events];
    for (const s of SURFACES) {
      const a = this.active[s];
      if (a && a.fn.length) {
        const pk = Math.max(...a.fn), dg = pk / (this.mass * G);
        out.push({ surface: s, t_start: a.tStart, t_end: null, force_normal_peak_raw_N: pk, decel_peak_g: dg,
                   classification: classify(this.metric === 'g' ? dg : pk, this.threshold, this.warnFraction),
                   active: true });
      }
    }
    return out;
  }

  dispose() { this.f6.delete(); }
}
