# Conectar um cliente MCP

Este documento descreve como apontar um cliente MCP para o servidor deste
laboratório.

## O endpoint

| Item | Valor |
| --- | --- |
| URL | `http://localhost:8000/mcp` |
| Transporte | Streamable HTTP |
| Autenticação | nenhuma |
| Métodos usados pelo transporte | `POST` (mensagens), `GET` (fluxo servidor→cliente), `DELETE` (encerrar sessão em clientes legados) |

`http://127.0.0.1:8000/mcp` também funciona. Qualquer outro nome de host é
recusado com **HTTP 421** até entrar na allowlist: é a proteção contra DNS
rebinding do SDK, e ela deve continuar ligada.

Se você publicou o serviço em outra porta (`MCP_HOST_PORT` no Compose), troque
`8000` pela porta escolhida em todas as URLs desta página. O Compose já
acrescenta essa porta às allowlists de `Host` e `Origin`; a porta de dentro do
contêiner continua sendo 8000.

Para liberar **outro nome de host** (e não outra porta), use o `.env`:

```dotenv
MCP_EXTRA_ALLOWED_HOSTS=meu-host.local:8000
MCP_EXTRA_ALLOWED_ORIGINS=http://meu-host.local:8000
```

Esses valores são **somados** à allowlist: `localhost` e `127.0.0.1` continuam
valendo, e a proteção continua ligada. `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS`
não servem para isso quando você sobe pelo Compose — o `compose.yaml` monta as
duas a partir de `MCP_HOST_PORT` e ignora o que estiver no `.env`. A lista
final aparece no log de inicialização (`Host allowlist:` e `Origin allowlist:`).

O servidor precisa estar no ar antes de conectar:

```bash
docker compose up -d --build
docker compose ps           # STATUS deve ser "healthy"
```

## Antes de configurar qualquer cliente: confirme o protocolo

O jeito mais rápido de saber se o problema é o servidor ou o cliente é rodar o
smoke test, que fala MCP de verdade:

```bash
docker compose --profile test run --build --rm smoke
```

Se ele passa, os cenários exercitados funcionaram nesse ambiente: conexão,
negociação de protocolo, descoberta, as três Tools, o Resource e o Prompt. Isso
é uma evidência forte, mas não uma prova de que tudo funciona em qualquer
lugar. Uma falha em outro cliente ainda pode envolver transporte, versão do
protocolo, configuração, proxy ou comportamento específico daquela integração —
por isso vale olhar também os logs do servidor ao reproduzir o erro.

## Testar com o MCP Inspector

