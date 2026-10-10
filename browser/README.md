# SpinJump no navegador — protótipo

> Resultados **qualitativos e exploratórios**; **não** são validação de segurança humana.

Objetivo: verificar se o SpinJump pode rodar **100% no navegador do visitante**, servido como
arquivos estáticos (GitHub Pages), sem servidor de simulação. A física do corpo rígido usa o MuJoCo
oficial compilado para WebAssembly (`@mujoco/mujoco` 3.15.0, mesma versão do Python); o modelo da
corda, o vento, o arrasto e os impactos foram portados para JavaScript.

Publicado em **https://rdrsdr.github.io/spinjump/** pela Action `.github/workflows/pages.yml` (a cada
push no `main` que mexa em `browser/`).

## Estado (2026-10-09)

| parte | situação |
|---|---|
| página inicial de aviso (`public/index.html`), exigida antes do simulador (`sim.html`) | portada da versão com servidor |
| configuração: padrão, presets, faixas válidas, `auto`, impulso ↔ velocidade | portada (`src/config.js`); dados gerados de `configs/*.yaml` e do Pydantic por `tools/export_config.py` → `public/config.json` |
| geração do MJCF, geoms do objeto, posição inicial, lançamento | portada (`src/model.js`, `src/scenario.js`); **idêntica ao Python** em 18 cenários (`tools/check_config.mjs`) |
| laço físico (`mj_step1` → forças → `mj_step2`), arrasto, vento OU | portado (`src/sim.js`, `src/wind.js`) |
| espiras travadas e deslizantes (kernel implícito com atrito) | portado (`src/rope.js`, `src/kernel.js`) |
| impactos (eventos, picos filtrados, classes) | portado (`src/impacts.js`) |
| formulário de parâmetros (mesmos campos da versão com servidor), presets, campo avançado `caminho=valor` para qualquer parâmetro, link compartilhável | feito (`app.js`) |
| cena 3D com interpolação entre quadros, telemetria, gráficos, lista de impactos | feito (`app.js`) |
| relatório (desfecho, respostas, energia, impactos, 8–9 gráficos SVG) + `timeseries.csv`, `summary.json`, `events.json`, `config_resolved.json` | gerado no navegador ao fim de cada execução (`src/report.js`) |
| renderização MuJoCo, GIF/vídeo, varreduras, teste de convergência | não portado (ficam na versão Python) |

Parâmetros pela URL: `sim.html?preset=rewind&set=launch.speed_ms=7&set=wind.enabled=false&speed=2&autostart=1`
(`render=0` desliga o desenho, para medir só a física).

## Validação contra o Python (mesmo cenário, vento sem rajadas)

Montagem do cenário (configuração → MJCF, corda, lançamento, vento): `node tools/check_config.mjs` compara
com `reference/*.json` (exportados por `tools/export_scenarios.py`): os 18 cenários (todos os presets e variantes
de geometria, hélice, lançamento por impulso, solo e contato) saem idênticos, MJCF caractere por caractere.

Dinâmica: `node tools/bench.mjs <cenário> --csv ...` e `tools/compare.py`:

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
| Node 26 (mesmo código JS + WASM) | **16–18 µs** (0,07 s CPU/s simulado) | **56 µs** (0,22 s/s) |
| Chromium headless, só física (`render=0`) | 32 µs | 128 µs |
| Chromium headless com 3D **por software** (SwiftShader disputa a CPU) | 60 µs | 200–220 µs |

Em tempo real (1×) o worker só usa a CPU que a física precisa e dorme quando está adiantado (antes
girava em vazio e ocupava 100% de um núcleo). No Chromium do container, com 3D por software:
travadas 1,00× com 22% de um núcleo; deslizantes 0,92–1,0× com ~73%; a página principal fica em ~7%.
Em "max" a física usa ~97% de um núcleo, como esperado. Em aparelhos reais o 3D vai para a GPU.
Falta medir em celular. Se faltar velocidade: atualizar a corda encostada a cada 2 passos
(`rope.coil_update_every_steps=2` no campo avançado), compilar o kernel para WASM, ou usar espiras travadas.
A limitação de CPU por CDP (`Emulation.setCPUThrottlingRate`) não afeta Web Workers.

## Como rodar

```bash
cd browser
npm install            # @mujoco/mujoco 3.15.0 e three 0.170.0
npm run vendor         # copia mujoco.js/.wasm e three para public/vendor (ignorado pelo git)
npm run serve          # http://localhost:8090 (página de aviso → simulador)
npm run check          # montagem do cenário em JS × referência do Python
npm run bench -- cmp_sliding --csv ../out/browser/cmp_sliding_js.csv
npm run bench -- rewind --set launch.speed_ms=7      # qualquer preset + alterações

# no container de desenvolvimento do projeto (raiz do repositório), após mudar configs/ ou config.py:
./dev.sh python browser/tools/export_config.py       # public/config.json
./dev.sh python browser/tools/export_scenarios.py    # reference/*.json
./dev.sh python browser/tools/compare.py cmp_sliding out/browser/cmp_sliding_js.csv
browser/tools/browser_check.sh   # Chromium/Playwright: aviso, formulário, execução + relatório, tempo real, celular
```

## Observações da API JavaScript do MuJoCo

- `DoubleBuffer` é `new mj.DoubleBuffer(n)` e `.GetView()` (o README do pacote mostra uma API antiga).
- `data.qpos`, `xfrc_applied`, `site_xpos` etc. são *views* diretas na memória do WASM (escrever nelas
  altera o estado). `data.contact` devolve **cópias** que precisam de `.delete()`.
- Enums: `mj.mjtObj.mjOBJ_BODY.value`.
- O `.wasm` tem ~10 MB (download único, cacheado pelo navegador).
