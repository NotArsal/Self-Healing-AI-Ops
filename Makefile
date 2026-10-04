.PHONY: setup up dev-api dev-console check test lint format types

# Default
all: setup check test

# Setup dependencies
setup:
	cd apps/control-plane && uv sync
	cd apps/console && pnpm install

# Start infrastructure
up:
	docker-compose -f infra/docker-compose.yml up -d

# Stop infrastructure
down:
	docker-compose -f infra/docker-compose.yml down

# Run the API server
dev-api:
	cd apps/control-plane && uv run uvicorn kavach.main:app --reload

# Run the console
dev-console:
	cd apps/console && pnpm dev

# Quality checks
lint:
	cd apps/control-plane && uv run ruff check .
	cd apps/console && pnpm lint

format:
	cd apps/control-plane && uv run ruff format .
	cd apps/console && pnpm format

types:
	cd apps/control-plane && uv run mypy .

check: lint format types

# Testing
test:
	cd apps/control-plane && uv run pytest
	cd apps/console && pnpm test

# Run a specific scenario validation and load
scenario:
	cd apps/control-plane && uv run python -m kavach.scenarios.runner $(NAME)
