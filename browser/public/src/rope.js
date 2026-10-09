// Porte de spinjump/rope.py (WrapTether, espiras travadas) e spinjump/surface_rope.py
// (SurfaceRope, espiras deslizantes). Mesmas equações; ver a documentação do projeto Python.
import { chainStep, distLoads } from './kernel.js';

export const TWO_PI = 2 * Math.PI;
const DEG = 180 / Math.PI;
const clamp1 = (v) => Math.max(-1, Math.min(1, v));
// módulo com sinal do divisor (como o % do Python)
const pmod = (a, n) => ((a % n) + n) % n;

export function ropeConsts(p) {
  const rc = p.R_wall + 0.5 * p.rope_d;
  return { rc, kappa: Math.hypot(rc, p.pitch / TWO_PI) };
}

function newState() {
  return {
    u_s: 0, psi: 0, psi_g: 0, psi_dot: 0, theta_u: 0, theta_raw: 0, regime: 1, peeling: false,
    P1: [0, 0, 0], D: [0, 0, 0], A: [0, 0, 0], e: [1, 0, 0],
    l_free: 0, l_geo: 0, l_geom: 0, l_rest: 0, stored_len: 0, wound_len: 0,
    delta: 0, delta_dot: 0, tension: 0, tension_anchor: 0,
    force_on_obj: [0, 0, 0], dist_load_on_obj: [0, 0, 0],
    slack: false, above_top: false, fully_wound: false, elastic_energy: 0,
    p_damp: 0, p_peel: 0, kink_deg: 0, k: 0, c: 0,
    chain_energy: 0, e_fric: 0, e_massflux: 0, coil_drop: 0,
  };
}

export class WrapTether {
  constructor(p) {
    this.modelName = 'locked';
    this.p = p;
    const { rc, kappa } = ropeConsts(p);
    this.rc = rc;
    this.kappa = kappa;
    this.pz = p.vertical * p.pitch / TWO_PI;
    this.phi_a = 0;
    this.s = newState();
    this.initialized = false;
    this.dl = new Float64Array(3);
  }

  storedPoint(u) {
    const p = this.p;
    const phi = this.phi_a + p.handedness * u;
    return [this.rc * Math.cos(phi), this.rc * Math.sin(phi), p.z_anchor + p.vertical * p.pitch * u / TWO_PI];
  }

  initialLayout(rhoA, thetaA) {
    const p = this.p, rc = this.rc;
    if (rhoA <= rc) throw new Error('attachment point inside the rope radius');
    const lh = Math.sqrt(rhoA * rhoA - rc * rc);
    const wound = p.length - lh;
    if (wound <= 0) throw new Error('rope too short for the start position');
    const u0 = wound / this.kappa;
    const beta = Math.acos(rc / rhoA);
    this.phi_a = thetaA - p.handedness * beta - p.handedness * u0;
    this.s.u_s = u0;
    const D = this.storedPoint(u0);
    const A = [rhoA * Math.cos(thetaA), rhoA * Math.sin(thetaA), D[2]];
    return { u0, wound0: wound, turns0: u0 / TWO_PI, free0: lh, D0: D, A0: A, phi_anchor: this.phi_a,
             helix_height: u0 / TWO_PI * p.pitch };
  }

  reset(A) {
    const th = Math.atan2(A[1], A[0]);
    this.s.theta_raw = th;
    const rho = Math.hypot(A[0], A[1]);
    const beta = Math.acos(Math.min(1, this.rc / Math.max(rho, 1e-9)));
    const target = this.phi_a + this.p.handedness * (this.s.u_s + beta);
    const k = Math.round((target - th) / TWO_PI);
    this.s.theta_u = th + k * TWO_PI;
    this.initialized = true;
  }

  trackTheta(A) {
    const th = Math.atan2(A[1], A[0]);
    let d = th - this.s.theta_raw;
    d = pmod(d + Math.PI, TWO_PI) - Math.PI;
    this.s.theta_raw = th;
    this.s.theta_u += d;
    return this.s.theta_u;
  }

