// Relatório da execução, gerado no navegador (equivalente a spinjump/report.py): página HTML
// autocontida com desfecho, respostas, balanço de energia, impactos e gráficos SVG, além dos
// arquivos de dados (timeseries.csv, summary.json, events.json, config_resolved.json).

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = (v, unit = '', nd = 2) => (v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(nd)}${unit ? ` ${unit}` : ''}`);

export const SAFETY = 'Simulation results are qualitative and exploratory, from a simplified model. They are not a '
  + 'human-safety validation and not instructions. The real activity can kill or seriously injure; never attempt it.';
const OUTCOME_TEXT = {
  AT_REST_CLEAN: 'The object came to rest on the ground without a structural hit.',
  HIT_STRUCTURE: 'The object hit the chimney above the structural-hit speed threshold.',
  REWOUND: 'The rope wound back onto the chimney (net rewinding above the threshold).',
  TIMEOUT: 'The time limit was reached before the object came to rest.',
  NUMERICAL_FAILURE: 'The integration diverged; the results are not meaningful.',
  STOPPED: 'The run was stopped by the user before it finished.',
};
const OUTCOME_COLOR = { AT_REST_CLEAN: '#0ca30c', HIT_STRUCTURE: '#d03b3b', NUMERICAL_FAILURE: '#d03b3b' };
const CLASS_COLOR = { OK: '#0ca30c', WARNING: '#d08a00', DAMAGE: '#d03b3b' };
const COLORS = ['#2a78d6', '#eb6834', '#0ca30c', '#8a4fd8', '#d03b3b'];

/** Colunas da série temporal (Float64Array plana + nomes) → objeto de arrays. */
export function columns(flat, fields) {
  const n = fields.length, rows = flat.length / n, out = {};
  fields.forEach((k, j) => { const a = new Float64Array(rows); for (let i = 0; i < rows; i++) a[i] = flat[i * n + j]; out[k] = a; });
  out.rows = rows;
  return out;
}

function thin(xs, ys, max = 1400) {
  const step = Math.max(1, Math.ceil(xs.length / max));
  const px = [], py = [];
  for (let i = 0; i < xs.length; i += step) { px.push(xs[i]); py.push(ys[i]); }
  if (xs.length && px[px.length - 1] !== xs[xs.length - 1]) { px.push(xs[xs.length - 1]); py.push(ys[ys.length - 1]); }
  return [px, py];
}

function niceTicks(lo, hi, n = 5) {
  const span = hi - lo || 1, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9 * span; v += step) out.push(Math.abs(v) < 1e-12 ? 0 : v);
  return out;
}
const tickLabel = (v) => (Math.abs(v) >= 1000 ? v.toFixed(0) : String(Number(v.toPrecision(4))));

/** Gráfico de linhas em SVG. series: [{x, y, label, color, dash}] */
function lineChart({ title, ylabel, xlabel = 'time (s)', series, hlines = [], vlines = [], ymin0 = false, equal = false,
                     circle = null, stems = false, W = 720, H = 300 }) {
  const m = { l: 62, r: 14, t: 30, b: 42 };
  let xs = [], ys = [];
  for (const s of series) { xs = xs.concat(s.x); ys = ys.concat(s.y); }
  for (const h of hlines) ys.push(h.y);
  if (circle) { xs.push(-circle.r, circle.r); ys.push(-circle.r, circle.r); }
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (!Number.isFinite(x0)) { x0 = 0; x1 = 1; y0 = 0; y1 = 1; }
  if (ymin0) y0 = Math.min(0, y0);
  if (y1 - y0 < 1e-9) { y0 -= 1; y1 += 1; }
  if (x1 - x0 < 1e-9) { x0 -= 1; x1 += 1; }
  const py = (y1 - y0) * 0.05; y1 += py; if (!ymin0) y0 -= py;
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  if (equal) {   // mesma escala nos dois eixos (vista de cima)
    const sx = pw / (x1 - x0), sy = ph / (y1 - y0), s = Math.min(sx, sy);
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    x0 = cx - pw / s / 2; x1 = cx + pw / s / 2; y0 = cy - ph / s / 2; y1 = cy + ph / s / 2;
  }
  const X = (v) => m.l + (v - x0) / (x1 - x0) * pw, Y = (v) => m.t + ph - (v - y0) / (y1 - y0) * ph;
  const g = [];
  g.push(`<rect x="${m.l}" y="${m.t}" width="${pw}" height="${ph}" fill="#fff" stroke="#d6d5ce"/>`);
  for (const v of niceTicks(x0, x1, 8)) g.push(`<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${m.t + ph}" stroke="#eceae3"/><text x="${X(v)}" y="${m.t + ph + 16}" text-anchor="middle">${tickLabel(v)}</text>`);
  for (const v of niceTicks(y0, y1, 5)) g.push(`<line x1="${m.l}" x2="${m.l + pw}" y1="${Y(v)}" y2="${Y(v)}" stroke="#eceae3"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${tickLabel(v)}</text>`);
  if (circle) g.push(`<circle cx="${X(0)}" cy="${Y(0)}" r="${Math.abs(X(circle.r) - X(0))}" fill="#b9aa9c" opacity="0.7"/>`);
  for (const h of hlines) g.push(`<line x1="${m.l}" x2="${m.l + pw}" y1="${Y(h.y)}" y2="${Y(h.y)}" stroke="${h.color || '#d03b3b'}" stroke-dasharray="5 4"/><text x="${m.l + pw - 4}" y="${Y(h.y) - 4}" text-anchor="end" fill="${h.color || '#d03b3b'}">${esc(h.label)}</text>`);
  for (const v of vlines) if (v.x != null && v.x >= x0 && v.x <= x1) g.push(`<line x1="${X(v.x)}" x2="${X(v.x)}" y1="${m.t}" y2="${m.t + ph}" stroke="#898781" stroke-dasharray="3 3"/><text x="${X(v.x) + 3}" y="${m.t + 12}" fill="#52514e">${esc(v.label)}</text>`);
  g.push(`<clipPath id="c${title.length}${W}"><rect x="${m.l}" y="${m.t}" width="${pw}" height="${ph}"/></clipPath>`);
  series.forEach((s, k) => {
    const col = s.color || COLORS[k % COLORS.length];
    if (stems) {
      s.x.forEach((xv, i) => g.push(`<line x1="${X(xv)}" x2="${X(xv)}" y1="${Y(0)}" y2="${Y(s.y[i])}" stroke="${s.colors?.[i] || col}" stroke-width="2"/><circle cx="${X(xv)}" cy="${Y(s.y[i])}" r="3.5" fill="${s.colors?.[i] || col}"/>`));
      return;
    }
    const d = s.x.map((xv, i) => `${i ? 'L' : 'M'}${X(xv).toFixed(1)},${Y(s.y[i]).toFixed(1)}`).join('');
    g.push(`<path d="${d}" fill="none" stroke="${col}" stroke-width="1.6"${s.dash ? ' stroke-dasharray="6 4"' : ''} clip-path="url(#c${title.length}${W})"/>`);
  });
  const legend = series.filter((s) => s.label).map((s, k) => `<tspan fill="${s.color || COLORS[k % COLORS.length]}">● </tspan><tspan>${esc(s.label)}   </tspan>`).join('');
  g.push(`<text x="${m.l}" y="18" font-weight="600" font-size="13">${esc(title)}</text>`);
  if (legend) g.push(`<text x="${m.l + pw}" y="18" text-anchor="end">${legend}</text>`);
  g.push(`<text x="${m.l + pw / 2}" y="${H - 6}" text-anchor="middle">${esc(xlabel)}</text>`);
  g.push(`<text transform="translate(14 ${m.t + ph / 2}) rotate(-90)" text-anchor="middle">${esc(ylabel)}</text>`);
  return `<figure><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(title)}" font-family="system-ui,sans-serif" font-size="11" fill="#33322f">${g.join('')}</svg></figure>`;
}

