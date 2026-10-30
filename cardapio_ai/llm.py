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

    def completar(self, sistema: str, usuario: str) -> RespostaLLM: ...


class ProvedorOpenAICompativel:
    """Qualquer API no formato da OpenAI: a própria OpenAI, o Ollama local e outras."""

    def __init__(
        self,
        modelo: str,
        base_url: str | None = None,
        api_key: str | None = None,
        json_mode: bool = True,
        temperatura: float = 0.0,
        timeout: float = 120.0,
    ):
        from openai import OpenAI  # importado aqui para os testes não dependerem do pacote

        self.nome = modelo
        self.json_mode = json_mode
        self.temperatura = temperatura  # 0 = respostas mais estáveis entre execuções
        # O Ollama ignora a chave, mas a biblioteca exige uma.
        self._cliente = OpenAI(base_url=base_url, api_key=api_key or "nao-usada", timeout=timeout)

    def completar(self, sistema: str, usuario: str) -> RespostaLLM:
        from openai import APIConnectionError, APIError

        extras = {"response_format": {"type": "json_object"}} if self.json_mode else {}
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
            raise ErroProvedor(f"O provedor recusou o pedido ({status or 'sem código'}): {erro}") from erro
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

    def __init__(self, respostas: list[str]):
        self._respostas = list(respostas)
        self.chamadas: list[tuple[str, str]] = []

    def completar(self, sistema: str, usuario: str) -> RespostaLLM:
        self.chamadas.append((sistema, usuario))
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
    return ProvedorOpenAICompativel(
        modelo=modelo,
        base_url=base_url,
        api_key=api_key,
        json_mode=os.getenv("LLM_JSON_MODE", "1") != "0",
    )
