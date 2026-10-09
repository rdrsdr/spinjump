# Planejamento de uma reimplementação do zero

Este é o roteiro para **um projeto novo** baseado em [prompt.md](prompt.md). Não é um plano de remendos para o código existente. Os problemas observados anteriormente entram aqui como requisitos originais: corda que realmente desenrola, objeto que gira por forças físicas, comportamento coerente após o solo, controle de impulso e tempo, interface desobstruída, sem corrente, vídeo ou logs rotineiros.

## Resultado verificável

O usuário preenche parâmetros no navegador e acompanha uma cena 3D ao vivo. Física e renderização rodam no servidor Docker; o navegador só envia comandos e apresenta frames/telemetria. O cenário demonstrativo produz ao menos uma volta antes da chegada ao solo e redução correspondente da corda enrolada. Após tocar o solo, o objeto desliza e a corda continua participando da dinâmica: quando esticada, impede fuga além do alcance e pode curvar a trajetória. O movimento até repouso vem de forças e atrito, sem parada ou trajetória impostas. A interface oferece impulso inicial editável e fator de reprodução; 1× é aferido por relógio e a taxa efetiva aparece na tela.

Resultados diferentes sob outros parâmetros são permitidos e devem ser reportados como consequência do modelo. Não se deve fabricar voltas, círculo perfeito, quique ou folga para agradar à visualização. Resultados numéricos instáveis são marcados como não confiáveis.

## Arquitetura proposta

| Componente | Responsabilidade |
| --- | --- |
| Configuração | YAML/Pydantic, defaults SI, presets, overrides CLI e entrada do formulário; configuração resolvida e seed persistidas. |
| Motor físico | MuJoCo headless, torre/solo/objeto, vento/arrasto, impulso, corda, contatos e integração com timestep fixo. |
| Modelo da corda | Enrolamento e contato com cilindro, trecho livre, alongamento, folga, tração unilateral e limite de alcance; estado físico único para forças e desenho. |
| Medição | Amostras, eventos agrupados, força/impulso, tração, energia, métricas de percurso e desfecho. |
| Servidor web | Sessões, iniciar/pausar/retomar/encerrar, stream de frames renderizados no servidor, telemetria e câmeras. |
| Interface | Formulário, presets, cena ao vivo, painel de medições fora da área da ação e controle de velocidade. |
| Entrega | CLI, relatórios, gráficos, testes, Dockerfile/Compose, README e NOTES. Sem MP4/GIF/replay e sem logs rotineiros. |

A renderização CPU com OSMesa é o caminho padrão. EGL/GPU é otimização opcional no servidor, nunca requisito para o navegador. Separar stepping, amostragem e renderização evita que taxa de frames ou fator de reprodução alterem a física.

## Fases, com portas de aceite

### 1. Fundação e contrato de configuração

- [ ] Criar repositório novo, pacote Python 3.11, versões fixadas, YAML/Pydantic, CLI, Dockerfile, `compose.yaml`, Makefile e estrutura de `out/`.
- [ ] Definir coordenadas, sentido do enrolamento, azimute, unidades SI, seed, estados, critério de repouso e nomes dos campos de telemetria.
- [ ] Publicar UI pela porta do Compose; garantir execução sem display e sem GPU; desligar logs de progresso, acesso e container por padrão.

**Passa quando:** container e configuração inicial funcionam; parâmetros da UI e da CLI chegam ao mesmo modelo sem perda; não existem opções de corrente, MP4 ou replay.

### 2. Prova da corda antes da aplicação completa

- [ ] Consultar documentação e exemplos do plugin `mujoco.elasticity.cable` da versão instalada. Criar protótipo de cilindro, hélice, âncora, massa terminal e contato.
- [ ] Medir se o plugin representa liberação de voltas, geometria tangente, comprimento, tração na âncora/objeto, folga e colisão estável. Medir custo por segundo simulado.
- [ ] Se falhar, documentar evidências em `NOTES.md` e implementar outra formulação física explícita de enrolamento/contato/tração. Não usar corrente de cápsulas como fallback nem deixar modo defeituoso selecionável.
- [ ] Testar comprimento total, tração unilateral, limite de alcance, involuta e resposta ao sentido do lançamento antes de avançar.

**Passa quando:** azimute positivo realmente diminui comprimento enrolado e muda trajetória; o objeto não atravessa parede nem escapa além da corda esticada; folga implica tração axial zero; erro/estabilidade/custo são quantificados. A hélice a desenhar pode ser reconstruída do estado físico.

### 3. Dinâmica completa e cenário demonstrativo

- [ ] Criar torre, solo, saco/manequim com massa e inércia, fixação da corda e matriz de colisões.
- [ ] Aplicar velocidade ou impulso em N·s, direção/elevação, vento com seed, arrasto e parâmetros de contato/atrito.
- [ ] Escolher cenário padrão por simulações de parâmetros, não apenas pela fórmula de L. Verificar voltas e desenrolamento antes do solo.
- [ ] Manter contato, atrito e corda após o impacto. Investigar forças e energia em qualquer parada imediata, escape radial, repique ou ausência de folga; refinar integração/contato quando for artefato.