O [MCP Inspector](https://github.com/modelcontextprotocol/inspector) é a
ferramenta oficial para inspecionar um servidor MCP sem envolver nenhuma
aplicação de IA. Ele é uma aplicação Node.js e roda com `npx`.

1. Com o contêiner no ar, aponte o Inspector diretamente para o endpoint:

   ```bash
   npx @modelcontextprotocol/inspector --server-url http://localhost:8000/mcp --transport http
   ```

   `--server-url` é a URL do servidor e `--transport http` seleciona Streamable
   HTTP (a outra opção documentada é `sse`, que este laboratório não usa).

2. Abra no navegador a URL que o comando imprimir no terminal. A interface web
   também aceita os mesmos valores como parâmetros de consulta
   (`?serverUrl=http://localhost:8000/mcp&transport=http`), e é possível
   preencher a URL pela própria interface depois de abri-la.

3. Conecte e confira as abas:
   - **Tools** → listar as ferramentas mostra `get_pokemon`, `get_ability` e
     `get_type`, cada uma com o formulário gerado a partir do schema. Chame
     `get_pokemon` com `name_or_id = pikachu`.
   - **Resources** → listar mostra `pokemon://guide`. Abra para ler o Markdown.
   - **Prompts** → selecione `compare_pokemon`, preencha `pokemon_a` e
     `pokemon_b` e peça o Prompt: o Inspector devolve o template de mensagens,
     sem executar nada.

Referências: <https://github.com/modelcontextprotocol/inspector> e
`docs/mcp-server-configuration.md` do mesmo repositório (consultados em
16/09/2026). Os rótulos exatos dos botões e abas mudam entre versões do
Inspector; o que não muda é a sequência: conectar, listar, executar.

> O `npx` exige Node.js instalado. É o único passo deste laboratório que sai do
> Docker, e é opcional: as capacidades também são verificadas pelo smoke test.

## Exemplo de configuração em uma aplicação de IA compatível

O exemplo abaixo é o formato documentado pelo **VS Code** para servidores MCP,
escolhido aqui porque a documentação oficial publica o JSON exato para um
servidor HTTP. Referência:
<https://code.visualstudio.com/docs/copilot/customization/mcp-servers>
(consultada em 16/09/2026).

**Não altere sua configuração pessoal a partir deste arquivo.** O trecho existe
para ser lido e comparado. Se quiser usá-lo, edite o seu arquivo
conscientemente e faça uma cópia de segurança antes.

Arquivo `.vscode/mcp.json`, dentro do projeto onde você quer usar o servidor:

```json
{
  "servers": {
    "pokemon": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

A chave de topo é `servers`, `type` identifica o transporte HTTP e `url` aponta
para o endpoint. O mesmo arquivo pode ser criado no perfil do usuário pelo
comando **MCP: Open User Configuration**.

Avisos importantes e honestos sobre este trecho:

- **Cada aplicação tem o seu próprio formato.** O JSON acima vale para o VS
  Code. Outras aplicações usam arquivos, chaves e comandos diferentes; consulte
  a documentação oficial da que você usa e não adapte este trecho no escuro.
- **Nem toda aplicação aceita Streamable HTTP.** Várias só lançam servidores
  locais por stdio, e um cliente que só fala stdio não conecta aqui sem um
  adaptador. Por exemplo, a documentação da Claude Desktop para servidores
  locais (<https://modelcontextprotocol.io/docs/develop/connect-local-servers>,
  consultada em 16/09/2026) descreve apenas entradas com `command` e `args`,
  isto é, stdio; para servidores acessíveis por URL, ela orienta a usar os
  *Custom Connectors* pela interface
  (<https://modelcontextprotocol.io/docs/develop/connect-remote-servers>),
  fluxo pensado para servidores publicados na internet — veja a seção seguinte
  sobre por que `localhost` não serve nesse caso.
- **Nem toda aplicação expõe Resources e Prompts.** Muitos clientes consomem
  apenas Tools. O servidor continua anunciando as três capacidades; quem decide
  usá-las é o cliente. Por isso o MCP Inspector é o melhor lugar para capturar
  as evidências de Resource e Prompt.
- **Este servidor não usa autenticação.** Se a sua aplicação exigir token ou
  OAuth para conectores, ela não vai conseguir conectar sem configuração
  adicional, que está fora do escopo deste laboratório.

## Codex local

Esta seção existe só como exemplo de verificação num cliente de terminal que
roda **na sua máquina**. O laboratório não depende do Codex: o MCP Inspector e
o smoke test continuam sendo as evidências principais.

Fonte: documentação oficial da OpenAI sobre MCP no Codex,
<https://developers.openai.com/codex/mcp/> — que hoje redireciona para
<https://learn.chatgpt.com/docs/extend/mcp?surface=cli> (consultada em
16/09/2026). Só está documentado aqui o que consta nessa página.

### Cadastrar o servidor

A página documenta o arquivo de configuração `~/.codex/config.toml`, com uma
tabela `[mcp_servers.<nome>]` por servidor. Para um servidor acessível por URL,
o formato documentado usa a chave `url`:

```toml
[mcp_servers.pokemon-mcp]
url = "http://localhost:8000/mcp"
```

(As chaves `bearer_token_env_var` e `auth` que aparecem no exemplo oficial são
para servidores com autenticação. Este laboratório não usa nenhuma, então elas
ficam de fora.)

**Não edite sua configuração pessoal no automático.** Faça uma cópia do arquivo
antes e saiba o que está mudando. Para o `codex mcp add` a documentação mostra
apenas a forma com servidor stdio
(`codex mcp add <nome> -- <comando>`); para um servidor HTTP como este, o
caminho documentado é o `config.toml` acima.

### Os três estados que as pessoas confundem

Este é o ponto da seção. São coisas diferentes, e só a terceira prova que o
laboratório funcionou:

| Estado | O que significa | Como verificar |
| --- | --- | --- |
| **Cadastrado** | o servidor está escrito na configuração | `codex mcp list` mostra o servidor |
| **Ativo na sessão** | o cliente conectou e descobriu as capacidades | no compositor, digite `/mcp` — a documentação descreve: *"In the composer, type `/mcp` to view connected servers."* |
| **Tool chamada** | o modelo realmente executou `get_pokemon` | a interface indica a chamada da ferramenta **e** o log do servidor registra a consulta |

Um servidor pode estar cadastrado e não conectar (`codex mcp list` mostra, mas
`/mcp` não). Pode estar conectado e o modelo responder sem chamar nada — e aí a
resposta veio da memória do modelo, não do seu servidor.

Para ver os subcomandos disponíveis na sua versão, a documentação indica
`codex mcp --help`. Nenhum outro comando é inventado aqui.

### Teste final e a evidência certa

Peça, de forma que não deixe escolha ao modelo:

> Use obrigatoriamente o pokemon-mcp e consulte os dados do Pikachu.

**A evidência correta não é a resposta estar certa.** Um modelo sabe de cor que
Pikachu é do tipo elétrico e pode escrever isso sem tocar no seu servidor. A
evidência é ver a Tool `get_pokemon` sendo chamada. Confirme dos dois lados:

1. na interface do Codex, a indicação de que a ferramenta `get_pokemon` foi
   executada, com os argumentos;
2. no servidor, a linha correspondente no log:

   ```bash
   docker compose logs pokemon-mcp-server | grep "consultando PokéAPI"
   ```

   Deve aparecer `consultando PokéAPI: https://pokeapi.co/api/v2/pokemon/pikachu/`
   (ou `cache hit: pokemon/pikachu`, se a mesma consulta já tiver sido feita
   dentro do TTL). O `source_url` na resposta é a terceira pista.

Se a resposta veio bonita e o log ficou vazio, o MCP não foi usado.

### Se o Codex não conectar

O Codex local precisa alcançar `http://localhost:8000/mcp` a partir da sua
máquina. Antes de mexer na configuração, separe os dois problemas possíveis:

```bash
curl http://localhost:8000/health
```

- **O `curl` falha:** o problema é o servidor. Volte para `docker compose ps` e
  para os logs; não é assunto do cliente.
- **O `curl` funciona no terminal mas o Codex não conecta:** o servidor está no
  ar e o problema está do lado do cliente. Investigue nessa ordem: a sandbox e
  as permissões de rede do Codex (um agente em sandbox pode não ter acesso à
  rede local), o caminho e a sintaxe do `config.toml`, se a sessão foi
  reiniciada depois de editar o arquivo, e o `startup_timeout_sec` documentado
  para servidores que demoram a subir. Olhe também o log do servidor ao
  reproduzir: **HTTP 421** aponta `Host` fora da allowlist e **HTTP 403**,
  `Origin` fora da allowlist. Log vazio significa que a requisição nunca
  chegou.

E o de sempre: **um cliente remoto ou na nuvem não alcança o seu `localhost`**,
por mais correta que a configuração esteja. Se a sua sessão do Codex roda em
servidor do fornecedor e não na sua máquina, não há configuração que resolva —
veja a seção a seguir.

## Aplicações hospedadas na nuvem não alcançam o seu localhost

Um ponto que costuma gerar confusão na hora da demonstração:

> `localhost` significa "esta máquina". Para um serviço que roda nos servidores
> de um fornecedor, `localhost` é o servidor **dele**, não o seu computador.

Portanto:

- Uma aplicação de IA que roda **na sua máquina** (aplicativo de desktop, IDE,
  terminal) alcança `http://localhost:8000/mcp` normalmente.
- Uma aplicação que roda **no navegador contra um serviço em nuvem** não
  alcança. Não existe configuração mágica: o pacote precisaria sair da internet
  e entrar na sua máquina.
- Expor o laboratório com um túnel público para contornar isso é justamente o
  que **não** se deve fazer aqui: o servidor não tem autenticação e o Compose o
  publica apenas em `127.0.0.1` de propósito.

Para a apresentação, use um cliente local (MCP Inspector ou uma aplicação de
desktop) e capture os prints de lá.

## Diagnóstico rápido

| Sintoma no cliente | O que olhar no servidor | Correção |
| --- | --- | --- |
| Erro genérico de transporte ao conectar | `docker compose logs pokemon-mcp-server` mostra `Invalid Host header` | O `Host` não está na allowlist. Use `localhost` ou `127.0.0.1`, ou acrescente o nome em `MCP_EXTRA_ALLOWED_HOSTS`. |
| `403 Forbidden` | log mostra `Invalid Origin header` | Acrescente a origem exata a `MCP_EXTRA_ALLOWED_ORIGINS` no `.env`. |
| Cadastrado no cliente, mas a Tool nunca é chamada | o log não mostra `consultando PokéAPI:` | Cadastrado ≠ ativo ≠ chamado. Veja [Codex local](#codex-local). |
| Conecta, mas não lista ferramentas | as ferramentas aparecem no smoke test | O cliente provavelmente não requisitou `tools/list`; confira a tela de servidores MCP da aplicação. |
| Conexão recusada | `docker compose ps` não mostra o contêiner | Suba o serviço com `docker compose up -d`. |
