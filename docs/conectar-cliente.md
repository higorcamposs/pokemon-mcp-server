# Conectar um cliente MCP

Este guia mostra como conectar o MCP Inspector, o VS Code e o Codex ao servidor
local. Para entender o que acontece depois da conexão, leia
[Como o Pokémon MCP Server funciona](como-funciona.md).

## Endpoint e requisitos

| Item | Valor |
| --- | --- |
| URL | `http://localhost:8000/mcp` |
| Transporte | Streamable HTTP |
| Autenticação | nenhuma |
| Acesso padrão | somente a máquina local |

`http://127.0.0.1:8000/mcp` também funciona. Se você definiu
`MCP_HOST_PORT`, substitua `8000` pela porta publicada.

Antes de configurar qualquer cliente, confirme:

- [ ] o contêiner está em execução;
- [ ] `docker ps` mostra o estado `healthy`;
- [ ] `curl http://localhost:8000/health` devolve `{"status":"ok",...}`;
- [ ] o cliente roda na mesma máquina que o servidor;
- [ ] o cliente oferece transporte Streamable HTTP.

Suba o servidor a partir do repositório com:

```bash
docker compose up -d --build
docker compose ps
```

Ou siga o [Quickstart sem clone](../README.md#quickstart-em-cinco-minutos).

## MCP Inspector

O MCP Inspector é a opção mais direta para verificar o protocolo sem envolver
um modelo de IA. Ele mostra as capacidades e permite executá-las manualmente.

### Configurar o Inspector

Pré-requisito adicional: Node.js com `npx`.

Com o servidor no ar:

```bash
npx @modelcontextprotocol/inspector \
  --server-url http://localhost:8000/mcp \
  --transport http
```

Abra no navegador a URL impressa no terminal. Os nomes exatos dos botões podem
mudar entre versões, mas o fluxo continua sendo conectar, listar e executar.

### Testar no Inspector

1. Abra **Tools** e confirme `get_pokemon`, `get_ability` e `get_type`.
2. Selecione `get_pokemon`.
3. Preencha `name_or_id` com `pikachu`.
4. Execute a Tool.
5. Abra **Resources** e leia `pokemon://guide`.
6. Abra **Prompts**, selecione `compare_pokemon` e informe `pikachu` e
   `bulbasaur`.

### Confirmar o Inspector

A execução de `get_pokemon` deve devolver `structured_content` com `id: 25`,
`types: ["electric"]` e um `source_url` da PokéAPI. O Resource deve abrir como
Markdown. O Prompt deve devolver um template, sem produzir a comparação final.

Referência: [repositório oficial do MCP Inspector](https://github.com/modelcontextprotocol/inspector).

## VS Code

O VS Code aceita servidores MCP por Streamable HTTP em um arquivo `mcp.json`.

### Configurar o VS Code

Crie `.vscode/mcp.json` no projeto em que deseja usar o servidor:

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

Também é possível abrir a configuração do perfil pelo comando
**MCP: Open User Configuration**. Use a configuração de projeto quando o
servidor fizer sentido apenas naquele repositório; use a de usuário quando
quiser disponibilizá-lo em vários projetos.

### Testar no VS Code

1. Abra a lista de servidores MCP do VS Code.
2. Confirme que `pokemon` está conectado e lista as três Tools.
3. Em uma conversa compatível, peça:

   > Use a ferramenta do servidor pokemon e consulte os dados do Pikachu.

### Confirmar o VS Code

A interface deve indicar uma chamada a `get_pokemon`, e os logs do contêiner
devem mostrar a consulta ou o cache:

```bash
docker compose logs pokemon-mcp-server | grep -E "consultando PokéAPI|cache hit"
```

Referência: [documentação oficial do VS Code para servidores MCP](https://code.visualstudio.com/docs/copilot/customization/mcp-servers).

## Codex

O app desktop do ChatGPT, o Codex CLI e a extensão IDE compartilham a
configuração MCP do mesmo Host Codex. O arquivo padrão do usuário é
`~/.codex/config.toml`; projetos confiáveis também podem ter
`.codex/config.toml`.

### Configurar o Codex

Adicione ao `config.toml` escolhido:

```toml
[mcp_servers.pokemon-mcp]
url = "http://localhost:8000/mcp"
```

O servidor não usa OAuth nem bearer token, portanto não precisa de campos de
autenticação. Reinicie o cliente depois de salvar a configuração.

No app desktop ou na extensão IDE, também é possível abrir a tela de servidores
MCP, escolher **Streamable HTTP** e informar a mesma URL.

### Testar no Codex

No Codex CLI, confira o cadastro com:

```bash
codex mcp list
```

Na interface interativa, use `/mcp` para ver os servidores ativos. Depois peça:

> Use obrigatoriamente o pokemon-mcp e consulte os dados do Pikachu.

### Confirmar o Codex

Existem três estados diferentes:

- **Cadastrado:** `codex mcp list` mostra a entrada da configuração.
- **Conectado:** `/mcp` mostra que o cliente descobriu as capacidades.
- **Tool executada:** a interface mostra `get_pokemon` e o log registra a
  consulta.

Uma resposta correta sobre Pikachu não basta como prova: o modelo pode conhecer
o assunto sem usar o servidor. Confirme a chamada na interface e nos logs.

Referência: [documentação oficial da OpenAI sobre MCP no Codex](https://learn.chatgpt.com/docs/extend/mcp).

## Confirmar o protocolo sem depender do cliente

Se você clonou o repositório, execute o smoke test:

```bash
docker compose --profile test run --build --rm smoke
```

Ele conecta pelo endpoint HTTP, negocia o protocolo, descobre as capacidades,
chama as três Tools, lê o Resource e obtém o Prompt. Uma execução bem-sucedida
termina com `SMOKE TEST OK`.

Se o smoke passa e outro cliente falha, concentre o diagnóstico na
configuração, versão, transporte ou permissões de rede desse cliente.

## Compatibilidade e alcance

### O cliente precisa falar Streamable HTTP

Nem todo cliente MCP oferece todos os transportes. Um cliente que aceita apenas
servidores locais por `command` e `args` usa stdio e não conecta diretamente a
este projeto.

Nem todo cliente exibe Resources e Prompts. É comum uma aplicação consumir
somente Tools; isso não significa que o servidor deixou de anunciar as outras
capacidades. Use o Inspector ou o smoke test para verificar o conjunto completo.

### `localhost` depende de onde o cliente roda

`localhost` significa “esta máquina”. Portanto:

- um cliente desktop, IDE ou terminal na sua máquina alcança o servidor;
- uma aplicação executada em contêiner precisa de uma rota até o Host;
- um serviço hospedado na nuvem não alcança o seu `localhost`.

Publicar a imagem num registry (GHCR ou Docker Hub) não muda isso. A imagem é
um programa para download, não um servidor hospedado. Não abra um túnel público
para este laboratório: ele não possui autenticação.

## Host, Origin e porta

O SDK valida os cabeçalhos `Host` e `Origin` para proteger o servidor local
contra DNS rebinding:

- Host fora da lista recebe HTTP 421;
- Origin fora da lista recebe HTTP 403;
- ausência de Origin é aceita para clientes que não são navegadores.

### Mudar somente a porta

Com Compose:

```bash
MCP_HOST_PORT=8001 docker compose up -d --build
```

O endpoint vira `http://localhost:8001/mcp`. O Compose acrescenta a porta às
allowlists automaticamente; a porta interna do contêiner continua sendo 8000.

### Permitir outro nome de Host

No `.env`:

```dotenv
MCP_EXTRA_ALLOWED_HOSTS=meu-host.local:8000
MCP_EXTRA_ALLOWED_ORIGINS=http://meu-host.local:8000
```

Esses valores são somados aos mínimos obrigatórios. Eles não removem
`localhost` e `127.0.0.1`, nem desligam a proteção. Veja a lista final nos logs:

```bash
docker compose logs pokemon-mcp-server | grep allowlist
```

Não desligue a proteção para corrigir um erro de conexão. Autorize apenas o
Host e a Origin exatos que o cliente realmente utiliza.

## Diagnóstico

- **Conexão recusada:** inicie o servidor e aguarde o estado `healthy`.
- **`/health` funciona, mas MCP não:** execute o smoke test e revise o
  transporte configurado no cliente.
- **HTTP 421:** use `localhost` ou autorize o Host exato mostrado no log.
- **HTTP 403:** autorize a Origin completa, incluindo esquema e porta.
- **Servidor cadastrado, mas ausente:** reinicie o cliente e confira a URL.
- **Tools não aparecem:** confirme com o smoke; o cliente pode não consumir
  Tools ou MCP.
- **Tool não é chamada:** peça explicitamente o uso do servidor e confira os
  logs.
- **Erro de PokéAPI:** confira a internet do contêiner e tente novamente.

Comandos úteis:

```bash
docker compose ps
curl http://localhost:8000/health
docker compose logs -f pokemon-mcp-server
docker compose --profile test run --build --rm smoke
```

## Próximos passos

- [Entender o fluxo completo](como-funciona.md)
- [Voltar ao README](../README.md)
- [Consultar as versões e referências](versoes-e-referencias.md)
