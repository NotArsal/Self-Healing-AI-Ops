FROM python:3.12-slim

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
