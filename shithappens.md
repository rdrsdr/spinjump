# Configurações que causam colisão com a estrutura

> Resultados **qualitativos e exploratórios** de um modelo simplificado. **Não são validação de
> segurança humana** nem orientação de prática; limiares de dano são ilustrativos, não clínicos.

Levantamento de 2026-10-09, modelo atual (`feature/sliding-coils`: espiras deslizantes,
desenrolamento de baixo para cima), partindo de `configs/default.yaml` (H = 50 m, D = 5 m,
lançamento 4 m/s, azimute 90°, elevação 5°, vento 2 m/s). Colisão estrutural = contato com a torre
com velocidade normal acima de 1 m/s (`HIT_STRUCTURE`).

Convenção do azimute: 0° = ao longo do vão livre, para longe da chaminé; positivo = sentido de
desenrolar (90° = tangencial); negativo = sentido de enrolar.

## 1. Direção do lançamento

Varredura `out/20261009-211302_sweep_colisao_azimute/` (vento padrão):

| azimute | 0,5 m/s | 4 m/s | 8 m/s |
|---|---|---|---|
| −150° | **colisão** | **colisão** | **colisão** |
| −90° | **colisão** | **colisão** | **colisão** |
| −60° | **colisão** | **colisão** | **colisão** |
| −30° | **colisão** | **colisão** | **colisão** |
| 0° | **colisão** | **colisão** | **colisão** |
| 45° | sem colisão (passa a 6 mm) | sem colisão | sem colisão |
| 90° (padrão) | sem colisão (passa a 8 cm) | sem colisão | sem colisão |
| 150° | sem colisão (toca abaixo de 1 m/s) | sem colisão | sem colisão |

Detalhe das colisões (primeiro contato com a torre):

| caso | t (s) | altura (m) | v normal (m/s) | v total (m/s) | pico (g) | mecanismo |
|---|---|---|---|---|---|---|
| azimute 0°, 4 m/s | 0,93 | 46,3 | 1,5 | 7,6 | 30 | pêndulo: sai para fora e volta contra a parede |
| azimute −90°, 4 m/s | 0,21 / 0,99 | 49,2 / 46,7 | 2,9 / 0,3 | 4,1 / 6,4 | 24 / 26 | reenrola ~0,08 volta e bate duas vezes no início |
| azimute −150°, 8 m/s | 0,08 | 49,3 | 7,4 | 7,9 | 64 | lançado praticamente contra a parede |

Todas as colisões por lançamento acontecem no **primeiro segundo**, perto do topo, quando o trecho
livre da corda ainda é curto (2–6 m) e quase vertical.

## 2. Vento forte

Varredura `out/20261009-211330_sweep_colisao_vento/` (lançamento padrão, rajadas 2,5 m/s;
direção = para onde o vento sopra, a partir de +x; o objeto parte do lado +x):

| direção | 10 m/s | 20 m/s |
|---|---|---|
| 0° (afastando da torre) | sem colisão | sem colisão (reenrola 0,31 volta) |
| 90° (lateral) | sem colisão | **colisão** |
| 180° (contra a torre) | sem colisão | **colisão** (172 contatos; reenrola 0,38 volta) |
| 270° (lateral) | sem colisão | **colisão** |

Detalhe (20 m/s):

| caso | t (s) | altura (m) | v normal (m/s) | pico (g) |
|---|---|---|---|---|
| vento 180° | 6,9 / 23,3 | 26,0 / 9,1 | 1,7 / 2,8 | 18 / 24 |
| vento 90° | 8,4 / 18,4 | 24,1 / 3,0 | 4,9 / 3,2 | 16 / 14 |

Com 10 m/s o arrasto no manequim (~40 N) é pequeno diante da tração (700–1800 N). Com 20 m/s o
vento freia a rotação, a corda afrouxa/reenrola e as colisões ocorrem no meio da descida e perto do
chão.

## 3. Outros casos conhecidos

- Preset `rewind` (azimute −60°, 6 m/s): colisão no início.
- Preset `straight_drop` (v0 = 0): no modelo de espiras travadas balança contra a parede
  (`HIT_STRUCTURE`); com espiras deslizantes e 0,5 m/s ainda roça a parede.
- Preset `short_rope` (35 m): não alcança o solo e reenrola (`REWOUND`).

## Como reproduzir

```bash
# casos isolados
docker compose run --rm cli run --set launch.azimuth_deg=0 --name colisao_az0
docker compose run --rm cli run --set launch.azimuth_deg=-90 --name colisao_az-90
docker compose run --rm cli run --set launch.azimuth_deg=-150 --set launch.speed_ms=8 --name colisao_az-150
docker compose run --rm cli run --set wind.direction_deg=180 --set wind.speed_mean_ms=20 --set wind.gust_std_ms=2.5 --name colisao_vento180
docker compose run --rm cli run --preset rewind

# varreduras
docker compose run --rm cli sweep --name colisao_azimute \
  --param launch.azimuth_deg=-150,-90,-60,-30,0,45,90,150 --param launch.speed_ms=0.5,4,8
docker compose run --rm cli sweep --name colisao_vento \
  --param wind.direction_deg=0,90,180,270 --param wind.speed_mean_ms=10,20 --set wind.gust_std_ms=2.5
```

Na interface: preset **rewind**, ou mude *launch azimuth* para 0 ou negativo, ou o vento para
20 m/s em direção lateral/contra a torre.
