import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg

POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://pokemon:pokemon@localhost:5432/pokedex")
SQL_GOLD = Path("sql/gold.sql")

TABELAS_GOLD = {
    "ranking_pokemon": """
        INSERT INTO gold.ranking_pokemon (pokemon_id, nome, tipo_1, geracao, vitorias, combates, taxa_vitorias)
        SELECT
            p.id, p.nome, t.nome, g.nome,
            SUM(CASE WHEN f.venceu THEN 1 ELSE 0 END),
            COUNT(*),
            ROUND(AVG(CASE WHEN f.venceu THEN 1.0 ELSE 0.0 END), 4)
        FROM silver.fato_confronto f
        JOIN silver.dim_pokemon p ON p.id = f.pokemon_id
        JOIN silver.dim_tipo t ON t.id = p.tipo_1_id
        JOIN silver.dim_geracao g ON g.id = p.geracao_id
        GROUP BY p.id, p.nome, t.nome, g.nome
    """,
    "taxa_vitorias_por_tipo": """
        INSERT INTO gold.taxa_vitorias_por_tipo (tipo, vitorias, combates, taxa_vitorias)
        SELECT
            t.nome,
            SUM(CASE WHEN f.venceu THEN 1 ELSE 0 END),
            COUNT(*),
            ROUND(AVG(CASE WHEN f.venceu THEN 1.0 ELSE 0.0 END), 4)
        FROM silver.fato_confronto f
        JOIN silver.dim_pokemon p ON p.id = f.pokemon_id
        JOIN silver.dim_tipo t ON t.id = p.tipo_1_id
        GROUP BY t.nome
    """,
    "taxa_vitorias_por_faixa_velocidade": """
        INSERT INTO gold.taxa_vitorias_por_faixa_velocidade (faixa, faixa_ordem, vitorias, combates, taxa_vitorias)
        SELECT
            faixa, faixa_ordem,
            SUM(CASE WHEN venceu THEN 1 ELSE 0 END),
            COUNT(*),
            ROUND(AVG(CASE WHEN venceu THEN 1.0 ELSE 0.0 END), 4)
        FROM (
            SELECT
                venceu,
                CASE
                    WHEN diferenca_velocidade <= -50 THEN 'muito mais lento (diferença <= -50)'
                    WHEN diferenca_velocidade <= -1 THEN 'mais lento (diferença -49 a -1)'
                    WHEN diferenca_velocidade = 0 THEN 'mesma velocidade (diferença 0)'
                    WHEN diferenca_velocidade <= 49 THEN 'mais rápido (diferença 1 a 49)'
                    ELSE 'muito mais rápido (diferença >= 50)'
                END AS faixa,
                CASE
                    WHEN diferenca_velocidade <= -50 THEN 1
                    WHEN diferenca_velocidade <= -1 THEN 2
                    WHEN diferenca_velocidade = 0 THEN 3
                    WHEN diferenca_velocidade <= 49 THEN 4
                    ELSE 5
                END AS faixa_ordem
            FROM silver.fato_confronto
        ) faixas
        GROUP BY faixa, faixa_ordem
    """,
    "taxa_vitorias_por_multiplicador": """
        INSERT INTO gold.taxa_vitorias_por_multiplicador (multiplicador, vitorias, combates, taxa_vitorias)
        SELECT
            multiplicador,
            SUM(CASE WHEN venceu THEN 1 ELSE 0 END),
            COUNT(*),
            ROUND(AVG(CASE WHEN venceu THEN 1.0 ELSE 0.0 END), 4)
        FROM (
            SELECT
                f.venceu,
                e1.multiplicador * COALESCE(e2.multiplicador, 1.0) AS multiplicador
            FROM silver.fato_confronto f
            JOIN silver.dim_pokemon eu ON eu.id = f.pokemon_id
            JOIN silver.dim_pokemon oponente ON oponente.id = f.oponente_id
            JOIN silver.efetividade_tipo e1
                ON e1.atacante_id = eu.tipo_1_id AND e1.defensor_id = oponente.tipo_1_id
            LEFT JOIN silver.efetividade_tipo e2
                ON e2.atacante_id = eu.tipo_1_id AND e2.defensor_id = oponente.tipo_2_id
        ) confrontos
        GROUP BY multiplicador
    """,
    "matriz_confronto": """
        INSERT INTO gold.matriz_confronto (tipo_atacante, tipo_defensor, vitorias, combates, taxa_vitorias, multiplicador_matriz)
        SELECT
            ta.nome, td.nome,
            SUM(CASE WHEN f.venceu THEN 1 ELSE 0 END),
            COUNT(*),
            ROUND(AVG(CASE WHEN f.venceu THEN 1.0 ELSE 0.0 END), 4),
            e.multiplicador
        FROM silver.fato_confronto f
        JOIN silver.dim_pokemon eu ON eu.id = f.pokemon_id
        JOIN silver.dim_pokemon oponente ON oponente.id = f.oponente_id
        JOIN silver.dim_tipo ta ON ta.id = eu.tipo_1_id
        JOIN silver.dim_tipo td ON td.id = oponente.tipo_1_id
        JOIN silver.efetividade_tipo e ON e.atacante_id = ta.id AND e.defensor_id = td.id
        GROUP BY ta.nome, td.nome, e.multiplicador
    """,
    # Análise 8 (proposta pelo grupo): taxa de vitórias por habitat de
    # origem -- dimensão não tocada pelas análises 3-7.
    "taxa_vitorias_por_habitat": """
        INSERT INTO gold.taxa_vitorias_por_habitat (habitat, vitorias, combates, taxa_vitorias)
        SELECT
            p.habitat,
            SUM(CASE WHEN f.venceu THEN 1 ELSE 0 END),
            COUNT(*),
            ROUND(AVG(CASE WHEN f.venceu THEN 1.0 ELSE 0.0 END), 4)
        FROM silver.fato_confronto f
        JOIN silver.dim_pokemon p ON p.id = f.pokemon_id
        GROUP BY p.habitat
    """,
}


def executar_ddl(conn):
    with conn.cursor() as cur:
        cur.execute(SQL_GOLD.read_text(encoding="utf-8"))
    conn.commit()


def repovoar(conn):
    with conn.cursor() as cur:
        for tabela, consulta in TABELAS_GOLD.items():
            cur.execute(f"TRUNCATE TABLE gold.{tabela}")
            cur.execute(consulta)
    conn.commit()


def main():
    conn = psycopg.connect(POSTGRES_DSN)

    executar_ddl(conn)
    repovoar(conn)

    momento = datetime.now(timezone.utc).isoformat()
    with conn.cursor() as cur:
        for tabela in TABELAS_GOLD:
            cur.execute(f"SELECT count(*) FROM gold.{tabela}")
            print(f"gold.{tabela}: {cur.fetchone()[0]} linhas (carregado em {momento})")

    conn.close()


if __name__ == "__main__":
    main()
