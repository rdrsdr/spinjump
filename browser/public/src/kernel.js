// Porte de spinjump/_chain_kernel.py: passo implícito da corda encostada e cargas distribuídas.
// Mesma formulação: Euler implícito linearizado, matriz bloco-tridiagonal 2×2 resolvida por Thomas,
// atrito de Coulomb por conjunto ativo dentro da solução implícita e contato vertical entre voltas.

const TWO_PI = 2 * Math.PI;
const FRICTION_ITERS = 8;

// áreas de trabalho reaproveitadas entre chamadas (evita alocação a cada passo)
let cap = 0;
let W = null;
function work(n) {
  if (n <= cap) return W;
  cap = Math.max(n, 2 * cap, 64);
  const f = () => new Float64Array(cap);
  W = {
    L: f(), nx: f(), nz: f(), T: f(), axx: f(), azz: f(), axz: f(), FX: f(), FZ: f(),
    Dxx: f(), Dzz: f(), Dxz: f(), rx: f(), rz: f(), Nlim: f(), v0x: f(), v0z: f(), dvx: f(), dvz: f(),
    ffx: f(), ffz: f(), Exx: f(), Ezz: f(), Exz: f(), qx: f(), qz: f(), ox: f(), oz: f(), xo: f(), zo: f(),
    env: f(), Pxx: f(), Pzz: f(), Pxz: f(), px: f(), pz: f(), stick: new Uint8Array(cap),
  };
  return W;
}

function thomas(Dxx, Dzz, Dxz, axx, azz, axz, rx, rz, nm, dvx, dvz, w) {
  const Pxx = w.Pxx, Pzz = w.Pzz, Pxz = w.Pxz, qx = w.px, qz = w.pz;
  for (let j = 0; j < nm; j++) { Pxx[j] = Dxx[j]; Pzz[j] = Dzz[j]; Pxz[j] = Dxz[j]; qx[j] = rx[j]; qz[j] = rz[j]; }
  for (let j = 1; j < nm; j++) {
    const exx = -axx[j], ezz = -azz[j], exz = -axz[j];
    const det = Pxx[j - 1] * Pzz[j - 1] - Pxz[j - 1] * Pxz[j - 1];
    const ixx = Pzz[j - 1] / det, izz = Pxx[j - 1] / det, ixz = -Pxz[j - 1] / det;
    const wxx = exx * ixx + exz * ixz, wxz = exx * ixz + exz * izz;
    const wzx = exz * ixx + ezz * ixz, wzz = exz * ixz + ezz * izz;
    Pxx[j] -= wxx * exx + wxz * exz;
    Pxz[j] -= wxx * exz + wxz * ezz;
    Pzz[j] -= wzx * exz + wzz * ezz;
    qx[j] -= wxx * qx[j - 1] + wxz * qz[j - 1];
    qz[j] -= wzx * qx[j - 1] + wzz * qz[j - 1];
  }
  for (let j = nm - 1; j >= 0; j--) {
    let bx = qx[j], bz = qz[j];
    if (j + 1 < nm) {
      const exx = -axx[j + 1], ezz = -azz[j + 1], exz = -axz[j + 1];
      bx -= exx * dvx[j + 1] + exz * dvz[j + 1];
      bz -= exz * dvx[j + 1] + ezz * dvz[j + 1];
    }
    const det = Pxx[j] * Pzz[j] - Pxz[j] * Pxz[j];
    dvx[j] = (Pzz[j] * bx - Pxz[j] * bz) / det;
    dvz[j] = (Pxx[j] * bz - Pxz[j] * bx) / det;
  }
}

function matvec(Dxx, Dzz, Dxz, axx, azz, axz, dvx, dvz, nm, ox, oz) {
  for (let j = 0; j < nm; j++) {
    ox[j] = Dxx[j] * dvx[j] + Dxz[j] * dvz[j];
    oz[j] = Dxz[j] * dvx[j] + Dzz[j] * dvz[j];
    if (j + 1 < nm) {
      ox[j] -= axx[j + 1] * dvx[j + 1] + axz[j + 1] * dvz[j + 1];
      oz[j] -= axz[j + 1] * dvx[j + 1] + azz[j + 1] * dvz[j + 1];
    }
    if (j >= 1) {
      ox[j] -= axx[j] * dvx[j - 1] + axz[j] * dvz[j - 1];
      oz[j] -= axz[j] * dvx[j - 1] + azz[j] * dvz[j - 1];
    }
  }
}

