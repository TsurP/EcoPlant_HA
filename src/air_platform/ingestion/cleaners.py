"""Cleaning operations for normalized sensor data."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from air_platform.ingestion.models import MissingStrategy, TableSchema


def nullify_out_of_range_values(
    dataframe: pd.DataFrame,
    table_schema: TableSchema,
) -> tuple[pd.DataFrame, int]:
    """Replace out-of-range numeric values with nulls."""

    cleaned = dataframe.copy()
    total_nullified = 0

    for column_name in table_schema.numeric_columns:
        column_schema = table_schema.columns[column_name]
        if column_schema.valid_range is None:
            continue

        min_value, max_value = column_schema.valid_range
        mask = cleaned[column_name].notna() & (
            (cleaned[column_name] < min_value) | (cleaned[column_name] > max_value)
        )
        total_nullified += int(mask.sum())
        cleaned.loc[mask, column_name] = pd.NA

    return cleaned, total_nullified


def apply_missing_strategy(
    dataframe: pd.DataFrame,
    numeric_columns: Sequence[str],
    strategy: MissingStrategy,
) -> pd.DataFrame:
    """Apply the selected missing-data strategy per device."""

    cleaned = dataframe.dropna(subset=["timestamp", "station_id", "device_id"]).copy()
    if cleaned.empty:
        return cleaned

    if strategy == MissingStrategy.DROP:
        return (
            cleaned.dropna(subset=list(numeric_columns))
            .sort_values(["device_id", "timestamp"])
            .reset_index(drop=True)
        )

    grouped_frames: list[pd.DataFrame] = []
    for _, group in cleaned.groupby("device_id", sort=False):
        ordered = group.sort_values("timestamp").copy()
        if strategy == MissingStrategy.FILL:
            # Forward-fill only: back-filling would propagate future observations
            # into earlier timestamps, making metrics time-unfaithful.
            ordered.loc[:, list(numeric_columns)] = ordered.loc[:, list(numeric_columns)].ffill()
        elif strategy == MissingStrategy.INTERPOLATE:
            # limit_direction="forward" prevents extrapolation before the first
            # known value, which would also leak future context.
            interpolated = (
                ordered.set_index("timestamp")
                .loc[:, list(numeric_columns)]
                .interpolate(method="time", limit_direction="forward")
            )
            ordered.loc[:, list(numeric_columns)] = interpolated.to_numpy()
        grouped_frames.append(ordered)

    return (
        pd.concat(grouped_frames, ignore_index=True)
        .sort_values(["device_id", "timestamp"])
        .reset_index(drop=True)
    )
