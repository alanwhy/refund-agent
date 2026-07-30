.PHONY: up down logs test lint typecheck

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
