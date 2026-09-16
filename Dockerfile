# syntax=docker/dockerfile:1

# Imagem oficial do uv já com Python 3.12, para instalar as dependências
# exatamente como estão no uv.lock.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

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
FROM python:3.12-slim-bookworm AS runtime

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

USER pokemon

EXPOSE 8000

CMD ["python", "-m", "pokemon_mcp"]


# --- Imagem de testes: acrescenta dependências de desenvolvimento e os testes. ---
FROM builder AS dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

COPY tests/ ./tests/
COPY scripts/ ./scripts/

CMD ["uv", "run", "--no-sync", "pytest"]
