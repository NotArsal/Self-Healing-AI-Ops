import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kavach.api.routes import alerts, debts, events, health, incidents, scenarios
from kavach.config import settings
from kavach.debt.checker import check_debts_loop
from kavach.detection.loop import detection_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    tasks = [
        asyncio.create_task(check_debts_loop()),
        asyncio.create_task(detection_loop()),
    ]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    telemetry={"tracer_provider": tracer_provider},
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


app.include_router(debts.router, prefix="/api/v1")
