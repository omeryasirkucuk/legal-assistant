.PHONY: setup db api api-protected web test migrate corpus

setup:
	cd services/api && uv sync --locked
	cd apps/web && npm ci

db:
	docker compose up -d --wait db

migrate: db
	cd services/api && uv run --locked alembic upgrade head

corpus: migrate
	cd services/api && uv run --locked python -m legal_api.corpus.statutes

api: migrate
	cd services/api && uv run --locked uvicorn legal_api.main:app --reload --port 8000

api-protected:
	cd services/api && DATA_MODE=protected uv run --locked uvicorn legal_api.main:app --no-access-log --port 8000

web:
	cd apps/web && npm run dev

test: migrate
	cd services/api && uv run --locked pytest
