from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from air_platform.metrics.models import MetricQuery, MetricResult
from air_platform.storage.sqlite import SQLiteMetricResultRepository


def test_metric_storage_round_trip_with_filters(tmp_path: Path) -> None:
    repository = SQLiteMetricResultRepository(tmp_path / "metrics.db")
    metric = MetricResult(
        station_id="station-1",
        device_id="device-1",
        metric_name="average_pressure_bar",
        metric_value=9.5,
        unit="bar",
        window_start=datetime(2024, 2, 1, tzinfo=UTC),
        window_end=datetime(2024, 2, 1, 1, tzinfo=UTC),
        computed_at=datetime(2024, 2, 2, tzinfo=UTC),
        resample_frequency="15min",
        missing_strategy="fill",
    )

    repository.save_metric_results([metric])
    results = repository.get_metric_results(
        MetricQuery(
            station_id="station-1",
            metric_name="average_pressure_bar",
            start_time=datetime(2024, 2, 1, tzinfo=UTC),
            end_time=datetime(2024, 2, 1, 2, tzinfo=UTC),
        )
    )

    assert len(results) == 1
    assert results[0].metric_value == 9.5
