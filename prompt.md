# Especificação para um novo simulador 3D de corda e chaminé

Construa **do zero, em um repositório novo**, uma aplicação de simulação física 3D em MuJoCo/Python. Entregue interface web interativa com cena ao vivo, Docker/Compose, CLI, testes físicos, relatórios e documentação em português. `planning.md` é o roteiro de implementação desta especificação. Tome decisões técnicas justificadas, registre limitações e não declare algo funcional antes de executar build, testes e simulação representativa.

## 1. Cenário e objetivo

Uma chaminé cilíndrica rígida e vertical, com altura H = 50 m e diâmetro D = 5 m por padrão, está fixa no solo. Uma ponta de uma corda de comprimento L está presa perto do topo. A corda começa enrolada em hélice de passo curto na parede, como linha num carretel fixo. A outra ponta prende um objeto com massa humana, do tipo saco de areia ou manequim. O objeto parte junto à borda, recebe velocidade inicial ou impulso configurável, cai, e a corda pode desenrolar enquanto ele gira ao redor da chaminé. Não há escorregador nem plataforma de lançamento modelada.

O cenário padrão demonstrativo deve produzir **voltas reais** antes de chegar ao solo, com a hélice liberando comprimento, e deslizamento no solo condicionado por atrito e corda. O giro deve surgir das forças e restrições, sem trajetória animada ou aceleração angular artificial. Para outras configurações, queda reta, colisão com a parede, folga e ausência de órbita são resultados possíveis e devem ser relatados, não ocultados. Responda: houve espiral ou colisão? Qual a velocidade/força de chegada ao solo e à estrutura? Quanto deslizou? A corda afrouxou ou reenrolou? Qual a tração máxima? Como impulso, L, vento, arrasto e atrito alteraram o desfecho?

Os resultados são qualitativos e exploratórios, **nunca validação de segurança humana**. Informe isso na interface, README e relatórios. Limiares de dano são ilustrativos, não clínicos.

## 2. Arquitetura e pilha

- Python 3.11, MuJoCo >= 3.2 com versão exata fixada, NumPy, SciPy, PyYAML, Pydantic, Matplotlib/Agg e pytest. Fixe versões testadas em `requirements.txt`.
- Toda a física e renderização 3D rodam no servidor Ubuntu dentro do Docker. O navegador envia parâmetros/comandos e apresenta frames e telemetria recebidos; não calcula a física nem renderiza a cena 3D localmente.
- OSMesa/headless por CPU é o padrão e funciona sem GPU. EGL/GPU no servidor é opcional e documentado. A máquina cliente não precisa de GPU especial.
- Separe passo de integração física, produção de telemetria e renderização/stream. O passo físico não depende da frequência da tela. Nada de MP4, GIF ou replay.
- Gere o modelo programaticamente a partir de YAML validado. Parâmetros físicos padrão ficam em `configs/default.yaml`, sem números físicos escondidos no código. Mesma configuração e seed no mesmo ambiente produzem as mesmas métricas.
- Desabilite logs rotineiros de progresso, requisições HTTP e container por padrão, inclusive no Compose. Informe erros necessários na interface e no resultado; mantenha eventos físicos nos artefatos e na telemetria, não num fluxo de log textual.

## 3. Modelo da corda: requisito central

A corda é componente físico, não apenas uma linha reta decorativa. Represente âncora, hélice em contato com cilindro, último ponto de contato, trecho livre tangente, comprimento liberado, alongamento, tração e eventual folga. A geometria exibida deriva do mesmo estado que calcula as forças. As voltas visíveis devem desaparecer à medida que o comprimento enrolado diminui. Quando frouxa, a corda não exerce tração axial negativa nem empurra o objeto; quando esticada, limita seu alcance, inclusive depois de tocar o solo. Elasticidade axial e amortecimento são configuráveis e documentados. Não force tensão ou folga para melhorar a aparência.

Antes de implementar o cenário completo, consulte a documentação e os exemplos do plugin `mujoco.elasticity.cable` na versão instalada e faça protótipo mínimo com corda enrolada, cilindro, âncora e massa terminal. Meça contato, estabilidade, liberação de voltas, tração e custo de cálculo. Use o plugin no produto somente se passar nos ensaios. Caso falhe, registre a evidência e implemente **outra formulação física explícita e validável** para o enrolamento, contato com parede, comprimento e tração unilateral. Não entregue `rope.model: chain` ou corrente de cápsulas como alternativa: esse modo foi excluído porque não produziu o comportamento requerido. Não exponha um modelo experimental na UI como equivalente a um validado.

