# SpinJump — simulador físico 3D de corda e chaminé (MuJoCo)

> **Aviso:** os resultados são **qualitativos e exploratórios**, produzidos por um modelo
> simplificado. **Não são validação de segurança humana.** Os limiares de dano (g ou N) são
> ilustrativos, não clínicos. O aviso aparece na interface, nos relatórios e na CLI.

Uma chaminé rígida (H = 50 m, D = 5 m por padrão) tem uma corda enrolada em hélice de passo curto
perto do topo. Na outra ponta há um objeto de massa humana (manequim ou saco de areia) que parte
junto à borda com velocidade ou impulso configurável. O objeto cai, a corda desenrola enquanto ele
gira em torno da chaminé, e depois ele toca o solo e desliza sob atrito e restrição da corda. O giro
surge apenas de forças e restrições; não há trajetória animada.

Física (MuJoCo) e renderização 3D rodam **no servidor**, dentro do Docker. O navegador só envia
parâmetros e comandos e mostra os quadros JPEG e a telemetria recebidos. Não há MP4, GIF nem replay.

Decisões, protótipos, falhas e calibração estão em [NOTES.md](NOTES.md).

**Idiomas:** a interface web (página inicial, simulador e os relatórios gerados a partir dela) é em
**inglês**. A CLI, os relatórios gerados pela CLI e esta documentação são em português
(`serve --lang pt|en` ou `SPINJUMP_WEB_LANG` muda o idioma da interface).

---

## 1. Início rápido

```bash
docker compose up --build            # http://localhost:8000 → página inicial; simulador em /app
SPINJUMP_PORT=9000 docker compose up --build   # outra porta no host
```

Sem GPU: a renderização usa OSMesa (CPU) por padrão. Os resultados ficam em `./out/` (volume
`./out:/app/out`, persistente). O contêiner roda como usuário não-root (UID 1000; ajuste com
`UID=$(id -u) GID=$(id -g) docker compose up`), e `./out` precisa ser gravável por esse usuário.

No navegador: a página inicial (`/`) explica o que é simulado, que é só uma simulação, que não é
recomendação nem instrução, os riscos reais e "não tente fazer isso". O simulador (`/app`) só abre
depois de marcar a confirmação. Lá: preencha o formulário (ou escolha um preset) → **Start** →
acompanhe a cena ao vivo → **Pause/Resume/Stop**. Ao terminar (repouso, tempo máximo ou
encerramento), aparecem o resumo e os links para o relatório e os arquivos.

### CLI (mesma imagem; o ENTRYPOINT é `python -m spinjump`)

```bash
docker compose run --rm cli run                                  # cenário padrão
docker compose run --rm cli run --convergence                    # + resolução ×2 e dt ÷2
docker compose run --rm cli run --preset rewind --name teste
docker compose run --rm cli run --set launch.mode=impulse --set launch.impulse_Ns=480 \
                                --set launch.speed_ms=null --set launch.duration_ms=200
docker compose run --rm cli sweep --param launch.azimuth_deg=-60,0,90 --param launch.speed_ms=2,6 --seeds 1,2
docker compose run --rm cli report out/<pasta> [--rerun]          # regera md/html; --rerun confere determinismo
docker compose run --rm cli rope-length [--height 50 --v0 0]
docker compose run --rm cli selftest
docker compose run --rm --entrypoint python cli -m pytest -q      # testes físicos e de interface
```

`make build|up|down|selftest|test|test-fast|run|sweep|ui-flow|ui-layout` são atalhos para os mesmos
comandos. Sem Compose: `docker run --rm -v "$PWD/out:/app/out" spinjump:1.0.0 run`.

A CLI não imprime progresso nem impactos: só um retorno curto (desfecho, voltas, chegada,
deslizamento, tração, maior impacto, pasta dos artefatos).

### Estrutura do repositório

```
spinjump/        pacote (config, model, rope, wind, sim, impacts, metrics, report, plots,
                    sweep, convergence, render, selftest, cli, web/)
configs/            default.yaml e presets/
tests/              ensaios de validação 1–10 (pytest)
tools/              ui_flow.py (fluxo via WebSocket), ui_layout.py/.sh (Chromium/Playwright)
prototypes/         protótipo do plugin cable (reprovado) e scripts de calibração citados no NOTES
Dockerfile, compose.yaml, compose.gpu.yaml, Makefile, requirements.txt, NOTES.md
```

---

## 2. Arquitetura

