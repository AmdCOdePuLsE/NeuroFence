from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DB
    database_url: str = "postgresql://postgres:postgres@localhost:5432/neurofence_hack"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # NeuroFence
    embedding_model: str = "all-MiniLM-L6-v2"
    contamination_threshold: float = 0.70
    isolation_enabled: bool = True


def get_settings() -> Settings:
    return Settings()
