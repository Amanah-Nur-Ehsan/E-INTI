.PHONY: up down dev api worker models db-upgrade db-revision test test-unit smoke lint fixtures web gen-api

up:
	docker compose up -d postgres redis

down:
	docker compose down

# One terminal, everything: containers + api + worker + web. Ctrl+C stops
# api/worker/web together (containers keep running -- `make down` for those).
dev:
	./scripts/dev.sh

api:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	PYTORCH_ENABLE_MPS_FALLBACK=1 uv run celery -A app.workers.celery_app worker \
		--loglevel=info --pool=solo

models:
	uv run python -m spacy download en_core_web_sm
	uv run python scripts/warmup_models.py

db-upgrade:
	uv run alembic upgrade head

db-revision:
	uv run alembic revision --autogenerate -m "$(m)"

test:
	uv run pytest -q

test-unit:
	uv run pytest -q -m "not integration"

smoke:
	USE_MOCK_PROVIDERS=true CELERY_TASK_ALWAYS_EAGER=true \
	EMBEDDING_FAKE=false RERANKER_FAKE=false PYTORCH_ENABLE_MPS_FALLBACK=1 \
	uv run python scripts/smoke_pipeline.py

lint:
	uv run ruff check app tests scripts

fixtures:
	uv run python scripts/make_fixtures.py

web:
	cd frontend && npm run dev

# Regenerate the typed API client from the running backend's OpenAPI schema.
# Requires `make api` running in another terminal.
gen-api:
	cd frontend && npx openapi-typescript http://localhost:8000/openapi.json -o lib/api/schema.d.ts