| componente | arquivo | papel |
|---|---|---|
| configuração | `spinjump/config.py`, `configs/` | YAML + Pydantic (campos estritos, faixas), presets, `--set caminho=valor`, resolução de `auto`/presets/impulso |
| modelo MJCF | `spinjump/model.py` | torre, solo, objeto (corpo rígido único) e **matriz de colisões explícita** (`<pair>`) |
| corda | `spinjump/rope.py` | modelo `wrap_tether`: hélice armazenada + trecho geodésico + vão livre, tração unilateral, folga, cargas distribuídas, geometria desenhada |
| vento | `spinjump/wind.py` | média + perfil vertical + rajadas Ornstein–Uhlenbeck com seed |
| motor | `spinjump/sim.py` | passo fixo `mj_step1 → forças → mj_step2`, telemetria, desfecho |
| impactos | `spinjump/impacts.py` | eventos agrupados, `mj_contactForce`, impulso, g, classificação |
| relatórios | `metrics.py`, `report.py`, `plots.py`, `sweep.py`, `convergence.py` | artefatos, gráficos, varredura, convergência |
| render | `spinjump/render.py` | OSMesa/EGL offscreen em **processo separado**, sem texto sobre a imagem |
| servidor | `spinjump/web/server.py` | FastAPI + WebSocket; sessões por visitante, capacidade, reconexão, limpeza |
| sessão | `spinjump/web/session_proc.py` | **um processo por visitante**: física com ritmo controlado + renderizador próprio |
| interface | `spinjump/web/static/` | página inicial (`intro.html`) e simulador (`index.html`, `app.js`), em inglês |
| idiomas | `spinjump/i18n.py` | textos em pt/en (CLI em pt, web em en) |

O passo físico (dt fixo) não depende da taxa de quadros nem do fator de reprodução: o servidor só
decide quantos passos executar por segundo de relógio. A telemetria é amostrada a `solver.output_hz`
e a renderização a `ui.render_hz`, a partir de instantâneos do estado.

---

## 3. Coordenadas e convenções

- z para cima, solo em z = 0; eixo da chaminé em x = y = 0; gravidade 9,81 m/s².
- `rope.winding_handedness`: sentido da hélice a partir da âncora, visto de cima (ccw = anti-horário).
  A âncora fica `rope.anchor_below_top_m` abaixo do topo e a hélice sobe a partir dela com passo
  `winding_pitch_factor × rope.diameter_m`, raio `D/2 + d/2`. O número de voltas sai do comprimento:
  `voltas = (L − vão_inicial) / κ`, com κ = sqrt(rc² + (p/2π)²) por radiano.
- O objeto começa na altura do ponto de saída, com a superfície a `object.start_clearance_m` da parede
  e a corda horizontal, tangente à torre e justa (tração zero).
- **Azimute do lançamento** (no plano horizontal, no ponto inicial):

```
                 vista de cima (hélice ccw)
                                      +90° (sentido de desenrolar = normal externa em D)
                                        ↑
              .-""""-.                  |
            /  torre   \     D          |
           |     ·      |----●=========[objeto]──→  0° (ao longo do vão livre,
            \          /     vão livre      |          para longe da chaminé)
              '-....-'                      ↓
                                      −90° (sentido de enrolar)
```

  0° aponta ao longo do vão livre, para longe da chaminé. Valores positivos giram para o sentido que
  **desenrola** (a velocidade ganha componente ao longo da normal externa no ponto de saída D) e
  valores negativos para o sentido que **enrola**. A convenção vale para os dois sentidos de hélice,
  e o teste 7 a verifica. `launch.elevation_deg` inclina para cima.
- Lançamento: `mode: velocity` usa `speed_ms`; `mode: impulse` usa `impulse_Ns` (N·s), com
  **J = m·Δv**. Com `duration_ms = 0` o Δv é instantâneo; com `duration_ms > 0` aplica-se uma força
  constante J/Δt durante o intervalo, e o momento resultante é J (teste 7).

---

## 4. Parâmetros (SI) — `configs/default.yaml`

Todos os valores padrão estão no YAML. O código só define tipos, faixas e regras. Campos
desconhecidos são rejeitados. Overrides: `--set caminho=valor` (repetível, valores em sintaxe YAML:
`null`, `true`, `[0.02, 1.5]`).

