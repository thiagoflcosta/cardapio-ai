import pytest

from cardapio_ai.precos import normalizar_preco, precos_explicitos, precos_no_texto


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("R$ 29,90", 29.9),
        ("29,9", 29.9),
        ("R$29", 29.0),
        ("1.200,00", 1200.0),
        ("12.50", 12.5),
        ("1.200", 1200.0),
        (34.9, 34.9),
        (10, 10.0),
        ("sob consulta", None),
        ("Consultar", None),
        ("consulte", None),
        ("grátis", None),
        ("", None),
        (None, None),
        (True, None),
    ],
)
def test_normalizar_preco(entrada, esperado):
    assert normalizar_preco(entrada) == esperado


def test_precos_no_texto():
    texto = "Burger ..... R$32,90\nCheddar ..... R$36,9\nRefri lata ..... 6,50"
    assert {32.9, 36.9, 6.5} <= precos_no_texto(texto)


def test_medidas_nao_contam_como_preco():
    texto = (
        "Refrigerante lata 350ml R$ 6,00 | 2 litros R$ 14,00\n"
        "Blend 160g, aberto das 18h às 23h, 8 fatias, 100% vegano"
    )
    precos = precos_no_texto(texto)
    assert {6.0, 14.0} <= precos
    assert not {350.0, 2.0, 160.0, 18.0, 23.0, 8.0, 100.0} & precos


def test_preco_inteiro_sem_unidade_continua_valendo():
    assert 15.0 in precos_no_texto("Açaí 300ml 15 / 500ml 20")
    assert 300.0 not in precos_no_texto("Açaí 300ml 15 / 500ml 20")


def test_precos_explicitos_exigem_centavos_ou_real():
    texto = "COMBO = 2 Smash + batata ..... R$ 44,90\nBorda ... + R$ 8\nÁgua ..... 4,00\n(serve 2)"
    assert precos_explicitos(texto) == {44.9, 8.0, 4.0}


def test_tamanho_depois_do_preco_nao_atrapalha():
    assert {39.9, 49.9, 59.9} <= precos_no_texto("Margherita P 39,90 M 49,90 G 59,90")
