# Versões e referências

Registro do que foi efetivamente usado para construir este laboratório e do
quanto disso é realmente reprodutível.

## Versões

| Componente | Versão | Como está declarado |
| --- | --- | --- |
| SDK oficial Python do MCP (`mcp`) | 2.2.0 | fixado em `pyproject.toml` e no `uv.lock` |
| `httpx2` (cliente HTTP assíncrono) | 2.13.0 | fixado em `pyproject.toml` e no `uv.lock` |
| `pydantic` | 2.13.5 | fixado em `pyproject.toml` e no `uv.lock` |
| `pytest` | 9.1.1 | fixado no grupo `dev` do `pyproject.toml` |
| `anyio` (plugin pytest para testes assíncronos) | 4.15.1 | fixado no grupo `dev` do `pyproject.toml` |
| Python | linha 3.12 (3.12.12 na execução verificada em 16/09/2026) | `requires-python = ">=3.12,<3.13"` e a tag da imagem base |
| Imagem de execução | `python:3.12-slim-bookworm` | tag de linha no `Dockerfile` |
| Imagem de build | `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` | tag de linha no `Dockerfile` |
| `uv` | o que vier nessa tag (0.9.30 na execução verificada) | não fixado |

## O que é reprodutível e o que não é

Vale ser exato aqui, porque "fixado" é uma palavra forte.

**Reprodutível:** as dependências Python. O `uv.lock` resolve 37 pacotes, com
versão e hash, incluindo as transitivas (entre elas `starlette` 1.6.0 e
`uvicorn` 0.53.0). `uv sync --locked` falha se o lock não corresponder ao
`pyproject.toml`, então todo ambiente instala o mesmo conjunto de pacotes.

**Não fixado, e tudo bem para um laboratório didático:**

- **As imagens base.** `python:3.12-slim-bookworm` e
  `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` são tags de linha: elas
  continuam apontando para 3.12, mas recebem correções de segurança e mudanças
  de patch com o tempo. Duas construções em datas diferentes podem trazer
  Python 3.12.x diferentes e versões diferentes do `uv`. Fixar por digest
  (`python:3.12-slim-bookworm@sha256:...`) congelaria isso, ao custo de ter que
  atualizar o digest na mão a cada correção de segurança — um preço que faz
  sentido em produção, não neste laboratório.
- **O backend de build.** `[build-system] requires = ["hatchling"]` não tem
  versão e é resolvido no momento do build, fora do `uv.lock`. O lock descreve
  o que o projeto instala, não o que constrói o pacote.

Em resumo: o `uv.lock` garante as dependências da aplicação, não "tudo o que
acontece no build".

## Por que `httpx2` e não `httpx`

O `mcp` 2.2.0 declara `httpx2>=2.5.0` como dependência (não `httpx`). O
`httpx2` é a continuação do `httpx`, mantida em
<https://github.com/pydantic/httpx2>, com a mesma API pública
(`AsyncClient`, `Timeout`, `MockTransport`, as exceções). Usar `httpx2` também
no código do servidor evita carregar duas bibliotecas HTTP no mesmo ambiente.

Verificação feita: `https://pypi.org/pypi/mcp/2.2.0/json` lista `httpx2>=2.5.0`
em `requires_dist`, e o código do SDK importa `httpx2` (por exemplo em
`src/mcp/client/streamable_http.py`).

## Linha 2.x do SDK, não 1.x

O SDK oficial tem duas linhas com APIs diferentes, e este projeto usa apenas a
2.x. As diferenças que mais aparecem em exemplos antigos:

| Assunto | Linha 1.x | Linha 2.x (usada aqui) |
| --- | --- | --- |
| Classe do servidor | `FastMCP` | `MCPServer`, em `mcp.server` |
| Import do contexto | `mcp.server.fastmcp` | `mcp.server.mcpserver` |
| Erro de Tool | — | `ToolError`, em `mcp.server.mcpserver.exceptions` |
| Mensagens de Prompt | `mcp.server.fastmcp.prompts.base` | `mcp.server.mcpserver.prompts.base` |
| Cliente | `ClientSession` + transporte manual | `Client("http://…/mcp")` |

Copiar um exemplo da linha 1.x para este projeto resulta em `ImportError`.

