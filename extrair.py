import csv
import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient

POKEAPI_BASE = "https://pokeapi.co/api/v2/"
POKEMON_CSV_URL = "https://raw.githubusercontent.com/cdiener/pokemon_app/master/pokemon.csv"
COMBATS_CSV_URL = "https://raw.githubusercontent.com/cdiener/pokemon_app/master/combats.csv"

DADOS_BRUTOS = Path("dados_brutos")
RATE_LIMIT_SEGUNDOS = 0.1
MAX_TENTATIVAS_429 = 3
ESPERA_429_SEGUNDOS = 5

ESPECIES_VALIDAS = range(1, 722)
TIPOS_VALIDOS = list(range(1, 20)) + [10001, 10002]

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://pokemon:pokemon@localhost:27017/?authSource=admin")
MONGO_DB = "pokedex_bronze"


def timestamp_atual():
    return datetime.now(timezone.utc).isoformat()

def caminho_cache(*partes):
    caminho = DADOS_BRUTOS.joinpath(*partes)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho

def requisitar_com_retry(url):
    tentativas_429 = 0
    while True:
        try:
            resposta = requests.get(url, timeout=10)
        except requests.RequestException as erro:
            raise RuntimeError(f"falha de conexão em {url}: {erro}")

        if resposta.status_code == 200:
            return resposta

        if resposta.status_code == 429:
            tentativas_429 += 1
            if tentativas_429 > MAX_TENTATIVAS_429:
                raise RuntimeError(f"429 persistente após {MAX_TENTATIVAS_429} tentativas: {url}")
            time.sleep(ESPERA_429_SEGUNDOS)
            continue

        if resposta.status_code >= 500:
            raise RuntimeError(f"erro {resposta.status_code} do servidor: {url}")

        raise RuntimeError(f"status inesperado {resposta.status_code}: {url}")

def buscar_json_com_cache(url, caminho):
    if caminho.exists():
        with caminho.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)

    dado = requisitar_com_retry(url).json()
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dado, arquivo, ensure_ascii=False)
    time.sleep(RATE_LIMIT_SEGUNDOS)
    return dado

def buscar_texto_com_cache(url, caminho):
    if caminho.exists():
        with caminho.open("r", encoding="utf-8") as arquivo:
            return arquivo.read()

    texto = requisitar_com_retry(url).text
    with caminho.open("w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    time.sleep(RATE_LIMIT_SEGUNDOS)
    return texto

def upsert_bronze(colecao, _id, doc_fonte, fonte, url_ou_caminho):
    doc = {
        "_id": _id,
        "_fonte": fonte,
        "_url": url_ou_caminho,
        "_ingerido_em": timestamp_atual(),
    }
    doc.update(doc_fonte)
    # replace_one (não update_one com $set): campos com "." no nome, como
    # "Sp. Atk" do pokemon.csv, seriam interpretados por $set como caminho
    # aninhado ("Sp" -> {" Atk": ...}) em vez de campo literal.
    colecao.replace_one({"_id": _id}, doc, upsert=True)

def id_da_url(url):
    return url.rstrip("/").rsplit("/", 1)[-1]

def extrair_pokedex(db):
    colecao_especies = db["especies"]
    colecao_pokemon = db["pokemon"]

    for especie_id in ESPECIES_VALIDAS:
        url_especie = f"{POKEAPI_BASE}pokemon-species/{especie_id}"
        especie = buscar_json_com_cache(url_especie, caminho_cache("especies", f"{especie_id}.json"))
        upsert_bronze(colecao_especies, f"especie/{especie_id}", especie, "pokeapi", url_especie)

        for variedade in especie["varieties"]:
            pokemon_url = variedade["pokemon"]["url"]
            pokemon_id = id_da_url(pokemon_url)
            pokemon = buscar_json_com_cache(pokemon_url, caminho_cache("pokemon", f"{pokemon_id}.json"))
            upsert_bronze(colecao_pokemon, f"pokemon/{pokemon_id}", pokemon, "pokeapi", pokemon_url)

def extrair_tipos(db):
    colecao_tipos = db["tipos"]

    for tipo_id in TIPOS_VALIDOS:
        url_tipo = f"{POKEAPI_BASE}type/{tipo_id}"
        tipo = buscar_json_com_cache(url_tipo, caminho_cache("tipos", f"{tipo_id}.json"))
        upsert_bronze(colecao_tipos, f"tipo/{tipo_id}", tipo, "pokeapi", url_tipo)

def extrair_pokemon_csv(db):
    colecao = db["pokemon_csv"]
    caminho = caminho_cache("pokemon.csv")
    texto = buscar_texto_com_cache(POKEMON_CSV_URL, caminho)

    leitor = csv.DictReader(io.StringIO(texto))
    for linha in leitor:
        numero = linha["#"]
        upsert_bronze(colecao, f"pokemon_csv/{numero}", linha, "pokemon.csv", str(caminho))

def extrair_combates(db):
    colecao = db["combates"]
    caminho = caminho_cache("combats.csv")
    texto = buscar_texto_com_cache(COMBATS_CSV_URL, caminho)

    leitor = csv.DictReader(io.StringIO(texto))
    for numero_linha, linha in enumerate(leitor, start=1):
        upsert_bronze(colecao, f"combate/{numero_linha}", linha, "combats.csv", str(caminho))

def main():
    cliente = MongoClient(MONGO_URI)
    db = cliente[MONGO_DB]

    extrair_pokedex(db)
    extrair_tipos(db)
    extrair_pokemon_csv(db)
    extrair_combates(db)

    cliente.close()

if __name__ == "__main__":
    main()