  update(A, vA, wind, airDensity, g) {
    const p = this.p, s = this.s, h = p.handedness, rc = this.rc, kappa = this.kappa;
    if (!this.initialized) this.reset(A);
    const thetaU = this.trackTheta(A);
    const rho = Math.hypot(A[0], A[1]);
    const rhoC = Math.max(rho, rc * (1 + 1e-9));
    const beta = Math.acos(rc / rhoC);
    const lh = Math.sqrt(Math.max(rhoC * rhoC - rc * rc, 0));
    let thetaDot = 0, rhoDot = 0;
    if (rho > 1e-9) {
      thetaDot = (A[0] * vA[1] - A[1] * vA[0]) / (rho * rho);
      rhoDot = (A[0] * vA[0] + A[1] * vA[1]) / rho;
    }
    const betaDot = lh > 1e-9 ? rc * rhoDot / (rhoC * lh) : 0;
    const psiPos = thetaU - beta - this.phi_a;
    const psiNeg = thetaU + beta - this.phi_a;
    const psiH = h === 1 ? psiPos : psiNeg;
    const uPrev = s.u_s;
    let peeling = false, uS;
    if (uPrev > 0) {
      const a = h * psiH;
      if (a < uPrev) { uS = Math.max(0, a); peeling = true; } else uS = uPrev;
    } else uS = 0;
    let regime, psi;
    if (uS > 0) { regime = h; psi = psiH; }
    else if (psiPos > 0) { regime = 1; psi = psiPos; }
    else if (psiNeg < 0) { regime = -1; psi = psiNeg; }
    else { regime = 0; psi = 0; }
    const psiG = uS > 0 ? psi - h * uS : psi;
    const psiDot = regime === 1 ? thetaDot - betaDot : regime === -1 ? thetaDot + betaDot : 0;
    const uSdot = peeling && uS > 0 ? h * psiDot : 0;
    const phi1 = this.phi_a + h * uS;
    const c1 = Math.cos(phi1), s1 = Math.sin(phi1);
    const pz = this.pz;
    const P1x = rc * c1, P1y = rc * s1, P1z = p.z_anchor + pz * uS;
    const tx = -h * rc * s1, ty = h * rc * c1, tz = pz;
    const ag = Math.abs(psiG);
    const runG = rc * ag;
    const X = runG + lh;
    const [Ax, Ay, Az] = A;
    const [vx, vy, vz] = vA;
    const dz = Az - P1z;
    const lGeom = Math.hypot(X, dz);
    const frac = X > 1e-12 ? runG / X : 0;
    const phiD = this.phi_a + psi;
    const Dx = rc * Math.cos(phiD), Dy = rc * Math.sin(phiD), Dz = P1z + dz * frac;
    const rx = Ax - Dx, ry = Ay - Dy, rz = Az - Dz;
    const lFree = Math.sqrt(rx * rx + ry * ry + rz * rz);
    let ex = 0, ey = 0, ez = -1;
    if (lFree > 1e-9) { ex = rx / lFree; ey = ry / lFree; ez = rz / lFree; }
    const lGeo = lGeom - lFree;
    const stored = uS * kappa;
    let lRest = p.length - stored;
    const fullyWound = lRest <= 1e-3;
    lRest = Math.max(lRest, 1e-3);
    const delta = lGeom - lRest;
    const eDotVA = ex * vx + ey * vy + ez * vz;
    const proj = ex * tx + ey * ty + ez * tz;
    let lDot, peelCoef;
    if (uSdot !== 0) { lDot = eDotVA - proj * uSdot; peelCoef = Math.max(0, kappa - proj); }
    else { lDot = eDotVA; peelCoef = 0; }
    const lRestDot = -kappa * uSdot;
    const deltaDot = lDot - lRestDot;
    const k = p.EA / lRest;
    const c = 2 * p.zeta * Math.sqrt(k * p.m_eff);
    let T = 0, elastic = 0, pDamp = 0;
    if (delta > 0) {
      T = Math.max(0, k * delta + c * deltaDot);
      elastic = 0.5 * k * delta * delta;
      pDamp = (T - k * delta) * deltaDot;
    }
    let pPeel = T * peelCoef * Math.abs(uSdot);
    if (delta > 0 && lRestDot > 0) pPeel += 0.5 * k * delta * delta * lRestDot / lRest;
    let cosk;
    if (ag < 1e-9) cosk = proj / kappa;
    else {
      const thx = -regime * s1, thy = regime * c1;
      cosk = ((X * thx) * tx + (X * thy) * ty + dz * tz) / Math.max(lGeom, 1e-9) / kappa;
    }
    const freeMass = p.lin_density * (lFree / Math.max(lGeom, 1e-9)) * lRest;
    const dist = this.distLoads(lFree, freeMass, Dz, rz, ex, ey, ez, vA, wind, airDensity, g);
    s.u_s = uS; s.psi = psi; s.psi_g = psiG; s.psi_dot = psiDot; s.regime = regime; s.peeling = peeling;
    s.P1 = [P1x, P1y, P1z]; s.D = [Dx, Dy, Dz]; s.A = [Ax, Ay, Az]; s.e = [ex, ey, ez];
    s.l_free = lFree; s.l_geo = lGeo; s.l_geom = lGeom; s.l_rest = lRest;
    s.stored_len = stored; s.wound_len = stored + lGeo;
    s.delta = delta; s.delta_dot = deltaDot;
    s.tension = T;
    s.tension_anchor = T * Math.exp(-p.mu_wall * uS);
    s.dist_load_on_obj = dist;
    s.force_on_obj = [-T * ex + dist[0], -T * ey + dist[1], -T * ez + dist[2]];
    s.slack = delta <= 0;
    s.above_top = Az > p.tower_height;
    s.fully_wound = fullyWound;
    s.elastic_energy = elastic;
    s.p_damp = pDamp; s.p_peel = pPeel; s.kink_deg = Math.acos(clamp1(cosk)) * DEG;
    s.k = k; s.c = c;
    return s;
  }

