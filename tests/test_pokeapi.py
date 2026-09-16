"""Normalização de identificadores, cache e tratamento de erros HTTP."""

from __future__ import annotations

import httpx2
import pytest

from pokemon_mcp.pokeapi import (
    InvalidIdentifierError,
    MalformedResponseError,
    PokeAPIClient,
    ResourceNotFoundError,
    TTLCache,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    normalize_identifier,
)

from .conftest import RecordingHandler

pytestmark = pytest.mark.anyio


def make_client(handler, **kwargs) -> PokeAPIClient:
    return PokeAPIClient(
        base_url="https://pokeapi.test/api/v2/",
        transport=httpx2.MockTransport(handler),
        **kwargs,
    )


# --- normalização ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pikachu", "pikachu"),
        ("  Pikachu  ", "pikachu"),
        ("PIKACHU", "pikachu"),
        ("mr-mime", "mr-mime"),
        ("25", "25"),
        ("025", "25"),
        ("\tcharizard\n", "charizard"),
    ],
)
def test_normalize_identifier_accepts_valid_input(raw: str, expected: str) -> None:
    assert normalize_identifier(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "0",
        "-1",
        "pika chu",
        "../../etc/passwd",
        "pokemon/pikachu",
        "https://example.com/api/v2/pokemon/1",
        "pikachu?x=1",
        "-pikachu",
        "pikachu-",
        "piká",
        "p" * 61,
    ],
)
def test_normalize_identifier_rejects_invalid_input(raw: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        normalize_identifier(raw)


# --- cache ----------------------------------------------------------------


def test_ttl_cache_expires_entries() -> None:
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("k", {"v": 1})
    assert cache.get("k") == {"v": 1}

    expired = TTLCache(ttl_seconds=-1, max_entries=10)
    expired.set("k", {"v": 1})
    assert expired.get("k") is None


def test_ttl_cache_evicts_least_recently_used() -> None:
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # "a" passa a ser o mais recente
    cache.set("c", 3)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


async def test_fetch_uses_cache_on_second_call(handler: RecordingHandler) -> None:
    client = make_client(handler)
    try:
        first, url = await client.fetch("pokemon", "pikachu")
        second, _ = await client.fetch("pokemon", "  PIKACHU ")
    finally:
        await client.aclose()

    assert first == second
    assert url == "https://pokeapi.test/api/v2/pokemon/pikachu/"
    # Uma única ida à rede, apesar das duas chamadas.
    assert handler.requests == ["pokemon/pikachu"]


async def test_fetch_skips_cache_when_ttl_is_zero(handler: RecordingHandler) -> None:
    client = make_client(handler, cache_ttl_seconds=0)
    try:
        await client.fetch("pokemon", "pikachu")
        await client.fetch("pokemon", "pikachu")
    finally:
        await client.aclose()

    assert handler.requests == ["pokemon/pikachu", "pokemon/pikachu"]


# --- erros ----------------------------------------------------------------


async def test_fetch_raises_not_found(handler: RecordingHandler) -> None:
    client = make_client(handler)
    try:
        with pytest.raises(ResourceNotFoundError):
            await client.fetch("pokemon", "pikachuu")
    finally:
        await client.aclose()


async def test_fetch_raises_on_timeout() -> None:
    def timeout_handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timeout", request=request)

    client = make_client(timeout_handler)
    try:
        with pytest.raises(UpstreamTimeoutError):
            await client.fetch("pokemon", "pikachu")
    finally:
        await client.aclose()


async def test_fetch_raises_on_connection_error() -> None:
    def connect_handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("sem rede", request=request)

    client = make_client(connect_handler)
    try:
        with pytest.raises(UpstreamUnavailableError):
            await client.fetch("pokemon", "pikachu")
    finally:
        await client.aclose()


async def test_fetch_raises_on_server_error() -> None:
    client = make_client(lambda request: httpx2.Response(500, text="boom"))
    try:
        with pytest.raises(UpstreamUnavailableError):
            await client.fetch("pokemon", "pikachu")
    finally:
        await client.aclose()


async def test_fetch_raises_on_invalid_json() -> None:
    client = make_client(lambda request: httpx2.Response(200, text="not json"))
    try:
        with pytest.raises(MalformedResponseError):
            await client.fetch("pokemon", "pikachu")
    finally:
        await client.aclose()


async def test_fetch_raises_when_payload_is_not_an_object() -> None:
    client = make_client(lambda request: httpx2.Response(200, json=[1, 2, 3]))
    try:
        with pytest.raises(MalformedResponseError):
            await client.fetch("pokemon", "pikachu")
    finally:
        await client.aclose()


async def test_fetch_rejects_invalid_identifier_without_network(
    handler: RecordingHandler,
) -> None:
    client = make_client(handler)
    try:
        with pytest.raises(InvalidIdentifierError):
            await client.fetch("pokemon", "https://example.com/evil")
    finally:
        await client.aclose()

    assert handler.requests == []
