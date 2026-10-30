"""Extração: texto do cardápio vira um Cardapio validado.

Fluxo:
1. pede o JSON ao modelo;
2. valida com Pydantic;
3. se falhar, devolve o erro ao modelo e pede correção (até max_tentativas);
4. aplica as regras determinísticas de revisão.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from .llm import ProvedorLLM
from .models import Cardapio
from .prompts import SISTEMA, montar_pedido, montar_reparo
from .regras import aplicar_regras


class ErroExtracao(Exception):
    """O modelo não devolveu um cardápio válido dentro das tentativas."""


@dataclass
class ResultadoExtracao:
    cardapio: Cardapio
    tentativas: int
    tokens_entrada: int
    tokens_saida: int
    segundos: float
    alertas: list[str] = field(default_factory=list)


_BLOCO_CODIGO = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def ler_json(texto: str) -> dict:
    """Lê o JSON mesmo quando o modelo o embrulha em ```json ... ``` ou escreve algo antes."""
    bloco = _BLOCO_CODIGO.search(texto)
    if bloco:
        texto = bloco.group(1)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise ValueError("a resposta não contém um objeto JSON")
    return json.loads(texto[inicio : fim + 1])


def extrair_cardapio(
    texto_cardapio: str, provedor: ProvedorLLM, max_tentativas: int = 2
) -> ResultadoExtracao:
    pedido = montar_pedido(texto_cardapio)
    tokens_entrada = tokens_saida = 0
    segundos = 0.0
    ultimo_erro = ""

    for tentativa in range(1, max_tentativas + 1):
        resposta = provedor.completar(SISTEMA, pedido)
        tokens_entrada += resposta.tokens_entrada
        tokens_saida += resposta.tokens_saida
        segundos += resposta.segundos
        try:
            cardapio = Cardapio.model_validate(ler_json(resposta.texto))
        except (ValueError, ValidationError) as erro:  # JSON quebrado ou fora do formato
            ultimo_erro = str(erro)
            pedido = montar_reparo(texto_cardapio, resposta.texto, ultimo_erro)
            continue
        cardapio, alertas = aplicar_regras(cardapio, texto_cardapio)
        return ResultadoExtracao(cardapio, tentativa, tokens_entrada, tokens_saida, segundos, alertas)

    raise ErroExtracao(
        f"{max_tentativas} tentativas sem um cardápio válido. Último erro: {ultimo_erro[:500]}"
    )