  distLoads(lFree, freeMass, Dz, rz, ex, ey, ez, vA, wind, airDensity, g) {
    const p = this.p, out = this.dl;
    if (wind && wind.enabled) {
      distLoads(lFree, freeMass, Dz, rz, ex, ey, ez, vA[0], vA[1], vA[2], airDensity, p.cd_normal, p.cd_tangent,
                p.rope_d, p.element_length, g, true, wind.U, wind.dir[0], wind.dir[1], wind.g[0], wind.g[1],
                wind.alpha, wind.zref, out);
    } else {
      distLoads(lFree, freeMass, Dz, rz, ex, ey, ez, vA[0], vA[1], vA[2], airDensity, p.cd_normal, p.cd_tangent,
                p.rope_d, p.element_length, g, false, 0, 0, 0, 0, 0, 0, 1, out);
    }
    return [out[0], out[1], out[2]];
  }

  get woundTurns() { return (this.s.u_s + Math.abs(this.s.psi_g)) / TWO_PI; }

  /** Polilinha da corda encostada (âncora → P1 → geodésica → D), para desenho. */
  wallPolyline(ptsPerTurn = 48) {
    const s = this.s, p = this.p, pts = [];
    if (s.u_s > 1e-6) {
      const n = Math.max(2, Math.ceil(s.u_s / TWO_PI * ptsPerTurn) + 1);
      for (let i = 0; i < n; i++) pts.push(this.storedPoint(s.u_s * i / (n - 1)));
    }
    const ag = Math.abs(s.psi_g);
    if (ag > 1e-6) {
      const n = Math.max(2, Math.ceil(ag / TWO_PI * ptsPerTurn) + 1);
      const sgn = s.psi_g > 0 ? 1 : -1, phi0 = Math.atan2(s.P1[1], s.P1[0]);
      for (let i = 0; i < n; i++) {
        const w = i / (n - 1), phi = phi0 + sgn * ag * w;
        pts.push([this.rc * Math.cos(phi), this.rc * Math.sin(phi), s.P1[2] + (s.D[2] - s.P1[2]) * w]);
      }
    }
    return pts;
  }
}

export class SurfaceRope extends WrapTether {
  constructor(p, dt) {
    super(p);
    this.modelName = 'surface';
    this.massScale = Math.max(1, p.mass_scale);
    this.kout = new Float64Array(5);
    this.updateEvery = Math.max(1, p.update_every | 0);
    this.tick = -1;
    this.chainE = 0;
    this.Tanchor = p.pretension;
    this.h = dt;
    this.T0 = Math.max(0, p.pretension);
    this.ds = p.element_length;
    this.m = Math.max(p.lin_density, 1e-3) * this.ds;
    this.N = Math.ceil(p.length / this.ds) + 3;
    this.x = new Float64Array(this.N);
    this.z = new Float64Array(this.N);
    this.vx = new Float64Array(this.N);
    this.vz = new Float64Array(this.N);
    this.zInit = new Float64Array(this.N);
    this.k = 0;
    this.w = 0;
    this.sw = p.handedness;
    this.sigD = 0;
    this.straight = false;
    this.lay = [1, 0];
    this.spanPrev = null;
    this.eNumeric = 0;
    this.windowTurns = Math.max(p.window_turns, Math.log(100) / (TWO_PI * Math.max(p.mu_wall, 0.05)));
    this.windowNodes = Math.max(4, Math.ceil(this.windowTurns * TWO_PI * this.kappa / this.ds));
    const hc = dt * this.updateEvery;
    this.mInertial = Math.max(this.m * this.massScale, (p.EA / this.ds) * hc * hc / 4);
  }

