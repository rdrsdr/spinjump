// Copia os arquivos de execução das dependências para public/vendor (servidos como estáticos).
import { cpSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const nm = join(root, 'node_modules');
const out = join(root, 'public', 'vendor');
mkdirSync(join(out, 'mujoco'), { recursive: true });
mkdirSync(join(out, 'three'), { recursive: true });
for (const f of ['mujoco.js', 'mujoco.wasm']) cpSync(join(nm, '@mujoco/mujoco', f), join(out, 'mujoco', f));
cpSync(join(nm, 'three/build/three.module.min.js'), join(out, 'three', 'three.module.min.js'));
cpSync(join(nm, 'three/examples/jsm/controls/OrbitControls.js'), join(out, 'three', 'OrbitControls.js'));
console.log('vendor ->', out);
