# Pokémon MCP Server

Laboratório didático para aprender **o que é e como funciona um MCP Server**.
Ele expõe dados reais da [PokéAPI](https://pokeapi.co/docs/v2) como Tools, um
Resource e um Prompt pelo protocolo MCP, usando o transporte Streamable HTTP.

O servidor **não contém um modelo de linguagem** e não precisa de chave de API.
Quem interpreta a pergunta e escolhe uma Tool é o cliente de IA conectado; este
projeto apenas consulta, valida e resume os dados da PokéAPI.

## Escolha seu caminho

| Quero... | Comece por |
| --- | --- |
| testar o servidor em cinco minutos | [Quickstart](#quickstart-em-cinco-minutos) |
| conectar VS Code, Codex ou outro cliente | [Guia de conexão](docs/conectar-cliente.md) |
| entender cada etapa da requisição | [Como o servidor funciona](docs/como-funciona.md) |
| estudar ou modificar o projeto | [Estudar e desenvolver](#estudar-e-desenvolver) |

## Quickstart em cinco minutos

### 1. Pré-requisito

Você precisa apenas de Docker para executar o servidor:

```bash
docker --version
```

Para experimentar as capacidades numa interface visual, o passo 4 usa o MCP
Inspector e requer Node.js. Ele é opcional: qualquer cliente compatível com
Streamable HTTP pode se conectar ao mesmo endpoint.

### 2. Execute a imagem publicada

```bash
docker run -d --name pokemon-mcp-server \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/higorcamposs/pokemon-mcp-server:0.1.2
```

O mapeamento começa com `127.0.0.1` de propósito: o servidor fica disponível
somente na sua máquina. Ele não tem autenticação e não deve ser exposto à rede
ou à internet.

### 3. Confirme que o processo está no ar

```bash
docker ps
curl http://localhost:8000/health
```

Resposta esperada do `curl`:

```json
{"status":"ok","server":"pokemon-mcp-server"}
```

O endpoint MCP é:

```text
http://localhost:8000/mcp
```

`/health` prova que o processo respondeu. A próxima etapa prova que o protocolo
MCP e as capacidades do servidor estão funcionando.

### 4. Conecte o MCP Inspector

Com Node.js instalado, execute:

```bash
npx @modelcontextprotocol/inspector \
  --server-url http://localhost:8000/mcp \
  --transport http
```

Abra no navegador a URL impressa pelo comando. No Inspector:

1. conecte ao servidor;
2. abra **Tools**;
3. selecione `get_pokemon`;
4. preencha `name_or_id` com `pikachu`;
5. execute a Tool.

O resultado estruturado contém dados como estes:

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
  "base_stats": {
    "hp": 35,
    "attack": 55,
    "defense": 40,
    "special-attack": 50,
    "special-defense": 50,
    "speed": 90
  },
  "source_url": "https://pokeapi.co/api/v2/pokemon/pikachu/"
}
```

Confira também os logs:

```bash
docker logs pokemon-mcp-server
```

Eles devem mostrar a consulta à PokéAPI ou um `cache hit` se o mesmo Pokémon já
tiver sido consultado dentro do TTL.

### 5. Encerre o servidor

```bash
docker rm -f pokemon-mcp-server
```

Para receitas específicas de VS Code, Codex e MCP Inspector, consulte o
[guia de conexão](docs/conectar-cliente.md).

## Como funciona em 60 segundos

```text
Usuário
  │ pergunta em linguagem natural
  ▼
Aplicação de IA / Host
  └── modelo escolhe uma Tool
        │ chamada MCP por Streamable HTTP
        ▼
      Pokémon MCP Server
        ├── valida o argumento
        ├── consulta e guarda cache
        ├── converte unidades
        └── valida o JSON recebido
              │ HTTPS / REST
              ▼
            PokéAPI

PokéAPI → resposta bruta → MCP Server → resposta estruturada → cliente → usuário
```

O protocolo MCP fica entre o cliente e este servidor. Entre o servidor e a
PokéAPI continua existindo HTTP/REST comum. Publicar a imagem no GHCR distribui
o programa, mas não cria um endpoint público: o contêiner roda na máquina de
quem o iniciou.

O fluxo completo, incluindo os arquivos envolvidos em cada etapa, está em
[docs/como-funciona.md](docs/como-funciona.md).

## O que o servidor oferece

| Capacidade | Função | Neste projeto |
| --- | --- | --- |
| Tool | executa uma operação | três consultas à PokéAPI |
| Resource | fornece conteúdo por URI | `pokemon://guide` |
| Prompt | fornece um template | `compare_pokemon` |

### Tools

- `get_pokemon`: tipos, unidades, habilidades e atributos base.
- `get_ability`: descrição em inglês e origem do texto.
- `get_type`: seis relações de dano de um tipo isolado.

As Tools aceitam nomes canônicos (`pikachu`, `mr-mime`) ou identificadores
positivos (`25`). Espaços nas extremidades e letras maiúsculas são
normalizados. Toda resposta traz `source_url`, a URL exata consultada.

### Resource e Prompt

- `pokemon://guide` explica as capacidades, a origem dos dados e os limites do
  laboratório.
- `compare_pokemon(pokemon_a, pokemon_b)` devolve instruções para o cliente
  consultar dois Pokémon e compará-los sem inventar um vencedor de batalha.

Obter o Prompt não executa Tools e não chama um modelo. O servidor devolve
apenas o template; a aplicação conectada decide o que fazer com ele.

## Estudar e desenvolver

### 1. Clone e suba o projeto

```bash
git clone https://github.com/higorcamposs/pokemon-mcp-server.git
cd pokemon-mcp-server
docker compose up -d --build
docker compose ps
```

O status deve ficar `healthy`. O endpoint continua sendo
`http://localhost:8000/mcp`.

### 2. Execute os testes automatizados

```bash
docker compose --profile test run --build --rm tests
```

Os testes usam respostas gravadas e transporte HTTP simulado; a disponibilidade
da PokéAPI não faz parte da suíte automatizada.

### 3. Execute o smoke test MCP

Com o servidor no ar:

```bash
docker compose --profile test run --build --rm smoke
```

O smoke test conecta pelo protocolo MCP, descobre as capacidades, chama as três
Tools, lê o Resource e obtém o Prompt. Ele faz poucas consultas reais à
PokéAPI.

### 4. Localize cada responsabilidade

Dentro de `src/pokemon_mcp/`:

| Arquivo | Responsabilidade |
| --- | --- |
| `__main__.py` | transporte HTTP e allowlists |
| `server.py` | capacidades MCP e `/health` |
| `pokeapi.py` | integração HTTP e cache |
| `models.py` | validação e modelos de saída |

Leia [Como o servidor funciona](docs/como-funciona.md) para acompanhar uma
requisição por esses quatro módulos e entender como adaptar o laboratório.

Para encerrar o ambiente de desenvolvimento:

```bash
docker compose down
```

## Configuração essencial

Todas as variáveis são opcionais. `.env.example` documenta porta, URL da
PokéAPI, timeout, cache, logs e allowlists com seus respectivos padrões.

Se a porta 8000 estiver ocupada:

```bash
MCP_HOST_PORT=8001 docker compose up -d --build
```

O endpoint passa a ser `http://localhost:8001/mcp`, e o Compose ajusta as
allowlists. Veja a [configuração de Host, Origin e porta](docs/conectar-cliente.md#host-origin-e-porta).

## Limites e segurança

- O servidor não simula batalhas nem determina vencedores.
- Relações de tipo não combinam os dois tipos de um Pokémon nem consideram
  habilidades, itens, movimentos ou condições de campo.
- Habilidades são possibilidades da espécie; um indivíduo usa uma por vez.
- Descrições de habilidade vêm em inglês e não são traduzidas pelo servidor.
- O cache existe apenas em memória e desaparece quando o contêiner reinicia.
- O servidor depende da PokéAPI e devolve erro quando ela está indisponível.
- Não há autenticação. O serviço deve permanecer no loopback e não deve ser
  publicado em rede, túnel público ou internet.

## Diagnóstico rápido

- **Contêiner não fica saudável:** leia `docker logs pokemon-mcp-server`.
- **Porta 8000 ocupada:** use `MCP_HOST_PORT=8001` com o Compose.
- **HTTP 421:** use `localhost` ou autorize o Host exato mostrado no log.
- **HTTP 403:** autorize a Origin completa mostrada no log.
- **PokéAPI indisponível:** confira a internet do contêiner e tente depois.

Se `/health` funciona, mas o cliente não conecta, execute o smoke test para
separar um problema do servidor de um problema específico do cliente. Veja o
[diagnóstico detalhado](docs/conectar-cliente.md#diagnostico).

## Documentação

### Para usar o servidor

- [Conectar MCP Inspector, VS Code ou Codex](docs/conectar-cliente.md)
- [Como o servidor funciona](docs/como-funciona.md)

### Para estudar o projeto

- [Versões, decisões e referências oficiais](docs/versoes-e-referencias.md)
- [Registro de validações executadas](docs/validacao.md)
- [Roteiro para capturar evidências da apresentação](docs/roteiro-prints.md)

### Para manter e publicar

- [Publicar uma nova imagem no GHCR](docs/publicar-imagem.md)
- `compose.ghcr.yaml`: executar a imagem publicada sem clonar o repositório
- `.env.example`: referência completa das variáveis de ambiente

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).