  initialLayout(rhoA, thetaA) {
    const p = this.p, ds = this.ds, rc = this.rc;
    if (rhoA <= rc) throw new Error('attachment point inside the rope radius');
    const lh = Math.sqrt(rhoA * rhoA - rc * rc);
    const woundMat = p.length - lh;
    if (woundMat <= ds) throw new Error('rope too short for the start position');
    const eps0 = this.T0 / p.EA;
    const u0 = woundMat * (1 + eps0) / this.kappa;
    const h = p.handedness;
    const beta = Math.acos(rc / rhoA);
    this.phi_a = thetaA - h * beta - h * u0;
    this.sw = h;
    const k = Math.floor(woundMat / ds);
    const nAct = Math.min(this.N, k + 2);
    for (let i = 0; i < nAct; i++) {
      const u = i * ds * (1 + eps0) / this.kappa;
      this.x[i] = rc * (this.phi_a + h * u);
      this.z[i] = p.z_anchor + p.vertical * p.pitch * u / TWO_PI;
    }
    this.zInit.fill(0);
    for (let i = 0; i < nAct; i++) this.zInit[i] = this.z[i];
    this.k = k;
    this.sigD = woundMat;
    this.w = (woundMat - k * ds) / ds;
    const D = this.Dpoint();
    const A = [rhoA * Math.cos(thetaA), rhoA * Math.sin(thetaA), D[2]];
    this.s.u_s = u0;
    return { u0, wound0: woundMat, turns0: u0 / TWO_PI, free0: lh, D0: D, A0: A, phi_anchor: this.phi_a,
             helix_height: u0 / TWO_PI * p.pitch };
  }

  Dpoint() {
    const rc = this.rc, k = this.k, w = this.w;
    if (this.straight) return this.storedPoint(0);
    const xD = this.x[k] + w * (this.x[k + 1] - this.x[k]);
    const zD = this.z[k] + w * (this.z[k + 1] - this.z[k]);
    const phi = xD / rc;
    return [rc * Math.cos(phi), rc * Math.sin(phi), zD];
  }

  activate(j, xj, zj, g) {
    this.x[j] = xj; this.z[j] = zj;
    this.vx[j] = 0; this.vz[j] = 0;
    this.zInit[j] = zj;
    const L = Math.hypot(xj - this.x[j - 1], zj - this.z[j - 1]);
    const st = Math.max(L - this.ds, 0);
    return -(this.m * g * zj + 0.5 * this.p.EA / this.ds * st * st);
  }

  deactivate(j, g) {
    const L = j >= 1 ? Math.hypot(this.x[j] - this.x[j - 1], this.z[j] - this.z[j - 1]) : this.ds;
    const st = Math.max(L - this.ds, 0);
    const e = 0.5 * this.mInertial * (this.vx[j] ** 2 + this.vz[j] ** 2) + this.m * g * this.z[j]
      + 0.5 * this.p.EA / this.ds * st * st;
    this.vx[j] = 0; this.vz[j] = 0;
    return e;
  }

  updateDeparture(xDt, g) {
    const sw = this.sw, ds = this.ds, x = this.x;
    let flux = 0;
    while (this.k >= 1 && sw * xDt < sw * x[this.k]) {
      flux += this.deactivate(this.k + 1, g);
      this.k -= 1;
    }
    while (sw * xDt > sw * x[this.k + 1] && this.k + 2 < this.N) {
      this.k += 1;
      const j = this.k + 1;
      flux += this.activate(j, x[this.k] + ds * this.lay[0], this.z[this.k] + ds * this.lay[1], g);
    }
    const dx = x[this.k + 1] - x[this.k];
    const w = Math.abs(dx) < 1e-12 ? 0 : (xDt - x[this.k]) / dx;
    this.w = Math.min(1, Math.max(0, w));
    this.sigD = (this.k + this.w) * ds;
    return flux;
  }