Cuidado adicional: existe no PyPI um pacote independente chamado `fastmcp`,
que **não** é o SDK oficial. Este laboratório não o utiliza.

## Referências consultadas

Consultadas em 16 de setembro de 2026.

### SDK Python do MCP

- Repositório: <https://github.com/modelcontextprotocol/python-sdk> (tag `v2.2.0`)
- Documentação: <https://py.sdk.modelcontextprotocol.io/>
- Páginas usadas diretamente:
  - `docs/servers/tools.md` — decorador `@mcp.tool()`, schema a partir dos type
    hints, `ToolAnnotations(read_only_hint=...)`
  - `docs/servers/resources.md` — `@mcp.resource(uri)`, `mime_type`
  - `docs/servers/prompts.md` — `@mcp.prompt()`, `UserMessage`, `Message`
  - `docs/servers/handling-errors.md` — quando usar `ToolError` e quando usar
    `MCPError`
  - `docs/servers/structured-output.md` — o tipo de retorno vira `output_schema`
    e `structured_content`
  - `docs/handlers/lifespan.md` — `lifespan=`, `ctx.request_context.lifespan_context`
  - `docs/run/index.md` — `mcp.run(transport="streamable-http", ...)` e as
    opções de transporte
  - `docs/run/asgi.md` — `@mcp.custom_route()` para a rota `/health`
  - `docs/run/deploy.md` — `TransportSecuritySettings`, HTTP 421 e 403
  - `docs/client/index.md` e `docs/get-started/testing.md` — `Client` por URL e
    `Client` em memória para os testes

### Protocolo MCP

- Especificação: <https://modelcontextprotocol.io/specification/>
- Guia de criação de servidores: <https://modelcontextprotocol.io/docs/develop/build-server>

A versão do protocolo é negociada pelo SDK. O servidor não implementa
handshake nem sessões manualmente; o `scripts/smoke_test.py` imprime a versão
efetivamente negociada na conexão.

### PokéAPI

- Documentação v2: <https://pokeapi.co/docs/v2>
- Endpoints usados:
  - `GET /api/v2/pokemon/{name_or_id}/`
  - `GET /api/v2/ability/{name_or_id}/`
  - `GET /api/v2/type/{name_or_id}/`
- Unidades confirmadas na documentação: o campo `height` é descrito como
  *"The height of this Pokémon in decimetres"* e `weight` como *"The weight of
  this Pokémon in hectograms"*. Daí as conversões `height_m = height / 10` e
  `weight_kg = weight / 10` feitas em `src/pokemon_mcp/models.py`.
  Conferência com dados reais: Pikachu vem como `height: 4` e `weight: 60`, o
  que resulta em 0,4 m e 6,0 kg.

#### Contrato usado na validação das respostas

As regras de `src/pokemon_mcp/models.py` não foram inventadas. Além da
documentação v2, elas foram conferidas contra a base inteira pelo endpoint
GraphQL da PokéAPI (<https://graphql.pokeapi.co/v1beta2>, consultado em
16/09/2026), o que evita criar limites que rejeitariam dados reais:

| Regra aplicada | Evidência |
| --- | --- |
| `id` ≥ 1 | menor `id` de Pokémon na base: 1 |
| `height` ≥ 0 | menor `height` observado: 1; a documentação não define mínimo, então só negativos são recusados |
| `weight` ≥ 0 (zero é válido) | `eternatus-eternamax` (id 10190) tem `weight: 0` |
| `slot` ≥ 1 | slots de habilidade vão de 1 a 3; de tipo, de 1 a 2 |
| `base_stat` ≥ 0, sem limite superior | valores reais vão de 1 (Shedinja, hp) a 255; a documentação não define faixa |
| os seis atributos base são obrigatórios | 1351 Pokémon e 8106 registros de `stat`: exatamente seis por Pokémon, os seis com `is_battle_only: false` |
| `abilities` pode ser uma lista vazia | nove Pokémon têm `abilities: []` (por exemplo `zygarde-mega`, id 10301) |
| as seis relações de dano são obrigatórias, mas podem ser listas vazias | `/type/unknown/` devolve as seis propriedades, todas vazias |

Em todos os casos a diferença que importa é a mesma: **propriedade ausente é
erro; propriedade presente e vazia é dado**.
