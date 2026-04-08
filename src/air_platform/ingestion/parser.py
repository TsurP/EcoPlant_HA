"""Parse and map raw queue event dicts into internal domain models.

Flow:
  raw dict (from transport)
  → RawSensorEvent  (Pydantic structural validation)
  → SensorReading   (domain model with coerced values)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from air_platform.ingestion.errors import EventValidationError, MalformedEventError
from air_platform.ingestion.event_models import RawSensorEvent, SensorReading

_EXPECTED_EVENT_TYPE = "sensor_reading"
_SENSOR_FIELDS = (
    "discharge_pressure",
    "air_flow_rate",
    "power_consumption",
    "motor_speed",
    "discharge_temp",
)


def parse_event(payload: dict[str, Any]) -> RawSensorEvent:
    """Deserialize a raw payload dict into a ``RawSensorEvent``.

    Raises:
        MalformedEventError: if the payload is structurally invalid.
        EventValidationError: if the event type is not "sensor_reading".
    """
    try:
        event = RawSensorEvent.model_validate(payload)
    except PydanticValidationError as exc:
        raise MalformedEventError(f"Event failed structural validation: {exc}") from exc

    if event.event_type != _EXPECTED_EVENT_TYPE:
        raise EventValidationError(
            f"Unexpected event_type '{event.event_type}'; expected '{_EXPECTED_EVENT_TYPE}'"
        )

    return event


def map_to_sensor_reading(event: RawSensorEvent) -> SensorReading:
    """Map a validated ``RawSensorEvent`` to an internal ``SensorReading``.

    Raises:
        EventValidationError: if the timestamp cannot be parsed.
    """
    timestamp = _parse_timestamp(event.timestamp)

    readings = event.readings
    return SensorReading(
        timestamp=timestamp,
        station_id=event.station_id,
        device_id=event.device_id,
        discharge_pressure=_coerce_float(readings.get("discharge_pressure")),
        air_flow_rate=_coerce_float(readings.get("air_flow_rate")),
        power_consumption=_coerce_float(readings.get("power_consumption")),
        motor_speed=_coerce_float(readings.get("motor_speed")),
        discharge_temp=_coerce_float(readings.get("discharge_temp")),
    )


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp string, raising EventValidationError on failure."""
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise EventValidationError(f"Unreadable timestamp: {value!r}") from exc


def _coerce_float(value: Any) -> float | None:
    """Coerce a raw reading value to float, returning None for non-numeric inputs."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