| seção | parâmetros principais |
|---|---|
| `tower` | `height_m`, `diameter_m`, `wall_friction` (objeto–parede) |
| `rope` | `model` (`wrap_tether`), `coil_sliding`, `helix_vertical` (`down`/`up`), `winding_pretension_N`, `coil_window_turns`, `coil_update_every_steps`, `coil_mass_scale`, `length_m` (`auto` ou m), `diameter_m`, `linear_density_kg_m`, `element_length_m` (resolução da quadratura de peso/arrasto do vão), `axial_EA_N` (N), `axial_damping_ratio` (ζ), `wall_friction` (cabrestante), `wind_drag_Cd_normal/tangent`, `winding_pitch_factor`, `winding_handedness`, `anchor_below_top_m`, `breaking_load_N`, `load_warn_fraction`; inaplicáveis ao modelo: `bend_E_pa`, `twist_G_pa`, `self_collision`, `ground_friction` (explicados no relatório) |
| `object` | `type` (`mannequin`/`sandbag`), `mass_kg`, `height_m`, `radius_m`, `attach_height_fraction` (ponto de fixação no eixo do corpo), `start_clearance_m`, `drag_CdA_m2`, `geom_friction` |
| `launch` | `mode`, `speed_ms` (m/s), `impulse_Ns` (N·s), `azimuth_deg`, `elevation_deg`, `duration_ms` |
| `air` / `wind` | `enabled`, `density_kg_m3`; `preset`, `speed_mean_ms`, `direction_deg` (para onde sopra, a partir de +x), `gust_std_ms`, `correlation_time_s`, `shear_exponent` (U(z) = U·(z/z_ref)^α), `reference_height_m`, `seed`, `presets` |
| `ground` / `contact` | `preset`, `friction_slide`, `friction_torsional` (m), `friction_rolling` (m), `presets`, `size_m`; `solref`, `solimp`, `cone`, `impratio` |
| `impact` | `damage_threshold_g` ou `damage_threshold_N`, `filter_window_ms`, `warn_fraction`, `merge_gap_ms` (20 ms), `structure_hit_speed_ms` |
| `solver` | `timestep_s`, `integrator`, `iterations`, `max_time_s`, `rest_speed_ms`, `rest_hold_s`, `rewind_threshold_turns`, `stop_on_structure_hit`, `output_hz` |
| `ui` | `render_hz`, `playback_factor` (0,1×–4×), `width`, `height`, `jpeg_quality`, `helix_visual_pitch_scale` (somente visual), `rope_visual_radius_m` (somente visual), `camera` |

Valores alterados em relação aos iniciais da especificação, com evidência em NOTES §4–5 e §11
(o sentido da hélice e as espiras deslizantes foram pedidos depois da entrega inicial):
`contact.solref` [0,004, 1,0] → **[0,02, 1,5]**, `solver.timestep_s` 0,5 ms → **0,25 ms**,
`ground.friction_rolling` 1e-4 → **0,02 m**, `ground.friction_torsional` 0,005 → **0,02 m** e
`launch.azimuth_deg` 20° → **90°**.

Presets (`configs/presets/`): `straight_drop`, `tangential_impulse`, `rewind`, `strong_wind`,
`no_air`, `sandbag`, `ice`, `short_rope`. Presets de vento e solo (`wind.preset`, `ground.preset`)
substituem a velocidade média e o atrito deslizante.

### Comprimento `auto`

Estimativa original, mostrada na configuração resolvida e no relatório:

```
v = sqrt(2 g H + v0²),   r_min = v · sqrt(H / g),   L = sqrt(r_min² + H²)
```

Para H = 50 m e v0 = 0: v = 31,3 m/s, r_min = 70,7 m, **L ≈ 86,6 m** (com v0 = 4 m/s, 87,3 m).
Hipóteses: queda livre de H com velocidade v0 e alcance horizontal r_min = v·sqrt(H/g), uma escala
simplificada. Ela **não garante** órbita, corda tensa, ausência de colisão ou de levantamento no
solo. O padrão demonstrativo foi escolhido por simulação (NOTES §5). Comprimentos manuais que não
alcançam o solo, considerando a âncora e o objeto deitado junto à base, geram aviso (preset
`short_rope`).

---

## 5. Modelo da corda (`wrap_tether`)

O plugin `mujoco.elasticity.cable` foi testado primeiro e **reprovado**: divergiu em < 0,7 s,
atravessou a parede, as espiras escorregaram e custou 20–3000 s de CPU por segundo simulado (NOTES
§2). A formulação adotada é explícita e validável. A parte encostada na torre tem duas variantes,
escolhidas por `rope.coil_sliding` (checkbox na interface):

### 5.1 Espiras deslizantes (`coil_sliding: true`, padrão)

- A corda encostada (da âncora ao ponto de saída D) é uma **cadeia de nós presos à superfície** do
  cilindro (coordenadas planificadas: ao redor × altura), espaçados de `element_length_m`. Não há
  colisão 3D, então ela não atravessa a parede por construção.
- Passo **implícito** (Euler implícito linearizado; sistema bloco-tridiagonal 2×2 resolvido
  diretamente) com rigidez axial unilateral, amortecimento e a rigidez do vão na ponta. O kernel é
  compilado com `numba`.
- **Atrito de Coulomb local** com a parede (`rope.wall_friction`), resolvido por conjunto ativo
  (nós aderidos ou escorregando). A força normal vem da tração e da curvatura sobre o cilindro,
  `N = T̄·Δs·cos²β/rc`. Disso saem o cabrestante (exp(μθ), verificado dinamicamente) e o
  **escorregamento das espiras** quando o puxão é inclinado.
