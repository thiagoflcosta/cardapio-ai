"""Avaliação: compara a extração com um gabarito feito à mão.

Sem medir, não dá para saber se uma mudança no prompt ou no modelo melhorou
ou piorou o resultado. Cada cardápio em dados/cardapios/ tem um gabarito com
o mesmo nome em dados/gabaritos/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .extrator import ErroExtracao, extrair_cardapio
from .llm import ProvedorLLM
from .models import Cardapio, ItemCardapio
from .regras import normalizar_texto

LIMIAR_NOME = 0.75  # semelhança mínima para considerar que dois nomes são o mesmo item


@dataclass
class Comparacao:
    itens_gabarito: int
    itens_extraidos: int
    casados: int = 0
    preco_ok: int = 0
    categoria_ok: int = 0
    tags_ok: int = 0
    prontos: int = 0  # nome, preço e categoria certos: dá para publicar sem mexer
    divergencias: list[str] = field(default_factory=list)


@dataclass
class ResultadoAvaliacao:
    arquivo: str
    comparacao: Comparacao
    tentativas: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    segundos: float = 0.0
    marcados_revisao: int = 0
    erro: str | None = None


def similaridade(a: str, b: str) -> float:
    a, b = normalizar_texto(a), normalizar_texto(b)
    if a == b:
        return 1.0
    nota = SequenceMatcher(None, a, b).ratio()
    curto, longo = sorted((a, b), key=len)
    if len(curto) >= 4 and f" {curto} " in f" {longo} ":
        nota = max(nota, 0.85)  # "Margherita" dentro de "Pizza Margherita"
    return nota


def casar_itens(
    gabarito: list[ItemCardapio], extraidos: list[ItemCardapio]
) -> list[tuple[ItemCardapio, ItemCardapio]]:
    """Casa cada item do gabarito com no máximo um extraído, começando pelos pares mais parecidos."""
    pares = sorted(
        (
            (similaridade(g.nome, e.nome), i, j)
            for i, g in enumerate(gabarito)
            for j, e in enumerate(extraidos)
        ),
        reverse=True,
    )
    usados_g: set[int] = set()
    usados_e: set[int] = set()
    casados = []
    for nota, i, j in pares:
        if nota < LIMIAR_NOME:
            break
        if i in usados_g or j in usados_e:
            continue
        usados_g.add(i)
        usados_e.add(j)
        casados.append((gabarito[i], extraidos[j]))
    return casados


def comparar(gabarito: Cardapio, extraido: Cardapio) -> Comparacao:
    casados = casar_itens(gabarito.itens, extraido.itens)
    resultado = Comparacao(len(gabarito.itens), len(extraido.itens), casados=len(casados))
    ids_g = {id(g) for g, _ in casados}
    ids_e = {id(e) for _, e in casados}

    resultado.divergencias += [f"faltou: {g.nome}" for g in gabarito.itens if id(g) not in ids_g]
    resultado.divergencias += [f"sobrou: {e.nome}" for e in extraido.itens if id(e) not in ids_e]

    for g, e in casados:
        preco_ok = _precos(g) == _precos(e)
        categoria_ok = g.categoria == e.categoria
        resultado.preco_ok += preco_ok
        resultado.categoria_ok += categoria_ok
        resultado.prontos += preco_ok and categoria_ok
        if not preco_ok:
            resultado.divergencias.append(f"preço: {g.nome} esperado {_fmt(g)}, veio {_fmt(e)}")
        if not categoria_ok:
            resultado.divergencias.append(
                f"categoria: {g.nome} esperado {g.categoria.value}, veio {e.categoria.value}"
            )
        if set(g.tags) == set(e.tags):
            resultado.tags_ok += 1
        else:
            esperado = sorted(t.value for t in g.tags)
            veio = sorted(t.value for t in e.tags)
            resultado.divergencias.append(f"tags: {g.nome} esperado {esperado}, veio {veio}")

    return resultado


def avaliar(pasta_dados: Path, provedor: ProvedorLLM) -> list[ResultadoAvaliacao]:
    """Roda a extração em cada cardápio de teste e compara com o gabarito."""
    resultados = []
    for caminho in sorted((pasta_dados / "cardapios").glob("*.txt")):
        caminho_gabarito = pasta_dados / "gabaritos" / f"{caminho.stem}.json"
        if not caminho_gabarito.exists():
            continue
        gabarito = Cardapio.model_validate_json(caminho_gabarito.read_text(encoding="utf-8"))
        texto = caminho.read_text(encoding="utf-8")
        try:
            extracao = extrair_cardapio(texto, provedor)
        except ErroExtracao as erro:
            comparacao = Comparacao(len(gabarito.itens), 0, divergencias=[str(erro)])
            resultados.append(ResultadoAvaliacao(caminho.stem, comparacao, erro=str(erro)))
            continue
        resultados.append(
            ResultadoAvaliacao(
                arquivo=caminho.stem,
                comparacao=comparar(gabarito, extracao.cardapio),
                tentativas=extracao.tentativas,
                tokens_entrada=extracao.tokens_entrada,
                tokens_saida=extracao.tokens_saida,
                segundos=extracao.segundos,
                marcados_revisao=sum(i.precisa_revisao for i in extracao.cardapio.itens),
            )
        )
    return resultados


def tabela_markdown(resultados: list[ResultadoAvaliacao]) -> str:
    cabecalho = (
        "| Cardápio | Itens (gabarito/extraídos) | Cobertura | Precisão | Preço | Categoria "
        "| Tags | Prontos | Revisão | Tentativas | Tokens (entrada/saída) | Tempo |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    linhas = [cabecalho] + [_linha(r.arquivo, [r]) for r in resultados]
    if len(resultados) > 1:
        linhas.append(_linha("**Total**", resultados))
    return "\n".join(linhas)


def _linha(nome: str, resultados: list[ResultadoAvaliacao]) -> str:
    soma = lambda campo: sum(getattr(r.comparacao, campo) for r in resultados)  # noqa: E731
    gab, ext, cas = soma("itens_gabarito"), soma("itens_extraidos"), soma("casados")
    return (
        f"| {nome} | {gab}/{ext} | {_pct(cas, gab)} | {_pct(cas, ext)} "
        f"| {_pct(soma('preco_ok'), cas)} | {_pct(soma('categoria_ok'), cas)} "
        f"| {_pct(soma('tags_ok'), cas)} | {_pct(soma('prontos'), gab)} "
        f"| {sum(r.marcados_revisao for r in resultados)} "
        f"| {sum(r.tentativas for r in resultados)} "
        f"| {sum(r.tokens_entrada for r in resultados)}/{sum(r.tokens_saida for r in resultados)} "
        f"| {sum(r.segundos for r in resultados):.1f}s |"
    )


def _pct(parte: int, total: int) -> str:
    return f"{100 * parte / total:.0f}%" if total else "-"


def _precos(item: ItemCardapio) -> tuple:
    return item.preco, sorted(v.preco for v in item.variacoes if v.preco is not None)


def _fmt(item: ItemCardapio) -> str:
    if item.variacoes:
        return " / ".join(
            f"{v.nome} {v.preco:.2f}" if v.preco is not None else f"{v.nome} ?" for v in item.variacoes
        )
    return f"{item.preco:.2f}" if item.preco is not None else "sem preço"
