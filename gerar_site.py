"""Órbita, passo 2: monta a pasta site/ a partir do arquivo.json.

Uso: python gerar_site.py
Precisa de dois arquivos na mesma pasta deste script:
  arquivo.json  (criado pelo coletar.py)
  modelo.html   (o visual da Órbita)
Resultado: a pasta site/, com o index.html e os dados.
Para ver o site, abra site/index.html no navegador.
"""
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PASTA = Path(__file__).parent
SITE = PASTA / "site"
DIAS_SEMANA = 7        # o que fica na página inicial
DESTAQUES = 5          # quantas notícias rodam no carrossel
TRECHO_ARQUIVO = 400   # no arquivo antigo o trecho é um pouco menor, para ficar leve
CATEGORIAS = ["tech", "sci", "game", "anime", "movie"]

for nome in ("arquivo.json", "modelo.html"):
    if not (PASTA / nome).exists():
        sys.exit(f"Não encontrei {nome} na pasta {PASTA}. Rode o coletar.py primeiro e confira se o modelo.html está aqui.")

dados = json.loads((PASTA / "arquivo.json").read_text(encoding="utf-8"))
historias = dados["historias"]


limite = datetime.now(timezone.utc) - timedelta(days=DIAS_SEMANA)

semana = [h for h in historias if datetime.fromisoformat(h["publicado"]) >= limite]
antigas = [h for h in historias if datetime.fromisoformat(h["publicado"]) < limite]

# Destaques: quanto mais fontes falam da história e quanto mais recente, mais ela sobe.
ordenadas = sorted(semana, key=lambda h: (len(h["fontes"]), h["publicado"]), reverse=True)
destaques = [h["id"] for h in ordenadas[:DESTAQUES]]


def escrever_js(caminho, texto):
    # O "<\/" evita problemas caso algum texto contenha "</script>".
    caminho.write_text(texto.replace("</", "<\\/"), encoding="utf-8")


(SITE / "dados").mkdir(parents=True, exist_ok=True)
shutil.copyfile(PASTA / "modelo.html", SITE / "index.html")

contagem_arq = {}
for cat in CATEGORIAS:
    lista = [h for h in antigas if h["categoria"] == cat]
    for h in lista:
        for f in h["fontes"]:
            # Só corta o texto se for o texto antigo. Se for da IA, não corta!
            if "resumo_ia" not in h and len(f["trecho"]) > TRECHO_ARQUIVO:
                f["trecho"] = f["trecho"][:TRECHO_ARQUIVO].rsplit(" ", 1)[0] + "…"
    contagem_arq[cat] = len(lista)
    corpo = json.dumps(lista, ensure_ascii=False, separators=(",", ":"))
    escrever_js(SITE / "dados" / f"arq-{cat}.js", f'window.ARQ=window.ARQ||{{}};window.ARQ["{cat}"]={corpo};')

semana_json = {
    "gerado_em": dados.get("gerado_em", datetime.now(timezone.utc).isoformat()),
    "destaques": destaques,
    "arq": contagem_arq,
    "historias": semana,
}
escrever_js(SITE / "dados" / "semana.js", "window.SEMANA=" + json.dumps(semana_json, ensure_ascii=False, separators=(",", ":")) + ";")

print(f"Pronto: {len(semana)} notícias na semana e {len(antigas)} no arquivo.")
for cat in CATEGORIAS:
    print(f"  {cat}: {sum(1 for h in semana if h['categoria'] == cat)} na semana, {contagem_arq[cat]} no arquivo")
print(f"Abra este arquivo no navegador: {SITE / 'index.html'}")