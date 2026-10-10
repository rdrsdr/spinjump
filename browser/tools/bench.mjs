// Roda uma simulação sem interface (Node) e mede o custo por passo; opcionalmente grava a série
// temporal em CSV para comparação com o simulador Python (tools/compare.py).
// Uso: node tools/bench.mjs <nome> [--set caminho=valor ...] [--csv arquivo] [--max-time s]
//   <nome> = cenário de referência em reference/ (ex.: cmp_sliding, exportado pelo Python, com a
//   rajada inicial igual à do Python) ou preset/"default" montado em JavaScript a partir de config.json.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import loadMujoco from '@mujoco/mujoco';
import { Simulation, SAMPLE_FIELDS } from '../public/src/sim.js';
import { loadRaw } from '../public/src/config.js';
import { buildScenario } from '../public/src/scenario.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const name = args[0] || 'default';
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const sets = args.flatMap((a, i) => (a === '--set' ? [args[i + 1]] : []));

let scen;
const refFile = join(root, 'reference', `${name}.json`);
if (existsSync(refFile) && !sets.length) {
  scen = JSON.parse(readFileSync(refFile, 'utf8'));
} else {
  const base = JSON.parse(readFileSync(join(root, 'public', 'config.json'), 'utf8'));
  const preset = name === 'default' ? null : name;
  ({ scen } = buildScenario(loadRaw(base, { preset, sets }), base.rules));
}
const maxT = opt('--max-time');
if (maxT) scen.max_time_s = Number(maxT);

const mj = await loadMujoco();
const sim = new Simulation(mj, scen);
const lay = sim.layout;
if (scen.layout) {
  const dPhi = Math.abs(lay.phi_anchor - scen.layout.phi_anchor);
  if (dPhi > 1e-9) console.error(`aviso: layout inicial difere do Python (Δφ = ${dPhi})`);
}
sim.advanceTo(scen.max_time_s + 1);
const s = sim.summary();
console.log(JSON.stringify({ scenario: name, ...s }, (k, v) => (typeof v === 'number' ? Number(v.toPrecision(6)) : v)));
const csv = opt('--csv');
if (csv) {
  const lines = [SAMPLE_FIELDS.join(',')];
  for (const r of sim.samples) lines.push(r.map((v) => (Number.isInteger(v) ? v : v.toPrecision(10))).join(','));
  writeFileSync(csv, lines.join('\n') + '\n');
}
sim.dispose();
