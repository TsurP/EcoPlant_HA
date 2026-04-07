"""Resampling utilities for processed sensor data."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def resample_sensor_data(
    dataframe: pd.DataFrame,
    frequency: str,
    numeric_columns: Sequence[str],
) -> pd.DataFrame:
    """Resample numeric sensor values per station and device."""

    if dataframe.empty:
        return dataframe.copy()

    resampled = (
        dataframe.sort_values("timestamp")
        .groupby(["station_id", "device_id"])
        .resample(frequency, on="timestamp")[list(numeric_columns)]
        .mean()
        .reset_index()
    )
    return (
        resampled.dropna(subset=list(numeric_columns), how="all")
        .sort_values(["device_id", "timestamp"])
        .reset_index(drop=True)
    )
