"""Órbita, passo 1: coleta as notícias dos feeds RSS e guarda tudo em arquivo.json.

Uso: python coletar.py
Não precisa instalar nada, só o Python.
O arquivo.json fica na mesma pasta deste script e CRESCE a cada rodada:
as notícias novas são acrescentadas e as antigas continuam guardadas
(por RETENCAO_DIAS dias). Assim o site pode mostrar só a semana na página
inicial e manter o resto no arquivo de cada seção.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

UA = "OrbitaBot/0.1 (projeto pessoal de agregador de noticias)"
ARQUIVO = Path(__file__).with_name("arquivo.json")

DIAS = 7                  # cada rodada lê as notícias dos últimos 7 dias de cada feed
MAX_POR_FEED = 15         # no máximo 60 itens lidos de cada feed
TRECHO = 600              # tamanho máximo do trecho guardado de cada matéria
RETENCAO_DIAS = 180       # notícias mais antigas que isso saem do arquivo
JANELA_JUNTAR_DIAS = 4    # só junta matérias publicadas com até 4 dias de diferença
MAX_IA_POR_RODADA = 150    # quantas histórias a IA processa por rodada (protege a cota gratuita)
PAUSA_IA = 4              # segundos entre uma chamada de IA e outra
DIAS_IA = 7               # a IA só trabalha nas histórias da última semana
FONTES_NA_IA = 3          # quantas fontes de cada história a IA lê

# Duas notícias contam como a mesma história se tiverem pelo menos MIN_PALAVRAS
# palavras em comum no título e a semelhança passar de LIMIAR.
LIMIAR = 0.30
MIN_PALAVRAS = 3

# Os nomes das categorias (tech, sci, game, anime, movie) são os mesmos do site.
FEEDS = {
    "tech": [
        ("Tecnoblog", "https://tecnoblog.net/feed", "pt"),
        ("Canaltech", "https://canaltech.com.br/rss/", "pt"),
        ("Olhar Digital", "https://olhardigital.com.br/feed/", "pt"),
    ],
    "sci": [
        ("NASA", "https://www.nasa.gov/feed/", "en"),
        ("Nature", "https://www.nature.com/nature.rss", "en"),
        ("Olhar Digital Ciência", "https://olhardigital.com.br/editorias/ciencia-e-espaco/feed/", "pt"),
    ],
    "game": [
        ("Tecnoblog Jogos", "https://tecnoblog.net/tema/jogos/feed", "pt"),
        ("IGN Brasil", "https://br.ign.com/feed.xml", "pt"),
    ],
    "anime": [
        ("Anime News Network", "https://www.animenewsnetwork.com/all/rss.xml", "en"),
        ("MyAnimeList", "https://myanimelist.net/rss/news.xml", "en"),
    ],
    "movie": [
        ("Observatório do Cinema", "https://observatoriodocinema.uol.com.br/feed", "pt"),
        ("Cinema com Rapadura", "https://cinemacomrapadura.com.br/feed", "pt"),
        ("Variety", "https://variety.com/feed/", "en"),
        ("Deadline", "https://deadline.com/feed/", "en"),
    ],
}

NS = {
    "atom": "{http://www.w3.org/2005/Atom}",
    "rdf": "{http://purl.org/rss/1.0/}",
    "content": "{http://purl.org/rss/1.0/modules/content/}",
    "media": "{http://search.yahoo.com/mrss/}",
    "dc": "{http://purl.org/dc/elements/1.1/}",
}

STOP = set(
    "de da do das dos a o as os e em um uma para por com que no na nos nas se ao "
    "the of and to in for on is are with at by from as it its an his her new".split()
)


# ---------- leitura dos feeds ----------

def campo(item, nome):
    """Lê um campo do item, seja o feed RSS 2.0, Atom ou RSS 1.0."""
    for prefixo in ("", NS["atom"], NS["rdf"]):
        el = item.find(prefixo + nome)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def limpar(texto):
    """Tira as marcações HTML e deixa só o texto."""
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def cortar(texto, n):
    """Corta no limite de tamanho sem partir uma palavra no meio."""
    if len(texto) <= n:
        return texto
    corte = texto[:n].rsplit(" ", 1)[0]
    return corte.rstrip(" ,;:.-") + "…"


def tirar_rodape(texto):
    """Remove frases do tipo 'O post X apareceu primeiro em Y', comuns em feeds WordPress."""
    return re.sub(
        r"\s*(O post|The post|O artigo|The article)\b.{0,250}?(apareceu primeiro em|appeared first on)[^.]*\.?\s*$",
        "", texto, flags=re.I,
    )


def achar_link(item):
    link = campo(item, "link")
    if link:
        return link
    for el in item.findall(NS["atom"] + "link"):  # feeds Atom guardam o link num atributo
        if el.get("rel", "alternate") == "alternate" and el.get("href"):
            return el.get("href")
    return ""


def achar_data(item):
    bruto = (
        campo(item, "pubDate")
        or campo(item, "published")
        or campo(item, "updated")
        or campo(item, NS["dc"] + "date")
    )
    for conversor in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            data = conversor(bruto)
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)
            return data.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def achar_imagem(item, html_bruto):
    for el in item.iter():
        if el.tag in (NS["media"] + "content", NS["media"] + "thumbnail"):
            tipo, medium, url = el.get("type", ""), el.get("medium", ""), el.get("url")
            eh_imagem = el.tag.endswith("thumbnail") or medium == "image" or tipo.startswith("image")
            if url and eh_imagem:
                return url
        if el.tag == "enclosure" and el.get("type", "").startswith("image") and el.get("url"):
            return el.get("url")
    achou = re.search(r'<img[^>]+src=["\']([^"\']+)', html_bruto)
    return achou.group(1) if achou else ""


def achar_video(html_bruto):
    achou = re.search(r"(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)([\w-]{11})", html_bruto)
    return f"https://www.youtube.com/watch?v={achou.group(1)}" if achou else ""


def ler_feed(xml_bytes, fonte, idioma, categoria):
    raiz = ET.fromstring(xml_bytes)
    itens = (
        raiz.findall(".//item")
        or raiz.findall(".//" + NS["atom"] + "entry")
        or raiz.findall(".//" + NS["rdf"] + "item")
    )
    limite = datetime.now(timezone.utc) - timedelta(days=DIAS)
    artigos = []
    for item in itens[:MAX_POR_FEED]:
        titulo = limpar(campo(item, "title"))
        link = achar_link(item)
        data = achar_data(item)
        if not (titulo and link and data) or data < limite:
            continue
        bruto = (
            campo(item, NS["content"] + "encoded")
            or campo(item, "description")
            or campo(item, "summary")
            or campo(item, "content")
        )
        artigos.append({
            "categoria": categoria,
            "fonte": fonte,
            "idioma": idioma,
            "titulo": titulo,
            "link": link,
            "publicado": data.isoformat(),
            "trecho": cortar(tirar_rodape(limpar(bruto)), TRECHO),
            "imagem": achar_imagem(item, bruto),
            "video": achar_video(bruto),
        })
    return artigos


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


# ---------- juntar notícias parecidas ----------

def palavras(titulo):
    base = unicodedata.normalize("NFKD", titulo.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return {p for p in re.findall(r"[a-z0-9]{3,}", base) if p not in STOP}


def mesma_historia(a, b):
    comuns = len(a & b)
    return comuns >= MIN_PALAVRAS and comuns / len(a | b) >= LIMIAR


# ---------- o arquivo que cresce ----------

def carregar_arquivo():
    if not ARQUIVO.exists():
        return []
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))["historias"]
    except (ValueError, KeyError, OSError):
        sys.exit("O arquivo.json está danificado. Renomeie ou apague esse arquivo e rode de novo.")


def incorporar(historias, artigos):
    """Acrescenta as matérias novas ao arquivo. Devolve (histórias novas, matérias juntadas)."""
    ja_tem = {f["link"] for h in historias for f in h["fontes"]}
    novos = [a for a in artigos if a["link"] not in ja_tem]
    criadas = juntadas = 0
    for art in sorted(novos, key=lambda a: a["publicado"]):
        data = datetime.fromisoformat(art["publicado"])
        p = palavras(art["titulo"])
        alvo = None
        for h in historias:
            if h["categoria"] != art["categoria"]:
                continue
            if abs(data - datetime.fromisoformat(h["publicado"])) > timedelta(days=JANELA_JUNTAR_DIAS):
                continue
            if any(f["fonte"] == art["fonte"] for f in h["fontes"]):
                continue  # uma fonte só entra uma vez em cada história
            if any(mesma_historia(p, palavras(f["titulo"])) for f in h["fontes"]):
                alvo = h
                break
        item = {k: art[k] for k in ("fonte", "idioma", "titulo", "link", "publicado", "trecho")}
        if alvo is not None:
            alvo["fontes"].append(item)
            alvo["publicado"] = max(alvo["publicado"], art["publicado"])
            alvo["imagem"] = alvo["imagem"] or art["imagem"]
            alvo["video"] = alvo["video"] or art["video"]
            juntadas += 1
        else:
            historias.append({
                "id": hashlib.sha1(art["link"].encode()).hexdigest()[:8],
                "categoria": art["categoria"],
                "titulo": art["titulo"],
                "publicado": art["publicado"],
                "imagem": art["imagem"],
                "video": art["video"],
                "fontes": [item],
            })
            criadas += 1
    return criadas, juntadas


# ---------- gravação e IA ----------

def salvar_arquivo(historias):
    """Grava o arquivo.json de uma vez só (troca o arquivo inteiro), para nunca ficar pela metade."""
    historias.sort(key=lambda h: h["publicado"], reverse=True)
    saida = {"gerado_em": datetime.now(timezone.utc).isoformat(), "historias": historias}
    tmp = ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(ARQUIVO)


def fila_ia(historias):
    """Histórias da última semana sem IA (ou que ganharam fontes novas), as mais importantes primeiro."""
    limite = datetime.now(timezone.utc) - timedelta(days=DIAS_IA)
    pendentes = []
    for h in historias:
        if datetime.fromisoformat(h["publicado"]) < limite:
            continue
        # Histórias já processadas por versões anteriores não têm ia_n_fontes: contam como prontas.
        feito = h.get("ia_n_fontes", len(h["fontes"]) if "resumo_ia" in h else 0)
        if feito < len(h["fontes"]):
            pendentes.append(h)
    pendentes.sort(key=lambda h: (len(h["fontes"]), h["publicado"]), reverse=True)
    return pendentes


def enriquecer(historias):
    chave = os.environ.get("GROQ_API_KEY", "").strip()
    if not chave:
        print('\nIA desligada: a variável GROQ_API_KEY não está definida. Para ligar: $env:GROQ_API_KEY="sua chave"')
        return
    from ia_helper import processar_noticia  # só importa aqui, para a coleta funcionar mesmo sem a IA

    pendentes = fila_ia(historias)
    print(f"\n{len(pendentes)} histórias esperando a IA. Vou processar até {MAX_IA_POR_RODADA}.")
    feitas = falhas = 0
    for h in pendentes[:MAX_IA_POR_RODADA]:
        print(f"  -> Analisando: {h['titulo'][:60]}")
        try:
            r = processar_noticia(h["fontes"][:FONTES_NA_IA])
        except Exception as erro:
            if "LIMITE_DIARIO_ATINGIDO" in str(erro):
                print("\nLimite diário da IA atingido. O que já foi feito está salvo. Rode de novo amanhã.")
                break
            print(f"  [Erro inesperado] {erro}")
            falhas += 1
            continue
        if not r:
            print("  [Aviso] A IA não respondeu direito. Tentará na próxima rodada.")
            falhas += 1
            continue
        h["titulo_original"] = h["fontes"][0]["titulo"]
        h["titulo"] = r["titulo_pt"]
        h["resumo_ia"] = r["resumo_ia"]
        h["contexto_ia"] = r["contexto_ia"]
        h["ia_n_fontes"] = len(h["fontes"])
        feitas += 1
        salvar_arquivo(historias)  # salva a cada história: se algo parar, nada se perde
        time.sleep(PAUSA_IA)
    print(f"IA: {feitas} histórias processadas, {falhas} falhas. Ainda faltam {len(fila_ia(historias))} na fila.")


# ---------- programa principal ----------

def main():
    artigos = []
    for categoria, lista in FEEDS.items():
        print(f"\n== {categoria} ==")
        for nome, url, idioma in lista:
            try:
                novos = ler_feed(baixar(url), nome, idioma, categoria)
            except Exception as erro:
                print(f"  [falhou] {nome}: {type(erro).__name__}: {erro}")
                continue
            artigos += novos
            print(f"  [ok    ] {nome}: {len(novos)} notícias dos últimos {DIAS} dias")

    if not artigos:
        print("\nNenhuma notícia coletada. O arquivo.json não foi alterado.")
        return

    historias = carregar_arquivo()
    antes = len(historias)
    criadas, juntadas = incorporar(historias, artigos)

    limite = datetime.now(timezone.utc) - timedelta(days=RETENCAO_DIAS)
    historias = [h for h in historias if datetime.fromisoformat(h["publicado"]) >= limite]
    salvar_arquivo(historias)  # primeiro guarda tudo que foi coletado...
    print("\nNotícias coletadas e salvas no arquivo.json.")
    enriquecer(historias)      # ...e só depois chama a IA

    semana = datetime.now(timezone.utc) - timedelta(days=7)
    print(f"\nPronto: {criadas} histórias novas e {juntadas} matérias juntadas a histórias que já existiam.")
    print(f"O arquivo tinha {antes} histórias e agora tem {len(historias)}.")
    for categoria in FEEDS:
        h = [x for x in historias if x["categoria"] == categoria]
        sem = sum(1 for x in h if datetime.fromisoformat(x["publicado"]) >= semana)
        print(f"  {categoria}: {sem} na última semana, {len(h)} no arquivo")
    print(f"Arquivo salvo em: {ARQUIVO}")


if __name__ == "__main__":
    main()
