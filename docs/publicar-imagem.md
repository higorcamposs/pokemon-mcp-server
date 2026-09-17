# Publicar a imagem (GHCR e Docker Hub)

Procedimento de manutenção para lançar uma versão nova da imagem nos dois
registries em que ela é distribuída:

| Registry | Nome da imagem |
| --- | --- |
| GHCR | `ghcr.io/higorcamposs/pokemon-mcp-server` |
| Docker Hub | `higorcamposs/pokemon-mcp-server` (= `docker.io/higorcamposs/pokemon-mcp-server`) |

**São duas distribuições de uma imagem só**, não duas imagens. O Buildx
constrói **um** índice multiarch e o mesmo push o envia para os dois destinos,
com o mesmo digest, as mesmas camadas e os mesmos metadados OCI.

O fluxo é automatizado por
[`.github/workflows/publish-image.yml`](../.github/workflows/publish-image.yml),
disparado por **release publicada**. Não existe publicação manual a partir da
máquina de ninguém: é o Actions que constrói e envia.

## Credenciais

| Registry | Credencial | Onde fica |
| --- | --- | --- |
| GHCR | `GITHUB_TOKEN` do próprio Actions | automático; `packages: write` só no job que publica |
| Docker Hub | variable `DOCKERHUB_USERNAME` + secret `DOCKERHUB_TOKEN` | **Settings → Secrets and variables → Actions** |

O `DOCKERHUB_TOKEN` é um *Personal Access Token* do Docker Hub com permissão de
leitura **e** escrita. Ele vive apenas no cofre de secrets do repositório: não
aparece no código, no README, em arquivo local nem nos logs — o workflow testa
só a **presença** dele, nunca imprime o valor, e o Actions mascara secrets na
saída.

