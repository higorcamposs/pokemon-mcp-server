"""Mapeamento do JSON da PokéAPI: conversão de unidades e validação estrita.

Os campos que o schema das Tools promete são obrigatórios. Estes testes
cobrem tanto o caminho feliz quanto as respostas fora do contrato, que precisam
terminar em `MalformedResponseError` — nunca numa ficha com listas vazias no
lugar dos dados.
"""

from __future__ import annotations

from typing import Any

import pytest

from pokemon_mcp.models import build_ability, build_pokemon, build_type
from pokemon_mcp.pokeapi import MalformedResponseError

URL = "https://pokeapi.test/api/v2/pokemon/pikachu/"


def minimal_pokemon() -> dict[str, Any]:
    """Menor resposta de `/pokemon/` que ainda respeita o contrato da PokéAPI."""
    return {
        "id": 1,
        "name": "bulbasaur",
        "height": 7,
        "weight": 69,
        "types": [{"slot": 1, "type": {"name": "grass"}}],
        "abilities": [
            {"is_hidden": False, "slot": 1, "ability": {"name": "overgrow"}}
        ],
        "stats": [
            {"base_stat": 45, "stat": {"name": "hp"}},
            {"base_stat": 49, "stat": {"name": "attack"}},
            {"base_stat": 49, "stat": {"name": "defense"}},
            {"base_stat": 65, "stat": {"name": "special-attack"}},
            {"base_stat": 65, "stat": {"name": "special-defense"}},
            {"base_stat": 45, "stat": {"name": "speed"}},
        ],
    }


def pokemon_without(key: str) -> dict[str, Any]:
    payload = minimal_pokemon()
    del payload[key]
    return payload


def pokemon_with(**overrides: Any) -> dict[str, Any]:
    payload = minimal_pokemon()
    payload.update(overrides)
    return payload


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
    pokemon = build_pokemon(minimal_pokemon(), URL)
    assert pokemon.height_m == 0.7
    assert pokemon.weight_kg == 6.9


def test_build_pokemon_accepts_an_empty_ability_list() -> None:
    """Lista vazia presente é dado real, diferente de chave ausente.

    Nove Pokémon da base têm "abilities": [] (por exemplo `zygarde-mega`,
    id 10301), então uma lista realmente vazia não pode virar erro.
    """
    pokemon = build_pokemon(pokemon_with(abilities=[]), URL)
    assert pokemon.abilities == []


def test_build_pokemon_accepts_zero_weight() -> None:
    """`eternatus-eternamax` (id 10190) tem weight 0 na PokéAPI."""
    pokemon = build_pokemon(pokemon_with(weight=0), URL)
    assert pokemon.weight_kg == 0.0


@pytest.mark.parametrize("key", ["id", "name", "height", "weight"])
def test_build_pokemon_requires_the_scalar_fields(key: str) -> None:
    with pytest.raises(MalformedResponseError):
        build_pokemon(pokemon_without(key), URL)


@pytest.mark.parametrize("key", ["types", "abilities", "stats"])
def test_build_pokemon_requires_the_lists_instead_of_emptying_them(key: str) -> None:
    """Campo ausente é erro explícito, não `[]` numa ficha aparentemente completa."""
    with pytest.raises(MalformedResponseError) as excinfo:
        build_pokemon(pokemon_without(key), URL)

    assert key in str(excinfo.value)


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"id": 0}, "id não pode ser zero"),
        ({"id": -25}, "id não pode ser negativo"),
        ({"id": "25"}, "id em texto não é convertido na marra"),
        ({"id": True}, "bool é subclasse de int, mas não é um id"),
        ({"height": -1}, "altura negativa não existe"),
        ({"weight": -1}, "peso negativo não existe"),
        ({"height": "alto"}, "altura precisa ser numérica"),
        ({"height": 4.5}, "a PokéAPI devolve decímetros inteiros"),
        ({"name": 999}, "nome precisa ser texto"),
        ({"name": "   "}, "nome em branco não é nome"),
    ],
)
def test_build_pokemon_rejects_impossible_numbers_and_types(
    overrides: dict[str, Any], why: str
) -> None:
    with pytest.raises(MalformedResponseError):
        build_pokemon(pokemon_with(**overrides), URL)


@pytest.mark.parametrize(
    ("abilities", "why"),
    [
        (123, "abilities não é lista"),
        ("static", "abilities é texto"),
        ([123], "item não é objeto"),
        ([{"is_hidden": False, "slot": 1}], "falta o objeto ability"),
        (
            [{"is_hidden": False, "slot": 1, "ability": {}}],
            "falta o nome da habilidade",
        ),
        (
            [{"is_hidden": "false", "slot": 1, "ability": {"name": "static"}}],
            "is_hidden em texto: bool('false') seria True",
        ),
        (
            [{"is_hidden": 0, "slot": 1, "ability": {"name": "static"}}],
            "is_hidden numérico não é booleano",
        ),
        (
            [{"is_hidden": False, "slot": "abc", "ability": {"name": "static"}}],
            "slot em texto: int('abc') levantaria ValueError",
        ),
        (
            [{"is_hidden": False, "slot": 0, "ability": {"name": "static"}}],
            "slot começa em 1 na PokéAPI",
        ),
        (
            [{"is_hidden": False, "ability": {"name": "static"}}],
            "slot ausente não vira zero",
        ),
    ],
)
def test_build_pokemon_rejects_malformed_abilities(
    abilities: Any, why: str
) -> None:
    with pytest.raises(MalformedResponseError):
        build_pokemon(pokemon_with(abilities=abilities), URL)


