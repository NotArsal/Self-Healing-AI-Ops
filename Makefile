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
# NOT 8080. `make up` publishes the container there, and on Windows a local
# uvicorn can bind the same port without error and shadow it. See .env.example.
DEV_API_PORT ?= 8081
# --env-file is REQUIRED, not decoration. Compose reads `.env` from the
# compose file's directory, so the repo-root .env was silently inert and
# every ${VAR} fell back to its default - which looked fine only because
# every var had one. `make setup` creates .env, so this path always exists.
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml
UV      := uv --directory $(CP)

.DEFAULT_GOAL := help
.PHONY: postmortem help setup up down ps logs dev-api dev-console lint format types test offline \
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
	@echo   test              pytest + console vitest
	@echo   socket-test       prove Docker socket access
	@echo   check             lint + types + test. THE GATE.
	@echo.
	@echo   target-up         start the system under management (P1)

# --- Setup -------------------------------------------------------------------

setup: .env
	$(UV) sync --extra dev
	cd $(CONSOLE) && pnpm install

# Compose needs this file to exist. Never overwritten: a real .env wins.
.env:
	@echo Creating .env from .env.example - set KAVACH_TARGET_ADMIN_TOKEN in it.
	cp .env.example .env

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
	@echo Hot-reload API on $(DEV_API_PORT). The NORMAL path is `make up` on 8080.
	$(UV) run uvicorn kavach.main:app --reload --port $(DEV_API_PORT)

dev-console:
	cd $(CONSOLE) && pnpm dev

# --- Quality -----------------------------------------------------------------

lint:
	$(UV) run ruff check .
	$(UV) run ruff check ../../harness
	cd $(CONSOLE) && pnpm lint

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

types:
	$(UV) run mypy
	$(UV) run mypy --strict ../../harness
	cd $(CONSOLE) && pnpm types

test:
	$(UV) run pytest -q
	cd $(CONSOLE) && pnpm test

socket-test:
	$(UV) run pytest -q -m docker -v

test-integration:
	@echo Not implemented until P3.
	@exit 1

# gen-client runs FIRST so `types` checks the console against a freshly
# generated client. A backend schema change therefore fails the gate here
# rather than at runtime in the browser.
check: gen-client lint types test
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
	$(UV) run python -m kavach.openapi
	cd $(CONSOLE) && pnpm gen:client

# --- Demo and measurement ----------------------------------------------------

# Capture a last-known-good baseline from the live target. Refuses to save an
# unhealthy capture; pass ARGS="--force" to override, and read the refusal
# first. Was a P1-era stub printing "Not implemented until P1" until
# 2026-10-17, long after P1 shipped the capture it calls.
onboard:
	$(UV) run python -m kavach.onboarding.baseline $(ARGS)

inject:
	@echo Not implemented until P2.
	@exit 1

# The four-act demo: autonomous heal, approval heal, rollback, and a
# refusal on a fault outside the catalogue. NAME picks the scenario, ACTS
# runs a subset (ACTS=2 to rehearse just the approval pause).
#
# ONE full run fits inside permit()'s five-incidents-an-hour blast radius;
# a second rehearsal in the same hour will park, which is correct behaviour
# and not a bug. Space rehearsals an hour apart.
scenario:
	$(UV) run python -I ../../harness/scenario.py --name $(or $(NAME),demo-full) $(ARGS)

# The P8 offline rehearsal: the four acts with every cloud provider key
# forced empty, proven empty inside the container, and put back afterwards.
# NEVER edits .env - compose resolves ${VAR:-} from the shell first, so the
# keys are overridden rather than rewritten. Pauses for you to pull the
# network; ARGS=--no-prompt skips that and says so in the result.
offline:
	bash harness/offline_rehearsal.sh $(ARGS)

# The metrics table from PRD section 10, over repeated live injections.
# PACED, NOT FAST: permit() allows five incident starts an hour and an
# approved heal costs two, so a full run is hours of mostly waiting. That is
# deliberate - the alternative was restarting the API between repetitions to
# clear the in-memory counter, which would have measured a system that does
# not exist. ARGS="--reps 1 --classes F08" for a smoke test.
# The postmortem Kavach writes about itself, from its own audit record.
# Renders the most recent incident; ARGS="INC-191650" picks one, and
# ARGS="--out notes.md" writes a file. Reads the running control plane,
# because the audit log lives inside its container.
postmortem:
	$(UV) run python -m kavach.audit.postmortem $(ARGS)

bench:
	$(UV) run python -I ../../harness/report.py $(ARGS)
