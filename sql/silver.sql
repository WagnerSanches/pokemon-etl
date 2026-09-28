-- Camada silver: esquema estrela.
-- Grão da tabela fato: 1 linha = 1 participação de um Pokémon em um combate
-- (2 linhas por combate, uma por lado). Ver decisão 1 no README.md.

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.dim_geracao (
    id      SERIAL PRIMARY KEY,
    numero  INT  NOT NULL UNIQUE,
    nome    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.dim_tipo (
    id         SERIAL PRIMARY KEY,
    nome       TEXT NOT NULL UNIQUE,
    pokeapi_id INT  NOT NULL UNIQUE
);

-- Tabela ponte: multiplicador de dano de cada tipo atacante contra cada tipo
-- defensor (decisão 3). 18 x 18 = 324 linhas. Um defensor com dois tipos exige
-- consultar esta tabela duas vezes e multiplicar os dois fatores.
CREATE TABLE IF NOT EXISTS silver.efetividade_tipo (
    atacante_id  INT     NOT NULL REFERENCES silver.dim_tipo (id),
    defensor_id  INT     NOT NULL REFERENCES silver.dim_tipo (id),
    multiplicador NUMERIC(3, 2) NOT NULL,
    PRIMARY KEY (atacante_id, defensor_id)
);

-- Natural keys da origem (pokedex_numero, csv_numero) são atributos, nunca
-- PK/FK (RS3) -- constituem o registro auditável da conciliação (R4).
--
-- Membro especial (R5): o registro sem nome do pokemon.csv (csv #63, ver
-- conciliacao.csv) não pôde ser conciliado por nome com a PokéAPI, mas
-- participa de combates -- entra como uma linha normal desta dimensão,
-- construída só com os atributos que o CSV fornece (pokedex_numero NULL,
-- nome_pokeapi NULL), para que nenhum combate seu seja descartado.
--
-- Herança de atributos de espécie (geração, habitat, raridade) para formas
-- alternativas: carregar.py lê o campo species.url de /pokemon/{id} e herda
-- os atributos da espécie correspondente, conforme exigido na seção 1.4.
CREATE TABLE IF NOT EXISTS silver.dim_pokemon (
    id                  SERIAL PRIMARY KEY,
    csv_numero          INT  NOT NULL UNIQUE,
    pokedex_numero      INT,
    nome                TEXT NOT NULL,
    nome_pokeapi        TEXT,
    tipo_1_id           INT  NOT NULL REFERENCES silver.dim_tipo (id),
    tipo_2_id           INT  REFERENCES silver.dim_tipo (id),
    geracao_id          INT  NOT NULL REFERENCES silver.dim_geracao (id),
    categoria_raridade  TEXT NOT NULL,
    -- 'nao_aplicavel': conceito de habitat não existe para a espécie (problema 3,
    -- conceito inaplicável). 'desconhecido': espécie não identificada pela
    -- conciliação (problema 2, dado ausente). Nunca NULL -- distingue as duas
    -- naturezas de ausência em vez de tratá-las da mesma forma.
    habitat             TEXT NOT NULL,
    hp                  INT  NOT NULL,
    ataque              INT  NOT NULL,
    defesa              INT  NOT NULL,
    ataque_especial     INT  NOT NULL,
    defesa_especial     INT  NOT NULL,
    velocidade          INT  NOT NULL,
    eh_forma_alternativa BOOLEAN NOT NULL
);

-- combate_numero é dimensão degenerada (o número da linha de combats.csv, 1 a
-- 50000): não descreve o Pokémon nem tem atributos próprios, apenas
-- identifica de forma estável o combate de origem para permitir upsert
-- idempotente (R7) sem duplicar as 100.000 linhas na 2a execução.
CREATE TABLE IF NOT EXISTS silver.fato_confronto (
    id                     BIGSERIAL PRIMARY KEY,
    combate_numero         INT     NOT NULL,
    papel                  TEXT    NOT NULL CHECK (papel IN ('primeiro', 'segundo')),
    pokemon_id             INT     NOT NULL REFERENCES silver.dim_pokemon (id),
    oponente_id            INT     NOT NULL REFERENCES silver.dim_pokemon (id),
    venceu                 BOOLEAN NOT NULL,
    -- decisão 2: diferença de velocidade materializada na fato (velocidade
    -- própria - velocidade do oponente), evita 2 JOINs em toda consulta da
    -- análise 5.
    diferenca_velocidade   INT     NOT NULL,
    UNIQUE (combate_numero, papel)
);

CREATE INDEX IF NOT EXISTS idx_fato_confronto_pokemon ON silver.fato_confronto (pokemon_id);
CREATE INDEX IF NOT EXISTS idx_fato_confronto_oponente ON silver.fato_confronto (oponente_id);
