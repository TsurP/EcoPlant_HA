"""Request and response models for the FastAPI service."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from air_platform.ingestion.models import MissingStrategy, QualityReport
from air_platform.metrics.models import MetricResult
from air_platform.service.orchestrator import StationProcessingSummary


class ProcessStationRequest(BaseModel):
    """Optional overrides for processing a station."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    resample_frequency: str | None = None
    missing_strategy: MissingStrategy | None = None
    flatline_window_minutes: int | None = Field(default=None, ge=1)
    active_rpm_threshold: int | None = Field(default=None, ge=0)
    specific_power_flow_threshold: float | None = Field(default=None, ge=0.0)


class GapIssueResponse(BaseModel):
    """Serialized gap issue."""

    device_id: str
    gap_start: datetime
    gap_end: datetime
    missing_intervals: int


class FlatlineIssueResponse(BaseModel):
    """Serialized flatline issue."""

    device_id: str
    column: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    value: float | int


class QualityReportResponse(BaseModel):
    """Serialized quality report."""

    total_rows_read: int
    total_rows_after_cleaning: int
    column_missing_pct: dict[str, float]
    out_of_range_counts: dict[str, int]
    malformed_value_counts: dict[str, int]
    timestamp_gaps: list[GapIssueResponse]
    flatline_periods: list[FlatlineIssueResponse]
    warnings: list[str]

    @classmethod
    def from_domain(cls, report: QualityReport) -> QualityReportResponse:
        payload = report.to_dict()
        return cls.model_validate(payload)


class TimeRangeResponse(BaseModel):
    """Serialized processing window."""

    start: datetime | None
    end: datetime | None


class ProcessStationResponse(BaseModel):
    """Summary returned after processing a station."""

    station_id: str
    station_name: str | None = None
    rows_read: int
    rows_after_cleaning: int
    rows_after_resampling: int
    devices_processed: int
    metrics_saved: int
    resample_frequency: str
    missing_strategy: MissingStrategy
    time_range: TimeRangeResponse
    quality_report: QualityReportResponse

    @classmethod
    def from_summary(cls, summary: StationProcessingSummary) -> ProcessStationResponse:
        dataset = summary.dataset
        return cls(
            station_id=dataset.station_id,
            station_name=(
                dataset.station_metadata.station_name if dataset.station_metadata else None
            ),
            rows_read=dataset.quality_report.total_rows_read,
            rows_after_cleaning=dataset.quality_report.total_rows_after_cleaning,
            rows_after_resampling=dataset.cleaning_summary.rows_after_resampling,
            devices_processed=len(dataset.device_ids),
            metrics_saved=summary.metrics_saved,
            resample_frequency=dataset.resample_frequency,
            missing_strategy=dataset.cleaning_summary.strategy,
            time_range=TimeRangeResponse(
                start=dataset.time_range.start,
                end=dataset.time_range.end,
            ),
            quality_report=QualityReportResponse.from_domain(dataset.quality_report),
        )


class MetricResponse(BaseModel):
    """Serialized metric row."""

    model_config = ConfigDict(from_attributes=True)

    station_id: str
    device_id: str
    metric_name: str
    metric_value: float
    unit: str
    window_start: datetime
    window_end: datetime
    computed_at: datetime
    resample_frequency: str
    missing_strategy: str

    @classmethod
    def from_domain(cls, metric: MetricResult) -> MetricResponse:
        return cls.model_validate(metric)


class HealthResponse(BaseModel):
    """Health endpoint payload."""

    status: str = "ok"
