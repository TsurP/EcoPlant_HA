"""Unit tests for the in-memory metrics aggregate repository."""

from __future__ import annotations

import queue as _queue
from datetime import UTC, datetime
from uuid import uuid4

from air_platform.ingestion.consumer import ConsumerRunner
from air_platform.ingestion.handler import EventHandler
from air_platform.repositories.errors import InMemoryErrorRepository
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.in_memory_queue import InMemoryQueueTransport
from tests.constants import SCHEMA_PATH

_STATION = "station-1"
_DEVICE = "device-a"
_METRIC = "discharge_pressure"
_BUCKET = "hour"
_BUCKET_START = datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC)
_TS = datetime(2024, 2, 1, 10, 5, 0, tzinfo=UTC)


def _make_repo() -> InMemoryMetricsAggregateRepository:
    return InMemoryMetricsAggregateRepository()


def _upsert(
    repo: InMemoryMetricsAggregateRepository,
    value: float,
    *,
    event_id: str | None = None,
) -> None:
    """Convenience wrapper for upserts using the shared test constants."""
    repo.upsert_aggregate(
        _STATION,
        _DEVICE,
        _METRIC,
        _BUCKET,
        _BUCKET_START,
        value,
        _TS,
        event_id=event_id,
    )


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


def _make_handler_and_repo() -> tuple[EventHandler, InMemoryMetricsAggregateRepository]:
    """Return a fresh handler/repo pair sharing the same metrics store."""
    metrics_repo = InMemoryMetricsAggregateRepository()
    status_repo = InMemoryProcessingStatusRepository()
    handler = EventHandler(
        schema_path=SCHEMA_PATH,
        metrics_aggregate_repo=metrics_repo,
        status_repo=status_repo,
    )
    return handler, metrics_repo


def _sensor_event(event_id: str, station_id: str = "s-dedup") -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "sensor_reading",
        "timestamp": "2024-02-01T10:05:00+00:00",
        "station_id": station_id,
        "device_id": "d-dedup",
        "readings": {
            "discharge_pressure": 8.5,
            "air_flow_rate": 100.0,
            "power_consumption": 55.0,
            "motor_speed": 1500,
            "discharge_temp": 45.0,
        },
    }


def _run_events(
    handler: EventHandler,
    metrics_repo: InMemoryMetricsAggregateRepository,
    events: list[dict[str, object]],
) -> None:
    """Push events through the consumer using a fresh queue per call."""
    status_repo = InMemoryProcessingStatusRepository()
    for event in events:
        q: _queue.Queue[dict[str, object] | None] = _queue.Queue()
        q.put(event)
        runner = ConsumerRunner(
            InMemoryQueueTransport(q),
            handler,
            status_repo,
            InMemoryErrorRepository(),
        )
        runner.run_until_empty()


class TestEventIdDeduplication:
    """Regression: duplicate / replayed events must not inflate aggregates.

    Deduplication is enforced at the EventHandler level, not in the repo.
    The same EventHandler instance must be reused for dedup to apply across
    multiple deliveries (which is exactly what the single-process consumer
    architecture provides).
    """

    def test_duplicate_event_id_is_ignored(self):
        """Re-delivering the same event_id must leave aggregates unchanged."""
        handler, metrics_repo = _make_handler_and_repo()
        event = _sensor_event("evt-abc-123")
        _run_events(handler, metrics_repo, [event, event])

        results = metrics_repo.query("s-dedup", metric_type="discharge_pressure", bucket="hour")
        assert len(results) == 1
        agg = results[0]
        assert agg.count == 1, "Duplicate event must not increment count"
        assert agg.total == 8.5
        assert agg.avg == 8.5

    def test_different_event_ids_are_both_applied(self):
        """Two distinct event_ids must produce a count of 2."""
        handler, metrics_repo = _make_handler_and_repo()
        _run_events(
            handler,
            metrics_repo,
            [_sensor_event("evt-1"), _sensor_event("evt-2")],
        )

        results = metrics_repo.query("s-dedup", metric_type="discharge_pressure", bucket="hour")
        assert results[0].count == 2

    def test_replay_stream_produces_same_aggregate_as_single_pass(self):
        """Replaying a full stream through the same handler must not change aggregates."""
        handler, metrics_repo = _make_handler_and_repo()
        events = [_sensor_event(f"evt-{i}") for i in range(3)]
        _run_events(handler, metrics_repo, events)
        first = metrics_repo.query("s-dedup", metric_type="discharge_pressure", bucket="hour")
        count_after_first = first[0].count

        # Replay the same events — handler has seen all event_ids.
        _run_events(handler, metrics_repo, events)
        replayed = metrics_repo.query("s-dedup", metric_type="discharge_pressure", bucket="hour")
        assert replayed[0].count == count_after_first, "Replay must not change aggregate count"

    def test_upsert_aggregate_without_event_id_is_not_deduplicated(self):
        """Direct upsert calls without event_id are never deduplicated (repo is stateless)."""
        repo = _make_repo()
        _upsert(repo, 8.0)
        _upsert(repo, 8.0)

        agg = repo.query(_STATION)[0]
        assert agg.count == 2

    def test_end_to_end_consumer_replay_is_idempotent(self):
        """Processing the same event twice via the consumer must not change metrics."""
        shared_event_id = str(uuid4())
        event = _sensor_event(shared_event_id)

        handler, metrics_repo = _make_handler_and_repo()

        def _run_once() -> None:
            q: _queue.Queue[dict[str, object] | None] = _queue.Queue()
            q.put(event)
            runner = ConsumerRunner(
                InMemoryQueueTransport(q),
                handler,
                InMemoryProcessingStatusRepository(),
                InMemoryErrorRepository(),
            )
            runner.run_until_empty()

        _run_once()
        results_after_first = metrics_repo.query("s-dedup")
        assert len(results_after_first) > 0
        first_count = results_after_first[0].count

        # Replay (same event_id) — aggregate must be unchanged.
        _run_once()
        results_after_replay = metrics_repo.query("s-dedup")
        assert results_after_replay[0].count == first_count, (
            "Replaying the same event_id must not increment the aggregate count"
        )
