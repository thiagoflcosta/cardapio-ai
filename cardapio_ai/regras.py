"""Regras determinísticas que marcam itens para revisão humana.

O LLM erra com confiança. Estas regras não usam IA: comparam a saída com o
texto original e com limites simples, e marcam o que uma pessoa deve conferir
antes de publicar. É a principal defesa contra alucinação do projeto.
"""
from __future__ import annotations

import unicodedata

from .models import Cardapio, ItemCardapio
from .precos import precos_no_texto

PRECO_MINIMO = 1.0
PRECO_MAXIMO = 500.0
FRACAO_MINIMA_NOME = 0.6  # parte das palavras do nome que precisa existir no texto


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sem acento e sem pontuação: 'Pão Brioche!' vira 'pao brioche'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in sem_acento).split())


def aplicar_regras(cardapio: Cardapio, texto_original: str) -> tuple[Cardapio, list[str]]:
    """Devolve o cardápio com os itens suspeitos marcados e a lista de alertas."""
    precos_validos = precos_no_texto(texto_original)
    palavras_texto = set(normalizar_texto(texto_original).split())
    vistos: set[str] = set()
    itens: list[ItemCardapio] = []
    alertas: list[str] = []

    for item in cardapio.itens:
        motivos = _motivos(item, precos_validos, palavras_texto, vistos)
        vistos.add(normalizar_texto(item.nome))
        if motivos:
            anteriores = [item.motivo_revisao] if item.motivo_revisao else []
            item = item.model_copy(
                update={"precisa_revisao": True, "motivo_revisao": "; ".join(anteriores + motivos)}
            )
            alertas.append(f"{item.nome}: {'; '.join(motivos)}")
        elif item.precisa_revisao:
            alertas.append(f"{item.nome}: {item.motivo_revisao or 'marcado pelo modelo'}")
        itens.append(item)

    return cardapio.model_copy(update={"itens": itens}), alertas


def _motivos(
    item: ItemCardapio, precos_validos: set[float], palavras_texto: set[str], vistos: set[str]
) -> list[str]:
    motivos: list[str] = []

    precos = [item.preco] if item.preco is not None else []
    precos += [v.preco for v in item.variacoes if v.preco is not None]
    if not precos:
        motivos.append("sem preço")
    for preco in precos:
        if not PRECO_MINIMO <= preco <= PRECO_MAXIMO:
            motivos.append(f"preço fora da faixa esperada ({preco:.2f})")
        if preco not in precos_validos:
            motivos.append(f"preço {preco:.2f} não aparece no cardápio original")

    palavras_nome = [p for p in normalizar_texto(item.nome).split() if len(p) >= 3]
    if palavras_nome:
        encontradas = sum(_aparece(p, palavras_texto) for p in palavras_nome)
        if encontradas / len(palavras_nome) < FRACAO_MINIMA_NOME:
            motivos.append("nome não encontrado no cardápio original")

    if normalizar_texto(item.nome) in vistos:
        motivos.append("item duplicado")

    return motivos


def _aparece(palavra: str, palavras_texto: set[str]) -> bool:
    """Aceita plural e singular: 'pizza' conta como presente se o texto diz 'pizzas'."""
    if palavra in palavras_texto:
        return True
    if len(palavra) < 4:
        return False
    return any(
        len(outra) >= 4 and (outra.startswith(palavra) or palavra.startswith(outra))
        for outra in palavras_texto
    )
