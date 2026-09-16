# Validação do laboratório

Registro das evidências **reais** de funcionamento. A regra deste arquivo é
simples: só entra aqui o que foi executado e observado. Nada de resultado
esperado escrito como se tivesse acontecido.

Cada execução nova pode substituir a tabela abaixo (ou virar uma seção nova,
se você quiser manter o histórico).

## Ambiente da última validação

| Item | Valor |
| --- | --- |
| Data | 16/09/2026 |
| Commit testado | `36c8995` **mais** as alterações desta rodada ainda não commitadas (allowlists com extras, validação das variáveis numéricas, ordenação de `types` por slot, docs). Ao commitar, troque por um hash único. |
| Sistema operacional | macOS 26.6.2 (Darwin 25.6.0, arm64) |
| Docker | 29.7.2 |
| Docker Compose | v5.5.1 |
| Python (contêiner de testes) | 3.12.12 |
| Python (CI) | 3.12 (`actions/setup-python@v5` com `python-version: "3.12"`) |
| SDK MCP | `mcp` 2.2.0 (linha 2.x, classe `MCPServer`) |
| Endpoint MCP | `http://localhost:8000/mcp` (Streamable HTTP) |
| Versão do protocolo negociada no smoke | **`2026-07-28`** |

A versão do protocolo não é escolhida pelo projeto: ela é negociada pelo SDK no
handshake e impressa pelo `scripts/smoke_test.py`. Um SDK ou cliente diferente
pode negociar outra.

## CI

Workflow: [`.github/workflows/tests.yml`](../.github/workflows/tests.yml)
(nome `tests`), disparado em `push` para `main`, em `pull_request` e por
`workflow_dispatch`. Dois jobs:

| Job | O que faz |
| --- | --- |
| `pytest (Python 3.12)` | `uv sync --locked` e `uv run pytest -v` no `ubuntu-latest` |
| `docker build` | `docker build --target runtime -t pokemon-mcp-server:ci .` |

A CI **não** toca a PokéAPI real: os testes usam as respostas gravadas em
`tests/fixtures/` com um transporte HTTP simulado. A disponibilidade de uma API
externa nunca é condição de merge. O smoke test pelo protocolo MCP não roda na
CI — ele precisa do contêiner no ar e de internet, e é executado à mão.

| Resultado | Valor |
| --- | --- |
| `pytest` | **a preencher** com o resultado do run da CI para o commit desta rodada |
| Quantidade de testes | **186** (execução local de 16/09/2026; a suíte é a mesma na CI) |
| `docker build` | **a preencher** com o resultado do run da CI |
| Link do run | **a preencher** (aba *Actions* do repositório) |

> As duas linhas "a preencher" ficam assim de propósito: no momento em que este
> arquivo foi escrito, as alterações desta rodada ainda não tinham sido
> enviadas ao GitHub, então não existe run de CI para elas. Preencha depois do
> push, copiando o resultado real.

## Validação local

Sequência executada em 16/09/2026, na máquina descrita acima. Reproduza na sua
e substitua os resultados pelos seus.

| # | Comando | Resultado observado |
| --- | --- | --- |
| 1 | `docker compose config -q` | sem saída (configuração válida) ✅ |
| 2 | `docker compose up -d --build` | imagem `pokemon-mcp-server:0.1.0` construída, contêiner iniciado ✅ |
| 3 | `docker compose ps` | `Up ... (healthy)`, portas `127.0.0.1:8000->8000/tcp` ✅ |
| 4 | `curl http://localhost:8000/health` | `{"status":"ok","server":"pokemon-mcp-server"}` ✅ |
| 5 | `docker compose --profile test run --build --rm tests` | `186 passed in 0.43s` (Python 3.12.12, pytest 9.1.1) ✅ |
| 6 | `docker compose --profile test run --build --rm smoke` | `SMOKE TEST OK`, código de saída 0, 33 verificações `[ok]` e nenhuma `[FALHA]`, protocolo `2026-07-28` ✅ |
| 7 | `docker compose logs pokemon-mcp-server` | allowlists registradas na inicialização, `GET /health 200 OK`, nenhum traceback ✅ — a única linha de falha é a esperada do passo 7 do smoke (`Tool 'get_pokemon' failed: ... não encontrou 'pikachuu'`), que é o teste de erro tratado |

