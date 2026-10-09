# NOTES (SpinJump) — decisões, protótipos, falhas, calibração e convergência

Registro técnico do desenvolvimento. Tudo foi executado dentro do container
(`python:3.11-slim-bookworm`, MuJoCo 3.15.0, CPU sem GPU, OSMesa/llvmpipe,
14 vCPUs em WSL2). Os números abaixo são saídas reais dos scripts citados.

> Resultados qualitativos e exploratórios; não são validação de segurança humana.

## 1. Ambiente e versões

- Python 3.11 (imagem `python:3.11-slim-bookworm`), versões fixadas em `requirements.txt`
  (mujoco 3.15.0, numpy 2.4.6, scipy 1.17.1, pydantic 2.13.5, matplotlib 3.11.2, fastapi 0.142.4,
  uvicorn 0.54.0, websockets 17.2, pillow 12.3.0, pytest 9.1.1).
- `MUJOCO_GL=osmesa` é o padrão; EGL só é usado se configurado (sem GPU neste ambiente → **EGL não
  testado**).

## 2. Fase 2 — protótipo do plugin `mujoco.elasticity.cable` (REPROVADO)

Script: `prototypes/cable_plugin_proto.py`; saídas em `prototypes/results/`.

Cenário: cilindro rígido D = 5 m, hélice ccw de passo 1,05·d (d = 12 mm) presa a uma âncora 0,3 m
abaixo do topo (o primeiro corpo do cabo é fixo, `initial="none"`), trecho livre tangente até
massa de 80 kg (`connect`), lançamento tangencial no sentido de desenrolar. Composite `cable` com
`vertex` explícito, cápsulas de raio d/2, contato cápsula–cilindro, atrito 0,4, cone elíptico.

| ensaio | nv | resultado |
|---|---|---|
| L = 86,6 m, seg. 0,2 m, dt 0,5 ms | 1302 | **3030 s de CPU por s simulado**; penetração corda–parede 52,8 mm; em 0,1 s a "hélice em contato" caiu de 84,8 para 46,8 m (espiras se soltando por impacto inicial) |
| L = 86,6 m, seg. 0,5 m, Newton | 522 | 208 s CPU/s simulado |
| idem, CG/pyramidal, 30 it. | 522 | 142 s CPU/s simulado; tração na âncora espúria de 3,1 kN em 20 ms |
| L = 20 m, seg. 0,5 m, dt 0,5 ms | 123 | **NaN em t = 0,6365 s**; penetração 518 mm (corda atravessou a parede) |
| L = 20 m, seg. 0,2 m, dt 0,5 ms | 303 | **NaN em t = 0,4115 s**; penetração 432 mm; espiras deslizaram de z∈[49,70; 49,71] para [49,06; 50,12] |
| L = 20 m, seg. 0,2 m, dt 0,1 ms | 303 | **NaN em t = 0,4156 s**; penetração 467 mm; 334 s CPU/s simulado |
| L = 20 m, seg. 0,5 m, dt 0,1 ms | 123 | sem NaN em 3 s, mas penetração 485 mm, picos de tração 11,7 kN (objeto) / 14,3 kN (âncora) com massa de 80 kg, 19 s CPU/s simulado |

Diagnóstico: cápsulas de 6 mm contra uma parede de raio 2,5 m atravessam o cilindro sob a tração
do lançamento (passo de segmento ≫ raio da cápsula), as espiras sem pré-tração escorregam pela
torre sob gravidade (não há normal sem tração circunferencial), e o custo do sistema com centenas
de corpos e contatos inviabiliza tempo real. **Decisão:** o plugin não é usado no produto. A
validação recusa `rope.model: cable_plugin` (mensagem aponta este arquivo); `chain` é recusado por
especificação.

## 3. Formulação adotada: `wrap_tether`

Arquivo `spinjump/rope.py` (docstring com as equações). Resumo:

1. **Hélice armazenada** (âncora → P1): raio rc = D/2 + d/2, passo p, ângulo u_s. Travada por atrito
   (não escorrega nem se alonga) e só diminui: quando a tangente horizontal de A cai "atrás" de P1,
   a corda **descasca** e P1 recua. As voltas visíveis somem conforme u_s diminui.
2. **Trecho geodésico** (P1 → D): ao girar no sentido de enrolar, a corda se apoia no cilindro ao
   longo de uma hélice cujo passo é dado pela geometria (corda de "tetherball"). Na planificação do
   cilindro, geodésica + vão livre formam uma reta: ℓ = sqrt((rc·|ψ_g| + ℓ_h)² + Δz²). A força em A é
   −T·e (gradiente do caminho mínimo): **conservativa**, logo reenrolar não cria energia.