Se a variable ou o secret faltarem, a release **ainda sai no GHCR** e o job
emite um `::warning::` dizendo que o Docker Hub ficou de fora. O GHCR nunca
depende do Docker Hub para funcionar. Para levar essa versão ao Docker Hub
depois, use a [promoção](#promover-uma-versão-já-publicada-para-o-docker-hub) —
sem reconstruir.

## O que o workflow faz, em ordem

| Etapa | Job | O que garante |
| --- | --- | --- |
| Checkout da tag da release | `validate` | o que é publicado é o commit da tag, não o topo da branch |
| Conferência da versão | `validate` | a tag, o `pyproject.toml`, o `__init__.py` e a versão anunciada pelo servidor batem |
| `uv sync --locked` + `pytest` | `validate` | a suíte passa com o lockfile **daquele commit** |
| `docker build --target runtime` | `validate` | a imagem de execução constrói |
| Subir o contêiner e checar `/health` e o usuário | `validate` | ela inicia, fica `healthy` e roda sem ser root |
| `needs: validate` | `publish` | nada é publicado antes de tudo acima passar |
| Login no GHCR e no Docker Hub | `publish` | os dois destinos autenticados antes de qualquer escrita |
| Recusa de tag já existente | `publish` | uma versão publicada nunca é regravada — conferido em **cada** registry |
| Build multiarch e push | `publish` | **um** build, `linux/amd64` + `linux/arm64`, estágio `runtime`, enviado aos dois registries |
| Leitura de volta do que foi publicado | `publish` | cada registry serve as duas arquiteturas e o **mesmo digest** do índice construído |
| Resumo da execução | `publish` | tags, revisão, arquiteturas, registries e digest ficam registrados |

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
gh release create v0.1.2 \
  --target <sha-do-commit> \
  --title "v0.1.2" \
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

### 6. Conferir a visibilidade nos dois registries

**Repositório público não implica pacote público.** No GHCR, um pacote
recém-criado nasce **privado**.

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

No Docker Hub, o repositório é criado pelo primeiro push e herda a privacidade
padrão da conta. Confira em <https://hub.docker.com/r/higorcamposs/pokemon-mcp-server>
→ **Settings**, ou pela API pública, que só responde para repositório público:

```bash
curl -s https://hub.docker.com/v2/repositories/higorcamposs/pokemon-mcp-server/ \
  | python3 -c 'import sys,json; print("privado:", json.load(sys.stdin)["is_private"])'
```

### 7. Provar que o download anônimo funciona

Não basta o pacote *parecer* público. Teste **sem credenciais**, usando um
diretório de configuração temporário do Docker — assim o seu login pessoal não
é apagado e o contexto do Docker Desktop não muda:

```bash
TMPCFG="$(mktemp -d)"
for ref in ghcr.io/higorcamposs/pokemon-mcp-server:0.1.2 \
           higorcamposs/pokemon-mcp-server:0.1.2; do
  docker --config "$TMPCFG" manifest inspect "$ref" | grep -E '"architecture"|"os"'
done
rm -rf "$TMPCFG"
```

Nunca use `docker logout` global só para este teste.

> Num Docker Desktop, um `pull` com `--config` temporário pode não achar o
> daemon, porque o contexto também mora na configuração. Se acontecer, aponte o
> socket na mão: `DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"`.

### 8. Validar o artefato realmente publicado

Valide a imagem **baixada do registry**, não a que ficou no cache do build
local. O digest é o mesmo nos dois, então validar um dos dois e conferir a
igualdade dos digests basta:

```bash
docker buildx imagetools inspect ghcr.io/higorcamposs/pokemon-mcp-server:0.1.2 \
  --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect higorcamposs/pokemon-mcp-server:0.1.2 \
  --format '{{.Manifest.Digest}}'
```

Use nome de contêiner e porta que não colidam com o laboratório em execução, e
passe os extras de allowlist correspondentes à porta escolhida:

```bash
docker run -d --name pmcp-verify -p 127.0.0.1:8010:8000 \
  -e MCP_EXTRA_ALLOWED_HOSTS=localhost:8010,127.0.0.1:8010 \
  -e MCP_EXTRA_ALLOWED_ORIGINS=http://localhost:8010,http://127.0.0.1:8010 \
  ghcr.io/higorcamposs/pokemon-mcp-server:0.1.2

curl http://localhost:8010/health
docker inspect pmcp-verify --format '{{.State.Health.Status}}'
docker exec pmcp-verify id -un          # precisa ser "pokemon", não root
docker image inspect ghcr.io/higorcamposs/pokemon-mcp-server:0.1.2 \
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

## Promover uma versão já publicada para o Docker Hub

Workflow: [`.github/workflows/promote-image.yml`](../.github/workflows/promote-image.yml)
(nome `promote image`), disparado à mão em **Actions → promote image → Run
workflow**, informando a versão (sem o `v`) e se o `latest` deve acompanhar.

Ele **não constrói nada**. `docker buildx imagetools create` copia o índice
multiarch e os blobs do GHCR para o Docker Hub: mesmo digest, mesmas camadas,
mesmos labels e anotações. Um rebuild a partir do código atual poderia produzir
bytes diferentes — por isso ele não acontece aqui.

Serve para dois casos:

1. **versões anteriores ao Docker Hub** (a `0.1.2` chegou lá assim);
2. **recuperação**: se um push falhar só na metade do Docker Hub, refazer a
   release é impossível — a tag do GHCR já existe e não se regrava. Promover o
   índice que ficou publicado é o caminho correto.

Ele confere, antes de escrever, que a origem existe e traz `linux/amd64` e
`linux/arm64`; recusa regravar uma tag de versão do Docker Hub que aponte para
outro digest (repetir a mesma promoção é inofensivo e passa); recusa mover o
`latest` para uma prerelease; e, depois de escrever, relê o Docker Hub exigindo
as duas arquiteturas e o digest idêntico ao da origem.

O equivalente manual, quando você tem `docker login` no Docker Hub:

```bash
digest="$(docker buildx imagetools inspect \
  ghcr.io/higorcamposs/pokemon-mcp-server:0.1.2 --format '{{.Manifest.Digest}}')"

docker buildx imagetools create \
  --tag docker.io/higorcamposs/pokemon-mcp-server:0.1.2 \
  --tag docker.io/higorcamposs/pokemon-mcp-server:latest \
  "ghcr.io/higorcamposs/pokemon-mcp-server@${digest}"
```

Prefira o workflow: ele faz as conferências acima, que o comando solto não faz.

## Regras que não mudam

- **Tag de versão não se regrava, em nenhum dos dois registries.** Quem baixou
  `:0.1.2` ontem precisa receber os mesmos bytes hoje. O workflow recusa
  publicar sobre uma versão existente em qualquer um dos destinos.
- **Uma imagem, dois registries.** Nunca construa uma imagem separada para o
  Docker Hub: o digest tem de ser o mesmo. Para levar algo já publicado, copie
  o índice (promoção), não reconstrua.
- **`latest` é ponteiro móvel**, e só aponta para a versão estável mais nova.
  Nunca para prerelease, nunca para uma versão antiga publicada depois.
- **Só o `runtime` é publicado.** O estágio `dev` carrega `pytest` e a suíte;
  ele existe para testar, não para distribuir.
- **Nenhum token em arquivo.** O `GITHUB_TOKEN` do Actions cobre o GHCR, com
  `packages: write` apenas no job que publica. O Docker Hub usa o secret
  `DOCKERHUB_TOKEN`, que fica no cofre do repositório e nunca é commitado,
  impresso ou escrito em disco.
- **Publicar a imagem não publica o endpoint.** O servidor continua local.
