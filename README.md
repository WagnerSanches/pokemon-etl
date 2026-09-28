# pokemon-etl

**Integrantes:** Wagner Aguiar Sanches Garcia Sobrinho

Pipeline ETL com arquitetura medalhão (EP01 — Ciência de Dados) que extrai a
PokéAPI e dois CSVs de batalhas, concilia e modela em PostgreSQL (esquema
estrela) e publica agregados prontos para consulta.

## 1. Procedimento de execução

Pré-requisitos: MongoDB e PostgreSQL em execução (máquina virtual da
disciplina ou instalação local), Python 3, banco `pokedex` já criado no
PostgreSQL.

```bash
export MONGO_URI="mongodb://usuario:senha@host:27017/?authSource=admin"   # ajustar ao ambiente
export POSTGRES_DSN="postgresql://usuario:senha@host:5432/pokedex"        # ajustar ao ambiente

pip install -r requirements.txt

python extrair.py           # fontes -> bronze (MongoDB pokedex_bronze)
python carregar.py          # bronze -> silver (PostgreSQL schema silver)
python publicar.py          # silver -> gold (PostgreSQL schema gold)
```

Sem as variáveis de ambiente acima, os scripts usam por padrão
`mongodb://pokemon:pokemon@localhost:27017/?authSource=admin` e
`postgresql://pokemon:pokemon@localhost:5432/pokedex`.

As consultas finais estão em `sql/consultas.sql` (rodar com `psql` ou qualquer
cliente SQL apontando para o banco `pokedex`).

Para validar do zero (o mesmo cenário da correção — duas execuções
consecutivas a partir de bancos vazios):

```bash
# limpar/recriar o banco pokedex_bronze (MongoDB) e o banco pokedex (PostgreSQL)
python extrair.py && python carregar.py && python publicar.py
python extrair.py && python carregar.py && python publicar.py   # 2a execução: não duplica nada
```

## 2. Por que MongoDB na camada bronze

O JSON retornado por `/pokemon/{id}` e `/pokemon-species/{id}` é
profundamente aninhado e heterogêneo entre registros: `varieties[]` tem
tamanho variável por espécie (de 1 a mais de 15 formas), `stats[]` e
`types[]` são listas de sub-objetos, e campos como `damage_relations` têm seis
listas de tamanho variável. Forçar esse formato em tabelas relacionais na
camada bronze exigiria decidir um esquema de normalização *antes* de saber
quais decisões de modelagem o silver vai tomar — exatamente o acoplamento que
a arquitetura medalhão evita. Um banco de documentos aceita o JSON como veio,
sem achatar nem escolher chaves estrangeiras precocemente, preservando a
capacidade de reprocessar o silver com outra modelagem sem nova consulta à
API.

## 3. Grão da fato e esquema estrela

**Grão de `silver.fato_confronto`: uma linha representa a participação de um
Pokémon em um combate** (portanto duas linhas por combate, uma por lado).

```
                         ┌──────────────────┐
                         │ silver.dim_geracao│
                         └─────────┬────────┘
                                   │
  ┌────────────────────┐   ┌──────┴───────────┐   ┌────────────────────┐
  │ silver.dim_pokemon  ├───┤                  ├───┤ silver.dim_pokemon  │
  │  (papel: pokemon_id)│   │ silver.fato_     │   │ (papel: oponente_id)│
  └──────────┬──────────┘   │  confronto       │   └──────────┬──────────┘
             │              │ (1 linha =       │              │
             │              │  1 participação) │              │
             │              └──────┬───────────┘              │
             │                     │                           │
             └─────────┬───────────┴─────────────┬─────────────┘
                        │                          │
                 silver.dim_tipo          silver.efetividade_tipo
                (tipo_1_id, tipo_2_id)    (tabela ponte 18×18,
                                           consultada por JOIN a
                                           partir de dim_tipo)
```

