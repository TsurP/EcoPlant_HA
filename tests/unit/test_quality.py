from __future__ import annotations

import pandas as pd

from air_platform.ingestion.quality import (
    detect_flatlines,
    detect_timestamp_gaps,
    infer_expected_interval,
)


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


def test_detect_timestamp_gaps_does_not_report_normal_intervals() -> None:
    dataframe = pd.DataFrame(
        {
            "device_id": ["device-1"] * 3,
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:05:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                ],
                utc=True,
            ),
        }
    )

    issues = detect_timestamp_gaps(dataframe)

    assert issues == []


def test_detect_timestamp_gaps_handles_multiple_devices_independently() -> None:
    dataframe = pd.DataFrame(
        {
            "device_id": ["dev-A", "dev-A", "dev-A", "dev-B", "dev-B", "dev-B"],
            "timestamp": pd.to_datetime(
                [
                    # dev-A: regular 5-min, then a 15-min gap (2 missing intervals)
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:05:00+00:00",
                    "2024-02-01T00:20:00+00:00",
                    # dev-B: regular 5-min interval throughout, no gap
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:05:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                ],
                utc=True,
            ),
        }
    )

    issues = detect_timestamp_gaps(dataframe)

    device_ids = {issue.device_id for issue in issues}
    assert device_ids == {"dev-A"}


def test_detect_timestamp_gaps_returns_empty_for_single_row_device() -> None:
    dataframe = pd.DataFrame(
        {
            "device_id": ["device-1"],
            "timestamp": pd.to_datetime(["2024-02-01T00:00:00+00:00"], utc=True),
        }
    )

    issues = detect_timestamp_gaps(dataframe)

    assert issues == []


def test_infer_expected_interval_breaks_ties_by_shorter_interval() -> None:
    # Two intervals each appearing once — tie should resolve to the shorter one.
    timestamps = pd.to_datetime(
        [
            "2024-02-01T00:00:00+00:00",
            "2024-02-01T00:05:00+00:00",  # +5 min
            "2024-02-01T00:15:00+00:00",  # +10 min
        ],
        utc=True,
    ).tolist()

    result = infer_expected_interval(timestamps)

    assert result == pd.Timedelta(minutes=5)


def test_detect_flatlines_does_not_flag_short_constant_period() -> None:
    dataframe = pd.DataFrame(
        {
            "device_id": ["device-1"] * 3,
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:05:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                ],
                utc=True,
            ),
            "discharge_pressure": [7.5, 7.5, 7.5],
        }
    )

    issues = detect_flatlines(
        dataframe,
        numeric_columns=["discharge_pressure"],
        default_window_minutes=30,
    )

    assert issues == []


def test_detect_flatlines_returns_empty_for_empty_dataframe() -> None:
    issues = detect_flatlines(
        pd.DataFrame(),
        numeric_columns=["discharge_pressure"],
        default_window_minutes=30,
    )

    assert issues == []
