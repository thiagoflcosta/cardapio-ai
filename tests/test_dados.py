"""Confere os próprios dados de teste: um gabarito errado estraga toda a avaliação."""
from pathlib import Path

import pytest

from cardapio_ai.avaliacao import avaliar
from cardapio_ai.cli import main
from cardapio_ai.llm import ProvedorFalso
from cardapio_ai.models import Cardapio
from cardapio_ai.precos import precos_no_texto
from cardapio_ai.regras import precos_orfaos

DADOS = Path(__file__).resolve().parent.parent / "dados"
CARDAPIOS = sorted((DADOS / "cardapios").glob("*.txt"))


def _gabarito(caminho: Path) -> Cardapio:
    return Cardapio.model_validate_json((DADOS / "gabaritos" / f"{caminho.stem}.json").read_text(encoding="utf-8"))


def _respostas_perfeitas() -> list[str]:
    return [(DADOS / "gabaritos" / f"{c.stem}.json").read_text(encoding="utf-8") for c in CARDAPIOS]


def test_existem_cardapios_de_teste():
    assert len(CARDAPIOS) >= 3


@pytest.mark.parametrize("caminho", CARDAPIOS, ids=lambda p: p.stem)
def test_precos_do_gabarito_existem_no_cardapio(caminho):
    precos = precos_no_texto(caminho.read_text(encoding="utf-8"))
    for item in _gabarito(caminho).itens:
        for preco in [item.preco, *(v.preco for v in item.variacoes)]:
            if preco is not None:
                assert preco in precos, f"{item.nome}: {preco}"


def test_gabarito_como_resposta_tira_nota_maxima_sem_falso_alarme():
    resultados = avaliar(DADOS, ProvedorFalso(_respostas_perfeitas()))
    for resultado, caminho in zip(resultados, CARDAPIOS, strict=True):
        gabarito = _gabarito(caminho)
        assert resultado.comparacao.prontos == resultado.comparacao.itens_gabarito
        # Só o que não tem preço deve ir para revisão: nenhum falso alarme das regras.
        sem_preco = sum(1 for i in gabarito.itens if i.preco is None and not i.variacoes)
        assert resultado.marcados_revisao == sem_preco


def test_cli_avaliar_salva_resultado(tmp_path, capsys):
    codigo = main(
        ["avaliar", "--dados", str(DADOS), "--saida", str(tmp_path)],
        provedor=ProvedorFalso(_respostas_perfeitas()),
    )
    assert codigo == 0
    assert list(tmp_path.glob("avaliacao-*.json"))
    assert "Total" in capsys.readouterr().out


@pytest.mark.parametrize("caminho", CARDAPIOS, ids=lambda p: p.stem)
def test_gabarito_nao_gera_alerta_de_item_faltando(caminho):
    """Se a extração estiver perfeita, a regra de preço órfão não pode reclamar."""
    assert precos_orfaos(_gabarito(caminho), caminho.read_text(encoding="utf-8")) == []


def test_regra_pega_a_borda_que_o_gpt_4o_mini_esqueceu():
    """Caso real da primeira avaliação: o modelo pulou o item escrito como "+ R$ 8,00"."""
    caminho = DADOS / "cardapios" / "pizzaria_bella_nonna.txt"
    sem_borda = _gabarito(caminho)
    sem_borda.itens = [i for i in sem_borda.itens if not i.nome.startswith("Borda")]
    alertas = precos_orfaos(sem_borda, caminho.read_text(encoding="utf-8"))
    assert len(alertas) == 1 and "Borda recheada" in alertas[0]
