"""Linha de comando.

    python -m cardapio_ai extrair dados/cardapios/pizzaria_bella_nonna.txt
    python -m cardapio_ai avaliar --detalhes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .avaliacao import avaliar, tabela_markdown
from .extrator import ErroExtracao, extrair_cardapio
from .llm import ErroProvedor, ProvedorLLM, provedor_do_ambiente
from .prompts import VERSAO_PROMPT


def main(argv: list[str] | None = None, provedor: ProvedorLLM | None = None) -> int:
    _carregar_env()
    parser = argparse.ArgumentParser(
        prog="cardapio_ai", description="Transforma cardápios em catálogo estruturado com LLM."
    )
    comandos = parser.add_subparsers(dest="comando", required=True)

    extrair = comandos.add_parser("extrair", help="extrai um cardápio .txt e imprime o JSON")
    extrair.add_argument("arquivo", type=Path)

    avaliar_ = comandos.add_parser("avaliar", help="compara a extração com os gabaritos")
    avaliar_.add_argument("--dados", type=Path, default=Path("dados"))
    avaliar_.add_argument("--saida", type=Path, default=Path("resultados"))
    avaliar_.add_argument("--detalhes", action="store_true", help="mostra cada divergência")

    args = parser.parse_args(argv)
    provedor = provedor or provedor_do_ambiente()

    try:
        if args.comando == "extrair":
            return _extrair(args.arquivo, provedor)
        return _avaliar(args.dados, args.saida, args.detalhes, provedor)
    except ErroProvedor as erro:
        print(f"Erro ao falar com o modelo: {erro}", file=sys.stderr)
        return 2


def _extrair(arquivo: Path, provedor: ProvedorLLM) -> int:
    try:
        resultado = extrair_cardapio(arquivo.read_text(encoding="utf-8"), provedor)
    except ErroExtracao as erro:
        print(f"Falhou: {erro}", file=sys.stderr)
        return 1
    print(resultado.cardapio.model_dump_json(indent=2))
    print(
        f"\n{len(resultado.cardapio.itens)} itens | {resultado.tentativas} tentativa(s) | "
        f"{resultado.tokens_entrada}/{resultado.tokens_saida} tokens | {resultado.segundos:.1f}s",
        file=sys.stderr,
    )
    for alerta in resultado.alertas:
        print(f"  revisar: {alerta}", file=sys.stderr)
    return 0


def _avaliar(dados: Path, saida: Path, detalhes: bool, provedor: ProvedorLLM) -> int:
    resultados = avaliar(dados, provedor)
    if not resultados:
        print(f"Nenhum par cardápio/gabarito encontrado em {dados}.", file=sys.stderr)
        return 1

    print(f"Modelo: {provedor.nome} | Prompt: {VERSAO_PROMPT}\n")
    print(tabela_markdown(resultados))
    custo = _custo(resultados)
    if custo is not None:
        print(f"\nCusto estimado: US$ {custo:.4f}")
    if detalhes:
        for r in resultados:
            if r.comparacao.divergencias:
                print(f"\n{r.arquivo}:")
                for divergencia in r.comparacao.divergencias:
                    print(f"  - {divergencia}")

    saida.mkdir(parents=True, exist_ok=True)
    arquivo = saida / f"avaliacao-{datetime.now():%Y%m%d-%H%M%S}.json"
    registro = {
        "data": datetime.now().isoformat(timespec="seconds"),
        "modelo": provedor.nome,
        "prompt": VERSAO_PROMPT,
        "custo_usd": custo,
        "resultados": [asdict(r) for r in resultados],
    }
    arquivo.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultado salvo em {arquivo}")
    return 0


def _custo(resultados) -> float | None:
    """Usa os preços por 1 milhão de tokens do .env, se você os definir."""
    entrada = os.getenv("LLM_CUSTO_ENTRADA_1M")
    saida = os.getenv("LLM_CUSTO_SAIDA_1M")
    if not entrada or not saida:
        return None
    tokens_e = sum(r.tokens_entrada for r in resultados)
    tokens_s = sum(r.tokens_saida for r in resultados)
    return (tokens_e * float(entrada) + tokens_s * float(saida)) / 1_000_000


def _carregar_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()
