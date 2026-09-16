"""MCP Server que expõe a PokéAPI como Tools, um Resource e um Prompt.

O servidor não contém nem chama nenhum LLM. Ele responde ao protocolo MCP e
consulta a PokéAPI por HTTPS; quem raciocina sobre os dados é a aplicação de
IA do outro lado da conexão.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Final, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.prompts.base import Message, UserMessage
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import models
from .pokeapi import (
    DEFAULT_BASE_URL,
    DEFAULT_CACHE_MAX_ENTRIES,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_IDENTIFIER_LENGTH,
    InvalidIdentifierError,
    MalformedResponseError,
    PokeAPIClient,
    PokeAPIError,
    ResourceNotFoundError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

logger = logging.getLogger("pokemon_mcp.server")

NameOrId = Annotated[
    str,
    Field(
        description=(
            "Nome canônico da PokéAPI (por exemplo 'pikachu') ou identificador "
            "numérico positivo (por exemplo '25')."
        ),
        min_length=1,
        # Mesmo limite que a normalização aplica, declarado no schema para que
        # o cliente rejeite a entrada antes de chegar ao servidor.
        max_length=MAX_IDENTIFIER_LENGTH,
    ),
]

READ_ONLY: Final = ToolAnnotations(read_only_hint=True, open_world_hint=True)
"""Somente leitura. `open_world_hint=True` porque os dados vêm de uma API externa."""

BuiltT = TypeVar("BuiltT")
"""Modelo devolvido por `models.build_*`."""


# --- leitura das variáveis numéricas --------------------------------------
#
# Verificar apenas o formato não basta: `float("nan")` e `float("inf")` são
# conversões válidas em Python e chegariam intactas ao `httpx2.Timeout` (timeout
# que nunca expira, ou que falha de imediato) e ao `TTLCache` (entradas que
# nunca vencem). Um valor negativo tem o mesmo problema. Nos três casos o
# servidor registra um aviso e segue com o padrão seguro, em vez de subir com
# uma configuração impossível.


def _env_float(name: str, default: float, *, allow_zero: bool) -> float:
    """Lê uma variável numérica em segundos. Recusa NaN, ±inf e negativos.

    `allow_zero` diz se zero tem significado para esta variável: o TTL do cache
    aceita 0 (desliga o cache), o tempo limite das consultas não.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r não é numérico; usando %s", name, raw, default)
        return default

    # Cobre NaN, +inf e -inf, que `float()` aceita sem reclamar.
    if not math.isfinite(value):
        logger.warning("%s=%r não é um número finito; usando %s", name, raw, default)
        return default

    if value < 0.0 or (value == 0.0 and not allow_zero):
        limite = (
            "não pode ser negativo" if allow_zero else "precisa ser maior que zero"
        )
        logger.warning("%s=%r %s; usando %s", name, raw, limite, default)
        return default

    return value


