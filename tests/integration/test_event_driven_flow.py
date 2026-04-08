"""Integration tests for the full event-driven flow.

Tests the complete path:
  queue → transport → consumer → handler → repositories → API

Uses real in-memory components; no mocks.
"""

from __future__ import annotations

import queue
from uuid import uuid4

import pytest

from air_platform.bootstrap.container import AppContainer
from air_platform.ingestion.consumer import ConsumerRunner
from air_platform.ingestion.handler import EventHandler
from air_platform.repositories.errors import InMemoryErrorRepository
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.in_memory_queue import InMemoryQueueTransport
from tests.constants import SCHEMA_PATH

_STATION = "station-1"
_DEVICE = "device-a"


def _good_event(
    station_id: str = _STATION,
    device_id: str = _DEVICE,
    ts: str = "2024-02-01T10:05:00+00:00",
) -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "event_type": "sensor_reading",
        "timestamp": ts,
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


@pytest.fixture
def runner_components():
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


class TestQueueToRepository:
    def test_event_produces_hour_and_day_aggregates(self, runner_components):
        runner, q, metrics_repo, _, _ = runner_components
        q.put(_good_event())
        runner.run_until_empty()
        hour_aggs = metrics_repo.query(_STATION, bucket="hour")
        day_aggs = metrics_repo.query(_STATION, bucket="day")
        assert len(hour_aggs) == 5  # 5 sensor columns
        assert len(day_aggs) == 5

    def test_multiple_devices_aggregated_independently(self, runner_components):
        runner, q, metrics_repo, _, _ = runner_components
        q.put(_good_event(device_id="device-a"))
        q.put(_good_event(device_id="device-b"))
        runner.run_until_empty()
        results = metrics_repo.query(_STATION, bucket="hour")
        devices = {r.device_id for r in results}
        assert devices == {"device-a", "device-b"}

    def test_multiple_hours_stored_in_separate_buckets(self, runner_components):
        runner, q, metrics_repo, _, _ = runner_components
        q.put(_good_event(ts="2024-02-01T10:05:00+00:00"))
        q.put(_good_event(ts="2024-02-01T11:15:00+00:00"))
        runner.run_until_empty()
        hour_aggs = metrics_repo.query(_STATION, metric_type="discharge_pressure", bucket="hour")
        assert len(hour_aggs) == 2  # two different hour buckets

    def test_same_hour_accumulates_into_one_bucket(self, runner_components):
        runner, q, metrics_repo, _, _ = runner_components
        q.put(_good_event(ts="2024-02-01T10:05:00+00:00"))
        q.put(_good_event(ts="2024-02-01T10:30:00+00:00"))
        runner.run_until_empty()
        hour_aggs = metrics_repo.query(_STATION, metric_type="discharge_pressure", bucket="hour")
        assert len(hour_aggs) == 1
        assert hour_aggs[0].count == 2

    def test_malformed_event_does_not_affect_good_events(self, runner_components):
        runner, q, metrics_repo, status_repo, _ = runner_components
        q.put({"garbage": "data"})
        q.put(_good_event())
        runner.run_until_empty()
        assert metrics_repo.query(_STATION) != []
        assert status_repo.get_status().events_processed_successfully == 1

    def test_status_tracks_all_outcomes(self, runner_components):
        runner, q, _, status_repo, _ = runner_components
        q.put(_good_event())
        q.put({"garbage": "data"})
        q.put(_good_event(station_id="station-2"))
        runner.run_until_empty()
        status = status_repo.get_status()
        assert status.events_consumed == 3
        assert status.events_processed_successfully == 2
        assert status.events_malformed == 1


class TestAppContainer:
    def test_build_creates_all_components(self):
        container = AppContainer.build(SCHEMA_PATH)
        assert container.event_queue is not None
        assert container.transport is not None
        assert container.metrics_aggregate_repo is not None
        assert container.status_repo is not None
        assert container.error_repo is not None
        assert container.consumer is not None

    def test_consumer_processes_event_end_to_end(self):
        container = AppContainer.build(SCHEMA_PATH)
        container.event_queue.put(_good_event())
        container.consumer.run_until_empty()
        results = container.metrics_aggregate_repo.query(_STATION)
        assert len(results) > 0


class TestAPIEndpoints:
    def test_processing_status_endpoint(self, app_settings):
        from fastapi.testclient import TestClient

        from air_platform.service.app import create_app

        with TestClient(create_app(app_settings)) as client:
            response = client.get("/processing/status")
            assert response.status_code == 200
            data = response.json()
            assert "consumer_running" in data
            assert "events_consumed" in data

    def test_processing_errors_endpoint_empty(self, app_settings):
        from fastapi.testclient import TestClient

        from air_platform.service.app import create_app

        with TestClient(create_app(app_settings)) as client:
            response = client.get("/processing/errors")
            assert response.status_code == 200
            assert response.json() == []

    def test_stream_metrics_endpoint_empty(self, app_settings):
        from fastapi.testclient import TestClient

        from air_platform.service.app import create_app

        with TestClient(create_app(app_settings)) as client:
            response = client.get(f"/metrics/stations/{_STATION}")
            assert response.status_code == 200
            assert response.json() == []

    def test_stream_metrics_populated_after_events(self, app_settings):
        from fastapi.testclient import TestClient

        from air_platform.service.app import create_app

        app = create_app(app_settings)
        with TestClient(app) as client:
            # Put an event into the container's queue and process it
            container = app.state.container
            container.event_queue.put(_good_event())
            container.consumer.run_until_empty()

            response = client.get(f"/metrics/stations/{_STATION}")
            assert response.status_code == 200
            data = response.json()
            assert len(data) > 0
            assert data[0]["station_id"] == _STATION

    def test_stream_metrics_filter_by_device(self, app_settings):
        from fastapi.testclient import TestClient

        from air_platform.service.app import create_app

        app = create_app(app_settings)
        with TestClient(app) as client:
            container = app.state.container
            container.event_queue.put(_good_event(device_id="device-a"))
            container.event_queue.put(_good_event(device_id="device-b"))
            container.consumer.run_until_empty()

            response = client.get(f"/metrics/stations/{_STATION}?device_id=device-a")
            assert response.status_code == 200
            data = response.json()
            assert all(r["device_id"] == "device-a" for r in data)

    def test_processing_errors_populated_after_bad_event(self, app_settings):
        from fastapi.testclient import TestClient

        from air_platform.service.app import create_app

        app = create_app(app_settings)
        with TestClient(app) as client:
            container = app.state.container
            container.event_queue.put({"garbage": "data"})
            container.consumer.run_until_empty()

            response = client.get("/processing/errors")
            assert response.status_code == 200
            errors = response.json()
            assert len(errors) == 1
            assert errors[0]["error_type"] == "malformed_event"
