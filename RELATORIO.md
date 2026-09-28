# Relatório de análises

Todas as consultas estão em `sql/consultas.sql`. Resultados obtidos rodando o
pipeline completo (`extrair.py` → `carregar.py` → `publicar.py`) contra os
dados atuais da PokéAPI e dos CSVs de origem.

## Análises sobre o cadastro

### 1. Quantidade de Pokémon por tipo primário e geração

Matriz completa em `sql/consultas.sql` (108 combinações tipo×geração). A
distribuição é consistente com o esperado: nenhuma geração fica sem
representantes de tipos comuns (`normal`, `water`), e tipos historicamente
raros (`ice`, `fairy`, `dragon`) aparecem em poucas linhas por geração — sem
nenhuma contagem zerada ou anômala, o que indica que a conciliação (799/800)
não introduziu distorção sistemática por geração.

Achado notável: `fairy` aparece em Geração I e II (2 e 5 Pokémon), mesmo esse
tipo só ter sido introduzido oficialmente na Geração VI — a PokéAPI
retroaplica a reclassificação de tipo (ex.: Clefairy, Jigglypuff) às espécies
originais, e o silver herda esse dado corretamente por vir da fonte de
identidade (PokéAPI), não do CSV.

### 2. Média de cada atributo de status por tipo primário

| Maior velocidade média | Menor velocidade média | Maior resistência média (defesa + defesa especial) |
|---|---|---|
| `flying` — 102,5 | `fairy` — 48,6 | `steel` — 206,3 |
| `electric` — 84,7 | `steel` — 55,3 | `rock` — 176,3 |
| `dragon` — 83,0 | `rock` — 55,9 | `dragon` — 175,2 |

**Nenhum tipo é superior em todos os atributos simultaneamente**: `steel` lidera
resistência mas fica entre os mais lentos; `flying` lidera velocidade mas não
aparece entre os 3 mais resistentes. Isso é o padrão esperado de um jogo com
trade-offs de status por tipo, e serve de checagem adicional de que os dados
carregados fazem sentido.

## Análises sobre as batalhas

### 3. Taxa de vitórias por Pokémon (corte: ≥ 50 combates)

**10 maiores:**

| Pokémon | Tipo | Vitórias | Combates | Taxa |
|---|---|---|---|---|
| aerodactyl-mega | rock | 127 | 129 | 0,9845 |
| weavile | dark | 116 | 119 | 0,9748 |
| tornadus-therian | flying | 121 | 125 | 0,9680 |
| beedrill-mega | bug | 115 | 119 | 0,9664 |
| aerodactyl | rock | 136 | 141 | 0,9645 |
| lopunny-mega | normal | 124 | 129 | 0,9612 |
| greninja | water | 122 | 127 | 0,9606 |
| meloetta-pirouette | normal | 118 | 123 | 0,9593 |
| mewtwo-mega-y | psychic | 119 | 125 | 0,9520 |
| sharpedo-mega | water | 114 | 120 | 0,9500 |

**10 menores:**

| Pokémon | Tipo | Vitórias | Combates | Taxa |
|---|---|---|---|---|
| shuckle | bug | 0 | 135 | 0,0000 |
| silcoon | bug | 3 | 138 | 0,0217 |
| togepi | fairy | 3 | 122 | 0,0246 |
| solosis | psychic | 4 | 129 | 0,0310 |
| slugma | fire | 4 | 123 | 0,0325 |
| munna | psychic | 5 | 128 | 0,0391 |
| igglybuff | normal | 5 | 115 | 0,0435 |
| wynaut | psychic | 6 | 130 | 0,0462 |
| wooper | water | 6 | 125 | 0,0480 |
| cascoon | bug | 7 | 133 | 0,0526 |

**Interpretação:** os dois extremos são consistentes com o resultado da
análise 5 — todos os "campeões" (aerodactyl, weavile, greninja...) são
Pokémon rápidos, e todos os "lanternas" (shuckle, silcoon, togepi...) são
Pokémon lentos e/ou pré-evoluções de baixo status. `shuckle` — famoso no jogo
original por defesa altíssima e ataque/velocidade pé­ssimos — perder 135/135
combates confirma que a simulação favorece agressividade (velocidade + poder
ofensivo) sobre resistência pura.

### 4. Taxa de vitórias por tipo primário

| Tipo | Taxa | Tipo | Taxa |
|---|---|---|---|
| flying | 0,7573 | ghost | 0,4803 |
| dark | 0,6364 | water | 0,4678 |
| dragon | 0,6333 | fighting | 0,4667 |
| electric | 0,6304 | ice | 0,4407 |
| fire | 0,5803 | grass | 0,4399 |
| psychic | 0,5462 | bug | 0,4306 |
| normal | 0,5388 | poison | 0,4299 |
| ground | 0,5369 | steel | 0,4295 |
|  |  | rock | 0,4055 |
|  |  | fairy | 0,3287 |

**Tipo dominante: `flying`** (75,7%), destacado dos demais por quase 12 pontos
percentuais do segundo colocado (`dark`). Coerente com a análise 2: `flying` é
o tipo de maior velocidade média — reforça que velocidade é o fator dominante
do simulador. No outro extremo, `fairy` (32,9%) é também o tipo de menor
velocidade média, fechando a correlação.

### 5. Relação entre diferença de velocidade e vitória

| Faixa | Vitórias | Combates | Taxa |
|---|---|---|---|
| muito mais lento (diferença ≤ -50) | 1.169 | 12.445 | 0,0939 |
| mais lento (diferença -49 a -1) | 1.853 | 36.239 | 0,0511 |
| mesma velocidade (diferença 0) | 1.316 | 2.632 | 0,5000 |
| mais rápido (diferença 1 a 49) | 34.386 | 36.239 | 0,9489 |
| muito mais rápido (diferença ≥ 50) | 11.276 | 12.445 | 0,9061 |

