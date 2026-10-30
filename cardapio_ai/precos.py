"""Conversão de preços escritos à mão para número.

Cardápios brasileiros escrevem preço de muitos jeitos: "R$ 29,90", "29,9",
"R$29", "1.200,00". O LLM às vezes devolve o texto em vez do número. Por isso
a conversão é feita aqui, em código determinístico, e não confiada ao modelo.
"""
from __future__ import annotations

import re

_NUMERO = re.compile(r"\d[\d.,]*\d|\d")
_SEM_PRECO = ("consulta", "consultar", "variavel", "variável", "a combinar")


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
    """Todos os números que parecem preço num texto. Usado para detectar preço inventado."""
    precos = (_converter(numero) for numero in _NUMERO.findall(texto))
    return {preco for preco in precos if preco is not None}


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