A hélice inicial parte de âncora logo abaixo do topo, sobe com passo `winding_pitch_factor × rope.diameter_m` e raio `D/2 + rope.diameter_m/2`; depois sai tangente em direção ao ponto de fixação no objeto. Derive número de voltas do comprimento disponível e valide a contabilidade de comprimento. Se uma representação visual precisar aumentar o espaçamento para ser legível, rotule claramente a alteração de escala visual; não altere a física por isso.

O objeto tem massa/inércia coerentes e ponto de fixação físico. Manequim pode ser composto por tronco, cabeça e membros; saco por cápsula/cilindro. Documente a matriz de colisões entre objeto, corda, torre e solo. A corda não deve atravessar livremente a parede.

## 4. Solo, lançamento e forças

O lançamento tem modos `velocity` e `impulse`. Exponha `speed_ms` e **`impulse_Ns` em N·s** no formulário conforme o modo, com faixa e unidade claras. Implemente `J = m Δv` para impulso instantâneo ou força equivalente no intervalo `duration_ms`. Defina azimute: zero aponta ao longo do trecho livre para longe da chaminé; positivo gira no sentido de desenrolamento. Elevação e sentido de enrolamento são configuráveis. Teste a convenção e mostre que alterar impulso muda a trajetória mensurável.

Após tocar o solo, mantenha ativos contato, atrito e restrição da corda. O objeto deve **deslizar** enquanto houver movimento; com corda tensa, a trajetória pode continuar curvada ou circular ao redor da chaminé e não pode escapar em linha reta além do alcance. Não imponha parada instantânea, quique, ausência de folga ou círculo perfeito. Se houver repique/levantamento ou folga, explique pelas forças e energia e verifique convergência numérica. Se o efeito for artefato de contato, corrija-o. O estado de repouso exige baixa velocidade sustentada no solo.

Aplique vento horizontal médio + rajadas Ornstein–Uhlenbeck com seed, opção de perfil vertical, e arrasto relativo ao vento. Para o objeto, `F = -½ ρ CdA |v_rel| v_rel`. Para corda com massa distribuída, inclua arrasto normal/tangencial conforme a representação. Permita desligar ar e vento separadamente. Documente simplificações.

## 5. Configuração parametrizável

Disponibilize YAML validado, presets, overrides CLI repetíveis `--set caminho.parametro=valor` e formulário. Use unidades SI. Inclua pelo menos:

- `tower`: altura, diâmetro, atrito da parede.
- `rope`: comprimento `auto` ou manual, diâmetro, densidade, resolução espacial (se aplicável), rigidez axial EA, amortecimento, flexão/torção (se aplicável), atrito parede/solo, arrasto normal/tangencial, passo e sentido da hélice, carga para alerta e demais parâmetros do modelo validado.
- `object`: tipo `sandbag`/`mannequin`, massa, dimensões, altura do ponto de fixação, afastamento inicial, arrasto e atrito.
- `launch`: modo, velocidade, impulso, azimute, elevação e duração.
- `air`/`wind`: densidade, habilitação, velocidade/direção média, rajadas, correlação, cisalhamento, seed e presets.
- `ground`/`contact`: atritos deslizante, torcional e de rolamento, dimensão do plano, presets, `solref` e `solimp`.
- `impact`: limiar em g ou N, janela de filtro e fração de aviso.
- `solver`: timestep, integrador, tempo máximo, critério de repouso, opção de parar em colisão estrutural e taxa de saída.
- `ui`: frequência de frames e **fator de reprodução** ajustável, por exemplo 0,1× a 4×. Em 1×, o alvo é um segundo simulado por segundo real. Mostre tempo simulado, tempo real e taxa efetiva medida. Se o servidor não sustentar a taxa solicitada, indique a taxa real; não acelere silenciosamente nem salte passos físicos.

Valores iniciais da configuração (a escolha final do modelo de corda e os parâmetros demonstrativos dependem da validação física):

