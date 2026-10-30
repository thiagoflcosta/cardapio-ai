import pytest

from cardapio_ai.precos import normalizar_preco, precos_no_texto


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
