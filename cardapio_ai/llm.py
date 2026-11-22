"""Acesso ao modelo de linguagem.

O resto do código conversa com a interface ProvedorLLM, e não com uma
biblioteca específica. Assim dá para trocar de modelo (Ollama local, OpenAI ou
outra API compatível) sem mexer no extrator, e testar tudo com um provedor falso.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol


class ErroProvedor(RuntimeError):
    """Falha ao falar com o modelo: servidor fora do ar, chave errada, modelo inexistente."""


@dataclass
class RespostaLLM:
    texto: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    segundos: float = 0.0


class ProvedorLLM(Protocol):
    nome: str

    def completar(self, sistema: str, usuario: str, schema: dict | None = None) -> RespostaLLM: ...


FORMATOS = ("schema", "json", "texto")


def formato_resposta(formato: str, schema: dict | None) -> dict:
    """Parâmetros extras do pedido para cada modo de saída.

    - schema: saída estruturada estrita; o provedor garante JSON no formato do schema.
    - json: só garante que é JSON válido; o formato depende do prompt.
    - texto: nenhuma garantia; para provedores que não aceitam nenhum dos dois.
    """
    if formato not in FORMATOS:
        raise ValueError(f"LLM_FORMATO deve ser um de {FORMATOS}, veio {formato!r}")
    if formato == "schema" and schema is not None:
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "cardapio", "strict": True, "schema": schema},
            }
        }
    if formato in ("schema", "json"):
        return {"response_format": {"type": "json_object"}}
    return {}


class ProvedorOpenAICompativel:
    """Qualquer API no formato da OpenAI: a própria OpenAI, o Ollama local e outras."""

    def __init__(
        self,
        modelo: str,
        base_url: str | None = None,
        api_key: str | None = None,
        formato: str = "schema",
        temperatura: float = 0.0,
        timeout: float = 120.0,
    ):
        from openai import OpenAI  # importado aqui para os testes não dependerem do pacote

        self.nome = modelo
        formato_resposta(formato, None)  # falha cedo se o modo for inválido
        self.formato = formato
        self.temperatura = temperatura  # 0 = respostas mais estáveis entre execuções
        # O Ollama ignora a chave, mas a biblioteca exige uma.
        self._cliente = OpenAI(base_url=base_url, api_key=api_key or "nao-usada", timeout=timeout)

    def completar(self, sistema: str, usuario: str, schema: dict | None = None) -> RespostaLLM:
        from openai import APIConnectionError, APIError

        extras = formato_resposta(self.formato, schema)
        inicio = time.perf_counter()
        try:
            resposta = self._cliente.chat.completions.create(
                model=self.nome,
                temperature=self.temperatura,
                messages=[
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
                **extras,
            )
        except APIConnectionError as erro:
            raise ErroProvedor(
                f"Não consegui conectar em {self._cliente.base_url}. O servidor (ex.: Ollama) está rodando?"
            ) from erro
        except APIError as erro:
            status = getattr(erro, "status_code", None)
            dica = " Se ele não aceita JSON Schema, use LLM_FORMATO=json no .env." if self.formato == "schema" else ""
            raise ErroProvedor(f"O provedor recusou o pedido ({status or 'sem código'}): {erro}.{dica}") from erro
        uso = resposta.usage
        return RespostaLLM(
            texto=resposta.choices[0].message.content or "",
            tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
            tokens_saida=getattr(uso, "completion_tokens", 0) or 0,
            segundos=time.perf_counter() - inicio,
        )


class ProvedorFalso:
    """Devolve respostas prontas, na ordem. Serve para testes e para treinar sem gastar."""

    nome = "falso"
    formato = "schema"

    def __init__(self, respostas: list[str]):
        self._respostas = list(respostas)
        self.chamadas: list[tuple[str, str]] = []
        self.schemas: list[dict | None] = []

    def completar(self, sistema: str, usuario: str, schema: dict | None = None) -> RespostaLLM:
        self.chamadas.append((sistema, usuario))
        self.schemas.append(schema)
        if not self._respostas:
            raise RuntimeError("ProvedorFalso ficou sem respostas")
        texto = self._respostas.pop(0)
        # Estimativa grosseira de tokens (cerca de 4 caracteres por token).
        return RespostaLLM(texto=texto, tokens_entrada=len(usuario) // 4, tokens_saida=len(texto) // 4)


def provedor_do_ambiente() -> ProvedorOpenAICompativel:
    """Monta o provedor a partir das variáveis do arquivo .env."""
    modelo = os.getenv("LLM_MODELO")
    base_url = os.getenv("LLM_BASE_URL") or None
    api_key = os.getenv("LLM_API_KEY") or None
    if not modelo:
        raise SystemExit("Defina LLM_MODELO no arquivo .env (veja o .env.example).")
    if base_url is None and api_key is None:
        raise SystemExit("Sem LLM_BASE_URL, o padrão é a OpenAI: defina LLM_API_KEY no .env.")
    # LLM_JSON_MODE=0 é a configuração antiga para "sem modo JSON"; LLM_FORMATO tem prioridade.
    formato = os.getenv("LLM_FORMATO") or ("texto" if os.getenv("LLM_JSON_MODE") == "0" else "schema")
    if formato not in FORMATOS:
        raise SystemExit(f"LLM_FORMATO deve ser um de {', '.join(FORMATOS)}.")
    return ProvedorOpenAICompativel(modelo=modelo, base_url=base_url, api_key=api_key, formato=formato)