function nearestIndex(t, tq) {
  if (tq == null) return -1;
  let lo = 0, hi = t.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (t[mid] < tq) lo = mid + 1; else hi = mid; }
  return lo;
}

function badge(cls) {
  const c = CLASS_COLOR[cls] || '#898781';
  return `<span class="badge" style="border-color:${c};color:${c}">${esc(cls)}</span>`;
}

/** Monta os arquivos do relatório. r = { summary, events, samples, fields, cfg, notes, warnings, meta } */
export function buildReport(r) {
  const s = r.summary, ev = r.events, cfg = r.cfg, c = columns(r.samples, r.fields);
  const t = Array.from(c.t);
  const iG = nearestIndex(t, s.ground_t);
  const tAnchorMax = c.tension_anchor ? Math.max(...c.tension_anchor) : null;
  const towerEv = ev.filter((e) => e.surface === 'tower');
  const thrV = cfg.impact.structure_hit_speed_ms;
  const firstG = ev.find((e) => e.surface === 'ground');
  const strongest = ev.reduce((a, e) => (!a || e.decel_peak_g > a.decel_peak_g ? e : a), null);
  const thrG = cfg.impact.damage_threshold_g;
  const answers = [
    ['Did the object spiral around the chimney before reaching the ground?',
      s.ground_t == null ? 'It did not reach the ground.'
        : `${f(s.turns_before_ground, 'turns')} around the chimney before the first ground contact; rope turns on the wall `
          + `${f(s.wound_turns_initial)} → ${iG >= 0 ? f(c.wound_turns[iG]) : '—'}.`],
    ['Did it hit the structure?',
      `${s.tower_hits ? 'Yes' : 'No'}: ${towerEv.length} contact(s) with the tower, ${s.tower_hits} above ${thrV} m/s normal speed. `
      + `Closest approach of the object surface to the wall: ${f(s.wall_dist_min_m, 'm', 3)} at ${f(s.wall_dist_min_t, 's')}.`],
    ['How did it reach the ground?',
      s.ground_t == null ? '—' : `At ${f(s.ground_speed, 'm/s')} after ${f(s.ground_t, 's')}`
        + (firstG ? `; first ground event peak ${f(firstG.force_normal_peak_filtered_N, 'N', 0)} (${f(firstG.decel_peak_g, 'g', 1)}, ${firstG.classification}).` : '.')],
    ['First contact with the structure',
      s.first_tower_t == null ? 'No contact with the tower.' : `At ${f(s.first_tower_t, 's')}, normal speed ${f(s.first_tower_vn, 'm/s')}.`],
    ['Ground phase', s.ground_t == null ? '—' : `Slide path ${f(s.slide_path_m, 'm')}; `
      + (s.rest_t != null ? `at rest after ${f(s.rest_t - s.ground_t, 's')} on the ground.` : 'did not come to rest.')],
    ['Slack rope and rewinding', `Slack for ${f(s.slack_time_s, 's')} in total; largest net rewinding ${f(s.rewind_max_turns, 'turns')}.`],
    ['Rope tension', `Maximum ${f(s.tension_max_N, 'N', 0)} at ${f(s.tension_max_t, 's')} (at the anchor ${f(tAnchorMax, 'N', 0)}); `
      + `breaking load ${f(cfg.rope.breaking_load_N, 'N', 0)}; load warning ${s.load_warning ? 'ON' : 'off'}.`],
    ['Strongest impact', strongest ? `On the ${strongest.surface} at ${f(strongest.t_start, 's')}: ${f(strongest.decel_peak_g, 'g', 1)}, `
      + `raw peak force ${f(strongest.force_normal_peak_raw_N, 'N', 0)} — ${strongest.classification}.` : 'None.'],
  ];
  const ENERGY_LABEL = { initial_J: 'initial mechanical energy', final_J: 'final mechanical energy',
    drag_object_work_J: 'air drag work on the object (includes wind)', rope_axial_damping_J: 'rope axial damping',
    rope_peel_kink_J: 'rope bending when peeling off the wall', coil_wall_friction_J: 'rope–wall friction (sliding coils)',
    contact_and_residual_J: 'contacts (ground/tower) and numerical residual' };
  const energy = Object.entries(s.energy || {}).map(([k, v]) => `<tr><td>${esc(ENERGY_LABEL[k] || k)}</td><td class="num">${f(v, '', 1)}</td></tr>`).join('');
  const evRows = ev.map((e) => `<tr><td>${e.surface}</td><td class="num">${f(e.t_start, '', 3)}</td><td class="num">${f(e.duration_s, '', 3)}</td>`
    + `<td class="num">${f(e.speed_in_ms)}</td><td class="num">${f(e.v_normal_in_ms)}</td><td class="num">${f(e.force_normal_peak_raw_N, '', 0)}</td>`
    + `<td class="num">${f(e.force_normal_peak_filtered_N, '', 0)}</td><td class="num">${f(e.impulse_normal_impact_Ns, '', 1)}</td>`
    + `<td class="num">${f(e.decel_peak_g, '', 1)}</td><td>${badge(e.classification)}</td><td>${esc(e.geoms.join(', '))}</td></tr>`).join('');
  const vG = [{ x: s.ground_t, label: 'ground' }];
  const plots = [];
  const [tx, txy] = thin(Array.from(c.x), Array.from(c.y));
  plots.push(lineChart({ title: 'Trajectory seen from above (centre of mass)', xlabel: 'x (m)', ylabel: 'y (m)', equal: true,
    circle: { r: cfg.tower.diameter_m / 2 }, series: [{ x: tx, y: txy, label: 'path' }], W: 560, H: 520 }));
  const S = (k) => thin(t, Array.from(c[k]));
  const ser = (k, label, color, dash) => { const [x, y] = S(k); return { x, y, label, color, dash }; };
  plots.push(lineChart({ title: 'Height', ylabel: 'm', ymin0: true, vlines: vG,
    series: [ser('z', 'centre of mass'), ser('floor', 'lowest point', '#eb6834')] }));
  plots.push(lineChart({ title: 'Speed', ylabel: 'm/s', ymin0: true, vlines: vG, series: [ser('speed', 'speed')] }));
  plots.push(lineChart({ title: 'Rope tension', ylabel: 'N', ymin0: true, vlines: vG,
    hlines: [{ y: cfg.rope.load_warn_fraction * cfg.rope.breaking_load_N, label: `${cfg.rope.load_warn_fraction} × breaking load` }],
    series: [ser('tension', 'at the object'), ser('tension_anchor', 'at the anchor', '#8a4fd8', true)] }));
  plots.push(lineChart({ title: 'Distance from the object surface to the wall', ylabel: 'm', ymin0: true, vlines: vG,
    hlines: [{ y: 0, label: 'contact', color: '#898781' }], series: [ser('wall_dist', 'distance')] }));
  plots.push(lineChart({ title: 'Rope on the wall and turns of the object', ylabel: 'turns', vlines: vG,
    series: [ser('wound_turns', 'rope turns on the wall'), ser('theta_turns', 'object turns around the chimney', '#0ca30c')] }));
  if (cfg.rope.coil_sliding) plots.push(lineChart({ title: 'Coil slide on the wall', ylabel: 'm', ymin0: true, vlines: vG, series: [ser('coil_drop', 'largest coil drop')] }));
  plots.push(lineChart({ title: 'Mechanical energy (object + rope)', ylabel: 'J', vlines: vG, series: [ser('e_total', 'total')] }));
  if (ev.length) {
    plots.push(lineChart({ title: 'Impacts: peak deceleration (filtered)', ylabel: 'g', ymin0: true, stems: true,
      hlines: thrG ? [{ y: thrG, label: `illustrative threshold ${thrG} g` }] : [],
      series: [{ x: ev.map((e) => e.t_start), y: ev.map((e) => e.decel_peak_g), colors: ev.map((e) => CLASS_COLOR[e.classification]) }] }));
  }
  const m = r.meta;
  const oc = s.outcome;
  const name = cfg.name || 'custom';
  const warns = (r.warnings || []).map((w) => `<li>${esc(w)}</li>`).join('');
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpinJump report · ${esc(name)}</title>
<style>
:root{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--grid:#e1e0d9}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}
.warn{border-left:4px solid #d03b3b;background:#fff;padding:10px 14px;margin:12px 0}
.outcome{border-left:6px solid ${OUTCOME_COLOR[oc] || '#d08a00'};background:#fff;padding:10px 14px;font-size:16px}
table{border-collapse:collapse;background:var(--surface);width:100%;margin:8px 0;font-size:13px}
td,th{border-bottom:1px solid var(--grid);padding:4px 8px;text-align:left} .num{text-align:right;font-variant-numeric:tabular-nums}
dt{font-weight:600;margin-top:8px} dd{margin:2px 0 0 0;color:var(--ink2)}
.badge{display:inline-block;border:1px solid;border-radius:10px;padding:0 7px;font-size:12px;font-weight:600}
figure{margin:12px 0;background:var(--surface)} .scroll{overflow-x:auto} pre{background:#fff;padding:10px;overflow:auto;font-size:12px}
.meta{color:var(--ink2)}
</style></head><body><main>
<h1>SpinJump report: ${esc(name)}</h1>
<div class="warn"><strong>Notice:</strong> ${esc(SAFETY)}</div>
<div class="outcome"><strong>${esc(oc)}</strong> — ${esc(OUTCOME_TEXT[oc] || '')} ${esc(s.failure || '')}</div>
<p class="meta">Generated in the browser on ${esc(m.date)} · rope model: ${cfg.rope.coil_sliding ? 'sliding coils' : 'locked coils'} ·
MuJoCo ${esc(m.mujoco)} (WebAssembly) · time step ${cfg.solver.timestep_s} s · simulated ${f(s.sim_time_s, 's')} ·
CPU ${f(s.sim_time_s * (s.cpu_s_per_sim_s || 0), 's', 1)} (${f(s.us_per_step, 'µs/step', 1)}) · wind seed ${cfg.wind.seed}
(browser random generator; gust sequences differ from the Python version) · ${esc(m.userAgent)}</p>
<h2>Answers</h2><dl>${answers.map(([q, a]) => `<dt>${esc(q)}</dt><dd>${esc(a)}</dd>`).join('')}</dl>
<h2>Rope length</h2><p>L = ${f(Number(cfg.rope.length_m), 'm')} (${esc(r.notes.rope_length_source)}). Simplified estimate:
v = √(2gH + v0²) = ${f(r.notes.rope_length_estimate.v_ms, 'm/s')}, r_min = v·√(H/g) = ${f(r.notes.rope_length_estimate.r_min_m, 'm')},
L = √(r_min² + H²) = ${f(r.notes.rope_length_estimate.L_m, 'm')}.</p>
<h2>Energy balance (J)</h2><table>${energy}</table>
<h2>Impacts</h2><p>Classification compares the filtered peak deceleration with an <b>illustrative</b> threshold
(${thrG ? `${thrG} g` : `${cfg.impact.damage_threshold_N} N`}; WARNING from ${cfg.impact.warn_fraction} of it). It is not an injury criterion.</p>
<div class="scroll"><table><tr><th>surface</th><th>t (s)</th><th>duration (s)</th><th>speed in (m/s)</th><th>normal speed in (m/s)</th>
<th>peak force raw (N)</th><th>peak force filtered (N)</th><th>impulse (N·s)</th><th>peak (g)</th><th>class</th><th>geoms</th></tr>
${evRows || '<tr><td colspan="11">none</td></tr>'}</table></div>
${warns ? `<h2>Warnings</h2><ul>${warns}</ul>` : ''}
<h2>Plots</h2>${plots.join('\n')}
<h2>Resolved configuration</h2><details><summary>show</summary><pre>${esc(JSON.stringify(cfg, null, 1))}</pre></details>
<p class="meta">Source code and the full Python version: <a href="https://github.com/rdrsdr/spinjump">github.com/rdrsdr/spinjump</a>.</p>
</main></body></html>`;
  const csv = [r.fields.join(',')];
  for (let i = 0; i < c.rows; i++) csv.push(r.fields.map((k) => Number(c[k][i].toPrecision(6))).join(','));
  return {
    'summary.html': html,
    'timeseries.csv': csv.join('\n') + '\n',
    'summary.json': JSON.stringify({ notice: SAFETY, ...s, warnings: r.warnings, meta: m }, null, 1),
    'events.json': JSON.stringify({ events: ev, threshold_g: thrG, note: 'illustrative threshold, not an injury criterion' }, null, 1),
    'config_resolved.json': JSON.stringify({ notice: SAFETY, ...cfg, _resolution: r.notes }, null, 1),
  };
}