`dim_pokemon` é referenciada duas vezes pela fato, em papéis distintos
(`pokemon_id` = "eu", `oponente_id` = "quem enfrentei") — dimensão papel
(decisão 4).

## 4. As 6 decisões de modelagem

1. **Grão da fato: 1 linha por participação (100.000 linhas), não 1 por
   combate.** Custo: dobra o volume da fato frente à alternativa de 1
   linha/combate. Ganho: toda taxa de vitórias (análises 3-8) vira uma média
   simples de uma coluna booleana (`AVG(venceu)`), sem localizar o mesmo
   Pokémon em duas colunas distintas nem risco de dupla contagem. A análise 7
   (matriz de confronto) exige orientação pelo vencedor — grão de
   participação entrega isso diretamente, uma linha por célula alimentada.

2. **Diferença de velocidade materializada em `fato_confronto`**
   (`diferenca_velocidade`), calculada na carga. Custo: uma coluna inteira a
   mais em 100.000 linhas. Ganho: a análise 5 não precisa de dois `JOIN` com
   `dim_pokemon` em cada consulta — é a mesma lógica já aplicada à métrica de
   vitória.

3. **Efetividade de tipos como tabela ponte** (`silver.efetividade_tipo`, 324
   linhas: 18 tipos atacantes × 18 defensores). Rejeitei "coluna computada na
   fato" porque fixaria o multiplicador no momento da carga; com a tabela
   ponte, um defensor de dois tipos é resolvido multiplicando dois `JOIN`
   (`e1.multiplicador * COALESCE(e2.multiplicador, 1.0)`) dentro do próprio
   `publicar.py`, sem reprocessar o silver. Custo: a consulta que popula o
   gold da análise 6 precisa de dois `JOIN` com a mesma tabela ponte, mas isso
   acontece uma vez (na publicação), não a cada leitura do gold.

4. **Dimensão papel para o oponente**: `fato_confronto.pokemon_id` e
   `oponente_id` referenciam a mesma `dim_pokemon`, em papéis diferentes.
   Alternativa rejeitada (duplicar a dimensão em `dim_pokemon_a`/
   `dim_pokemon_b`) duplicaria a manutenção de 800 linhas de cadastro sem
   ganho — o papel já está no nome da coluna FK.

5. **Atributos de status apenas em `dim_pokemon`** (não duplicados na fato),
   com a exceção já coberta pela decisão 2 (`diferenca_velocidade`). Custo de
   duplicar os 6 status em 100.000 linhas não se justifica: a análise 2 (que
   precisa da média por tipo) é uma consulta de cadastro sobre a dimensão, e a
   única comparação de combate que os requisitos exigem (velocidade) já está
   materializada.

6. **Categoria de raridade derivada na carga** (`categoria_raridade` em
   `dim_pokemon`: `comum`/`lendario`/`mitico`/`baby`, resolvida a partir de
   `is_legendary`/`is_mythical`/`is_baby` uma única vez em `carregar.py`).
   Custo: qualquer mudança de critério exige reprocessar o silver. Ganho:
   nenhuma consulta futura repete a expressão condicional — inclusive
   consultas ad hoc fora de `consultas.sql` (verificação da seção 6 do
   enunciado) já encontram a categoria pronta.

### Tipos extras da PokéAPI (`stellar`, `unknown`, `shadow`)

Extraídos na bronze (fidelidade total: `/type/` retorna 21, não filtramos a
fonte). Excluídos do silver: os três têm `damage_relations` vazio nos dados
retornados (confirmado ao carregar `sql/silver.sql` — nenhum dos 800 Pokémon
do CSV usa esses tipos como `Type 1`/`Type 2`) e não existem no jogo que
originou `combats.csv`. Incluí-los em `dim_tipo` só adicionaria linhas nunca
referenciadas por `fato_confronto`.

## 5. Análise proposta pelo grupo (8ª análise)

**Pergunta:** existe relação entre o habitat de origem de um Pokémon e sua
taxa de vitórias em combate?

