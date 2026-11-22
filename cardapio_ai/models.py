"""Modelos de dados do cardápio.

O LLM devolve texto; o Pydantic transforma esse texto em dados confiáveis.
Tudo o que o modelo devolve passa por aqui antes de ser usado. Se não passar,
o extrator devolve o erro ao modelo e pede correção.
"""
from __future__ import annotations

import unicodedata
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .precos import normalizar_preco


class Categoria(str, Enum):
    ENTRADA = "entrada"
    PRATO_PRINCIPAL = "prato_principal"
    LANCHE = "lanche"
    PIZZA = "pizza"
    PORCAO = "porcao"
    SOBREMESA = "sobremesa"
    BEBIDA = "bebida"
    COMBO = "combo"
    ADICIONAL = "adicional"
    OUTRO = "outro"


class Tag(str, Enum):
    VEGETARIANO = "vegetariano"
    VEGANO = "vegano"
    SEM_GLUTEN = "sem_gluten"
    SEM_LACTOSE = "sem_lactose"
    PICANTE = "picante"
    CONTEM_ALCOOL = "contem_alcool"


def slug(valor: str) -> str:
    """'Prato Principal' vira 'prato_principal'; 'Sem glúten' vira 'sem_gluten'."""
    sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode()
    return "_".join(sem_acento.lower().replace("-", " ").split())


class Variacao(BaseModel):
    """Tamanho ou versão de um item com preço próprio (P/M/G, lata/2 litros)."""

    nome: str = Field(min_length=1)
    preco: float | None = Field(default=None, ge=0)

    @field_validator("preco", mode="before")
    @classmethod
    def _normaliza_preco(cls, valor):
        return normalizar_preco(valor)


class ItemCardapio(BaseModel):
    nome: str = Field(min_length=1)
    descricao: str | None = None
    categoria: Categoria
    preco: float | None = Field(default=None, ge=0)
    variacoes: list[Variacao] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    precisa_revisao: bool = False
    motivo_revisao: str | None = None

    @field_validator("nome", mode="before")
    @classmethod
    def _limpa_nome(cls, valor):
        return " ".join(str(valor).split()) if isinstance(valor, str) else valor

    @field_validator("preco", mode="before")
    @classmethod
    def _normaliza_preco(cls, valor):
        return normalizar_preco(valor)

    @field_validator("categoria", mode="before")
    @classmethod
    def _normaliza_categoria(cls, valor):
        # Aceita "Prato Principal" ou "BEBIDA"; uma categoria inexistente ainda reprova.
        return slug(valor) if isinstance(valor, str) else valor

    @field_validator("tags", mode="before")
    @classmethod
    def _filtra_tags(cls, valor):
        # Decisão: tag desconhecida é descartada, em vez de reprovar o item inteiro.
        if not valor:
            return []
        validas = {tag.value for tag in Tag}
        slugs = (slug(v) for v in valor if isinstance(v, str))
        return list(dict.fromkeys(s for s in slugs if s in validas))


class Cardapio(BaseModel):
    restaurante: str | None = None
    itens: list[ItemCardapio] = Field(min_length=1)


# Palavras do JSON Schema que o modo estrito da OpenAI aceita. O resto (default, title,
# minLength, minimum...) sai do schema enviado e continua sendo checado pelo Pydantic.
_CHAVES_SCHEMA = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "anyOf", "$ref", "$defs",
    "description",
}


def schema_estrito(modelo: type[BaseModel] = Cardapio) -> dict:
    """JSON Schema do modelo no formato de saída estruturada estrita (OpenAI, Ollama e compatíveis).

    No modo estrito o provedor só gera tokens que respeitam o schema: JSON quebrado, campo
    faltando e categoria inventada deixam de acontecer na origem. Exigências do modo estrito:
    todo campo é obrigatório (opcional vira "tipo ou null") e não pode haver campo extra.
    """

    def limpar(no):
        if isinstance(no, list):
            return [limpar(x) for x in no]
        if not isinstance(no, dict):
            return no
        saida = {}
        for chave, valor in no.items():
            if chave not in _CHAVES_SCHEMA:
                continue
            if chave in ("properties", "$defs"):
                saida[chave] = {nome: limpar(sub) for nome, sub in valor.items()}
            else:
                saida[chave] = limpar(valor)
        if "properties" in saida:
            saida["required"] = list(saida["properties"])
            saida["additionalProperties"] = False
        return saida

    return limpar(modelo.model_json_schema())