**Interpretação:** o efeito é extremo e monotônico. Ser mais rápido, mesmo por
pouco (1 a 49 pontos), já garante 94,9% de vitórias; ser mais lento reduz a
taxa para ~5-9%. A faixa "mesma velocidade" fecha em exatamente 0,5000, o que
é esperado por simetria (todo combate empatado em velocidade contribui uma
vitória e uma derrota) e funciona como checagem de consistência do modelo, não
como achado. A conclusão prática é que, neste conjunto de batalhas simuladas,
velocidade é o fator isoladamente mais determinante do resultado — mais até
que tipo (análise 4) ou vantagem de tipo (análise 6).

### 6. Relação entre vantagem de tipo e vitória

| Multiplicador | Vitórias | Combates | Taxa |
|---|---|---|---|
| 0,00 | 1.338 | 3.234 | 0,4137 |
| 0,25 | 960 | 2.309 | 0,4158 |
| 0,50 | 9.702 | 20.519 | 0,4728 |
| 1,00 | 29.123 | 57.408 | 0,5073 |
| 2,00 | 8.128 | 15.242 | 0,5333 |
| 4,00 | 749 | 1.288 | 0,5815 |

**Interpretação:** a taxa de vitórias cresce de forma monotônica com o
multiplicador (41,4% → 41,6% → 47,3% → 50,7% → 53,3% → 58,2%) — a mecânica de
efetividade de tipo **está**, sim, refletida nos dados, mas com efeito bem
mais modesto que a velocidade (amplitude de ~17 pontos percentuais entre os
extremos do multiplicador, contra ~90 pontos na análise 5). Um resultado que
não mostrasse esse efeito também seria válido (o enunciado avisa que a
simulação pode não empregar a tabela de tipos) — aqui ele aparece, mas como
fator secundário.

### 7. Matriz de confronto entre tipos (18×18)

Matriz completa em `sql/consultas.sql` (324 células). Posições onde a taxa de
vitórias observada diverge da vantagem prevista pela matriz oficial (com pelo
menos 30 combates na célula):

| Atacante | Defensor | Taxa observada | Multiplicador oficial | Combates |
|---|---|---|---|---|
| fairy | dark | 0,2048 | 2,00 (vantagem) | 83 |
| dark | fairy | 0,7952 | 0,50 (desvantagem) | 83 |
| dragon | steel | 0,7943 | 0,50 (desvantagem) | 141 |
| ice | dragon | 0,3103 | 2,00 (vantagem) | 116 |
| electric | grass | 0,6667 | 0,50 (desvantagem) | 459 |
| fighting | fairy | 0,6613 | 0,50 (desvantagem) | 62 |
| fairy | fighting | 0,3387 | 2,00 (vantagem) | 62 |
| bug | dark | 0,3625 | 2,00 (vantagem) | 309 |

**Interpretação:** o par `fairy`↔`dark` é o mais extremo — `fairy` tem
vantagem de tipo sobre `dark` e ainda assim vence só 20,5% dos confrontos,
enquanto `dark` (em desvantagem) vence 79,5%. Isso é coerente com a análise 2
(`fairy` tem a menor velocidade média entre todos os tipos, `dark` está entre
os de melhor taxa de vitórias geral na análise 4): o status base dos Pokémon
de cada tipo pesa mais na simulação do que a vantagem de tipo isolada. O mesmo
padrão se repete em `dragon`/`steel` e `bug`/`dark` — em todos os casos, o
tipo "estatisticamente mais forte" (maior velocidade/melhor taxa geral) supera
a desvantagem de tipo prevista pela matriz oficial.

### 8. Taxa de vitórias por habitat de origem (análise proposta pelo grupo)

**Pergunta de negócio:** existe relação entre o habitat de origem de um
Pokémon e sua taxa de vitórias em combate?

| Habitat | Vitórias | Combates | Taxa |
|---|---|---|---|
| rare | 1.703 | 2.100 | 0,8110 |
| desconhecido | 85 | 108 | 0,7870 |
| rough-terrain | 1.967 | 3.737 | 0,5264 |
| grassland | 5.619 | 10.787 | 0,5209 |
| nao_aplicavel | 23.813 | 45.991 | 0,5178 |
| urban | 2.471 | 5.021 | 0,4921 |
| sea | 2.589 | 5.449 | 0,4751 |
| forest | 4.447 | 9.522 | 0,4670 |
| cave | 1.904 | 4.398 | 0,4329 |
| mountain | 2.755 | 6.413 | 0,4296 |
| waters-edge | 2.647 | 6.474 | 0,4089 |

**Interpretação:** há relação clara. O habitat `rare` — reservado pela
PokéAPI a Pokémon lendários/míticos e formas raras — tem a maior taxa de
vitórias (81,1%), bem acima de qualquer habitat "comum". A categoria
`desconhecido` (o único registro não conciliado, csv #63) também aparece com
taxa alta (78,7%), mas sobre uma amostra pequena (108 combates) — o próprio
requisito da análise 3 avisa que taxas altas com poucos combates são ruído
estatístico, então esse valor específico deve ser lido com cautela. Os
demais habitats (`waters-edge` a `rough-terrain`) ficam todos próximos de
50%, sem diferença marcante entre si — o que sugere que o habitat só importa
como *proxy* de raridade (via `rare`), não como fator independente de
desempenho em combate.
