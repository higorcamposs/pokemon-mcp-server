"""Leitura da configuração de ambiente: allowlists e variáveis numéricas.

Duas coisas que só quebram em produção se ninguém as testar:

- a allowlist de `Host`/`Origin`, montada a partir de várias variáveis, não
  pode perder os valores mínimos por causa de um `.env` mal preenchido;
- um valor numérico absurdo (`-1`, `nan`, `inf`) não pode chegar ao cliente
  HTTP nem ao cache — lá ele viraria um timeout que nunca expira ou uma
  entrada de cache eterna, sem nenhuma mensagem de erro.
"""

from __future__ import annotations

from typing import Any

import pytest

from pokemon_mcp import server as server_module
from pokemon_mcp.__main__ import (
    REQUIRED_ALLOWED_HOSTS,
    REQUIRED_ALLOWED_ORIGINS,
    build_allowlist,
    build_transport_security,
)
from pokemon_mcp.pokeapi import (
    DEFAULT_CACHE_MAX_ENTRIES,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)

ALLOWLIST_VARS = (
    "MCP_ALLOWED_HOSTS",
    "MCP_ALLOWED_ORIGINS",
    "MCP_EXTRA_ALLOWED_HOSTS",
    "MCP_EXTRA_ALLOWED_ORIGINS",
)

NUMERIC_VARS = (
    "POKEAPI_TIMEOUT_SECONDS",
    "POKEAPI_CACHE_TTL_SECONDS",
    "POKEAPI_CACHE_MAX_ENTRIES",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parte de um ambiente limpo: o `.env` da máquina não influencia o teste."""
    for name in (*ALLOWLIST_VARS, *NUMERIC_VARS):
        monkeypatch.delenv(name, raising=False)


# --- allowlist de Host e Origin -------------------------------------------


def test_allowlist_without_any_variable_is_the_required_minimum() -> None:
    assert build_allowlist(REQUIRED_ALLOWED_HOSTS, "MCP_ALLOWED_HOSTS") == list(
        REQUIRED_ALLOWED_HOSTS
    )


def test_allowlist_appends_the_values_of_each_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ordem é: mínimos, depois o que o Compose deriva, depois os extras."""
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "localhost:8001")
    monkeypatch.setenv("MCP_EXTRA_ALLOWED_HOSTS", "meu-host.local:8000")

    allowlist = build_allowlist(
        REQUIRED_ALLOWED_HOSTS, "MCP_ALLOWED_HOSTS", "MCP_EXTRA_ALLOWED_HOSTS"
    )

    assert allowlist == [
        "127.0.0.1:8000",
        "localhost:8000",
        "[::1]:8000",
        "localhost:8001",
        "meu-host.local:8000",
    ]


def test_allowlist_keeps_the_minimum_even_when_the_variable_replaces_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Definir a variável complementa a lista; ela nunca remove o mínimo.

    É o ponto todo do desenho: um `.env` com um único host esquisito não pode
    tirar `localhost:8000` da lista e derrubar o healthcheck e o smoke test.
    """
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "so-esse-host.example:9999")

    allowlist = build_allowlist(REQUIRED_ALLOWED_HOSTS, "MCP_ALLOWED_HOSTS")

    assert set(REQUIRED_ALLOWED_HOSTS) <= set(allowlist)
    assert "so-esse-host.example:9999" in allowlist


def test_allowlist_ignores_blanks_and_repetitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O Compose repete valores quando MCP_HOST_PORT=8000 e quebra linha com `>-`."""
    monkeypatch.setenv(
        "MCP_ALLOWED_HOSTS",
        "127.0.0.1:8000,localhost:8000,[::1]:8000, , 127.0.0.1:8000,,localhost:8000",
    )

    assert build_allowlist(REQUIRED_ALLOWED_HOSTS, "MCP_ALLOWED_HOSTS") == list(
        REQUIRED_ALLOWED_HOSTS
    )


