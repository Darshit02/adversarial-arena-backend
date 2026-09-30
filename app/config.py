"""Application settings using Pydantic Settings v2."""

from functools import lru_cache
from typing import Any, Literal

from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for Adversarial Arena backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_ENV: Literal["development", "production", "test"] = "development"
    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    APP_NAME: str = "Adversarial Arena Backend"
    APP_DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    API_BASE_PATH: str = "/api/v1"
    API_V1_PREFIX: str = "/api/v1"

    # Security & Encryption
    # 32-byte url-safe base64 key
    ENCRYPTION_KEY: str = "2j8S9k_wwrYCfONyKkMNUmsik6l3Xm-uIWEkS6ENLjY="
    FERNET_KEY: str | None = None
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 60
    RATE_LIMIT_RUNS_PER_MINUTE: int = 10

    # Clerk Authentication
    CLERK_SECRET_KEY: str = "sk_test_xxx"
    CLERK_JWKS_URL: str = "https://your-app.clerk.accounts.dev/.well-known/jwks.json"
    CLERK_ISSUER: str = "https://your-app.clerk.accounts.dev"
    CLERK_AUDIENCE: str | None = None
    CLERK_WEBHOOK_SECRET: str = "whsec_test_secret"
    JWKS_CACHE_TTL_SECONDS: int = 3600  # 1 hour cache in Redis

    # Database (PostgreSQL 16 via asyncpg)
    POSTGRES_USER: str = "arena_user"
    POSTGRES_PASSWORD: str = "arena_secure_password"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "adversarial_arena"
    DATABASE_URL: str = (
        "postgresql+asyncpg://arena_user:arena_secure_password@postgres:5432/adversarial_arena"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30

    # Redis 7
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://redis:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    CELERY_TASK_TIME_LIMIT: int = 1800  # 30 minutes
    CELERY_TASK_ACKS_LATE: bool = True
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1

    # External LLM Providers & Local Model Defaults
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://ollama:11434"

    # Observability & Logging
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    REDACT_PROMPTS_IN_LOGS: bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    SENTRY_DSN: str | None = None
    METRICS_USER: str = ""
    METRICS_PASSWORD: str = ""

    # Report Artifact Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_DIR: str = "/tmp/arena_reports"
    S3_BUCKET_NAME: str | None = None
    S3_REGION: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="before")
    @classmethod
    def sync_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("FERNET_KEY"):
                data["ENCRYPTION_KEY"] = data["FERNET_KEY"]
            if "API_BASE_PATH" in data and "API_V1_PREFIX" not in data:
                data["API_V1_PREFIX"] = data["API_BASE_PATH"]
            if "ENVIRONMENT" in data and "APP_ENV" not in data:
                env_map = {"dev": "development", "staging": "development", "prod": "production"}
                data["APP_ENV"] = env_map.get(data["ENVIRONMENT"], "development")
        return data

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_fernet_key(cls, v: str) -> str:
        """Ensure encryption key is a valid Fernet key."""
        try:
            Fernet(v.encode())
        except Exception as e:
            raise ValueError(
                f"ENCRYPTION_KEY must be a valid 32-byte url-safe base64 string: {e}"
            ) from e
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "prod" or self.APP_ENV == "production"

    @property
    def is_test(self) -> bool:
        return self.APP_ENV == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton accessor for application settings."""
    return Settings()


# Module-level singleton instance
settings = get_settings()
