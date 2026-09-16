"""Fixtures compartilhadas. Nenhum teste deste diretório acessa a internet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Plugin anyio do pytest: rodar os testes assíncronos no asyncio."""
    return "asyncio"


def load_fixture(name: str) -> dict[str, Any]:
    """Carrega uma resposta da PokéAPI gravada em disco."""
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def pokeapi_fixtures() -> dict[str, dict[str, Any]]:
    return {
        "pokemon/pikachu": load_fixture("pokemon_pikachu"),
        # Na PokéAPI, /pokemon/25/ devolve exatamente a mesma ficha que
        # /pokemon/pikachu/. Consultar por número precisa funcionar de verdade,
        # e não apenas gerar outra chave de cache.
        "pokemon/25": load_fixture("pokemon_pikachu"),
        "ability/static": load_fixture("ability_static"),
        "type/electric": load_fixture("type_electric"),
    }


class RecordingHandler:
    """Handler do MockTransport que conta as requisições que chegaram.

    `responses` é lido a cada chamada, então um teste pode trocar a resposta de
    uma URL entre duas requisições (usado para provar que uma resposta
    malformada não fica presa no cache).
    """

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path.strip("/")
        # "api/v2/pokemon/pikachu" -> "pokemon/pikachu"
        key = "/".join(path.split("/")[-2:])
        self.requests.append(key)

        if key in self.responses:
            return httpx2.Response(200, json=self.responses[key])
        return httpx2.Response(404, json={"detail": "Not found."})


@pytest.fixture
def handler(pokeapi_fixtures: dict[str, dict[str, Any]]) -> RecordingHandler:
    return RecordingHandler(pokeapi_fixtures)