@pytest.mark.parametrize(
    ("types", "why"),
    [
        (123, "types não é lista"),
        ([{"slot": 1}], "falta o objeto type"),
        ([{"slot": 1, "type": {"url": "..."}}], "falta o nome do tipo"),
        ([{"slot": 1, "type": {"name": 13}}], "nome do tipo não é texto"),
        ([{"slot": 1, "type": "electric"}], "type não é objeto"),
        ([{"type": {"name": "grass"}}], "falta o slot"),
        ([{"slot": 0, "type": {"name": "grass"}}], "slot começa em 1"),
        ([{"slot": -1, "type": {"name": "grass"}}], "slot negativo"),
        ([{"slot": "1", "type": {"name": "grass"}}], "slot em texto"),
        ([{"slot": 1.5, "type": {"name": "grass"}}], "slot fracionário"),
        ([{"slot": True, "type": {"name": "grass"}}], "bool não é slot"),
    ],
)
def test_build_pokemon_rejects_malformed_types(types: Any, why: str) -> None:
    with pytest.raises(MalformedResponseError):
        build_pokemon(pokemon_with(types=types), URL)


def test_build_pokemon_orders_types_by_slot() -> None:
    """A ordem prometida no schema é garantida pelo servidor, não herdada.

    Bulbasaur é grass/poison: slot 1 é grass. Aqui a resposta chega com os
    slots fora de ordem, e o resultado ainda precisa sair em ordem de slot.
    """
    payload = pokemon_with(
        types=[
            {"slot": 2, "type": {"name": "poison"}},
            {"slot": 1, "type": {"name": "grass"}},
        ]
    )

    assert build_pokemon(payload, URL).types == ["grass", "poison"]


def test_build_pokemon_keeps_types_already_in_order() -> None:
    """O caso normal da PokéAPI continua igual: nada é embaralhado."""
    payload = pokemon_with(
        types=[
            {"slot": 1, "type": {"name": "grass"}},
            {"slot": 2, "type": {"name": "poison"}},
        ]
    )

    assert build_pokemon(payload, URL).types == ["grass", "poison"]


def test_build_pokemon_accepts_non_contiguous_slots() -> None:
    """Ordenar é por valor de slot, não por posição: 1 e 3 não viram erro."""
    payload = pokemon_with(
        types=[
            {"slot": 3, "type": {"name": "flying"}},
            {"slot": 1, "type": {"name": "grass"}},
        ]
    )

    assert build_pokemon(payload, URL).types == ["grass", "flying"]


@pytest.mark.parametrize(
    "missing_stat",
    ["hp", "attack", "defense", "special-attack", "special-defense", "speed"],
)
def test_build_pokemon_requires_every_base_stat(missing_stat: str) -> None:
    """Ficha parcial vira erro: melhor falhar do que entregar dado faltando."""
    payload = minimal_pokemon()
    payload["stats"] = [
        entry for entry in payload["stats"] if entry["stat"]["name"] != missing_stat
    ]

    with pytest.raises(MalformedResponseError) as excinfo:
        build_pokemon(payload, URL)

    assert missing_stat in str(excinfo.value)


@pytest.mark.parametrize(
    ("base_stat", "why"),
    [
        ("35", "valor em texto"),
        (None, "valor nulo"),
        (True, "bool não é atributo base"),
        (-1, "atributo base negativo não existe"),
        (35.5, "atributo base fracionário não existe"),
    ],
)
def test_build_pokemon_rejects_malformed_base_stat(base_stat: Any, why: str) -> None:
    payload = minimal_pokemon()
    payload["stats"][0]["base_stat"] = base_stat

    with pytest.raises(MalformedResponseError):
        build_pokemon(payload, URL)


def test_build_pokemon_keeps_valid_extreme_base_stats() -> None:
    """Sem limite superior inventado: 1 (Shedinja) e 255 (Blissey) são reais."""
    payload = minimal_pokemon()
    payload["stats"][0]["base_stat"] = 1
    payload["stats"][1]["base_stat"] = 255

    pokemon = build_pokemon(payload, URL)

    assert pokemon.base_stats["hp"] == 1
    assert pokemon.base_stats["attack"] == 255


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


def test_build_ability_uses_a_filled_short_effect_alone() -> None:
    payload = {
        "id": 44,
        "name": "so-resumo",
        "effect_entries": [
            {"language": {"name": "en"}, "effect": "", "short_effect": "Resumo útil."}
        ],
        "flavor_text_entries": [
            {"language": {"name": "en"}, "flavor_text": "não deve ser usado"}
        ],
    }
    ability = build_ability(payload, URL)

    assert ability.description_source == "effect_entries"
    assert ability.short_effect == "Resumo útil."
    assert ability.effect is None


