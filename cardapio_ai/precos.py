"""Conversão de preços escritos à mão para número.

Cardápios brasileiros escrevem preço de muitos jeitos: "R$ 29,90", "29,9",
"R$29", "1.200,00". O LLM às vezes devolve o texto em vez do número. Por isso
a conversão é feita aqui, em código determinístico, e não confiada ao modelo.
"""
from __future__ import annotations

import re

_NUMERO = re.compile(r"\d[\d.,]*\d|\d")
_SEM_PRECO = ("consulta", "consultar", "consulte", "variavel", "variável", "a combinar")
# Número seguido de unidade não é preço: "350ml", "2 litros", "160g", "18h", "8 fatias", "100%".
_UNIDADE = re.compile(
    r"\s*(?:ml|l|litros?|g|gr|gramas?|kg|h|hs|horas?|min|cm"
    r"|fatias?|pessoas?|unidades?|un|pe[cç]as?)\b|\s*%",
    re.IGNORECASE,
)
# Preço escrito de forma inequívoca: com centavos ("29,90", "12.50") ou depois de "R$".
_CENTAVOS = re.compile(r"[.,]\d{2}$")
_ANTES_REAIS = re.compile(r"r\$\s*$", re.IGNORECASE)


def normalizar_preco(valor) -> float | None:
    """Converte qualquer forma de preço em float com 2 casas, ou None se não houver preço."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    texto = str(valor).strip().lower()
    if not texto or any(termo in texto for termo in _SEM_PRECO):
        return None
    achado = _NUMERO.search(texto)
    return _converter(achado.group()) if achado else None


def precos_no_texto(texto: str) -> set[float]:
    """Todos os números que podem ser preço num texto. Usado para detectar preço inventado.

    Ignora números que são medidas ("350ml", "2 litros", "18h"): se o modelo usar um deles
    como preço, a regra de alucinação pega.
    """
    return {preco for _, preco in _numeros_preco(texto)}


def precos_explicitos(texto: str) -> set[float]:
    """Só os preços escritos sem ambiguidade: com centavos ou depois de "R$".

    "2 Smash Duplo" ou "serve 2" não entram. Usado para achar itens que o modelo esqueceu,
    onde um falso alarme custa mais do que deixar passar um preço inteiro.
    """
    return {
        preco
        for achado, preco in _numeros_preco(texto)
        if _CENTAVOS.search(achado.group()) or _ANTES_REAIS.search(texto[: achado.start()])
    }


def _numeros_preco(texto: str):
    for achado in _NUMERO.finditer(texto):
        # Com centavos é preço mesmo antes de letra: em "P 39,90 G 59,90" o G é tamanho.
        if not _CENTAVOS.search(achado.group()) and _UNIDADE.match(texto, achado.end()):
            continue
        preco = _converter(achado.group())
        if preco is not None:
            yield achado, preco


def _converter(numero: str) -> float | None:
    if "," in numero and "." in numero:
        if numero.rfind(",") > numero.rfind("."):  # 1.200,50
            numero = numero.replace(".", "").replace(",", ".")
        else:  # 1,200.50
            numero = numero.replace(",", "")
    elif "," in numero:
        inteiro, _, decimal = numero.rpartition(",")
        if len(decimal) in (1, 2):  # 29,9 ou 29,90
            numero = inteiro.replace(",", "") + "." + decimal
        else:  # 1,200
            numero = numero.replace(",", "")
    elif "." in numero:
        _, _, decimal = numero.rpartition(".")
        if len(decimal) == 3:  # 1.200 é mil e duzentos
            numero = numero.replace(".", "")
    try:
        return round(float(numero), 2)
    except ValueError:  # algo como "1.2.3"
        return None
