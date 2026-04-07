"""Typed ingestion domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import pandas as pd


class MissingStrategy(StrEnum):
    """Supported missing-value strategies."""

    DROP = "drop"
    FILL = "fill"
    INTERPOLATE = "interpolate"


@dataclass(frozen=True)
class TimeRange:
    """Requested or actual processing time window."""

    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class ProcessingConfig:
    """Configuration for a single processing run."""

    station_id: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    resample_frequency: str = "15min"
    missing_strategy: MissingStrategy = MissingStrategy.FILL
    flatline_window_minutes: int = 30


@dataclass(frozen=True)
class ColumnSchema:
    """Single column description from the JSON schema."""

    name: str
    data_type: str
    required: bool
    valid_range: tuple[float, float] | None = None
    unit: str | None = None
    description: str = ""


@dataclass(frozen=True)
class SensorTypeSchema:
    """Sensor-specific configuration from the JSON schema."""

    name: str
    flatline_threshold_minutes: int | None = None
    typical_operating_range: tuple[float, float] | None = None


@dataclass(frozen=True)
class TableSchema:
    """Schema definition for a source table."""

    name: str
    columns: dict[str, ColumnSchema]

    @property
    def required_columns(self) -> list[str]:
        return [name for name, column in self.columns.items() if column.required]

    @property
    def numeric_columns(self) -> list[str]:
        return [
            name
            for name, column in self.columns.items()
            if column.data_type in {"float", "integer"}
        ]


@dataclass(frozen=True)
class SensorSchema:
    """Parsed schema document."""

    version: str
    tables: dict[str, TableSchema]
    sensor_types: dict[str, SensorTypeSchema]


@dataclass(frozen=True)
class StationMetadata:
    """Static station details."""

    station_id: str
    station_name: str
    location: str
    commissioned_date: str
    num_compressors: int


@dataclass(frozen=True)
class GapIssue:
    """Detected gap in time-series data."""

    device_id: str
    gap_start: datetime
    gap_end: datetime
    missing_intervals: int


@dataclass(frozen=True)
class FlatlineIssue:
    """Detected flatline period for a sensor signal."""

    device_id: str
    column: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    value: float | int


@dataclass(frozen=True)
class ValidationResult:
    """Normalized data and validation findings."""

    dataframe: pd.DataFrame
    malformed_value_counts: dict[str, int]
    out_of_range_counts: dict[str, int]


@dataclass(frozen=True)
class CleaningSummary:
    """Summary of the cleaning pass."""

    strategy: MissingStrategy
    rows_before_cleaning: int
    rows_after_cleaning: int
    rows_after_resampling: int
    malformed_values_coerced: int
    out_of_range_values_nullified: int

    @property
    def rows_removed(self) -> int:
        return self.rows_before_cleaning - self.rows_after_cleaning


@dataclass(frozen=True)
class QualityReport:
    """Aggregated data quality findings."""

    total_rows_read: int
    total_rows_after_cleaning: int
    column_missing_pct: dict[str, float]
    out_of_range_counts: dict[str, int]
    malformed_value_counts: dict[str, int]
    timestamp_gaps: list[GapIssue] = field(default_factory=list)
    flatline_periods: list[FlatlineIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_rows_read": self.total_rows_read,
            "total_rows_after_cleaning": self.total_rows_after_cleaning,
            "column_missing_pct": self.column_missing_pct,
            "out_of_range_counts": self.out_of_range_counts,
            "malformed_value_counts": self.malformed_value_counts,
            "timestamp_gaps": [
                {
                    "device_id": issue.device_id,
                    "gap_start": issue.gap_start.isoformat(),
                    "gap_end": issue.gap_end.isoformat(),
                    "missing_intervals": issue.missing_intervals,
                }
                for issue in self.timestamp_gaps
            ],
            "flatline_periods": [
                {
                    "device_id": issue.device_id,
                    "column": issue.column,
                    "start_time": issue.start_time.isoformat(),
                    "end_time": issue.end_time.isoformat(),
                    "duration_minutes": issue.duration_minutes,
                    "value": issue.value,
                }
                for issue in self.flatline_periods
            ],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class ProcessedDataset:
    """Output contract for the ingestion pipeline."""

    station_id: str
    processed_data: pd.DataFrame
    time_range: TimeRange
    resample_frequency: str
    quality_report: QualityReport
    cleaning_summary: CleaningSummary
    station_metadata: StationMetadata | None = None

    @property
    def rows(self) -> int:
        return len(self.processed_data)

    @property
    def device_ids(self) -> list[str]:
        values = self.processed_data["device_id"].dropna().astype(str).unique().tolist()
        values.sort()
        return values
