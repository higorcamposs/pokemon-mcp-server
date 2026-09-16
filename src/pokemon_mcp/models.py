"""Schemas de saída das Tools e mapeamento do JSON da PokéAPI.

Cada função aqui é pura: recebe o JSON bruto e a URL consultada e devolve um
modelo Pydantic enxuto. Nada de rede, o que deixa tudo testável sem internet.

Unidades: a documentação da PokéAPI descreve `height` em decímetros e `weight`
em hectogramas (https://pokeapi.co/docs/v2#pokemon). A conversão para metros e
quilogramas acontece aqui, uma única vez.

Validação: os campos que a Tool promete no seu schema são obrigatórios. Se a
PokéAPI devolver algo fora do formato esperado, o resultado é um
`MalformedResponseError` explícito — nunca uma ficha aparentemente completa com
listas vazias no lugar dos dados que faltaram.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, Field

from .pokeapi import MalformedResponseError

DECIMETRES_TO_METRES: Final = 0.1
HECTOGRAMS_TO_KILOGRAMS: Final = 0.1

REQUIRED_STAT_NAMES: Final = (
    "hp",
    "attack",
    "defense",
    "special-attack",
    "special-defense",
    "speed",
)
"""Atributos base que toda ficha de Pokémon da PokéAPI traz.

