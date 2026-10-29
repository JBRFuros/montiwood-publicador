"""Robô de publicação do Instagram da MontiWood.

Lê fila.json, publica no @mont_iwood os itens cujo horário já chegou e que ainda
não estão em publicados.json. Roda no GitHub Actions a cada 15 minutos.

Uso local:  IG_TOKEN=... python3 publicar.py [--teste ID]
  --teste ID  cria o container do item ID e espera ficar pronto, SEM publicar.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

API = "https://graph.instagram.com/v21.0"
IG_USER = "17841479933107578"
RAW = "https://raw.githubusercontent.com/JBRFuros/montiwood-publicador/main/"
FUSO = ZoneInfo("America/Sao_Paulo")
AQUI = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ["IG_TOKEN"]


def chamar(metodo, caminho, **params):
    params["access_token"] = TOKEN
    dados = urllib.parse.urlencode(params).encode()
    if metodo == "GET":
        req = urllib.request.Request(f"{API}/{caminho}?{dados.decode()}")
    else:
        req = urllib.request.Request(f"{API}/{caminho}", data=dados, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{caminho}: {e.read().decode()}") from None


def esperar_pronto(container, limite_s=600):
    inicio = time.time()
    while time.time() - inicio < limite_s:
        st = chamar("GET", container, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"container {container} com erro: {st}")
        time.sleep(10)
    raise RuntimeError(f"container {container} não ficou pronto em {limite_s}s")


def criar_container(item):
    midias = [RAW + m for m in item["midias"]]
    legenda = item["legenda"]
    if item["tipo"] == "REELS":
        params = dict(media_type="REELS", video_url=midias[0], caption=legenda, share_to_feed="true")
        if item.get("capa"):
            params["cover_url"] = RAW + item["capa"]
        c = chamar("POST", f"{IG_USER}/media", **params)["id"]
    elif item["tipo"] == "CAROUSEL":
        filhos = []
        for url in midias:
            f = chamar("POST", f"{IG_USER}/media", image_url=url, is_carousel_item="true")["id"]
            esperar_pronto(f)
            filhos.append(f)
        c = chamar("POST", f"{IG_USER}/media", media_type="CAROUSEL", children=",".join(filhos), caption=legenda)["id"]
    else:  # IMAGE
        c = chamar("POST", f"{IG_USER}/media", image_url=midias[0], caption=legenda)["id"]
    esperar_pronto(c)
    return c


def main():
    with open(os.path.join(AQUI, "fila.json"), encoding="utf-8") as f:
        fila = json.load(f)
    caminho_pub = os.path.join(AQUI, "publicados.json")
    publicados = {}
    if os.path.exists(caminho_pub):
        with open(caminho_pub, encoding="utf-8") as f:
            publicados = json.load(f)

    if len(sys.argv) == 3 and sys.argv[1] == "--teste":
        item = next(i for i in fila if i["id"] == sys.argv[2])
        c = criar_container(item)
        print(f"TESTE OK: container {c} pronto para '{item['id']}' (não publicado)")
        return

    agora = datetime.now(FUSO)
    for item in sorted(fila, key=lambda i: i["quando"]):
        if item["id"] in publicados:
            continue
        if datetime.fromisoformat(item["quando"]) > agora:
            continue
        print(f"publicando {item['id']} ({item['quando']})")
        try:
            c = criar_container(item)
            pub = chamar("POST", f"{IG_USER}/media_publish", creation_id=c)["id"]
            link = chamar("GET", pub, fields="permalink")["permalink"]
            publicados[item["id"]] = {"media_id": pub, "link": link, "em": agora.isoformat()}
            print(f"  ok → {link}")
        except Exception as e:  # um item com erro não trava os outros
            print(f"  ERRO em {item['id']}: {e}")
        with open(caminho_pub, "w", encoding="utf-8") as f:
            json.dump(publicados, f, ensure_ascii=False, indent=2)
        break  # no máximo 1 publicação por rodada, para não amontoar posts atrasados


if __name__ == "__main__":
    main()