/** Atualiza x, z, vx, vz nos nós b+1..kend (b fixo). out = [atrito J, energia J, T_âncora N, dDx, dDz]. */
export function chainStep(x, z, vx, vz, b, kend, ds, EA, zeta, m, mReal, g, h, fxEnd, fzEnd, ksEnd,
                          mu, rc, vertical, ropeD, sw, wD, out) {
  const n = kend - b + 1, nm = n - 1, nseg = n - 1;
  const w = work(kend + 2);
  const { L, nx, nz, T, axx, azz, axz, FX, FZ, Dxx, Dzz, Dxz, rx, rz, Nlim, v0x, v0z, dvx, dvz,
          ffx, ffz, Exx, Ezz, Exz, qx, qz, ox, oz, xo, zo, env, stick } = w;
  const EAds = EA / ds;
  const cseg0 = 2 * zeta * Math.sqrt(EAds * m);
  for (let i = 0; i < n; i++) { FX[i] = 0; FZ[i] = -mReal * g; }
  for (let s = 0; s < nseg; s++) {
    const i = b + s;
    const dx = x[i + 1] - x[i], dz = z[i + 1] - z[i];
    let Ls = Math.sqrt(dx * dx + dz * dz);
    if (Ls < 1e-12) Ls = 1e-12;
    const ux = dx / Ls, uz = dz / Ls;
    L[s] = Ls; nx[s] = ux; nz[s] = uz;
    const taut = Ls > ds ? 1 : 0;
    const Ts = EAds * (Ls - ds) * taut;
    T[s] = Ts;
    const c = cseg0 * taut;
    const v0x_ = s > 0 ? vx[i] : 0, v0z_ = s > 0 ? vz[i] : 0;
    const dvn = (vx[i + 1] - v0x_) * ux + (vz[i + 1] - v0z_) * uz;
    const fs = Ts + c * dvn;
    FX[s] += fs * ux; FZ[s] += fs * uz;
    FX[s + 1] -= fs * ux; FZ[s + 1] -= fs * uz;
    const gk = Ts / Ls;
    const kxx = taut * (EAds * ux * ux + gk * (1 - ux * ux));
    const kzz = taut * (EAds * uz * uz + gk * (1 - uz * uz));
    const kxz = taut * (EAds - gk) * ux * uz;
    axx[s] = h * c * ux * ux + h * h * kxx;
    azz[s] = h * c * uz * uz + h * h * kzz;
    axz[s] = h * c * ux * uz + h * h * kxz;
  }
  FX[n - 1] += wD * fxEnd; FZ[n - 1] += wD * fzEnd;
  if (n >= 3) { FX[n - 2] += (1 - wD) * fxEnd; FZ[n - 2] += (1 - wD) * fzEnd; }
  else { FX[n - 1] += (1 - wD) * fxEnd; FZ[n - 1] += (1 - wD) * fzEnd; }
  const Fm = Math.sqrt(fxEnd * fxEnd + fzEnd * fzEnd);
  for (let j = 0; j < nm; j++) {
    Dxx[j] = m + axx[j]; Dzz[j] = m + azz[j]; Dxz[j] = axz[j];
    if (j + 1 < nseg) { Dxx[j] += axx[j + 1]; Dzz[j] += azz[j + 1]; Dxz[j] += axz[j + 1]; }
  }
  if (Fm > 0) {
    const ux = fxEnd / Fm, uz = fzEnd / Fm;
    const pairs = [[nm - 1, wD * wD], [nm - 2, (1 - wD) * (1 - wD)]];
    for (const [jj, wt] of pairs) {
      if (jj >= 0) {
        Dxx[jj] += h * h * ksEnd * wt * ux * ux;
        Dzz[jj] += h * h * ksEnd * wt * uz * uz;
        Dxz[jj] += h * h * ksEnd * wt * ux * uz;
      }
    }
  }
  for (let j = 0; j < nm; j++) { rx[j] = h * FX[j + 1]; rz[j] = h * FZ[j + 1]; }
  for (let j = 0; j < nm; j++) {
    const i = b + 1 + j;
    let Tn, tx, tz;
    if (j < nm - 1) {
      Tn = 0.5 * (T[j] + T[j + 1]);
      tx = x[i + 1] - x[i - 1]; tz = z[i + 1] - z[i - 1];
    } else {
      Tn = 0.5 * (T[j] + Fm);
      tx = x[i] - x[i - 1] + (Fm > 0 ? fxEnd / Fm * ds : 0);
      tz = z[i] - z[i - 1] + (Fm > 0 ? fzEnd / Fm * ds : 0);
    }
    const t2 = tx * tx + tz * tz;
    const cos2 = t2 > 1e-18 ? tx * tx / t2 : 1;
    Nlim[j] = mu * Tn * ds * cos2 / rc;
  }
  for (let j = 0; j < nm; j++) { v0x[j] = vx[b + 1 + j]; v0z[j] = vz[b + 1 + j]; dvx[j] = 0; dvz[j] = 0; }
  thomas(Dxx, Dzz, Dxz, axx, azz, axz, rx, rz, nm, dvx, dvz, w);
  for (let j = 0; j < nm; j++) {
    const tvx = v0x[j] + dvx[j], tvz = v0z[j] + dvz[j];
    const vm = Math.sqrt(tvx * tvx + tvz * tvz);
    if (m * vm <= Nlim[j] * h) { stick[j] = 1; ffx[j] = 0; ffz[j] = 0; }
    else { stick[j] = 0; ffx[j] = -Nlim[j] * tvx / vm; ffz[j] = -Nlim[j] * tvz / vm; }
  }
  const PEN = 1e9 * (m + 1);
  for (let it = 0; it < FRICTION_ITERS; it++) {
    for (let j = 0; j < nm; j++) {
      if (stick[j]) {
        Exx[j] = Dxx[j] + PEN; Ezz[j] = Dzz[j] + PEN; Exz[j] = Dxz[j];
        qx[j] = -PEN * v0x[j]; qz[j] = -PEN * v0z[j];
      } else {
        Exx[j] = Dxx[j]; Ezz[j] = Dzz[j]; Exz[j] = Dxz[j];
        qx[j] = rx[j] + h * ffx[j]; qz[j] = rz[j] + h * ffz[j];
      }
    }
    thomas(Exx, Ezz, Exz, axx, azz, axz, qx, qz, nm, dvx, dvz, w);
    matvec(Dxx, Dzz, Dxz, axx, azz, axz, dvx, dvz, nm, ox, oz);
    let changed = false;
    for (let j = 0; j < nm; j++) {
      const nvx = v0x[j] + dvx[j], nvz = v0z[j] + dvz[j];
      if (stick[j]) {
        const fxReq = (ox[j] - rx[j]) / h, fzReq = (oz[j] - rz[j]) / h;
        const fr = Math.sqrt(fxReq * fxReq + fzReq * fzReq);
        if (fr > Nlim[j] * (1 + 1e-9)) {
          stick[j] = 0;
          ffx[j] = Nlim[j] * fxReq / fr; ffz[j] = Nlim[j] * fzReq / fr;
          changed = true;
        }
      } else if (nvx * ffx[j] + nvz * ffz[j] >= 0) {
        stick[j] = 1;
        changed = true;
      } else {
        const vm = Math.sqrt(nvx * nvx + nvz * nvz);
        ffx[j] = -Nlim[j] * nvx / vm; ffz[j] = -Nlim[j] * nvz / vm;
      }
    }
    if (!changed) break;
  }
  let eFric = 0;
  const kd = kend - 1 > b ? kend - 1 : kend;
  const xD0 = (1 - wD) * x[kd] + wD * x[kend], zD0 = (1 - wD) * z[kd] + wD * z[kend];
  for (let j = 0; j < nm; j++) {
    const i = b + 1 + j;
    if (stick[j]) { vx[i] = 0; vz[i] = 0; }
    else {
      vx[i] = v0x[j] + dvx[j]; vz[i] = v0z[j] + dvz[j];
      eFric += -(ffx[j] * vx[i] + ffz[j] * vz[i]) * h;
    }
  }
  for (let j = 0; j < nm; j++) {
    const i = b + 1 + j;
    xo[j] = x[i]; zo[j] = z[i];
    x[i] += h * vx[i]; z[i] += h * vz[i];
  }
  // contato entre voltas: material uma volta depois fica a ≥ d da volta anterior na vertical
  const turn = TWO_PI * rc;
  const na = kend + 1;
  let acc = -1e300;
  for (let i = 0; i < na; i++) { const v = sw * x[i]; if (v > acc) acc = v; env[i] = acc; }
  for (let j = 0; j < nm; j++) {
    const i = b + 1 + j;
    const q = sw * x[i] - turn;
    if (q < env[0]) continue;
    let lo = 0, hi = i;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (env[mid] <= q) lo = mid; else hi = mid; }
    const span = env[hi] - env[lo];
    let f = span > 1e-12 ? (q - env[lo]) / span : 0;
    if (f > 1) f = 1;
    const zp = z[lo] + f * (z[hi] - z[lo]);
    if (vertical < 0) { const lim = zp - ropeD; if (z[i] > lim) z[i] = lim; }
    else { const lim = zp + ropeD; if (z[i] < lim) z[i] = lim; }
  }
  for (let j = 0; j < nm; j++) {
    const i = b + 1 + j;
    vx[i] = (x[i] - xo[j]) / h; vz[i] = (z[i] - zo[j]) / h;
  }
  vx[b] = 0; vz[b] = 0;
  let E = 0, T0 = 0;
  for (let i = 1; i <= kend; i++) {
    E += 0.5 * m * (vx[i] * vx[i] + vz[i] * vz[i]) + mReal * g * z[i];
    const dx = x[i] - x[i - 1], dz = z[i] - z[i - 1];
    const st = Math.sqrt(dx * dx + dz * dz) - ds;
    if (st > 0) { E += 0.5 * EAds * st * st; if (i === 1) T0 = EAds * st; }
  }
  out[0] = eFric; out[1] = E; out[2] = T0;
  out[3] = (1 - wD) * x[kd] + wD * x[kend] - xD0;
  out[4] = (1 - wD) * z[kd] + wD * z[kend] - zD0;
}