```yaml
tower:
  height_m: 50.0
  diameter_m: 5.0
  wall_friction: 0.5
rope:
  length_m: auto
  diameter_m: 0.012
  linear_density_kg_m: 0.075
  element_length_m: 0.2
  bend_E_pa: 5.0e7
  twist_G_pa: 2.0e7
  axial_EA_N: 5.0e4
  axial_damping_ratio: 0.1
  wall_friction: 0.4
  ground_friction: 0.5
  wind_drag_Cd_normal: 1.2
  wind_drag_Cd_tangent: 0.05
  winding_pitch_factor: 1.05
  winding_handedness: ccw
  self_collision: false
  breaking_load_N: 22000
object:
  type: mannequin
  mass_kg: 80.0
  height_m: 1.75
  radius_m: 0.20
  attach_height_fraction: 0.65
  start_clearance_m: 0.6
  drag_CdA_m2: 0.7
  geom_friction: 0.8
launch:
  mode: velocity
  speed_ms: 4.0
  impulse_Ns: null
  azimuth_deg: 20.0
  elevation_deg: 5.0
  duration_ms: 0
air:
  enabled: true
  density_kg_m3: 1.225
wind:
  enabled: true
  speed_mean_ms: 2.0
  direction_deg: 0.0
  gust_std_ms: 0.7
  correlation_time_s: 4.0
  shear_exponent: 0.0
  seed: 42
  presets: {calm: 0, light: 2, breeze: 5, strong: 10}
ground:
  friction_slide: 0.6
  friction_torsional: 0.005
  friction_rolling: 0.0001
  presets: {dry_asphalt: 0.7, concrete: 0.6, grass: 0.4, wet: 0.3, ice: 0.1}
  size_m: 600.0
contact:
  solref: [0.004, 1.0]
  solimp: [0.9, 0.95, 0.001]
impact:
  damage_threshold_g: 10.0
  damage_threshold_N: null
  filter_window_ms: 3.0
  warn_fraction: 0.5
solver:
  timestep_s: 0.0005
  integrator: implicitfast
  max_time_s: 120.0
  rest_speed_ms: 0.05
  stop_on_structure_hit: false
  output_hz: 200
ui:
  render_hz: 15
  playback_factor: 1.0
```

`rope.model` será o modelo aprovado na fase de validação. `cable_plugin` é o primeiro protótipo; `chain` não é uma opção. `rope.axial_EA_N: null` indica inextensível apenas se o modelo escolhido suportar esse regime de modo estável. Presets e parâmetros inaplicáveis ao modelo escolhido devem ser explicados, não ignorados silenciosamente.

Para `rope.length_m: auto`, apresente no relatório e configuração resolvida a estimativa original: `v = sqrt(2gH + v0²)`, `r_min = v sqrt(H/g)`, `L = sqrt(r_min² + H²)`. Para H=50 m e v0=0, resulta aproximadamente 86,6 m. Essa fórmula é ponto de partida simplificado, não garantia de órbita, de corda tensa ou de ausência de levantamento no solo. Escolha o padrão demonstrativo por validação. Avise sobre comprimento manual que impossibilite chegar ao chão, considerando a geometria real.

## 6. Interface gráfica ao vivo

A interface acessada pelo navegador deve ter formulário, presets, iniciar, pausar, retomar e encerrar. Mostre cena 3D renderizada no servidor e transmitida ao vivo, com câmeras livre, lateral e de acompanhamento controladas pelo servidor. Exiba velocidade, altura, tempo, taxa efetiva, distância à parede, voltas, corda enrolada/livre, folga, tração e impactos em tempo real. A hélice visível deve se desenrolar; o trecho livre não pode se comportar como linha que ignora a física.

Coloque labels, aviso de segurança e telemetria num painel fora da imagem ou em posições que **não cubram a chaminé, o objeto nem a corda**. Verifique layout em viewport comum. O controle de reprodução não muda forças físicas, apenas o ritmo em que os passos são executados e apresentados.

## 7. Impactos, relatórios e CLI

Detecte impactos do objeto contra solo e torre. Um evento representa intervalo contínuo de contato, agrupando interrupções menores que 20 ms e contatos simultâneos entre geometrias do mesmo objeto; um pouso não deve virar dezenas de eventos artificiais. Registre tempo, local, tipo, geom, força normal bruta/filtrada, impulso normal integrado, desaceleração em g, velocidades normal/tangencial e duração. Calcule força por `mj_contactForce` ou equivalente verificado. Classifique OK/ATENÇÃO/DANO com limiar configurável e destaque cores na UI, gráficos e HTML. Documente que picos dependem de `solref`, `solimp` e passo de tempo; limiar em g não é critério de lesão validado.

