// Página do simulador: formulário de parâmetros, cena three.js (eixo z para cima, como no MuJoCo),
// telemetria e relatório. A física roda no Web Worker (worker.js); aqui se monta a configuração e se
// desenha o que ele envia, interpolando entre quadros para o movimento ficar suave.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/OrbitControls.js';
import { loadRaw, getPath } from './src/config.js';
import { buildReport } from './src/report.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const drawEnabled = params.get('render') !== '0';   // render=0: só física (medição de desempenho)
const worker = new Worker('./worker.js', { type: 'module' });

// ------------------------------------------------------------------ formulário
// [caminho, rótulo, unidade, mín, máx, passo, tipo] — mesmos campos da versão com servidor
const FIELDS = [
  ['Tower', [
    ['tower.height_m', 'Height H', 'm', 5, 200, 0.5],
    ['tower.diameter_m', 'Diameter D', 'm', 0.5, 20, 0.1],
    ['tower.wall_friction', 'Object–wall friction', '', 0, 1.5, 0.05],
  ]],
  ['Rope', [
    ['rope.coil_sliding', 'Coils can slide on the wall (more realistic, slower)', '', null, null, null, 'bool'],
    ['rope.helix_vertical', 'Coils unwind from', '', null, null, null, ['down', 'up']],
    ['rope.winding_pretension_N', 'Winding pretension', 'N', 0, 500, 1],
    ['rope.length_auto', 'Automatic length', '', null, null, null, 'bool'],
    ['rope.length_m', 'Length L', 'm', 5, 400, 0.5],
    ['rope.axial_EA_N', 'Axial stiffness EA', 'N', 1000, 1e6, 1000],
    ['rope.axial_damping_ratio', 'Damping ratio ζ', '', 0, 1, 0.01],
    ['rope.wall_friction', 'Rope–wall friction', '', 0, 1.5, 0.05],
    ['rope.winding_handedness', 'Helix direction', '', null, null, null, ['ccw', 'cw']],
    ['rope.winding_pitch_factor', 'Pitch / diameter', '', 1, 5, 0.05],
    ['rope.linear_density_kg_m', 'Linear density', 'kg/m', 0, 1, 0.005],
    ['rope.wind_drag_Cd_normal', 'Normal Cd', '', 0, 3, 0.05],
    ['rope.breaking_load_N', 'Breaking load', 'N', 1000, 100000, 500],
  ]],
  ['Object', [
    ['object.type', 'Type', '', null, null, null, ['mannequin', 'sandbag']],
    ['object.mass_kg', 'Mass', 'kg', 5, 200, 1],
    ['object.start_clearance_m', 'Initial clearance', 'm', 0, 5, 0.05],
    ['object.attach_height_fraction', 'Attachment (height fraction)', '', 0, 1, 0.05],
    ['object.drag_CdA_m2', 'Cd·A', 'm²', 0, 2, 0.05],
    ['object.geom_friction', 'Object friction', '', 0, 1.5, 0.05],
  ]],
  ['Launch', [
    ['launch.mode', 'Mode', '', null, null, null, ['velocity', 'impulse']],
    ['launch.speed_ms', 'Speed', 'm/s', 0, 30, 0.1],
    ['launch.impulse_Ns', 'Impulse J', 'N·s', 0, 2400, 10],
    ['launch.azimuth_deg', 'Azimuth (−180 to 180)', '°', -180, 180, 1],
    ['launch.elevation_deg', 'Elevation', '°', -60, 60, 1],
    ['launch.duration_ms', 'Duration (0 = instantaneous)', 'ms', 0, 2000, 10],
  ]],
  ['Air and wind', [
    ['air.enabled', 'Air drag', '', null, null, null, 'bool'],
    ['wind.enabled', 'Wind', '', null, null, null, 'bool'],
    ['wind.preset', 'Wind preset', '', null, null, null, ['', 'calm', 'light', 'breeze', 'strong']],
    ['wind.speed_mean_ms', 'Mean speed', 'm/s', 0, 40, 0.5],
    ['wind.direction_deg', 'Direction (blowing toward)', '°', -180, 360, 5],
    ['wind.gust_std_ms', 'Gusts (std. dev.)', 'm/s', 0, 10, 0.1],
    ['wind.correlation_time_s', 'Gust correlation time', 's', 0.1, 60, 0.1],
    ['wind.shear_exponent', 'Profile exponent', '', 0, 0.5, 0.01],
    ['wind.seed', 'Seed', '', 0, 1e9, 1],
  ]],
  ['Ground and contact', [
    ['ground.preset', 'Ground preset', '', null, null, null, ['', 'dry_asphalt', 'concrete', 'grass', 'wet', 'ice']],
    ['ground.friction_slide', 'Sliding friction', '', 0, 1.5, 0.05],
    ['ground.friction_rolling', 'Rolling resistance', 'm', 0, 0.2, 0.005],
    ['contact.solref_t', 'solref (time constant)', 's', 0.001, 0.1, 0.001],
  ]],
  ['Impact and run', [
    ['impact.damage_threshold_g', 'Damage threshold (illustrative)', 'g', 1, 200, 1],
    ['solver.max_time_s', 'Maximum time', 's', 1, 300, 1],
    ['solver.stop_on_structure_hit', 'Stop on tower hit', '', null, null, null, 'bool'],
  ]],
];
const OPTION_LABELS = { down: 'bottom coil', up: 'top coil', '': '(none)' };
// caminhos reais da configuração cobertos pelo formulário (para o link compartilhável)
const FORM_PATHS = new Set(FIELDS.flatMap(([, fs]) => fs.map((x) => x[0]))
  .filter((p) => p !== 'rope.length_auto' && p !== 'contact.solref_t').concat(['contact.solref']));

