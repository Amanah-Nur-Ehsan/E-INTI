# Shared image for the API and Celery worker services -- same dependencies,
# only the command differs per docker-compose service. NOT used for local
# Mac dev: `make dev` runs uvicorn/celery directly on the host so local
# models (SPECTER2, the cross-encoder) can use Apple Silicon's MPS GPU,
# which Docker cannot pass through. This image is CPU-only and meant for a
# Linux server deploy behind a reverse proxy.
FROM python:3.12-slim

# curl: used by the api service's healthcheck in docker-compose.yml.
# build-essential: some of spaCy's dependency chain (thinc/blis) falls back
# to compiling from source on platforms without a prebuilt wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /usr/local/bin/

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

# Dependencies before app code: this layer is cached across code changes
# that don't touch pyproject.toml/uv.lock, so a normal code-only rebuild
# skips reinstalling torch/spacy/etc. entirely.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# Bake spaCy + SPECTER2 + the cross-encoder into the image at build time:
# the container then needs no network access for models at runtime and
# doesn't lose the cache on every restart/redeploy (no volume needed).
# USE_MOCK_PROVIDERS=true here only satisfies Settings' fail-fast key check
# for this one-off script -- it has no effect on which model weights
# actually get downloaded (that's EMBEDDING_FAKE/RERANKER_FAKE, both false
# by default).
RUN USE_MOCK_PROVIDERS=true python -m spacy download en_core_web_sm && \
    USE_MOCK_PROVIDERS=true python scripts/warmup_models.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
