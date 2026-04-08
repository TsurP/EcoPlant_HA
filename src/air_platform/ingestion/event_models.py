"""Models for raw queue events and the internal sensor reading domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Raw event models (Pydantic) — represent the wire format from the producer
# ---------------------------------------------------------------------------


class RawSensorEvent(BaseModel):
    """Parsed representation of a raw queue event dict.

    Validation here is structural only: field presence and basic types.
    Business validation (event_type, value ranges) happens in the parser.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: str
    event_type: str
    timestamp: str
    station_id: str
    device_id: str
    readings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal domain model — passed through the processing pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensorReading:
    """Single sensor reading mapped from a validated queue event.

    Values are already coerced to float | None. None means the value was
    absent, malformed, or nullified by range validation.
    """

    timestamp: datetime
    station_id: str
    device_id: str
    discharge_pressure: float | None = None
    air_flow_rate: float | None = None
    power_consumption: float | None = None
    motor_speed: float | None = None
    discharge_temp: float | None = None

    def sensor_values(self) -> dict[str, float | None]:
        """Return all sensor fields as a column-name → value mapping."""
        return {
            "discharge_pressure": self.discharge_pressure,
            "air_flow_rate": self.air_flow_rate,
            "power_consumption": self.power_consumption,
            "motor_speed": self.motor_speed,
            "discharge_temp": self.discharge_temp,
        }