def test_build_ability_uses_a_filled_effect_alone() -> None:
    payload = {
        "id": 45,
        "name": "so-efeito",
        "effect_entries": [
            {"language": {"name": "en"}, "effect": "Texto completo.", "short_effect": ""}
        ],
    }
    ability = build_ability(payload, URL)

    assert ability.description_source == "effect_entries"
    assert ability.effect == "Texto completo."
    assert ability.short_effect is None


def test_build_ability_falls_back_when_the_english_effect_is_blank() -> None:
    """Strings vazias não são descrição e não podem bloquear o fallback."""
    payload = {
        "id": 46,
        "name": "efeito-vazio",
        "effect_entries": [
            {"language": {"name": "en"}, "effect": "", "short_effect": "   "}
        ],
        "flavor_text_entries": [
            {"language": {"name": "en"}, "flavor_text": "May\nparalyze\fon contact."}
        ],
    }
    ability = build_ability(payload, URL)

    assert ability.description_source == "flavor_text_entries"
    assert ability.short_effect == "May paralyze on contact."
    assert ability.note is not None


def test_build_ability_reports_no_description_when_every_text_is_blank() -> None:
    payload = {
        "id": 47,
        "name": "tudo-vazio",
        "effect_entries": [{"language": {"name": "en"}, "effect": "", "short_effect": ""}],
        "flavor_text_entries": [{"language": {"name": "en"}, "flavor_text": "  "}],
    }
    ability = build_ability(payload, URL)

    assert ability.effect is None
    assert ability.short_effect is None
    assert ability.language is None
    assert ability.description_source is None
    assert ability.note is not None


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"name": "static"}, "sem id"),
        ({"id": 9}, "sem name"),
        ({"id": "9", "name": "static"}, "id em texto"),
        ({"id": 0, "name": "static"}, "id não positivo"),
        ({"id": 9, "name": 9}, "nome não é texto"),
        ({"id": 9, "name": "static", "effect_entries": 123}, "effect_entries não é lista"),
        (
            {"id": 9, "name": "static", "flavor_text_entries": "texto"},
            "flavor_text_entries não é lista",
        ),
    ],
)
def test_build_ability_rejects_malformed_payload(
    payload: dict[str, Any], why: str
) -> None:
    with pytest.raises(MalformedResponseError):
        build_ability(payload, URL)


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


def test_build_type_accepts_six_genuinely_empty_lists() -> None:
    """O tipo `unknown` da PokéAPI vem com as seis relações vazias."""
    payload = {
        "id": 10001,
        "name": "unknown",
        "damage_relations": {
            "double_damage_from": [],
            "double_damage_to": [],
            "half_damage_from": [],
            "half_damage_to": [],
            "no_damage_from": [],
            "no_damage_to": [],
        },
    }
    ptype = build_type(payload, URL)

    assert ptype.damage_relations.double_damage_from == []
    assert ptype.damage_relations.no_damage_to == []


def test_build_type_rejects_payload_without_damage_relations() -> None:
    with pytest.raises(MalformedResponseError):
        build_type({"id": 13, "name": "electric"}, URL)


def test_build_type_rejects_damage_relations_that_is_not_an_object() -> None:
    with pytest.raises(MalformedResponseError):
        build_type({"id": 13, "name": "electric", "damage_relations": []}, URL)


@pytest.mark.parametrize(
    "missing",
    [
        "double_damage_from",
        "double_damage_to",
        "half_damage_from",
        "half_damage_to",
        "no_damage_from",
        "no_damage_to",
    ],
)
def test_build_type_requires_each_of_the_six_relations(missing: str) -> None:
    """Propriedade ausente não é o mesmo que lista vazia."""
    relations = {
        "double_damage_from": [],
        "double_damage_to": [],
        "half_damage_from": [],
        "half_damage_to": [],
        "no_damage_from": [],
        "no_damage_to": [],
    }
    del relations[missing]

    with pytest.raises(MalformedResponseError) as excinfo:
        build_type({"id": 13, "name": "electric", "damage_relations": relations}, URL)

    assert missing in str(excinfo.value)


def test_build_type_rejects_an_incomplete_damage_relations_object() -> None:
    """O caso da auditoria: damage_relations={} virava seis listas vazias."""
    with pytest.raises(MalformedResponseError):
        build_type({"id": 13, "name": "electric", "damage_relations": {}}, URL)


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("ground", "relação não é lista"),
        ([{"url": "..."}], "item sem nome"),
        (["ground"], "item não é objeto"),
        ([{"name": 5}], "nome não é texto"),
    ],
)
def test_build_type_rejects_malformed_relation_entries(value: Any, why: str) -> None:
    relations = {field: [] for field in (
        "double_damage_from",
        "double_damage_to",
        "half_damage_from",
        "half_damage_to",
        "no_damage_from",
        "no_damage_to",
    )}
    relations["double_damage_from"] = value

    with pytest.raises(MalformedResponseError):
        build_type({"id": 13, "name": "electric", "damage_relations": relations}, URL)
