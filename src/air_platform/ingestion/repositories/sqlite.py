"""SQLite implementation of the raw sensor repository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from air_platform.errors import StorageError
from air_platform.ingestion.models import StationMetadata


def _to_utc_naive_iso(dt: datetime) -> str:
    """Normalise *dt* to UTC and strip tzinfo before converting to ISO string.

    SQLite stores timestamps as plain text and compares them lexicographically.
    Supplying a tz-aware string like ``2024-01-01T01:00:00+01:00`` would sort
    differently than the equivalent UTC string ``2024-01-01T00:00:00``, so we
    always normalise to naive-UTC before building query parameters.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat()


class SQLiteSensorDataRepository:
    """Load raw readings and station metadata from SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def fetch_sensor_readings(
        self,
        station_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        query = """
            SELECT
                timestamp,
                station_id,
                device_id,
                discharge_pressure,
                air_flow_rate,
                power_consumption,
                motor_speed,
                discharge_temp
            FROM sensor_readings
            WHERE station_id = ?
        """
        parameters: list[str] = [station_id]
        if start_time is not None:
            query += " AND timestamp >= ?"
            parameters.append(_to_utc_naive_iso(start_time))
        if end_time is not None:
            query += " AND timestamp <= ?"
            parameters.append(_to_utc_naive_iso(end_time))
        query += " ORDER BY device_id, timestamp"

        try:
            with sqlite3.connect(self.db_path) as connection:
                return pd.read_sql_query(query, connection, params=tuple(parameters))
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to fetch sensor readings for station {station_id}") from exc

    def fetch_station_metadata(self, station_id: str) -> StationMetadata | None:
        query = """
            SELECT
                station_id,
                station_name,
                location,
                commissioned_date,
                num_compressors
            FROM station_metadata
            WHERE station_id = ?
        """
        try:
            with sqlite3.connect(self.db_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(query, (station_id,)).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to fetch station metadata for station {station_id}"
            ) from exc

        if row is None:
            return None

        return StationMetadata(
            station_id=str(row["station_id"]),
            station_name=str(row["station_name"]),
            location=str(row["location"]),
            commissioned_date=str(row["commissioned_date"]),
            num_compressors=int(row["num_compressors"]),
        )