def test_transport_security_sums_the_three_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenário real: MCP_HOST_PORT=8001 no Compose e um extra no `.env`."""
    monkeypatch.setenv(
        "MCP_ALLOWED_HOSTS",
        "127.0.0.1:8000,localhost:8000,[::1]:8000,"
        "127.0.0.1:8001,localhost:8001,[::1]:8001",
    )
    monkeypatch.setenv("MCP_EXTRA_ALLOWED_HOSTS", "meu-host.local:8000")
    monkeypatch.setenv(
        "MCP_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,http://[::1]:8000,"
        "http://127.0.0.1:8001,http://localhost:8001,http://[::1]:8001",
    )
    monkeypatch.setenv("MCP_EXTRA_ALLOWED_ORIGINS", "http://meu-host.local:8000")

    security = build_transport_security()

    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == [
        "127.0.0.1:8000",
        "localhost:8000",
        "[::1]:8000",
        "127.0.0.1:8001",
        "localhost:8001",
        "[::1]:8001",
        "meu-host.local:8000",
    ]
    assert security.allowed_origins == [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://[::1]:8000",
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://[::1]:8001",
        "http://meu-host.local:8000",
    ]


def test_extra_variables_never_disable_the_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_EXTRA_ALLOWED_HOSTS", "*")
    monkeypatch.setenv("MCP_EXTRA_ALLOWED_ORIGINS", "*")

    security = build_transport_security()

    assert security.enable_dns_rebinding_protection is True
    assert set(REQUIRED_ALLOWED_HOSTS) <= set(security.allowed_hosts)
    assert set(REQUIRED_ALLOWED_ORIGINS) <= set(security.allowed_origins)


# --- variáveis numéricas ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("dez", "texto"),
        ("", "vazio"),
        ("   ", "só espaços"),
        ("-1", "negativo"),
        ("-0.5", "negativo fracionário"),
        ("0", "zero seria 'sem tempo nenhum'"),
        ("nan", "NaN não é um tempo"),
        ("inf", "+inf nunca expiraria"),
        ("-inf", "-inf expiraria antes de começar"),
    ],
)
def test_timeout_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, raw: str, why: str
) -> None:
    monkeypatch.setenv("POKEAPI_TIMEOUT_SECONDS", raw)

    assert (
        server_module._env_float(
            "POKEAPI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, allow_zero=False
        )
        == DEFAULT_TIMEOUT_SECONDS
    )


@pytest.mark.parametrize("raw", ["0.5", "10", "30.5"])
def test_timeout_accepts_positive_finite_values(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("POKEAPI_TIMEOUT_SECONDS", raw)

    assert server_module._env_float(
        "POKEAPI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, allow_zero=False
    ) == float(raw)


@pytest.mark.parametrize("raw", ["-1", "-0.1", "nan", "inf", "-inf", "cinco"])
def test_cache_ttl_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("POKEAPI_CACHE_TTL_SECONDS", raw)

    assert (
        server_module._env_float(
            "POKEAPI_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS, allow_zero=True
        )
        == DEFAULT_CACHE_TTL_SECONDS
    )


def test_cache_ttl_accepts_zero_to_disable_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero é uma escolha legítima aqui: `TTLCache.set` não guarda nada."""
    monkeypatch.setenv("POKEAPI_CACHE_TTL_SECONDS", "0")

    assert (
        server_module._env_float(
            "POKEAPI_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS, allow_zero=True
        )
        == 0.0
    )


@pytest.mark.parametrize("raw", ["-1", "1.5", "nan", "inf", "-inf", "duzentos"])
def test_cache_max_entries_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("POKEAPI_CACHE_MAX_ENTRIES", raw)

    assert (
        server_module._env_int(
            "POKEAPI_CACHE_MAX_ENTRIES", DEFAULT_CACHE_MAX_ENTRIES, allow_zero=True
        )
        == DEFAULT_CACHE_MAX_ENTRIES
    )


def test_cache_max_entries_accepts_zero_to_disable_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POKEAPI_CACHE_MAX_ENTRIES", "0")

    assert (
        server_module._env_int(
            "POKEAPI_CACHE_MAX_ENTRIES", DEFAULT_CACHE_MAX_ENTRIES, allow_zero=True
        )
        == 0
    )


def test_invalid_values_are_logged_as_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Silêncio seria pior que o valor errado: quem sobe o contêiner precisa ver."""
    monkeypatch.setenv("POKEAPI_TIMEOUT_SECONDS", "inf")

    with caplog.at_level("WARNING", logger="pokemon_mcp.server"):
        server_module._env_float(
            "POKEAPI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, allow_zero=False
        )

    assert "POKEAPI_TIMEOUT_SECONDS" in caplog.text


def test_broken_values_never_reach_the_http_client_or_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O que `create_pokeapi_client` entrega ao httpx2 e ao TTLCache.

    Este é o teste que importa: não basta a função de leitura devolver o
    padrão, o valor absurdo não pode chegar ao `httpx2.Timeout` nem ao cache.
    """
    monkeypatch.setenv("POKEAPI_TIMEOUT_SECONDS", "nan")
    monkeypatch.setenv("POKEAPI_CACHE_TTL_SECONDS", "-inf")
    monkeypatch.setenv("POKEAPI_CACHE_MAX_ENTRIES", "-5")

    captured: dict[str, Any] = {}

    class RecordingClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(server_module, "PokeAPIClient", RecordingClient)
    server_module.create_pokeapi_client()

    assert captured["timeout_seconds"] == DEFAULT_TIMEOUT_SECONDS
    assert captured["cache_ttl_seconds"] == DEFAULT_CACHE_TTL_SECONDS
    assert captured["cache_max_entries"] == DEFAULT_CACHE_MAX_ENTRIES
