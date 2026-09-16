#!/usr/bin/env python3
"""Smoke test do servidor em execução, falando MCP de verdade.

Conecta-se ao endpoint Streamable HTTP com o cliente do SDK oficial e exercita
todas as capacidades: as três Tools, o Resource e o Prompt. Nenhuma função
Python do servidor é chamada diretamente — tudo passa pelo protocolo e as
consultas chegam à PokéAPI real.

Uso:
    python scripts/smoke_test.py [URL]

Padrão: http://localhost:8000/mcp (ou a variável MCP_URL).
Sai com código 0 se tudo passar e 1 na primeira falha.
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Any

import anyio
from mcp import Client
from mcp.types import TextContent, TextResourceContents

DEFAULT_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")

EXPECTED_TOOLS = {"get_pokemon", "get_ability", "get_type"}
GUIDE_URI = "pokemon://guide"

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  [ok]    {label}")
        return
    suffix = f" — {detail}" if detail else ""
    print(f"  [FALHA] {label}{suffix}")
    failures.append(f"{label}{suffix}")


def structured(result: Any, label: str) -> dict[str, Any]:
    """Valida que a chamada deu certo e devolve o conteúdo estruturado."""
    if result.is_error:
        text = "\n".join(
            block.text for block in result.content if isinstance(block, TextContent)
        )
        check(label, False, f"a Tool devolveu erro: {text}")
        return {}
    if not isinstance(result.structured_content, dict):
        check(label, False, "sem structured_content")
        return {}
    return result.structured_content


async def run(url: str) -> None:
    print(f"Conectando a {url} (Streamable HTTP)\n")

    async with Client(url) as client:
        print("1. Conexão e identidade do servidor")
        check(
            "protocolo negociado pelo SDK",
            bool(client.protocol_version),
            "nenhuma versão negociada",
        )
        print(f"         versão do protocolo: {client.protocol_version}")
        if client.server_info is not None:
            print(
                f"         servidor: {client.server_info.name} "
                f"{client.server_info.version}"
            )
        capabilities = client.server_capabilities
        check("capacidade tools anunciada", capabilities.tools is not None)
        check("capacidade resources anunciada", capabilities.resources is not None)
        check("capacidade prompts anunciada", capabilities.prompts is not None)

        print("\n2. Descoberta das Tools")
        listing = await client.list_tools()
        found = {tool.name for tool in listing.tools}
        check(
            "as três Tools foram descobertas",
            EXPECTED_TOOLS <= found,
            f"encontradas: {sorted(found)}",
        )
        for tool in listing.tools:
            if tool.name in EXPECTED_TOOLS:
                print(f"         {tool.name}: {tool.title or '(sem título)'}")

        print("\n3. get_pokemon('pikachu')")
        data = structured(
            await client.call_tool("get_pokemon", {"name_or_id": "pikachu"}),
            "get_pokemon respondeu",
        )
        if data:
            check("id é 25", data.get("id") == 25, str(data.get("id")))
            check("nome é pikachu", data.get("name") == "pikachu")
            check("tipo electric presente", "electric" in (data.get("types") or []))
            check(
                "altura convertida para metros",
                data.get("height_m") == 0.4,
                str(data.get("height_m")),
            )
            check(
                "peso convertido para quilogramas",
                data.get("weight_kg") == 6.0,
                str(data.get("weight_kg")),
            )
            check("atributos base presentes", bool(data.get("base_stats")))
            check(
                "habilidade oculta sinalizada",
                any(a.get("is_hidden") for a in data.get("abilities") or []),
            )
            check("source_url presente", "pokeapi.co" in str(data.get("source_url")))
            print(f"         source_url: {data.get('source_url')}")

        print("\n4. get_ability('static')")
        data = structured(
            await client.call_tool("get_ability", {"name_or_id": "static"}),
            "get_ability respondeu",
        )
        if data:
            check("nome é static", data.get("name") == "static")
            check("idioma informado", data.get("language") == "en")
            check(
                "descrição disponível",
                bool(data.get("short_effect") or data.get("effect")),
            )
            check("source_url presente", "pokeapi.co" in str(data.get("source_url")))

        print("\n5. get_type('electric')")
        data = structured(
            await client.call_tool("get_type", {"name_or_id": "electric"}),
            "get_type respondeu",
        )
        if data:
            relations = data.get("damage_relations") or {}
            check(
                "as seis relações de dano estão presentes",
                {
                    "double_damage_from",
                    "double_damage_to",
                    "half_damage_from",
                    "half_damage_to",
                    "no_damage_from",
                    "no_damage_to",
                }
                <= set(relations),
                f"chaves: {sorted(relations)}",
            )
            check(
                "ground causa dano dobrado ao tipo elétrico",
                "ground" in (relations.get("double_damage_from") or []),
            )
            check("source_url presente", "pokeapi.co" in str(data.get("source_url")))

        print("\n6. Erro tratado: get_pokemon com nome inexistente")
        result = await client.call_tool("get_pokemon", {"name_or_id": "pikachuu"})
        check("a falha veio marcada como erro", result.is_error is True)
        check("sem dados estruturados na falha", result.structured_content is None)

        print(f"\n7. Resource {GUIDE_URI}")
        resources = await client.list_resources()
        uris = [str(resource.uri) for resource in resources.resources]
        check(f"{GUIDE_URI} está na listagem", GUIDE_URI in uris, f"listados: {uris}")

        read = await client.read_resource(GUIDE_URI)
        contents = read.contents[0] if read.contents else None
        check(
            "o guia foi lido como texto",
            isinstance(contents, TextResourceContents),
        )
        if isinstance(contents, TextResourceContents):
            check("o guia menciona as Tools", "get_pokemon" in contents.text)
            check(
                "o guia declara os limites",
                "Limitações do laboratório" in contents.text,
            )
            print(f"         {len(contents.text)} caracteres em Markdown")

        print("\n8. Prompt compare_pokemon")
        prompts = await client.list_prompts()
        names = [prompt.name for prompt in prompts.prompts]
        check("compare_pokemon está na listagem", "compare_pokemon" in names)

        rendered = await client.get_prompt(
            "compare_pokemon", {"pokemon_a": "pikachu", "pokemon_b": "bulbasaur"}
        )
        check("o Prompt devolveu mensagens", bool(rendered.messages))
        if rendered.messages:
            content = rendered.messages[0].content
            text = content.text if isinstance(content, TextContent) else ""
            check("o template cita os dois Pokémon", "pikachu" in text and "bulbasaur" in text)
            check("o template orienta a usar get_pokemon", "get_pokemon" in text)
            check(
                "o template proíbe declarar vencedor",
                "Não afirme quem venceria" in text,
            )


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    try:
        anyio.run(run, url)
    except Exception:  # noqa: BLE001 - o script precisa relatar qualquer falha
        print("\nErro ao falar com o servidor:\n")
        traceback.print_exc()
        print(
            "\nVerifique se o contêiner está no ar (docker compose ps) e se a URL "
            f"está correta ({url}). HTTP 421 significa que o cabeçalho Host não "
            "está na allowlist MCP_ALLOWED_HOSTS."
        )
        return 1

    print()
    if failures:
        print(f"SMOKE TEST FALHOU: {len(failures)} verificação(ões) com problema")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("SMOKE TEST OK: capacidades descobertas e executadas pelo protocolo MCP,")
    print("com dados reais da PokéAPI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