let base = null;       // config.json: padrão, presets, faixas
let presetRaw = null;  // configuração do preset escolhido (para "Reset" e para o link)

function setPath(obj, path, v) {
  const ks = path.split('.'); let o = obj;
  ks.slice(0, -1).forEach((k) => { o[k] = o[k] ?? {}; o = o[k]; });
  o[ks[ks.length - 1]] = v;
}

function buildForm() {
  const form = $('form');
  form.innerHTML = '';
  for (const [title, fields] of FIELDS) {
    const fs = document.createElement('details');
    fs.className = 'group';
    fs.open = title === 'Launch';
    fs.innerHTML = `<summary>${title}</summary>`;
    for (const [path, label, unit, min, max, step, kind] of fields) {
      const lab = document.createElement('label');
      lab.className = kind === 'bool' ? 'check' : 'field';
      let input;
      if (Array.isArray(kind)) {
        input = document.createElement('select');
        for (const o of kind) { const op = document.createElement('option'); op.value = o; op.textContent = OPTION_LABELS[o] ?? o; input.appendChild(op); }
      } else if (kind === 'bool') {
        input = document.createElement('input'); input.type = 'checkbox';
      } else {
        input = document.createElement('input'); input.type = 'number'; input.inputMode = 'decimal';
        if (min !== null) input.min = min; if (max !== null) input.max = max; if (step !== null) input.step = step;
      }
      input.name = path;
      const txt = `<span>${label}${unit ? ` <span class="unit">(${unit})</span>` : ''}</span>`;
      if (kind === 'bool') { lab.appendChild(input); lab.insertAdjacentHTML('beforeend', txt); }
      else { lab.innerHTML = txt; lab.appendChild(input); }
      fs.appendChild(lab);
    }
    if (title === 'Launch') fs.insertAdjacentHTML('beforeend', '<p class="desc" id="launch-hint"></p>');
    form.appendChild(fs);
  }
}

function fillForm(cfg) {
  for (const el of $('form').elements) {
    const p = el.name; if (!p) continue;
    let v;
    if (p === 'rope.length_auto') v = cfg.rope.length_m === 'auto';
    else if (p === 'rope.length_m') v = cfg.rope.length_m === 'auto' ? '' : cfg.rope.length_m;
    else if (p === 'contact.solref_t') v = cfg.contact.solref[0];
    else v = getPath(cfg, p);
    if (el.type === 'checkbox') el.checked = !!v;
    else el.value = v ?? '';
  }
  updateVisibility();
}

