"""Transporte HTTP: rota /health e proteção contra DNS rebinding.

A aplicação ASGI é a mesma que o `__main__` serve com uvicorn, montada aqui em
memória e exercitada com um transporte ASGI. Não há porta, processo nem rede:
o objetivo é provar as respostas de borda (200, 421 e 403), não reimplementar a
suíte do SDK, que já cobre o transporte Streamable HTTP em si.

O caminho feliz completo do protocolo continua sendo verificado em dois lugares
melhores: `tests/test_server.py` (cliente MCP em memória) e
`scripts/smoke_test.py` (servidor de verdade, PokéAPI de verdade).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx2
import pytest

from pokemon_mcp import server as server_module
from pokemon_mcp.__main__ import PATH, build_transport_security

pytestmark = pytest.mark.anyio

ALLOWED_HOST = "localhost:8000"
ALLOWED_ORIGIN = "http://localhost:8000"

INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "teste-transporte", "version": "0"},
    },
}

MCP_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


@pytest.fixture
async def http_client() -> AsyncIterator[httpx2.AsyncClient]:
    """Aplicação ASGI com a mesma allowlist usada pelo ponto de entrada."""
    app = server_module.mcp.streamable_http_app(
        streamable_http_path=PATH,
        transport_security=build_transport_security(),
        # O mesmo endereço do contêiner: não é localhost, então a proteção
        # precisa vir da allowlist explícita, e não do atalho do SDK.
        host="0.0.0.0",  # noqa: S104
    )
    # A lifespan do app inicia o gerenciador de sessões do Streamable HTTP.
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url=f"http://{ALLOWED_HOST}",
            timeout=10.0,
        ) as client,
    ):
        yield client


async def test_health_answers_without_touching_mcp(
    http_client: httpx2.AsyncClient,
) -> None:
    response = await http_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "server": "pokemon-mcp-server"}


async def test_allowed_host_reaches_the_mcp_endpoint(
    http_client: httpx2.AsyncClient,
) -> None:
    """Host e Origin na allowlist: a requisição chega ao transporte MCP."""
    response = await http_client.post(
        PATH,
        content=json.dumps(INITIALIZE_REQUEST),
        headers={**MCP_HEADERS, "host": ALLOWED_HOST, "origin": ALLOWED_ORIGIN},
    )

    assert response.status_code == 200
    assert response.status_code not in (403, 421)
    # O SDK abre uma sessão e responde ao initialize.
    assert "mcp-session-id" in response.headers


async def test_invalid_host_is_rejected_with_421(
    http_client: httpx2.AsyncClient,
) -> None:
    """Proteção contra DNS rebinding: Host fora da allowlist não é atendido."""
    response = await http_client.post(
        PATH,
        content=json.dumps(INITIALIZE_REQUEST),
        headers={**MCP_HEADERS, "host": "evil.example.com"},
    )

    assert response.status_code == 421
    assert "Invalid Host header" in response.text


async def test_invalid_origin_is_rejected_with_403(
    http_client: httpx2.AsyncClient,
) -> None:
    response = await http_client.post(
        PATH,
        content=json.dumps(INITIALIZE_REQUEST),
        headers={
            **MCP_HEADERS,
            "host": ALLOWED_HOST,
            "origin": "http://evil.example.com",
        },
    )

    assert response.status_code == 403
    assert "Invalid Origin header" in response.text


async def test_dns_rebinding_protection_is_enabled_by_default() -> None:
    """A allowlist padrão cobre apenas o laboratório local."""
    security = build_transport_security()

    assert security.enable_dns_rebinding_protection is True
    assert "localhost:8000" in security.allowed_hosts
    assert "http://localhost:8000" in security.allowed_origins