3. **Vão livre** reto D → A, tangente ao cilindro em D (não atravessa a parede por construção).
4. **Lei axial unilateral:** T = max(0, kδ + cδ̇) se δ > 0, senão 0; k = EA/L_rep, c = 2ζ·sqrt(k·m).
   δ < 0 = folga (T = 0, não empurra). EA nulo (inextensível) é recusado: a lei explícita não é estável
   com rigidez infinita.
5. **Cargas distribuídas** no vão (peso + arrasto normal/tangencial) por quadratura com segmentos de
   `rope.element_length_m`, transmitidas ao objeto pela regra da alavanca (sem flecha). A corda tem
   massa distribuída apenas como carga; sua inércia é desprezada (6,5 kg contra 80 kg).
6. **Âncora:** T_âncora = T·exp(−μ·u_s) (cabrestante com atrito mobilizado).

### 3.1 Dissipação na dobra de saída (achado importante)

Ao descascar com o vão inclinado, há uma dobra em P1 entre a espira (quase horizontal) e o vão. O
material liberado (κ por radiano) é maior que o crescimento geométrico do vão (e·dP1/du), e a
diferença consome energia elástica sem trabalho: P = T·(κ − e·dP1/du)·|u̇|. É a perda clássica de
uma dobra que percorre material sob tração (T·v·(1 − cos θ)), fisicamente associada a atrito e
arraste da corda sobre as espiras. Inclui-se também a perda de inserção de material sem deformação
(½·δ²·EA·L̇/L²). No cenário padrão essa perda responde por **~60% da energia inicial** e funciona
como um freio de descida (como um descensor): a queda de 50 m leva ~30 s em espiral, e não 3,2 s.
**É a hipótese de modelo de maior influência no resultado.** Um modelo em que as espiras escorregam
pela torre daria outro desfecho; esse escorregamento não é simulado. Como diagnóstico, o sumário
reporta `coil_slip_ratio_max`: a componente vertical do vão em P1 dividida pela capacidade de atrito
da hélice, T·(1 − e^(−μ·u_s)). Valores > 1 indicam que a hipótese de espiras travadas exigiria mais
atrito que o disponível. No padrão o máximo é ≈ 0,94 (limite).

### 3.2 Balanço de energia

Rastreados: arrasto sobre o objeto, aporte do vento, trabalho das cargas distribuídas, amortecimento
axial, dobra/inserção e força de lançamento. Em voo (antes do primeiro contato), o resíduo
|E_obj + E_el − (E0 + ΣW)| é 18,6 J com dt 0,5 ms, 8,4 J com dt 0,25 ms e 4,5 J com dt 0,125 ms,
sobre E0 ≈ 39,5 kJ: erro de integração de primeira ordem, coerente com Euler semi-implícito. Antes
de incluir a perda de inserção o resíduo era ~485 J; foi isso que revelou o termo.

## 4. Calibração do contato e do solo (com evidência)

| problema observado | evidência | decisão |
|---|---|---|
| Manequim deitado balançava sem parar (ω 0,1–0,4 rad/s após 10 s) | `prototypes/rest_jitter.py`: corpo rígido de superfícies curvas com resistência ao rolamento 1e-4 m rola como cadeira de balanço sem dissipação | `ground.friction_rolling` = `friction_torsional` = 0,02 m (resistência ao rolamento de corpo deformável); o balanço cai para ω ≈ 0,001 rad/s |
| Rebote numérico após impacto vertical mesmo com `dampratio` 1 | `prototypes/bounce_check.py`: saco a 6 m/s → salto de 2,6 mm (solref 0,02/1,0); com o valor inicial 0,004/1,0, saltos de 25 mm (6 m/s) e 52 mm (9 m/s); `dampratio` ≥ 1,3 elimina o salto em 2, 6 e 9 m/s | `contact.solref = [0.02, 1.5]` |
| Picos de impacto não convergiam com contato rígido | estudo do pouso (`prototypes/landing_study.py`): solref 0,004 → 189 / 141 / 92 g para dt 0,5 / 0,25 / 0,125 ms; 0,02 → 26 / 28 / 29 g | constante de tempo de 20 ms (complacência de manequim/saco); picos dependem de solref/solimp/dt e isso é documentado |
| Deslizamento do pouso não convergia com dt 0,5 ms | deslizamento 15,1 / 12,6 / 13,0 m (dt 0,5 / 0,25 / 0,125 ms) | `solver.timestep_s = 0.00025` |

