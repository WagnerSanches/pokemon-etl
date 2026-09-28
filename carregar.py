import csv
import os
import re
import unicodedata
from pathlib import Path

import psycopg
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://pokemon:pokemon@localhost:27017/?authSource=admin")
MONGO_DB = "pokedex_bronze"
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://pokemon:pokemon@localhost:5432/pokedex")

SQL_SILVER = Path("sql/silver.sql")
CONCILIACAO_CSV = Path("conciliacao.csv")

NUMERO_ROMANO = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}
NOME_GERACAO = {
    1: "Geração I (Kanto)",
    2: "Geração II (Johto)",
    3: "Geração III (Hoenn)",
    4: "Geração IV (Sinnoh)",
    5: "Geração V (Unova)",
    6: "Geração VI (Kalos)",
}

OVERRIDES_NOME = {
    "DeoxysAttack Forme": "deoxys-attack", 
    "Kyurem Black Kyurem": "kyurem-black", 
    "Kyurem White Kyurem": "kyurem-white",
    "Hoopa Confined": "hoopa", 
    "Zygarde Half Forme": "zygarde-50", 
}
SUFIXOS_FORMA = (" Forme", " Mode", " Size", " Cloak")


def slug_basico(nome):
    nome = nome.replace("♀", " f").replace("♂", " m")
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = nome.replace("'", "").replace(".", "")
    nome = re.sub(r"[^A-Za-z0-9]+", "-", nome).strip("-").lower()
    return nome


def normalizar_nome_csv(nome):
    if nome in OVERRIDES_NOME:
        return OVERRIDES_NOME[nome]
    if nome != "Rotom" and nome.endswith(" Rotom"):
        return "rotom-" + slug_basico(nome[: -len(" Rotom")])
    if nome.startswith("Mega "):
        resto = nome[len("Mega "):]
        partes = resto.rsplit(" ", 1)
        if len(partes) == 2 and len(partes[1]) <= 2:
            base, sufixo = partes
            return f"{slug_basico(base)}-mega-{sufixo.lower()}"
        return f"{slug_basico(resto)}-mega"
    if nome.startswith("Primal "):
        return f"{slug_basico(nome[len('Primal '):])}-primal"
    for sufixo in SUFIXOS_FORMA:
        if nome.endswith(sufixo):
            return slug_basico(nome[: -len(sufixo)])
    return slug_basico(nome)


def localizar_pokemon(db, nome_csv):
    """Retorna (doc_pokemon, doc_especie) ou (None, None) se não conciliado."""
    slug = normalizar_nome_csv(nome_csv)

    pokemon = db.pokemon.find_one({"name": slug})
    if pokemon is None:
        especie_candidata = db.especies.find_one({"name": slug})
        if especie_candidata is not None:
            variedade_default = next(
                (v for v in especie_candidata["varieties"] if v["is_default"]), None
            )
            if variedade_default is not None:
                pokemon = db.pokemon.find_one({"name": variedade_default["pokemon"]["name"]})

    if pokemon is None:
        return None, None

    especie_id = int(pokemon["species"]["url"].rstrip("/").rsplit("/", 1)[-1])
    especie = db.especies.find_one({"_id": f"especie/{especie_id}"})
    return pokemon, especie


def categoria_raridade_de(especie):
    if especie["is_baby"]:
        return "baby"
    if especie["is_mythical"]:
        return "mitico"
    if especie["is_legendary"]:
        return "lendario"
    return "comum"


def habitat_de(especie):
    return especie["habitat"]["name"] if especie["habitat"] else "nao_aplicavel"


def numero_geracao_de(especie):
    return NUMERO_ROMANO[especie["generation"]["name"].rsplit("-", 1)[-1]]


def stats_de(pokemon):
    valores = {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]}
    return {
        "hp": valores["hp"],
        "ataque": valores["attack"],
        "defesa": valores["defense"],
        "ataque_especial": valores["special-attack"],
        "defesa_especial": valores["special-defense"],
        "velocidade": valores["speed"],
    }


def tipos_de(pokemon):
    ordenado = sorted(pokemon["types"], key=lambda t: t["slot"])
    nomes = [t["type"]["name"] for t in ordenado]
    return nomes[0], (nomes[1] if len(nomes) > 1 else None)


def executar_ddl(conn):
    with conn.cursor() as cur:
        cur.execute(SQL_SILVER.read_text(encoding="utf-8"))
    conn.commit()


def carregar_dim_geracao(conn):
    with conn.cursor() as cur:
        for numero, nome in NOME_GERACAO.items():
            cur.execute(
                """
                INSERT INTO silver.dim_geracao (numero, nome) VALUES (%s, %s)
                ON CONFLICT (numero) DO UPDATE SET nome = EXCLUDED.nome
                """,
                (numero, nome),
            )
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT numero, id FROM silver.dim_geracao")
        return dict(cur.fetchall())


