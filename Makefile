.PHONY: setup up down dev-api dev-api-live dev-console check test test-integration lint format format-check types migrate migration scenario bench bench-live onboard target-up inject revert

# Default
all: setup check test

# Setup dependencies
setup:
	cd apps/control-plane && uv sync
	cd apps/console && pnpm install

# Start infrastructure
up:
	docker-compose $(if $(PROFILE),--profile $(PROFILE),) -f infra/docker-compose.yml up -d

# Stop infrastructure
down:
	docker-compose -f infra/docker-compose.yml down

# Run the API server
dev-api:
	cd apps/control-plane && uv run uvicorn kavach.main:app --reload --port 8001

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

# What `check` uses. `format` rewrites the tree, so a gate built on it always
# passed: it reported success having changed 41 files.
format-check:
	cd apps/control-plane && uv run ruff format --check .

types:
	cd apps/control-plane && uv run mypy .

# AGENTS.md documents this as "lint + types + test. The gate." It was
# lint + format + types, with no tests and a formatter that could not fail.
check: lint format-check types test

# Testing
test:
	cd apps/control-plane && uv run pytest -m "not live and not llm and not laya"
	cd apps/console && pnpm test

# The live F01 loop against targets/proof2. Starts its own copy of the target,
# so `make target-up` must NOT be running or port 8080 will be taken.
test-integration:
	cd apps/control-plane && uv run pytest -m live -v

# Run a specific scenario validation and load
scenario:
	cd apps/control-plane && uv run python -m kavach.scenarios.runner $(NAME)

# Measurements that need no running target: RCA accuracy with the conditional
# heal metrics, and shadow Laya against the rule engine. Needs Ollama.
bench:
	cd apps/control-plane && uv run python -m harness.rca_bench
	cd apps/control-plane && uv run python -m harness.laya_vs_rules
	cd apps/control-plane && uv run python -m harness.report

# The undo ablation measures a live application, so the target must be up:
#   make target-up ; make onboard APP=targets/proof2 ; make bench-live
bench-live:
	cd apps/control-plane && uv run python -m harness.ablation_undo

# Database
migrate:
	cd apps/control-plane && uv run alembic upgrade head

migration:
	cd apps/control-plane && uv run alembic revision --autogenerate -m "$(NAME)"

# Onboard an application: preflight + capture the healthy baseline that
# verification measures its deltas against. Run it with the target up and healthy.
onboard:
	cd apps/control-plane && uv run python scripts/onboard.py ../../$(APP)/kavach.yaml

# The application under management.
target-up:
	cd targets/proof2 && uv run --with fastapi --with uvicorn python main.py

# Break it / unbreak it. FAULT=F01 or F03.
inject:
	curl -s -X POST http://localhost:8080/inject/$(FAULT)

revert:
	curl -s -X POST http://localhost:8080/revert/$(FAULT)

# The control plane watching proof2 autonomously. Detection ticks every 15s.
dev-api-live:
	cd apps/control-plane && TARGET_MANIFEST=../../targets/proof2/kavach.yaml \
		EXECUTION_MODE=AUTONOMOUS uv run uvicorn kavach.main:app --reload
