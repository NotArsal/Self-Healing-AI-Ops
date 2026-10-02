"""Settings. The one module-level singleton AGENTS.md permits.

Every environment variable the control plane reads is declared here, so that
`.env.example` can be checked against a single source of truth rather than
grepped for out of call sites.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["SIMULATION", "APPROVAL", "AUTONOMOUS"]


class Settings(BaseSettings):
    """Control-plane configuration, read from the environment.

    Phase 0 declares only what Phase 0 uses, plus the infrastructure URLs that
    compose already supplies — a mismatch between compose and config is the kind
    of drift that costs an hour in P3.

    No `redis_url`: Redis is not started in Phase 0 because nothing uses it. It
    returns in P3 (FR-16/17/18 and console pub/sub), and the setting comes back
    with it rather than sitting here unread.
    """

    model_config = SettingsConfigDict(
        env_prefix="KAVACH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"

    # Infrastructure. Unused in Phase 0 — wired in P2/P3.
    database_url: str = "postgresql+asyncpg://kavach:kavach@localhost:5433/kavach"
    prometheus_url: str = "http://localhost:9091"
    otlp_endpoint: str = "http://localhost:4318"

    # Kavach's own RCA model. Points DIRECTLY at Ollama, never through
    # Toxiproxy, so injecting F01/F02 into the target cannot blind the
    # diagnostician (PRD.md §6.3).
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"

    # Global default mode. SIMULATION, per PRD.md §5.4 — a project must be moved
    # out of it explicitly, after preflight passes.
    default_mode: Mode = "SIMULATION"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so FastAPI's Depends does not re-read the environment per request."""
    return Settings()