function updateVisibility() {
  const f = $('form').elements;
  const mode = f['launch.mode'].value;
  f['launch.speed_ms'].closest('label').hidden = mode !== 'velocity';
  f['launch.impulse_Ns'].closest('label').hidden = mode !== 'impulse';
  f['rope.length_m'].disabled = f['rope.length_auto'].checked;
  const m = parseFloat(f['object.mass_kg'].value) || 0;
  let txt;
  if (mode === 'velocity') txt = `Equivalent impulse J = m·Δv = ${(m * (parseFloat(f['launch.speed_ms'].value) || 0)).toFixed(0)} N·s.`;
  else { const J = parseFloat(f['launch.impulse_Ns'].value) || 0; txt = `Δv = J/m = ${(m > 0 ? J / m : 0).toFixed(2)} m/s.`; }
  $('launch-hint').textContent = `${txt} Azimuth 0° = along the free span, away from the chimney; positive = unwinding direction.`;
}

/** Valores do formulário como alterações sobre o preset (mesmo formato da versão com servidor). */
function readForm() {
  const out = {};
  const f = $('form').elements;
  for (const el of f) {
    const p = el.name; if (!p || p === 'rope.length_auto') continue;
    if (p === 'rope.length_m') { setPath(out, p, f['rope.length_auto'].checked ? 'auto' : (el.value === '' ? null : parseFloat(el.value))); continue; }
    if (p === 'contact.solref_t') { setPath(out, 'contact.solref', [parseFloat(el.value), presetRaw.contact.solref[1]]); continue; }
    if (el.type === 'checkbox') setPath(out, p, el.checked);
    else if (el.tagName === 'SELECT') setPath(out, p, el.value === '' ? null : el.value);
    else if (el.value === '') setPath(out, p, null);
    else setPath(out, p, p === 'wind.seed' ? parseInt(el.value, 10) : parseFloat(el.value));
  }
  if (out.launch.mode === 'velocity') out.launch.impulse_Ns = null; else out.launch.speed_ms = null;
  return out;
}

const setLines = () => $('sets').value.split('\n').map((s) => s.trim()).filter((s) => s && !s.startsWith('#'));

/** Configuração completa: padrão ← preset ← formulário ← linhas avançadas. */
function currentRaw() {
  return loadRaw(base, { preset: $('preset').value || null, extra: readForm(), sets: setLines() });
}

function showErrors(list) {
  $('errors').hidden = !list.length;
  $('errors').innerHTML = list.length ? `<b>Fix before starting:</b><ul>${list.map((e) => `<li>${e}</li>`).join('')}</ul>` : '';
}
function showWarnings(list) {
  $('warnings').hidden = !list.length;
  $('warnings').innerHTML = list.map((w) => `<p>${w}</p>`).join('');
}

// ------------------------------------------------------------------ cena
const canvas = $('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xb9cde0);
scene.fog = new THREE.Fog(0xb9cde0, 150, 600);
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 2000);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
let dirty = true;
controls.addEventListener('change', () => { dirty = true; });
scene.add(new THREE.HemisphereLight(0xeef3ff, 0x5b5346, 1.4));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(-40, 30, 100);
scene.add(sun);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(800, 800), new THREE.MeshLambertMaterial({ color: 0x6f7a63 }));
scene.add(ground);
const grid = new THREE.GridHelper(400, 80, 0x8f9a80, 0x7d886f);
grid.rotation.x = Math.PI / 2;
grid.position.z = 0.01;
scene.add(grid);

let tower = null;
let bodyMeshes = [];
const MAXP = 8192;
const wallGeo = new THREE.BufferGeometry();
wallGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MAXP * 3), 3));
const wallLine = new THREE.Line(wallGeo, new THREE.LineBasicMaterial({ color: 0xf2c94c }));
wallLine.frustumCulled = false;
scene.add(wallLine);
// vão livre como cilindro fino (linhas WebGL têm 1 px)
const span = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 6), new THREE.MeshLambertMaterial({ color: 0xe0b400 }));
scene.add(span);

