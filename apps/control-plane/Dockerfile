FROM python:3.12-slim

# git is a RUNTIME dependency, not a build tool. `onboarding/preflight.py`
# shells out to it to read the target's HEAD and working-tree state, and
# `executor/adapters/git.py` does the same for apply_patch. Without it
# `GET /v1/preflight` returns
#   FileNotFoundError: [Errno 2] No such file or directory: 'git'
# and reports `passed: false` with zero checks run - a preflight that cannot
# run is not a preflight that passed, and it looked like a project problem
# rather than a missing package. Found 2026-11-01 on a rebuilt image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# uv for dependency resolution; same tool as local dev so the lock is shared.
COPY --from=ghcr.io/astral-sh/uv:0.5.29 /uv /usr/local/bin/uv

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY kavach ./kavach

EXPOSE 8000

CMD ["uvicorn", "kavach.main:app", "--host", "0.0.0.0", "--port", "8000"]
