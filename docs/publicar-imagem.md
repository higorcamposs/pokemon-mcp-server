# Publicar a imagem no GHCR

Procedimento de manutenção para lançar uma versão nova da imagem em
`ghcr.io/higorcamposs/pokemon-mcp-server`.

O fluxo é automatizado por
[`.github/workflows/publish-image.yml`](../.github/workflows/publish-image.yml),
disparado por **release publicada**. Não existe publicação manual a partir da
máquina de ninguém: é o Actions que constrói e envia, com o `GITHUB_TOKEN`.

## O que o workflow faz, em ordem

| Etapa | Job | O que garante |
| --- | --- | --- |
| Checkout da tag da release | `validate` | o que é publicado é o commit da tag, não o topo da branch |
| Conferência da versão | `validate` | a tag, o `pyproject.toml`, o `__init__.py` e a versão anunciada pelo servidor batem |
| `uv sync --locked` + `pytest` | `validate` | a suíte passa com o lockfile **daquele commit** |
| `docker build --target runtime` | `validate` | a imagem de execução constrói |
| Subir o contêiner e checar `/health` e o usuário | `validate` | ela inicia, fica `healthy` e roda sem ser root |
| `needs: validate` | `publish` | nada é publicado antes de tudo acima passar |
| Recusa de tag já existente | `publish` | uma versão publicada nunca é regravada |
| Build multiarch e push | `publish` | `linux/amd64` + `linux/arm64`, estágio `runtime` |
| Resumo da execução | `publish` | tags, revisão, arquiteturas e digest ficam registrados |

A CI verde de um commit anterior **não** vale como aprovação: a validação roda
no mesmo fluxo, sobre o commit que será publicado.

## Lançar uma versão

### 1. Escolher e alinhar a versão

Quatro lugares precisam concordar, ou o job `validate` falha de propósito:

| Onde | Campo | Conferido pelo workflow? |
| --- | --- | --- |
| `pyproject.toml` | `version = "X.Y.Z"` | sim |
| `src/pokemon_mcp/__init__.py` | `__version__ = "X.Y.Z"` | sim |
| `src/pokemon_mcp/server.py` | `version="X.Y.Z"` no `MCPServer(...)` | sim |
| tag Git / release | `vX.Y.Z` | é a referência |

Vale alinhar também, embora o workflow não barre por eles: o `user_agent` em
`src/pokemon_mcp/pokeapi.py`, as tags locais do `compose.yaml` e a tag padrão
do `compose.ghcr.yaml`.

Ao mudar a versão, atualize o lockfile do próprio projeto:

```bash
uv lock          # ou: docker compose --profile test run --build --rm tests
```

Atualize **apenas** o que a mudança de versão exige. Não aproveite a viagem
para subir outras dependências.

### 2. Validar localmente antes de lançar

```bash
docker compose config -q
docker compose --profile test run --build --rm tests
docker compose up -d --build
docker compose --profile test run --build --rm smoke
docker compose logs pokemon-mcp-server
```

### 3. Enviar o commit e conferir a CI

```bash
git push origin main
```

Confira o workflow `tests` do commit exato que vai ser lançado, na aba
**Actions** do repositório.

### 4. Criar a release

A release é o gatilho. Aponte-a para o commit conferido no passo anterior:

```bash
gh release create v0.1.1 \
  --target <sha-do-commit> \
  --title "v0.1.1" \
  --notes "Descreva o que mudou nesta versão."
```

Sem o `gh` autenticado, use **Releases → Draft a new release** na interface do
GitHub, criando a tag `vX.Y.Z` a partir daquele commit.

Para uma versão de teste, marque-a como **prerelease**: o workflow publica a
tag de versão, mas **não** move o `latest`.

### 5. Acompanhar a publicação

Na aba **Actions**, abra a execução de `publish image`. Ao final, o resumo traz
as tags, a revisão, as arquiteturas e o **digest do índice multiarch** —
guarde o digest, é ele que identifica os bytes exatos.

### 6. Conferir a visibilidade do pacote

**Repositório público não implica pacote público.** Um pacote recém-criado
nasce **privado**.

