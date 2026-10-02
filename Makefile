# Kavach. Canonical task definitions — AGENTS.md § Commands.
#
# Targets not yet implemented fail LOUDLY rather than silently succeeding, so a
# green `make check` never means "the target did nothing".
#
# Windows note: GNU make is not installed by default. `make.ps1` mirrors these
# targets so Phase 0 runs without it. Install GNU make (winget install
# ezwinports.make) and delete make.ps1 to remove the duplication.

CP      := apps/control-plane
CONSOLE := apps/console
COMPOSE := docker compose -f infra/docker-compose.yml
UV      := uv --directory $(CP)

.DEFAULT_GOAL := help
.PHONY: help setup up down logs dev-api dev-console lint format types test \
        test-integration check migrate migration gen-client target-up target-down \
        onboard inject scenario bench socket-test

help:
	@echo "Kavach — see AGENTS.md for the full list"
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

# --- Setup -------------------------------------------------------------------

setup: ## uv sync + pnpm install
	$(UV) sync --extra dev
	cd $(CONSOLE) && pnpm install

# --- Stacks ------------------------------------------------------------------

up: ## start the control plane
	$(COMPOSE) up -d --build

down: ## stop the control plane
	$(COMPOSE) down

logs: ## tail a service: make logs SERVICE=api
	$(COMPOSE) logs -f $(SERVICE)

target-up: ## start the system under management (separate repo)
	@echo "Not implemented until P1. The target is a separate compose project:"
	@echo "  cd \"$$KAVACH_TARGET_PATH\" && docker compose up -d"
	@exit 1

target-down:
	@echo "Not implemented until P1." && exit 1

# --- Development -------------------------------------------------------------

dev-api: ## FastAPI with reload
	$(UV) run uvicorn kavach.main:app --reload --port 8000

dev-console: ## Next.js dev server
	cd $(CONSOLE) && pnpm dev

# --- Quality -----------------------------------------------------------------

lint: ## ruff check + eslint
	$(UV) run ruff check .
	cd $(CONSOLE) && pnpm lint

format: ## ruff format + prettier
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

types: ## mypy --strict + tsc --noEmit
	$(UV) run mypy
	cd $(CONSOLE) && pnpm types

test: ## pytest + vitest
	$(UV) run pytest -q

socket-test: ## prove Docker socket access (PL-03)
	$(UV) run pytest -q -m docker -v

test-integration: ## the seven fault-loop tests
	@echo "Not implemented until P3." && exit 1

check: lint types test ## THE GATE
	@echo "check: OK"

# --- Database ----------------------------------------------------------------

migrate:
	@echo "Not implemented until P3 (no schema yet)." && exit 1

migration:
	@echo "Not implemented until P3 (no schema yet)." && exit 1

# --- Codegen -----------------------------------------------------------------

gen-client:
	@echo "Not implemented until P5." && exit 1

# --- Demo and measurement ----------------------------------------------------

onboard:
	@echo "Not implemented until P1." && exit 1

inject:
	@echo "Not implemented until P2." && exit 1

scenario:
	@echo "Not implemented until P9." && exit 1

bench:
	@echo "Not implemented until P8." && exit 1
