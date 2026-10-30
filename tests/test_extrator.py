import json

import pytest

from cardapio_ai.extrator import ErroExtracao, extrair_cardapio, ler_json
from cardapio_ai.llm import ProvedorFalso
from cardapio_ai.models import Categoria

TEXTO = "LANCHONETE TESTE\nX-Burger ..... R$ 25,90\nSuco de laranja ..... 8,00"
VALIDO = json.dumps(
    {
        "restaurante": "Lanchonete Teste",
        "itens": [
            {"nome": "X-Burger", "categoria": "lanche", "preco": "R$ 25,90"},
            {"nome": "Suco de laranja", "categoria": "Bebida", "preco": 8},
        ],
    }
)


def test_extrai_na_primeira_tentativa():
    resultado = extrair_cardapio(TEXTO, ProvedorFalso([VALIDO]))
    assert resultado.tentativas == 1
    assert resultado.cardapio.itens[0].preco == 25.9
    assert resultado.cardapio.itens[1].categoria is Categoria.BEBIDA
    assert resultado.alertas == []


def test_corrige_resposta_invalida_na_segunda_tentativa():
    provedor = ProvedorFalso(["isto não é JSON", VALIDO])
    resultado = extrair_cardapio(TEXTO, provedor)
    assert resultado.tentativas == 2
    assert "não passou na validação" in provedor.chamadas[1][1]


def test_desiste_depois_das_tentativas():
    vazio = '{"itens": []}'
    with pytest.raises(ErroExtracao):
        extrair_cardapio(TEXTO, ProvedorFalso([vazio, vazio]))


def test_le_json_dentro_de_bloco_de_codigo():
    assert ler_json('Aqui está:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_marca_preco_inventado_para_revisao():
    inventado = json.dumps({"itens": [{"nome": "X-Burger", "categoria": "lanche", "preco": 99.9}]})
    item = extrair_cardapio(TEXTO, ProvedorFalso([inventado])).cardapio.itens[0]
    assert item.precisa_revisao
    assert "não aparece" in item.motivo_revisao


def test_nome_no_plural_nao_vira_falso_alarme():
    texto = "PIZZAS\nMargherita ..... 39,90"
    resposta = json.dumps({"itens": [{"nome": "Pizza Margherita", "categoria": "pizza", "preco": 39.9}]})
    item = extrair_cardapio(texto, ProvedorFalso([resposta])).cardapio.itens[0]
    assert not item.precisa_revisao


def test_marca_item_inventado_para_revisao():
    inventado = json.dumps({"itens": [{"nome": "Lasanha bolonhesa", "categoria": "prato_principal", "preco": 8}]})
    item = extrair_cardapio(TEXTO, ProvedorFalso([inventado])).cardapio.itens[0]
    assert "nome não encontrado" in item.motivo_revisao
