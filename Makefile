# Kavach. Canonical task definitions - AGENTS.md section "Commands".
#
# Targets not yet implemented fail LOUDLY rather than silently succeeding, so a
# green `make check` never means "the target did nothing".
#
# PORTABILITY: recipes must work under BOTH sh (Linux/macOS/CI) and cmd.exe,
# which is what GNU make uses on Windows when sh is not on PATH. That means:
#   - no grep/awk/sed in a recipe
#   - no `$$VAR` shell expansion
#   - no quotes around echo text (cmd prints them literally)
# `make.ps1` mirrors these targets for anyone without GNU make installed.

CP      := apps/control-plane
CONSOLE := apps/console
COMPOSE := docker compose -f infra/docker-compose.yml
UV      := uv --directory $(CP)

.DEFAULT_GOAL := help
.PHONY: help setup up down ps logs dev-api dev-console lint format types test \
        socket-test test-integration check migrate migration gen-client \
        target-up target-down onboard inject scenario bench

help:
	@echo Kavach - control plane. See AGENTS.md for the full list.
	@echo.
	@echo   setup             uv sync + pnpm install
	@echo   up                start the control plane
	@echo   down              stop the control plane
	@echo   ps                container status
	@echo   logs SERVICE=api  tail one service
	@echo.
	@echo   dev-api           FastAPI with reload
	@echo   dev-console       Next.js dev server
	@echo.
	@echo   lint              ruff check + eslint
	@echo   format            ruff format + fix
	@echo   types             mypy --strict + tsc --noEmit
	@echo   test              pytest
	@echo   socket-test       prove Docker socket access
	@echo   check             lint + types + test. THE GATE.
	@echo.
	@echo   target-up         start the system under management (P1)

# --- Setup -------------------------------------------------------------------

setup:
	$(UV) sync --extra dev
	cd $(CONSOLE) && pnpm install

# --- Stacks ------------------------------------------------------------------

up:
	$(COMPOSE) up -d --build --remove-orphans

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f $(SERVICE)

target-up:
	@echo Not implemented until P1.
	@echo The target is a SEPARATE compose project in its own repository:
	@echo   cd D:\Vit\Academics Sem-5\EDI\Target_RAG-App
	@echo   docker compose up -d
	@exit 1

target-down:
	@echo Not implemented until P1.
	@exit 1

# --- Development -------------------------------------------------------------

dev-api:
	$(UV) run uvicorn kavach.main:app --reload --port 8080

dev-console:
	cd $(CONSOLE) && pnpm dev

# --- Quality -----------------------------------------------------------------

lint:
	$(UV) run ruff check .
	cd $(CONSOLE) && pnpm lint

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

types:
	$(UV) run mypy
	cd $(CONSOLE) && pnpm types

test:
	$(UV) run pytest -q

socket-test:
	$(UV) run pytest -q -m docker -v

test-integration:
	@echo Not implemented until P3.
	@exit 1

check: lint types test
	@echo check: OK

# --- Database ----------------------------------------------------------------

migrate:
	@echo Not implemented until P3 - no schema yet.
	@exit 1

migration:
	@echo Not implemented until P3 - no schema yet.
	@exit 1

# --- Codegen -----------------------------------------------------------------

gen-client:
	@echo Not implemented until P5.
	@exit 1

# --- Demo and measurement ----------------------------------------------------

onboard:
	@echo Not implemented until P1.
	@exit 1

inject:
	@echo Not implemented until P2.
	@exit 1

scenario:
	@echo Not implemented until P9.
	@exit 1

bench:
	@echo Not implemented until P8.
	@exit 1
