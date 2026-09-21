from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import endpoints
from app.memory.store import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise the pgvector memory table on startup
    init_db()
    yield


app = FastAPI(title="AIOps Control Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
