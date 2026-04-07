"""Validation and normalization for raw sensor data."""

from __future__ import annotations

import pandas as pd

from air_platform.errors import ValidationError
from air_platform.ingestion.models import TableSchema, ValidationResult


def validate_required_columns(dataframe: pd.DataFrame, table_schema: TableSchema) -> None:
    """Ensure all required columns are present."""

    missing_columns = [
        column_name
        for column_name in table_schema.required_columns
        if column_name not in dataframe.columns
    ]
    if missing_columns:
        joined = ", ".join(sorted(missing_columns))
        raise ValidationError(f"Missing required columns: {joined}")


def normalize_sensor_dataframe(
    dataframe: pd.DataFrame,
    table_schema: TableSchema,
) -> ValidationResult:
    """Normalize raw data types and collect validation counts."""

    validate_required_columns(dataframe, table_schema)

    normalized = dataframe.copy()
    malformed_counts: dict[str, int] = {}
    out_of_range_counts: dict[str, int] = {}

    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce", utc=True)
    malformed_counts["timestamp"] = int(normalized["timestamp"].isna().sum())
    if normalized["timestamp"].notna().sum() == 0:
        raise ValidationError("All timestamps are unreadable")

    for column_name, column_schema in table_schema.columns.items():
        if column_name not in normalized.columns or column_name == "timestamp":
            continue

        if column_schema.data_type in {"float", "integer"}:
            original = normalized[column_name]
            coerced = pd.to_numeric(original, errors="coerce")
            malformed_counts[column_name] = int(original.notna().sum() - coerced.notna().sum())
            normalized[column_name] = coerced

            if column_schema.valid_range is not None:
                min_value, max_value = column_schema.valid_range
                out_of_range_mask = coerced.notna() & (
                    (coerced < min_value) | (coerced > max_value)
                )
                out_of_range_counts[column_name] = int(out_of_range_mask.sum())
            else:
                out_of_range_counts[column_name] = 0
        else:
            normalized[column_name] = normalized[column_name].astype("string")
            malformed_counts[column_name] = 0
            out_of_range_counts[column_name] = 0

    normalized = normalized.sort_values(["device_id", "timestamp"]).reset_index(drop=True)
    return ValidationResult(
        dataframe=normalized,
        malformed_value_counts=malformed_counts,
        out_of_range_counts=out_of_range_counts,
    )