const objPos = new THREE.Vector3(3.4, 0, 49.6);
function resetCamera() {
  controls.target.copy(objPos);
  camera.position.set(objPos.x + 10.6, objPos.y - 12, objPos.z + 3.4);
  dirty = true;
}

function buildStatic(info) {
  if (tower) scene.remove(tower);
  const { R, H } = info.tower;
  const tg = new THREE.CylinderGeometry(R, R, H, 64, 1);
  tg.rotateX(Math.PI / 2);
  tower = new THREE.Mesh(tg, new THREE.MeshLambertMaterial({ color: 0x9e8574 }));
  tower.position.set(0, 0, H / 2);
  scene.add(tower);
  for (const m of bodyMeshes) scene.remove(m);
  bodyMeshes = info.geoms.map((g) => {
    let geo;
    if (g.type === 3) { geo = new THREE.CapsuleGeometry(g.size[0], 2 * g.size[1], 6, 12); geo.rotateX(Math.PI / 2); }
    else geo = new THREE.SphereGeometry(g.size[0], 16, 12);
    const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: new THREE.Color(g.rgba[0], g.rgba[1], g.rgba[2]) }));
    scene.add(mesh);
    return mesh;
  });
  const r = Math.max(info.rope.d, 0.012) * 1.5;
  span.scale.set(r, 1, r);
  dirty = true;
}

// quadros recebidos (com quaternions pré-calculados) e relógio de exibição interpolado
let frames = [];
let dispT = 0;
const m4 = new THREE.Matrix4();
function prepFrame(f) {
  const n = f.geoms.length / 12;
  f.quats = [];
  for (let i = 0; i < n; i++) {
    const g = f.geoms.subarray(12 * i, 12 * i + 12);
    m4.set(g[3], g[4], g[5], 0, g[6], g[7], g[8], 0, g[9], g[10], g[11], 0, 0, 0, 0, 1);
    f.quats.push(new THREE.Quaternion().setFromRotationMatrix(m4));
  }
  return f;
}

const up = new THREE.Vector3(0, 1, 0);
const vA = new THREE.Vector3(), vB = new THREE.Vector3(), vD = new THREE.Vector3(), vT = new THREE.Vector3();
const lerp = (a, b, s) => a + (b - a) * s;

function drawAt(a, b, s) {
  bodyMeshes.forEach((mesh, i) => {
    const ga = a.geoms, gb = b.geoms, o = 12 * i;
    mesh.position.set(lerp(ga[o], gb[o], s), lerp(ga[o + 1], gb[o + 1], s), lerp(ga[o + 2], gb[o + 2], s));
    mesh.quaternion.slerpQuaternions(a.quats[i], b.quats[i], s);
  });
  const w = (s < 0.5 ? a : b).wall;
  const n = Math.min(w.length / 3, MAXP);
  wallGeo.attributes.position.array.set(w.subarray(0, 3 * n));
  wallGeo.setDrawRange(0, n);
  wallGeo.attributes.position.needsUpdate = true;
  vD.set(lerp(a.D[0], b.D[0], s), lerp(a.D[1], b.D[1], s), lerp(a.D[2], b.D[2], s));
  vA.set(lerp(a.A[0], b.A[0], s), lerp(a.A[1], b.A[1], s), lerp(a.A[2], b.A[2], s));
  const len = vD.distanceTo(vA);
  span.position.copy(vD).add(vA).multiplyScalar(0.5);
  span.quaternion.setFromUnitVectors(up, vB.copy(vA).sub(vD).normalize());
  span.scale.y = Math.max(len, 1e-3);
  objPos.set(lerp(a.geoms[0], b.geoms[0], s), lerp(a.geoms[1], b.geoms[1], s), lerp(a.geoms[2], b.geoms[2], s));
}

