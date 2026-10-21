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
# Extra pytest flags. CI passes -m "not docker".
#
# NOT a way to make the gate quieter. The docker-marked tests need a
# provisioned target application and a local Ollama, not merely a reachable
# socket - and a GitHub runner HAS a socket, so `conftest.py`'s probe does not
# skip them there and they fail on a missing ../Target_RAG-App. Excluding them
# by marker states that plainly in the workflow; loosening the probe to make
# them disappear would hide them on developer machines too.
PYTEST_ARGS ?=

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
	@echo   bench             the metrics table, paced under the limiter
	@echo   figures           report figures from harness/reports
	@echo   diagnoses         freeze the in-memory diagnoses to an artifact
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
	$(UV) run pytest -q $(PYTEST_ARGS)
	cd $(CONSOLE) && pnpm test

socket-test:
	$(UV) run pytest -q -m docker -v

# gen-client runs FIRST so `types` checks the console against a freshly
# generated client. A backend schema change therefore fails the gate here
# rather than at runtime in the browser.
check: gen-client lint types test
	@echo check: OK

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

# Wired 2026-10-20. It had printed "Not implemented until P2" and exited 1
# since the scaffold, while `harness/inject.py` has injected F01, F06, F07 and
# F08 since P6 - and README.md documented `make inject` as a working command.
# A recipe that lies about a capability the repository has is worse than an
# absent one: it tells a reader the feature does not exist.
inject:
	$(UV) run python -I ../../harness/inject.py $(ARGS)

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
# RUN THIS FROM GIT BASH ON WINDOWS. Under PowerShell, make shells out
# through cmd.exe and `bash` there resolves to WSL, which cannot see the
# Docker socket or uv. The script detects that and refuses with a pointer.
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

# Report figures, drawn from the artifacts in harness/reports. Paths are
# passed explicitly because $(UV) runs with apps/control-plane as its working
# directory, so the script's own relative defaults would miss.
figures:
	$(UV) run python -I ../../harness/figures.py \
		--reports ../../harness/reports \
		--out ../../harness/reports/figures $(ARGS)

# Freezes the diagnoses behind RESEARCH_NOTES section 10 to an artifact. They
# live in the API's in-process ring (RESEARCH_NOTES 7.2), so `make down` loses
# them. Read-only: no injection, no gate interaction, nothing mutated.
diagnoses:
	$(UV) run python -I ../../harness/dump_diagnoses.py \
		--out ../../harness/reports/diagnoses-$$(date +%Y%m%d).json $(ARGS)
