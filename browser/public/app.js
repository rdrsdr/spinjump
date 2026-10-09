// Página: cena three.js (eixo z para cima, como no MuJoCo), controles e telemetria. A física roda
// no Web Worker (worker.js); aqui só se desenha o que ele envia.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const drawEnabled = params.get('render') !== '0';   // render=0: só física (medição de desempenho)
const worker = new Worker('./worker.js', { type: 'module' });

// ------------------------------------------------------------------ cena
const canvas = $('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xb9cde0);
scene.fog = new THREE.Fog(0xb9cde0, 150, 600);
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 2000);
camera.up.set(0, 0, 1);
camera.position.set(14, -12, 53);
const controls = new OrbitControls(camera, canvas);
controls.target.set(3.4, 0, 49.6);
controls.enableDamping = true;
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
const freeGeo = new THREE.BufferGeometry();
freeGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
const freeLine = new THREE.Line(freeGeo, new THREE.LineBasicMaterial({ color: 0xffd84d }));
freeLine.frustumCulled = false;
scene.add(freeLine);
// vão livre também como cilindro fino (linhas WebGL têm 1 px)
const span = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 6), new THREE.MeshLambertMaterial({ color: 0xe0b400 }));
scene.add(span);

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
    mesh.matrixAutoUpdate = false;
    scene.add(mesh);
    return mesh;
  });
  span.scale.set(Math.max(info.rope.d, 0.012) * 1.5, 1, Math.max(info.rope.d, 0.012) * 1.5);
}

const up = new THREE.Vector3(0, 1, 0);
const tmpA = new THREE.Vector3(), tmpB = new THREE.Vector3(), tmpD = new THREE.Vector3();
let objPos = new THREE.Vector3(3.4, 0, 49.6);

function drawFrame(f) {
  f.geoms.forEach((g, i) => {
    const mesh = bodyMeshes[i];
    if (!mesh) return;
    mesh.matrix.set(g[3], g[4], g[5], g[0], g[6], g[7], g[8], g[1], g[9], g[10], g[11], g[2], 0, 0, 0, 1);
  });
  const pos = wallGeo.attributes.position.array;
  const n = Math.min(f.wall.length, MAXP);
  for (let i = 0; i < n; i++) { pos[3 * i] = f.wall[i][0]; pos[3 * i + 1] = f.wall[i][1]; pos[3 * i + 2] = f.wall[i][2]; }
  wallGeo.setDrawRange(0, n);
  wallGeo.attributes.position.needsUpdate = true;
  const fp = freeGeo.attributes.position.array;
  fp.set([...f.D, ...f.A]);
  freeGeo.attributes.position.needsUpdate = true;
  tmpD.set(...f.D); tmpA.set(...f.A);
  const len = tmpD.distanceTo(tmpA);
  span.position.copy(tmpD).add(tmpA).multiplyScalar(0.5);
  span.quaternion.setFromUnitVectors(up, tmpB.copy(tmpA).sub(tmpD).normalize());
  span.scale.y = Math.max(len, 1e-3);
  objPos.set(f.geoms[0][0], f.geoms[0][1], f.geoms[0][2]);
}

const followDelta = new THREE.Vector3();
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }
}
function animate() {
  resize();
  if ($('follow').checked) {
    // alvo e câmera andam juntos: mantém a distância e o ângulo escolhidos pelo usuário
    const dlt = followDelta.copy(objPos).sub(controls.target).multiplyScalar(0.25);
    controls.target.add(dlt);
    camera.position.add(dlt);
  }
  controls.update();
  if (drawEnabled) renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// ------------------------------------------------------------------ painel
const fmt = (v, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));
const PHASE = ['launch', 'airborne', 'ground', 'at rest'];
function showTele(t) {
  const rows = [['time (s)', fmt(t.t, 2)], ['speed (m/s)', fmt(t.speed, 2)], ['distance to floor (m)', fmt(t.floor, 2)],
    ['distance to wall (m)', fmt(t.wall, 2)], ['turns around the chimney', fmt(t.turns, 2)],
    ['rope turns on the wall', fmt(t.wound, 2)], ['rope tension (N)', fmt(t.tension, 0)],
    ['coil drop (m)', fmt(t.coil_drop, 2)], ['phase', PHASE[t.phase] || '—']];
  $('tele').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}
function showPerf(p) {
  const rows = [['simulated / real time', p.rate == null ? '—' : `${fmt(p.rate, 2)}×`],
    ['CPU per physics step', p.us_per_step == null ? '—' : `${fmt(p.us_per_step, 1)} µs`],
    ['steps per simulated second', '4000']];
  $('perf').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}