def _env_int(name: str, default: int, *, allow_zero: bool) -> int:
    """Lê uma variável numérica inteira. Recusa negativos (e 'nan'/'inf')."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    # `int()` já rejeita "nan", "inf" e "1e3" com ValueError.
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r não é inteiro; usando %s", name, raw, default)
        return default

    if value < 0 or (value == 0 and not allow_zero):
        limite = (
            "não pode ser negativo" if allow_zero else "precisa ser maior que zero"
        )
        logger.warning("%s=%r %s; usando %s", name, raw, limite, default)
        return default

    return value


@dataclass
class AppContext:
    """Objeto compartilhado por todos os handlers durante a vida do servidor."""

    pokeapi: PokeAPIClient


def create_pokeapi_client() -> PokeAPIClient:
    """Monta o cliente da PokéAPI a partir das variáveis de ambiente.

    Os testes substituem esta função para injetar um transporte simulado, o que
    mantém a suíte automatizada sem nenhuma consulta externa.
    """
    return PokeAPIClient(
        base_url=os.getenv("POKEAPI_BASE_URL", DEFAULT_BASE_URL),
        # O tempo limite precisa ser positivo: zero significaria "sem tempo".
        timeout_seconds=_env_float(
            "POKEAPI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, allow_zero=False
        ),
        # TTL e tamanho máximo aceitam zero: é assim que se desliga o cache.
        cache_ttl_seconds=_env_float(
            "POKEAPI_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS, allow_zero=True
        ),
        cache_max_entries=_env_int(
            "POKEAPI_CACHE_MAX_ENTRIES", DEFAULT_CACHE_MAX_ENTRIES, allow_zero=True
        ),
    )


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    """Cria o cliente HTTP na inicialização e o fecha no desligamento."""
    client = create_pokeapi_client()
    logger.info("cliente HTTP pronto (base_url=%s)", client.base_url)
    try:
        yield AppContext(pokeapi=client)
    finally:
        await client.aclose()
        logger.info("cliente HTTP encerrado")


INSTRUCTIONS: Final = (
    "Servidor MCP didático com dados da PokéAPI. Use get_pokemon, get_ability "
    "e get_type para consultar dados reais e cite o campo source_url nas "
    "respostas. O servidor apenas consulta e resume a PokéAPI: ele não simula "
    "batalhas nem decide vencedores."
)

mcp = MCPServer(
    "Pokémon MCP Server",
    version="0.1.0",
    instructions=INSTRUCTIONS,
    lifespan=lifespan,
    log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
)


def _to_tool_error(exc: PokeAPIError) -> ToolError:
    """Traduz a falha para uma mensagem que o modelo possa ler e corrigir."""
    if isinstance(exc, InvalidIdentifierError):
        return ToolError(f"Argumento inválido: {exc}")
    if isinstance(exc, ResourceNotFoundError):
        return ToolError(str(exc))
    if isinstance(exc, UpstreamTimeoutError):
        return ToolError(f"Tempo esgotado ao consultar a PokéAPI: {exc}")
    if isinstance(exc, UpstreamUnavailableError):
        return ToolError(f"A PokéAPI está indisponível: {exc}")
    if isinstance(exc, MalformedResponseError):
        return ToolError(f"Resposta inesperada da PokéAPI: {exc}")
    return ToolError(f"Falha ao consultar a PokéAPI: {exc}")


async def _consult(
    ctx: Context[AppContext],
    resource: str,
    name_or_id: str,
    build: Callable[[dict[str, Any], str], BuiltT],
) -> BuiltT:
    """Consulta a PokéAPI e valida a resposta com o `build_*` do recurso.

    Um `MalformedResponseError` significa que o JSON guardado no cache não
    serve para esta Tool, então a entrada é descartada: a próxima chamada
    consulta a PokéAPI de novo em vez de reaproveitar a resposta quebrada até
    o fim do TTL.
    """
    client = ctx.request_context.lifespan_context.pokeapi
    try:
        payload, url = await client.fetch(resource, name_or_id)
        return build(payload, url)
    except MalformedResponseError as exc:
        client.invalidate(resource, name_or_id)
        raise _to_tool_error(exc) from exc
    except PokeAPIError as exc:
        raise _to_tool_error(exc) from exc


@mcp.tool(
    title="Consultar Pokémon",
    annotations=READ_ONLY,
)
async def get_pokemon(name_or_id: NameOrId, ctx: Context[AppContext]) -> models.Pokemon:
    """Consulta um Pokémon na PokéAPI e devolve identificador, nome, tipos,
    altura em metros, peso em quilogramas, habilidades possíveis (incluindo a
    habilidade oculta) e atributos base."""
    return await _consult(ctx, "pokemon", name_or_id, models.build_pokemon)


@mcp.tool(
    title="Consultar habilidade",
    annotations=READ_ONLY,
)
async def get_ability(name_or_id: NameOrId, ctx: Context[AppContext]) -> models.Ability:
    """Consulta uma habilidade na PokéAPI e devolve identificador, nome e a
    descrição disponível em inglês, informando o idioma e a origem do texto.
    Nenhuma descrição é traduzida ou inventada pelo servidor."""
    return await _consult(ctx, "ability", name_or_id, models.build_ability)


@mcp.tool(
    title="Consultar tipo",
    annotations=READ_ONLY,
)
async def get_type(name_or_id: NameOrId, ctx: Context[AppContext]) -> models.PokemonType:
    """Consulta um tipo elemental na PokéAPI e devolve as seis relações de dano:
    recebido (double/half/no_damage_from) e causado (double/half/no_damage_to).
    São relações do tipo isolado, não de um Pokémon específico."""
    return await _consult(ctx, "type", name_or_id, models.build_type)


GUIDE: Final = """# Pokémon MCP Server