- **Pré-tensão de enrolamento** (`winding_pretension_N`, padrão 20 N): sem ela não há força normal e
  as espiras caem pelo próprio peso.
- **Contato entre voltas**: uma volta não atravessa a vizinha na vertical.
- `helix_vertical: down` (padrão): a hélice desce a partir da âncora e **desenrola de baixo para
  cima**. Com `up`, a espira puxada é a de cima e se apoia nas de baixo.
- A massa da corda encostada é irrelevante diante das trações. A inércia dos nós é **escalonada**
  (`coil_mass_scale`, padrão 50; o peso usa a massa real), técnica quase-estática que evita o chicote
  numérico de nós de 15 g. O resultado não depende da escala entre 20 e 150 (NOTES §11).
- Só os nós dentro de uma janela a partir do ponto de saída se movem (`coil_window_turns`, mínimo
  1,5 volta, ampliada automaticamente para ln(100)/(2πμ) voltas com atrito baixo). Os demais ficam
  parados porque a tração decai exponencialmente ao longo do enrolamento.
- O ponto de saída D continua dado pela tangência a partir do objeto. A força do vão é aplicada em
  D pela regra da alavanca, e o balanço de energia fecha (resíduo em voo de 0,4% no padrão).

Efeito no cenário padrão: com a corda saindo inclinada, as espiras escorregam pela torre (até
~11,6 m) e o **atrito delas na parede vira o freio da descida**, com 21,6 kJ dissipados. No modelo
travado, esse papel era da perda na dobra.

### 5.2 Espiras travadas (`coil_sliding: false`)

Modelo original, mais leve (~0,2 s de CPU por s simulado):

- **Hélice armazenada** (âncora → P1), travada por atrito: só diminui, descascando na saída. As voltas
  desenhadas somem junto.
- **Trecho geodésico** (P1 → D): corda apoiada na torre ao reenrolar, como em um tetherball.
  Conservativo.
- **Vão livre** reto D → A, tangente ao cilindro (não atravessa a parede).
- Tração **unilateral** T = max(0, kδ + cδ̇) com k = EA/L_rep, c = 2ζ·sqrt(k·m). Com folga, T = 0 e a
  corda não empurra. Esticada, limita o alcance, inclusive no solo (teste 8).
- Comprimento: `L = armazenado + repouso(P1→A)`, e `caminho − repouso = alongamento − folga`
  (fecha com erro zero em todas as amostras, teste 8).
- Peso e arrasto distribuídos (normal/tangencial) por quadratura com `element_length_m`.
- Tração na âncora por cabrestante: T·exp(−μ·θ_armazenado).
- **Perda na dobra de saída** ao descascar com o vão inclinado: dissipa ~60% da energia no padrão e
  freia a descida. É a hipótese mais influente (NOTES §3.1).

A geometria desenhada (corda encostada, geodésica, vão e folga) vem do **mesmo estado** que calcula
as forças. Com espiras travadas, o passo da hélice é ampliado na cena (padrão ×12, só para
leitura); com espiras deslizantes, a cena mostra a geometria real. Nos dois casos a corda é
engrossada para leitura, com rótulo na legenda fora da imagem. A forma da corda com folga é ilustrativa (parábola
com o comprimento disponível).

### Matriz de colisões

| | solo | torre | objeto | corda |
|---|---|---|---|---|
| objeto | sim (condim 6: atrito deslizante, torcional, rolamento) | sim (condim 3) | não (corpo rígido único) | não |
| corda | não (o vão parte do alto) | geométrico: nunca penetra (raio rc e tangência) | não | não (passo ≥ diâmetro) |

---

## 6. Vento e arrasto

Vento horizontal = média·perfil(z) + rajada OU 2D, discretizada exatamente:
g ← g·e^(−Δt/τ) + σ·sqrt(1 − e^(−2Δt/τ))·ξ, com seed. A rajada é espacialmente uniforme. Objeto:
**F = −½ ρ CdA |v_rel| v_rel** no centro de massa. Corda: arrasto normal (Cd_n·d) e tangencial
(π·d·Cd_t) por segmento, com velocidade do material crescendo linearmente de D (parado) até A. `air`
e `wind` desligam separadamente (sem ar, não há arrasto nem vento).

## 7. Impactos e desfechos

Um **evento** é um intervalo contínuo de contato do objeto com o solo ou a torre. Contatos
simultâneos de várias geoms do mesmo objeto e interrupções < `merge_gap_ms` (20 ms) são agrupados.
Por evento: tempo, local, geoms, força normal bruta e filtrada (média móvel de `filter_window_ms`),
impulso normal (fase de impacto e evento inteiro), desaceleração (g), velocidades normal/tangencial e
duração. As forças vêm de `mj_contactForce`. Classificação por pico filtrado:

