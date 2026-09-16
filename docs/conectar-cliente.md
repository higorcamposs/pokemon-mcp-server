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
recusado com **HTTP 421** até ser acrescentado a `MCP_ALLOWED_HOSTS`: é a
proteção contra DNS rebinding do SDK, e ela deve continuar ligada.

O servidor precisa estar no ar antes de conectar:

```bash
docker compose up -d --build
docker compose ps           # STATUS deve ser "healthy"
```

## Antes de configurar qualquer cliente: confirme o protocolo

O jeito mais rápido de saber se o problema é o servidor ou o cliente é rodar o
smoke test, que fala MCP de verdade:

```bash
docker compose --profile test run --rm smoke
```

Se ele passa, o servidor está correto e qualquer falha seguinte é de
configuração do cliente.

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
| Erro genérico de transporte ao conectar | `docker compose logs pokemon-mcp-server` mostra `Invalid Host header` | O `Host` não está em `MCP_ALLOWED_HOSTS`. Use `localhost` ou `127.0.0.1`. |
| `403 Forbidden` | log mostra `Invalid Origin header` | Acrescente a origem exata a `MCP_ALLOWED_ORIGINS`. |
| Conecta, mas não lista ferramentas | as ferramentas aparecem no smoke test | O cliente provavelmente não requisitou `tools/list`; confira a tela de servidores MCP da aplicação. |
| Conexão recusada | `docker compose ps` não mostra o contêiner | Suba o serviço com `docker compose up -d`. |
