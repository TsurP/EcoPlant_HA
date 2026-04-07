"""FastAPI dependency providers."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request

from air_platform.config import AppSettings
from air_platform.ingestion.pipeline import IngestionPipeline
from air_platform.ingestion.repositories.sqlite import SQLiteSensorDataRepository
from air_platform.metrics.models import MetricConfig
from air_platform.service.orchestrator import StationProcessingService
from air_platform.storage.sqlite import SQLiteMetricResultRepository


@lru_cache(maxsize=1)
def _default_settings() -> AppSettings:
    return AppSettings()


def get_settings(request: Request) -> AppSettings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, AppSettings):
        return settings
    settings = _default_settings()
    request.app.state.settings = settings
    return settings


def get_processing_service(request: Request) -> StationProcessingService:
    settings = get_settings(request)
    pipeline = IngestionPipeline(
        repository=SQLiteSensorDataRepository(settings.sensor_db_path),
        schema_path=settings.sensor_schema_path,
    )
    metric_repository = SQLiteMetricResultRepository(settings.metrics_db_path)
    metric_config = MetricConfig(
        active_rpm_threshold=settings.active_rpm_threshold,
        specific_power_flow_threshold=settings.specific_power_flow_threshold,
    )
    return StationProcessingService(
        pipeline=pipeline,
        metric_repository=metric_repository,
        default_metric_config=metric_config,
    )
