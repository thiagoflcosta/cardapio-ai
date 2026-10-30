"""Textos enviados ao modelo.

Mude o prompt aqui e rode `python -m cardapio_ai avaliar` para medir o efeito.
Toda mudança de prompt deve vir acompanhada de um número antes e depois.
"""
from __future__ import annotations

from .models import Categoria, Tag

VERSAO_PROMPT = "v1"

CATEGORIAS = ", ".join(f'"{c.value}"' for c in Categoria)
TAGS = ", ".join(f'"{t.value}"' for t in Tag)

EXEMPLO = """{
  "restaurante": "Nome do restaurante ou null",
  "itens": [
    {
      "nome": "Margherita",
      "descricao": "Molho de tomate, muçarela e manjericão",
      "categoria": "pizza",
      "preco": null,
      "variacoes": [{"nome": "P", "preco": 39.9}, {"nome": "G", "preco": 59.9}],
      "tags": [],
      "precisa_revisao": false,
      "motivo_revisao": null
    }
  ]
}"""

SISTEMA = f"""Você extrai cardápios de restaurantes para um app de delivery.
Recebe o texto de um cardápio e devolve APENAS um objeto JSON, sem comentários, neste formato:

{EXEMPLO}

Regras:
1. Não invente itens, preços ou descrições. Use só o que está no texto.
2. Use o nome do item como aparece no cardápio, sem acrescentar a categoria (ex.: "Margherita", e não "Pizza Margherita").
3. "preco" é um número em reais com ponto decimal (29.9), nunca texto.
4. Se o item tem tamanhos ou versões com preços diferentes (P/M/G, lata/2 litros), deixe "preco" como null e liste cada versão em "variacoes".
5. Se o preço não aparece ou diz "sob consulta", use "preco": null, sem variações, e marque "precisa_revisao": true com o motivo.
6. Categorias permitidas: {CATEGORIAS}. Adicionais pagos (bordas, extras) usam "adicional". Porções para compartilhar usam "porcao".
7. Tags permitidas: {TAGS}. Use uma tag só se o cardápio disser isso explicitamente, exceto "contem_alcool", que vale para qualquer bebida alcoólica.
8. Combos são um item só, com categoria "combo" e o que vem nele na descrição.
9. "restaurante" é o nome do restaurante, se aparecer; senão, null."""


def montar_pedido(texto_cardapio: str) -> str:
    return f"Cardápio:\n<<<\n{texto_cardapio.strip()}\n>>>"


def montar_reparo(texto_cardapio: str, resposta_anterior: str, erro: str) -> str:
    """Segunda chance: o modelo vê a própria resposta e o erro de validação."""
    return (
        "Sua resposta anterior não passou na validação.\n"
        f"Erro:\n{erro[:1500]}\n\n"
        f"Resposta anterior:\n{resposta_anterior[:4000]}\n\n"
        "Corrija e devolva APENAS o JSON completo, no formato pedido, para o cardápio abaixo.\n\n"
        + montar_pedido(texto_cardapio)
    )