**Capacidade exigida que as 7 obrigatórias não exigem:** usa `habitat`, um
atributo de `dim_pokemon` que nenhuma das análises 1-7 toca. Também é a única
análise que materializa o tratamento do **problema 3** (habitat nulo =
conceito inaplicável para espécies pós-FireRed/LeafGreen): a categoria
`nao_aplicavel` aparece como qualquer outra no `GROUP BY`, nunca como ausência
silenciosa de linha. A categoria `desconhecido` cumpre o mesmo papel para o
registro não conciliado (csv #63, problema 2) — evidenciando que os dois
problemas, embora pareçam o mesmo NULL, viram categorias semanticamente
distintas no modelo.

**Relevância:** se o habitat correlaciona com desempenho, é sinal de que a
raridade/geração de origem (que tende a concentrar Pokémon fortes em
habitats como `rare`) atravessa a dimensão de cadastro para a de combate —
teste de que o modelo dimensional generaliza além das 7 perguntas para as
quais foi desenhado.

Tabela própria: `gold.taxa_vitorias_por_habitat`. Resultado e interpretação
no `RELATORIO.md`.

## 6. Idempotência por camada

- **Bronze**: cada documento usa `_id` = chave natural (`pokemon/25`,
  `combate/12345`, ...) e é gravado com `replace_one(..., upsert=True)`
  (não `update_one` com `$set` — esse operador interpretaria `.` em nomes de
  campo como caminho aninhado, corrompendo colunas como `Sp. Atk` do CSV).
  Reexecutar não duplica documentos, e o cache em `dados_brutos/` garante
  zero requisições à PokéAPI na 2ª execução.
- **Silver**: toda dimensão tem `UNIQUE` na chave natural
  (`dim_geracao.numero`, `dim_tipo.nome`, `dim_pokemon.csv_numero`) e é
  populada com `INSERT ... ON CONFLICT ... DO UPDATE`. A fato usa
  `UNIQUE (combate_numero, papel)` com o mesmo padrão de upsert — o
  `combate_numero` é dimensão degenerada (número da linha do
  `combats.csv`), não descreve o Pokémon, só identifica o combate de origem
  de forma estável entre execuções.
- **Gold**: cada tabela é esvaziada com `TRUNCATE` e repovoada com
  `INSERT ... SELECT` dentro da mesma transação — o estado final independe
  de quantas vezes `publicar.py` roda.

## 7. Decisões de projeto não especificadas pelo enunciado

- **Driver `psycopg` (v3) com o extra `[binary]`** — evita depender de
  `libpq-dev` instalado no sistema para compilar a extensão C; ainda é
  exatamente o driver `psycopg` citado no R11, só empacotado com o binário
  pré-compilado.
- **Faixas de diferença de velocidade (análise 5)**: 5 faixas simétricas em
  torno de 0, com limiar de 50 pontos (`<= -50`, `-49 a -1`, `0`, `1 a 49`,
  `>= 50`). 50 foi escolhido por ser da mesma ordem de grandeza da maior
  velocidade base observada (~180), produzindo faixas com volume comparável
  de combates em vez de uma cauda vazia.
- **Corte mínimo de 50 combates na análise 3**: a média é de ~125
  combates/Pokémon (50.000 combates × 2 participações / ~800 Pokémon); 50
  filtra a amostra claramente insuficiente sem descartar Pokémon com
  participação abaixo da média. Materializado como coluna (`combates`) em
  `gold.ranking_pokemon`, não como filtro na carga — o corte é ajustável só
  mudando o `WHERE` de `consultas.sql`.
- **Nomes de tipo em inglês minúsculo** (`grass`, `fire`, ...), iguais aos da
  PokéAPI e do `pokemon.csv` (após normalização de caixa) — evita uma tabela
  de tradução sem necessidade, já que são nomes amplamente reconhecíveis e o
  próprio enunciado os usa em português técnico sem tradução.
