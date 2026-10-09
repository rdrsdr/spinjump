// Roda um cenário sem interface (Node) e mede o custo por passo; opcionalmente grava a série
// temporal em CSV para comparação com o simulador Python (tools/compare.py).
// Uso: node tools/bench.mjs <cenário> [--csv arquivo] [--max-time s]
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import loadMujoco from '@mujoco/mujoco';
import { Simulation, SAMPLE_FIELDS } from '../public/src/sim.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const name = args[0] || 'default';
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const scen = JSON.parse(readFileSync(join(root, 'public', 'scenarios', `${name}.json`), 'utf8'));
const maxT = opt('--max-time');
if (maxT) scen.max_time_s = Number(maxT);

const mj = await loadMujoco();
const sim = new Simulation(mj, scen);
const lay = sim.layout;
const dPhi = Math.abs(lay.phi_anchor - scen.layout.phi_anchor);
if (dPhi > 1e-9) console.error(`aviso: layout inicial difere do Python (Δφ = ${dPhi})`);
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