| classe | critério | cor |
|---|---|---|
| OK | < `warn_fraction` × limiar | verde ✓ |
| ATENÇÃO | ≥ `warn_fraction` × limiar | âmbar ! |
| DANO | ≥ limiar | vermelho ✕ |

Os picos **dependem de `contact.solref`, `contact.solimp` e do passo de tempo**. O limiar em g não é
critério de lesão validado.

Desfechos: `AT_REST_CLEAN` (repouso sustentado no solo, sem colisão estrutural nem reenrolamento),
`HIT_STRUCTURE` (contato com a torre acima de `structure_hit_speed_ms`), `REWOUND` (reenrolamento ≥
`rewind_threshold_turns`), `TIMEOUT` (tempo máximo ou encerramento manual) e `NUMERICAL_FAILURE`.
Repouso exige velocidade (linear e periférica) < `rest_speed_ms` por `rest_hold_s` em contato com o
solo.

## 8. Artefatos (`out/<data>_<nome>/`)

`config_resolved.yaml` (com estimativa de L, notas e parâmetros inaplicáveis), `timeseries.csv`,
`events.json`, `summary.json`, `summary.md`, `summary.html` e os gráficos `trajectory_3d.png`,
`trajectory_top.png`, `height.png`, `speed.png`, `wall_distance.png`, `tension.png`,
`wound_length.png`, `energy.png` e `impacts.png`. `sweep` gera `sweep.csv`, `heatmap_*.png` e
`sweep.md`. Vídeo e replay não são gravados.

## 9. Interface

- **Página inicial** (`/`): o que é simulado (com diagrama), o que é e o que não é, perigos reais,
  por que os números não são de segurança, "nunca tente", como funciona o servidor compartilhado, e
  uma caixa de confirmação obrigatória ("I understand…"). Sem confirmação, `/app` redireciona para
  `/`. A confirmação vale para a aba (sessionStorage), com `?ack=1` como alternativa quando o
  navegador bloqueia armazenamento.
- **Multitenant:** cada aba recebe um identificador aleatório (`sid`) e sua própria simulação, em
  processo próprio (física + renderizador). Pausar, encerrar, mudar câmera ou ritmo afeta só a
  própria sessão. Recarregar a página reconecta à mesma simulação. No máximo
  `SPINJUMP_MAX_SESSIONS` simulações rodam ao mesmo tempo (padrão: metade das CPUs disponíveis); a
  seguinte recebe "server busy". Sessões sem visitante por `SPINJUMP_DETACH_GRACE_S` (60 s) são
  encerradas, com artefatos gravados; sessões terminadas liberam o renderizador após
  `SPINJUMP_FINISHED_TTL_S` (600 s). `SPINJUMP_MAX_SIM_TIME_S` limita o tempo simulado por execução
  (0 = sem teto). O cabeçalho mostra quantas simulações estão rodando.
- Formulário com unidades e faixas, presets, modo velocidade/impulso (mostra o Δv ou J equivalente),
  Start/Pause/Resume/Stop.
- Cena renderizada no servidor e transmitida por WebSocket. Câmeras **Livre** (arrastar = orbitar,
  roda = zoom), **Lateral** e **Acompanhar**, todas controladas pelo servidor.
- Fator de reprodução de 0,1× a 4×. Em 1× o alvo é 1 s simulado por 1 s de relógio. A tela mostra
  tempo simulado, tempo real (sem pausas) e **taxa efetiva medida**. Se o servidor não sustentar o
  pedido, aparece a taxa real: o ritmo não acelera para recuperar atraso nem pula passos.
- Telemetria: velocidade, altura, distância à parede, voltas do objeto e da hélice, corda
  enrolada/livre, alongamento/folga, tração (objeto/âncora/máxima), forças de contato, fase, eventos
  com classe colorida, e minigráficos de altura e tração.
- Rótulos, aviso e medições ficam **fora** da imagem. Isso foi verificado com Chromium a 1366×768,
  1920×1080, 1024×768 e 390×844 (`tools/ui_layout.py`): nenhum elemento sobre a cena, sem rolagem
  horizontal.

### Publicar no Hugging Face Spaces (gratuito)

`deploy/huggingface/make_space.sh <pasta>` (ou `make hf-space SPACE_DIR=<pasta>`) monta o
repositório de um Space com SDK Docker. Ele copia código, configs, testes e documentação e usa o
cartão `deploy/huggingface/README.md` (em inglês; cabeçalho `title: SpinJump`, `sdk: docker`,
`app_port: 7860`). O Dockerfile gerado é o do projeto com `PORT=7860`, `LP_NUM_THREADS=1` (2 vCPUs),
`SPINJUMP_MAX_SESSIONS=2`, `SPINJUMP_MAX_SIM_TIME_S=180` e `SPINJUMP_KEEP_RUNS=30` (só as 30
execuções mais recentes ficam em disco), sem `VOLUME`.

