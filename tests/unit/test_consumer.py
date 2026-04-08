"""Unit tests for the ConsumerRunner."""

from __future__ import annotations

import queue
from uuid import uuid4

from air_platform.ingestion.consumer import ConsumerRunner
from air_platform.ingestion.handler import EventHandler
from air_platform.repositories.errors import InMemoryErrorRepository
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.in_memory_queue import InMemoryQueueTransport
from tests.constants import SCHEMA_PATH


def _make_runner() -> tuple[
    ConsumerRunner,
    queue.Queue[dict[str, object] | None],
    InMemoryMetricsAggregateRepository,
    InMemoryProcessingStatusRepository,
    InMemoryErrorRepository,
]:
    q: queue.Queue[dict[str, object] | None] = queue.Queue()
    transport = InMemoryQueueTransport(q)
    metrics_repo = InMemoryMetricsAggregateRepository()
    status_repo = InMemoryProcessingStatusRepository()
    error_repo = InMemoryErrorRepository()
    handler = EventHandler(
        schema_path=SCHEMA_PATH,
        metrics_aggregate_repo=metrics_repo,
        status_repo=status_repo,
    )
    runner = ConsumerRunner(
        transport=transport,
        handler=handler,
        status_repo=status_repo,
        error_repo=error_repo,
    )
    return runner, q, metrics_repo, status_repo, error_repo


def _good_event(station_id: str = "station-1", device_id: str = "device-a") -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "event_type": "sensor_reading",
        "timestamp": "2024-02-01T10:05:00+00:00",
        "station_id": station_id,
        "device_id": device_id,
        "readings": {
            "discharge_pressure": 8.5,
            "air_flow_rate": 100.0,
            "power_consumption": 55.0,
            "motor_speed": 1500,
            "discharge_temp": 45.0,
        },
    }


def _malformed_event() -> dict[str, object]:
    return {"event_id": str(uuid4()), "garbage": "data"}


class TestConsumerRunUntilEmpty:
    def test_processes_single_valid_event(self):
        runner, q, metrics_repo, status_repo, _ = _make_runner()
        q.put(_good_event())
        runner.run_until_empty()
        assert status_repo.get_status().events_consumed == 1
        assert status_repo.get_status().events_processed_successfully == 1

    def test_processes_multiple_valid_events(self):
        runner, q, _, status_repo, _ = _make_runner()
        for _ in range(5):
            q.put(_good_event())
        runner.run_until_empty()
        assert status_repo.get_status().events_consumed == 5
        assert status_repo.get_status().events_processed_successfully == 5

    def test_malformed_event_recorded_and_loop_continues(self):
        runner, q, _, status_repo, error_repo = _make_runner()
        q.put(_malformed_event())
        q.put(_good_event())
        runner.run_until_empty()
        status = status_repo.get_status()
        assert status.events_consumed == 2
        assert status.events_malformed == 1
        assert status.events_processed_successfully == 1
        errors = error_repo.get_recent()
        assert len(errors) == 1
        assert errors[0].error_type == "malformed_event"

    def test_wrong_event_type_counted_as_failed(self):
        runner, q, _, status_repo, error_repo = _make_runner()
        bad = _good_event()
        bad["event_type"] = "alarm"
        q.put(bad)
        runner.run_until_empty()
        status = status_repo.get_status()
        assert status.events_failed == 1
        assert len(error_repo.get_recent()) == 1

    def test_empty_queue_returns_immediately(self):
        runner, _, _, status_repo, _ = _make_runner()
        runner.run_until_empty()
        assert status_repo.get_status().events_consumed == 0

    def test_aggregates_populated_after_processing(self):
        runner, q, metrics_repo, _, _ = _make_runner()
        q.put(_good_event(station_id="s1", device_id="d1"))
        runner.run_until_empty()
        results = metrics_repo.query("s1")
        assert len(results) > 0

    def test_sentinel_none_stops_loop(self):
        runner, q, _, status_repo, _ = _make_runner()
        q.put(_good_event())
        q.put(None)  # sentinel
        runner.run_until_empty()
        # Only 1 real event processed; sentinel is handled transparently
        assert status_repo.get_status().events_consumed == 1


class TestConsumerBackground:
    def test_start_and_stop(self):
        runner, q, _, status_repo, _ = _make_runner()
        runner.start_background()
        assert status_repo.get_status().consumer_running is True
        runner.stop()
        assert status_repo.get_status().consumer_running is False

    def test_start_twice_is_idempotent(self):
        runner, q, _, status_repo, _ = _make_runner()
        runner.start_background()
        runner.start_background()  # should not raise or start second thread
        runner.stop()

    def test_run_loop_exits_on_sentinel_without_explicit_stop(self):
        """run_loop must terminate by itself after the producer sentinel is received.

        Regression test for the bug where sentinel_received=True but consumer_running
        stayed True because run_loop never checked the sentinel flag.
        """
        runner, q, _, status_repo, _ = _make_runner()
        q.put(_good_event())
        q.put(None)  # end-of-stream sentinel
        runner.start_background()

        assert runner._thread is not None
        runner._thread.join(timeout=3.0)

        assert not runner._thread.is_alive(), (
            "run_loop did not exit after the sentinel — sentinel_received was ignored"
        )
        assert status_repo.get_status().consumer_running is False
        assert status_repo.get_status().events_consumed == 1
