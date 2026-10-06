from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kavach.api.routes import alerts, events, health, incidents, scenarios
from kavach.config import settings

from contextlib import asynccontextmanager
import asyncio
from kavach.debt.checker import check_debts_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task = asyncio.create_task(check_debts_loop())
    yield
    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(scenarios.router)
app.include_router(incidents.router)
app.include_router(events.router)
app.include_router(alerts.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": f"Welcome to {settings.app_name}"}
