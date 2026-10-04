"""App factory and routing.

`/healthz` is intentionally a liveness check and nothing more. The dependency
checking health endpoint that preflight and verification probe 1 need is on the
*target*, not here (PRD.md §5.2 item 2); the console reads a composed view of
every dependency from `GET /v1/system` instead.

P4 mounts the console API (`kavach.api.routes`). It is read-only apart from one
parameterless route that asks the control plane to run the loop it already
runs — see that module for what the browser deliberately cannot say.
"""

from typing import Annotated, Literal

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from kavach import __version__
from kavach.api.routes import router as console_router
from kavach.config import Mode, Settings, get_settings

logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    """Phase 0's only response model."""

    status: Literal["ok"]
    version: str
    default_mode: Mode


def create_app() -> FastAPI:
    app = FastAPI(
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

    app.include_router(console_router)
    return app


app = create_app()
