"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


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
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 3

    # Challenge 3 — event consumer settings
    consumer_error_cap: int = 100  # Max recent errors kept in memory

    model_config = SettingsConfigDict(env_prefix="AIR_PLATFORM_", extra="ignore")
