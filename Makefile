.PHONY: up down logs test lint typecheck smoke-model

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api worker web

test:
	docker compose run --rm api pytest
	docker compose run --rm web npm test -- --run

lint:
	docker compose run --rm api ruff check src tests
	docker compose run --rm web npm run lint

typecheck:
	docker compose run --rm api mypy src
	docker compose run --rm web npm run typecheck

smoke-model:
	docker compose run --rm -e RUN_REAL_MODEL_SMOKE=1 api \
		pytest -q tests/smoke/test_real_model_gateway.py
