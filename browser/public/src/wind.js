// Porte de spinjump/wind.py: vento médio (perfil vertical opcional) + rajadas Ornstein–Uhlenbeck.
// O gerador aleatório é próprio (sementes iguais não reproduzem a sequência do NumPy). O estado
// inicial da rajada é sorteado da distribuição estacionária, ou vem do cenário exportado pelo Python
// (campo g0, usado nas comparações).

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class Wind {
  constructor(w, dt) {
    this.enabled = !!w.enabled;
    this.U = w.U;
    this.dir = [w.dir[0], w.dir[1]];
    this.sigma = w.sigma;
    this.tau = w.tau;
    this.alpha = w.alpha;
    this.zref = w.zref;
    this.a = Math.exp(-dt / this.tau);
    this.b = this.sigma * Math.sqrt(Math.max(0, 1 - this.a * this.a));
    this.rand = mulberry32(w.seed);
    this.spare = null;
    if (!this.enabled) this.g = [0, 0];
    else if (w.g0) this.g = [w.g0[0], w.g0[1]];
    else this.g = [this.sigma * this.normal(), this.sigma * this.normal()];
  }

  normal() {
    if (this.spare !== null) { const s = this.spare; this.spare = null; return s; }
    let u = 0;
    while (u === 0) u = this.rand();
    const v = this.rand();
    const r = Math.sqrt(-2 * Math.log(u));
    this.spare = r * Math.sin(2 * Math.PI * v);
    return r * Math.cos(2 * Math.PI * v);
  }

  advance() {
    if (this.enabled && this.sigma > 0) {
      const x0 = this.normal(), x1 = this.normal();
      this.g = [this.a * this.g[0] + this.b * x0, this.a * this.g[1] + this.b * x1];
    }
  }

  at(z) {
    if (!this.enabled) return [0, 0, 0];
    const u = this.alpha === 0 ? this.U : this.U * Math.pow(Math.max(z, 0.5) / this.zref, this.alpha);
    return [u * this.dir[0] + this.g[0], u * this.dir[1] + this.g[1], 0];
  }
}
