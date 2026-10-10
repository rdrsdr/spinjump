// Confere a montagem do cenário em JavaScript (config.js + model.js + scenario.js) contra os
// cenários de referência exportados pelo Python: MJCF idêntico e números iguais.
// Uso: ./dev.sh python browser/tools/export_scenarios.py   (gera browser/reference)
//      node browser/tools/check_config.mjs [pasta]
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadRaw } from '../public/src/config.js';
import { buildScenario } from '../public/src/scenario.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const base = JSON.parse(readFileSync(join(root, 'public', 'config.json'), 'utf8'));
const dir = process.argv[2] || join(root, 'reference');
const SKIP = new Set(['name', 'description', 'preset', 'overrides', 'mass', 'g0', 'turns0', 'load_warn_fraction']);

function diff(a, b, path, out) {
  if (typeof a === 'number' && typeof b === 'number') {
    if (Math.abs(a - b) > 1e-12 + 1e-12 * Math.abs(b)) out.push(`${path}: js=${a} py=${b}`);
  } else if (Array.isArray(b)) {
    if (!Array.isArray(a) || a.length !== b.length) { out.push(`${path}: length/type differs`); return; }
    b.forEach((v, i) => diff(a[i], v, `${path}[${i}]`, out));
  } else if (b && typeof b === 'object') {
    for (const k of Object.keys(b)) if (!SKIP.has(k)) diff(a?.[k], b[k], path ? `${path}.${k}` : k, out);
  } else if (a !== b) {
    if (typeof b === 'string' && typeof a === 'string') {
      let i = 0; while (a[i] === b[i]) i++;
      out.push(`${path}: differs at char ${i}: js «${a.slice(i - 20, i + 40)}» py «${b.slice(i - 20, i + 40)}»`);
    } else out.push(`${path}: js=${JSON.stringify(a)} py=${JSON.stringify(b)}`);
  }
}

let fails = 0;
for (const f of readdirSync(dir).filter((x) => x.endsWith('.json')).sort()) {
  const ref = JSON.parse(readFileSync(join(dir, f), 'utf8'));
  const raw = loadRaw(base, { preset: ref.preset, sets: ref.overrides || [] });
  const { scen } = buildScenario(raw, base.rules);
  const out = [];
  diff(scen, ref, '', out);
  console.log(`${out.length ? 'FAIL' : 'ok  '} ${f.replace('.json', '')}${out.length ? `\n  ${out.slice(0, 6).join('\n  ')}` : ''}`);
  if (out.length) fails++;
}
// validação: valores fora da faixa devem ser recusados
const bad = [['tower.height_m=0.5'], ['rope.length_m=0.5'], ['launch.speed_ms=null'], ['rope.anchor_below_top_m=60'],
  ['wind.preset="hurricane"'], ['rope.winding_handedness="left"'], ['rope.axial_EA_N=5']];
for (const sets of bad) {
  let refused = false;
  try { buildScenario(loadRaw(base, { sets }), base.rules); } catch (e) { refused = true; }
  console.log(`${refused ? 'ok  ' : 'FAIL'} refuses ${sets[0]}`);
  if (!refused) fails++;
}
process.exit(fails ? 1 : 0);
