"""Mapeamento do JSON da PokéAPI: conversão de unidades e campos ausentes."""

from __future__ import annotations

from typing import Any

import pytest

from pokemon_mcp.models import build_ability, build_pokemon, build_type
from pokemon_mcp.pokeapi import MalformedResponseError

URL = "https://pokeapi.test/api/v2/pokemon/pikachu/"


def test_build_pokemon_converts_units(pokeapi_fixtures: dict[str, Any]) -> None:
    payload = pokeapi_fixtures["pokemon/pikachu"]
    pokemon = build_pokemon(payload, URL)

    # A PokéAPI devolve decímetros e hectogramas.
    assert payload["height"] == 4
    assert payload["weight"] == 60
    assert pokemon.height_m == 0.4
    assert pokemon.weight_kg == 6.0


def test_build_pokemon_maps_fields(pokeapi_fixtures: dict[str, Any]) -> None:
    pokemon = build_pokemon(pokeapi_fixtures["pokemon/pikachu"], URL)

    assert pokemon.id == 25
    assert pokemon.name == "pikachu"
    assert pokemon.types == ["electric"]
    assert pokemon.base_stats["hp"] == 35
    assert pokemon.base_stats["speed"] == 90
    assert set(pokemon.base_stats) == {
        "hp",
        "attack",
        "defense",
        "special-attack",
        "special-defense",
        "speed",
    }
    assert pokemon.source_url == URL

    hidden = [ability for ability in pokemon.abilities if ability.is_hidden]
    assert [ability.name for ability in pokemon.abilities] == ["static", "lightning-rod"]
    assert [ability.name for ability in hidden] == ["lightning-rod"]
    assert "possibilidades" in pokemon.abilities_note


def test_build_pokemon_rounds_to_two_decimals() -> None:
    pokemon = build_pokemon(
        {"id": 1, "name": "bulbasaur", "height": 7, "weight": 69}, URL
    )
    assert pokemon.height_m == 0.7
    assert pokemon.weight_kg == 6.9


def test_build_pokemon_tolerates_missing_optional_lists() -> None:
    pokemon = build_pokemon({"id": 1, "name": "x", "height": 1, "weight": 1}, URL)

    assert pokemon.types == []
    assert pokemon.abilities == []
    assert pokemon.base_stats == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "pikachu", "height": 4, "weight": 60},  # sem id
        {"id": 25, "height": 4, "weight": 60},  # sem name
        {"id": 25, "name": "pikachu", "weight": 60},  # sem height
        {"id": 25, "name": "pikachu", "height": "alto", "weight": 60},
        {"id": 25, "name": 999, "height": 4, "weight": 60},
    ],
)
def test_build_pokemon_rejects_malformed_payload(payload: dict[str, Any]) -> None:
    with pytest.raises(MalformedResponseError):
        build_pokemon(payload, URL)


def test_build_ability_prefers_english_effect(
    pokeapi_fixtures: dict[str, Any],
) -> None:
    ability = build_ability(pokeapi_fixtures["ability/static"], URL)

    assert ability.id == 9
    assert ability.name == "static"
    assert ability.language == "en"
    assert ability.description_source == "effect_entries"
    assert ability.short_effect is not None
    assert "paralyz" in ability.short_effect.lower()
    assert ability.note is None


def test_build_ability_falls_back_to_flavor_text() -> None:
    payload = {
        "id": 42,
        "name": "exemplo",
        "effect_entries": [
            {"language": {"name": "fr"}, "effect": "texto em frances"}
        ],
        "flavor_text_entries": [
            {"language": {"name": "en"}, "flavor_text": "May\nparalyze\fon contact."}
        ],
    }
    ability = build_ability(payload, URL)

    assert ability.language == "en"
    assert ability.description_source == "flavor_text_entries"
    assert ability.short_effect == "May paralyze on contact."
    assert ability.note is not None


def test_build_ability_reports_missing_description() -> None:
    payload = {
        "id": 43,
        "name": "sem-descricao",
        "effect_entries": [{"language": {"name": "de"}, "effect": "text"}],
        "flavor_text_entries": [],
    }
    ability = build_ability(payload, URL)

    assert ability.effect is None
    assert ability.short_effect is None
    assert ability.language is None
    assert ability.description_source is None
    assert ability.note is not None and "não traz descrição" in ability.note


def test_build_type_maps_all_six_relations(pokeapi_fixtures: dict[str, Any]) -> None:
    ptype = build_type(pokeapi_fixtures["type/electric"], URL)
    relations = ptype.damage_relations

    assert ptype.id == 13
    assert ptype.name == "electric"
    assert relations.double_damage_from == ["ground"]
    assert relations.double_damage_to == ["flying", "water"]
    assert relations.half_damage_from == ["flying", "steel", "electric"]
    assert relations.half_damage_to == ["grass", "electric", "dragon"]
    assert relations.no_damage_from == []
    assert relations.no_damage_to == ["ground"]
    assert "tipo isolado" in ptype.note


def test_build_type_rejects_payload_without_damage_relations() -> None:
    with pytest.raises(MalformedResponseError):
        build_type({"id": 13, "name": "electric"}, URL)
