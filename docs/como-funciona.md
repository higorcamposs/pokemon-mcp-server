# Como o Pokémon MCP Server funciona

Este guia acompanha uma requisição completa, explica o papel de cada módulo e
mostra quais partes você trocaria para adaptar o laboratório a outro domínio.

Para executar o projeto antes de estudar o código, siga o
[Quickstart do README](../README.md#quickstart-em-cinco-minutos).

## As peças do sistema

| Termo | Papel neste projeto |
| --- | --- |
| Usuário | faz uma pergunta em linguagem natural |
| Host | aplicação que contém o cliente MCP e, normalmente, o modelo de IA |
| Cliente MCP | conecta ao servidor, descobre capacidades e envia chamadas MCP |
| Servidor MCP | publica Tools, Resource e Prompt usando um contrato comum |
| Tool | operação que o modelo pode escolher executar |
| Resource | conteúdo identificado por uma URI que o cliente pode carregar |
| Prompt | template de mensagens que o usuário pode selecionar |
| PokéAPI | API REST externa que fornece os dados de Pokémon |

O Host e o cliente MCP podem fazer parte da mesma aplicação. VS Code, Codex e
MCP Inspector são exemplos de clientes; a PokéAPI não é cliente MCP e não fala
esse protocolo.

## Visão geral

```text
Usuário
  │ “Quais são as habilidades do Pikachu?”
  ▼
Host / aplicação de IA
  ├── modelo lê a descrição das Tools
  └── cliente chama get_pokemon({"name_or_id": "pikachu"})
        │
        │ MCP sobre Streamable HTTP
        ▼
Pokémon MCP Server
  ├── normaliza o identificador
  ├── procura a resposta no cache
  ├── consulta a PokéAPI quando necessário
  ├── valida o JSON
  ├── converte unidades
  └── devolve um objeto estruturado com source_url
        │
        │ HTTPS / REST
        ▼
PokéAPI
```

O servidor não recebe a pergunta em português diretamente. O modelo conectado
interpreta a pergunta, descobre que `get_pokemon` é adequada e monta a chamada
com o argumento definido pelo schema da Tool.

## O ciclo de `get_pokemon("pikachu")`

### 1. O cliente descobre as capacidades

Ao conectar, o cliente MCP negocia a versão do protocolo e consulta o que o
servidor oferece. A resposta anuncia:

- as Tools `get_pokemon`, `get_ability` e `get_type`;
- o Resource `pokemon://guide`;
- o Prompt `compare_pokemon`;
- as instruções gerais do servidor.

O cliente recebe nome, descrição e schema de entrada de cada Tool. Ele não
precisa ter sido programado especificamente para Pokémon.

### 2. O modelo escolhe uma Tool

A descrição de `get_pokemon` informa que ela devolve tipos, unidades
normalizadas, habilidades e atributos base. O modelo envia uma chamada MCP
equivalente a:

```json
{
  "name": "get_pokemon",
  "arguments": {"name_or_id": "pikachu"}
}
```

Isso é uma mensagem do protocolo, não uma chamada direta à função Python.

### 3. O servidor valida o argumento

O schema limita o tamanho do texto. Em seguida, `normalize_identifier`:

- remove espaços das extremidades;
- converte letras para minúsculas;
- aceita um nome canônico com hífens ou um número positivo;
- rejeita URLs, caminhos, espaços internos e caracteres especiais.

Assim, o argumento do cliente não consegue escolher uma URL arbitrária. O
recurso (`pokemon`, `ability` ou `type`) é definido pelo próprio servidor.

### 4. O cliente HTTP consulta a PokéAPI

A chave `pokemon/pikachu` é procurada no cache em memória. Se não existir ou
estiver vencida, o servidor faz:

```text
GET https://pokeapi.co/api/v2/pokemon/pikachu/
```

O mesmo cliente HTTP é reutilizado durante toda a vida do processo. Isso evita
abrir um pool de conexões novo para cada Tool.

### 5. A resposta externa é validada

O JSON da PokéAPI é grande. O servidor seleciona apenas o contrato que promete
ao cliente e confere tipos, campos obrigatórios e limites numéricos.

Para um Pokémon, ele também:

- ordena os tipos pelo campo `slot`;
- converte `height` de decímetros para metros;
- converte `weight` de hectogramas para quilogramas;
- identifica habilidades ocultas;
- exige os seis atributos base.

Uma resposta incompleta ou com tipos inesperados não vira uma ficha
aparentemente válida. Ela produz um erro explícito e é retirada do cache.

### 6. O cliente recebe conteúdo estruturado

O modelo Pydantic se transforma no `structured_content` da resposta MCP. Além
dos dados resumidos, o objeto contém:

```json
{
  "source_url": "https://pokeapi.co/api/v2/pokemon/pikachu/"
}
```

O cliente pode mostrar o objeto diretamente ou entregá-lo ao modelo para
redigir uma resposta em linguagem natural. O dado veio da PokéAPI; a redação
final pertence à aplicação de IA.

## Passeio pelos módulos

### `src/pokemon_mcp/__main__.py`: entrada e transporte

[Abra o arquivo](../src/pokemon_mcp/__main__.py).

Esse módulo define o endereço interno `0.0.0.0:8000`, o caminho `/mcp` e inicia
o servidor com transporte Streamable HTTP. Também monta as listas permitidas
de `Host` e `Origin`, usadas pelo SDK contra DNS rebinding.

A porta interna é fixa. `MCP_HOST_PORT` muda apenas a porta publicada pelo
Compose na máquina do usuário.

### `src/pokemon_mcp/server.py`: capacidades MCP

[Abra o arquivo](../src/pokemon_mcp/server.py).

Aqui o `MCPServer` é criado e recebe instruções gerais. O módulo registra:

- três funções decoradas com `@mcp.tool`;
- o guia decorado com `@mcp.resource`;
- o template decorado com `@mcp.prompt`;
- a rota HTTP auxiliar `/health`;
- o `lifespan` que abre e fecha o cliente da PokéAPI.

A função `_consult` concentra o fluxo comum das três Tools: buscar, transformar
e traduzir falhas internas para mensagens de Tool compreensíveis.

### `src/pokemon_mcp/pokeapi.py`: integração HTTP

[Abra o arquivo](../src/pokemon_mcp/pokeapi.py).

Esse módulo não conhece MCP. Ele recebe um recurso e um identificador, monta a
requisição HTTP, aplica timeout, trata status de erro e devolve o JSON bruto
junto com a URL consultada.

Ele também contém:

- a normalização segura de identificadores;
- o cache TTL com limite LRU;
- as exceções específicas para entrada, timeout, indisponibilidade, 404 e JSON
  malformado.

Essa separação permite testar toda a integração com um transporte HTTP
simulado, sem iniciar um servidor MCP e sem acessar a internet.

### `src/pokemon_mcp/models.py`: contrato de saída

[Abra o arquivo](../src/pokemon_mcp/models.py).

Os modelos Pydantic descrevem exatamente o que cada Tool devolve. As funções
`build_pokemon`, `build_ability` e `build_type` transformam o JSON externo
nesses modelos.

Essas funções são puras: recebem dados e devolvem um modelo, sem rede ou estado
global. Por isso os casos normais e malformados podem ser testados com fixtures.

## De onde vêm os schemas das Tools

O projeto não mantém um JSON Schema manual para cada Tool. O SDK usa:

- a assinatura e os type hints da função para formar a entrada;
- `Annotated` e `Field` para limites e descrições do argumento;
- a docstring como explicação da Tool;
- o modelo Pydantic de retorno como schema da saída estruturada;
- `ToolAnnotations` para informar que a operação é somente leitura e acessa
  dados externos.

Quando um cliente lista as Tools, recebe esse contrato e consegue montar uma
interface ou orientar um modelo sem conhecer o código Python.

## Tool, Resource e Prompt na prática

### Tool executa uma operação

`get_pokemon` pode causar uma consulta externa. O modelo normalmente escolhe
quando chamá-la com base na pergunta e no schema disponível.

### Resource fornece conteúdo endereçável

`pokemon://guide` é um texto Markdown estático. O cliente lista e lê o recurso
por URI; nenhuma consulta à PokéAPI é necessária.

### Prompt fornece um template

Ao obter `compare_pokemon`, o cliente recebe uma mensagem orientando duas
chamadas de `get_pokemon`. Obter o Prompt:

- não chama as Tools;
- não consulta a PokéAPI;
- não executa um modelo;
- não produz a comparação final.

A aplicação conectada decide se apresenta, envia ou executa as instruções do
template.

## Cache, falhas e rastreabilidade

### Cache

O cache vive apenas no processo. Por padrão, guarda até 256 entradas durante
300 segundos. Reiniciar o contêiner apaga tudo. Definir TTL ou limite como
zero desliga o cache.

### Falhas

As exceções internas são convertidas em erros de Tool diferentes para:

- argumento inválido;
- recurso inexistente;
- timeout;
- PokéAPI indisponível;
- resposta externa fora do contrato.

O servidor não preenche lacunas com conhecimento interno e não devolve uma
ficha inventada quando a fonte falha.

### Rastreabilidade

Todas as Tools incluem `source_url`. Os logs distinguem uma consulta externa de
um `cache hit`, permitindo verificar se a fonte foi realmente acessada.

## Segurança e limite de implantação

O Compose publica a porta somente em `127.0.0.1`. O transporte também valida
`Host` e `Origin`. Essas proteções são importantes porque o laboratório não tem
autenticação.

Ele foi desenhado para uso local. Publicar a imagem no GHCR não publica o
servidor, e criar um túnel público remove a principal barreira de segurança do
laboratório.

## Como adaptar o laboratório para outro MCP Server

Use a estrutura como referência, não apenas troque nomes. Uma adaptação segura
segue esta ordem:

1. Defina a fonte de dados e quais operações realmente precisam virar Tools.
2. Descreva modelos de saída pequenos e úteis, sem repassar respostas externas
   inteiras ao modelo.
3. Implemente o cliente da fonte externa separado do protocolo MCP.
4. Valide entradas antes de montar URLs, consultas ou comandos.
5. Converta a resposta externa em modelos explícitos e trate campos ausentes.
6. Registre Tools com nomes, docstrings e anotações que descrevam efeitos reais.
7. Adicione Resource ou Prompt somente quando houver um caso de uso claro.
8. Documente origem, limites e situações em que o servidor deve falhar.

Preserve pelo menos estas camadas de teste:

- validação e normalização de entradas;
- transformação de respostas válidas e rejeição de respostas quebradas;
- timeout, 404, indisponibilidade e cache;
- descoberta e execução por um cliente MCP em memória;
- proteção de Host e Origin no transporte HTTP;
- smoke test contra o processo empacotado.

Se a nova integração escrever dados, acessar credenciais ou ficar disponível
fora do loopback, o desenho de segurança muda. Revise autenticação, autorização,
anotações das Tools e política de rede antes de reaproveitar a configuração
deste laboratório.

## Próximos passos

- [Executar o Quickstart](../README.md#quickstart-em-cinco-minutos)
- [Conectar um cliente MCP](conectar-cliente.md)
- [Ver os testes automatizados](../tests/)
- [Consultar versões e referências](versoes-e-referencias.md)
