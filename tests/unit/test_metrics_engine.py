from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from air_platform.ingestion.models import (
    CleaningSummary,
    MissingStrategy,
    ProcessedDataset,
    QualityReport,
    TimeRange,
)
from air_platform.metrics.engine import MetricsEngine
from air_platform.metrics.models import MetricConfig


def test_metrics_engine_computes_expected_values() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:15:00+00:00",
                    "2024-02-01T00:30:00+00:00",
                    "2024-02-01T00:45:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 4,
            "device_id": ["device-1"] * 4,
            "discharge_pressure": [8.0, 10.0, 12.0, 14.0],
            "air_flow_rate": [0.0, 100.0, 100.0, 50.0],
            "power_consumption": [0.0, 50.0, 60.0, 30.0],
            "motor_speed": [0, 1000, 1000, 0],
            "discharge_temp": [20.0, 21.0, 22.0, 20.0],
        }
    )
    dataset = ProcessedDataset(
        station_id="station-1",
        processed_data=dataframe,
        time_range=TimeRange(
            start=datetime(2024, 2, 1, tzinfo=UTC),
            end=datetime(2024, 2, 1, 0, 45, tzinfo=UTC),
        ),
        resample_frequency="15min",
        quality_report=QualityReport(
            total_rows_read=4,
            total_rows_after_cleaning=4,
            column_missing_pct={},
            out_of_range_counts={},
            malformed_value_counts={},
        ),
        cleaning_summary=CleaningSummary(
            strategy=MissingStrategy.FILL,
            rows_before_cleaning=4,
            rows_after_cleaning=4,
            rows_after_resampling=4,
            malformed_values_coerced=0,
            out_of_range_values_nullified=0,
        ),
    )

    engine = MetricsEngine(
        MetricConfig(active_rpm_threshold=500, specific_power_flow_threshold=1.0)
    )
    metrics = {metric.metric_name: metric.metric_value for metric in engine.compute(dataset)}

    assert metrics["active_duration_hours"] == 0.5
    assert metrics["active_ratio_pct"] == 50.0
    assert metrics["average_pressure_bar"] == 11.0
    assert metrics["peak_pressure_bar"] == 14.0
    assert round(metrics["mean_specific_power_kw_per_m3h"], 2) == 0.57
    assert metrics["cycle_count"] == 1.0
    assert metrics["total_flow_volume_m3"] == 62.5


def test_metrics_engine_returns_zero_specific_power_when_all_flow_is_zero() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-02-01T00:00:00+00:00", "2024-02-01T00:15:00+00:00"],
                utc=True,
            ),
            "station_id": ["station-1"] * 2,
            "device_id": ["device-1"] * 2,
            "discharge_pressure": [8.0, 8.0],
            "air_flow_rate": [0.0, 0.0],
            "power_consumption": [50.0, 50.0],
            "motor_speed": [1000, 1000],
            "discharge_temp": [20.0, 20.0],
        }
    )
    dataset = ProcessedDataset(
        station_id="station-1",
        processed_data=dataframe,
        time_range=TimeRange(
            start=datetime(2024, 2, 1, tzinfo=UTC),
            end=datetime(2024, 2, 1, 0, 15, tzinfo=UTC),
        ),
        resample_frequency="15min",
        quality_report=QualityReport(
            total_rows_read=2,
            total_rows_after_cleaning=2,
            column_missing_pct={},
            out_of_range_counts={},
            malformed_value_counts={},
        ),
        cleaning_summary=CleaningSummary(
            strategy=MissingStrategy.FILL,
            rows_before_cleaning=2,
            rows_after_cleaning=2,
            rows_after_resampling=2,
            malformed_values_coerced=0,
            out_of_range_values_nullified=0,
        ),
    )

    engine = MetricsEngine(MetricConfig(specific_power_flow_threshold=1.0))
    metrics = {metric.metric_name: metric.metric_value for metric in engine.compute(dataset)}

    # No rows pass the flow threshold, so specific power falls back to zero
    assert metrics["mean_specific_power_kw_per_m3h"] == 0.0
    assert metrics["total_flow_volume_m3"] == 0.0


def test_metrics_engine_computes_independent_metrics_per_device() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:15:00+00:00",
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:15:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 4,
            "device_id": ["device-1", "device-1", "device-2", "device-2"],
            "discharge_pressure": [8.0, 10.0, 5.0, 5.0],
            "air_flow_rate": [100.0, 100.0, 0.0, 0.0],
            "power_consumption": [50.0, 50.0, 0.0, 0.0],
            "motor_speed": [1000, 1000, 0, 0],
            "discharge_temp": [20.0, 20.0, 18.0, 18.0],
        }
    )
    dataset = ProcessedDataset(
        station_id="station-1",
        processed_data=dataframe,
        time_range=TimeRange(
            start=datetime(2024, 2, 1, tzinfo=UTC),
            end=datetime(2024, 2, 1, 0, 15, tzinfo=UTC),
        ),
        resample_frequency="15min",
        quality_report=QualityReport(
            total_rows_read=4,
            total_rows_after_cleaning=4,
            column_missing_pct={},
            out_of_range_counts={},
            malformed_value_counts={},
        ),
        cleaning_summary=CleaningSummary(
            strategy=MissingStrategy.FILL,
            rows_before_cleaning=4,
            rows_after_cleaning=4,
            rows_after_resampling=4,
            malformed_values_coerced=0,
            out_of_range_values_nullified=0,
        ),
    )

    engine = MetricsEngine(MetricConfig(active_rpm_threshold=500))
    results = engine.compute(dataset)
    by_device = {(r.device_id, r.metric_name): r.metric_value for r in results}

    assert by_device[("device-1", "average_pressure_bar")] == 9.0
    assert by_device[("device-2", "average_pressure_bar")] == 5.0
    assert by_device[("device-1", "active_ratio_pct")] == 100.0
    assert by_device[("device-2", "active_ratio_pct")] == 0.0


def test_metrics_engine_ignores_initial_active_state_for_cycle_count() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:15:00+00:00",
                    "2024-02-01T00:30:00+00:00",
                    "2024-02-01T00:45:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 4,
            "device_id": ["device-1"] * 4,
            "discharge_pressure": [8.0, 8.0, 8.0, 8.0],
            "air_flow_rate": [10.0, 10.0, 10.0, 10.0],
            "power_consumption": [5.0, 5.0, 5.0, 5.0],
            "motor_speed": [1000, 1000, 0, 1000],
            "discharge_temp": [20.0, 20.0, 20.0, 20.0],
        }
    )
    dataset = ProcessedDataset(
        station_id="station-1",
        processed_data=dataframe,
        time_range=TimeRange(
            start=datetime(2024, 2, 1, tzinfo=UTC),
            end=datetime(2024, 2, 1, 0, 45, tzinfo=UTC),
        ),
        resample_frequency="15min",
        quality_report=QualityReport(
            total_rows_read=4,
            total_rows_after_cleaning=4,
            column_missing_pct={},
            out_of_range_counts={},
            malformed_value_counts={},
        ),
        cleaning_summary=CleaningSummary(
            strategy=MissingStrategy.FILL,
            rows_before_cleaning=4,
            rows_after_cleaning=4,
            rows_after_resampling=4,
            malformed_values_coerced=0,
            out_of_range_values_nullified=0,
        ),
    )

    engine = MetricsEngine()
    metrics = {metric.metric_name: metric.metric_value for metric in engine.compute(dataset)}

    assert metrics["cycle_count"] == 1.0
