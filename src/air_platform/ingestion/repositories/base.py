"""Repository interfaces for raw sensor data."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd

from air_platform.ingestion.models import StationMetadata


class SensorDataRepository(Protocol):
    """Abstract repository for raw sensor data."""

    def fetch_sensor_readings(
        self,
        station_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Return raw sensor readings for a station."""

    def fetch_station_metadata(self, station_id: str) -> StationMetadata | None:
        """Return station metadata if it exists."""
