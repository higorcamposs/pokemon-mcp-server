# Pokémon MCP Server

Laboratório didático que responde, com código funcionando, à pergunta
**"o que é e como criar um MCP Server?"**.

O servidor roda em contêiner, fala o **Model Context Protocol (MCP)** por
Streamable HTTP e consulta a [PokéAPI](https://pokeapi.co/docs/v2) para
entregar dados reais sobre Pokémon, habilidades e tipos.

Ele **não contém um modelo de linguagem**. Quem raciocina sobre os dados é a
aplicação de IA conectada como cliente MCP; o servidor apenas expõe
capacidades e devolve dados.

## Conceitos que este laboratório demonstra

- A **PokéAPI é a fonte de dados**, não o MCP Server. Ela é uma API REST
  pública e não fala MCP.
- O **MCP Server integra a PokéAPI**: recebe uma chamada MCP, consulta a API
  por HTTPS, normaliza a resposta e devolve algo enxuto e citável.
- **MCP é o protocolo entre cliente e servidor.** Entre o servidor e a PokéAPI
  continua sendo HTTP/REST comum.
- O **servidor não precisa de um LLM embutido**, nem de chave de nenhum
  provedor de IA. Ele é testável sozinho.
- **Compatibilidade depende do transporte e das capacidades do cliente.** Nem
  toda aplicação de IA fala Streamable HTTP, e nem toda aplicação usa Resources
  ou Prompts.
- **Publicar o código no GitHub não hospeda o servidor.** Quem executa o
  contêiner é você, na sua máquina.

## Arquitetura

```
Usuário
  ↕
Aplicação de IA / Host
  └── MCP Client
        ↕  protocolo MCP sobre Streamable HTTP  →  http://localhost:8000/mcp
      Pokémon MCP Server (contêiner Docker)
        ↕  HTTPS / REST
      PokéAPI  →  https://pokeapi.co/api/v2/
```

O contêiner escuta em `0.0.0.0:8000` internamente, mas o Compose publica a
porta **somente em `127.0.0.1`**. O serviço não fica acessível pela rede.

## Obter o projeto

```bash
git clone https://github.com/higorcamposs/pokemon-mcp-server.git
cd pokemon-mcp-server
```

## Pré-requisitos

- Docker e Docker Compose (`docker compose version`).
- Acesso à internet, para que o contêiner alcance a PokéAPI.

**Não é preciso ter Python nem `uv` instalados na máquina.** Tudo roda dentro
dos contêineres, inclusive os testes.

## Como usar

### Iniciar

```bash
docker compose up -d --build
```

Nenhum arquivo precisa ser criado antes. O `.env` é opcional: os padrões estão
no `compose.yaml` e documentados no `.env.example`.

Endpoint MCP: **`http://localhost:8000/mcp`** (transporte Streamable HTTP).

### Verificar se está no ar

```bash
docker compose ps                      # deve mostrar STATUS "healthy"
curl http://localhost:8000/health      # {"status":"ok", ...}
```

`GET /health` é uma rota HTTP auxiliar: ela não consulta a PokéAPI, não é uma
ferramenta MCP e **não prova que o protocolo funciona**. Para isso, use o smoke
test abaixo.

### Ver os logs

```bash
docker compose logs -f pokemon-mcp-server
```

### Testar

Testes automatizados, sem internet e com respostas HTTP simuladas:

```bash
docker compose --profile test run --build --rm tests
```

O `--build` não é enfeite: sem ele o Compose reaproveita a imagem `dev` que já
existir na máquina, e você pode acabar rodando os testes de uma versão anterior
do código. Ele reconstrói usando o cache de camadas do Docker, então continua
rápido — não é preciso `--no-cache`.

Smoke test pelo protocolo MCP de verdade, contra o contêiner em execução
(faz poucas consultas reais à PokéAPI):

```bash
docker compose --profile test run --build --rm smoke
```

O smoke test usa o cliente do SDK oficial: ele conecta no endpoint HTTP,
descobre as capacidades, chama as três Tools, lê o Resource, obtém o Prompt e
sai com código diferente de zero em caso de falha. Nenhuma função Python do
servidor é chamada diretamente.

Se preferir rodar o smoke test fora do Docker (aí sim precisa de Python e do
pacote `mcp` instalados):

```bash
python scripts/smoke_test.py http://localhost:8000/mcp
```

### Encerrar

```bash
docker compose down
```

## Capacidades expostas

### Tools

| Tool | Argumento | Consulta | Devolve |
| --- | --- | --- | --- |
| `get_pokemon` | `name_or_id` (texto) | `GET /api/v2/pokemon/{name_or_id}/` | `id`, `name`, `types`, `height_m`, `weight_kg`, `abilities` (com `is_hidden`), `base_stats`, `source_url` |
| `get_ability` | `name_or_id` (texto) | `GET /api/v2/ability/{name_or_id}/` | `id`, `name`, `short_effect`, `effect`, `language`, `description_source`, `source_url` |
| `get_type` | `name_or_id` (texto) | `GET /api/v2/type/{name_or_id}/` | `id`, `name`, `damage_relations` (seis listas), `source_url` |

As três são somente leitura (`read_only_hint=True`) e todas devolvem
`source_url`, a URL exata consultada na PokéAPI.

### Resource

| URI | Tipo | Conteúdo |
| --- | --- | --- |
| `pokemon://guide` | `text/markdown` | Objetivo do servidor, ferramentas, exemplos de identificadores, origem dos dados e limitações do laboratório. |

### Prompt

| Nome | Argumentos | O que faz |
| --- | --- | --- |
| `compare_pokemon` | `pokemon_a`, `pokemon_b` | Devolve um template de mensagens orientando o assistente a consultar os dois Pokémon com `get_pokemon`, comparar tipos, atributos base e habilidades, responder em português e não declarar vencedor. |

**Disponibilizar um Prompt é diferente de executá-lo.** Obter
`compare_pokemon` devolve apenas o texto do template: o servidor não chama
ferramentas nem modelo nenhum. Quem decide seguir as instruções, chamar
`get_pokemon` duas vezes e escrever a resposta é a aplicação de IA, depois que
o usuário escolhe esse Prompt no cliente. Isso é verificado no teste
`test_compare_pokemon_prompt_returns_a_template`, que confere que nenhuma
requisição HTTP saiu do servidor ao obter o Prompt.

## Exemplos de uso

Identificadores aceitos: nome canônico em minúsculas com hífen (`pikachu`,
`mr-mime`) ou número positivo (`25`). Espaços nas extremidades e maiúsculas são
normalizados.

| Pergunta em linguagem natural no cliente | Tool que o assistente tende a usar |
| --- | --- |
| "Quais são os tipos e as habilidades do Pikachu?" | `get_pokemon` com `pikachu` |
| "O que faz a habilidade Static?" | `get_ability` com `static` |
| "Quais tipos causam dano dobrado ao tipo elétrico?" | `get_type` com `electric` |
| "Compare Pikachu e Bulbasaur pelos atributos base." | `get_pokemon` duas vezes (ou o Prompt `compare_pokemon`) |

Resposta real de `get_pokemon` com `name_or_id="pikachu"` (campo
`structured_content`, abreviado):

```json
{
  "id": 25,
  "name": "pikachu",
  "types": ["electric"],
  "height_m": 0.4,
  "weight_kg": 6.0,
  "abilities": [
    {"name": "static", "is_hidden": false, "slot": 1},
    {"name": "lightning-rod", "is_hidden": true, "slot": 3}
  ],
  "base_stats": {"hp": 35, "attack": 55, "defense": 40, "speed": 90},
  "source_url": "https://pokeapi.co/api/v2/pokemon/pikachu/"
}
```

A PokéAPI devolve `height` em decímetros e `weight` em hectogramas; a conversão
para metros e quilogramas é feita pelo servidor.

## Conectar um cliente MCP

Passo a passo (MCP Inspector e exemplo de configuração para uma aplicação de
IA compatível) em **[docs/conectar-cliente.md](docs/conectar-cliente.md)**.

Resumo: endpoint `http://localhost:8000/mcp`, transporte Streamable HTTP, sem
autenticação.

## Estrutura do projeto

```
pokemon-mcp-server/
├── src/pokemon_mcp/
│   ├── __main__.py     # transporte, portas e allowlist de Host/Origin
│   ├── server.py       # MCPServer: Tools, Resource, Prompt e /health
│   ├── pokeapi.py      # HTTP, normalização, cache e erros
│   └── models.py       # schemas de saída e conversão de unidades
├── tests/              # testes automatizados, sem internet
├── scripts/smoke_test.py
├── docs/
│   ├── conectar-cliente.md
│   ├── roteiro-prints.md
│   ├── validacao.md
│   └── versoes-e-referencias.md
├── .github/workflows/  # CI: instala o projeto e roda os testes
├── Dockerfile          # runtime (não root) e dev (testes)
├── compose.yaml
├── pyproject.toml / uv.lock
├── LICENSE
└── .env.example
```

## Configuração

Todas as variáveis são opcionais e têm padrão. Veja `.env.example` para copiar
como `.env`. As principais:

| Variável | Padrão | Para que serve |
| --- | --- | --- |
| `POKEAPI_BASE_URL` | `https://pokeapi.co/api/v2/` | Base fixa das consultas. As Tools **não** aceitam URL como argumento. |
| `POKEAPI_TIMEOUT_SECONDS` | `10` | Tempo limite de cada consulta. |
| `POKEAPI_CACHE_TTL_SECONDS` | `300` | Validade de cada entrada no cache em memória. |
| `POKEAPI_CACHE_MAX_ENTRIES` | `256` | Tamanho máximo do cache (descarte LRU). |
| `MCP_HOST_PORT` | `8000` | Porta publicada na sua máquina, sempre em `127.0.0.1`. |
| `MCP_LOG_LEVEL` | `INFO` | Nível de log. |
| `MCP_ALLOWED_HOSTS` | derivada de `MCP_HOST_PORT` pelo `compose.yaml` | Allowlist do cabeçalho `Host` (proteção contra DNS rebinding). Definir no `.env` **não** tem efeito sob o Compose. |
| `MCP_ALLOWED_ORIGINS` | derivada de `MCP_HOST_PORT` pelo `compose.yaml` | O mesmo, para o cabeçalho `Origin`. |
| `MCP_EXTRA_ALLOWED_HOSTS` | vazio | **É aqui que você acrescenta um host seu**, pelo `.env`. O valor é somado à allowlist. |
| `MCP_EXTRA_ALLOWED_ORIGINS` | vazio | O mesmo, para `Origin`. |

As três variáveis numéricas precisam ser números finitos e não negativos
(`POKEAPI_TIMEOUT_SECONDS` precisa ser maior que zero; nas duas do cache, `0`
desliga o cache). Um valor fora disso — texto, negativo, `nan`, `inf` — não
chega ao cliente HTTP nem ao cache: o servidor registra um aviso no log e usa o
padrão da tabela.

### As allowlists de `Host` e `Origin`

A lista que o servidor usa é a **soma** de três partes, nesta ordem:

1. os mínimos obrigatórios, fixos em `src/pokemon_mcp/__main__.py`
   (`127.0.0.1:8000`, `localhost:8000`, `[::1]:8000`) — a porta **interna** do
   contêiner, de que o healthcheck e o contêiner de smoke dependem;
2. `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS`, que o `compose.yaml` deriva de
   `MCP_HOST_PORT` (a porta publicada na sua máquina);
3. `MCP_EXTRA_ALLOWED_HOSTS`/`MCP_EXTRA_ALLOWED_ORIGINS`, lidas do seu `.env`.

Somar em vez de substituir é proposital: assim um `.env` mal preenchido
acrescenta um host, mas nunca remove `localhost` da lista e derruba o
laboratório sem explicação. Repetições e espaços são descartados.

```dotenv
# .env
MCP_EXTRA_ALLOWED_HOSTS=meu-host.local:8000
MCP_EXTRA_ALLOWED_ORIGINS=http://meu-host.local:8000
```

A proteção contra DNS rebinding continua ligada em qualquer combinação. Para
ver a lista final, leia as linhas `Host allowlist:` e `Origin allowlist:` em
`docker compose logs pokemon-mcp-server`.

**Dentro do contêiner, o endereço é fixo:** `0.0.0.0:8000` e endpoint `/mcp`.
Não existe variável para mudar isso, e é de propósito: o healthcheck, o smoke
test e a allowlist de `Host` dependem desse valor, e deixá-los livres só cria
combinações que não funcionam. O que dá para mudar é a porta publicada na sua
máquina, com `MCP_HOST_PORT` (use se a 8000 já estiver ocupada). Ao mudar:

- o endpoint do cliente passa a ser `http://localhost:<MCP_HOST_PORT>/mcp`;
- o Compose já acrescenta essa porta às allowlists de `Host` e `Origin`;
- um smoke test rodado **fora** do Docker precisa da nova URL;
- o smoke test rodado pelo Compose continua usando `http://localhost:8000/mcp`,
  porque o contêiner de smoke compartilha a rede do servidor.

## Limites do laboratório

- **Três Tools, um Resource e um Prompt.** Movimentos, evoluções, espécies e o
  resto da PokéAPI ficam de fora de propósito.
- **Não há simulador de batalha.** As relações de tipo descrevem um tipo
  isolado; elas não dizem quem vence um confronto. Um Pokémon tem um ou dois
  tipos, e o resultado real ainda depende de habilidades, nível, movimentos,
  itens e condições de campo.
- **Habilidades são possibilidades da espécie.** Um Pokémon individual tem
  apenas uma ativa por vez, e `is_hidden` marca a habilidade oculta.
- **Descrições de habilidade vêm em inglês**, como estão na PokéAPI. O servidor
  não traduz nem inventa texto; quando não há descrição, ele diz isso.
- **O cache é em memória** e se perde ao reiniciar o contêiner. Não há banco de
  dados no projeto.
- **Sem autenticação.** O serviço é publicado apenas em `127.0.0.1` e não deve
  ser exposto à internet, à rede corporativa ou por túneis públicos.
- **O servidor depende da PokéAPI estar no ar.** Se ela falhar, a Tool devolve
  erro; ela nunca inventa dados para preencher a lacuna.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
| --- | --- | --- |
| `docker compose ps` mostra `unhealthy` | O processo não subiu. | `docker compose logs pokemon-mcp-server` e leia o traceback. |
| O cliente não conecta e o log do servidor mostra `Invalid Host header` (HTTP 421) | O `Host` usado não está na allowlist. | Conecte por `http://localhost:8000/mcp` ou `http://127.0.0.1:8000/mcp`. Se precisar de outro nome, acrescente-o em `MCP_EXTRA_ALLOWED_HOSTS` no `.env` — **não** desligue a proteção. |
| HTTP 403 com `Invalid Origin header` | Cliente de navegador com `Origin` fora da lista. | Acrescente a origem exata a `MCP_EXTRA_ALLOWED_ORIGINS` no `.env`. |
| Porta 8000 ocupada | Outro serviço local. | Defina `MCP_HOST_PORT=8001` (no `.env` ou no ambiente) e suba de novo. As allowlists acompanham; o endpoint vira `http://localhost:8001/mcp`. |
| Tool responde "A PokéAPI está indisponível" | Sem internet no contêiner ou PokéAPI fora do ar. | Teste `curl https://pokeapi.co/api/v2/pokemon/pikachu/` na máquina. |
| Tool responde "Argumento inválido" | Entrada com espaço interno, URL, caminho ou acento. | Use nome canônico (`mr-mime`) ou número positivo. |
| Uma aplicação de IA hospedada na nuvem não enxerga o servidor | `localhost` dela não é a sua máquina. | Veja a explicação em [docs/conectar-cliente.md](docs/conectar-cliente.md). |

## Versões e referências

As versões fixadas e a documentação oficial consultada estão em
**[docs/versoes-e-referencias.md](docs/versoes-e-referencias.md)**.

Em resumo: Python 3.12, SDK oficial `mcp` 2.2.0 (linha 2.x, classe
`MCPServer`), `httpx2` 2.13.0 e `pydantic` 2.13.5. As dependências Python estão
fixadas no `uv.lock` (versão e hash); as imagens base do Docker usam tags de
linha (`python:3.12-slim-trixie`, Debian 13), que continuam em 3.12 mas recebem
atualizações — elas não estão fixadas por digest.

## Registro de validação

O que já foi verificado, onde e com qual resultado está em
**[docs/validacao.md](docs/validacao.md)** — incluindo a checklist para
preencher com a sua própria execução local.

## Material da apresentação

O roteiro para capturar os prints da parte prática está em
**[docs/roteiro-prints.md](docs/roteiro-prints.md)**. As imagens vão em
`assets/screenshots/`.
