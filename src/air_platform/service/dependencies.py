"""FastAPI dependency providers."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request

from air_platform.config import AppSettings
from air_platform.errors import LLMNotConfiguredError
from air_platform.ingestion.pipeline import IngestionPipeline
from air_platform.ingestion.repositories.sqlite import SQLiteSensorDataRepository
from air_platform.llm.openai_provider import OpenAIProvider
from air_platform.llm.provider import LLMProvider
from air_platform.llm.use_cases import (
    AnswerNLQueryUseCase,
    GenerateDataQualityReportUseCase,
    SummarizeStationHealthUseCase,
)
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


def get_metric_repository(request: Request) -> SQLiteMetricResultRepository:
    """Return the metric results repository for the current settings."""
    settings = get_settings(request)
    return SQLiteMetricResultRepository(settings.metrics_db_path)


def get_processing_service(request: Request) -> StationProcessingService:
    settings = get_settings(request)
    pipeline = IngestionPipeline(
        repository=SQLiteSensorDataRepository(settings.sensor_db_path),
        schema_path=settings.sensor_schema_path,
    )
    metric_config = MetricConfig(
        active_rpm_threshold=settings.active_rpm_threshold,
        specific_power_flow_threshold=settings.specific_power_flow_threshold,
    )
    return StationProcessingService(
        pipeline=pipeline,
        metric_repository=get_metric_repository(request),
        default_metric_config=metric_config,
    )


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the configured LLM provider, or raise if the API key is absent."""
    settings = get_settings(request)
    if not settings.openai_api_key:
        raise LLMNotConfiguredError(
            "OPENAI_API_KEY (env: AIR_PLATFORM_OPENAI_API_KEY) is not configured. "
            "LLM endpoints require a valid OpenAI API key."
        )
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )


def get_station_summary_use_case(request: Request) -> SummarizeStationHealthUseCase:
    return SummarizeStationHealthUseCase(
        metric_repository=get_metric_repository(request),
        llm=get_llm_provider(request),
    )


def get_nl_query_use_case(request: Request) -> AnswerNLQueryUseCase:
    return AnswerNLQueryUseCase(
        metric_repository=get_metric_repository(request),
        llm=get_llm_provider(request),
    )


def get_dq_report_use_case(request: Request) -> GenerateDataQualityReportUseCase:
    settings = get_settings(request)
    pipeline = IngestionPipeline(
        repository=SQLiteSensorDataRepository(settings.sensor_db_path),
        schema_path=settings.sensor_schema_path,
    )
    return GenerateDataQualityReportUseCase(pipeline=pipeline, llm=get_llm_provider(request))