Deslizamento puro validado: caixa e saco deslizando ao longo do eixo param a v²/(2μg) com erro
< 0,2% (`prototypes/slide_check.py`, teste 2).

Atrito do par objeto–superfície = menor coeficiente entre superfície (solo/parede) e objeto
(`object.geom_friction`): a superfície mais escorregadia domina.

## 5. Escolha do cenário demonstrativo

Varredura `sweep --param launch.azimuth_deg=-60,-20,0,20,45,90 --param launch.speed_ms=2,4,6,8`
(24 execuções, configuração intermediária: contato 0,02/1,0; refeita em escala menor com os
parâmetros finais, ver README). Resultado notável: **a espiral é um
atrator**. Em todas as combinações ocorreram 3,01–3,05 voltas antes do solo, com chegada a
9,1–9,4 m/s. O lançamento altera a fase inicial:

- azimute ≤ 0: contato com a torre (HIT_STRUCTURE em 11 de 12 casos), reenrolamento inicial de
  0,03–0,09 volta, trações de até 8,4 kN;
- azimute 20° (valor inicial da especificação): sem colisão, mas o objeto passa a 0,19 m da parede
  e sofre tranco inicial de 3,9 kN (o lançamento estica a corda já tensa); no estudo de convergência,
  o deslizamento variou 11,5% com a resolução espacial dobrada (acima de 10%);
- azimute 90° / 4 m/s: sem folga em voo, tração máxima 1,78 kN, afastamento mínimo 0,6 m, e
  convergência dentro de 5% em todas as métricas.

**Padrão escolhido:** `launch.azimuth_deg = 90`, `speed_ms = 4`, `elevation_deg = 5`. Os demais
parâmetros iniciais da especificação foram mantidos, exceto os de contato/solo/dt da seção 4.

## 6. Pouso: tombamento físico (não numérico)

O manequim rígido toca o solo quase de pé a ~9 m/s tangencial e tomba. Há 11–26 "voos" curtos
(até 0,15–0,6 m do ponto mais baixo). Verificações:

- o número e a altura dos saltos não tendem a zero ao reduzir dt (0,5 → 0,125 ms), logo não são
  instabilidade de integração;
- o ensaio isolado de impacto vertical com o contato escolhido não rebate (seção 4);
- após o toque, a energia mecânica nunca aumenta além do aporte do vento (teste 9). Os saltos vêm
  da conversão de energia de rotação do tombamento, não de energia injetada pelo contato.

Cada salto com voo > 20 ms gera um novo evento de impacto (regra da especificação). Contatos
simultâneos de várias geoms e interrupções < 20 ms são agrupados. O relatório também informa a
contagem de saltos (`ground_hops`) e a altura máxima.

## 7. Convergência (cenário padrão)

`run --convergence` no padrão final (contêiner):

| variante | chegada (m/s) | deslizamento (m) | tração máx. (N) |
|---|---|---|---|
| base (dt 0,25 ms, segmento 0,2 m) | 9,311 | 11,826 | 1784,1 |
| resolução espacial ×2 (0,1 m) | 9,311 | 11,834 | 1784,1 |
| timestep ÷2 (0,125 ms) | 8,864 | 11,950 | 1779,8 |

Variação máxima: 4,8% (chegada) → confiável (≤ 10%). A velocidade de chegada é medida no primeiro
contato; com o manequim tombando, ela depende de qual geom toca primeiro, daí os ~5%.

Antes das correções, o padrão com azimute 20° tinha variação de 11,5% no deslizamento (resolução
×2) e, com dt 0,5 ms, de 16–20%. Essas variações motivaram as escolhas das seções 4 e 5.

## 8. Desempenho

- Física: ~72 µs/passo no ar, ~107 µs/passo no solo (dt 0,25 ms) → 0,29–0,43 s de CPU por s simulado.
  Antes das otimizações escalares eram 311 µs/passo.
- Render OSMesa 960×600: 205 ms/quadro com sombras + MSAA; 54 ms sem eles; ~23–30 ms com malhas
  leves (16 fatias, 6 camadas) e hélice com 36 pontos por volta.
- Processo de render separado (spawn), para não disputar o GIL. Mesmo assim, um render a toda
  velocidade desacelera a física em ~80% (interferência de CPU entre processos neste host).
  `LP_NUM_THREADS=2` reduziu a interferência. Sessão com fator 4× pedido sustentou 2,86×; 1× e 2×
  são sustentados. Acima disso, a interface mostra a taxa real.
- O ritmo nunca acelera para "recuperar" atraso: se a física fica > 0,25 s de relógio atrás, o
  ritmo é reancorado (passos não são pulados) e a taxa efetiva aparece na tela.

