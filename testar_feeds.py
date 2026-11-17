"""Testa se os feeds RSS candidatos da Órbita estão respondendo.

Uso: python testar_feeds.py
Não precisa instalar nada, só o Python.
"""
import urllib.request
import xml.etree.ElementTree as ET

# Identifique o robô de forma honesta: alguns sites bloqueiam User-Agent genérico.
UA = "OrbitaBot/0.1 (projeto pessoal de agregador de noticias)"
ATOM = "{http://www.w3.org/2005/Atom}"
RDF = "{http://purl.org/rss/1.0/}"  # formato antigo (RSS 1.0), usado pela Nature

FEEDS = {
    "Tecnologia": [
        ("Tecnoblog", "https://tecnoblog.net/feed"),
        ("Canaltech", "https://canaltech.com.br/rss/"),
        ("Olhar Digital", "https://olhardigital.com.br/feed/"),
    ],
    "Ciência": [
        ("NASA", "https://www.nasa.gov/feed/"),
        ("Nature", "https://www.nature.com/nature.rss"),
        ("Olhar Digital (ciência)", "https://olhardigital.com.br/editorias/ciencia-e-espaco/feed/"),
    ],
    "Games": [
        ("Tecnoblog Jogos", "https://tecnoblog.net/tema/jogos/feed"),
        ("IGN Brasil", "https://br.ign.com/feed.xml"),
    ],
    "Animes": [
        ("Anime News Network", "https://www.animenewsnetwork.com/all/rss.xml"),
        ("MyAnimeList", "https://myanimelist.net/rss/news.xml"),
    ],
    "Filmes": [
        ("Papo de Cinema", "https://www.papodecinema.com.br/feed/"),
        ("Observatório do Cinema", "https://observatoriodocinema.uol.com.br/feed"),
        ("Cinema com Rapadura", "https://cinemacomrapadura.com.br/feed"),
        ("Variety", "https://variety.com/feed/"),
        ("Deadline", "https://deadline.com/feed/"),
    ],
}


def ler(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raiz = ET.fromstring(resp.read())
    itens = (
        raiz.findall(".//item")
        or raiz.findall(f".//{ATOM}entry")
        or raiz.findall(f".//{RDF}item")
    )
    primeiro = ""
    if itens:
        primeiro = (
            itens[0].findtext("title")
            or itens[0].findtext(f"{ATOM}title")
            or itens[0].findtext(f"{RDF}title")
            or ""
        )
    return len(itens), primeiro.strip()


ok = total = 0
for secao, lista in FEEDS.items():
    print(f"\n== {secao} ==")
    for nome, url in lista:
        total += 1
        try:
            qtd, titulo = ler(url)
            if qtd == 0:
                print(f"  [vazio ] {nome}: o feed abriu, mas não trouxe itens")
            else:
                ok += 1
                print(f"  [ok    ] {nome}: {qtd} itens. Último: {titulo[:70]}")
        except Exception as erro:
            print(f"  [falhou] {nome}: {type(erro).__name__}: {erro}")

print(f"\nResultado: {ok} de {total} feeds funcionando.")