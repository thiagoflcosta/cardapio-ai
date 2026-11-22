# CardápioAI

[![CI](https://github.com/thiagoflcosta/cardapio-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/thiagoflcosta/cardapio-ai/actions/workflows/ci.yml)

Transforma o cardápio de um restaurante em um catálogo estruturado para delivery: itens, preços, tamanhos, categorias e tags. O que o sistema não tem certeza vai para revisão humana, em vez de ser publicado errado.

## O problema

Restaurantes mandam cardápio em todo formato: texto de WhatsApp, PDF, foto. Alguém precisa transformar isso em itens cadastrados, com preço, categoria e tamanhos. É trabalho manual, repetitivo e sujeito a erro, e um preço errado no app vira prejuízo ou reclamação.

Um LLM resolve boa parte do trabalho, mas erra com confiança: inventa preço, troca categoria, esquece item. Este projeto trata o LLM como um componente que precisa ser validado e medido, não como uma caixa-preta confiável.

## Como funciona

```mermaid
flowchart LR
    A[Cardápio em texto] --> B[LLM devolve JSON<br>no formato do JSON Schema]
    B --> C{Pydantic valida?}
    C -- não --> D[Devolve o erro ao LLM] --> B
    C -- sim --> E[Regras determinísticas]
    E --> F[Catálogo + itens para revisão<br>+ alertas de item faltando]
    F -.-> G[Avaliação contra gabarito]
```

1. **Extração:** o LLM recebe o cardápio e um prompt com formato e regras. Com saída estruturada estrita, o provedor só consegue gerar JSON que segue o schema gerado a partir dos modelos Pydantic.
2. **Validação:** o Pydantic confere tipos, categorias e preços. Se falhar, o erro volta ao modelo para uma nova tentativa.
3. **Regras sem IA:** cada preço precisa existir no texto original, cada nome precisa aparecer no cardápio, preços fora da faixa e itens duplicados são marcados para revisão.
   Também procura o erro contrário, a omissão: todo preço do cardápio que nenhum item extraído usa vira um alerta de "item faltando?" apontando a linha original.
4. **Avaliação:** um conjunto de cardápios com gabarito feito à mão mede cobertura, precisão, acerto de preço, categoria e tags, além de tokens, tempo e custo.

## Decisões técnicas

| Decisão | Por quê |
|---|---|
| Saída estruturada validada com Pydantic | O resto do sistema só recebe dados no formato certo. Erro de formato vira nova tentativa, não exceção em produção. |
| Preços normalizados em código | "R$ 36,9" e "1.200,00" são convertidos de forma determinística. O modelo não precisa acertar formatação. |
| Checagem de alucinação por regras | Um preço que não existe no texto original é suspeito por definição. Essa checagem é barata, explicável e não depende de outro LLM. |
| Provedor de LLM trocável | O extrator conversa com uma interface. Dá para comparar modelos (Ollama local, OpenAI ou outro compatível) e testar tudo sem chamar API. |
| Saída estruturada estrita (JSON Schema) | O schema sai dos mesmos modelos Pydantic, então não há dois formatos para manter. O provedor deixa de gerar JSON quebrado ou categoria inexistente; a validação do Pydantic continua como segunda barreira. Dá para voltar a `json` ou `texto` no `.env` em provedores sem suporte. |
| Detecção de item esquecido | As regras de alucinação pegam o que o modelo inventou, mas não o que ele pulou. Na primeira avaliação o gpt-4o-mini pulou a borda escrita como "+ R$ 8,00"; a regra de preço órfão pega esse caso, que virou teste. Só conta preços inequívocos (com centavos ou "R$") para não gerar falso alarme com "2 Smash" ou "serve 2". |
| Medidas não contam como preço | "350ml", "2 litros", "18h" e "8 fatias" são ignorados na checagem. Antes, um preço inventado de 350,00 passaria só porque "350" aparece no texto. |
| Avaliação com gabarito | Toda mudança de prompt ou modelo é medida. Sem número de antes e depois, não há como saber se melhorou. |
| Temperatura 0 | Respostas mais estáveis entre execuções, o que torna a avaliação comparável. |

## Rodando

Requisitos: Python 3.11 ou mais novo.

```bash
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # no Windows: copy .env.example .env
```

Configure o modelo no `.env`:

- **Grátis, local:** instale o [Ollama](https://ollama.com), baixe um modelo e coloque o nome dele em `LLM_MODELO`. Mantenha `LLM_BASE_URL=http://localhost:11434/v1`.
- **API:** qualquer provedor compatível com a API da OpenAI. Preencha `LLM_API_KEY`, `LLM_MODELO` e, se não for a OpenAI, `LLM_BASE_URL`.
- **Formato da resposta:** `LLM_FORMATO=schema` (padrão) usa saída estruturada estrita. Se o provedor recusar, use `json` ou `texto`.

Use:

```bash
python -m cardapio_ai extrair dados/cardapios/pizzaria_bella_nonna.txt
python -m cardapio_ai avaliar --detalhes
pytest
```

Os testes não chamam nenhum modelo: usam um provedor falso. O GitHub Actions roda `ruff check` e `pytest` em Python 3.11, 3.12 e 3.13 a cada push.

## Resultados

Cada linha é uma execução de `python -m cardapio_ai avaliar`. "Prontos" é a métrica principal: itens com nome, preço e categoria certos, que poderiam ser publicados sem correção.

| Data | Modelo | Prompt | Formato | Cardápios | Itens | Cobertura | Preço | Categoria | Prontos | Custo |
|---|---|---|---|---|---|---|---|---|---|---|
| 30/10/2026 | gpt-4o-mini | v1 | json | 3 | 39 | 97% | 100% | 95% | 92% | – |
| 22/11/2026 | gpt-4o-mini | v1 | schema | 3 (os mesmos) | 39 | 97% | 100% | 100% | 97% | – |
| 22/11/2026 | gpt-4o-mini | v1 | schema | 6 | 82 | 94% | 99% | 94% | 87% | ~US$ 0,005 |

Nos 3 cardápios originais, a mudança para JSON Schema coincidiu com as pizzas doces passando a sair como "pizza", mas é uma execução só: pode ser variação. A borda continuou de fora, só que agora gera o alerta "item faltando?". Nos cardápios novos, os erros que sobraram mostram o que atacar no prompt v2:

- **Açaí:** os adicionais escritos como "+3" foram ignorados, e a regra de item faltando não vê preço sem centavos.
- **Tags inventadas:** "contem_alcool" apareceu em refrigerante e água de coco. Nenhuma regra checa tags hoje.
- **Chopp:** o tamanho de 300ml virou preço do item em vez de variação.
- **Categorias ambíguas:** açaí saiu como "outro", e as chapas para compartilhar saíram como "prato_principal".

**Métricas**

- **Cobertura:** itens do gabarito que o sistema encontrou.
- **Precisão:** itens extraídos que existem no gabarito (o resto é invenção ou divisão errada).
- **Preço, categoria, tags:** acerto entre os itens encontrados.
- **Prontos:** itens do gabarito encontrados com preço e categoria certos.
- **Revisão:** itens que as regras ou o modelo marcaram para conferência humana.
- **Alerta de falta:** linhas do cardápio com preço que nenhum item extraído usa.

## Limitações conhecidas

- Por enquanto lê só texto. PDF e foto estão no roteiro.
- O conjunto de avaliação tem 6 cardápios e 82 itens: três limpos e três difíceis (texto de WhatsApp com emojis e preços sem "R$", texto com cara de OCR com tabela em colunas, e boteco com meia/inteira). Ainda é pequeno para conclusões fortes.
- Algumas categorias são ambíguas por natureza (pizza doce é "pizza" ou "sobremesa"? açaí?). O gabarito registra uma decisão, e parte dos erros de categoria é discordância, não erro.
- A detecção de item faltando só vê preços com centavos ou "R$". Um adicional escrito "+3" que o modelo pular não gera alerta.
- Cardápios muito longos podem passar do limite de contexto do modelo.

## Estrutura

```
cardapio_ai/
  models.py      formato do catálogo e validação (Pydantic)
  precos.py      conversão de preços escritos à mão
  prompts.py     prompt do sistema e prompt de correção
  llm.py         interface com o modelo e provedor falso para testes
  extrator.py    extração com nova tentativa em caso de erro
  regras.py      checagens sem IA que marcam itens para revisão
  avaliacao.py   comparação com gabarito e métricas
  cli.py         linha de comando
dados/
  cardapios/     cardápios fictícios de teste
  gabaritos/     resposta esperada de cada cardápio
tests/
ruff.toml        regras de lint
.github/         CI (lint e testes a cada push)
```

## Próximos passos

- Ler cardápios em PDF e foto
- API com FastAPI e fila de revisão em banco de dados
- Integração com n8n: o cardápio chega por e-mail ou Telegram e os itens suspeitos vão para revisão
- Comparar modelos em acerto, custo e tempo
- Dividir cardápios longos em partes
- Serviço de catálogo em Java com Spring Boot, que recebe o JSON e publica os itens