Servidor MCP didático que consulta a [PokéAPI](https://pokeapi.co/docs/v2) e
expõe os dados pelo protocolo MCP. Ele não contém um modelo de linguagem: quem
interpreta os resultados é a aplicação de IA conectada como cliente MCP.

## Ferramentas disponíveis

| Tool | Argumento | O que devolve |
| --- | --- | --- |
| `get_pokemon` | `name_or_id` | Identificador, nome, tipos, altura (m), peso (kg), habilidades possíveis e atributos base. |
| `get_ability` | `name_or_id` | Identificador, nome, descrição em inglês (quando existir), idioma e origem do texto. |
| `get_type` | `name_or_id` | Identificador, nome e as seis relações de dano do tipo. |

Todas as respostas trazem `source_url`, a URL exata consultada na PokéAPI.

## Exemplos de identificadores

- Pokémon: `pikachu`, `charizard`, `bulbasaur`, `mr-mime`, `25`
- Habilidades: `static`, `overgrow`, `blaze`, `torrent`
- Tipos: `electric`, `fire`, `water`, `grass`

Nomes usam minúsculas e hífen. Identificadores numéricos são positivos.

## Origem dos dados

Todos os dados vêm de `https://pokeapi.co/api/v2/`. O servidor apenas consulta,
normaliza unidades e resume a resposta. Nenhum dado é gerado pelo servidor.

A PokéAPI descreve `height` em decímetros e `weight` em hectogramas; este
servidor converte para metros e quilogramas.

## Limitações do laboratório

- Não há simulador de batalhas. Relações de tipo não determinam vencedores.
- As habilidades listadas em `get_pokemon` são as possibilidades da espécie;
  um Pokémon individual tem apenas uma ativa por vez.
- `get_type` descreve um tipo isolado. Ele não considera a combinação de
  tipos de um Pokémon específico (que pode ter um ou dois), habilidades,
  itens ou condições de campo.
- O cache é em memória e se perde ao reiniciar o contêiner.
- Só há três Tools. Movimentos, evoluções e demais recursos da PokéAPI ficam
  fora do escopo.
"""


@mcp.resource(
    "pokemon://guide",
    title="Guia do servidor",
    mime_type="text/markdown",
)
def guide() -> str:
    """Guia em Markdown com o objetivo do servidor, as ferramentas disponíveis,
    exemplos de identificadores, a origem dos dados e os limites do laboratório."""
    return GUIDE


@mcp.prompt(title="Comparar dois Pokémon")
def compare_pokemon(
    pokemon_a: Annotated[
        str, Field(description="Primeiro Pokémon: nome canônico ou identificador.")
    ],
    pokemon_b: Annotated[
        str, Field(description="Segundo Pokémon: nome canônico ou identificador.")
    ],
) -> list[Message]:
    """Template de mensagens que orienta o assistente a comparar dois Pokémon
    usando a Tool get_pokemon. Obter este Prompt apenas devolve o texto: o
    servidor não executa ferramentas nem chama nenhum modelo."""
    return [
        UserMessage(
            f"Compare os Pokémon {pokemon_a} e {pokemon_b}.\n\n"
            "Siga estes passos:\n"
            f"1. Chame a ferramenta get_pokemon com name_or_id='{pokemon_a}'.\n"
            f"2. Chame a ferramenta get_pokemon com name_or_id='{pokemon_b}'.\n"
            "3. Compare tipos, atributos base (hp, attack, defense, "
            "special-attack, special-defense, speed) e habilidades possíveis.\n"
            "4. Responda em português, citando o campo source_url de cada "
            "consulta.\n\n"
            "Restrições da resposta:\n"
            "- Use apenas os dados devolvidos pelas ferramentas. Não complete "
            "lacunas de memória.\n"
            "- Deixe explícito que habilidades são possibilidades da espécie e "
            "que apenas uma fica ativa por vez.\n"
            "- Não afirme quem venceria uma batalha: atributos base não "
            "consideram nível, movimentos, itens, EVs, IVs nem condições de "
            "campo.\n"
            "- Se alguma consulta falhar, diga isso em vez de estimar valores."
        )
    ]


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    """Verificação de processo para o Docker.

    Esta rota é HTTP comum, não uma capacidade MCP. Ela não consulta a PokéAPI
    e não prova que o protocolo MCP está funcionando: para isso use o
    `scripts/smoke_test.py`, que fala MCP de verdade.
    """
    return JSONResponse({"status": "ok", "server": "pokemon-mcp-server"})
