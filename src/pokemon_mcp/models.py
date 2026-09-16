"""Schemas de saída das Tools e mapeamento do JSON da PokéAPI.

Cada função aqui é pura: recebe o JSON bruto e a URL consultada e devolve um
modelo Pydantic enxuto. Nada de rede, o que deixa tudo testável sem internet.

Unidades: a documentação da PokéAPI descreve `height` em decímetros e `weight`
em hectogramas (https://pokeapi.co/docs/v2#pokemon). A conversão para metros e
quilogramas acontece aqui, uma única vez.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, Field

from .pokeapi import MalformedResponseError

DECIMETRES_TO_METRES: Final = 0.1
HECTOGRAMS_TO_KILOGRAMS: Final = 0.1

ABILITIES_NOTE: Final = (
    "Habilidades são as possibilidades da espécie. Um Pokémon individual tem "
    "apenas uma delas ativa por vez; 'is_hidden' indica a habilidade oculta."
)


class PokemonAbility(BaseModel):
    """Uma habilidade possível do Pokémon."""

    name: str = Field(description="Nome canônico da habilidade na PokéAPI.")
    is_hidden: bool = Field(description="Verdadeiro se for a habilidade oculta.")
    slot: int = Field(description="Posição da habilidade na ficha da espécie.")


class Pokemon(BaseModel):
    """Ficha resumida de um Pokémon."""

    id: int = Field(description="Identificador numérico na PokéAPI.")
    name: str = Field(description="Nome canônico.")
    types: list[str] = Field(description="Tipos do Pokémon, em ordem de slot.")
    height_m: float = Field(description="Altura em metros (origem: decímetros).")
    weight_kg: float = Field(description="Peso em quilogramas (origem: hectogramas).")
    abilities: list[PokemonAbility] = Field(
        description="Habilidades possíveis da espécie."
    )
    base_stats: dict[str, int] = Field(
        description=(
            "Atributos base indexados pelo nome usado na PokéAPI: hp, attack, "
            "defense, special-attack, special-defense e speed."
        )
    )
    abilities_note: str = Field(
        default=ABILITIES_NOTE,
        description="Como interpretar a lista de habilidades.",
    )
    source_url: str = Field(description="URL da PokéAPI consultada.")


class Ability(BaseModel):
    """Descrição de uma habilidade."""

    id: int = Field(description="Identificador numérico na PokéAPI.")
    name: str = Field(description="Nome canônico.")
    short_effect: str | None = Field(
        default=None, description="Resumo do efeito, quando disponível."
    )
    effect: str | None = Field(
        default=None, description="Texto completo do efeito, quando disponível."
    )
    language: str | None = Field(
        default=None,
        description="Idioma do texto devolvido. Nulo quando não há descrição.",
    )
    description_source: str | None = Field(
        default=None,
        description=(
            "Campo da PokéAPI de onde veio o texto: 'effect_entries' ou "
            "'flavor_text_entries'. Nulo quando não há descrição."
        ),
    )
    note: str | None = Field(
        default=None, description="Aviso sobre ausência de descrição adequada."
    )
    source_url: str = Field(description="URL da PokéAPI consultada.")


class DamageRelations(BaseModel):
    """Relações de dano de um tipo isolado, sem combinar com outros fatores."""

    double_damage_from: list[str] = Field(
        description="Tipos que causam dano dobrado A ESTE tipo (defesa)."
    )
    half_damage_from: list[str] = Field(
        description="Tipos que causam metade do dano A ESTE tipo (defesa)."
    )
    no_damage_from: list[str] = Field(
        description="Tipos que não causam dano A ESTE tipo (defesa)."
    )
    double_damage_to: list[str] = Field(
        description="Tipos que ESTE tipo atinge com dano dobrado (ataque)."
    )
    half_damage_to: list[str] = Field(
        description="Tipos que ESTE tipo atinge com metade do dano (ataque)."
    )
    no_damage_to: list[str] = Field(
        description="Tipos que ESTE tipo não consegue atingir (ataque)."
    )


TYPE_NOTE: Final = (
    "Relações de um tipo isolado. Um Pokémon real combina dois tipos, "
    "habilidades e outras condições, então estas tabelas não descrevem o "
    "resultado de um confronto específico."
)


class PokemonType(BaseModel):
    """Ficha de um tipo elemental."""

    id: int = Field(description="Identificador numérico na PokéAPI.")
    name: str = Field(description="Nome canônico do tipo.")
    damage_relations: DamageRelations = Field(
        description="Relações de dano recebido (from) e causado (to)."
    )
    note: str = Field(default=TYPE_NOTE, description="Limite de interpretação.")
    source_url: str = Field(description="URL da PokéAPI consultada.")


def _require(payload: dict[str, Any], key: str, url: str) -> Any:
    if key not in payload:
        raise MalformedResponseError(
            f"A resposta de {url} não traz o campo obrigatório '{key}'."
        )
    return payload[key]


def _resource_names(entries: Any) -> list[str]:
    """Extrai `entry['name']` de uma lista de NamedAPIResource."""
    if not isinstance(entries, list):
        return []
    return [
        entry["name"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]


def _nested_names(entries: Any, inner_key: str) -> list[str]:
    """Extrai `entry[inner_key]['name']` de uma lista, ignorando itens quebrados."""
    if not isinstance(entries, list):
        return []
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        inner = entry.get(inner_key)
        if isinstance(inner, dict) and isinstance(inner.get("name"), str):
            names.append(inner["name"])
    return names


def build_pokemon(payload: dict[str, Any], source_url: str) -> Pokemon:
    """Converte o JSON de `/pokemon/{id}/` na ficha resumida."""
    try:
        height = float(_require(payload, "height", source_url))
        weight = float(_require(payload, "weight", source_url))
        identifier = int(_require(payload, "id", source_url))
    except (TypeError, ValueError) as exc:
        raise MalformedResponseError(
            f"A resposta de {source_url} traz campos numéricos inválidos."
        ) from exc

    name = _require(payload, "name", source_url)
    if not isinstance(name, str):
        raise MalformedResponseError(f"O campo 'name' de {source_url} não é um texto.")

    abilities: list[PokemonAbility] = []
    for entry in payload.get("abilities") or []:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("ability")
        if not isinstance(inner, dict) or not isinstance(inner.get("name"), str):
            continue
        abilities.append(
            PokemonAbility(
                name=inner["name"],
                is_hidden=bool(entry.get("is_hidden", False)),
                slot=int(entry.get("slot", 0) or 0),
            )
        )

    base_stats: dict[str, int] = {}
    for entry in payload.get("stats") or []:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("stat")
        base = entry.get("base_stat")
        if (
            isinstance(inner, dict)
            and isinstance(inner.get("name"), str)
            and isinstance(base, int)
        ):
            base_stats[inner["name"]] = base

    return Pokemon(
        id=identifier,
        name=name,
        types=_nested_names(payload.get("types"), "type"),
        # round() evita ruído de ponto flutuante como 0.30000000000000004.
        height_m=round(height * DECIMETRES_TO_METRES, 2),
        weight_kg=round(weight * HECTOGRAMS_TO_KILOGRAMS, 2),
        abilities=abilities,
        base_stats=base_stats,
        source_url=source_url,
    )


def _english_effect(payload: dict[str, Any]) -> dict[str, str] | None:
    """Primeira entrada de `effect_entries` em inglês."""
    for entry in payload.get("effect_entries") or []:
        if not isinstance(entry, dict):
            continue
        language = entry.get("language")
        if not isinstance(language, dict) or language.get("name") != "en":
            continue
        effect = entry.get("effect")
        short_effect = entry.get("short_effect")
        if isinstance(effect, str) or isinstance(short_effect, str):
            return {
                "effect": effect if isinstance(effect, str) else "",
                "short_effect": short_effect if isinstance(short_effect, str) else "",
            }
    return None


def _english_flavor_text(payload: dict[str, Any]) -> str | None:
    """Primeiro `flavor_text` em inglês, usado quando não há `effect_entries`."""
    for entry in payload.get("flavor_text_entries") or []:
        if not isinstance(entry, dict):
            continue
        language = entry.get("language")
        if not isinstance(language, dict) or language.get("name") != "en":
            continue
        text = entry.get("flavor_text")
        if isinstance(text, str) and text.strip():
            # A PokéAPI quebra esses textos com \n e \f.
            return " ".join(text.split())
    return None


def build_ability(payload: dict[str, Any], source_url: str) -> Ability:
    """Converte o JSON de `/ability/{id}/`, preferindo a descrição em inglês."""
    try:
        identifier = int(_require(payload, "id", source_url))
    except (TypeError, ValueError) as exc:
        raise MalformedResponseError(
            f"O campo 'id' de {source_url} não é numérico."
        ) from exc

    name = _require(payload, "name", source_url)
    if not isinstance(name, str):
        raise MalformedResponseError(f"O campo 'name' de {source_url} não é um texto.")

    effect_entry = _english_effect(payload)
    if effect_entry is not None:
        return Ability(
            id=identifier,
            name=name,
            short_effect=effect_entry["short_effect"] or None,
            effect=effect_entry["effect"] or None,
            language="en",
            description_source="effect_entries",
            source_url=source_url,
        )

    flavor_text = _english_flavor_text(payload)
    if flavor_text is not None:
        return Ability(
            id=identifier,
            name=name,
            short_effect=flavor_text,
            effect=None,
            language="en",
            description_source="flavor_text_entries",
            note=(
                "Esta habilidade não tem 'effect_entries' em inglês na PokéAPI; "
                "o texto veio de 'flavor_text_entries', que é mais curto."
            ),
            source_url=source_url,
        )

    return Ability(
        id=identifier,
        name=name,
        language=None,
        description_source=None,
        note=(
            "A PokéAPI não traz descrição em inglês para esta habilidade. "
            "Nenhum texto foi gerado ou traduzido pelo servidor."
        ),
        source_url=source_url,
    )


def build_type(payload: dict[str, Any], source_url: str) -> PokemonType:
    """Converte o JSON de `/type/{id}/` nas seis relações de dano."""
    try:
        identifier = int(_require(payload, "id", source_url))
    except (TypeError, ValueError) as exc:
        raise MalformedResponseError(
            f"O campo 'id' de {source_url} não é numérico."
        ) from exc

    name = _require(payload, "name", source_url)
    if not isinstance(name, str):
        raise MalformedResponseError(f"O campo 'name' de {source_url} não é um texto.")

    relations = _require(payload, "damage_relations", source_url)
    if not isinstance(relations, dict):
        raise MalformedResponseError(
            f"O campo 'damage_relations' de {source_url} não é um objeto."
        )

    return PokemonType(
        id=identifier,
        name=name,
        damage_relations=DamageRelations(
            double_damage_from=_resource_names(relations.get("double_damage_from")),
            half_damage_from=_resource_names(relations.get("half_damage_from")),
            no_damage_from=_resource_names(relations.get("no_damage_from")),
            double_damage_to=_resource_names(relations.get("double_damage_to")),
            half_damage_to=_resource_names(relations.get("half_damage_to")),
            no_damage_to=_resource_names(relations.get("no_damage_to")),
        ),
        source_url=source_url,
    )