1. Em huggingface.co: *New Space* → SDK **Docker** (template em branco), hardware **CPU basic** (grátis).
2. Crie um token de acesso com permissão de escrita (*Settings → Access Tokens*).
3. `git clone https://huggingface.co/spaces/<usuario>/spinjump ../spinjump-space`
4. `deploy/huggingface/make_space.sh ../spinjump-space`
5. `cd ../spinjump-space && git add -A && git commit -m "SpinJump" && git push`
   (usuário = seu login no HF, senha = o token). A construção leva alguns minutos e o app fica em
   `https://<usuario>-<space>.hf.space`.

Para atualizar, repita os passos 4 e 5. Testado localmente no perfil do plano gratuito (porta 7860,
UID 1000, sem volume, `--cpus 2`): interface a 14,8 quadros/s, 1× = 1,00 e 2× = 2,00 com um visitante;
com dois visitantes simultâneos, ~0,95× cada (com três cairia para ~0,5×, por isso o limite de 2).

## 10. Operação headless, CPU e GPU

- Padrão: `MUJOCO_GL=osmesa` (CPU, sem display, sem GPU). `LP_NUM_THREADS=2` limita as threads do
  llvmpipe para reduzir a interferência com a física. O cliente não precisa de GPU.
- Opcional (GPU NVIDIA no servidor, com NVIDIA Container Toolkit):
  `docker compose -f compose.yaml -f compose.gpu.yaml up --build` (usa `MUJOCO_GL=egl`).
  **Não testado neste ambiente (sem GPU).**
- Desempenho medido (CPU, 14 vCPUs/WSL2): física ~0,5 s de CPU por s simulado com espiras
  deslizantes e ~0,2 s com espiras travadas (kernels `numba`); quadro 960×600 em ~23–40 ms. Uma sessão sustenta 1× e 2×; com 4× pedido, ~2,9× efetivos. Com sessões em processos
  separados, 2 simultâneas rodam a 1,0× cada e 3 a ~0,94× (antes, na mesma thread de processo, 2
  sessões caíam para 0,6× por disputa do GIL).
- Logs: uvicorn sem access log (nível `error`), Compose com `logging: driver: none`. Não há log de
  progresso. Erros aparecem na interface e nos artefatos. Para depurar, rode o serviço com
  `docker compose run --rm --service-ports cli serve`.
- Variáveis de ambiente do servidor: `PORT`, `SPINJUMP_WEB_LANG` (en/pt), `SPINJUMP_MAX_SESSIONS`,
  `SPINJUMP_MAX_SIM_TIME_S`, `SPINJUMP_DETACH_GRACE_S`, `SPINJUMP_FINISHED_TTL_S`,
  `SPINJUMP_KEEP_RUNS` (0 = não apagar), `SPINJUMP_OUT` (pasta de saída).

## 11. Validação

Executada dentro do contêiner (`pytest`, `selftest`, `run --convergence`, `sweep`, `tools/ui_flow.py`,
`tools/ui_layout.py`). Os resultados estão na seção "Resultados da validação" abaixo.

### Resultados da validação (contêiner final, CPU, sem GPU)

