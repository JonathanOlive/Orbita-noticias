"""Conversa com a Groq para traduzir, resumir e comentar uma história."""

import os
import re
import sys
import time

from groq import Groq

MODELO = os.environ.get("ORBITA_MODELO_IA", "openai/gpt-oss-120b")
client = Groq(api_key=os.environ.get("GROQ_API_KEY", "").strip() or None)

# --- AQUI DEFINIMOS O ESTILO DE CADA CATEGORIA ---
ESTILOS = {
    "tech": "Use uma linguagem moderna, direta e focada em inovação. Destaque o impacto prático da tecnologia na vida das pessoas e o futuro do setor.",
    "sci": "Use uma linguagem acadêmica, formal e precisa. Explique conceitos complexos de forma clara, mas mantenha o rigor científico e a seriedade do texto.",
    "game": "Use uma linguagem jovem, empolgada e dinâmica, voltada para o público gamer. Pode usar termos do universo dos jogos, mas sem perder a clareza jornalística.",
    "anime": "Use uma linguagem animada e entusiasmada, voltada para os fãs de animes e mangás. Destaque a emoção das histórias, os estúdios e o impacto na comunidade otaku.",
    "movie": "Use uma linguagem de crítico de cinema: analítica, envolvente e focada em enredo, direção, elenco e impacto cultural ou de bilheteria."
}

PROMPT = """Você é jornalista do site "Órbita" e escreve em português do Brasil.
Abaixo estão uma ou mais fontes sobre o mesmo assunto, algumas em inglês. Use SOMENTE o que está nelas.
Os trechos às vezes vêm misturados com menus, links e textos de navegação do site. Ignore tudo isso e aproveite só o conteúdo da notícia.

DIRETRIZ DE ESTILO PARA ESTA NOTÍCIA:
{estilo_especifico}

{fontes}

Responda ESTRITAMENTE neste formato, sem markdown e sem texto extra:
TITULO_TRADUZIDO: título em português (se o original já está em português, repita-o)
RESUMO: Escreva 1 parágrafo curto e direto (cerca de 3 frases) explicando o que aconteceu, já aplicando o estilo pedido acima.
CONTEXTO: Escreva 2 parágrafos separados por uma linha em branco. O primeiro explica o impacto imediato (o que muda na prática). O segundo traz o cenário geral (use conhecimento de mundo para explicar o que é a empresa/jogo, sem inventar fatos).

Regras: tom factual e neutro (mesmo com o estilo específico), sem opinião própria. Se a notícia envolver acusação, processo ou investigação, relate só o que as fontes informam e deixe claro que são alegações. Não invente números, datas, nomes nem citações."""

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
    
    # Pega a categoria da primeira fonte para saber qual estilo usar
    categoria = fontes[0].get("categoria", "tech")
    estilo = ESTILOS.get(categoria, "Use uma linguagem jornalística neutra, clara e direta.")

    bloco = "\n\n".join(
        f'FONTE {i}: {f["fonte"]} (idioma: {"inglês" if f["idioma"] == "en" else "português"})\n'
        f'Título: {f["titulo"]}\nTrecho: {f["trecho"] or "(sem trecho)"}'
        for i, f in enumerate(fontes, 1)
    )
    
    # Injeta o estilo específico no prompt
    prompt = PROMPT.format(estilo_especifico=estilo, fontes=bloco)

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