/** Par de quadros em torno do instante t e fração de interpolação. */
function frameAt(t) {
  const last = frames[frames.length - 1];
  if (frames.length === 1 || t >= last.t) return [last, last, 0];
  if (t <= frames[0].t) return [frames[0], frames[0], 0];
  let i = frames.length - 2;
  while (i > 0 && frames[i].t > t) i--;
  const a = frames[i], b = frames[i + 1];
  return [a, b, b.t > a.t ? (t - a.t) / (b.t - a.t) : 1];
}

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const pr = renderer.getPixelRatio();
  if (canvas.width !== Math.floor(w * pr) || canvas.height !== Math.floor(h * pr)) {
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
    dirty = true;
  }
}

let lastRaf = performance.now();
let lastUi = 0;
let drawn = [null, null, -1];
function animate(now) {
  const dtReal = Math.min((now - lastRaf) / 1000, 0.1);
  lastRaf = now;
  resize();
  if (frames.length) {
    const newest = frames[frames.length - 1].t;
    const sp = Number($('speed').value);
    if (state === 'running' && sp > 0) {
      // exibição ~2 quadros atrás do mais novo, para sempre haver um quadro à frente para interpolar
      const lag = 0.04 * sp;
      dispT += dtReal * sp;
      if (dispT > newest) dispT = newest;
      if (newest - dispT > lag + 0.25 * sp) dispT = newest - lag;
    } else dispT = newest;
    const [a, b, s] = frameAt(dispT);
    if (a !== drawn[0] || b !== drawn[1] || s !== drawn[2]) { drawAt(a, b, s); drawn = [a, b, s]; dirty = true; }
    if (now - lastUi > 120) { lastUi = now; showTele(s < 0.5 ? a : b); }
  }
  if ($('follow').checked) {
    // alvo e câmera andam juntos: mantém a distância e o ângulo escolhidos pelo usuário
    const dlt = vT.copy(objPos).sub(controls.target).multiplyScalar(0.25);
    if (dlt.lengthSq() > 1e-10) { controls.target.add(dlt); camera.position.add(dlt); dirty = true; }
  }
  if (controls.update()) dirty = true;
  if (dirty && drawEnabled) renderer.render(scene, camera);   // só redesenha quando algo mudou
  dirty = false;
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// ------------------------------------------------------------------ painel
const fmt = (v, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));
const PHASE = ['launch', 'airborne', 'ground', 'at rest'];
const hist = { z: [], T: [] };
let teleKey = '';
function showTele(f) {
  const t = f.tele;
  const rows = [['time (s)', fmt(t.t, 2)], ['speed (m/s)', fmt(t.speed, 2)], ['distance to floor (m)', fmt(t.floor, 2)],
    ['distance to wall (m)', fmt(t.wall, 2)], ['turns around the chimney', fmt(t.turns, 2)],
    ['rope turns on the wall', fmt(t.wound, 2)], ['rope tension (N)', fmt(t.tension, 0)],
    ['coil drop (m)', fmt(t.coil_drop, 2)], ['phase', PHASE[t.phase] || '—']];
  const key = rows.map((r) => r[1]).join('|');
  if (key === teleKey) return;
  teleKey = key;
  $('tele').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
  $('clock').textContent = `t = ${fmt(t.t, 1)} s`;
  spark('sp-height', hist.z, '#2a78d6');
  spark('sp-tension', hist.T, '#eb6834');
  if (f.events) showEvents(f.events);
}
function spark(id, ys, color) {
  const c = $(id), g = c.getContext('2d');
  const w = c.width, h = c.height;
  g.clearRect(0, 0, w, h);
  if (ys.length < 2) return;
  let mx = 1e-9, mn = 0;
  for (const y of ys) { if (y > mx) mx = y; if (y < mn) mn = y; }
  g.strokeStyle = color; g.lineWidth = 1.5; g.beginPath();
  const step = Math.max(1, Math.floor(ys.length / w));
  for (let i = 0; i < ys.length; i += step) {
    const X = (i / (ys.length - 1)) * (w - 2) + 1;
    const Y = h - 2 - ((ys[i] - mn) / (mx - mn || 1)) * (h - 4);
    i ? g.lineTo(X, Y) : g.moveTo(X, Y);
  }
  g.stroke();
}
let perfShown = 0;
function showPerf(p, force = false) {
  const now = performance.now();
  if (!force && now - perfShown < 500) return;
  perfShown = now;
  const rows = [['simulated / real time', p.rate == null ? '—' : `${fmt(p.rate, 2)}×`],
    ['physics load (one CPU core)', p.load == null ? '—' : `${fmt(100 * Math.min(p.load, 1), 0)} %`],
    ['CPU per physics step', p.us_per_step == null ? '—' : `${fmt(p.us_per_step, 1)} µs`]];
  $('perf').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}