  update(A, vA, wind, airDensity, g) {
    const p = this.p, s = this.s, h = this.h, rc = this.rc;
    if (!this.initialized) this.reset(A);
    const thetaU = this.trackTheta(A);
    const rho = Math.hypot(A[0], A[1]);
    const rhoC = Math.max(rho, rc * (1 + 1e-9));
    const beta = Math.acos(rc / rhoC);
    let flux = 0;
    const sigPrev = this.sigD;
    const xDt = rc * (thetaU - this.sw * beta);
    if (!this.straight) {
      flux += this.updateDeparture(xDt, g);
      if (this.k === 0 && this.sw * xDt <= this.sw * this.x[0]) {
        flux += this.deactivate(1, g);
        this.straight = true;
        this.sigD = 0;
      }
    }
    if (this.straight) {
      const x0 = this.x[0];
      for (const sgn of [this.sw, -this.sw]) {
        const xt = rc * (thetaU - sgn * beta);
        if (sgn * (xt - x0) > 0) {
          this.sw = sgn;
          this.straight = false;
          this.k = 0;
          this.lay = [sgn, 0];
          flux += this.activate(1, x0 + sgn * this.ds, this.z[0], g);
          flux += this.updateDeparture(xt, g);
          break;
        }
      }
    }
    const D = this.Dpoint();
    const rx = A[0] - D[0], ry = A[1] - D[1], rz = A[2] - D[2];
    const lFree = Math.sqrt(rx * rx + ry * ry + rz * rz);
    const e = lFree > 1e-9 ? [rx / lFree, ry / lFree, rz / lFree] : [0, 0, -1];
    const lRest = Math.max(p.length - this.sigD, 1e-3);
    const delta = lFree - lRest;
    const kAx = p.EA / lRest;
    const cAx = 2 * p.zeta * Math.sqrt(kAx * p.m_eff);
    const elasticFree = delta > 0 ? 0.5 * kAx * delta * delta : 0;
    const cphi = D[0] / rc, sphi = D[1] / rc;
    const exS = -e[0] * sphi + e[1] * cphi, ezS = e[2];
    const nrm = Math.hypot(exS, ezS);
    if (nrm > 1e-9) { this.lay[0] = exS / nrm; this.lay[1] = ezS / nrm; }
    const kk = this.k;
    const tx = this.x[kk + 1] - this.x[kk], tz = this.z[kk + 1] - this.z[kk];
    const tn = Math.hypot(tx, tz);
    const cosK = this.straight || tn <= 1e-12 ? 1 : (tx * this.lay[0] + tz * this.lay[1]) / tn;
    const release = Math.max(0, sigPrev - this.sigD) / h;
    let sigDot = 0;
    if (rho > 1e-9 && !this.straight) {
      const thetaDot = (A[0] * vA[1] - A[1] * vA[0]) / (rho * rho);
      const rhoDot = (A[0] * vA[0] + A[1] * vA[1]) / rho;
      const lh = Math.sqrt(Math.max(rhoC * rhoC - rc * rc, 1e-18));
      const betaDot = rc * rhoDot / (rhoC * lh);
      const xDdot = rc * (thetaDot - this.sw * betaDot);
      const dxds = (this.x[this.k + 1] - this.x[this.k]) / this.ds;
      sigDot = Math.abs(dxds) > 1e-6 ? xDdot / dxds : 0;
    }
    const eDotVA = e[0] * vA[0] + e[1] * vA[1] + e[2] * vA[2];
    const deltaDot = eDotVA + sigDot * (1 - cosK);
    const T = delta > 0 ? Math.max(0, kAx * delta + cAx * deltaDot) : 0;
    let pPeel = 0, pDamp = 0;
    if (this.spanPrev) {
      const [ePrev, wObj, wChain, fDamp, deltaPrev] = this.spanPrev;
      const dDamp = fDamp * (Math.max(delta, 0) - Math.max(deltaPrev, 0));
      pDamp = dDamp / h;
      const loss = wObj + wChain - (elasticFree - ePrev) - dDamp;
      if (loss >= 0) pPeel = loss / h; else this.eNumeric += -loss;
    }
    const [eFric, chainE, Tanchor] = this.stepChain(T * exS, T * ezS, g);
    const D2 = this.Dpoint();
    const dD = [D2[0] - D[0], D2[1] - D[1], D2[2] - D[2]];
    const fDamp = delta > 0 ? T - kAx * delta : 0;
    this.spanPrev = [elasticFree, T * eDotVA * h, -T * (e[0] * dD[0] + e[1] * dD[1] + e[2] * dD[2]), fDamp, delta];
    const freeMass = p.lin_density * lRest;
    const dist = this.distLoads(lFree, freeMass, D[2], rz, e[0], e[1], e[2], vA, wind, airDensity, g);
    const uS = this.straight ? 0
      : Math.abs(this.x[this.k] + this.w * (this.x[this.k + 1] - this.x[this.k]) - this.x[0]) / rc;
    s.u_s = uS; s.psi = this.sw * uS; s.psi_g = 0; s.regime = this.straight ? 0 : this.sw;
    s.peeling = release > 0;
    s.theta_u = thetaU;
    s.P1 = D; s.D = D; s.A = [A[0], A[1], A[2]]; s.e = e;
    s.l_free = lFree; s.l_geo = 0; s.l_geom = lFree; s.l_rest = lRest;
    s.stored_len = this.sigD; s.wound_len = this.sigD;
    s.delta = delta; s.delta_dot = deltaDot;
    s.tension = T;
    s.tension_anchor = Tanchor;
    s.dist_load_on_obj = dist;
    s.force_on_obj = [-T * e[0] + dist[0], -T * e[1] + dist[1], -T * e[2] + dist[2]];
    s.slack = delta <= 0;
    s.above_top = A[2] > p.tower_height;
    s.fully_wound = lRest <= 1e-3;
    s.elastic_energy = elasticFree;
    s.chain_energy = chainE;
    s.p_damp = pDamp; s.p_peel = pPeel;
    s.kink_deg = Math.acos(clamp1(cosK)) * DEG;
    s.e_fric = eFric; s.e_massflux = flux;
    s.coil_drop = this.coilDrop();
    s.k = kAx; s.c = cAx;
    return s;
  }