## 9. Falhas, hipóteses e itens não verificados

- EGL/GPU: sem GPU no ambiente de teste; `compose.gpu.yaml` está documentado e **não foi testado**.
- Escorregamento das espiras ao longo da torre não é modelado (ver 3.1); o diagnóstico é só um
  indicador.
- Contato corda–objeto, corda–solo e corda–borda do topo não são modelados. O aviso aparece se a
  elevação de lançamento for alta (> 60°).
- A forma da corda com folga é ilustrativa (parábola com o comprimento disponível); a dinâmica da
  folga não tem massa própria.
- Trecho geodésico sem atrito; o cabrestante só é aplicado à hélice armazenada.
- Classificação de desfecho: no início, o tempo máximo fixava `TIMEOUT` antes da classificação, e o
  preset `short_rope` (reenrolou 1,12 volta) saía como `TIMEOUT`. Corrigido com a precedência
  NUMERICAL_FAILURE > HIT_STRUCTURE > REWOUND > TIMEOUT > AT_REST_CLEAN.
- Interface: o placeholder com `display:flex` ignorava o atributo `hidden` e cobria a cena. O
  verificador de layout passava porque também ignorava elementos com `hidden`. Corrigidos os dois: a
  verificação agora usa só o estilo computado.
- Tombamento do manequim rígido é caótico: detalhes do pouso (número de saltos) variam com dt; as
  métricas agregadas (velocidade de chegada, deslizamento, tração máxima) convergem dentro de 10%.
- Picos de força/g dependem de solref/solimp/dt; o limiar em g é ilustrativo.

## 10. SpinJump: nome, idiomas, multitenant e página inicial (2026-10-08)

- **Nome:** pacote, CLI, imagem, Compose e variáveis renomeados para `spinjump` / `SPINJUMP_*`.
- **Idiomas:** `spinjump/i18n.py` concentra os textos em pt/en. O idioma é por processo: a CLI fica em
  pt e `serve` usa en (`--lang`, `SPINJUMP_WEB_LANG`). Códigos de dados (desfechos, classes
  OK/ATENÇÃO/DANO) não mudam; só os rótulos (OK/WARNING/DAMAGE). Presets ganharam `description_en`.
  - Bug encontrado na troca: variáveis locais chamadas `t` (tempos) escondiam a função `t()` em
    `impacts.py`. Qualquer impacto encerrado derrubava a simulação; nos testes isso aparecia como
    uma sessão que congelava ao bater na torre. Corrigido com apelidos (`tr`, `_t`) nos módulos com
    variáveis `t`.
- **Multitenant:** primeiro implementado com uma sessão por visitante em threads do mesmo processo.
  Medição (`prototypes/mt_rate.py`): 2 sessões simultâneas caíam para 0,6× cada, por disputa do GIL
  entre os laços físicos em Python. Solução: cada sessão roda em processo próprio
  (`web/session_proc.py`, spawn, não-daemon porque cria o processo de render). O servidor mantém só
  um proxy que repassa quadros e mensagens. Resultado: 2 sessões a 1,0× cada, 3 a ~0,94× (14 vCPUs);
  com `--cpus 2`, 2 sessões a ~0,95× e 3 a ~0,5×.
  - Outro bug: a mensagem `hello` era montada com `**mgr.load()`, que trazia `"type": "server"` e
    sobrescrevia o tipo. O cliente nunca recebia o `hello`.
  - Se o servidor morrer, o pipe fecha e o processo da sessão encerra a simulação e sai (sem órfãos).
- **Página inicial:** `/` (inglês) explica o que é simulado, deixa claro que é só simulação, que não é
  recomendação nem instrução, os riscos reais e "não tente", e pede confirmação antes de `/app`.
  Verificada com Chromium (layout, bloqueio sem confirmação, sem erros JS).

## 11. Espiras deslizantes (opção B) e desenrolamento de baixo para cima (2026-10-09)

Pedido: simular o escorregamento das espiras pela torre (a hipótese mais influente do modelo
travado) e desenrolar de baixo para cima. O estado anterior está versionado (`git tag
v1-locked-coils`, branch `main`); o trabalho está no branch `feature/sliding-coils`.

### Formulação final (`spinjump/surface_rope.py`, `spinjump/_chain_kernel.py`)

Cadeia de nós da âncora até o ponto de saída, presos à superfície do cilindro (2 GDL por nó nas
coordenadas planificadas), com:
- passo implícito com matriz bloco-tridiagonal 2×2 (rigidez axial unilateral + geométrica,
  amortecimento axial e rigidez do vão na ponta), resolvida por Thomas em blocos;
