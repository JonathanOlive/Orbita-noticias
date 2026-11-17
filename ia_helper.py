"""Conversa com a Groq para traduzir, resumir e comentar uma história.

A chave NÃO fica neste arquivo. Ela vem da variável de ambiente GROQ_API_KEY:
    $env:GROQ_API_KEY="Coloquei minha chave aqui"
Instalação (uma vez):  pip install groq
"""
import os
import re
import sys
import time

from groq import Groq

# --- AQUI ESTAVAM AS LINHAS QUE FALTARAM ---
MODELO = os.environ.get("ORBITA_MODELO_IA", "openai/gpt-oss-120b")
client = Groq(api_key=os.environ.get("GROQ_API_KEY", "").strip() or None)
# -------------------------------------------

PROMPT = """Você é jornalista do site "Órbita" e escreve em português do Brasil.
Abaixo estão uma ou mais fontes sobre o mesmo assunto, algumas em inglês. Use SOMENTE o que está nelas.
Os trechos às vezes vêm misturados com menus, links e textos de navegação do site (por exemplo "Archive Submissions Index Search Calendar RSS"). Ignore tudo isso e aproveite só o conteúdo da notícia.

{fontes}

Responda ESTRITAMENTE neste formato, sem markdown e sem texto extra:
TITULO_TRADUZIDO: título em português (se o original já está em português, repita-o)
RESUMO: Escreva 1 parágrafo curto e direto (cerca de 3 frases) explicando o que aconteceu.
CONTEXTO: Escreva 2 parágrafos separados por uma linha em branco. O primeiro explica o impacto imediato (o que muda na prática). O segundo traz o cenário geral (use conhecimento de mundo para explicar o que é a empresa/jogo, sem inventar fatos).

Regras: tom factual e neutro, sem opinião própria. Se a notícia envolver acusação, processo ou investigação, relate só o que as fontes informam e deixe claro que são alegações. Não invente números, datas, nomes nem citações."""

def _secao(texto, rotulo, seguintes):
    """Pega o texto que vem depois de 'ROTULO:' até o próximo rótulo."""
    fim = "|".join(seguintes)
    achou = re.search(rf"{rotulo}\s*:\s*(.*?)(?=\n\s*(?:{fim})\s*:|\Z)", texto, re.S | re.I)
    if not achou:
        return ""
    campo = achou.group(1).strip()
    if campo.startswith("[") and campo.endswith("]"):
        campo = campo[1:-1].strip()
    return campo

def processar_noticia(fontes):
    """Recebe a lista de fontes de uma história e devolve titulo_pt, resumo_ia e contexto_ia (ou None)."""
    bloco = "\n\n".join(
        f'FONTE {i}: {f["fonte"]} (idioma: {"inglês" if f["idioma"] == "en" else "português"})\n'
        f'Título: {f["titulo"]}\nTrecho: {f["trecho"] or "(sem trecho)"}'
        for i, f in enumerate(fontes, 1)
    )
    prompt = PROMPT.format(fontes=bloco)

    for tentativa in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODELO,
                messages=[{"role": "user", "content": prompt}],
            )
            texto = (resp.choices[0].message.content or "").replace("**", "")
            titulo = _secao(texto, "TITULO_TRADUZIDO", ["RESUMO", "CONTEXTO"])
            resumo = _secao(texto, "RESUMO", ["TITULO_TRADUZIDO", "CONTEXTO"])
            contexto = _secao(texto, "CONTEXTO", ["TITULO_TRADUZIDO", "RESUMO"])
            if titulo and resumo:
                return {"titulo_pt": titulo, "resumo_ia": resumo, "contexto_ia": contexto}
            print("    resposta fora do formato; tentando de novo")
        except Exception as erro:
            msg = str(erro)
            baixo = msg.lower()
            if "401" in msg or "invalid_api_key" in baixo:
                sys.exit("A chave da Groq foi recusada. Confira a variável GROQ_API_KEY.")
            if "model_not_found" in baixo or "does not exist" in baixo or "404" in msg:
                sys.exit(f"O modelo {MODELO} não foi encontrado na Groq. Confira o nome do modelo.")
            if "429" in msg or "rate_limit" in baixo:
                if "per day" in baixo or "(tpd)" in baixo or "(rpd)" in baixo:
                    raise Exception("LIMITE_DIARIO_ATINGIDO")
                print("    limite por minuto da Groq; esperando 20 segundos")
                time.sleep(20)
                continue
            print(f"    erro: {msg[:150]}")
            time.sleep(3 * (tentativa + 1))
    return None