Os comandos, na ordem:

```bash
docker compose config -q
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
docker compose --profile test run --build --rm tests
docker compose --profile test run --build --rm smoke
docker compose logs pokemon-mcp-server
```

O `--build` nos dois últimos não é opcional na prática: sem ele o Compose
reaproveita uma imagem `dev` antiga e você pode validar código que não é o
atual.

### Allowlist com porta e host personalizados

Verificação extra de 16/09/2026, para confirmar que o `.env` realmente
complementa a allowlist sem remover os mínimos:

```bash
MCP_HOST_PORT=8001 \
MCP_EXTRA_ALLOWED_HOSTS=meu-host.local:8000 \
MCP_EXTRA_ALLOWED_ORIGINS=http://meu-host.local:8000 \
docker compose up -d --force-recreate
docker compose logs pokemon-mcp-server | grep allowlist
```

Saída observada:

```
Host allowlist: 127.0.0.1:8000, localhost:8000, [::1]:8000, 127.0.0.1:8001, localhost:8001, [::1]:8001, meu-host.local:8000
Origin allowlist: http://127.0.0.1:8000, http://localhost:8000, http://[::1]:8000, http://127.0.0.1:8001, http://localhost:8001, http://[::1]:8001, http://meu-host.local:8000
```

Ou seja: mínimos obrigatórios + porta publicada (`MCP_HOST_PORT`) + extras do
usuário, nessa ordem e sem repetição. Com `MCP_HOST_PORT=8000` (o padrão) a
lista fica com apenas três entradas, porque as duas metades coincidem.

## Evidências MCP

Marque só o que você observou com os próprios olhos. Os itens abaixo foram
verificados pelo smoke test de 16/09/2026 (`SMOKE TEST OK`, código de saída 0,
33 verificações `[ok]` e nenhuma `[FALHA]`), que fala o protocolo MCP de
verdade contra o contêiner em execução e consulta a PokéAPI real:

- [x] MCP Client conectou
- [x] Tools foram descobertas
- [x] `get_pokemon("pikachu")` funcionou
- [x] `get_pokemon("25")` funcionou
- [x] `get_ability("static")` funcionou
- [x] `get_type("electric")` funcionou
- [x] Resource `pokemon://guide` foi lido
- [x] Prompt `compare_pokemon` foi obtido
- [x] erro de Pokémon inexistente foi tratado

### Em um cliente MCP de verdade

O smoke test usa o cliente do SDK oficial. Ele prova o protocolo, **não** prova
que a aplicação de IA que você usa vai conectar. Esta segunda checklist é para
preencher com o seu cliente (MCP Inspector, IDE, Codex local — veja
[conectar-cliente.md](conectar-cliente.md)):

| Evidência | Cliente usado | Data | Observação |
| --- | --- | --- | --- |
| Servidor cadastrado | | | |
| Servidor ativo/conectado na sessão | | | |
| Tools listadas pelo cliente | | | |
| Tool `get_pokemon` efetivamente chamada | | | a evidência é a chamada aparecer no cliente **e** a linha `consultando PokéAPI:` no log do servidor — não basta a resposta estar certa |
| Resource lido pelo cliente | | | nem todo cliente expõe Resources |
| Prompt obtido pelo cliente | | | nem todo cliente expõe Prompts |

## O que ainda não foi validado

Honestidade sobre os limites deste registro:

- **CI para esta rodada**: as alterações ainda não foram enviadas ao GitHub, e
  não existe run correspondente.
- **`uv run pytest -v` fora do Docker**: `uv` não está instalado na máquina que
  fez esta validação. A suíte rodou dentro do contêiner `tests`, que instala
  exatamente o `uv.lock` — é o mesmo conjunto de pacotes que a CI usa.
- **Clientes MCP reais**: a tabela acima está vazia. O smoke test não substitui
  essa evidência.
- **Outros sistemas operacionais**: só macOS/arm64 foi exercitado.
