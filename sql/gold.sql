-- Camada gold: agregados já materializados no grão de cada pergunta.
-- Populada só por publicar.py via INSERT ... SELECT a partir do silver --
-- nenhuma linha aqui é escrita por consulta manual.

CREATE SCHEMA IF NOT EXISTS gold;

-- Análise 3: taxa de vitórias por Pokémon. O corte mínimo de combates é
-- decisão de consulta (WHERE combates >= N em consultas.sql), não de carga --
-- por isso qtd_combates fica materializada como coluna, e não como filtro.
CREATE TABLE IF NOT EXISTS gold.ranking_pokemon (
    pokemon_id     INT PRIMARY KEY,
    nome           TEXT    NOT NULL,
    tipo_1         TEXT    NOT NULL,
    geracao        TEXT    NOT NULL,
    vitorias       INT     NOT NULL,
    combates       INT     NOT NULL,
    taxa_vitorias  NUMERIC NOT NULL
);

-- Análise 4: taxa de vitórias por tipo primário.
CREATE TABLE IF NOT EXISTS gold.taxa_vitorias_por_tipo (
    tipo           TEXT PRIMARY KEY,
    vitorias       INT     NOT NULL,
    combates       INT     NOT NULL,
    taxa_vitorias  NUMERIC NOT NULL
);

-- Análise 5: efeito da diferença de velocidade. faixa_ordem guarda a ordem de
-- leitura das faixas (não alfabética) para ORDER BY na consulta final.
CREATE TABLE IF NOT EXISTS gold.taxa_vitorias_por_faixa_velocidade (
    faixa          TEXT PRIMARY KEY,
    faixa_ordem    INT     NOT NULL,
    vitorias       INT     NOT NULL,
    combates       INT     NOT NULL,
    taxa_vitorias  NUMERIC NOT NULL
);

-- Análise 6: efeito da vantagem de tipo. multiplicador considera os dois
-- tipos do defensor (decisão 3) -- valores possíveis 0, 0.25, 0.5, 1, 2, 4.
CREATE TABLE IF NOT EXISTS gold.taxa_vitorias_por_multiplicador (
    multiplicador  NUMERIC PRIMARY KEY,
    vitorias       INT     NOT NULL,
    combates       INT     NOT NULL,
    taxa_vitorias  NUMERIC NOT NULL
);

-- Análise 7: matriz de confronto 18x18. multiplicador_matriz é o valor da
-- matriz tipo-a-tipo (silver.efetividade_tipo, só tipo primário) trazido para
-- comparação direta com a taxa de vitórias observada, sem recalcular na
-- consulta final.
CREATE TABLE IF NOT EXISTS gold.matriz_confronto (
    tipo_atacante        TEXT NOT NULL,
    tipo_defensor        TEXT NOT NULL,
    vitorias             INT     NOT NULL,
    combates             INT     NOT NULL,
    taxa_vitorias        NUMERIC NOT NULL,
    multiplicador_matriz NUMERIC NOT NULL,
    PRIMARY KEY (tipo_atacante, tipo_defensor)
);

-- Análise 8 (proposta pelo grupo): taxa de vitórias por habitat de origem do
-- Pokémon. Usa uma dimensão (habitat) não tocada pelas 7 análises anteriores,
-- e materializa o tratamento do problema 3 (conceito inaplicável) --
-- 'nao_aplicavel' e 'desconhecido' aparecem como categorias de habitat como
-- outra qualquer, nunca como ausência silenciosa de linha.
CREATE TABLE IF NOT EXISTS gold.taxa_vitorias_por_habitat (
    habitat        TEXT PRIMARY KEY,
    vitorias       INT     NOT NULL,
    combates       INT     NOT NULL,
    taxa_vitorias  NUMERIC NOT NULL
);