**Passa quando:** padrão registra pelo menos uma volta antes do solo, comprimento liberado consistente, contato com solo seguido de deslizamento físico e trajetória condicionada pela corda. Aumentar impulso ou mudar atrito/comprimento altera métricas. Com corda tensa no solo, a distância ao ponto/curva de amarração respeita o alcance. Eventual levantamento ou folga tem causa mecânica e converge numericamente.

### 4. Medições e relatórios auditáveis

- [ ] Amostrar tempo, posição, velocidade, altura, ângulo/voltas, distância à parede, comprimento enrolado/livre, alongamento/folga, tração, forças de contato, vento, estado e energia.
- [ ] Agrupar contatos simultâneos e interrupções curtas em eventos físicos; não multiplicar um pouso por cada geom do manequim.
- [ ] Calcular força bruta/filtrada, impulso normal, velocidades de chegada, pico de tração, distância de deslizamento, ângulo percorrido no solo, colisão estrutural e desfecho.
- [ ] Gerar configuração resolvida, CSV, JSON, HTML/Markdown e gráficos estáticos. Incluir alertas de convergência e aviso metodológico.

**Passa quando:** ensaio de queda isolada reproduz impulso normal analítico dentro da tolerância; relatório e séries permitem explicar por que houve giro, folga, quique, deslizamento ou parada; pouso contínuo aparece como evento agrupado.

### 5. Interface 3D ao vivo

- [ ] Criar formulário com parâmetros essenciais, presets e modo velocidade/impulso; permitir editar `impulse_Ns` diretamente.
- [ ] Criar stream de frames 3D renderizados no servidor e telemetria sincronizada; implementar iniciar, pausar, retomar, encerrar e câmeras livre/lateral/acompanhando.
- [ ] Desenhar hélice restante, saída tangente, trecho livre e folga a partir do estado físico; distinguir qualquer escala visual ampliada da geometria física.
- [ ] Colocar labels, avisos e métricas fora da área que contém torre, objeto e corda; conferir layout em navegador comum.
- [ ] Expor fator de reprodução (por exemplo 0,1×–4×), tempo simulado, tempo real e taxa efetiva. Pausa congela a integração; mudança de ritmo não altera forças.

**Passa quando:** preencher formulário e iniciar gera simulação no servidor visível ao vivo; alterações em impulso/sentido/atrito mudam o resultado; corda visual e métricas coincidem; nenhuma label obstrui a ação; 1× se aproxima de tempo real no perfil de hardware declarado ou a interface expõe claramente a taxa inferior.

### 6. Validação, desempenho e entrega

- [ ] Rodar testes físicos: queda livre < 0,5%; deslizamento isolado < 5%; impulso normal < 3%; involuta/energia < 2% no regime aplicável; cabrestante com tolerância justificada; comprimento, folga, sentido do azimute e determinismo.
- [ ] Repetir cenário com resolução espacial dobrada e timestep pela metade. Se velocidade de chegada, distância de deslizamento ou tração máxima variar > 10%, marcar resultados como não confiáveis.
- [ ] Executar build, selftest, pytest, cenário padrão completo, varredura curta e fluxo UI dentro do container. Medir custo físico, custo de renderização e fator real de reprodução em CPU; testar EGL somente se houver GPU disponível.
- [ ] Conferir ausência de MP4/GIF/replay e logs rotineiros. Finalizar README em português, comandos Docker/Compose, parâmetros/unidades, diagrama de azimute, hipóteses/limitações e `NOTES.md` com decisões e falhas.

**Passa quando:** execução demonstrativa tem evidência numérica de voltas, corda liberada, trajetória e distância após o solo, tração e impactos; testes/integração aprovam ou falhas ficam explicitamente identificadas. Relatório final apresenta saídas reais e itens não verificados.

## Riscos que decidem o projeto

| Risco | Ensaio ou decisão |
| --- | --- |
| Cabo discreto cai reto ou atravessa a torre | Medir contatos, orientação do impulso, liberação de comprimento e tensão no protótipo. Rejeitar o modelo se persistir. |
| Corda é só uma linha visual | Comparar geometria exibida, comprimento, pontos de contato e tração com estado físico a cada amostra. |
| Objeto para, quica ou foge em linha reta após o solo | Examinar força normal, atrito, folga, tração e energia; repetir com passo/contato refinados. |
| Tempo exibido difere do relógio | Medir segundos simulados por segundo real com renderização ativa e mostrar taxa efetiva. |
| Forças de impacto são sensíveis ao solver | Reportar impulso, força bruta/filtrada e estudo de convergência; não inferir segurança humana. |
| Hélice densa fica ilegível | Ajustar câmera, iluminação e contraste sem mudar física; rotular qualquer ampliação visual. |

Não avance para a UI completa antes de validar a corda. Não reduza tolerâncias apenas para fazer testes passarem e não crie rotação, círculo ou parada por animação. Se uma configuração não permitir a espiral, a aplicação deve mostrar esse resultado e os parâmetros que o causaram.
