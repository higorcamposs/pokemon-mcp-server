# Versões e referências

Registro do que foi efetivamente usado para construir este laboratório, para
que qualquer pessoa consiga reproduzir o mesmo ambiente.

## Versões fixadas

| Componente | Versão | Onde está fixado |
| --- | --- | --- |
| Python | 3.12 (imagem `python:3.12-slim-bookworm`; 3.12.14 na execução verificada) | `Dockerfile`, `requires-python` no `pyproject.toml` |
| SDK oficial Python do MCP (`mcp`) | 2.2.0 | `pyproject.toml` e `uv.lock` |
| `httpx2` (cliente HTTP assíncrono) | 2.13.0 | `pyproject.toml` e `uv.lock` |
| `pydantic` | 2.13.5 | `pyproject.toml` e `uv.lock` |
| `pytest` | 9.1.1 | grupo `dev` do `pyproject.toml` |
| `anyio` (plugin pytest para testes assíncronos) | 4.15.1 | grupo `dev` do `pyproject.toml` |
| `uv` | 0.9.30, imagem `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` | `Dockerfile` |

O `uv.lock` resolve 37 pacotes e fixa também todas as dependências
transitivas (entre elas `starlette` 1.6.0 e `uvicorn` 0.53.0). É ele que garante
que a imagem construída hoje e daqui a seis meses instale o mesmo conjunto de
pacotes.

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