Na primeira publicação, torne-o público pela interface (não existe API oficial
para isso):

1. abra <https://github.com/higorcamposs?tab=packages>;
2. escolha `pokemon-mcp-server`;
3. **Package settings**;
4. em **Danger Zone**, **Change visibility** → **Public**.

Confirme também, em **Manage Actions access**, que o repositório
`pokemon-mcp-server` aparece com permissão de escrita — é o que permite ao
workflow publicar nas próximas versões.

Depois da primeira vez, as publicações seguintes herdam a visibilidade.

### 7. Provar que o download anônimo funciona

Não basta o pacote *parecer* público. Teste **sem credenciais**, usando um
diretório de configuração temporário do Docker — assim o seu login pessoal não
é apagado e o contexto do Docker Desktop não muda:

```bash
TMPCFG="$(mktemp -d)"
docker --config "$TMPCFG" pull ghcr.io/higorcamposs/pokemon-mcp-server:0.1.1
docker --config "$TMPCFG" manifest inspect ghcr.io/higorcamposs/pokemon-mcp-server:0.1.1 \
  | grep -E '"architecture"|"os"'
rm -rf "$TMPCFG"
```

Nunca use `docker logout` global só para este teste.

### 8. Validar o artefato realmente publicado

Valide a imagem **baixada do GHCR**, não a que ficou no cache do build local.
Use nome de contêiner e porta que não colidam com o laboratório em execução, e
passe os extras de allowlist correspondentes à porta escolhida:

```bash
docker run -d --name pmcp-verify -p 127.0.0.1:8010:8000 \
  -e MCP_EXTRA_ALLOWED_HOSTS=localhost:8010,127.0.0.1:8010 \
  -e MCP_EXTRA_ALLOWED_ORIGINS=http://localhost:8010,http://127.0.0.1:8010 \
  ghcr.io/higorcamposs/pokemon-mcp-server:0.1.1

curl http://localhost:8010/health
docker inspect pmcp-verify --format '{{.State.Health.Status}}'
docker exec pmcp-verify id -un          # precisa ser "pokemon", não root
docker image inspect ghcr.io/higorcamposs/pokemon-mcp-server:0.1.1 \
  --format '{{json .Config.Labels}}'
```

Depois rode o smoke test do commit da release contra esse servidor. O cliente
roda em separado — `uv` e `pytest` não existem dentro do runtime, e não
deveriam:

```bash
docker compose --profile test run --build --rm \
  --entrypoint sh smoke -c \
  "uv run --no-sync python scripts/smoke_test.py http://host.docker.internal:8010/mcp"
```

Anote a **versão do protocolo MCP negociada** que o smoke imprime.

Ao terminar, remova só o que você criou:

```bash
docker rm -f pmcp-verify
```

### 9. Registrar as evidências

Atualize [validacao.md](validacao.md) com: release/tag, commit testado, link da
execução do workflow, imagem, digest, arquiteturas construídas, arquiteturas
efetivamente **testadas** e resultados observados.

Construir um manifesto multiarch **não** é testar as duas arquiteturas. Diga
qual método foi usado em cada uma (execução nativa ou emulação) e não marque
uma arquitetura como testada só porque ela aparece no manifesto.

Se precisar corrigir a documentação depois da publicação, **não** regrave a
tag. Use as notas da release ou um commit novo de documentação.

## Regras que não mudam

- **Tag de versão não se regrava.** Quem baixou `:0.1.1` ontem precisa receber
  os mesmos bytes hoje. O workflow recusa publicar sobre uma versão existente.
- **`latest` é ponteiro móvel**, e só aponta para a versão estável mais nova.
  Nunca para prerelease, nunca para uma versão antiga publicada depois.
- **Só o `runtime` é publicado.** O estágio `dev` carrega `pytest` e a suíte;
  ele existe para testar, não para distribuir.
- **Nenhum token pessoal no repositório.** O `GITHUB_TOKEN` do Actions basta, e
  `packages: write` existe apenas no job que publica.
- **Publicar a imagem não publica o endpoint.** O servidor continua local.
