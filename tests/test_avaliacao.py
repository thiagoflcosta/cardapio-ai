from cardapio_ai.avaliacao import comparar, similaridade
from cardapio_ai.models import Cardapio


def _cardapio(*itens):
    return Cardapio.model_validate({"itens": list(itens)})


def test_nome_com_categoria_na_frente_casa():
    assert similaridade("Margherita", "Pizza Margherita") >= 0.75


def test_nomes_diferentes_nao_casam():
    assert similaridade("Pudim de leite", "Suco natural") < 0.75


def test_comparacao_perfeita():
    gabarito = _cardapio(
        {"nome": "Margherita", "categoria": "pizza", "variacoes": [{"nome": "P", "preco": 39.9}]}
    )
    resultado = comparar(gabarito, gabarito)
    assert (resultado.casados, resultado.preco_ok, resultado.categoria_ok, resultado.prontos) == (1, 1, 1, 1)
    assert resultado.divergencias == []


def test_detecta_item_faltando_e_preco_errado():
    gabarito = _cardapio(
        {"nome": "Pudim", "categoria": "sobremesa", "preco": 9},
        {"nome": "Suco", "categoria": "bebida", "preco": 8.5},
    )
    extraido = _cardapio({"nome": "Pudim de leite", "categoria": "sobremesa", "preco": 9.9})
    resultado = comparar(gabarito, extraido)
    assert resultado.casados == 1
    assert resultado.preco_ok == 0
    assert "faltou: Suco" in resultado.divergencias
