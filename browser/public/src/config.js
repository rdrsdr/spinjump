// Porte de spinjump/config.py: mesclagem de presets e alterações, validação (faixas exportadas do
// Pydantic em config.json + regras escritas à mão) e resolução (presets de vento/solo, comprimento
// "auto", impulso ↔ velocidade). Funciona no navegador e no Node.
export const G = 9.81;

const clone = (o) => JSON.parse(JSON.stringify(o));

export function deepMerge(base, over) {
  const out = clone(base);
  for (const [k, v] of Object.entries(over || {})) {
    if (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object'
        && !Array.isArray(out[k]) && k !== 'presets') out[k] = deepMerge(out[k], v);
    else out[k] = clone(v);
  }
  return out;
}

export const getPath = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);

export function setPath(obj, path, value) {
  const ks = path.split('.');
  let o = obj;
  for (const k of ks.slice(0, -1)) {
    if (!o[k] || typeof o[k] !== 'object') throw new Error(`invalid override path: ${path}`);
    o = o[k];
  }
  if (!(ks[ks.length - 1] in o)) throw new Error(`unknown parameter in override: ${path}`);
  o[ks[ks.length - 1]] = value;
}

/** Valor textual de um override "caminho=valor" com as regras simples do YAML. */
export function parseScalar(text) {
  const t = text.trim();
  if (/^(null|~)$/i.test(t)) return null;
  if (/^true$/i.test(t)) return true;
  if (/^false$/i.test(t)) return false;
  if (t !== '' && !Number.isNaN(Number(t))) return Number(t);
  if (t.startsWith('[')) return JSON.parse(t);
  return t.replace(/^["']|["']$/g, '');
}

/** Configuração bruta = padrão ← preset ← alterações (objeto) ← overrides "a.b=v" (como load_raw). */
export function loadRaw(base, { preset = null, extra = null, sets = [] } = {}) {
  let raw = clone(base.defaults);
  if (preset) {
    const p = base.presets.find((x) => x.name === preset);
    if (!p) throw new Error(`unknown preset: ${preset}`);
    raw = deepMerge(raw, p.overrides);
    if (!raw.name || raw.name === 'default') raw.name = preset;
  }
  if (extra) raw = deepMerge(raw, extra);
  for (const s of sets) {
    const i = s.indexOf('=');
    if (i < 0) throw new Error(`override must look like path=value: ${s}`);
    setPath(raw, s.slice(0, i).trim(), parseScalar(s.slice(i + 1)));
  }
  return raw;
}

function checkRule(path, v, r, errors) {
  if (v === null || v === undefined) { if (!r.nullable) errors.push(`${path}: a value is required`); return; }
  if (r.consts && r.consts.includes(v)) return;
  if (r.enum) { if (!r.enum.includes(v)) errors.push(`${path}: must be one of ${r.enum.join(', ')}`); return; }
  if (r.type === 'boolean') { if (typeof v !== 'boolean') errors.push(`${path}: must be true or false`); return; }
  if (r.type === 'array') {
    if (!Array.isArray(v) || v.some((x) => typeof x !== 'number' || !Number.isFinite(x))) errors.push(`${path}: must be a list of numbers`);
    else if ((r.minItems && v.length < r.minItems) || (r.maxItems && v.length > r.maxItems)) errors.push(`${path}: wrong number of items`);
    return;
  }
  if (r.type === 'number' || r.type === 'integer') {
    if (typeof v !== 'number' || !Number.isFinite(v)) { errors.push(`${path}: must be a number`); return; }
    if (r.type === 'integer' && !Number.isInteger(v)) errors.push(`${path}: must be an integer`);
    if (r.minimum !== undefined && v < r.minimum) errors.push(`${path}: must be ≥ ${r.minimum}`);
    if (r.maximum !== undefined && v > r.maximum) errors.push(`${path}: must be ≤ ${r.maximum}`);
    if (r.exclusiveMinimum !== undefined && v <= r.exclusiveMinimum) errors.push(`${path}: must be > ${r.exclusiveMinimum}`);
    if (r.exclusiveMaximum !== undefined && v >= r.exclusiveMaximum) errors.push(`${path}: must be < ${r.exclusiveMaximum}`);
  }
}

/** Converte textos numéricos em números onde a regra pede número (como o modo tolerante do Pydantic;
 *  o YAML 1.1 lê "5.0e7" como texto). Devolve uma cópia. */
export function coerce(cfg, rules) {
  const c = clone(cfg);
  for (const [path, r] of Object.entries(rules)) {
    const v = getPath(c, path);
    if ((r.type === 'number' || r.type === 'integer') && typeof v === 'string' && v.trim() !== ''
        && !(r.consts || []).includes(v) && Number.isFinite(Number(v))) setPath(c, path, Number(v));
  }
  return c;
}

/** Lista de erros (vazia = válida), equivalente a SimConfig.model_validate. */
export function validate(cfg, rules) {
  const errors = [];
  for (const [path, r] of Object.entries(rules)) checkRule(path, getPath(cfg, path), r, errors);
  for (const [sec, obj] of Object.entries(cfg)) {
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      for (const k of Object.keys(obj)) if (!(`${sec}.${k}` in rules)) errors.push(`${sec}.${k}: unknown parameter`);
    }
  }
  const { rope, launch, impact, tower, wind, ground } = cfg;
  if (rope.model !== 'wrap_tether') errors.push(`rope.model: only "wrap_tether" is supported`);
  if (rope.length_m !== 'auto' && typeof rope.length_m === 'number' && !(rope.length_m >= 1 && rope.length_m <= 2000)) {
    errors.push('rope.length_m: must be between 1 and 2000 m, or "auto"');
  }
  if (rope.axial_EA_N == null) errors.push('rope.axial_EA_N: a value is required');
  else if (!(rope.axial_EA_N >= 1e2 && rope.axial_EA_N <= 1e8)) errors.push('rope.axial_EA_N: must be between 100 and 1e8 N');
  if (launch.mode === 'velocity' && launch.speed_ms == null) errors.push('launch.speed_ms: required in velocity mode');
  if (launch.mode === 'impulse' && launch.impulse_Ns == null) errors.push('launch.impulse_Ns: required in impulse mode');
  if (impact.damage_threshold_g == null && impact.damage_threshold_N == null) errors.push('impact: set damage_threshold_g or damage_threshold_N');
  if (rope.anchor_below_top_m >= tower.height_m) errors.push('rope.anchor_below_top_m must be smaller than tower.height_m');
  if (wind.preset != null && !(wind.preset in wind.presets)) errors.push(`wind.preset "${wind.preset}" is not in wind.presets`);
  if (ground.preset != null && !(ground.preset in ground.presets)) errors.push(`ground.preset "${ground.preset}" is not in ground.presets`);
  return errors;
}

export function autoRopeLength(H, v0 = 0, g = G) {
  const v = Math.sqrt(2 * g * H + v0 * v0);
  const rMin = v * Math.sqrt(H / g);
  return { v_ms: v, r_min_m: rMin, L_m: Math.sqrt(rMin * rMin + H * H) };
}

export const launchSpeed = (c) => (c.launch.mode === 'velocity' ? c.launch.speed_ms : c.launch.impulse_Ns / c.object.mass_kg);
export const launchImpulse = (c) => (c.launch.mode === 'impulse' ? c.launch.impulse_Ns : c.launch.speed_ms * c.object.mass_kg);

/** round(x, 3) do Python (meio-par sobre a representação decimal exata). */
function round3(x) {
  const y = x * 1000, f = Math.floor(y), d = y - f;
  if (Math.abs(d - 0.5) < 1e-9) return (f % 2 === 0 ? f : f + 1) / 1000;
  return Math.round(y) / 1000;
}

/** Aplica presets de vento/solo e o comprimento "auto" (como config.resolve). */
export function resolve(cfg) {
  const c = clone(cfg);
  const notes = {};
  if (c.wind.preset != null) c.wind.speed_mean_ms = Number(c.wind.presets[c.wind.preset]);
  if (c.ground.preset != null) c.ground.friction_slide = Number(c.ground.presets[c.ground.preset]);
  const est = autoRopeLength(c.tower.height_m, launchSpeed(c));
  notes.rope_length_estimate = est;
  if (c.rope.length_m === 'auto') { c.rope.length_m = round3(est.L_m); notes.rope_length_source = 'automatic estimate'; }
  else notes.rope_length_source = 'set by the user';
  return { cfg: c, notes };
}
