"""Data quality checks for time-series sensor data."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from air_platform.ingestion.models import FlatlineIssue, GapIssue


def calculate_missing_percentages(
    dataframe: pd.DataFrame,
    columns: Sequence[str],
) -> dict[str, float]:
    """Calculate per-column missing-value percentages."""

    if dataframe.empty:
        return {column: 0.0 for column in columns}

    total_rows = len(dataframe)
    return {
        column: round(float(dataframe[column].isna().sum()) / float(total_rows) * 100.0, 2)
        for column in columns
    }


def detect_timestamp_gaps(dataframe: pd.DataFrame) -> list[GapIssue]:
    """Find gaps between consecutive timestamps for each device."""

    issues: list[GapIssue] = []
    if dataframe.empty:
        return issues

    for device_id, group in dataframe.dropna(subset=["timestamp"]).groupby("device_id"):
        ordered = group.sort_values("timestamp").reset_index(drop=True)
        timestamps = _coerce_timestamps(ordered["timestamp"].tolist())
        expected_interval = infer_expected_interval(timestamps)
        if expected_interval is None:
            continue

        for index in range(1, len(timestamps)):
            diff = timestamps[index] - timestamps[index - 1]
            if diff <= expected_interval:
                continue

            missing_intervals = max(int(round(diff / expected_interval)) - 1, 1)
            issues.append(
                GapIssue(
                    device_id=str(device_id),
                    gap_start=timestamps[index - 1].to_pydatetime(),
                    gap_end=timestamps[index].to_pydatetime(),
                    missing_intervals=missing_intervals,
                )
            )

    return issues


def infer_expected_interval(timestamps: Sequence[pd.Timestamp]) -> pd.Timedelta | None:
    """Infer the most common positive interval in a timestamp series."""

    if len(timestamps) < 2:
        return None

    diffs = [
        timestamps[index] - timestamps[index - 1]
        for index in range(1, len(timestamps))
        if timestamps[index] > timestamps[index - 1]
    ]
    if not diffs:
        return None

    counts: dict[pd.Timedelta, int] = {}
    for diff in diffs:
        counts[diff] = counts.get(diff, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


def detect_flatlines(
    dataframe: pd.DataFrame,
    numeric_columns: Sequence[str],
    default_window_minutes: int,
    sensor_thresholds: dict[str, int | None] | None = None,
) -> list[FlatlineIssue]:
    """Detect consecutive flatline periods for each numeric column."""

    issues: list[FlatlineIssue] = []
    if dataframe.empty:
        return issues

    thresholds = sensor_thresholds or {}
    for device_id, group in dataframe.dropna(subset=["timestamp"]).groupby("device_id"):
        ordered = group.sort_values("timestamp")
        for column in numeric_columns:
            series = ordered[["timestamp", column]].dropna()
            if len(series) < 2:
                continue

            run_ids = series[column].ne(series[column].shift()).cumsum()
            threshold = thresholds.get(column) or default_window_minutes
            for _, run in series.groupby(run_ids):
                if len(run) < 2:
                    continue

                start_time = pd.Timestamp(run["timestamp"].iloc[0])
                end_time = pd.Timestamp(run["timestamp"].iloc[-1])
                duration_minutes = (end_time - start_time).total_seconds() / 60.0
                if duration_minutes < float(threshold):
                    continue

                issues.append(
                    FlatlineIssue(
                        device_id=str(device_id),
                        column=column,
                        start_time=start_time.to_pydatetime(),
                        end_time=end_time.to_pydatetime(),
                        duration_minutes=duration_minutes,
                        value=float(run[column].iloc[0]),
                    )
                )

    return issues


def _coerce_timestamps(values: Sequence[object]) -> list[pd.Timestamp]:
    timestamps: list[pd.Timestamp] = []
    for value in values:
        coerced = pd.Timestamp(str(value))
        if not pd.isna(coerced):
            timestamps.append(coerced)
    return timestamps