| # | ensaio | critério | resultado medido |
|---|---|---|---|
| 1 | queda livre sem corda/ar | erro < 0,5% | posição 0,25% (máx., t = 0,1 s), velocidade 2e-13 |
| 2 | deslizamento isolado (μ = 0,6 / 0,3 / 0,1) | erro < 5% vs v²/(2μg) | +0,02% / +0,04% / +0,06% |
| 3 | impulso normal de impacto | erro < 3% vs m·Δv | sem gravidade 0,00%; com gravidade (+m·g·τ) 0,06%; pouso + repouso = 1 evento |
| 4 | involuta (sem atrito/gravidade/arrasto) | ΔKE < 2%; erro espacial informado | ΔKE 0,040%; erro espacial máx. 8,1 mm com ℓ = 15,7 m (0,86 volta liberada) |
| 5 | cabrestante | exp(μθ) com tolerância justificada | equilíbrio de forças discretizado (N = 20 000) → erro 3,6e-4; razão âncora/objeto do modelo = exp(−μθ) com rtol 1e-6 (lei aplicada analiticamente; hélice ancorada não escorrega) |
| 6 | convergência (resolução ×2, dt ÷2) | ≤ 10% | chegada 4,8%, deslizamento 1,05%, tração máx. 0,24% → confiável |
| 7 | azimute/determinismo/impulso | +libera, −reenrola; mesma seed = mesmos números | +90°: libera e gira no sentido de desenrolar; −90°: gira no sentido de enrolar e reenrola > 0,05 volta; séries idênticas com a mesma seed e diferentes com outra; J = 160 vs 640 N·s muda a posição em t = 3 s; impulso com duração entrega J com erro < 0,1% |
| 8 | comprimento, unilateralidade, alcance | fechamento exato; T ≥ 0; T = 0 com folga; alcance limitado | L = armazenado + repouso com erro 0 em todas as amostras; folga → T = 0; no solo o raio nunca passa do raio do toque (20,12 m); sem corda após o toque o objeto escapa até 20,54 m e termina a 5,8 m de distância |
| 9 | cenário demonstrativo | ≥ 1 volta, desenrolamento sincronizado, desliza, condicionado pela corda, sem quique numérico | 3,04 voltas antes do solo; hélice 5,38 → 2,24 voltas (correlação > 0,99 com o giro); 11,8 m de deslizamento; 34° de varredura no solo; corda tensa 100% do tempo no solo; repouso 3,9 s após o toque; energia após o toque nunca aumenta além do aporte do vento |
| 10 | fluxo UI/Docker | formulário → frames → pausa/retomada → artefatos; 1× por relógio; sem sobreposição; CPU; sem vídeo/logs | via `docker compose up`: 14,8 quadros/s; 1× = 1,000 (relógio do servidor); 2× pedido = 1,95× (servidor) / 1,93× (relógio do cliente); pausa congela o tempo simulado; relatório servido; Chromium em 4 viewports sem sobreposição, sem erro JS, sem rolagem horizontal; sem `/dev/dri` nem `/dev/nvidia*`; log driver `none` (`docker compose logs` vazio); nenhum MP4/GIF |

`pytest`: **37 testes aprovados** (~2 min; inclui página inicial, multitenant, capacidade, reconexão e limpeza de sessões); `selftest`: OK; `report --rerun`: métricas idênticas.

### Cenário padrão (`run --convergence`)

`AT_REST_CLEAN`. **3,04 voltas** do objeto antes do solo e 3,15 voltas liberadas pela hélice
(5,38 → 2,24). Distância mínima à parede: 0,60 m. Chegada ao solo em t = 29,5 s a **9,31 m/s**
(normal ~1,1–1,6 m/s, quase toda tangencial). Deslizamento de **11,8 m** e varredura de 34° em torno
da torre, com a corda tensa o tempo todo (tração no solo até 882 N). O objeto, rígido, tomba (22
saltos curtos, até 0,15 m). Repouso em t = 33,4 s. Tração máxima **1784 N** (8% da ruptura), na
âncora ~3 N. Sem folga em voo. Maior impacto: 32,4 g (25,5 kN filtrado) no solo, classificado
**DANO** pelo limiar ilustrativo de 10 g. Energia: 39,5 kJ iniciais; dobra/inserção 22,1 kJ, arrasto
12,2 kJ, contato/atrito 3,3 kJ, distribuídas 1,6 kJ, amortecimento 0,16 kJ, vento +0,72 kJ; resíduo
em voo 4 J. Custo: 33,4 s simulados em 13,2 s de CPU.

### Como os parâmetros alteraram o desfecho

| execução | desfecho | voltas antes do solo | chegada (m/s) | deslizamento (m) | tração máx. (N) | observação |
|---|---|---|---|---|---|---|
| padrão (az 90°, 4 m/s) | AT_REST_CLEAN | 3,04 | 9,31 | 11,8 | 1784 | sem folga em voo |
| `straight_drop` (v0 = 0) | HIT_STRUCTURE | 3,03 | 9,11 | 13,4 | 2328 | balança contra a parede no início e depois espirala |
| `tangential_impulse` (480 N·s em 200 ms) | AT_REST_CLEAN | 3,04 | 9,39 | 12,1 | 1852 | — |
| `rewind` (az −60°, 6 m/s) | HIT_STRUCTURE | 3,03 | 9,21 | 12,3 | 3848 | reenrolou 0,086 volta e bateu na torre (33 g) |
| `strong_wind` (10 m/s, rajadas 2,5) | AT_REST_CLEAN | 2,94 | 7,06 | 7,7 | 1599 | — |
| `no_air` | AT_REST_CLEAN | 3,83 | 19,8 | 68,2 | 1889 | sem arrasto a chegada dobra |
| `sandbag` (60 kg, fixo no topo) | AT_REST_CLEAN | 3,09 | 10,3 | 25,1 | 2231 | folga de 6,5 s no solo |
| `ice` (μ = 0,1) | AT_REST_CLEAN | 3,04 | 9,31 | 35,7 | 1784 | varre 90° em torno da torre |
| `short_rope` (35 m) | REWOUND | — | — | — | 1784 | não alcança o solo; reenrola 1,12 volta (aviso emitido) |

