"""Unit tests for the EventHandler."""

from __future__ import annotations

from uuid import uuid4

import pytest

from air_platform.ingestion.errors import EventValidationError, MalformedEventError
from air_platform.ingestion.handler import EventHandler, _floor_to_bucket
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.base import TransportMessage
from tests.constants import SCHEMA_PATH

_STATION = "station-1"
_DEVICE = "device-a"


def _make_handler() -> tuple[
    EventHandler, InMemoryMetricsAggregateRepository, InMemoryProcessingStatusRepository
]:
    metrics_repo = InMemoryMetricsAggregateRepository()
    status_repo = InMemoryProcessingStatusRepository()
    handler = EventHandler(
        schema_path=SCHEMA_PATH,
        metrics_aggregate_repo=metrics_repo,
        status_repo=status_repo,
    )
    return handler, metrics_repo, status_repo


def _make_message(**overrides: object) -> TransportMessage:
    payload: dict[str, object] = {
        "event_id": str(uuid4()),
        "event_type": "sensor_reading",
        "timestamp": "2024-02-01T10:05:00+00:00",
        "station_id": _STATION,
        "device_id": _DEVICE,
        "readings": {
            "discharge_pressure": 8.5,
            "air_flow_rate": 100.0,
            "power_consumption": 55.0,
            "motor_speed": 1500,
            "discharge_temp": 45.0,
        },
    }
    payload.update(overrides)
    return TransportMessage(id=str(payload.get("event_id", "")), payload=payload)


class TestHandlerSuccessPath:
    def test_valid_event_updates_aggregates(self):
        handler, metrics_repo, _ = _make_handler()
        handler.handle(_make_message())
        results = metrics_repo.query(_STATION)
        # 5 sensors × 2 buckets = 10 aggregate entries
        assert len(results) == 10

    def test_aggregates_have_correct_station_and_device(self):
        handler, metrics_repo, _ = _make_handler()
        handler.handle(_make_message())
        for agg in metrics_repo.query(_STATION):
            assert agg.station_id == _STATION
            assert agg.device_id == _DEVICE

    def test_out_of_range_value_excluded_from_aggregates(self):
        handler, metrics_repo, _ = _make_handler()
        # discharge_pressure valid range per schema is 0–25 bar; 999 is out of range
        handler.handle(_make_message(readings={"discharge_pressure": 999.0}))
        results = metrics_repo.query(_STATION, metric_type="discharge_pressure")
        assert results == []

    def test_multiple_readings_accumulate(self):
        handler, metrics_repo, _ = _make_handler()
        for _ in range(3):
            handler.handle(
                _make_message(
                    readings={"discharge_pressure": 8.0},
                    event_id=str(uuid4()),
                )
            )
        agg = metrics_repo.query(_STATION, metric_type="discharge_pressure", bucket="hour")
        assert len(agg) == 1
        assert agg[0].count == 3
        assert agg[0].avg == pytest.approx(8.0)


class TestHandlerErrorPaths:
    def test_malformed_payload_raises_malformed_event_error(self):
        handler, _, _ = _make_handler()
        msg = TransportMessage(id="x", payload={"garbage": "data"})
        with pytest.raises(MalformedEventError):
            handler.handle(msg)

    def test_wrong_event_type_raises_validation_error(self):
        handler, _, _ = _make_handler()
        msg = _make_message(event_type="alarm")
        with pytest.raises(EventValidationError):
            handler.handle(msg)

    def test_bad_timestamp_raises_validation_error(self):
        handler, _, _ = _make_handler()
        payload = {
            "event_id": str(uuid4()),
            "event_type": "sensor_reading",
            "timestamp": "not-a-date",
            "station_id": _STATION,
            "device_id": _DEVICE,
            "readings": {"discharge_pressure": 8.0},
        }
        msg = TransportMessage(id="x", payload=payload)
        with pytest.raises(EventValidationError):
            handler.handle(msg)

    def test_all_null_readings_creates_no_aggregates(self):
        handler, metrics_repo, _ = _make_handler()
        handler.handle(
            _make_message(
                readings={
                    "discharge_pressure": None,
                    "air_flow_rate": None,
                    "power_consumption": None,
                    "motor_speed": None,
                    "discharge_temp": None,
                }
            )
        )
        assert metrics_repo.query(_STATION) == []


class TestFloorToBucket:
    def test_floor_to_hour(self):
        from datetime import UTC, datetime

        dt = datetime(2024, 2, 1, 10, 37, 45, tzinfo=UTC)
        result = _floor_to_bucket(dt, "hour")
        assert result == datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC)

    def test_floor_to_day(self):
        from datetime import UTC, datetime

        dt = datetime(2024, 2, 1, 15, 37, 45, tzinfo=UTC)
        result = _floor_to_bucket(dt, "day")
        assert result == datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)

    def test_unknown_bucket_raises(self):
        from datetime import UTC, datetime

        with pytest.raises(ValueError, match="Unknown bucket"):
            _floor_to_bucket(datetime(2024, 2, 1, tzinfo=UTC), "week")