function showEvents(ev) {
  $('ev-count').textContent = ev.length ? `(${ev.length})` : '';
  if (!ev.length) { $('events').innerHTML = '<li class="empty">none yet</li>'; return; }
  let best = -1;
  ev.forEach((e, i) => { if (best < 0 || e.decel_peak_g > ev[best].decel_peak_g) best = i; });
  $('events').innerHTML = ev.map((e, i) => [i, e]).reverse().map(([i, e]) =>
    `<li><span>t=${fmt(e.t_start, 2)} s · ${e.surface}${i === best ? ' · <b>strongest</b>' : ''}</span>` +
    `<span>${fmt(e.decel_peak_g, 1)} g <span class="badge b-${e.classification}">${e.classification}</span></span></li>`).join('');
}
const OUTCOME = { AT_REST_CLEAN: 'at rest on the ground, no structure hit', HIT_STRUCTURE: 'hit the chimney',
  REWOUND: 'the rope rewound', TIMEOUT: 'time limit reached', NUMERICAL_FAILURE: 'numerical failure' };
function showResult(s) {
  const si = s.strongest_impact;
  $('result').innerHTML = `<h2>Result</h2><p><b>${s.outcome}</b> — ${OUTCOME[s.outcome] || ''}.</p>
    <dl class="tele">
    <dt>turns before reaching the ground</dt><dd>${fmt(s.turns_before_ground, 2)}</dd>
    <dt>ground arrival</dt><dd>${s.ground_t == null ? '—' : `${fmt(s.ground_speed, 1)} m/s at ${fmt(s.ground_t, 1)} s`}</dd>
    <dt>slide on the ground (m)</dt><dd>${fmt(s.slide_path_m, 1)}</dd>
    <dt>max rope tension (N)</dt><dd>${fmt(s.tension_max_N, 0)}</dd>
    <dt>coil drop (m)</dt><dd>${fmt(s.coil_drop_max_m, 2)}</dd>
    <dt>strongest impact</dt><dd>${si ? `${fmt(si.g, 1)} g (${si.surface})` : '—'}</dd>
    <dt>CPU per step</dt><dd>${fmt(s.us_per_step, 1)} µs</dd></dl>
    <p class="desc">Impact labels compare with an illustrative 10 g threshold — not an injury criterion.</p>`;
  $('result').hidden = false;
}

// ------------------------------------------------------------------ fluxo
let state = 'idle';
function setButtons() {
  $('start').disabled = state === 'loading' || state === 'running';
  $('pause').disabled = state !== 'running';
  $('start').textContent = state === 'paused' ? 'Resume' : state === 'done' ? 'Run again' : 'Start';
}
worker.onmessage = (ev) => {
  const m = ev.data;
  if (m.type === 'ready') {
    $('loading').hidden = true;
    buildStatic(m.info);
    drawFrame(m.frame); showTele(m.frame.tele); showEvents(m.frame.events); showPerf({});
    $('desc').textContent = `${m.info.description} Rope model: ${m.info.model === 'surface' ? 'sliding coils' : 'locked coils'}.`;
    state = m.auto ? 'running' : 'idle'; setButtons();
    if (params.get('bench') && !window.__benchStarted) { window.__benchStarted = true; start(); }
  } else if (m.type === 'frame') {
    drawFrame(m.frame); showTele(m.frame.tele); showEvents(m.frame.events); showPerf(m.perf);
    window.__lastPerf = m.perf;
  } else if (m.type === 'done') {
    showEvents(m.events); showResult(m.summary);
    state = 'done'; setButtons();
    window.__benchResult = { summary: m.summary, perf: window.__lastPerf };
  } else if (m.type === 'error') {
    $('loading').hidden = false; $('loading').textContent = `Error: ${m.message}`;
    window.__benchResult = { error: m.message };
  } else if (m.type === 'log') console.log(m.text);
};
function load(name) {
  state = 'loading'; setButtons(); $('result').hidden = true;
  worker.postMessage({ type: 'load', name });
}
function start() {
  if (state === 'done') { $('result').hidden = true; }
  state = 'running'; setButtons();
  worker.postMessage({ type: 'start', speed: Number($('speed').value) });
}
$('start').onclick = start;
$('pause').onclick = () => { state = 'paused'; setButtons(); worker.postMessage({ type: 'pause' }); };
$('speed').onchange = () => worker.postMessage({ type: 'speed', speed: Number($('speed').value) });
$('scenario').onchange = () => load($('scenario').value);

const list = await (await fetch('./scenarios/index.json')).json();
$('scenario').innerHTML = list.map((s) => `<option value="${s.name}">${s.name.replace('_', ' ')}</option>`).join('');
const first = params.get('bench') || params.get('scenario') || 'default';
$('scenario').value = first;
if (params.get('speed') != null) $('speed').value = params.get('speed');
load(first);
