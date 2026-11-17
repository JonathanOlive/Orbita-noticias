"""Testa a chave e o modelo do Gemini antes de rodar o projeto inteiro.

Passo 1 (uma vez, no terminal do VS Code):
    pip install google-genai

Passo 2 (em cada terminal novo): guarde a chave numa variável de ambiente,
FORA do código, assim ela nunca vai parar no GitHub por engano:
    $env:GEMINI_API_KEY="cole_sua_chave_aqui"

Passo 3:
    python testar_gemini.py
"""
import json
import os
import sys

from google import genai
from google.genai import types

# Se a qualidade dos textos não agradar, troque por "gemini-3.5-flash".
MODELO = "gemini-3.1-flash-lite"

chave = os.environ.get("GEMINI_API_KEY", "").strip()
if not chave or "SUA_CHAVE" in chave or "cole_sua" in chave:
    sys.exit(
        "A variável GEMINI_API_KEY não está definida, ou ainda tem o texto de exemplo.\n"
        'Rode no terminal: $env:GEMINI_API_KEY="sua chave de verdade"'
    )

client = genai.Client(api_key=chave)


def processar_noticia(titulo, trecho):
    """Traduz o título e escreve resumo e contexto. Devolve um dicionário, ou None se falhar."""
    prompt = f"""Você é jornalista do site "Órbita". Leia a notícia abaixo, que pode estar
em inglês, e escreva em português do Brasil.

Título: {titulo}
Trecho: {trecho}

Responda apenas com um JSON com estas chaves:
"titulo_pt": o título traduzido,
"resumo": um resumo de 2 a 3 frases sobre o que aconteceu,
"contexto": um parágrafo explicando por que isso importa.
Use somente informações que estão no título e no trecho. Não invente fatos nem citações."""

    try:
        resposta = client.models.generate_content(
            model=MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        dados = json.loads(resposta.text)
        return {
            "titulo_pt": dados["titulo_pt"].strip(),
            "resumo_ia": dados["resumo"].strip(),
            "contexto_ia": dados["contexto"].strip(),
        }
    except Exception as erro:
        texto = str(erro)
        # Erros que não adianta tentar de novo: para tudo, em vez de repetir 17 vezes.
        if "API_KEY_INVALID" in texto or "API key not valid" in texto:
            sys.exit("A chave foi recusada pelo Google (API key not valid). Crie uma chave nova no Google AI Studio.")
        if "NOT_FOUND" in texto or "404" in texto:
            sys.exit(f"O modelo {MODELO} não foi encontrado. Confira o nome do modelo.")
        if "429" in texto or "RESOURCE_EXHAUSTED" in texto:
            raise Exception("LIMITE_DIARIO_ATINGIDO")
        print(f"Erro na IA: {erro}")
        return None


if __name__ == "__main__":
    print(f"Testando o modelo {MODELO}...\n")
    resultado = processar_noticia(
        "Studio sets release date for sci-fi sequel",
        "The studio said on Monday that the sequel will reach theaters next summer, "
        "with most of the original cast returning.",
    )
    if resultado:
        print("FUNCIONOU!\n")
        for campo, valor in resultado.items():
            print(f"{campo}: {valor}\n")
    else:
        print("A chave foi aceita, mas a resposta veio com problema. Copie a mensagem acima e me mande.")