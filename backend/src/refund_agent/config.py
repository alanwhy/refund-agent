from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Refund Agent"
    environment: str = "development"
    database_url: str = "sqlite:///./refund-agent.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "local-demo-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    llm_mode: str = "fake"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    rules_dir: Path = Path("/config/rules")
    prompts_dir: Path = Path("/app/prompts")

    @field_validator("llm_mode")
    @classmethod
    def validate_llm_mode(cls, value: str) -> str:
        if value not in {"fake", "compatible"}:
            raise ValueError("LLM_MODE must be fake or compatible")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
