import json

import pytest

from cardapio_ai.extrator import SCHEMA, extrair_cardapio
from cardapio_ai.llm import ProvedorFalso, formato_resposta
from cardapio_ai.models import Cardapio, schema_estrito


def _objetos(no):
    """Todos os objetos (dicts com "properties") de um schema, em qualquer profundidade."""
    if isinstance(no, dict):
        if "properties" in no:
            yield no
        for valor in no.values():
            yield from _objetos(valor)
    elif isinstance(no, list):
        for valor in no:
            yield from _objetos(valor)


def test_schema_estrito_segue_as_exigencias_do_modo_estrito():
    schema = schema_estrito(Cardapio)
    objetos = list(_objetos(schema))
    assert len(objetos) == 3  # Cardapio, ItemCardapio, Variacao
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert objeto["required"] == list(objeto["properties"])
    texto = json.dumps(schema)
    for proibida in ('"default"', '"title"', '"minLength"', '"minimum"', '"minItems"'):
        assert proibida not in texto


def test_schema_estrito_mantem_categorias_e_tags_fechadas():
    defs = schema_estrito(Cardapio)["$defs"]
    assert "pizza" in defs["Categoria"]["enum"]
    assert "vegano" in defs["Tag"]["enum"]


def test_formato_resposta_por_modo():
    schema = {"type": "object"}
    estrito = formato_resposta("schema", schema)["response_format"]
    assert estrito["type"] == "json_schema"
    assert estrito["json_schema"]["strict"] is True
    assert estrito["json_schema"]["schema"] is schema
    assert formato_resposta("json", schema) == {"response_format": {"type": "json_object"}}
    assert formato_resposta("texto", schema) == {}
    with pytest.raises(ValueError):
        formato_resposta("xml", schema)


def test_extrator_envia_o_schema_ao_provedor():
    resposta = json.dumps({"itens": [{"nome": "Coxinha", "categoria": "porcao", "preco": 7}]})
    provedor = ProvedorFalso([resposta])
    extrair_cardapio("Coxinha ..... 7,00", provedor)
    assert provedor.schemas == [SCHEMA]
