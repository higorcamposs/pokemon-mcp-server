"""Ponto de entrada: serve o MCP Server por Streamable HTTP.

O endereço interno do servidor é fixo: `0.0.0.0:8000` com o endpoint em
`/mcp`. Num laboratório didático, deixar isso configurável só cria chances de
o healthcheck, o smoke test e a allowlist de Host apontarem para lugares
diferentes. Para publicar em outra porta da máquina, mude `MCP_HOST_PORT` no
Compose: quem muda é o mapeamento de portas, não o servidor.

O que continua configurável por variável de ambiente: `MCP_LOG_LEVEL`,
`MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` (o Compose as deriva de
`MCP_HOST_PORT`) e `MCP_EXTRA_ALLOWED_HOSTS`/`MCP_EXTRA_ALLOWED_ORIGINS`, que
são o lugar certo para acrescentar um nome de host seu. Veja `.env.example`.
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

REQUIRED_ALLOWED_HOSTS = ("127.0.0.1:8000", "localhost:8000", "[::1]:8000")
"""Mínimo que nunca sai da allowlist de `Host`.

É a porta INTERNA do contêiner, usada pelo healthcheck e pelo contêiner de
smoke (que compartilha a rede do servidor). Estes valores são acrescentados
sempre, mesmo que `MCP_ALLOWED_HOSTS` venha definida: assim um `.env` mal
preenchido complementa a lista, em vez de derrubar o laboratório sem aviso.
"""

REQUIRED_ALLOWED_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://[::1]:8000",
)
"""O mesmo mínimo, para o cabeçalho `Origin`."""


def _csv(raw: str | None) -> list[str]:
    """Quebra uma lista separada por vírgulas, ignorando espaços e itens vazios."""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _csv_env(name: str) -> list[str]:
    return _csv(os.getenv(name))


def build_allowlist(required: tuple[str, ...], *env_names: str) -> list[str]:
    """Junta os valores obrigatórios com o que vier das variáveis de ambiente.

    A ordem é preservada e as repetições são descartadas: o Compose e o `.env`
    podem citar o mesmo host duas vezes (acontece sempre que
    `MCP_HOST_PORT=8000`) sem poluir o log de inicialização.
    """
    allowlist: list[str] = []
    for value in [*required, *(item for name in env_names for item in _csv_env(name))]:
        if value not in allowlist:
            allowlist.append(value)
    return allowlist


def build_transport_security() -> TransportSecuritySettings:
    """Allowlist de Host e Origin (proteção contra DNS rebinding).

    O SDK só arma essa proteção sozinho quando o servidor escuta em localhost.
    Dentro do contêiner ele escuta em 0.0.0.0, então a allowlist é declarada
    aqui de forma explícita, com os valores que o cliente realmente usa na
    máquina do usuário. Não desative isso para "resolver" um erro de conexão:
    HTTP 421 significa Host fora da lista e HTTP 403, Origin fora da lista.

    A lista final é sempre: mínimos obrigatórios + o que o Compose deriva de
    `MCP_HOST_PORT` + os extras do usuário.
    """
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=build_allowlist(
            REQUIRED_ALLOWED_HOSTS, "MCP_ALLOWED_HOSTS", "MCP_EXTRA_ALLOWED_HOSTS"
        ),
        allowed_origins=build_allowlist(
            REQUIRED_ALLOWED_ORIGINS, "MCP_ALLOWED_ORIGINS", "MCP_EXTRA_ALLOWED_ORIGINS"
        ),
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