  stepChain(fxEnd, fzEnd, g) {
    const kend = this.k + 1;
    if (this.straight) return [0, 0, Math.hypot(fxEnd, fzEnd)];
    this.tick += 1;
    if (this.tick % this.updateEvery) return [0, this.chainE, this.Tanchor];
    const p = this.p, h = this.h * this.updateEvery;
    const j0 = Math.max(1, kend - this.windowNodes);
    const out = this.kout;
    chainStep(this.x, this.z, this.vx, this.vz, j0 - 1, kend, this.ds, p.EA, p.zeta, this.mInertial, this.m, g, h,
              fxEnd, fzEnd, p.EA / Math.max(p.length - this.sigD, 1e-3), p.mu_wall, this.rc, p.vertical, p.rope_d,
              this.sw, this.w, out);
    this.chainE = out[1];
    this.Tanchor = out[2];
    return [out[0], this.chainE, this.Tanchor];
  }

  coilDrop() {
    const kend = this.k;
    if (this.straight || kend < 1) return 0;
    let mx = 0;
    for (let i = 1; i <= kend; i++) { const d = Math.abs(this.zInit[i] - this.z[i]); if (d > mx) mx = d; }
    return mx;
  }

  get woundTurns() { return this.s.u_s / TWO_PI; }

  wallPolyline(ptsPerTurn = 48) {
    if (this.straight) return [];
    const rc = this.rc, kend = this.k, pts = [];
    const perTurn = TWO_PI * this.kappa / this.ds;
    const stride = Math.max(1, Math.round(perTurn / Math.max(ptsPerTurn, 1)));
    for (let i = 0; i <= kend; i += stride) {
      const phi = this.x[i] / rc;
      pts.push([rc * Math.cos(phi), rc * Math.sin(phi), this.z[i]]);
    }
    if ((kend % stride) !== 0) {
      const phi = this.x[kend] / rc;
      pts.push([rc * Math.cos(phi), rc * Math.sin(phi), this.z[kend]]);
    }
    pts.push(this.Dpoint());
    return pts;
  }
}
