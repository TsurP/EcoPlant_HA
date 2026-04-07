from __future__ import annotations

import pandas as pd

from air_platform.ingestion.quality import detect_flatlines, detect_timestamp_gaps


def test_detect_timestamp_gaps_reports_missing_intervals() -> None:
    dataframe = pd.DataFrame(
        {
            "device_id": ["device-1", "device-1", "device-1"],
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:01:00+00:00",
                    "2024-02-01T00:04:00+00:00",
                ],
                utc=True,
            ),
        }
    )

    issues = detect_timestamp_gaps(dataframe)

    assert len(issues) == 1
    assert issues[0].missing_intervals == 2


def test_detect_flatlines_reports_long_constant_periods() -> None:
    dataframe = pd.DataFrame(
        {
            "device_id": ["device-1"] * 5,
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                    "2024-02-01T00:20:00+00:00",
                    "2024-02-01T00:30:00+00:00",
                    "2024-02-01T00:40:00+00:00",
                ],
                utc=True,
            ),
            "discharge_pressure": [7.5, 7.5, 7.5, 7.5, 7.5],
        }
    )

    issues = detect_flatlines(
        dataframe,
        numeric_columns=["discharge_pressure"],
        default_window_minutes=30,
    )

    assert len(issues) == 1
    assert issues[0].column == "discharge_pressure"
    assert issues[0].duration_minutes == 40.0
