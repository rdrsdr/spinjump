# SpinJump no navegador — protótipo

> Resultados **qualitativos e exploratórios**; **não** são validação de segurança humana.

Objetivo: verificar se o SpinJump pode rodar **100% no navegador do visitante**, servido como
arquivos estáticos (GitHub Pages), sem servidor de simulação. A física do corpo rígido usa o MuJoCo
oficial compilado para WebAssembly (`@mujoco/mujoco` 3.15.0, mesma versão do Python); o modelo da
corda, o vento, o arrasto e os impactos foram portados para JavaScript.

## Estado (2026-10-09)

| parte | situação |
|---|---|
| laço físico (`mj_step1` → forças → `mj_step2`), lançamento, arrasto, vento OU | portado (`public/src/sim.js`, `wind.js`) |
| espiras travadas (`WrapTether`) | portado (`public/src/rope.js`) |
| espiras deslizantes (`SurfaceRope` + kernel implícito com atrito) | portado (`rope.js`, `kernel.js`) |
| impactos (eventos, picos filtrados, classes) | portado (`impacts.js`) |
| cena 3D (three.js), telemetria, lista de impactos, resultado | protótipo (`public/index.html`, `app.js`) |
| configuração (YAML/Pydantic, presets, `auto`) e geração do MJCF | **ainda no Python**: `tools/export_scenarios.py` gera `public/scenarios/*.json` |
| formulário de parâmetros, página inicial de segurança, relatórios/gráficos | não feito |

## Validação contra o Python (mesmo cenário, vento sem rajadas)

`node tools/bench.mjs <cenário> --csv ...` e `tools/compare.py`:

| cenário | maior diferença de posição em voo | métricas |
|---|---|---|
| `cmp_locked` (espiras travadas) | 8·10⁻⁹ m | idênticas (3,052 voltas; 9,187 m/s a 29,68 s; 12,54 m; 1777 N; 34,43 g) |
| `cmp_sliding` (deslizantes) | 1,2 mm | voltas 2,776; chegada 10,096 m/s; queda das espiras 10,30 m; atrito 21,3 kJ — iguais ao Python; deslizamento no solo 10,0 × 10,3 m (caótico, já marcado como não confiável) |
| `cmp_rewind` (bate na torre) | 4,8 cm | ambos `HIT_STRUCTURE`; diferenças só após contatos (caóticos) |

As rajadas usam um gerador próprio (mulberry32 + Box–Muller): com rajadas, as sequências diferem
do NumPy e os resultados coincidem só estatisticamente.

## Desempenho (passo de 0,25 ms = 4000 passos por segundo simulado)

| ambiente | travadas | deslizantes |
|---|---|---|
| Python (MuJoCo nativo + numba), referência | ~53 µs/passo | ~117 µs/passo |
| Node 26 (mesmo código JS + WASM) | **15,8 µs** (0,06 s CPU/s simulado) | **55,6 µs** (0,22 s/s) |
| Chromium headless em container, só física | 32 µs (0,13 s/s) | 128 µs (0,51 s/s) |
| idem, com renderização 3D **por software** (SwiftShader) | 83 µs | 300 µs (tempo real ~0,73×) |

Em aparelhos reais a renderização usa a GPU; o número relevante é o "só física". Estimativa para
celulares intermediários (2–3× mais lentos que o desktop em JS): travadas folgadas; deslizantes perto
do limite do tempo real — precisa de medição em aparelho real. Alternativas se faltar: atualizar a
corda encostada a cada 2 passos (`coil_update_every_steps`), compilar o kernel para WASM, ou usar
espiras travadas em aparelhos lentos. A limitação de CPU por CDP (`Emulation.setCPUThrottlingRate`)
não afeta Web Workers, então não serve para simular celulares.

## Como rodar

```bash
cd browser
npm install            # @mujoco/mujoco 3.15.0 e three 0.170.0
npm run vendor         # copia mujoco.js/.wasm e three para public/vendor (ignorado pelo git)
npm run serve          # http://localhost:8090  (?scenario=locked, ?speed=0 = máximo, ?render=0)
npm run bench -- cmp_sliding --csv ../out/browser/cmp_sliding_js.csv

# no container de desenvolvimento do projeto (raiz do repositório):
./dev.sh python browser/tools/export_scenarios.py
./dev.sh python browser/tools/compare.py cmp_sliding out/browser/cmp_sliding_js.csv
browser/tools/browser_check.sh   # Chromium/Playwright: execução completa, tempo real, celular
```

## Observações da API JavaScript do MuJoCo

- `DoubleBuffer` é `new mj.DoubleBuffer(n)` e `.GetView()` (o README do pacote mostra uma API antiga).
- `data.qpos`, `xfrc_applied`, `site_xpos` etc. são *views* diretas na memória do WASM (escrever nelas
  altera o estado). `data.contact` devolve **cópias** que precisam de `.delete()`.
- Enums: `mj.mjtObj.mjOBJ_BODY.value`.
- O `.wasm` tem ~10 MB (download único, cacheado pelo navegador).
