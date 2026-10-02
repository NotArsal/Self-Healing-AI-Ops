"""App factory and the only route Phase 0 ships.

`/healthz` is intentionally a liveness check and nothing more. The dependency
checking health endpoint that preflight and verification probe 1 need is on the
*target*, not here (PRD.md §5.2 item 2) — and Kavach's own dependency checks
arrive with the components that have dependencies, in P2/P3.
"""

from typing import Annotated, Literal

import structlog
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from kavach import __version__
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
            "Autonomous self-healing operations platform. Phase 0 scaffold — "
            "no ingestion, detection, graph, safety engine or executor yet."
        ),
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

    return app


app = create_app()
