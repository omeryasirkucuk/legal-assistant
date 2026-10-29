.PHONY: db api web test migrate

db:
	docker compose up -d --wait db

migrate: db
	cd services/api && uv run alembic upgrade head

api: migrate
	cd services/api && uv run uvicorn legal_api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

test: migrate
	cd services/api && uv run pytest