São os seis `stat` com `is_battle_only=false` do endpoint `/stat/`. Conferido
em 16/09/2026 na base completa: 1351 Pokémon e 8106 registros de `stat`, ou
seja, exatamente seis por Pokémon.
"""

DAMAGE_RELATION_FIELDS: Final = (
    "double_damage_from",
    "double_damage_to",
    "half_damage_from",
    "half_damage_to",
    "no_damage_from",
    "no_damage_to",
)
"""As seis propriedades de `damage_relations` em `/type/{id}/`."""

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
    "Estas relações descrevem um tipo isolado e não consideram a combinação de "
    "tipos, habilidades, itens e outras condições de um Pokémon específico. "
    "Elas não determinam o resultado de um confronto: isto não é um simulador "
    "de batalha."
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


# --- validação do JSON bruto ----------------------------------------------
#
# As funções abaixo trocam qualquer formato inesperado por
# `MalformedResponseError`. Nenhuma delas converte tipos "na marra": não existe
# `bool("false")` nem `int("abc")` aqui, justamente para que um `ValueError` ou
# `TypeError` não escape da Tool como erro genérico.


def _malformed(url: str, detail: str) -> MalformedResponseError:
    return MalformedResponseError(f"A resposta de {url} {detail}")


def _require(payload: dict[str, Any], key: str, url: str, label: str | None = None) -> Any:
    """Valor de um campo obrigatório. Campo ausente é erro, não lista vazia."""
    if key not in payload:
        raise _malformed(url, f"não traz o campo obrigatório '{label or key}'.")
    return payload[key]


def _as_str(value: Any, label: str, url: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _malformed(url, f"traz '{label}' que não é um texto preenchido.")
    return value


def _as_int(value: Any, label: str, url: str, *, minimum: int) -> int:
    # `bool` é subclasse de `int` em Python: True/False não valem como número.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _malformed(url, f"traz '{label}' que não é um número inteiro.")
    if value < minimum:
        raise _malformed(
            url, f"traz '{label}' = {value}, abaixo do mínimo esperado ({minimum})."
        )
    return value


def _as_bool(value: Any, label: str, url: str) -> bool:
    if not isinstance(value, bool):
        raise _malformed(url, f"traz '{label}' que não é um booleano.")
    return value


def _as_list(value: Any, label: str, url: str) -> list[Any]:
    if not isinstance(value, list):
        raise _malformed(url, f"traz '{label}' que não é uma lista.")
    return value


def _as_dict(value: Any, label: str, url: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _malformed(url, f"traz '{label}' que não é um objeto JSON.")
    return value


def _resource_names(value: Any, label: str, url: str) -> list[str]:
    """Nomes de uma lista de NamedAPIResource (`[{"name": ..., "url": ...}]`).

    A lista precisa existir e cada item precisa ter um nome. Uma lista
    realmente vazia é aceita: a PokéAPI tem casos legítimos, como o tipo
    `unknown`, cujas seis relações de dano vêm vazias.
    """
    entries = _as_list(value, label, url)
    names: list[str] = []
    for index, entry in enumerate(entries):
        item = _as_dict(entry, f"{label}[{index}]", url)
        names.append(_as_str(_require(item, "name", url, f"{label}[{index}].name"),
                             f"{label}[{index}].name", url))
    return names


def _nested_names(value: Any, label: str, inner_key: str, url: str) -> list[str]:
    """Nomes em `entry[inner_key]['name']`, como em `types[].type.name`."""
    entries = _as_list(value, label, url)
    names: list[str] = []
    for index, entry in enumerate(entries):
        item = _as_dict(entry, f"{label}[{index}]", url)
        inner_label = f"{label}[{index}].{inner_key}"
        inner = _as_dict(_require(item, inner_key, url, inner_label), inner_label, url)
        names.append(
            _as_str(
                _require(inner, "name", url, f"{inner_label}.name"),
                f"{inner_label}.name",
                url,
            )
        )
    return names


def build_pokemon(payload: dict[str, Any], source_url: str) -> Pokemon:
    """Converte o JSON de `/pokemon/{id}/` na ficha resumida.

    Todos os campos que o schema da Tool promete são obrigatórios: `id`,
    `name`, `height`, `weight`, `types`, `abilities` e `stats`. Um campo
    ausente ou com tipo errado vira `MalformedResponseError`.

    Limites numéricos: `id` é positivo; `height` e `weight` não podem ser
    negativos. Zero é aceito em `weight` porque existe na base real
    (`eternatus-eternamax`, id 10190, tem `weight: 0`). Nenhum limite superior
    é inventado: a documentação da PokéAPI não define nenhum.
    """
    identifier = _as_int(_require(payload, "id", source_url), "id", source_url, minimum=1)
    name = _as_str(_require(payload, "name", source_url), "name", source_url)
    height = _as_int(
        _require(payload, "height", source_url), "height", source_url, minimum=0
    )
    weight = _as_int(
        _require(payload, "weight", source_url), "weight", source_url, minimum=0
    )

    types = _nested_names(
        _require(payload, "types", source_url), "types", "type", source_url
    )

    abilities: list[PokemonAbility] = []
    # A lista pode vir vazia de verdade: nove Pokémon da base (por exemplo
    # `zygarde-mega`, id 10301) têm "abilities": []. O que não vale é a chave
    # sumir ou vir com outro tipo.
    for index, entry in enumerate(
        _as_list(_require(payload, "abilities", source_url), "abilities", source_url)
    ):
        label = f"abilities[{index}]"
        item = _as_dict(entry, label, source_url)
        inner = _as_dict(
            _require(item, "ability", source_url, f"{label}.ability"),
            f"{label}.ability",
            source_url,
        )
        abilities.append(
            PokemonAbility(
                name=_as_str(
                    _require(inner, "name", source_url, f"{label}.ability.name"),
                    f"{label}.ability.name",
                    source_url,
                ),
                is_hidden=_as_bool(
                    _require(item, "is_hidden", source_url, f"{label}.is_hidden"),
                    f"{label}.is_hidden",
                    source_url,
                ),
                slot=_as_int(
                    _require(item, "slot", source_url, f"{label}.slot"),
                    f"{label}.slot",
                    source_url,
                    minimum=1,
                ),
            )
        )

    base_stats: dict[str, int] = {}
    for index, entry in enumerate(
        _as_list(_require(payload, "stats", source_url), "stats", source_url)
    ):
        label = f"stats[{index}]"
        item = _as_dict(entry, label, source_url)
        inner = _as_dict(
            _require(item, "stat", source_url, f"{label}.stat"),
            f"{label}.stat",
            source_url,
        )
        stat_name = _as_str(
            _require(inner, "name", source_url, f"{label}.stat.name"),
            f"{label}.stat.name",
            source_url,
        )
        base_stats[stat_name] = _as_int(
            _require(item, "base_stat", source_url, f"{label}.base_stat"),
            f"{label}.base_stat",
            source_url,
            minimum=0,
        )

    missing = [stat for stat in REQUIRED_STAT_NAMES if stat not in base_stats]
    if missing:
        raise _malformed(
            source_url,
            f"não traz os atributos base obrigatórios: {', '.join(missing)}.",
        )

    return Pokemon(
        id=identifier,
        name=name,
        types=types,
        # round() evita ruído de ponto flutuante como 0.30000000000000004.
        height_m=round(height * DECIMETRES_TO_METRES, 2),
        weight_kg=round(weight * HECTOGRAMS_TO_KILOGRAMS, 2),
        abilities=abilities,
        base_stats=base_stats,
        source_url=source_url,
    )


def _english_effect(payload: dict[str, Any], source_url: str) -> dict[str, str] | None:
    """Primeira entrada de `effect_entries` em inglês com texto aproveitável.

    Texto em branco não conta como descrição: uma entrada com
    `{"effect": "", "short_effect": ""}` é ignorada para que o fallback para
    `flavor_text_entries` continue valendo.
    """
    entries = payload.get("effect_entries")
    if entries is None:
        return None

    for index, entry in enumerate(_as_list(entries, "effect_entries", source_url)):
        if not isinstance(entry, dict):
            continue
        language = entry.get("language")
        if not isinstance(language, dict) or language.get("name") != "en":
            continue
        effect = entry.get("effect")
        short_effect = entry.get("short_effect")
        effect = effect.strip() if isinstance(effect, str) else ""
        short_effect = short_effect.strip() if isinstance(short_effect, str) else ""
        if effect or short_effect:
            return {"effect": effect, "short_effect": short_effect}
    return None


def _english_flavor_text(payload: dict[str, Any], source_url: str) -> str | None:
    """Primeiro `flavor_text` em inglês com conteúdo, usado como fallback."""
    entries = payload.get("flavor_text_entries")
    if entries is None:
        return None

    for entry in _as_list(entries, "flavor_text_entries", source_url):
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
    """Converte o JSON de `/ability/{id}/`, preferindo a descrição em inglês.

    Ordem de preferência: `effect_entries` em inglês com texto, depois
    `flavor_text_entries` em inglês com texto e, por fim, campos nulos com uma
    nota explicando a ausência. Nenhum texto é gerado nem traduzido aqui.
    """
    identifier = _as_int(_require(payload, "id", source_url), "id", source_url, minimum=1)
    name = _as_str(_require(payload, "name", source_url), "name", source_url)

    effect_entry = _english_effect(payload, source_url)
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

    flavor_text = _english_flavor_text(payload, source_url)
    if flavor_text is not None:
        return Ability(
            id=identifier,
            name=name,
            short_effect=flavor_text,
            effect=None,
            language="en",
            description_source="flavor_text_entries",
            note=(
                "Esta habilidade não tem 'effect_entries' em inglês com texto na "
                "PokéAPI; o texto veio de 'flavor_text_entries', que é mais curto."
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
    """Converte o JSON de `/type/{id}/` nas seis relações de dano.

    As seis propriedades são obrigatórias. Uma lista vazia é aceita quando a
    propriedade existe e realmente é vazia (o tipo `unknown` é assim na
    PokéAPI); propriedade ausente é `MalformedResponseError`.
    """
    identifier = _as_int(_require(payload, "id", source_url), "id", source_url, minimum=1)
    name = _as_str(_require(payload, "name", source_url), "name", source_url)

    relations = _as_dict(
        _require(payload, "damage_relations", source_url),
        "damage_relations",
        source_url,
    )

    names = {
        field: _resource_names(
            _require(relations, field, source_url, f"damage_relations.{field}"),
            f"damage_relations.{field}",
            source_url,
        )
        for field in DAMAGE_RELATION_FIELDS
    }

    return PokemonType(
        id=identifier,
        name=name,
        damage_relations=DamageRelations(**names),
        source_url=source_url,
    )
