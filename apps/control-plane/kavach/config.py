"""Settings. The one module-level singleton AGENTS.md permits.

Every environment variable the control plane reads is declared here, so that
`.env.example` can be checked against a single source of truth rather than
grepped for out of call sites.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["SIMULATION", "APPROVAL", "AUTONOMOUS"]


def _env_files() -> tuple[str, ...]:
    """`.env` by cwd AND `.env` at the repository root.

    `env_file=".env"` alone is resolved against the CURRENT WORKING
    DIRECTORY, so it silently found nothing whenever the process did not
    start at the repo root - and `uv --directory apps/control-plane`, which
    is how every harness and Makefile target runs, never does. Keys written
    to the one gitignored file a user is told to use read back empty, with no
    error, because an absent `.env` is not an error.

    That cost real time twice: once on `KAVACH_TARGET_ADMIN_TOKEN` (a 401
    that looked like a target problem, and the Makefile carries a comment
    about it) and once on the cloud provider keys. Anchoring to the
    repository root as well fixes the class, not the instance.

    Both entries are returned rather than one: the root path does not exist
    inside the image, where the package lives at `/app/kavach` with no
    repository around it and compose supplies the environment directly. A
    missing env file is ignored, so listing both is safe in both places. The
    later entry wins where they differ, and they are the same file whenever
    the process did start at the root.
    """
    parents = Path(__file__).resolve().parents
    root = parents[3] if len(parents) > 3 else parents[1]
    return (".env", str(root / ".env"))


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
        env_file=_env_files(),
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

    # Which provider answers. `ollama` is the default and the REPORTED
    # configuration: PL-02 forbids a required cloud key, and a live demo that
    # depends on a third-party API being up is a demo that can fail in the
    # room. A cloud provider is opt-in, for the work where a bigger model is
    # the variable under test - see ADR 0011 on the 0-of-15 diff finding.
    #
    # Valid values are `llm/providers.py`'s `names()`. Nothing infers the
    # provider from which key happens to be set.
    llm_provider: str = "ollama"

    # Cloud keys. No defaults, deliberately: a credential literal in source is
    # a credential in git history. Empty means "that provider is unavailable",
    # which is a correct and supported state, not an error.
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    opencodezen_api_key: str = ""
    # Ollama's HOSTED api, which is a different thing from `llm_base_url`
    # above: that one is the local server and takes no key.
    ollamacloud_api_key: str = ""
    nvidia_api_key: str = ""

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
    # NO DEFAULT, deliberately. A credential literal in source is a credential
    # in git history, and this field held one. The target reads the same value
    # from `KAVACH_ADMIN_TOKEN` (its manifest declares `auth_env`), so the two
    # sides are configured from the environment and agree by configuration
    # rather than by a shared constant.
    #
    # Empty means the config interface is unreachable: the target answers 401
    # and the loop escalates instead of writing. That is the correct failure.
    target_admin_token: str = ""
    target_service_names: str = "backend,db,frontend,toxiproxy,prometheus"

    # Floor below which a diagnosis cannot drive a repair. Mirrors the
    # manifest's value; the RCA validator is what enforces it.
    confidence_threshold: float = 0.75

    # Dev-only browser origin for the console. Empty in production, where the
    # console is served from the same origin and CORS is unnecessary.
    console_origin: str = "http://localhost:3001"

    # Where Kavach's own files live: the fast-verification set and the
    # baseline captures. Empty means "work it out", which is right on a host
    # checkout and impossible inside the image - see `root()`.
    kavach_root: str = ""

    def target_services(self) -> list[str]:
        return [s.strip() for s in self.target_service_names.split(",") if s.strip()]

    def root(self) -> Path:
        """The directory Kavach reads its own files from.

        On a host checkout this is the repository root, three levels above this
        file. Inside the image the package sits at `/app/kavach` with no
        repository around it, so that ancestor does not exist - and deriving it
        with a fixed `parents[n]` raised IndexError on the containerised API's
        first request. Compose therefore sets `KAVACH_ROOT=/app` explicitly,
        and the fallback below keeps a bare `python -m` run working too.
        """
        if self.kavach_root:
            return Path(self.kavach_root)
        parents = Path(__file__).resolve().parents
        # parents[3] is the repo root from apps/control-plane/kavach/config.py;
        # parents[1] is the package parent when there is no repo above it.
        return parents[3] if len(parents) > 3 else parents[1]

    def baselines_dir(self) -> Path:
        return self.root() / "harness" / "baselines"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so FastAPI's Depends does not re-read the environment per request."""
    return Settings()
