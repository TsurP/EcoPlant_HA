"""API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from air_platform.config import AppSettings
from air_platform.ingestion.models import MissingStrategy, ProcessingConfig
from air_platform.metrics.models import MetricConfig, MetricQuery
from air_platform.service.dependencies import get_processing_service, get_settings
from air_platform.service.orchestrator import StationProcessingService
from air_platform.service.schemas import (
    HealthResponse,
    MetricResponse,
    ProcessStationRequest,
    ProcessStationResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    """Simple health endpoint."""

    return HealthResponse()


@router.post("/stations/{station_id}/process", response_model=ProcessStationResponse)
def process_station(
    station_id: str,
    request: ProcessStationRequest | None = None,
    service: StationProcessingService = Depends(get_processing_service),
    settings: AppSettings = Depends(get_settings),
) -> ProcessStationResponse:
    """Process a station, compute metrics, and persist results."""

    payload = request or ProcessStationRequest()
    processing_config = ProcessingConfig(
        station_id=station_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        resample_frequency=payload.resample_frequency or settings.default_resample_frequency,
        missing_strategy=(
            payload.missing_strategy or MissingStrategy(settings.default_missing_strategy)
        ),
        flatline_window_minutes=(
            payload.flatline_window_minutes
            if payload.flatline_window_minutes is not None
            else settings.default_flatline_window_minutes
        ),
    )
    metric_config = MetricConfig(
        active_rpm_threshold=(
            payload.active_rpm_threshold
            if payload.active_rpm_threshold is not None
            else settings.active_rpm_threshold
        ),
        specific_power_flow_threshold=(
            payload.specific_power_flow_threshold
            if payload.specific_power_flow_threshold is not None
            else settings.specific_power_flow_threshold
        ),
    )
    summary = service.process_station(processing_config, metric_config)
    return ProcessStationResponse.from_summary(summary)


@router.get("/metrics", response_model=list[MetricResponse])
def get_metrics(
    station_id: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    metric_name: str | None = Query(default=None),
    service: StationProcessingService = Depends(get_processing_service),
) -> list[MetricResponse]:
    """Retrieve previously computed metrics with optional filters."""

    query = MetricQuery(
        station_id=station_id,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        metric_name=metric_name,
    )
    return [MetricResponse.from_domain(metric) for metric in service.get_metrics(query)]
