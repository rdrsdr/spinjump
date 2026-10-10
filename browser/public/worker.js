// Web Worker: carrega o MuJoCo (WebAssembly), monta o cenário a partir da configuração e roda a
// simulação no ritmo pedido, enviando quadros para a página. Tudo no navegador do visitante.
import loadMujoco from './vendor/mujoco/mujoco.js';
import { Simulation, SAMPLE_FIELDS } from './src/sim.js';
import { buildScenario, ConfigError } from './src/scenario.js';

let mj = null;
let rules = null;
let sim = null;
let lastRaw = null;
let built = null;
let running = false;
let speed = 1;
let simT0 = 0;
let wall0 = 0;
let lastFrame = 0;
let rateWin = [];
let timer = null;

const FRAME_MS = 16;     // ~60 quadros/s para a página (que interpola entre eles)
const SLICE_MS = 12;     // trabalho máximo por fatia, para o worker continuar respondendo
const IDLE_MS = 6;       // adiantado em relação ao relógio: dorme em vez de girar em vazio

const post = (m, transfer) => self.postMessage(m, transfer || []);

async function ensureMujoco() {
  if (!mj) {
    const t0 = performance.now();
    mj = await loadMujoco();
    post({ type: 'log', text: `MuJoCo WebAssembly loaded in ${(performance.now() - t0).toFixed(0)} ms` });
  }
}

function staticInfo(scen, notes, warnings) {
  const m = sim.m;
  const geoms = sim.objGids.map((g) => ({
    type: m.geom_type[g], size: Array.from(m.geom_size.subarray(3 * g, 3 * g + 3)),
    rgba: Array.from(m.geom_rgba.subarray(4 * g, 4 * g + 4)),
  }));
  return { geoms, tower: scen.tower, rope: { d: scen.rope.rope_d, rc: sim.rope.rc, length: scen.rope.length,
    source: notes.rope_length_source }, model: sim.rope.modelName, max_time_s: scen.max_time_s,
    turns0: scen.layout.turns0, mass: sim.mass, warnings };
}

function packFrame() {
  const f = sim.frame();
  const g = new Float64Array(f.geoms.length * 12);
  f.geoms.forEach((row, i) => g.set(row, 12 * i));
  const w = new Float32Array(f.wall.length * 3);
  f.wall.forEach((p, i) => { w[3 * i] = p[0]; w[3 * i + 1] = p[1]; w[3 * i + 2] = p[2]; });
  return [{ ...f, geoms: g, wall: w }, [g.buffer, w.buffer]];
}

function finished() {
  // relatório: série temporal completa e contexto, gerado na página (src/report.js)
  const n = SAMPLE_FIELDS.length, flat = new Float64Array(sim.samples.length * n);
  sim.samples.forEach((row, i) => flat.set(row, i * n));
  post({ type: 'done', summary: sim.summary(), events: sim.impacts.events,
         report: { samples: flat, fields: SAMPLE_FIELDS, cfg: built.cfg, notes: built.notes, warnings: built.warnings } },
       [flat.buffer]);
}

function stop() {
  running = false;
  if (timer !== null && timer !== 'kick') clearTimeout(timer);
  timer = null;
}

async function load(raw, auto = false) {
  stop();
  await ensureMujoco();
  try {
    built = buildScenario(raw, rules);
  } catch (e) {
    if (e instanceof ConfigError) { post({ type: 'invalid', errors: e.errors }); return false; }
    throw e;
  }
  if (sim) sim.dispose();
  sim = new Simulation(mj, built.scen);
  lastRaw = raw;
  const [frame, tr] = packFrame();
  post({ type: 'ready', info: staticInfo(built.scen, built.notes, built.warnings), frame, auto }, tr);
  return true;
}

// "continue já" via MessageChannel: setTimeout(0) encadeado espera no mínimo 4 ms
const kick = new MessageChannel();
kick.port1.onmessage = () => { if (timer === 'kick') loop(); };
function schedule(ms) {
  if (ms > 0) timer = setTimeout(loop, ms);
  else { timer = 'kick'; kick.port2.postMessage(0); }
}

function loop() {
  timer = null;
  if (!running || !sim) return;
  const now = performance.now();
  const target = speed === 0 ? Infinity : simT0 + (now - wall0) / 1000 * speed;
  const tBefore = sim.d.time;
  while (sim.status === 'running' && sim.d.time < target - 1e-12 && performance.now() - now < SLICE_MS) {
    sim.advanceTo(Math.min(target, sim.d.time + 0.004));
  }
  const busy = performance.now() - now;
  rateWin.push([now, sim.d.time - tBefore, busy]);
  while (rateWin.length && now - rateWin[0][0] > 2000) rateWin.shift();
  const behind = speed !== 0 && sim.d.time < target - 1e-9;
  if (speed !== 0 && sim.d.time < target - 0.25 * speed) { simT0 = sim.d.time; wall0 = now; }  // re-ancora
  const isDone = sim.status !== 'running';
  if (now - lastFrame >= FRAME_MS || isDone) {
    lastFrame = now;
    const span = rateWin.length > 1 ? (now - rateWin[0][0]) / 1000 : 0;
    const simDone = rateWin.reduce((a, r) => a + r[1], 0);
    const busyMs = rateWin.reduce((a, r) => a + r[2], 0);
    const [frame, tr] = packFrame();
    post({ type: 'frame', frame, perf: {
      rate: span > 0.2 ? simDone / span : null, load: span > 0.2 ? busyMs / 1000 / span : null,
      us_per_step: sim.stepCount ? sim.cpuMs * 1000 / sim.stepCount : null, behind } }, tr);
  }
  if (isDone) {
    running = false;
    finished();
    return;
  }
  // velocidade máxima ou atrasado: continua já; senão espera o relógio (sem girar em vazio)
  schedule(speed === 0 || behind ? 0 : IDLE_MS);
}

function resume() {
  simT0 = sim.d.time; wall0 = performance.now(); rateWin = [];
  running = true;
  if (timer === null) loop();
}

self.onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (m.type === 'init') { rules = m.rules; await ensureMujoco(); post({ type: 'engine' }); }
    else if (m.type === 'load') await load(m.raw);
    else if (m.type === 'start') {
      speed = m.speed;
      if (await load(m.raw || lastRaw, true)) resume();
    } else if (m.type === 'resume') { speed = m.speed; if (sim && sim.status === 'running') resume(); }
    else if (m.type === 'pause') stop();
    else if (m.type === 'stop') {
      stop();
      if (sim && sim.status === 'running') {
        sim.outcome = 'STOPPED';
        sim.finish();   // fecha eventos de impacto em aberto
        finished();
      }
    } else if (m.type === 'speed') { speed = m.speed; if (sim) { simT0 = sim.d.time; wall0 = performance.now(); } }
  } catch (e) {
    post({ type: 'error', message: String((e && e.message) || e) });
  }
};
