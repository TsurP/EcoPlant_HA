"""Unit tests for the in-memory metrics aggregate repository."""

from __future__ import annotations

from datetime import UTC, datetime

from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository

_STATION = "station-1"
_DEVICE = "device-a"
_METRIC = "discharge_pressure"
_BUCKET = "hour"
_BUCKET_START = datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC)
_TS = datetime(2024, 2, 1, 10, 5, 0, tzinfo=UTC)


def _make_repo() -> InMemoryMetricsAggregateRepository:
    return InMemoryMetricsAggregateRepository()


class TestUpsertAggregate:
    def test_first_insert_creates_aggregate(self):
        repo = _make_repo()
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, _BUCKET, _BUCKET_START, 8.5, _TS)
        results = repo.query(_STATION)
        assert len(results) == 1
        agg = results[0]
        assert agg.count == 1
        assert agg.avg == 8.5
        assert agg.min_value == 8.5
        assert agg.max_value == 8.5
        assert agg.total == 8.5

    def test_second_insert_updates_running_average(self):
        repo = _make_repo()
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, _BUCKET, _BUCKET_START, 8.0, _TS)
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, _BUCKET, _BUCKET_START, 10.0, _TS)
        agg = repo.query(_STATION)[0]
        assert agg.count == 2
        assert agg.avg == 9.0
        assert agg.min_value == 8.0
        assert agg.max_value == 10.0
        assert agg.total == 18.0

    def test_min_and_max_tracked_correctly(self):
        repo = _make_repo()
        for v in [5.0, 3.0, 7.0, 1.0, 6.0]:
            repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, _BUCKET, _BUCKET_START, v, _TS)
        agg = repo.query(_STATION)[0]
        assert agg.min_value == 1.0
        assert agg.max_value == 7.0

    def test_latest_timestamp_updated(self):
        repo = _make_repo()
        ts1 = datetime(2024, 2, 1, 10, 5, 0, tzinfo=UTC)
        ts2 = datetime(2024, 2, 1, 10, 30, 0, tzinfo=UTC)
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, _BUCKET, _BUCKET_START, 8.0, ts1)
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, _BUCKET, _BUCKET_START, 9.0, ts2)
        agg = repo.query(_STATION)[0]
        assert agg.latest_timestamp == ts2

    def test_different_buckets_stored_separately(self):
        repo = _make_repo()
        hour_start = datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC)
        day_start = datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, "hour", hour_start, 8.0, _TS)
        repo.upsert_aggregate(_STATION, _DEVICE, _METRIC, "day", day_start, 8.0, _TS)
        results = repo.query(_STATION)
        assert len(results) == 2

    def test_different_devices_stored_separately(self):
        repo = _make_repo()
        repo.upsert_aggregate(_STATION, "device-a", _METRIC, _BUCKET, _BUCKET_START, 8.0, _TS)
        repo.upsert_aggregate(_STATION, "device-b", _METRIC, _BUCKET, _BUCKET_START, 9.0, _TS)
        results = repo.query(_STATION)
        assert len(results) == 2


class TestQuery:
    def _populated_repo(self) -> InMemoryMetricsAggregateRepository:
        repo = _make_repo()
        hour_start = datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC)
        hour_start_2 = datetime(2024, 2, 1, 11, 0, 0, tzinfo=UTC)
        day_start = datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)
        ts = datetime(2024, 2, 1, 10, 5, 0, tzinfo=UTC)

        for device in ("device-a", "device-b"):
            for metric in ("discharge_pressure", "motor_speed"):
                repo.upsert_aggregate(_STATION, device, metric, "hour", hour_start, 8.0, ts)
                repo.upsert_aggregate(_STATION, device, metric, "hour", hour_start_2, 9.0, ts)
                repo.upsert_aggregate(_STATION, device, metric, "day", day_start, 8.5, ts)
        return repo

    def test_filter_by_device(self):
        repo = self._populated_repo()
        results = repo.query(_STATION, device_id="device-a")
        assert all(r.device_id == "device-a" for r in results)

    def test_filter_by_metric_type(self):
        repo = self._populated_repo()
        results = repo.query(_STATION, metric_type="motor_speed")
        assert all(r.metric_type == "motor_speed" for r in results)

    def test_filter_by_bucket(self):
        repo = self._populated_repo()
        results = repo.query(_STATION, bucket="day")
        assert all(r.bucket == "day" for r in results)

    def test_filter_by_time_range(self):
        repo = self._populated_repo()
        start = datetime(2024, 2, 1, 11, 0, 0, tzinfo=UTC)
        end = datetime(2024, 2, 1, 12, 0, 0, tzinfo=UTC)
        results = repo.query(_STATION, bucket="hour", start_time=start, end_time=end)
        assert all(r.bucket_start >= start for r in results)
        assert all(r.bucket_start < end for r in results)

    def test_wrong_station_returns_empty(self):
        repo = self._populated_repo()
        results = repo.query("other-station")
        assert results == []

    def test_returns_empty_when_no_data(self):
        repo = _make_repo()
        assert repo.query(_STATION) == []
