# Roteiro de prints para o KS

Guia para capturar as evidências da parte prática do compartilhamento
**"O que é e como criar um MCP Server?"**. Não haverá desenvolvimento ao vivo:
cada print substitui uma demonstração.

Salve as imagens em `assets/screenshots/` com os nomes sugeridos.

**Antes de começar**, deixe o ambiente pronto e limpo:

```bash
docker compose down
docker compose up -d --build
docker compose ps
```

Regras para não estragar as evidências:

- Capture telas reais. Não monte prints em editor de imagem nem reescreva logs.
- Aumente a fonte do terminal antes de capturar: o slide será projetado.
- Se algo não puder ser capturado (por exemplo, um cliente que você não usa),
  deixe o print de fora e diga isso na apresentação, em vez de simular.

---

## 1. Estrutura do projeto

**Arquivo sugerido:** `01-estrutura-projeto.png`

**O que capturar:** a árvore de arquivos, seja no explorador do editor, seja no
terminal:

```bash
find . -not -path './.git/*' -not -path './.venv/*' -not -name '.DS_Store' | sort
```

Deixe visíveis: `src/pokemon_mcp/`, `tests/`, `scripts/smoke_test.py`,
`Dockerfile`, `compose.yaml`, `pyproject.toml`, `uv.lock`.

**Conceito demonstrado:** um MCP Server é um projeto pequeno e comum. Não é uma
plataforma: são quatro módulos Python, um Dockerfile e um Compose.

---

## 2. Trecho que registra uma Tool

**Arquivo sugerido:** `02-registro-tool.png`

**O que capturar:** no editor, o bloco de `src/pokemon_mcp/server.py` que
começa em `@mcp.tool(` e termina no `raise _to_tool_error(exc)` de
`get_pokemon`. Inclua o decorador, a assinatura tipada e a docstring.

Se couber, capture junto a definição de `NameOrId` (o `Annotated[str, Field(...)]`),
logo acima no arquivo.

**Conceito demonstrado:** o schema da ferramenta não é escrito à mão. O SDK
gera o JSON Schema a partir dos type hints, usa a docstring como descrição para
o modelo e transforma o valor de retorno em conteúdo estruturado. As anotações
`read_only_hint=True` dizem ao cliente que a ferramenta só lê.

---

## 3. Dockerfile e Compose

**Arquivo sugerido:** `03-dockerfile-compose.png`

**O que capturar:** os dois arquivos lado a lado no editor. Destaque:

- no `Dockerfile`: a instalação com `uv sync --locked`, o `USER pokemon`
  (usuário não root) e o `CMD ["python", "-m", "pokemon_mcp"]`;
- no `compose.yaml`: o mapeamento
  `"127.0.0.1:${MCP_HOST_PORT:-8000}:8000"` (publicação só no loopback) e o
  bloco `healthcheck`.

**Conceito demonstrado:** empacotar o servidor em contêiner é o que torna o
laboratório fácil de repetir: não é preciso ter Python na máquina, as
dependências Python estão fixadas no `uv.lock`, o processo roda sem privilégios
e a porta fica publicada apenas no loopback. (A imagem base usa tag de linha,
não digest — veja `docs/versoes-e-referencias.md`.)

---

## 4. Contêiner saudável

**Arquivo sugerido:** `04-container-saudavel.png`

**O que capturar:** um terminal com a sequência completa:

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

O `STATUS` precisa aparecer como `Up ... (healthy)` e o `curl` deve devolver
`{"status":"ok","server":"pokemon-mcp-server"}`.

**Conceito demonstrado:** o processo está no ar e o healthcheck do Compose
confirma isso. Diga na apresentação que este print prova apenas que o
**processo** responde: `/health` é uma rota HTTP auxiliar, não uma capacidade
MCP. A prova do protocolo vem nos prints 5 a 8.

---

## 5. Descoberta das Tools

**Arquivo sugerido:** `05-descoberta-tools.png`

**O que capturar:** o MCP Inspector conectado a `http://localhost:8000/mcp`
pelo transporte HTTP, na aba de ferramentas, com as três ferramentas listadas e
o formulário de argumentos de uma delas visível.

O comando exato do Inspector e os rótulos que mudam entre versões estão em
[conectar-cliente.md](conectar-cliente.md).

Alternativa sem Node.js: capture a saída do smoke test, que também lista as
ferramentas descobertas:

```bash
docker compose --profile test run --build --rm smoke
```

O `--build` garante que a imagem usada contém o código e os scripts atuais;
sem ele o Compose pode reaproveitar uma imagem `dev` construída antes das suas
últimas alterações — e o print mostraria a versão errada.

