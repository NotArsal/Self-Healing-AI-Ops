from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Kavach Autonomous AI Operations Platform"
    version: str = "0.1.0"


settings = Settings()
