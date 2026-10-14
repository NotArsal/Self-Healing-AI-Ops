from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Kavach Autonomous AI Operations Platform"
    version: str = "0.1.0"

    # Path to the onboarded application's kavach.yaml. Detection is off when unset,
    # so the control plane never probes a target nobody asked it to watch.
    target_manifest: str | None = None
    detection_interval_s: int = 15
    debt_interval_s: int = 60
    # SIMULATION writes nothing. Anything else permits live side effects, so the
    # default stays the safe one.
    execution_mode: str = "SIMULATION"


settings = Settings()
