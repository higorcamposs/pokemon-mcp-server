"""Ponto de entrada: serve o MCP Server por Streamable HTTP.

O endereço interno do servidor é fixo: `0.0.0.0:8000` com o endpoint em
`/mcp`. Num laboratório didático, deixar isso configurável só cria chances de
o healthcheck, o smoke test e a allowlist de Host apontarem para lugares
diferentes. Para publicar em outra porta da máquina, mude `MCP_HOST_PORT` no
Compose: quem muda é o mapeamento de portas, não o servidor.

O que continua configurável por variável de ambiente: `MCP_LOG_LEVEL`,
`MCP_ALLOWED_HOSTS` e `MCP_ALLOWED_ORIGINS`. Veja `.env.example`.
"""

from __future__ import annotations

import logging
import os

from mcp.server.transport_security import TransportSecuritySettings

from .server import mcp

logger = logging.getLogger("pokemon_mcp")

HOST = "0.0.0.0"  # noqa: S104 - dentro do contêiner; o compose publica só em 127.0.0.1
PORT = 8000
PATH = "/mcp"
DEFAULT_ALLOWED_HOSTS = "127.0.0.1:8000,localhost:8000,[::1]:8000"
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:8000,http://localhost:8000,http://[::1]:8000"
)


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_transport_security() -> TransportSecuritySettings:
    """Allowlist de Host e Origin (proteção contra DNS rebinding).

    O SDK só arma essa proteção sozinho quando o servidor escuta em localhost.
    Dentro do contêiner ele escuta em 0.0.0.0, então a allowlist é declarada
    aqui de forma explícita, com os valores que o cliente realmente usa na
    máquina do usuário. Não desative isso para "resolver" um erro de conexão:
    HTTP 421 significa Host fora da lista e HTTP 403, Origin fora da lista.
    """
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_csv_env("MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
        allowed_origins=_csv_env("MCP_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS),
    )


def main() -> None:
    security = build_transport_security()

    logger.info(
        "Pokémon MCP Server em http://%s:%s%s (Streamable HTTP)", HOST, PORT, PATH
    )
    logger.info("Host allowlist: %s", ", ".join(security.allowed_hosts))
    logger.info("Origin allowlist: %s", ", ".join(security.allowed_origins))

    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path=PATH,
        transport_security=security,
    )


if __name__ == "__main__":
    main()