let evKey = '';
function showEvents(ev) {
  const key = ev.length + '|' + ev.slice(-3).map((e) => `${e.t_start}:${e.decel_peak_g}:${e.classification}`).join(',');
  if (key === evKey) return;
  evKey = key;
  $('ev-count').textContent = ev.length ? `(${ev.length})` : '';
  if (!ev.length) { $('events').innerHTML = '<li class="empty">none yet</li>'; return; }
  let best = -1;
  ev.forEach((e, i) => { if (best < 0 || e.decel_peak_g > ev[best].decel_peak_g) best = i; });
  $('events').innerHTML = ev.map((e, i) => [i, e]).reverse().map(([i, e]) =>
    `<li><span>t=${fmt(e.t_start, 2)} s · ${e.surface}${i === best ? ' · <b>strongest</b>' : ''}</span>` +
    `<span>${fmt(e.decel_peak_g, 1)} g <span class="badge b-${e.classification}">${e.classification}</span></span></li>`).join('');
}
const OUTCOME = { AT_REST_CLEAN: 'at rest on the ground, no structure hit', HIT_STRUCTURE: 'hit the chimney',
  REWOUND: 'the rope rewound', TIMEOUT: 'time limit reached', NUMERICAL_FAILURE: 'numerical failure',
  STOPPED: 'stopped by the user' };