def carregar_dim_tipo(conn, db):
    tipo_por_nome = {}
    tipo_por_pokeapi_id = {}
    with conn.cursor() as cur:
        for tipo_id in range(1, 19):
            tipo = db.tipos.find_one({"_id": f"tipo/{tipo_id}"})
            nome = tipo["name"]
            cur.execute(
                """
                INSERT INTO silver.dim_tipo (nome, pokeapi_id) VALUES (%s, %s)
                ON CONFLICT (nome) DO UPDATE SET pokeapi_id = EXCLUDED.pokeapi_id
                RETURNING id
                """,
                (nome, tipo_id),
            )
            surrogate_id = cur.fetchone()[0]
            tipo_por_nome[nome] = surrogate_id
            tipo_por_pokeapi_id[tipo_id] = surrogate_id
    conn.commit()
    return tipo_por_nome, tipo_por_pokeapi_id


def carregar_efetividade_tipo(conn, db, tipo_por_pokeapi_id):
    multiplicador = {}
    for atacante_id in range(1, 19):
        for defensor_id in range(1, 19):
            multiplicador[(atacante_id, defensor_id)] = 1.0

    for atacante_id in range(1, 19):
        tipo = db.tipos.find_one({"_id": f"tipo/{atacante_id}"})
        relacoes = tipo["damage_relations"]
        for alvo in relacoes["double_damage_to"]:
            defensor_id = int(alvo["url"].rstrip("/").rsplit("/", 1)[-1])
            if defensor_id <= 18:
                multiplicador[(atacante_id, defensor_id)] = 2.0
        for alvo in relacoes["half_damage_to"]:
            defensor_id = int(alvo["url"].rstrip("/").rsplit("/", 1)[-1])
            if defensor_id <= 18:
                multiplicador[(atacante_id, defensor_id)] = 0.5
        for alvo in relacoes["no_damage_to"]:
            defensor_id = int(alvo["url"].rstrip("/").rsplit("/", 1)[-1])
            if defensor_id <= 18:
                multiplicador[(atacante_id, defensor_id)] = 0.0

    linhas = [
        (tipo_por_pokeapi_id[a], tipo_por_pokeapi_id[d], m)
        for (a, d), m in multiplicador.items()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver.efetividade_tipo (atacante_id, defensor_id, multiplicador)
            VALUES (%s, %s, %s)
            ON CONFLICT (atacante_id, defensor_id) DO UPDATE SET multiplicador = EXCLUDED.multiplicador
            """,
            linhas,
        )
    conn.commit()
    return len(linhas)


def concilar_e_carregar_dim_pokemon(conn, db, tipo_por_nome, geracao_por_numero):
    linhas_csv = list(db.pokemon_csv.find())
    linhas_csv.sort(key=lambda d: int(d["#"]))

    registros_conciliacao = []
    csv_numero_para_id = {}
    velocidade_por_csv_numero = {}

    with conn.cursor() as cur:
        for linha in linhas_csv:
            csv_numero = int(linha["#"])
            nome_csv = linha["Name"]

            if not nome_csv.strip():
                slug_tentado = ""
                pokemon, especie = None, None
            else:
                slug_tentado = normalizar_nome_csv(nome_csv)
                pokemon, especie = localizar_pokemon(db, nome_csv)

            if pokemon is not None and especie is not None:
                nome = pokemon["name"]
                nome_pokeapi = pokemon["name"]
                pokedex_numero = especie["id"]
                tipo_1, tipo_2 = tipos_de(pokemon)
                stats = stats_de(pokemon)
                categoria = categoria_raridade_de(especie)
                habitat = habitat_de(especie)
                numero_geracao = numero_geracao_de(especie)
                eh_forma_alternativa = pokemon["id"] > 10000
                situacao = "conciliado"
                tratamento = ""
            else:
                nome = nome_csv.strip() or f"(sem nome - csv #{csv_numero})"
                nome_pokeapi = None
                pokedex_numero = None
                tipo_1 = linha["Type 1"].lower()
                tipo_2 = linha["Type 2"].lower() if linha["Type 2"].strip() else None
                stats = {
                    "hp": int(linha["HP"]),
                    "ataque": int(linha["Attack"]),
                    "defesa": int(linha["Defense"]),
                    "ataque_especial": int(linha["Sp. Atk"]),
                    "defesa_especial": int(linha["Sp. Def"]),
                    "velocidade": int(linha["Speed"]),
                }
                categoria = "lendario" if linha["Legendary"] == "True" else "comum"
                habitat = "desconhecido"
                numero_geracao = int(linha["Generation"])
                eh_forma_alternativa = False
                situacao = "nao_conciliado"
                tratamento = (
                    "sem nome na fonte: carregado só com atributos do CSV "
                    "(tipo, status, geração, lendário); pokedex_numero e habitat "
                    "desconhecidos"
                    if not nome_csv.strip()
                    else "nome não encontrado na PokéAPI: carregado só com atributos do CSV"
                )

            velocidade_por_csv_numero[csv_numero] = stats["velocidade"]
            registros_conciliacao.append(
                {
                    "csv_numero": csv_numero,
                    "nome_csv": nome_csv,
                    "slug_tentado": slug_tentado,
                    "situacao": situacao,
                    "tratamento_aplicado": tratamento,
                }
            )

            tipo_1_id = tipo_por_nome[tipo_1]
            tipo_2_id = tipo_por_nome[tipo_2] if tipo_2 else None
            geracao_id = geracao_por_numero[numero_geracao]

            cur.execute(
                """
                INSERT INTO silver.dim_pokemon (
                    csv_numero, pokedex_numero, nome, nome_pokeapi,
                    tipo_1_id, tipo_2_id, geracao_id, categoria_raridade, habitat,
                    hp, ataque, defesa, ataque_especial, defesa_especial, velocidade,
                    eh_forma_alternativa
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (csv_numero) DO UPDATE SET
                    pokedex_numero = EXCLUDED.pokedex_numero,
                    nome = EXCLUDED.nome,
                    nome_pokeapi = EXCLUDED.nome_pokeapi,
                    tipo_1_id = EXCLUDED.tipo_1_id,
                    tipo_2_id = EXCLUDED.tipo_2_id,
                    geracao_id = EXCLUDED.geracao_id,
                    categoria_raridade = EXCLUDED.categoria_raridade,
                    habitat = EXCLUDED.habitat,
                    hp = EXCLUDED.hp,
                    ataque = EXCLUDED.ataque,
                    defesa = EXCLUDED.defesa,
                    ataque_especial = EXCLUDED.ataque_especial,
                    defesa_especial = EXCLUDED.defesa_especial,
                    velocidade = EXCLUDED.velocidade,
                    eh_forma_alternativa = EXCLUDED.eh_forma_alternativa
                RETURNING id
                """,
                (
                    csv_numero, pokedex_numero, nome, nome_pokeapi,
                    tipo_1_id, tipo_2_id, geracao_id, categoria, habitat,
                    stats["hp"], stats["ataque"], stats["defesa"],
                    stats["ataque_especial"], stats["defesa_especial"], stats["velocidade"],
                    eh_forma_alternativa,
                ),
            )
            csv_numero_para_id[csv_numero] = cur.fetchone()[0]
    conn.commit()

    with CONCILIACAO_CSV.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=["csv_numero", "nome_csv", "slug_tentado", "situacao", "tratamento_aplicado"],
        )
        escritor.writeheader()
        escritor.writerows(registros_conciliacao)

    conciliados = sum(1 for r in registros_conciliacao if r["situacao"] == "conciliado")
    nao_conciliados = [r for r in registros_conciliacao if r["situacao"] != "conciliado"]
    print(f"conciliação: {conciliados}/{len(registros_conciliacao)} conciliados por nome")
    for r in nao_conciliados:
        print(f"  não conciliado: csv #{r['csv_numero']} ({r['nome_csv']!r}) -- {r['tratamento_aplicado']}")

    return csv_numero_para_id, velocidade_por_csv_numero


def carregar_fato_confronto(conn, db, csv_numero_para_id, velocidade_por_csv_numero):
    linhas = []
    for combate in db.combates.find():
        combate_numero = int(combate["_id"].rsplit("/", 1)[-1])
        primeiro = int(combate["First_pokemon"])
        segundo = int(combate["Second_pokemon"])
        vencedor = int(combate["Winner"])

        vel_primeiro = velocidade_por_csv_numero[primeiro]
        vel_segundo = velocidade_por_csv_numero[segundo]

        linhas.append((
            combate_numero, "primeiro",
            csv_numero_para_id[primeiro], csv_numero_para_id[segundo],
            vencedor == primeiro, vel_primeiro - vel_segundo,
        ))
        linhas.append((
            combate_numero, "segundo",
            csv_numero_para_id[segundo], csv_numero_para_id[primeiro],
            vencedor == segundo, vel_segundo - vel_primeiro,
        ))

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver.fato_confronto (
                combate_numero, papel, pokemon_id, oponente_id, venceu, diferenca_velocidade
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (combate_numero, papel) DO UPDATE SET
                pokemon_id = EXCLUDED.pokemon_id,
                oponente_id = EXCLUDED.oponente_id,
                venceu = EXCLUDED.venceu,
                diferenca_velocidade = EXCLUDED.diferenca_velocidade
            """,
            linhas,
        )
    conn.commit()
    return len(linhas)


def main():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    conn = psycopg.connect(POSTGRES_DSN)

    executar_ddl(conn)
    geracao_por_numero = carregar_dim_geracao(conn)
    tipo_por_nome, tipo_por_pokeapi_id = carregar_dim_tipo(conn, db)
    qtd_efetividade = carregar_efetividade_tipo(conn, db, tipo_por_pokeapi_id)
    csv_numero_para_id, velocidade_por_csv_numero = concilar_e_carregar_dim_pokemon(
        conn, db, tipo_por_nome, geracao_por_numero
    )
    qtd_fato = carregar_fato_confronto(conn, db, csv_numero_para_id, velocidade_por_csv_numero)

    with conn.cursor() as cur:
        for tabela in (
            "dim_geracao", "dim_tipo", "efetividade_tipo", "dim_pokemon", "fato_confronto",
        ):
            cur.execute(f"SELECT count(*) FROM silver.{tabela}")
            print(f"silver.{tabela}: {cur.fetchone()[0]} linhas")

    conn.close()


if __name__ == "__main__":
    main()
