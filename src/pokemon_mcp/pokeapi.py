"""Acesso HTTP à PokéAPI: normalização de identificadores, cache em memória e erros.

Este módulo não conhece MCP. Ele só sabe buscar um recurso da PokéAPI e
devolver o JSON bruto junto com a URL consultada. O mapeamento para os
schemas expostos pelas Tools vive em `models.py`.
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Final

import httpx2

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final = "https://pokeapi.co/api/v2/"
DEFAULT_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_CACHE_TTL_SECONDS: Final = 300.0
DEFAULT_CACHE_MAX_ENTRIES: Final = 256
DEFAULT_CONNECT_RETRIES: Final = 2

MAX_IDENTIFIER_LENGTH: Final = 60
"""Limite de tamanho da entrada. Nomes canônicos da PokéAPI são bem menores."""

_IDENTIFIER_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
"""Nome canônico da PokéAPI: minúsculas, dígitos e hífens entre segmentos."""

_NUMERIC_PATTERN: Final = re.compile(r"^[0-9]+$")
"""Somente dígitos ASCII.

`str.isdigit()` não serve aqui: ele aceita dígitos Unicode como '²' (que faz
`int()` levantar ValueError) e '٢' (que `int()` converteria silenciosamente
para 2). A URL da PokéAPI só aceita dígitos ASCII, então a validação usa
exatamente esse conjunto.
"""


class PokeAPIError(Exception):
    """Base de todas as falhas ao consultar a PokéAPI."""


class InvalidIdentifierError(PokeAPIError):
    """A entrada não é um nome canônico nem um identificador numérico positivo."""


class ResourceNotFoundError(PokeAPIError):
    """A PokéAPI respondeu 404 para o recurso pedido."""


class UpstreamTimeoutError(PokeAPIError):
    """A PokéAPI não respondeu dentro do tempo limite."""


class UpstreamUnavailableError(PokeAPIError):
    """Erro de conexão ou resposta de erro da PokéAPI."""


class MalformedResponseError(PokeAPIError):
    """A resposta não é o JSON esperado para este recurso."""


def normalize_identifier(raw: str) -> str:
    """Normaliza e valida `name_or_id` antes de montar a URL.

    Aceita nomes canônicos (`pikachu`, `mr-mime`) e identificadores numéricos
    positivos em dígitos ASCII (`25`, e `025` vira `25`). Rejeita entradas
    vazias, longas demais, caminhos, URLs, espaços internos, acentos e dígitos
    Unicode fora do ASCII, de forma que o argumento nunca possa apontar para
    fora da base configurada.
    """
    if not isinstance(raw, str):
        raise InvalidIdentifierError("O identificador precisa ser um texto.")

    value = raw.strip().lower()

    if not value:
        raise InvalidIdentifierError("O identificador não pode ser vazio.")

    if len(value) > MAX_IDENTIFIER_LENGTH:
        raise InvalidIdentifierError(
            f"O identificador excede {MAX_IDENTIFIER_LENGTH} caracteres."
        )

    if _NUMERIC_PATTERN.match(value):
        number = int(value)
        if number <= 0:
            raise InvalidIdentifierError("O identificador numérico deve ser positivo.")
        return str(number)

    if not _IDENTIFIER_PATTERN.match(value):
        raise InvalidIdentifierError(
            "Use um nome canônico da PokéAPI (minúsculas e hífens, como "
            "'mr-mime') ou um identificador numérico positivo. URLs, caminhos "
            "e caracteres especiais não são aceitos."
        )

    return value


class TTLCache:
    """Cache em memória com expiração por tempo e limite de entradas (LRU).

    O cache é do processo. Reiniciar o contêiner esvazia o cache, e isso é
    aceitável: ele só evita repetir a mesma consulta à PokéAPI.
    """

    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        # `clock` existe para que os testes possam avançar o tempo sem sleep().
        # O padrão é o relógio monotônico, imune a ajustes do relógio do sistema.
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None

        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return None

        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if self._max_entries <= 0 or self._ttl <= 0:
            return

        self._entries[key] = (self._clock() + self._ttl, value)
        self._entries.move_to_end(key)

        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def delete(self, key: str) -> None:
        """Remove a entrada, se existir. Chamar para uma chave ausente é inócuo."""
        self._entries.pop(key, None)

    def __len__(self) -> int:
        return len(self._entries)


class PokeAPIClient:
    """Cliente assíncrono da PokéAPI, reutilizado por toda a vida do servidor."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        transport: httpx2.AsyncBaseTransport | None = None,
        user_agent: str = "pokemon-mcp-server/0.1.2 (+laboratorio educacional MCP)",
    ) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self._cache = TTLCache(cache_ttl_seconds, cache_max_entries)
        self._client = httpx2.AsyncClient(
            base_url=self.base_url,
            timeout=httpx2.Timeout(timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": user_agent},
            # `retries` do transporte só repete falhas de conexão, e no máximo
            # duas vezes. Respostas de erro da API nunca são repetidas.
            transport=transport
            or httpx2.AsyncHTTPTransport(retries=DEFAULT_CONNECT_RETRIES),
        )

    async def aclose(self) -> None:
        """Fecha o pool de conexões. Chamado no desligamento do servidor."""
        await self._client.aclose()

    def build_url(self, resource: str, identifier: str) -> str:
        """URL pública do recurso, devolvida às Tools como `source_url`."""
        return f"{self.base_url}{resource}/{identifier}/"

    @staticmethod
    def cache_key(resource: str, identifier: str) -> str:
        """Chave de cache do recurso já com o identificador normalizado."""
        return f"{resource}/{identifier}"

    def invalidate(self, resource: str, name_or_id: str) -> None:
        """Esquece a resposta guardada para este recurso.

        Chamado quando a validação específica do recurso (`models.build_*`)
        rejeita o JSON: uma resposta malformada não pode ficar presa no cache
        até o fim do TTL e continuar sendo servida às próximas chamadas.
        """
        try:
            identifier = normalize_identifier(name_or_id)
        except InvalidIdentifierError:
            # Um identificador inválido nunca chegou a virar entrada de cache.
            return
        self._cache.delete(self.cache_key(resource, identifier))

    async def fetch(self, resource: str, name_or_id: str) -> tuple[dict[str, Any], str]:
        """Busca `resource/{name_or_id}` e devolve `(json, source_url)`.

        `resource` é escolhido pelo código do servidor, nunca pelo cliente MCP.
        """
        identifier = normalize_identifier(name_or_id)
        url = self.build_url(resource, identifier)
        cache_key = self.cache_key(resource, identifier)

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("cache hit: %s", cache_key)
            return cached, url

        logger.info("consultando PokéAPI: %s", url)
        try:
            response = await self._client.get(f"{resource}/{identifier}/")
        except httpx2.TimeoutException as exc:
            raise UpstreamTimeoutError(
                f"A PokéAPI não respondeu a tempo ao consultar {url}."
            ) from exc
        except httpx2.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"Não foi possível conectar à PokéAPI ao consultar {url}: {exc}"
            ) from exc

        if response.status_code == 404:
            raise ResourceNotFoundError(
                f"A PokéAPI não encontrou '{identifier}' em '{resource}' ({url})."
            )

        if response.status_code >= 400:
            raise UpstreamUnavailableError(
                f"A PokéAPI respondeu HTTP {response.status_code} para {url}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponseError(
                f"A resposta de {url} não é um JSON válido."
            ) from exc

        if not isinstance(payload, dict):
            raise MalformedResponseError(
                f"A resposta de {url} não tem o formato esperado (objeto JSON)."
            )

        self._cache.set(cache_key, payload)
        return payload, url

    @property
    def cache_size(self) -> int:
        return len(self._cache)
