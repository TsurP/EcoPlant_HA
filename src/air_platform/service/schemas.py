"""Request and response models for the FastAPI service."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from air_platform.ingestion.models import MissingStrategy, QualityReport
from air_platform.llm.use_cases import DQReportResult, NLQueryResult, StationSummaryResult
from air_platform.metrics.models import MetricResult
from air_platform.repositories.errors import ProcessingError
from air_platform.repositories.metrics_aggregate import MetricAggregate
from air_platform.repositories.processing_status import ProcessingStatus
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

    @field_validator("resample_frequency")
    @classmethod
    def validate_resample_frequency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            offset = pd.tseries.frequencies.to_offset(v)
        except ValueError:
            offset = None
        if offset is None:
            raise ValueError(
                f"Invalid resample_frequency {v!r}. "
                "Use a pandas offset string such as '1min', '5min', '15min', '1h', '1D'."
            )
        return v

    @model_validator(mode="after")
    def validate_time_range_order(self) -> ProcessStationRequest:
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be strictly before end_time")
        return self


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


# ---------------------------------------------------------------------------
# LLM endpoint schemas
# ---------------------------------------------------------------------------


class StationSummaryRequest(BaseModel):
    """Optional time window for the station health summary endpoint."""

    start_time: datetime | None = None
    end_time: datetime | None = None


class MetricSnapshotItem(BaseModel):
    """Single metric entry returned alongside a generated summary."""

    model_config = ConfigDict(from_attributes=True)

    station_id: str
    device_id: str
    metric_name: str
    metric_value: float
    unit: str
    window_start: datetime
    window_end: datetime

    @classmethod
    def from_domain(cls, metric: MetricResult) -> MetricSnapshotItem:
        return cls.model_validate(metric)


class StationSummaryResponse(BaseModel):
    """Response for the station health summary endpoint."""

    station_id: str
    start_time: datetime | None
    end_time: datetime | None
    summary: str | None
    metrics: list[MetricSnapshotItem]
    llm_failed: bool = False
    warning: str | None = None

    @classmethod
    def from_result(cls, result: StationSummaryResult) -> StationSummaryResponse:
        return cls(
            station_id=result.station_id,
            start_time=result.start_time,
            end_time=result.end_time,
            summary=result.summary,
            metrics=[MetricSnapshotItem.from_domain(m) for m in result.metrics],
            llm_failed=result.llm_failed,
            warning=result.warning,
        )


class NLQueryRequest(BaseModel):
    """Request body for the natural-language query endpoint."""

    question: str = Field(..., min_length=1, description="Plain-English question about metrics.")


class ParsedQueryResponse(BaseModel):
    """Serialised StructuredMetricQuery returned with the NL query response."""

    station_id: str | None
    device_id: str | None
    metric_name: str | None
    aggregation: str
    start_time: str | None
    end_time: str | None
    needs_clarification: bool
    clarification_message: str | None


class NLQueryResponse(BaseModel):
    """Response for the natural-language query endpoint."""

    original_question: str
    parsed_query: ParsedQueryResponse
    metric_results: list[MetricSnapshotItem]
    aggregate_value: float | None
    natural_language_answer: str | None
    llm_rendering_failed: bool = False
    warning: str | None = None

    @classmethod
    def from_result(cls, result: NLQueryResult) -> NLQueryResponse:
        pq = result.parsed_query
        return cls(
            original_question=result.original_question,
            parsed_query=ParsedQueryResponse(
                station_id=pq.station_id,
                device_id=pq.device_id,
                metric_name=pq.metric_name,
                aggregation=pq.aggregation,
                start_time=pq.start_time,
                end_time=pq.end_time,
                needs_clarification=pq.needs_clarification,
                clarification_message=pq.clarification_message,
            ),
            metric_results=[MetricSnapshotItem.from_domain(m) for m in result.metric_results],
            aggregate_value=result.aggregate_value,
            natural_language_answer=result.natural_language_answer,
            llm_rendering_failed=result.llm_rendering_failed,
            warning=result.warning,
        )


class DQReportRequest(BaseModel):
    """Optional time window for the data quality report endpoint."""

    start_time: datetime | None = None
    end_time: datetime | None = None


class DQReportResponse(BaseModel):
    """Response for the data quality report endpoint."""

    station_id: str
    start_time: datetime | None
    end_time: datetime | None
    report: str | None
    total_rows_read: int
    total_rows_after_cleaning: int
    column_missing_pct: dict[str, float]
    out_of_range_counts: dict[str, int]
    malformed_value_counts: dict[str, int]
    gap_count: int
    flatline_count: int
    warnings: list[str]
    llm_failed: bool = False
    llm_warning: str | None = None

    @classmethod
    def from_result(cls, result: DQReportResult) -> DQReportResponse:
        return cls(
            station_id=result.station_id,
            start_time=result.start_time,
            end_time=result.end_time,
            report=result.report,
            total_rows_read=result.total_rows_read,
            total_rows_after_cleaning=result.total_rows_after_cleaning,
            column_missing_pct=result.column_missing_pct,
            out_of_range_counts=result.out_of_range_counts,
            malformed_value_counts=result.malformed_value_counts,
            gap_count=result.gap_count,
            flatline_count=result.flatline_count,
            warnings=result.warnings,
            llm_failed=result.llm_failed,
            llm_warning=result.llm_warning,
        )


# ---------------------------------------------------------------------------
# Challenge 3 — stream metrics and processing status schemas
# ---------------------------------------------------------------------------


class MetricAggregateResponse(BaseModel):
    """Serialized incremental aggregate for one metric/bucket."""

    station_id: str
    device_id: str
    metric_type: str
    bucket: str
    bucket_start: datetime
    count: int
    avg: float
    min_value: float | None
    max_value: float | None
    total: float
    latest_timestamp: datetime | None

    @classmethod
    def from_domain(cls, agg: MetricAggregate) -> MetricAggregateResponse:
        return cls(
            station_id=agg.station_id,
            device_id=agg.device_id,
            metric_type=agg.metric_type,
            bucket=agg.bucket,
            bucket_start=agg.bucket_start,
            count=agg.count,
            avg=agg.avg,
            min_value=agg.min_value,
            max_value=agg.max_value,
            total=agg.total,
            latest_timestamp=agg.latest_timestamp,
        )


class ProcessingStatusResponse(BaseModel):
    """Serialized consumer processing status."""

    consumer_running: bool
    events_consumed: int
    events_processed_successfully: int
    events_malformed: int
    events_failed: int
    last_event_timestamp: datetime | None
    last_success_timestamp: datetime | None
    last_error_timestamp: datetime | None
    queue_depth: int | None

    @classmethod
    def from_domain(cls, status: ProcessingStatus) -> ProcessingStatusResponse:
        return cls(
            consumer_running=status.consumer_running,
            events_consumed=status.events_consumed,
            events_processed_successfully=status.events_processed_successfully,
            events_malformed=status.events_malformed,
            events_failed=status.events_failed,
            last_event_timestamp=status.last_event_timestamp,
            last_success_timestamp=status.last_success_timestamp,
            last_error_timestamp=status.last_error_timestamp,
            queue_depth=status.queue_depth,
        )


class ProcessingErrorResponse(BaseModel):
    """Serialized processing error record."""

    error_id: str
    error_type: str
    message: str
    event_id: str | None
    occurred_at: datetime
    detail: str | None

    @classmethod
    def from_domain(cls, error: ProcessingError) -> ProcessingErrorResponse:
        return cls(
            error_id=error.error_id,
            error_type=error.error_type,
            message=error.message,
            event_id=error.event_id,
            occurred_at=error.occurred_at,
            detail=error.detail,
        )
