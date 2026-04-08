"""End-to-end ingestion pipeline orchestration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from air_platform.errors import DataNotFoundError, ValidationError
from air_platform.ingestion.cleaners import apply_missing_strategy, nullify_out_of_range_values
from air_platform.ingestion.models import (
    CleaningSummary,
    FlatlineIssue,
    GapIssue,
    ProcessedDataset,
    ProcessingConfig,
    QualityReport,
    SensorSchema,
    TableSchema,
    TimeRange,
)
from air_platform.ingestion.quality import (
    calculate_missing_percentages,
    detect_flatlines,
    detect_timestamp_gaps,
)
from air_platform.ingestion.repositories.base import SensorDataRepository
from air_platform.ingestion.resampling import resample_sensor_data
from air_platform.ingestion.schema_loader import load_schema
from air_platform.ingestion.validators import normalize_sensor_dataframe


class IngestionPipeline:
    """Reusable ingestion pipeline independent from the API layer."""

    def __init__(self, repository: SensorDataRepository, schema_path: str | Path) -> None:
        self.repository = repository
        self.schema_path = Path(schema_path)
        self._schema = load_schema(self.schema_path)
        self._table_schema = _get_sensor_table_schema(self._schema)

    def run(self, config: ProcessingConfig) -> ProcessedDataset:
        schema = self._schema
        table_schema = self._table_schema

        raw_data = self.repository.fetch_sensor_readings(
            station_id=config.station_id,
            start_time=config.start_time,
            end_time=config.end_time,
        )
        if raw_data.empty:
            raise DataNotFoundError(f"No sensor data found for station {config.station_id}")

        station_metadata = self.repository.fetch_station_metadata(config.station_id)

        validation = normalize_sensor_dataframe(raw_data, table_schema)
        quality_frame, nullified_count = nullify_out_of_range_values(
            validation.dataframe,
            table_schema,
        )

        missing_percentages = calculate_missing_percentages(
            quality_frame,
            ["timestamp", *table_schema.numeric_columns],
        )
        gap_issues = detect_timestamp_gaps(quality_frame[["device_id", "timestamp"]])
        flatline_issues = detect_flatlines(
            quality_frame,
            numeric_columns=table_schema.numeric_columns,
            default_window_minutes=config.flatline_window_minutes,
            sensor_thresholds={
                name: schema.sensor_types[name].flatline_threshold_minutes
                for name in table_schema.numeric_columns
                if name in schema.sensor_types
            },
        )

        cleaned = apply_missing_strategy(
            quality_frame,
            numeric_columns=table_schema.numeric_columns,
            strategy=config.missing_strategy,
        )
        if cleaned.empty:
            raise ValidationError("No usable rows remain after cleaning")

        resampled = resample_sensor_data(
            cleaned,
            frequency=config.resample_frequency,
            numeric_columns=table_schema.numeric_columns,
        )
        if resampled.empty:
            raise ValidationError("No rows remain after resampling")

        quality_report = QualityReport(
            total_rows_read=len(raw_data),
            total_rows_after_cleaning=len(cleaned),
            column_missing_pct=missing_percentages,
            out_of_range_counts=validation.out_of_range_counts,
            malformed_value_counts=validation.malformed_value_counts,
            timestamp_gaps=gap_issues,
            flatline_periods=flatline_issues,
            warnings=_build_warnings(validation.out_of_range_counts, gap_issues, flatline_issues),
        )
        cleaning_summary = CleaningSummary(
            strategy=config.missing_strategy,
            rows_before_cleaning=len(quality_frame),
            rows_after_cleaning=len(cleaned),
            rows_after_resampling=len(resampled),
            malformed_values_coerced=sum(validation.malformed_value_counts.values()),
            out_of_range_values_nullified=nullified_count,
        )
        actual_range = TimeRange(
            start=_timestamp_or_none(resampled["timestamp"].min()),
            end=_timestamp_or_none(resampled["timestamp"].max()),
        )

        return ProcessedDataset(
            station_id=config.station_id,
            processed_data=resampled,
            time_range=actual_range,
            resample_frequency=config.resample_frequency,
            quality_report=quality_report,
            cleaning_summary=cleaning_summary,
            station_metadata=station_metadata,
        )


def _get_sensor_table_schema(schema: SensorSchema) -> TableSchema:
    try:
        return schema.tables["sensor_readings"]
    except KeyError as exc:
        raise ValidationError("Schema does not define sensor_readings") from exc


def _build_warnings(
    out_of_range_counts: dict[str, int],
    gap_issues: list[GapIssue],
    flatline_issues: list[FlatlineIssue],
) -> list[str]:
    warnings: list[str] = []
    out_of_range_total = sum(out_of_range_counts.values())
    if out_of_range_total > 0:
        warnings.append(f"{out_of_range_total} out-of-range values were nullified")
    if gap_issues:
        warnings.append(f"{len(gap_issues)} timestamp gaps detected")
    if flatline_issues:
        warnings.append(f"{len(flatline_issues)} flatline periods detected")
    return warnings


def _timestamp_or_none(value: object) -> datetime | None:
    if value is pd.NaT or value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return pd.Timestamp(str(value)).to_pydatetime()