**Conceito demonstrado:** é isto que MCP resolve. O cliente não foi programado
para conhecer este servidor: ele perguntou quais capacidades existem e recebeu
nomes, descrições e schemas. Qualquer cliente MCP faria o mesmo.

---

## 6. Execução de uma Tool e resultado real

**Arquivo sugerido:** `06-execucao-tool.png`

**O que capturar:** no Inspector, o resultado de `get_pokemon` com
`name_or_id = pikachu`. Deixe visível o painel de resultado com o conteúdo
estruturado, incluindo `height_m: 0.4`, `weight_kg: 6.0`, a habilidade
`lightning-rod` com `is_hidden: true` e o `source_url`.

**Print complementar sugerido:** `06b-logs-consulta.png`, com

```bash
docker compose logs pokemon-mcp-server | tail -20
```

mostrando as linhas `consultando PokéAPI: https://pokeapi.co/api/v2/pokemon/pikachu/`
e a resposta `200 OK`.

**Conceito demonstrado:** o dado é real e rastreável. O servidor consultou a
PokéAPI por HTTPS, converteu decímetros e hectogramas para metros e
quilogramas, devolveu um objeto enxuto em vez do JSON gigante da API e informou
a URL exata da fonte. Aqui fica claro o papel de cada peça: a PokéAPI é a fonte
de dados, o MCP Server é o integrador, MCP é o protocolo entre cliente e
servidor.

---

## 7. Leitura do Resource

**Arquivo sugerido:** `07-resource-guide.png`

**O que capturar:** no Inspector, a aba de recursos, com `pokemon://guide`
listado e o conteúdo Markdown aberto ao lado.

**Conceito demonstrado:** um Resource é conteúdo endereçado por URI que a
**aplicação** decide carregar como contexto, diferente de uma Tool, que o
**modelo** decide chamar. É o mesmo servidor, a mesma conexão e outra
capacidade do protocolo.

---

## 8. Obtenção do Prompt

**Arquivo sugerido:** `08-prompt-compare.png`

**O que capturar:** no Inspector, a aba de prompts, com `compare_pokemon`
selecionado, os campos `pokemon_a` e `pokemon_b` preenchidos (por exemplo,
`pikachu` e `bulbasaur`) e o resultado da renderização: a mensagem de template.

**Conceito demonstrado:** obter um Prompt devolve **o template**, não a
resposta. O servidor não chamou `get_pokemon` e não falou com nenhum modelo.
Quem executa as instruções é a aplicação de IA, depois que o usuário escolhe o
Prompt. Vale mostrar no print que o texto proíbe declarar vencedor de batalha:
os limites do dado são escritos por quem constrói o servidor.

---

## 9. Pergunta em linguagem natural em um cliente compatível

**Arquivo sugerido:** `09-pergunta-natural.png`

**O que capturar:** uma conversa em uma aplicação de IA local já conectada ao
servidor (veja [conectar-cliente.md](conectar-cliente.md)), mostrando a
pergunta, a indicação de que uma ferramenta foi chamada e a resposta final.

Perguntas sugeridas, uma por print se quiser mais de um:

- "Quais são os tipos e as habilidades do Pikachu?"
- "O que faz a habilidade Static?"
- "Quais tipos causam dano dobrado ao tipo elétrico?"
- "Compare Pikachu e Bulbasaur pelos atributos base."

**Conceito demonstrado:** o fechamento do ciclo. O usuário escreveu português,
o modelo escolheu a ferramenta, o servidor buscou o dado real e a resposta veio
com fonte. O servidor continua sem nenhum LLM dentro dele.

**Se você não usar nenhuma aplicação compatível**, não fabrique a conversa.
Substitua este print pela saída do smoke test e explique em voz que a etapa
seguinte é conectar o cliente da sua preferência.

---

## Conferência final

Antes de montar os slides, verifique se os prints, juntos, sustentam estas
afirmações:

- [ ] o servidor é um projeto pequeno e comum (print 1 e 2);
- [ ] ele roda em contêiner, sem Python na máquina (print 3 e 4);
- [ ] um cliente descobre as capacidades sozinho (print 5);
- [ ] as consultas devolvem dados reais e citáveis (print 6);
- [ ] Resource e Prompt existem além das Tools (prints 7 e 8);
- [ ] o ciclo completo funciona em linguagem natural (print 9);
- [ ] nenhuma imagem mostra chave de API, token de sessão do Inspector ou dado
      pessoal. Recorte ou borre se aparecer.
