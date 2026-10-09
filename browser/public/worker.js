// Web Worker: carrega o MuJoCo (WebAssembly) e roda a simulação em tempo real, enviando quadros
// para a página. Tudo no navegador do visitante; nenhum servidor além dos arquivos estáticos.
import loadMujoco from './vendor/mujoco/mujoco.js';
import { Simulation } from './src/sim.js';

let mj = null;
let sim = null;
let scen = null;
let running = false;
let speed = 1;
let simT0 = 0;
let wall0 = 0;
let lastFrame = 0;
let rateWin = [];

const post = (m) => self.postMessage(m);

async function ensureMujoco() {
  if (!mj) {
    const t0 = performance.now();
    mj = await loadMujoco();
    post({ type: 'log', text: `MuJoCo WebAssembly loaded in ${(performance.now() - t0).toFixed(0)} ms` });
  }
}

function staticInfo() {
  const m = sim.m;
  const geoms = sim.objGids.map((g) => ({
    type: m.geom_type[g], size: Array.from(m.geom_size.subarray(3 * g, 3 * g + 3)),
    rgba: Array.from(m.geom_rgba.subarray(4 * g, 4 * g + 4)),
  }));
  return { geoms, tower: scen.tower, rope: { d: scen.rope.rope_d, rc: sim.rope.rc }, model: sim.rope.modelName,
           description: scen.description, max_time_s: scen.max_time_s };
}

async function load(name, auto = false) {
  running = false;
  await ensureMujoco();
  const r = await fetch(`./scenarios/${name}.json`);
  scen = await r.json();
  if (sim) sim.dispose();
  sim = new Simulation(mj, scen);
  post({ type: 'ready', info: staticInfo(), frame: sim.frame(), auto });
}

function loop() {
  if (!running || !sim) return;
  const now = performance.now();
  const budgetMs = 14;
  let target = speed === 0 ? Infinity : simT0 + (now - wall0) / 1000 * speed;
  // passos limitados por fatia de tempo para manter o worker responsivo
  const t0 = performance.now();
  const tBefore = sim.d.time;
  while (sim.status === 'running' && sim.d.time < target - 1e-12 && performance.now() - t0 < budgetMs) {
    sim.advanceTo(Math.min(target, sim.d.time + 0.02));
  }
  const work = performance.now() - t0;
  rateWin.push([now, sim.d.time - tBefore]);
  while (rateWin.length && now - rateWin[0][0] > 2000) rateWin.shift();
  if (speed !== 0 && sim.d.time < target - 0.25) {
    // atrasado: re-ancora o relógio para não acumular atraso (mostra a taxa efetiva)
    simT0 = sim.d.time; wall0 = now;
  }
  if (now - lastFrame > 33 || sim.status !== 'running') {
    lastFrame = now;
    const span = rateWin.length > 1 ? (now - rateWin[0][0]) / 1000 : 0;
    const simDone = rateWin.reduce((a, r) => a + r[1], 0);
    post({ type: 'frame', frame: sim.frame(), perf: {
      rate: span > 0.2 ? simDone / span : null,
      us_per_step: sim.stepCount ? sim.cpuMs * 1000 / sim.stepCount : null, busy_ms: work } });
  }
  if (sim.status !== 'running') {
    running = false;
    post({ type: 'done', summary: sim.summary(), events: sim.impacts.events });
    return;
  }
  setTimeout(loop, 0);
}

self.onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (m.type === 'load') await load(m.name);
    else if (m.type === 'start') {
      if (!sim || sim.status !== 'running') await load(scen.name, true);
      speed = m.speed;
      simT0 = sim.d.time; wall0 = performance.now(); rateWin = [];
      running = true;
      loop();
    } else if (m.type === 'pause') running = false;
    else if (m.type === 'speed') { speed = m.speed; simT0 = sim ? sim.d.time : 0; wall0 = performance.now(); }
  } catch (e) {
    post({ type: 'error', message: String(e && e.message || e) });
  }
};
