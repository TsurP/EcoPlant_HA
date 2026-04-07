from __future__ import annotations

import pandas as pd

from air_platform.ingestion.cleaners import apply_missing_strategy
from air_platform.ingestion.models import MissingStrategy


def test_fill_strategy_forward_and_backward_fills_per_device() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:01:00+00:00",
                    "2024-02-01T00:02:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 3,
            "device_id": ["device-1"] * 3,
            "discharge_pressure": [None, 7.0, None],
        }
    )

    cleaned = apply_missing_strategy(dataframe, ["discharge_pressure"], MissingStrategy.FILL)

    assert cleaned["discharge_pressure"].tolist() == [7.0, 7.0, 7.0]


def test_interpolate_strategy_interpolates_over_time() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                    "2024-02-01T00:20:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 3,
            "device_id": ["device-1"] * 3,
            "discharge_pressure": [0.0, None, 20.0],
        }
    )

    cleaned = apply_missing_strategy(
        dataframe,
        ["discharge_pressure"],
        MissingStrategy.INTERPOLATE,
    )

    assert cleaned["discharge_pressure"].tolist() == [0.0, 10.0, 20.0]


def test_drop_strategy_removes_rows_with_missing_sensor_values() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:01:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1", "station-1"],
            "device_id": ["device-1", "device-1"],
            "discharge_pressure": [7.0, None],
        }
    )

    cleaned = apply_missing_strategy(dataframe, ["discharge_pressure"], MissingStrategy.DROP)

    assert len(cleaned) == 1
