"""
Application configuration via pydantic-settings.
All config read from environment variables with sensible defaults for local dev.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # App
    app_name: str = "overplanned-api"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", pattern=r"^(development|staging|production)$")
    debug: bool = False

    # Database
    database_url: str = Field(default="postgresql://overplanned:overplanned_dev@localhost:16432/overplanned")

    # Redis
    redis_url: str = Field(default="redis://:overplanned_dev@localhost:16379/0")

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "https://overplanned.app"]
    )

    # Sentry
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)

    # Rate Limiting
    rate_limit_anon_per_min: int = 10
    rate_limit_auth_per_min: int = 60
    rate_limit_llm_per_min: int = 5
    rate_limit_events_per_min: int = 60

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = ""

    # Search
    search_score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # Events
    events_batch_max_size: int = 1000
    events_request_max_bytes: int = 1_048_576  # 1MB

    # Anthropic
    anthropic_api_key: str = ""

    # Generation
    generation_candidate_pool_size: int = 30
    generation_llm_timeout_s: float = 5.0

    # Weather (OpenWeatherMap)
    # Free tier: 1,000 calls/day. Redis caching (1 hour per city) keeps usage well under budget.
    openweathermap_api_key: str = ""
    weather_api_timeout_s: float = 8.0

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
