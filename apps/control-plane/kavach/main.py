"""App factory and routing.

`/healthz` is intentionally a liveness check and nothing more. The dependency
checking health endpoint that preflight and verification probe 1 need is on the
*target*, not here (PRD.md §5.2 item 2); the console reads a composed view of
every dependency from `GET /v1/system` instead.

P4 mounts the console API (`kavach.api.routes`). It is read-only apart from one
parameterless route that asks the control plane to run the loop it already
runs — see that module for what the browser deliberately cannot say.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import structlog
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from kavach import __version__, telemetry
from kavach.api.routes import router as console_router
from kavach.config import Mode, Settings, get_settings

logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    """Phase 0's only response model."""

    status: Literal["ok"]
    version: str
    default_mode: Mode


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Connect the incident store once, at startup.

    Connecting belongs here and not in a constructor: a runner built in a test
    must never wait on a database. Unavailable is a state rather than a
    failure, so a store that cannot connect is logged and the loop heals
    without it.
    """
    from kavach.api.routes import get_runner

    get_runner(get_settings()).init_store()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title="Kavach control plane",
        version=__version__,
        description=(
            "Autonomous self-healing operations platform. The implemented slice "
            "is F06 only: deterministic detection, LLM RCA behind a "
            "deterministic validation gate, one config-rollback repair, and "
            "fast verification. No safety engine, no graph, no persistence yet."
        ),
    )

    settings = get_settings()
    # First, so that anything logged during startup is already JSON at the
    # configured level and already in the buffer /v1/logs serves. Until
    # 2026-10-19 structlog.configure() was never called at all and
    # KAVACH_LOG_LEVEL was read by nothing (ADR 0018).
    telemetry.configure_logging(settings)
    if settings.console_origin:
        # Development only: the console runs on its own port under `next dev`.
        # Served from one origin in production, this middleware does nothing.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.console_origin],
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz(
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            default_mode=settings.default_mode,
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Kavach's own series, for the `kavach-api` scrape job.

        Out of the schema because it is not part of the console API and
        its format is Prometheus exposition, not JSON. Unauthenticated
        for the same reason `/healthz` is: it carries counters and
        durations, never a target value, a config key or a token.
        """
        body, content_type = telemetry.exposition()
        return Response(content=body, media_type=content_type)

    app.include_router(console_router)
    # Last, so the instrumentor sees every route. A collector that is
    # down or absent returns False and changes nothing else.
    tracing_on = telemetry.setup_tracing(app, settings)
    # The only log line that is not a failure path. It earns its place
    # twice: an operator reading /v1/logs after a restart sees WHICH build
    # and WHICH mode they are looking at, and its presence is the proof
    # that logging is configured at all - the other four statements fire
    # only when something has already gone wrong, so a silent buffer and a
    # broken buffer looked identical.
    #
    # AFTER setup_tracing, not before. Logged earlier it reported
    # tracing=False unconditionally, because tracing had not been set up
    # yet - a line whose stated fact was always wrong, which is worse than
    # no line at all.
    logger.info(
        "control plane started",
        version=__version__,
        default_mode=settings.default_mode,
        log_level=settings.log_level,
        tracing=tracing_on,
    )
    return app


app = create_app()
