from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Refund Agent"
    environment: str = "development"
    database_url: str = "sqlite:///./refund-agent.db"
    redis_url: str = "redis://localhost:6379/0"
    service_role: str = "api"
    jwt_secret: str = "local-demo-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    agent_max_steps: int = 6
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    rules_dir: Path = Path("/config/rules")
    prompts_dir: Path = Path("/app/prompts")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def checkpoint_database_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def require_model_config(self) -> tuple[str, str, str]:
        key = self.llm_api_key.get_secret_value() if self.llm_api_key else ""
        if not self.llm_base_url or not key or not self.llm_model:
            raise ValueError("LLM_BASE_URL, LLM_API_KEY and LLM_MODEL are required")
        return self.llm_base_url, key, self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
