"""Unit tests for the event parser and mapper."""

from __future__ import annotations

from uuid import uuid4

import pytest

from air_platform.ingestion.errors import EventValidationError, MalformedEventError
from air_platform.ingestion.parser import map_to_sensor_reading, parse_event


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": str(uuid4()),
        "event_type": "sensor_reading",
        "timestamp": "2024-02-01T10:00:00+00:00",
        "station_id": "station-1",
        "device_id": "device-a",
        "readings": {
            "discharge_pressure": 8.5,
            "air_flow_rate": 100.0,
            "power_consumption": 55.0,
            "motor_speed": 1500,
            "discharge_temp": 45.0,
        },
        "metadata": {},
    }
    payload.update(overrides)
    return payload


class TestParseEvent:
    def test_valid_event_parses_successfully(self):
        event = parse_event(_valid_payload())
        assert event.station_id == "station-1"
        assert event.device_id == "device-a"
        assert event.event_type == "sensor_reading"

    def test_missing_required_field_raises_malformed(self):
        payload = _valid_payload()
        del payload["station_id"]
        with pytest.raises(MalformedEventError):
            parse_event(payload)

    def test_missing_device_id_raises_malformed(self):
        payload = _valid_payload()
        del payload["device_id"]
        with pytest.raises(MalformedEventError):
            parse_event(payload)

    def test_missing_timestamp_raises_malformed(self):
        payload = _valid_payload()
        del payload["timestamp"]
        with pytest.raises(MalformedEventError):
            parse_event(payload)

    def test_corrupt_payload_raises_malformed(self):
        with pytest.raises(MalformedEventError):
            parse_event({"garbage": "data", "random_number": 42})

    def test_wrong_event_type_raises_validation_error(self):
        with pytest.raises(EventValidationError, match="event_type"):
            parse_event(_valid_payload(event_type="station_alarm"))

    def test_extra_fields_are_ignored(self):
        payload = _valid_payload()
        payload["unexpected_field"] = "ignored"
        event = parse_event(payload)
        assert event.station_id == "station-1"

    def test_empty_readings_dict_is_accepted(self):
        event = parse_event(_valid_payload(readings={}))
        assert event.readings == {}


class TestMapToSensorReading:
    def test_all_values_mapped(self):
        event = parse_event(_valid_payload())
        reading = map_to_sensor_reading(event)
        assert reading.station_id == "station-1"
        assert reading.device_id == "device-a"
        assert reading.discharge_pressure == pytest.approx(8.5)
        assert reading.air_flow_rate == pytest.approx(100.0)
        assert reading.motor_speed == pytest.approx(1500.0)

    def test_non_numeric_values_coerced_to_none(self):
        payload = _valid_payload(
            readings={
                "discharge_pressure": "not_a_number",
                "air_flow_rate": [1, 2, 3],
                "power_consumption": None,
            }
        )
        event = parse_event(payload)
        reading = map_to_sensor_reading(event)
        assert reading.discharge_pressure is None
        assert reading.air_flow_rate is None
        assert reading.power_consumption is None

    def test_missing_readings_default_to_none(self):
        event = parse_event(_valid_payload(readings={}))
        reading = map_to_sensor_reading(event)
        assert reading.discharge_pressure is None
        assert reading.motor_speed is None

    def test_bad_timestamp_raises_validation_error(self):
        payload = _valid_payload(timestamp="not-a-date")
        event = parse_event(payload)
        with pytest.raises(EventValidationError, match="timestamp"):
            map_to_sensor_reading(event)

    def test_sensor_values_dict_has_all_columns(self):
        event = parse_event(_valid_payload())
        reading = map_to_sensor_reading(event)
        keys = set(reading.sensor_values().keys())
        assert keys == {
            "discharge_pressure",
            "air_flow_rate",
            "power_consumption",
            "motor_speed",
            "discharge_temp",
        }
