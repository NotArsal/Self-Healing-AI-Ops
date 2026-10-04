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
    #
    # NOTE: this is a declared default, not an enforced gate. Nothing reads it
    # to decide whether an action may run, because `permit()` does not exist
    # until P6 (docs/decisions/0006, amendment 2026-10-04). The console says so
    # on screen rather than implying a gate that is not there.
    default_mode: Mode = "SIMULATION"

    # --- the target, as the console and the loop runner address it (P4) ------
    # These mirror `kavach.yaml`'s control interface and the harness defaults.
    # Declared here rather than hardcoded in the API layer so compose and config
    # cannot drift.
    target_path: str = "D:/Vit/Academics Sem-5/EDI/Target_RAG-App"
    target_project: str = "simple-rag"
    target_compose_project: str = "target_rag-app"
    target_health_url: str = "http://localhost:8000/healthz"
    target_chat_url: str = "http://localhost:8000/v1/chat"
    target_config_url: str = "http://localhost:8000/v1/admin/config"
    target_admin_token: str = "local-dev-token"
    target_service_names: str = "backend,db,frontend,toxiproxy,prometheus"

    # Floor below which a diagnosis cannot drive a repair. Mirrors the
    # manifest's value; the RCA validator is what enforces it.
    confidence_threshold: float = 0.75

    # Dev-only browser origin for the console. Empty in production, where the
    # console is served from the same origin and CORS is unnecessary.
    console_origin: str = "http://localhost:3001"

    def target_services(self) -> list[str]:
        return [s.strip() for s in self.target_service_names.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so FastAPI's Depends does not re-read the environment per request."""
    return Settings()
