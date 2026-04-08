"""FastAPI dependency providers."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request

from air_platform.bootstrap.container import AppContainer
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
from air_platform.repositories.errors import InMemoryErrorRepository
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
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
    """Return the metric results repository, cached on app.state after first call."""
    repo = getattr(request.app.state, "metric_repository", None)
    if not isinstance(repo, SQLiteMetricResultRepository):
        settings = get_settings(request)
        repo = SQLiteMetricResultRepository(settings.metrics_db_path)
        request.app.state.metric_repository = repo
    return repo


def _get_cached_pipeline(request: Request, settings: AppSettings) -> IngestionPipeline:
    """Return the IngestionPipeline cached on app.state (builds once, reused per request)."""
    pipeline = getattr(request.app.state, "ingestion_pipeline", None)
    if not isinstance(pipeline, IngestionPipeline):
        pipeline = IngestionPipeline(
            repository=SQLiteSensorDataRepository(settings.sensor_db_path),
            schema_path=settings.sensor_schema_path,
        )
        request.app.state.ingestion_pipeline = pipeline
    return pipeline


def get_processing_service(request: Request) -> StationProcessingService:
    svc = getattr(request.app.state, "processing_service", None)
    if not isinstance(svc, StationProcessingService):
        settings = get_settings(request)
        pipeline = _get_cached_pipeline(request, settings)
        metric_config = MetricConfig(
            active_rpm_threshold=settings.active_rpm_threshold,
            specific_power_flow_threshold=settings.specific_power_flow_threshold,
        )
        svc = StationProcessingService(
            pipeline=pipeline,
            metric_repository=get_metric_repository(request),
            default_metric_config=metric_config,
        )
        request.app.state.processing_service = svc
    return svc


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the configured LLM provider cached on app.state, or raise if key absent."""
    provider = getattr(request.app.state, "llm_provider", None)
    if not isinstance(provider, OpenAIProvider):
        settings = get_settings(request)
        if settings.openai_api_key is None:
            raise LLMNotConfiguredError(
                "OPENAI_API_KEY (env: AIR_PLATFORM_OPENAI_API_KEY) is not configured. "
                "LLM endpoints require a valid OpenAI API key."
            )
        provider = OpenAIProvider(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        request.app.state.llm_provider = provider
    return provider


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
    pipeline = _get_cached_pipeline(request, settings)
    return GenerateDataQualityReportUseCase(
        pipeline=pipeline,
        llm=get_llm_provider(request),
        resample_frequency=settings.default_resample_frequency,
        missing_strategy=settings.default_missing_strategy,
        flatline_window_minutes=settings.default_flatline_window_minutes,
    )


# ---------------------------------------------------------------------------
# Challenge 3 — event-driven container dependencies
# ---------------------------------------------------------------------------


def get_container(request: Request) -> AppContainer:
    """Return the shared AppContainer stored on app.state."""
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise RuntimeError(
            "AppContainer is not initialized. "
            "Ensure the FastAPI lifespan has run before handling requests."
        )
    return container


def get_metrics_aggregate_repo(request: Request) -> InMemoryMetricsAggregateRepository:
    return get_container(request).metrics_aggregate_repo


def get_processing_status_repo(request: Request) -> InMemoryProcessingStatusRepository:
    return get_container(request).status_repo


def get_error_repo(request: Request) -> InMemoryErrorRepository:
    return get_container(request).error_repo