// arquivos do último relatório (URLs de blob, liberadas no relatório seguinte)
let reportUrls = {};
function makeReport(m) {
  for (const u of Object.values(reportUrls)) URL.revokeObjectURL(u);
  reportUrls = {};
  const files = buildReport({ summary: m.summary, events: m.events, ...m.report,
    meta: { date: new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC', mujoco: '3.15.0', userAgent: navigator.userAgent } });
  const TYPES = { html: 'text/html', csv: 'text/csv', json: 'application/json' };
  for (const [name, text] of Object.entries(files)) {
    reportUrls[name] = URL.createObjectURL(new Blob([text], { type: `${TYPES[name.split('.').pop()]};charset=utf-8` }));
  }
  window.__report = files;
}

function showResult(s) {
  const si = s.strongest_impact;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-');
  const dl = Object.keys(reportUrls).filter((n) => n !== 'summary.html')
    .map((n) => `<a href="${reportUrls[n]}" download="spinjump-${stamp}-${n}">${n}</a>`).join(' · ');
  $('result').innerHTML = `<h2>Result</h2><p><b>${s.outcome}</b> — ${OUTCOME[s.outcome] || ''}.</p>
    <dl class="tele">
    <dt>turns before reaching the ground</dt><dd>${fmt(s.turns_before_ground, 2)}</dd>
    <dt>ground arrival</dt><dd>${s.ground_t == null ? '—' : `${fmt(s.ground_speed, 1)} m/s at ${fmt(s.ground_t, 1)} s`}</dd>
    <dt>slide on the ground (m)</dt><dd>${fmt(s.slide_path_m, 1)}</dd>
    <dt>max rope tension (N)</dt><dd>${fmt(s.tension_max_N, 0)}</dd>
    <dt>closest approach to the wall (m)</dt><dd>${fmt(s.wall_dist_min_m, 2)}</dd>
    <dt>coil drop (m)</dt><dd>${fmt(s.coil_drop_max_m, 2)}</dd>
    <dt>strongest impact</dt><dd>${si ? `${fmt(si.g, 1)} g (${si.surface})` : '—'}</dd></dl>
    ${s.failure ? `<p class="desc">${s.failure}</p>` : ''}
    <div class="row"><button id="open-report" class="primary" type="button">Open the report</button>
      <a href="${reportUrls['summary.html']}" download="spinjump-${stamp}-report.html">download</a></div>
    <p class="desc">Data: ${dl}</p>
    <p class="desc">The report is generated in your browser and is not stored anywhere; download it to keep it.
      Impact labels compare with an illustrative threshold — not an injury criterion.</p>`;
  $('result').hidden = false;
  $('open-report').onclick = () => window.open(reportUrls['summary.html'], '_blank', 'noopener');
}

// ------------------------------------------------------------------ fluxo
let state = 'loading';   // loading | idle | invalid | running | paused | done
function setButtons() {
  $('start').disabled = state === 'loading' || state === 'running' || state === 'invalid';
  $('pause').disabled = !(state === 'running' || state === 'paused');
  $('stop').disabled = !(state === 'running' || state === 'paused');
  $('pause').textContent = state === 'paused' ? 'Resume' : 'Pause';
  $('start').textContent = state === 'done' || state === 'paused' ? 'Run again' : 'Start';
}

let camPlaced = false;
worker.onmessage = (ev) => {
  const m = ev.data;
  if (m.type === 'engine') { preview(); }
  else if (m.type === 'ready') {
    $('loading').hidden = true;
    buildStatic(m.info);
    frames = [prepFrame(m.frame)]; dispT = m.frame.t; drawn = [null, null, -1];
    hist.z = [m.frame.tele.floor]; hist.T = [m.frame.tele.tension];
    objPos.set(m.frame.geoms[0], m.frame.geoms[1], m.frame.geoms[2]);
    if (!camPlaced) { resetCamera(); camPlaced = true; }
    evKey = ''; teleKey = ''; showTele(m.frame); showEvents([]); showPerf({}, true);
    showErrors([]); showWarnings(m.info.warnings);
    $('preset-desc').textContent = `${presetDesc()} Rope ${fmt(m.info.rope.length, 1)} m (${m.info.rope.source}), `
      + `${fmt(m.info.turns0, 2)} turns on the wall; ${m.info.model === 'surface' ? 'sliding' : 'locked'} coils; `
      + `object ${fmt(m.info.mass, 1)} kg.`;
    state = m.auto ? 'running' : 'idle'; setButtons();
    if (m.auto) $('result').hidden = true;
    if (params.get('autostart') === '1' && !window.__benchStarted) { window.__benchStarted = true; start(); }
  } else if (m.type === 'invalid') {
    $('loading').hidden = true;
    showErrors(m.errors); showWarnings([]);
    state = 'invalid'; setButtons();
  } else if (m.type === 'frame') {
    frames.push(prepFrame(m.frame));
    if (frames.length > 40) frames.splice(0, frames.length - 40);
    hist.z.push(m.frame.tele.floor); hist.T.push(m.frame.tele.tension);
    if (hist.z.length > 6000) { hist.z.splice(0, 2000); hist.T.splice(0, 2000); }
    showPerf(m.perf);
    window.__lastPerf = m.perf;
  } else if (m.type === 'done') {
    showEvents(m.events);
    try { makeReport(m); } catch (e) { console.error(e); }
    showResult(m.summary);
    state = 'done'; setButtons();
    window.__benchResult = { summary: m.summary, perf: window.__lastPerf };
  } else if (m.type === 'error') {
    $('loading').hidden = false; $('loading').textContent = `Error: ${m.message}`;
    window.__benchResult = { error: m.message };
  } else if (m.type === 'log') console.log(m.text);
};

function presetDesc() {
  const p = base.presets.find((x) => x.name === $('preset').value);
  return p ? p.description : 'Default demo: sliding coils unwinding from the bottom, 4 m/s tangential launch.';
}

function rawOrErrors() {
  try { return currentRaw(); } catch (e) { showErrors([e.message]); state = 'invalid'; setButtons(); return null; }
}

/** Monta o cenário com os valores atuais e mostra a posição inicial (sem rodar). */
function preview() {
  if (state === 'running' || state === 'paused') {
    $('warnings').hidden = false;
    $('warnings').innerHTML = '<p>Changes apply on the next <b>Run again</b>.</p>';
    return;
  }
  const raw = rawOrErrors();
  if (raw) worker.postMessage({ type: 'load', raw });
}
let previewTimer = null;
function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(preview, 350); }

function start() {
  const raw = rawOrErrors();
  if (!raw) return;
  $('result').hidden = true;
  state = 'running'; setButtons();
  worker.postMessage({ type: 'start', raw, speed: Number($('speed').value) });
}
$('start').onclick = start;
$('pause').onclick = () => {
  if (state === 'running') { state = 'paused'; worker.postMessage({ type: 'pause' }); }
  else if (state === 'paused') { state = 'running'; worker.postMessage({ type: 'resume', speed: Number($('speed').value) }); }
  setButtons();
};
$('stop').onclick = () => worker.postMessage({ type: 'stop' });
$('speed').onchange = () => worker.postMessage({ type: 'speed', speed: Number($('speed').value) });
$('cam-reset').onclick = resetCamera;
$('form').addEventListener('input', () => { updateVisibility(); schedulePreview(); });
$('form').addEventListener('change', () => { updateVisibility(); schedulePreview(); });
$('sets').addEventListener('input', schedulePreview);
$('preset').onchange = () => { applyPreset(); preview(); };
$('reset').onclick = () => { applyPreset(); $('sets').value = ''; preview(); };

function applyPreset(sets = []) {
  const preset = $('preset').value || null;
  presetRaw = loadRaw(base, { preset });
  fillForm(sets.length ? loadRaw(base, { preset, sets }) : presetRaw);
}

/** Link com o preset e só o que difere dele (formulário + linhas avançadas). */
$('share').onclick = async () => {
  const q = new URLSearchParams();
  if ($('preset').value) q.set('preset', $('preset').value);
  let raw;
  try { raw = currentRaw(); } catch (e) { $('share-msg').textContent = e.message; return; }
  const extra = setLines();
  const extraPaths = new Set(extra.map((s) => s.split('=')[0].trim()));
  for (const p of FORM_PATHS) {
    if (extraPaths.has(p)) continue;
    const a = getPath(raw, p), b = getPath(presetRaw, p);
    if (JSON.stringify(a) !== JSON.stringify(b)) q.append('set', `${p}=${Array.isArray(a) ? JSON.stringify(a) : a}`);
  }
  for (const s of extra) q.append('set', s);
  const url = `${location.origin}${location.pathname}${q.toString() ? `?${q}` : ''}`;
  history.replaceState(null, '', url);
  try { await navigator.clipboard.writeText(url); $('share-msg').textContent = 'link copied'; }
  catch { $('share-msg').textContent = 'link is in the address bar'; }
  setTimeout(() => { $('share-msg').textContent = ''; }, 3000);
};

// ------------------------------------------------------------------ início
base = await (await fetch('./config.json')).json();
for (const p of base.presets) {
  const o = document.createElement('option');
  o.value = p.name; o.textContent = p.name.replace(/_/g, ' '); o.title = p.description;
  $('preset').appendChild(o);
}
buildForm();
const urlPreset = params.get('preset');
if (urlPreset && base.presets.some((p) => p.name === urlPreset)) $('preset').value = urlPreset;
// ?set=caminho=valor (repetível): campos do formulário vão para o formulário; o resto, para "Advanced"
const urlSets = params.getAll('set');
const formSets = urlSets.filter((s) => FORM_PATHS.has(s.split('=')[0].trim()));
$('sets').value = urlSets.filter((s) => !formSets.includes(s)).join('\n');
if ($('sets').value) $('sets').closest('details').open = true;
try { applyPreset(formSets); } catch (e) { applyPreset(); showErrors([e.message]); }
if (params.get('speed') != null) $('speed').value = params.get('speed');
setButtons();
worker.postMessage({ type: 'init', rules: base.rules });