Reporte tração na âncora e no objeto, pico e alerta de carga, velocidade de chegada, distância de deslizamento, variação angular após contato com o solo, mínima distância à parede, voltas, comprimento desenrolado, folga e maior impacto. Classifique `AT_REST_CLEAN`, `HIT_STRUCTURE`, `REWOUND`, `TIMEOUT`, `NUMERICAL_FAILURE`.

Em `out/<data>_<nome>/`, salve `config_resolved.yaml`, `timeseries.csv`, `events.json`, `summary.json`, `summary.md`, `summary.html` e gráficos estáticos: trajetória 3D/superior, altura, velocidade, distância à torre, tração, comprimento enrolado e impactos. Não salve MP4, GIF ou replay. A CLI `python -m spinjump` oferece `run`, `sweep`, `report`, `rope-length` e `selftest`; `sweep` produz CSV e mapas de calor com grade de parâmetros/seeds, sem display. Não emita logs de progresso/impactos no terminal; resultados vão para artefatos, UI e retorno conciso da CLI.

## 8. Validação obrigatória

Implemente e rode dentro do container testes para:

1. Queda livre sem corda/ar: posição e velocidade com erro < 0,5% da solução analítica.
2. Deslizamento isolado no solo: distância de parada próxima de `v²/(2 μ g)`, erro < 5%.
3. Impacto isolado: impulso normal integrado próximo de `m Δv`, erro < 3%.
4. Involuta sem atrito/gravidade/arrasto: trajetória próxima da analítica e variação de energia cinética < 2% no regime definido; informe erro espacial.
5. Cabrestante sobre cilindro: razão de trações coerente com `exp(μθ)` dentro de tolerância justificada para o modelo escolhido.
6. Convergência com resolução espacial dobrada e timestep reduzido pela metade: velocidade de chegada, distância de deslizamento e tração máxima variam ≤ 10%; se não, sinalize resultado como não confiável.
7. Azimute positivo libera corda; negativo tende a reenrolar. Mesmo seed e configuração reproduzem resultados.
8. Comprimento total fecha com trecho enrolado, livre, alongamento/folga conforme o modelo; tração é unilateral; corda tensa limita o alcance após contato com o solo.
9. Cenário demonstrativo: pelo menos uma volta física antes do solo, redução sincronizada de comprimento enrolado, deslizamento após impacto e trajetória pós-solo condicionada pela corda. Sem parada instantânea ou quique numérico.
10. Fluxo UI/Docker: formulário → simulação → frames ao vivo → pausa/retomada → artefatos. Meça 1× por relógio; verifique ausência de label obstruindo a cena, funcionamento em CPU sem GPU, ausência de vídeos/replays e logs rotineiros.

Não afrouxe tolerâncias para fazer testes passarem. Registre falhas e hipóteses em `NOTES.md`.

## 9. Docker, README e entrega

Use `python:3.11-slim-bookworm`, bibliotecas OSMesa/EGL/GL necessárias, usuário não-root, volume `out/`, porta da UI, `PIP_NO_CACHE_DIR=1`, `MUJOCO_GL=osmesa` como padrão, `.dockerignore`, `Makefile` e `compose.yaml` obrigatório. Documente `docker compose up --build`, execução CLI/testes, publicação da porta, dados persistentes e EGL/NVIDIA Container Toolkit opcionais. O Compose não gera logs de rotina. Se um modo CLI usar ENTRYPOINT diferente da web, documente comandos prontos.

O README em português deve explicar parâmetros/unidades, fórmula de L e suas hipóteses, convenção de azimute com diagrama, desfechos/cores, limites metodológicos, operação headless e CPU/GPU. Registre em `NOTES.md` decisões, protótipos, falhas, calibração e convergência. Execute build, selftest, pytest, simulação padrão completa, varredura pequena e fluxo da interface dentro do container. O relatório final traz as saídas reais, métricas físicas, itens não verificados e limitações. Siga a sequência e os critérios de aceite de `planning.md`.
