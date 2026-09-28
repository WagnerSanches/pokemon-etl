-- As 8 análises finais.
-- 1 e 2: cadastro, direto sobre o silver (RS6 não se aplica a elas).
-- 3-8: leitura direta do gold, só com WHERE/ORDER BY/LIMIT (sem agregação
-- nem junção com o silver -- a agregação já foi materializada por publicar.py).

-- ============================================================
-- Análise 1 — Quantidade de Pokémon por tipo primário e geração
-- ============================================================
-- Matriz tipo x geração. Serve como verificação de consistência: uma
-- distribuição muito diferente do esperado indicaria falha na conciliação.
SELECT
    t.nome AS tipo_primario,
    g.nome AS geracao,
    COUNT(*) AS quantidade
FROM silver.dim_pokemon p
JOIN silver.dim_tipo t ON t.id = p.tipo_1_id
JOIN silver.dim_geracao g ON g.id = p.geracao_id
GROUP BY t.nome, g.nome
ORDER BY t.nome, g.nome;

-- ============================================================
-- Análise 2 — Média de cada atributo de status por tipo primário
-- ============================================================
SELECT
    t.nome AS tipo_primario,
    ROUND(AVG(p.hp), 1) AS hp_medio,
    ROUND(AVG(p.ataque), 1) AS ataque_medio,
    ROUND(AVG(p.defesa), 1) AS defesa_media,
    ROUND(AVG(p.ataque_especial), 1) AS ataque_especial_medio,
    ROUND(AVG(p.defesa_especial), 1) AS defesa_especial_media,
    ROUND(AVG(p.velocidade), 1) AS velocidade_media
FROM silver.dim_pokemon p
JOIN silver.dim_tipo t ON t.id = p.tipo_1_id
GROUP BY t.nome
ORDER BY t.nome;

-- Tipo de maior velocidade média:
-- SELECT t.nome, ROUND(AVG(p.velocidade),1) AS velocidade_media
-- FROM silver.dim_pokemon p JOIN silver.dim_tipo t ON t.id = p.tipo_1_id
-- GROUP BY t.nome ORDER BY velocidade_media DESC LIMIT 1;

-- Tipo de maior resistência média (defesa + defesa especial):
-- SELECT t.nome, ROUND(AVG(p.defesa + p.defesa_especial),1) AS resistencia_media
-- FROM silver.dim_pokemon p JOIN silver.dim_tipo t ON t.id = p.tipo_1_id
-- GROUP BY t.nome ORDER BY resistencia_media DESC LIMIT 1;

-- ============================================================
-- Análise 3 — Taxa de vitórias por Pokémon (10 maiores e 10 menores)
-- ============================================================
-- Corte mínimo de 50 combates (~40% da média esperada de ~125 por Pokémon,
-- ver README.md) -- ajustável aqui, sem reprocessar o pipeline.
SELECT nome, tipo_1, geracao, vitorias, combates, taxa_vitorias
FROM gold.ranking_pokemon
WHERE combates >= 50
ORDER BY taxa_vitorias DESC, combates DESC
LIMIT 10;

SELECT nome, tipo_1, geracao, vitorias, combates, taxa_vitorias
FROM gold.ranking_pokemon
WHERE combates >= 50
ORDER BY taxa_vitorias ASC, combates DESC
LIMIT 10;

-- ============================================================
-- Análise 4 — Taxa de vitórias por tipo primário
-- ============================================================
SELECT tipo, vitorias, combates, taxa_vitorias
FROM gold.taxa_vitorias_por_tipo
ORDER BY taxa_vitorias DESC;

-- ============================================================
-- Análise 5 — Relação entre diferença de velocidade e vitória
-- ============================================================
SELECT faixa, vitorias, combates, taxa_vitorias
FROM gold.taxa_vitorias_por_faixa_velocidade
ORDER BY faixa_ordem;

-- ============================================================
-- Análise 6 — Relação entre vantagem de tipo e vitória
-- ============================================================
-- Multiplicador considera os dois tipos do defensor (decisão 3): valores
-- possíveis 0, 0.25, 0.5, 1, 2, 4.
SELECT multiplicador, vitorias, combates, taxa_vitorias
FROM gold.taxa_vitorias_por_multiplicador
ORDER BY multiplicador;

-- ============================================================
-- Análise 7 — Matriz de confronto entre tipos (18 x 18)
-- ============================================================
SELECT tipo_atacante, tipo_defensor, vitorias, combates, taxa_vitorias, multiplicador_matriz
FROM gold.matriz_confronto
ORDER BY tipo_atacante, tipo_defensor;

-- Posições em que a taxa observada diverge da matriz oficial (limiar de 10
-- pontos percentuais, ajustável):
SELECT tipo_atacante, tipo_defensor, taxa_vitorias, multiplicador_matriz
FROM gold.matriz_confronto
WHERE combates >= 30
  AND (
        (multiplicador_matriz > 1 AND taxa_vitorias < 0.5)
     OR (multiplicador_matriz < 1 AND taxa_vitorias > 0.5)
  )
ORDER BY ABS(taxa_vitorias - 0.5) DESC;

-- ============================================================
-- Análise 8 (proposta pelo grupo) — Taxa de vitórias por habitat de origem
-- ============================================================
-- Pergunta: o habitat de origem do Pokémon (dimensão não usada pelas 7
-- análises anteriores) se relaciona com o desempenho em combate? Inclui as
-- categorias especiais 'nao_aplicavel' (conceito inexistente para a espécie,
-- problema 3 do enunciado) e 'desconhecido' (registro não conciliado, csv #63).
SELECT habitat, vitorias, combates, taxa_vitorias
FROM gold.taxa_vitorias_por_habitat
ORDER BY taxa_vitorias DESC;
