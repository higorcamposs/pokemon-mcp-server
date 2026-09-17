# syntax=docker/dockerfile:1

# Imagem oficial do uv já com Python 3.12, para instalar as dependências
# exatamente como estão no uv.lock.
#
# Base Debian 13 (trixie), não bookworm: a Astral parou de publicar atualizações
# da variante bookworm (a última é de fevereiro/2026), então continuar nela
# significaria construir com um uv congelado. O Python continua sendo 3.12, que
# é o que `requires-python` exige — nada no `pyproject.toml` ou no `uv.lock`
# muda por causa desta troca.
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Primeiro só os manifestos: a camada de dependências só é refeita quando eles mudam.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


# --- Imagem de execução: Python slim, sem uv e sem ferramentas de build. ---
FROM python:3.12-slim-trixie AS runtime

# O endereço interno (0.0.0.0:8000 e /mcp) é fixo no código do servidor, em
# src/pokemon_mcp/__main__.py: não há variável de ambiente para mudá-lo.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Usuário não root.
RUN groupadd --system --gid 1001 pokemon \
    && useradd --system --uid 1001 --gid pokemon --create-home pokemon

WORKDIR /app

COPY --from=builder --chown=pokemon:pokemon /app/.venv /app/.venv
COPY --chown=pokemon:pokemon src/ /app/src/
# A licença viaja junto com a imagem: quem baixa do registry não tem o
# repositório à mão para consultá-la.
COPY --chown=pokemon:pokemon LICENSE /app/LICENSE

USER pokemon

EXPOSE 8000

# Mesma verificação do compose.yaml, agora embutida na própria imagem: quem
# roda um `docker run` avulso também enxerga o estado de saúde. Usa o Python
# que já está na imagem — instalar curl só para isto seria peso morto.
#
# Ela confirma apenas que o PROCESSO responde. Não consulta a PokéAPI e não
# exercita o protocolo MCP; para isso existe o scripts/smoke_test.py.
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

# Preenchidos pelo fluxo de publicação (.github/workflows/publish-image.yml).
# Os padrões abaixo existem só para um build local não mentir dizendo que é uma
# versão lançada.
ARG VERSION=0.0.0-dev
ARG REVISION=unknown

LABEL org.opencontainers.image.source="https://github.com/higorcamposs/pokemon-mcp-server" \
      org.opencontainers.image.title="Pokémon MCP Server" \
      org.opencontainers.image.description="MCP Server didático que expõe dados da PokéAPI como três Tools, um Resource e um Prompt por Streamable HTTP. Não embute modelo de linguagem." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

CMD ["python", "-m", "pokemon_mcp"]


# --- Imagem de testes: acrescenta dependências de desenvolvimento e os testes. ---
FROM builder AS dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

COPY tests/ ./tests/
COPY scripts/ ./scripts/

CMD ["uv", "run", "--no-sync", "pytest"]
