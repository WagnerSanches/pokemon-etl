# pokemon-etl

**Integrantes:** Wagner Aguiar Sanches Garcia Sobrinho

Pipeline ETL com arquitetura medalhão (EP01, Ciência de Dados): extrai a
PokéAPI e dois CSVs de batalhas, concilia e modela em PostgreSQL (esquema
estrela), publica agregados para consulta.

## 1. Procedimento de execução

Pré-requisitos: MongoDB e PostgreSQL rodando (VM da disciplina ou local),
Python 3, banco `pokedex` já criado.

```bash
export MONGO_URI="mongodb://usuario:senha@host:27017/?authSource=admin"   # ajustar ao ambiente
export POSTGRES_DSN="postgresql://usuario:senha@host:5432/pokedex"        # ajustar ao ambiente

pip install -r requirements.txt

python extrair.py           # fontes -> bronze (MongoDB pokedex_bronze)
python carregar.py          # bronze -> silver (PostgreSQL schema silver)
python publicar.py          # silver -> gold (PostgreSQL schema gold)
```

Sem essas variáveis, os scripts caem no padrão
`mongodb://pokemon:pokemon@localhost:27017/?authSource=admin` e
`postgresql://pokemon:pokemon@localhost:5432/pokedex`.

Consultas finais em `sql/consultas.sql`.

Para testar idempotência (bancos vazios, dois ciclos seguidos):

```bash
python extrair.py && python carregar.py && python publicar.py
python extrair.py && python carregar.py && python publicar.py   # não duplica nada
```

## 2. Por que MongoDB na bronze

O JSON da PokéAPI é aninhado e heterogêneo: cada espécie pode ter só uma
forma ou mais de quinze, os atributos de combate vêm em listas de
sub-objetos, e a matriz de efetividade de tipos é composta por seis listas
de tamanho variável. Guardar isso em tabelas relacionais exigiria decidir a
normalização antes de saber o que a camada seguinte vai precisar. É o
acoplamento que a arquitetura medalhão evita. Um banco de documentos aceita
o JSON como veio; o modelo relacional pode ser refeito sem nova consulta à
API.

## 3. Grão da fato e esquema estrela

**Grão: uma linha representa a participação de um Pokémon em um combate**
(duas linhas por combate).

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

A dimensão de Pokémon é referenciada duas vezes pela fato, em papéis
diferentes: dimensão papel.

## 4. As 6 decisões de modelagem

1. **Grão: uma linha por participação** (100.000 linhas), não por combate.
   Dobra o volume, mas reduz toda taxa de vitórias a uma média simples de
   uma única coluna, sem duplicar o mesmo Pokémon em duas colunas. A matriz
   de confronto (análise 7) sai direto daí, orientada pelo vencedor.

2. **Diferença de velocidade materializada na fato.** Uma coluna a mais em
   100.000 linhas, mas evita duas junções extras em toda consulta da
   análise 5.

3. **Efetividade de tipos como tabela ponte** (324 linhas: 18 tipos
   atacantes por 18 defensores). Descartei coluna computada na fato: ela
   fixaria o multiplicador no momento da carga. Defensor com dois tipos:
   multiplica os dois fatores uma vez, na hora de publicar o gold.

4. **Oponente como dimensão papel.** A fato aponta duas vezes pra mesma
   dimensão de Pokémon, em papéis diferentes. Duplicar essa dimensão
   dobraria a manutenção de 800 linhas de cadastro sem ganho nenhum.

5. **Status só na dimensão de Pokémon**, sem duplicar na fato (exceto a
   diferença de velocidade da decisão 2). A análise 2 é sobre cadastro, não
   sobre combate, e não precisa da fato.

6. **Categoria de raridade derivada na carga** (comum, lendário, mítico,
   baby, a partir dos indicadores booleanos que a PokéAPI já fornece).
   Custa reprocessar o silver se o critério mudar, mas nenhuma consulta
   repete a lógica de classificação depois.

### Tipos extras (`stellar`, `unknown`, `shadow`)

Ficam na bronze, por fidelidade: a API retorna 21 tipos, e não filtro a
fonte. Saem do modelo relacional: não têm relação de dano nos dados
retornados, e nenhum dos 800 Pokémon do CSV usa esses tipos.

## 5. Análise proposta (8ª)

**Pergunta:** o habitat de origem se relaciona com a taxa de vitórias?

Usa o habitat, atributo que nenhuma das 7 análises obrigatórias toca.
Também é a única que mostra como o modelo trata o habitat nulo (inaplicável
pra espécies mais recentes): essa ausência vira uma categoria própria na
contagem, nunca some. O único registro não conciliado com a PokéAPI recebe
o mesmo tratamento, com sua própria categoria.

Relevância: se o habitat se relaciona com desempenho, é sinal de que
raridade/geração de origem atravessa do cadastro pro combate.

Tabela própria no gold. Resultado no RELATORIO.md.

## 6. Idempotência por camada

- **Bronze**: cada documento é identificado pela própria chave de origem, e
  a gravação sempre substitui o documento inteiro em vez de mesclar campo a
  campo, evitando corromper campos com ponto no nome, como os do CSV
  original. O cache local evita repetir requisições à PokéAPI.
- **Silver**: cada dimensão tem restrição de unicidade na chave de origem,
  e a carga atualiza em vez de duplicar quando encontra conflito. A fato
  segue o mesmo princípio, usando o número do combate como identificador
  estável.
- **Gold**: cada tabela é esvaziada e repovoada inteira a cada execução,
  dentro da mesma transação.

## 7. Decisões de projeto fora do enunciado

- **Driver de PostgreSQL com binário pré-compilado**, pra não depender de
  bibliotecas de sistema pra compilar a extensão C.
- **Faixas de velocidade (análise 5)**: 5 faixas simétricas, corte em 50,
  mesma ordem de grandeza da maior velocidade base (~180).
- **Corte de 50 combates (análise 3)**: média é ~125/Pokémon; 50 filtra
  amostra insuficiente sem cortar quem está abaixo da média. Fica como
  coluna na tabela de ranking, ajustável na consulta final sem reprocessar
  o pipeline.
- **Nomes de tipo em inglês minúsculo**: iguais à PokéAPI e ao CSV, sem
  tabela de tradução.