- atrito de Coulomb local por conjunto ativo (aderido = velocidade final nula; escorregando = força
  μN contra o movimento; até 8 iterações), com N = T̄·Δs·cos²β/rc;
- contato vertical entre voltas vizinhas (projeção);
- pré-tensão de enrolamento;
- inércia escalonada com piso ω·h ≤ 2;
- janela móvel adaptativa;
- força do vão aplicada em D pela regra da alavanca entre os dois nós vizinhos.

O balanço do vão sem massa dá a perda na saída, e o amortecimento usa o alongamento efetivo do passo.

### Tentativas e falhas (em ordem)

1. **XPBD com massa real (7,5–15 g/nó), 2 iterações.** O nó da ponta, puxado com kN, chicoteava
   (até 26 m/s), com resíduo de energia de até 110 kJ e trações espúrias de 8–11 kN.
2. **Relaxação quase-estática (Gauss-Seidel vermelho-preto).** Estável, mas convergia devagar: a
   descida das espiras ia de 0,5 a 3,5 m entre 3 e 40 varreduras por passo, e 40 varreduras custavam
   38× o tempo real.
3. **Amortecimento por diferença finita do alongamento.** Picos de 30–72 kN, porque os saltos do
   ponto de saída viravam "velocidade". Corrigido com δ̇ = e·v_A + σ̇_D(1 − cos θ), σ̇_D geométrico.
4. **Passo implícito com massa real.** Chicote a 70–250 m/s no ensaio isolado. A escala de massa
   resolveu, e o resultado é invariante entre escalas 30 e 100 (3,35–3,41 m; atrito ~1,9 kJ).
5. **Atrito aplicado depois da solução implícita.** Como a corda é rígida, o atrito agia no total do
   trecho, não nó a nó, e o cabrestante dava 0,162 para μ = 0,2. O conjunto ativo corrigiu isso. A
   janela fixa de 1,5 volta também truncava o perfil com μ baixo, daí a janela adaptativa.
6. **Força aplicada no último nó com ponta geométrica.** O ponto de saída se deslocava mais que o
   nó, e o resíduo ficava em 3 kJ. A regra da alavanca com ponta dinâmica fechou o balanço (resíduo
   de 646 → 183 J em 10 s).
7. **Caso degenerado:** parede sem atrito com corda sem massa e EA 100× divergia. O piso de inércia
   o estabiliza, mas ainda há deriva de energia de ~8% (limitação registrada).
8. **Bug da internacionalização:** uma variável local `t` escondia a função de tradução em
   `impacts.py` e derrubava a simulação no primeiro impacto (visto como sessão congelando ao bater na
   torre).

### Validação

Ver README §11 ("Espiras deslizantes"): cabrestante dinâmico (≤ 2,2% durante o escorregamento),
pré-tensão, puxão inclinado, involuta, energia, sensibilidade e convergência. Comparação física: o
freio total é parecido nos dois modelos (10,6 kJ contra 9,0 kJ em 10 s de voo), mas o mecanismo muda
(atrito real na parede em vez da fórmula da dobra), e a descida fica mais rápida (24,6 s contra
29,5 s até o solo). Isso concorda com a análise de curva de transição limitada pelo atrito: a corda
sai inclinada em α e o ponto de saída desce da ordem de (rc/μ)(sec α − 1) ou mais.

### Caos do pouso

Com espiras deslizantes, o instante e a atitude do toque variam com perturbações mínimas: ±0,5 s
para 1 mm/s na velocidade de lançamento. O manequim rígido tomba de forma diferente a cada vez. Num
conjunto de 6 execuções, o deslizamento no solo teve média de 18,4 m e desvio-padrão de 5,7 m (dt
base), contra 13,3 ± 2,2 m (dt/2). As grandezas de voo convergem (chegada 3,3%, voltas 0,7%,
tração 0,1%, descida das espiras 3,8%). O estudo de convergência do produto continua comparando
execuções únicas, como a especificação pede, e marca o deslizamento como NÃO CONFIÁVEL.

### Desempenho

Kernels `numba` (corda encostada e cargas distribuídas do vão): 117 µs/passo com espiras
deslizantes e 53 µs/passo com travadas. Antes, eram 214 e 83 µs/passo em NumPy. O cache de
compilação é gerado na construção da imagem (`/tmp/numba_cache`, legível e gravável por qualquer
UID). As medições com várias sessões simultâneas variaram bastante neste host WSL2 (por exemplo,
0,47× e 0,73× para 2 e 3 sessões sem limite de CPU numa rodada).
