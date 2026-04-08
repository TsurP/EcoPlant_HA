"""Application configuration."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

_VALID_MISSING_STRATEGIES = {"drop", "fill", "interpolate"}


class AppSettings(BaseSettings):
    """Runtime settings for the API service."""

    sensor_db_path: Path = DATA_DIR / "sensor_data.db"
    sensor_schema_path: Path = DATA_DIR / "sensor_schema.json"
    metrics_db_path: Path = DATA_DIR / "metrics.db"
    default_resample_frequency: str = "15min"
    default_missing_strategy: str = "fill"
    default_flatline_window_minutes: int = 30
    active_rpm_threshold: int = 500
    specific_power_flow_threshold: float = 1.0

    # LLM / OpenAI settings
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: Annotated[int, Field(ge=0)] = 3

    # Challenge 3 — event consumer settings
    consumer_error_cap: int = 100  # Max recent errors kept in memory
    # Bound the in-process event queue to apply backpressure when the consumer
    # lags behind the producer.  0 = unbounded (legacy behaviour).
    consumer_queue_maxsize: int = 10_000

    model_config = SettingsConfigDict(
        env_prefix="AIR_PLATFORM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("default_missing_strategy")
    @classmethod
    def _validate_missing_strategy(cls, v: str) -> str:
        if v not in _VALID_MISSING_STRATEGIES:
            valid = sorted(_VALID_MISSING_STRATEGIES)
            raise ValueError(f"default_missing_strategy must be one of {valid}, got {v!r}")
        return v
