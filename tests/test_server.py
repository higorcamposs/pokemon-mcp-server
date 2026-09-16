"""Tools, Resource e Prompt vistos por um cliente MCP, sem sair para a rede.

O `Client` do SDK conecta-se ao objeto do servidor em memória: o protocolo é o
mesmo, mas não há processo nem porta. As consultas HTTP são atendidas por um
transporte simulado.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp.types import TextContent, TextResourceContents

from pokemon_mcp import server as server_module
from pokemon_mcp.pokeapi import PokeAPIClient

from .conftest import RecordingHandler

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch, handler: RecordingHandler
) -> AsyncIterator[Client]:
    """Servidor MCP real, ligado a um transporte HTTP simulado."""

    def fake_factory() -> PokeAPIClient:
        return PokeAPIClient(
            base_url="https://pokeapi.test/api/v2/",
            transport=httpx2.MockTransport(handler),
        )

    monkeypatch.setattr(server_module, "create_pokeapi_client", fake_factory)

    async with Client(server_module.mcp, raise_exceptions=True) as connected:
        yield connected


def text_of(result: Any) -> str:
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


# --- descoberta -----------------------------------------------------------


async def test_lists_the_three_tools(client: Client) -> None:
    result = await client.list_tools()
    names = sorted(tool.name for tool in result.tools)

    assert names == ["get_ability", "get_pokemon", "get_type"]

    by_name = {tool.name: tool for tool in result.tools}
    for tool in by_name.values():
        assert tool.description
        assert tool.input_schema["properties"]["name_or_id"]["type"] == "string"
        assert tool.input_schema["required"] == ["name_or_id"]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


# --- get_pokemon ----------------------------------------------------------


async def test_get_pokemon_returns_structured_data(client: Client) -> None:
    result = await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})

    assert result.is_error is False
    data = result.structured_content
    assert data is not None
    assert data["id"] == 25
    assert data["name"] == "pikachu"
    assert data["types"] == ["electric"]
    assert data["height_m"] == 0.4
    assert data["weight_kg"] == 6.0
    assert data["source_url"] == "https://pokeapi.test/api/v2/pokemon/pikachu/"
    assert {a["name"]: a["is_hidden"] for a in data["abilities"]} == {
        "static": False,
        "lightning-rod": True,
    }


async def test_get_pokemon_normalizes_the_argument(
    client: Client, handler: RecordingHandler
) -> None:
    result = await client.call_tool("get_pokemon", {"name_or_id": "  PIKACHU  "})

    assert result.is_error is False
    assert handler.requests == ["pokemon/pikachu"]


async def test_get_pokemon_accepts_a_numeric_id(
    client: Client, handler: RecordingHandler
) -> None:
    """Consultar por número devolve a ficha, não só outra chave de cache."""
    result = await client.call_tool("get_pokemon", {"name_or_id": "25"})

    assert result.is_error is False
    data = result.structured_content
    assert data is not None
    assert data["id"] == 25
    assert data["name"] == "pikachu"
    assert data["types"] == ["electric"]
    assert data["source_url"] == "https://pokeapi.test/api/v2/pokemon/25/"
    assert handler.requests == ["pokemon/25"]


async def test_get_pokemon_normalizes_leading_zeros(
    client: Client, handler: RecordingHandler
) -> None:
    result = await client.call_tool("get_pokemon", {"name_or_id": "025"})

    assert result.is_error is False
    assert handler.requests == ["pokemon/25"]


async def test_get_pokemon_reports_unknown_pokemon(client: Client) -> None:
    result = await client.call_tool("get_pokemon", {"name_or_id": "pikachuu"})

    assert result.is_error is True
    assert result.structured_content is None
    assert "não encontrou" in text_of(result)


async def test_get_pokemon_rejects_url_argument(
    client: Client, handler: RecordingHandler
) -> None:
    result = await client.call_tool(
        "get_pokemon", {"name_or_id": "https://example.com/api"}
    )

    assert result.is_error is True
    assert "Argumento inválido" in text_of(result)
    assert handler.requests == []


async def test_get_pokemon_rejects_empty_argument(client: Client) -> None:
    # Rejeitado pelo schema (min_length=1), antes de a função rodar.
    result = await client.call_tool("get_pokemon", {"name_or_id": ""})
    assert result.is_error is True


# --- get_ability e get_type -----------------------------------------------


async def test_get_ability_returns_english_description(client: Client) -> None:
    result = await client.call_tool("get_ability", {"name_or_id": "static"})

    assert result.is_error is False
    data = result.structured_content
    assert data is not None
    assert data["id"] == 9
    assert data["name"] == "static"
    assert data["language"] == "en"
    assert data["description_source"] == "effect_entries"
    assert data["source_url"] == "https://pokeapi.test/api/v2/ability/static/"


async def test_get_type_returns_the_six_damage_relations(client: Client) -> None:
    result = await client.call_tool("get_type", {"name_or_id": "electric"})

    assert result.is_error is False
    data = result.structured_content
    assert data is not None
    relations = data["damage_relations"]
    assert set(relations) == {
        "double_damage_from",
        "double_damage_to",
        "half_damage_from",
        "half_damage_to",
        "no_damage_from",
        "no_damage_to",
    }
    assert relations["double_damage_from"] == ["ground"]
    assert relations["no_damage_to"] == ["ground"]
    assert data["source_url"] == "https://pokeapi.test/api/v2/type/electric/"


# --- cache visto pelo protocolo -------------------------------------------


async def test_repeated_calls_hit_the_cache(
    client: Client, handler: RecordingHandler
) -> None:
    await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})
    await client.call_tool("get_pokemon", {"name_or_id": "25"})
    await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})

    # "25" é outra chave de cache; "pikachu" repetido não vai à rede de novo.
    assert handler.requests == ["pokemon/pikachu", "pokemon/25"]


async def test_malformed_response_is_not_kept_in_the_cache(
    client: Client, handler: RecordingHandler
) -> None:
    """Uma resposta quebrada não pode envenenar o cache pelo TTL inteiro.

    1. a PokéAPI devolve um JSON fora do contrato -> a Tool falha;
    2. a mesma URL passa a devolver a resposta correta;
    3. a Tool consulta de novo e funciona, ou seja, o payload ruim saiu do cache.
    """
    good = handler.responses["pokemon/pikachu"]
    broken = {key: value for key, value in good.items() if key != "stats"}
    handler.responses["pokemon/pikachu"] = broken

    failed = await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})
    assert failed.is_error is True
    assert failed.structured_content is None
    assert "Resposta inesperada da PokéAPI" in text_of(failed)
    assert handler.requests == ["pokemon/pikachu"]

    handler.responses["pokemon/pikachu"] = good

    recovered = await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})
    assert recovered.is_error is False
    assert recovered.structured_content is not None
    assert recovered.structured_content["id"] == 25
    # Duas idas à rede: a segunda chamada não reaproveitou o payload malformado.
    assert handler.requests == ["pokemon/pikachu", "pokemon/pikachu"]


async def test_valid_response_is_still_cached_after_a_failure(
    client: Client, handler: RecordingHandler
) -> None:
    """A invalidação atinge só a entrada quebrada; o cache continua útil."""
    handler.responses["type/electric"] = {"id": 13, "name": "electric"}

    failed = await client.call_tool("get_type", {"name_or_id": "electric"})
    assert failed.is_error is True

    await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})
    await client.call_tool("get_pokemon", {"name_or_id": "pikachu"})

    assert handler.requests == ["type/electric", "pokemon/pikachu"]


# --- Resource -------------------------------------------------------------


async def test_guide_resource_is_listed_and_readable(client: Client) -> None:
    listing = await client.list_resources()
    uris = [str(resource.uri) for resource in listing.resources]
    assert "pokemon://guide" in uris

    result = await client.read_resource("pokemon://guide")
    contents = result.contents[0]
    assert isinstance(contents, TextResourceContents)
    assert contents.mime_type == "text/markdown"
    assert "# Pokémon MCP Server" in contents.text
    assert "get_pokemon" in contents.text
    assert "Limitações do laboratório" in contents.text


# --- Prompt ---------------------------------------------------------------


async def test_compare_pokemon_prompt_is_listed(client: Client) -> None:
    listing = await client.list_prompts()
    prompt = next(p for p in listing.prompts if p.name == "compare_pokemon")

    assert prompt.description
    assert sorted(argument.name for argument in prompt.arguments or []) == [
        "pokemon_a",
        "pokemon_b",
    ]
    assert all(argument.required for argument in prompt.arguments or [])


async def test_compare_pokemon_prompt_returns_a_template(
    client: Client, handler: RecordingHandler
) -> None:
    result = await client.get_prompt(
        "compare_pokemon", {"pokemon_a": "pikachu", "pokemon_b": "bulbasaur"}
    )

    assert len(result.messages) == 1
    message = result.messages[0]
    assert message.role == "user"
    assert isinstance(message.content, TextContent)

    text = message.content.text
    assert "pikachu" in text and "bulbasaur" in text
    assert "get_pokemon" in text
    assert "português" in text
    assert "Não afirme quem venceria" in text

    # Obter o Prompt devolve o texto: o servidor não executou nenhuma Tool.
    assert handler.requests == []