Varreduras (parâmetros finais):

- azimute × velocidade: azimute ≤ 0° leva a contato com a torre e tração de até 6,3 kN; 90° mantém
  0,6 m da parede e ~1,8 kN;
- L ∈ {70; 87,3; 110} m × μ_solo ∈ {0,2; 0,6} × 2 seeds: L praticamente não altera o resultado (3,06–3,07
  voltas, 9,0–9,2 m/s), porque o objeto chega ao solo após liberar ~3 voltas (~50 m) e o resto da
  corda fica armazenado; μ = 0,2 dobra o deslizamento (≈ 24 m contra ≈ 12 m).

O número de voltas antes do solo (~3) é quase insensível ao lançamento: é um atrator do regime de
descida em espiral freado pela dobra de saída (NOTES §3.1, §5). O lançamento decide a fase inicial
(colisão, tranco, reenrolamento); ar e atrito decidem a chegada e o deslizamento.

### Espiras deslizantes (padrão atual; 48 testes aprovados)

| ensaio | resultado medido |
|---|---|
| cabrestante dinâmico | inclinação de ln T na zona que escorrega: 0,196–0,2015 para μ = 0,2 e 0,391–0,399 para μ = 0,4 (≤ 2,2%; tolerância 5%) |
| pré-tensão | 20 N seguram as espiras contra o peso (< 2 mm); sem pré-tensão elas caem |
| puxão inclinado 60° | `down`: as espiras descem 10,3 m; `up`: o contato entre voltas segura (1 mm) |
| involuta (atrito realista na parede) | erro espacial 78,6 mm em ℓ = 15,7 m; ΔKE 0,4% |
| balanço de energia em voo | resíduo 184 J (0,4% de E0) no voo completo, caindo com dt |
| sensibilidade (10 s de voo) | descida das espiras 4,84–4,99 m e voltas 1,441–1,446 para dt ÷ 2, resolução × 2, janela 1,5–3 voltas, escala de massa 20–150 e atualização a cada 1–8 passos |
| convergência do cenário completo | chegada 0,9%, tração máxima 0,5%; deslizamento no solo **21% → NÃO CONFIÁVEL** |
| caos do pouso | perturbar a velocidade de lançamento em 1 mm/s muda o deslizamento de 9,7 para 27,7 m (desvio-padrão 5,7 m); as grandezas de voo mal mudam (chegada ±0,17 m/s, voltas ±0,04) |

Cenário padrão com espiras deslizantes: `AT_REST_CLEAN`, **2,78 voltas** antes do solo, chegada a
**10,05 m/s** em t = 24,6 s, deslizamento de 10,0 m (não confiável, ver acima), tração máxima 1825 N,
espiras descendo até 11,6 m pela torre, atrito na parede de 21,6 kJ. Custo: 0,50 s de CPU por s
simulado. Uma sessão roda em tempo real; num servidor de 2 CPUs, duas sessões simultâneas ficaram
entre 0,66× e 0,93× (medições variáveis neste host). Com as mesmas condições, as espiras travadas
dão 3,03 voltas e chegada a 9,31 m/s em 29,5 s.

As tabelas acima desta seção foram medidas com as espiras travadas e a hélice subindo (modelo
original).

### Não verificado

- Renderização EGL/GPU (`compose.gpu.yaml`): sem GPU no ambiente.
- Desempenho de várias sessões simultâneas com espiras deslizantes no Hugging Face real (medido só
  localmente com `--cpus 2`).
- Nada sobre lesão humana: os limiares são ilustrativos.


## 12. Limites metodológicos

- Modelo de corda simplificado. Com espiras deslizantes: corda encostada como cadeia sobre a
  superfície com Coulomb simples, contato entre voltas só na vertical, inércia escalonada e vão
  reto sem massa inercial nem flexão/torção. O atrito corda–parede domina o freio da descida. Com
  espiras travadas: sem escorregamento ao longo da torre, e a perda na dobra de saída é o freio
  (NOTES §3.1). Nos dois casos a forma com folga é ilustrativa.
- Com espiras deslizantes, parede sem atrito combinada com corda sem massa e muito rígida é mal
  condicionada (deriva de energia de ~8%).
- Objeto rígido único (manequim sem articulações): o pouso tende a tombamentos caóticos. Os
  detalhes do pouso variam, e as métricas agregadas são verificadas por convergência.
- Contato macio com complacência escolhida (20 ms). Os picos dependem disso e não representam
  tecido humano.
- Sem contato corda–objeto, corda–solo ou corda–borda do topo.
- Vento com rajada espacialmente uniforme; sem esteira da chaminé.
- Nada aqui é critério de segurança.
