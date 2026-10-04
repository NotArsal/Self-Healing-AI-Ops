from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kavach.api.routes import events, health, incidents, scenarios
from kavach.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
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


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": f"Welcome to {settings.app_name}"}