/** Peso e arrasto distribuídos do vão livre; parcela transmitida ao objeto (regra da alavanca). */
export function distLoads(lFree, freeMass, Dz, rz, ex, ey, ez, vx, vy, vz, rho, cdn, cdt, d, elem, g,
                          windOn, wU, wdx, wdy, gx, gy, alpha, zref, out) {
  out[0] = 0; out[1] = 0; out[2] = 0;
  if (lFree <= 1e-6) return;
  const n = Math.max(1, Math.ceil(lFree / elem));
  const ds = lFree / n;
  let sqSum = 0, fx = 0, fy = 0, fz = 0;
  const q = 0.5 * rho * d * ds;
  const drag = rho > 0 && (cdn > 0 || cdt > 0);
  for (let i = 0; i < n; i++) {
    const sq = (i + 0.5) / n;
    sqSum += sq;
    if (drag) {
      let ux = sq * vx, uy = sq * vy;
      const uz = sq * vz;
      if (windOn) {
        let u;
        if (alpha === 0) u = wU;
        else { let zz = Dz + sq * rz; if (zz < 0.5) zz = 0.5; u = wU * Math.pow(zz / zref, alpha); }
        ux -= u * wdx + gx;
        uy -= u * wdy + gy;
      }
      const vt = ux * ex + uy * ey + uz * ez;
      const nx = ux - vt * ex, ny = uy - vt * ey, nz = uz - vt * ez;
      const vn = Math.sqrt(nx * nx + ny * ny + nz * nz);
      const cn = -q * cdn * vn * sq;
      const ct = -q * Math.PI * cdt * Math.abs(vt) * vt * sq;
      fx += cn * nx + ct * ex; fy += cn * ny + ct * ey; fz += cn * nz + ct * ez;
    }
  }
  out[0] = fx; out[1] = fy; out[2] = fz - g * (freeMass / n) * sqSum;
}
